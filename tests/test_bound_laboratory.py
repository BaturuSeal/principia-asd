import copy
import json

import pytest
from test_bound_checkpoint import PowerLoss
from test_bound_engine import fixture

from principia_asd.engine.bound_checkpoint import DurableBoundRun, RecoveryRequired
from principia_asd.engine.bound_laboratory import ROLES, STAGES, BoundLaboratory
from principia_asd.evaluate.bound import evaluate_bound_nominations
from principia_asd.io import read_json, sha
from principia_asd.methods.registry import DEFAULT_ROLES


class LaboratoryGateway:
    """Scripted engineering fixture, no provider access or scientific trial."""

    def __init__(self, transform=None, crash_after=None):
        self.calls, self.receipts, self.recovered = [], {}, []
        self.transform, self.crash_after = transform, crash_after

    def complete(self, **request):
        assert request["request_id"] not in self.receipts, "paid call replayed"
        self.calls.append(copy.deepcopy(request))
        c = json.loads(request["prompt"])
        stage = c["laboratory_stage"]
        out = {
            "research_brief": {
                "question": "Saturation?",
                "hypotheses": ["linear", "saturating"],
                "limitations": ["synthetic"],
            },
            "experiment_plan": {
                "objective": "Compare structures",
                "experiments": ["fit affine", "revise using residuals"],
                "selection_criterion": "dev rmse",
                "risks": ["nonidentifiability"],
            },
            "initial_engineering": {
                "expression": "p0+p1*normalized_0",
                "initial": {"p0": 0, "p1": 1},
            },
            "experimental_critique": {
                "experiment_ids": ["experiment-1"],
                "issues": ["nonlinear residual"],
                "revision": "test saturation",
            },
            "revised_engineering": {
                "expression": "p0+p1*tanh(normalized_0)",
                "initial": {"p0": 0, "p1": 1},
            },
            "evidence_report": {
                "summary": "Executed two synthetic structures",
                "experiment_ids": ["experiment-1", "experiment-2"],
                "candidate_ids": [
                    s["candidate_id"]
                    for s in c.get("frozen_evidence", {})
                    .get("selection", {})
                    .get("nominations", [])
                    if s["candidate_id"]
                ],
                "limitations": ["synthetic, not discovery"],
                "observed_cohort": c["cohort"]["verified_counts"],
            },
        }[stage]
        if self.transform:
            out = self.transform(stage, out, c)
        response = {
            "text": json.dumps(out),
            "model": request["model"],
            "request_id": request["request_id"],
        }
        self.receipts[request["request_id"]] = (sha(request), response)
        if len(self.calls) == self.crash_after:
            self.crash_after = None
            raise PowerLoss()
        return response

    def recover_completed(self, **request):
        digest, response = self.receipts[request["request_id"]]
        assert sha(request) == digest
        self.recovered.append(request["request_id"])
        return copy.deepcopy(response)


def make(gateway=None, **kwargs):
    return BoundLaboratory(
        *fixture(), gateway=gateway or LaboratoryGateway(), run_id="laboratory-fixture", **kwargs
    )


def test_handoffs_use_executed_feedback_with_only_two_fits():
    g = LaboratoryGateway()
    e = make(g)
    out = e.run()
    assert out["status"] == "complete", out["failure"]
    assert all(out["conformance"].values())
    assert out["host_submission"]["accounting"]["fitting_attempts"] == 2
    assert len(out["host_submission"]["candidates"]) == 2
    assert [c["model"] for c in g.calls] == [DEFAULT_ROLES[r] for r in ROLES]
    assert [h["name"] for h in out["handoffs"]] == list(STAGES)
    assert out["configuration"]["weak_prior_fits"] == 0
    for index, call in enumerate(g.calls):
        ctx = json.loads(call["prompt"])
        assert out["handoffs"][index]["input_sha256"] == sha(ctx)
        assert ctx["preceding_handoffs"] == out["handoffs"][:index]
        assert "test_secret" not in call["prompt"] and "canary" not in call["prompt"]
        assert ctx["cohort"]["verified_counts"]["training_rows"] == 7
    assert json.loads(g.calls[3]["prompt"])["experiments"] == out["experiments"][:1]
    assert (
        json.loads(g.calls[4]["prompt"])["preceding_handoffs"][-1]["output"]["revision"]
        == "test saturation"
    )
    assert json.loads(g.calls[5]["prompt"])["experiments"] == out["experiments"]
    assert all(
        c["simplicity"]["train_statistic_scalars"] == 2
        for c in out["host_submission"]["candidates"]
    )
    assert sum(s["status"] == "unfilled" for s in out["selection"]["nominations"]) == 1
    assert e.run() == out and len(g.calls) == 6


@pytest.mark.parametrize(
    "initial", ["0.123*x", "unknown_state*x", "__import__('os')", "log(-abs(x))"]
)
def test_invalid_initial_is_retained_and_repair_executes(initial):
    def alter(stage, data, ctx):
        return {"expression": initial, "initial": {}} if stage == "initial_engineering" else data

    g = LaboratoryGateway(alter)
    out = make(g).run()
    assert out["status"] == "complete", out["failure"]
    assert out["experiments"][0]["failures"]
    assert out["experiments"][1]["result"]
    assert json.loads(g.calls[3]["prompt"])["experiments"][0]["failures"]


@pytest.mark.parametrize(
    "kind",
    [
        "duplicate",
        "rename",
        "expanded_alias",
        "invented_critique",
        "wrong_cohort",
        "wrong_report_ids",
        "empty_brief",
        "extra_state",
    ],
)
def test_missing_behavior_cannot_pass_conformance(kind):
    def alter(stage, data, ctx):
        if stage == "revised_engineering" and kind in {"duplicate", "rename", "expanded_alias"}:
            if kind == "duplicate":
                return {"expression": "p0+p1*normalized_0", "initial": {"p0": 0, "p1": 1}}
            if kind == "rename":
                return {"expression": "p2+p3*normalized_0", "initial": {"p2": 7, "p3": 9}}
            expr = ctx["inventory"]["kernels"][0]["expression"]
            return {"expression": "p0+p1*(" + expr + ")", "initial": {"p0": 3, "p1": 4}}
        if stage == "experimental_critique" and kind == "invented_critique":
            data["experiment_ids"] = ["unexecuted"]
        if stage == "evidence_report" and kind == "wrong_cohort":
            data["observed_cohort"]["training_rows"] = 6
        if stage == "evidence_report" and kind == "wrong_report_ids":
            data["candidate_ids"] = ["invented"]
        if stage == "research_brief" and kind == "empty_brief":
            data["hypotheses"] = []
        if stage == "initial_engineering" and kind == "extra_state":
            data["fitted_state"] = 0.3
        return data

    out = make(LaboratoryGateway(alter)).run()
    assert out["status"] == "incomplete_method_execution", out["failure"]
    assert len(out["selection"]["nominations"]) == 3
    assert not out["ranking_authorized"]


def test_report_cannot_fit_and_assessment_never_refits(monkeypatch):
    g = LaboratoryGateway()
    e = make(g)

    def report_check(stage, data, ctx):
        if stage == "evidence_report":
            assert e.host.closed
            with pytest.raises(ValueError, match="frozen"):
                e.host.fit("p0", {"p0": 0})
        return data

    g.transform = report_check
    out = e.run()

    def forbidden(*a, **kw):
        pytest.fail("Final assessment called a model or fitted a rule")

    monkeypatch.setattr(e.host, "fit", forbidden)
    monkeypatch.setattr(g, "complete", forbidden)
    receipt = evaluate_bound_nominations(
        out,
        out["nomination_freeze"]["sha256"],
        [{"x": 0.5}],
        [0.45],
        expected_result_sha256=out["sha256"],
    )
    assert receipt["fixed_denominator"] == len(receipt["receipts"]) == 3
    assert receipt["api_calls"] == receipt["fitting_attempts"] == 0
    assert not receipt["ranking_authorized"]


@pytest.mark.parametrize(
    "limits", [{"max_calls": 3}, {"max_fits": 1}, {"max_optimizer_evaluations": 1}]
)
def test_budget_failure_cannot_claim_complete(limits):
    out = make(limits=limits).run()
    assert out["status"] in {"failed", "incomplete_method_execution"}
    assert len(out["selection"]["nominations"]) == 3
    assert out["model_requests"] <= limits.get("max_calls", 6)
    assert out["host_submission"]["accounting"]["fitting_attempts"] <= limits.get("max_fits", 2)


def durable(path, gateway, hook=lambda r: None):
    return DurableBoundRun(
        make(gateway), path, provider_binding={"fixture": "zero-api"}, after_record=hook
    )


@pytest.mark.parametrize("boundary", range(10))
def test_every_committed_step_restores_without_refits_or_model_replay(tmp_path, boundary):
    g = LaboratoryGateway()

    def stop(record):
        if record["type"] == "commit" and record["sequence"] // 2 == boundary:
            raise PowerLoss()

    with pytest.raises(PowerLoss):
        durable(tmp_path, g, stop).run()
    before = read_json(sorted((tmp_path / "checkpoints").glob("*.json"))[-1])
    out = durable(tmp_path, g).run()
    assert out["status"] == "complete", out["failure"]
    assert out["host_submission"]["accounting"]["fitting_attempts"] == 2
    assert len(g.calls) == 6
    assert (
        out["host_submission"]["accounting"]["optimizer_evaluations"]
        >= before["state"]["host"]["optimizer_evaluations"]
    )
    assert durable(tmp_path, g).run() == out


@pytest.mark.parametrize("call", range(1, 7))
def test_settled_request_recovered_from_identical_cached_payload(tmp_path, call):
    g = LaboratoryGateway(crash_after=call)
    with pytest.raises(PowerLoss):
        durable(tmp_path, g).run()
    out = durable(tmp_path, g).run()
    assert out["status"] == "complete", out["failure"]
    assert len(g.calls) == 6 and len(g.recovered) == 1
    assert out["host_submission"]["accounting"]["fitting_attempts"] == 2


@pytest.mark.parametrize("name", ["initial_engineering", "experiment-1"])
def test_unknown_provider_or_local_work_is_never_replayed(tmp_path, name):
    g = LaboratoryGateway()

    def stop(record):
        if record["type"] == "intent" and record["name"] == name:
            raise PowerLoss()

    with pytest.raises(PowerLoss):
        durable(tmp_path, g, stop).run()
    count = len(g.calls)
    with pytest.raises(RecoveryRequired):
        durable(tmp_path, g).run()
    assert len(g.calls) == count


def test_cancel_before_dispatch_freezes_all_unfilled_slots():
    g = LaboratoryGateway()
    out = make(g, stopped=lambda: True).run()
    assert out["status"] == "failed" and not g.calls
    assert out["host_submission"]["accounting"]["fitting_attempts"] == 0
    assert all(s["status"] == "unfilled" for s in out["selection"]["nominations"])
