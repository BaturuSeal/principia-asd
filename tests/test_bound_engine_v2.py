import json

import pytest
from test_bound_checkpoint import PowerLoss, SettledGateway
from test_bound_engine import FixtureGateway, fixture
from test_bound_jobs import setup  # noqa: F401

from principia_asd import bound_jobs
from principia_asd.engine.bound_checkpoint import DurableBoundRun, _restore, _snapshot
from principia_asd.engine.bound_engine import BoundEngine
from principia_asd.engine.bound_engine_v2 import CONTRACTS, POLICY, SchemaBoundEngine
from principia_asd.engine.bound_worker import validate_worker_request
from principia_asd.evaluate.bound import evaluate_bound_nominations
from principia_asd.io import read_json, sha, write_json
from principia_asd.store.ledger import CostLedger


def engine(gateway=None):
    return SchemaBoundEngine(
        *fixture(), gateway=gateway or FixtureGateway(), run_id="schema-fixture"
    )


def test_new_policy_retains_algorithm_and_numerical_limits():
    gateway = FixtureGateway()
    e = engine(gateway)
    result = e.run()
    assert result["status"] == "complete" and result["policy"] == POLICY
    assert len(gateway.calls) == 7
    assert all("--bound-v2--" in c["request_id"] for c in gateway.calls)
    assert result["host_submission"]["accounting"]["fitting_attempts"] == 6
    assert result["host_submission"]["accounting"]["optimizer_evaluations"] == 46
    old = BoundEngine(*fixture(), gateway=FixtureGateway(), run_id="old-fixture").run()
    assert e.configuration["limits"] == old["configuration"]["limits"]
    assert e.configuration["sha256"] != old["configuration"]["sha256"]
    assert len(result["selection"]["nominations"]) == 3
    contexts = [json.loads(c["prompt"]) for c in gateway.calls]
    assert contexts[0]["role_contract"] == CONTRACTS["planner"]
    assert contexts[1]["role_contract"] == CONTRACTS["coder"]
    assert contexts[2]["role_contract"] == CONTRACTS["critic"]
    assert contexts[-1]["role_contract"] == CONTRACTS["reporter"]
    assert all("parameter-free" in c["system"] for c in gateway.calls)
    assert all(len((c["system"] + c["prompt"]).encode()) < 48000 for c in gateway.calls)
    task, _, rows = fixture()
    targets = [r[task["output"]] for r in rows]
    receipt = evaluate_bound_nominations(
        result,
        result["nomination_freeze"]["sha256"],
        rows,
        targets,
        expected_result_sha256=result["sha256"],
    )
    assert receipt["fixed_denominator"] == 3 and receipt["api_calls"] == 0
    assert not receipt["ranking_authorized"]


@pytest.mark.parametrize(
    "proposal",
    [
        {"name": "wrong_name", "expression": "tanh(x)"},
        {"name": "k_bad_name", "expression": "tanh(x)"},
        {"name": "k_curve", "expression": "tanh(x)", "rationale": "wrong location"},
        {"name": "k_curve", "expression": "p0*x"},
        {"name": "k_curve", "expression": "2*x"},
    ],
)
def test_prompt_revision_does_not_relax_kernel_legality(proposal):
    e = engine()
    e._initialize()
    fits = e.host.fits
    assert e._patch({"kernels": [proposal]}, 0) == []
    assert e.host.fits == fits and len(e.rejections) == 1


def test_complete_inventory_and_failure_projection_have_exact_lineage_without_refitting():
    e = engine()
    e._initialize()
    e._patch({"kernels": [{"name": "k_curve", "expression": "tanh(normalized_0)"}]}, 0)
    e._fit({"expression": "p0+p1*k_curve", "initial": {"p0": 0, "p1": 1}}, "fixture")
    e._fit({"expression": "log(x)+p0", "initial": {"p0": 0}}, "failure-fixture")
    e._patch(
        {"kernels": [{"name": "k_other", "expression": "x", "rationale": "long prose" * 1000}]}, 0
    )
    snapshot = _snapshot(e)
    context = e._context("planner", "development test")
    f = context["development_feedback"]
    assert context["inventory"] == e._inventory()
    assert len(f["candidate_archive"]) == len(e.host.candidates)
    assert f["record_counts"]["failures"] == len(e.host.failures) == 1
    assert f["failures"][0]["full_record_sha256"] == sha(e.host.failures[0])
    assert f["failures"][0]["expression"] == "log(x)+p0"
    assert f["rejected_patches"][0]["extra_fields"] == ["rationale"]
    assert f["rejected_patches"][0]["full_record_sha256"] == sha(e.rejections[0])
    assert "long prose" not in json.dumps(context)
    assert f["full_records_sha256"]["failures"] == sha(e.host.failures)
    for packet in f["candidates"]:
        card = e.host.candidates[packet["candidate_id"]]
        assert packet["program_sha256"] == card["program"]["sha256"]
        assert packet["parameters"] == card["program"]["specification"]["parameters"]
        assert packet["residuals"] == card["residuals"]
        assert (
            packet["simplicity"]["learned_scalar_count"]
            == card["simplicity"]["learned_scalar_count"]
        )
    assert _snapshot(e)["host"] == snapshot["host"]
    assert e.requests == 0
    restored = engine()
    import time

    _restore(restored, json.loads(json.dumps(snapshot, sort_keys=True)), time.time())
    assert restored._context("planner", "development test") == context


def test_oversized_context_still_fails_without_dispatch_or_slicing():
    g = FixtureGateway()
    e = engine(g)
    e.host.task["title"] = "X" * 50000
    result = e.run()
    assert result["status"] == "failed" and result["model_requests"] == 0
    assert "context exceeds" in result["failure"]["reason"]
    assert not g.calls


@pytest.mark.parametrize("call", range(1, 8))
def test_compact_payloads_recover_after_each_settled_response_without_replay(tmp_path, call):
    g = SettledGateway(crash_after=call)

    def run():
        return DurableBoundRun(engine(g), tmp_path, provider_binding={"fixture": "zero-api"}).run()

    with pytest.raises(PowerLoss):
        run()
    result = run()
    assert result["status"] == "complete", result["failure"]
    assert len(g.calls) == 7 and len(g.recovered) == 1
    assert result["host_submission"]["accounting"]["fitting_attempts"] == 6
    assert run() == result
    assert len(g.calls) == 7


def test_v1_v2_checkpoint_identity_cannot_be_interchanged(tmp_path):
    g = FixtureGateway()
    DurableBoundRun(engine(g), tmp_path, provider_binding={"fixture": "zero-api"}).run()
    old = BoundEngine(*fixture(), gateway=g, run_id="schema-fixture")
    with pytest.raises(ValueError, match="configuration changed"):
        DurableBoundRun(old, tmp_path, provider_binding={"fixture": "zero-api"}).run()
    assert len(g.calls) == 7


def test_new_worker_scope_and_recovery_id_are_explicit(setup):  # noqa: F811
    settings, scenario = setup
    folder = bound_jobs.prepare(settings, scenario, "SYNTHETIC", protocol="v2")
    req = validate_worker_request(folder, settings)[3]
    assert req["scope"] == "engineering_only_explicit_state_v2"
    assert read_json(folder / "ui.json")["protocol_revision"] == "v2"
    ledger = CostLedger(folder.parent.parent / "costs.sqlite")
    rid = folder.name + "--bound-v2--planner--1"
    ledger.reserve(rid, 2)
    ledger.record({"request_id": rid, "state": "completed", "actual_cny": 0.01})
    write_json(folder / "provider" / (sha(rid) + ".json"), {"fixture": "worker revalidates"})
    write_json(
        folder / "checkpoints/0000.json",
        {
            "type": "intent",
            "kind": "provider",
            "name": "plan-0",
            "state": {"engine": {"requests": 0}},
        },
    )
    assert bound_jobs.recovery(folder, ledger)[0]
    req["scope"] = "engineering_only_explicit_state_v3"
    write_json(folder / "request.json", req)
    with pytest.raises(ValueError, match="scope"):
        validate_worker_request(folder, settings)
    assert not bound_jobs.recovery(folder, ledger)[0]


def test_contract_copy_cannot_mutate_future_context():
    e = engine()
    e._initialize()
    context = e._context("planner", "test")
    context["role_contract"]["rules"].clear()
    assert len(e._context("planner", "test")["role_contract"]["rules"]) == 5
    assert e.configuration["role_contracts_sha256"] == sha(CONTRACTS)
