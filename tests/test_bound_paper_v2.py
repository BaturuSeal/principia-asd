import copy
import json

import pytest
from test_bound_data_to_paper import PaperGateway
from test_bound_engine import fixture
from test_paper_jobs import child, helper

from principia_asd import adapter_jobs, bound_jobs, bound_pilot, paper_jobs, paper_v2_jobs
from principia_asd.engine.bound_data_to_paper import CONTRACTS, BoundDataToPaper
from principia_asd.engine.bound_data_to_paper_v2 import FORMAT_RULES, SchemaBoundDataToPaper
from principia_asd.evaluate.bound import evaluate_bound_nominations
from principia_asd.io import file_sha, read_json, sha, write_json
from principia_asd.llm.siliconflow import PROFILES
from principia_asd.store.ledger import CostLedger


def method(gateway=None):
    return SchemaBoundDataToPaper(*fixture(), gateway=gateway or PaperGateway(), run_id="paper-v2")


def test_revision_changes_interface_without_replacing_scientific_algorithm_or_guards():
    new, old = method(), BoundDataToPaper(*fixture(), gateway=None, run_id="v1")
    for name in [
        "run",
        "_plan_guard",
        "_analysis",
        "_statistics",
        "_review_guard",
        "_report_guard",
        "_nominate",
    ]:
        assert getattr(SchemaBoundDataToPaper, name) is getattr(BoundDataToPaper, name)
    assert new.limits == old.limits and new.roles == old.roles
    assert new.configuration["contracts_sha256"] == old.configuration["contracts_sha256"]
    assert new.configuration["instructions_sha256"] == old.configuration["instructions_sha256"]
    assert new.configuration["sha256"] != old.configuration["sha256"]
    assert new.request_tag != old.request_tag and new.policy != old.policy


def test_every_stage_uses_flat_exact_fields_and_metadata_without_fitted_state_injection():
    g = PaperGateway()
    out = method(g).run()
    assert out["status"] == "complete"
    assert out["host_submission"]["accounting"]["fitting_attempts"] == 1
    for request in g.calls:
        c = json.loads(request["prompt"])
        stage = c["paper_stage"]
        assert c["exact_top_level_keys"] == sorted(CONTRACTS[stage])
        assert set(c["response_example"]) == set(CONTRACTS[stage])
        assert c["response_rules"] == FORMAT_RULES
        assert "Do not wrap" in request["system"] and "--paper-bound-v2--" in request["request_id"]
        if stage == "evidence_report":
            assert c["response_example"]["observed_cohort"] == c["cohort"]["verified_counts"]
            assert c["response_example"]["facts_sha256"] == c["computed_facts"]["sha256"]
    assessed = evaluate_bound_nominations(
        out,
        out["nomination_freeze"]["sha256"],
        [{"x": 0.5}],
        [0.45],
        expected_result_sha256=out["sha256"],
    )
    assert len(assessed["receipts"]) == 3


@pytest.mark.parametrize(
    "shape", ["wrapper", "extra", "literal_placeholder", "test_partition", "target_alias"]
)
def test_known_bad_plans_still_stop_before_any_fit_or_repair(shape):
    def change(stage, out, context):
        if stage != "analysis_plan":
            pytest.fail("Invalid plan must not reach later stages")
        if shape == "wrapper":
            return {"analysis_plan": out}
        if shape == "extra":
            return out | {"planned_model": {"expression": "x"}}
        if shape == "literal_placeholder":
            return copy.deepcopy(context["response_example"])
        if shape == "test_partition":
            return out | {"selection_partition": "test"}
        return out | {"inputs": ["y"]}

    out = method(PaperGateway(transform=change)).run()
    assert out["status"] == "incomplete_method_execution"
    assert (
        out["model_requests"] == 1 and out["host_submission"]["accounting"]["fitting_attempts"] == 0
    )
    assert len(out["selection"]["nominations"]) == 3


@pytest.mark.parametrize("crash", [2, 4, 6])
def test_v2_copied_worker_recovers_conditional_repairs_without_changing_identity(tmp_path, crash):
    settings, scenario = helper.helper().fixture(tmp_path)
    folder = paper_v2_jobs.prepare(settings, scenario)
    config, request, _ = paper_v2_jobs.verify_binding(folder, check_environment=True)
    assert request["scope"] == paper_v2_jobs.SCOPE
    with pytest.raises(ValueError, match="identity"):
        paper_jobs.verify_binding(folder)
    assert adapter_jobs.PROTOCOL_ADAPTERS["paper-v2"] == "paper_v2"
    for point, expected in [(crash, 91), (-1, 0), (-1, 0)]:
        proc = child(folder, "--case", "both_repairs", "--crash-at", str(point))
        assert proc.returncode == expected, proc.stderr.decode()[-2000:]
    out = paper_v2_jobs.verify_finished(folder, config)
    assert out["policy"] == "data-to-paper-explicit-state-v2-dev" and out["status"] == "complete"
    calls = [json.loads(s) for s in (folder / "mock-dispatches.jsonl").read_text().splitlines()]
    assert len(calls) == len({c["request_id"] for c in calls}) == 6
    assert all("--paper-bound-v2--" in c["request_id"] for c in calls)
    before = file_sha(folder / "result.json")
    bound_jobs.launch(folder)
    assert file_sha(folder / "result.json") == before


@pytest.mark.parametrize(
    "stage,role",
    [
        ("analysis_plan", "planner"),
        ("analysis_repair", "coder"),
        ("statistical_review", "critic"),
        ("report_repair", "reporter"),
    ],
)
def test_recovery_cannot_use_a_v1_paid_receipt_for_v2(tmp_path, stage, role):
    settings, scenario = helper.helper().fixture(tmp_path)
    folder = paper_v2_jobs.prepare(settings, scenario)
    write_json(
        folder / "checkpoints/0000.json",
        {"type": "intent", "kind": "provider", "name": stage, "state": {"engine": {"requests": 0}}},
    )
    ledger = CostLedger(tmp_path / "private/costs.sqlite")
    for version in ["v1", "v2"]:
        rid = f"{folder.name}--paper-bound-{version}--{role}--1"
        ledger.reserve(rid, 2)
        ledger.record({"request_id": rid, "state": "completed", "actual_cny": 0.02})
        write_json(folder / "provider" / (sha(rid) + ".json"), {"eligibility_fixture": True})
        assert bound_jobs.recovery(folder, ledger)[0] == (version == "v2")


def test_v2_pilot_is_frozen_and_keeps_fixed_nomination_slots(tmp_path, monkeypatch):
    settings, scenario = helper.helper().fixture(tmp_path)
    path = scenario / "task-contracts/task-001.json"
    task = read_json(path) | {"task_id": "SYNTHETIC.task"}
    write_json(path, task)
    monkeypatch.setattr(bound_pilot, "CASES", ("SYNTHETIC",))
    prices = {
        "rates": {m: {k: v[k] for k in ["input_rate", "output_rate"]} for m, v in PROFILES.items()}
    }
    root, manifest = bound_pilot.prepare(settings, "paper-v2-fixture", prices, protocol="paper-v2")
    assert manifest["policy"] == "explicit-state-data-to-paper-pilot-v2"
    monkeypatch.setattr(bound_pilot, "probe", lambda *a: True)

    def launch(folder):
        p = child(folder)
        assert p.returncode == 0, p.stderr.decode()

    monkeypatch.setattr(bound_jobs, "launch", launch)
    result = bound_pilot.drive(root)
    assert result["fixed_nomination_slots"] == 3 and result["nominated_slots"] == 1
    assert bound_pilot.summary(root)["costs"]["requests"] == 4
    monkeypatch.setattr(bound_jobs, "launch", lambda *a: pytest.fail("Replay"))
    assert bound_pilot.drive(root) == result
