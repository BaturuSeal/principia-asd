import copy
import json

import pytest
from test_bound_checkpoint import PowerLoss
from test_bound_engine import fixture

from principia_asd.engine.bound_asta import BoundAsta
from principia_asd.engine.bound_checkpoint import DurableBoundRun, RecoveryRequired
from principia_asd.evaluate.bound import evaluate_bound_nominations
from principia_asd.io import sha
from principia_asd.methods.registry import DEFAULT_ROLES


class AstaGateway:
    """Scripted observer samples; not live model conformance or calibrated beliefs."""

    def __init__(self, transform=None, crash_after=None):
        self.calls, self.receipts, self.recovered = [], {}, []
        self.transform, self.crash_after = transform, crash_after

    def complete(self, **request):
        assert request["request_id"] not in self.receipts, "Provider call replayed"
        self.calls.append(copy.deepcopy(request))
        ctx = json.loads(request["prompt"])
        stage, node = ctx["asta_stage"], ctx["node_id"]
        if stage == "nomination":
            expressions = [
                "p0+p1*normalized_0",
                "p0+p1*tanh(normalized_0)",
                "p0+p1*normalized_0*normalized_0",
                "p0+p1*sin(normalized_0)",
            ]
            out = {
                "hypothesis": "Synthetic branch",
                "expression": expressions[int(node[-1]) - 1],
                "initial": {"p0": 0, "p1": 1},
                "rationale": "Private planner prose",
            }
        elif stage == "engineering":
            out = copy.deepcopy(ctx["frozen_program"])
        elif stage in ("prior", "posterior"):
            out = {"belief": stage == "posterior", "reason": "Synthetic scripted expectation"}
        else:
            out = {
                "summary": "Retain all four synthetic experiments",
                "experiment_ids": [f"hypothesis-{i + 1}" for i in range(4)],
                "candidate_ids": [
                    s["candidate_id"]
                    for s in ctx["frozen_evidence"]["selection"]["nominations"]
                    if s["candidate_id"]
                ],
                "limitations": ["synthetic only"],
                "observed_cohort": ctx["cohort"]["verified_counts"],
            }
        if self.transform:
            out = self.transform(stage, out, ctx)
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
    return BoundAsta(*fixture(), gateway=gateway or AstaGateway(), run_id="asta-fixture", **kwargs)


def durable(path, gateway, hook=lambda r: None):
    return DurableBoundRun(
        make(gateway), path, provider_binding={"fixture": "zero-api"}, after_record=hook
    )


def test_tree_executes_true_branching_and_retains_expanded_fits():
    gateway = AstaGateway()
    e = make(gateway)
    out = e.run()
    assert out["status"] == "complete", out["failure"]
    assert all(out["conformance"].values())
    assert len(gateway.calls) == out["model_requests"] == 25
    assert out["host_submission"]["accounting"]["fitting_attempts"] == 4
    assert len(out["host_submission"]["candidates"]) == 4
    root = out["search_tree"][0]
    assert root["visits"] == 4 and len(root["children"]) == 2
    assert root["reward_sum"] > 0
    assert root["reward_sum"] == pytest.approx(
        sum(n["belief_update"]["reward"] for n in out["search_tree"][1:])
    )
    assert any(s["parent_id"] != "root" for s in out["selection_history"])
    assert all(
        c["simplicity"]["train_statistic_scalars"] == 2
        for c in out["host_submission"]["candidates"]
    )
    assert out["configuration"]["weak_prior_fits"] == 0
    assert len(out["selection"]["nominations"]) == 3
    assert e.run() == out and len(gateway.calls) == 25


def test_prior_and_posterior_payloads_are_isolated_and_parent_uses_outcomes():
    gateway = AstaGateway()
    out = make(gateway).run()
    for index, request in enumerate(gateway.calls):
        ctx = json.loads(request["prompt"])
        assert sha(ctx) == out["handoffs"][index]["input_sha256"]
        role = {
            "nomination": "planner",
            "engineering": "coder",
            "prior": "critic",
            "posterior": "critic",
            "report": "reporter",
        }[ctx["asta_stage"]]
        assert request["model"] == DEFAULT_ROLES[role]
        assert "canary" not in request["prompt"] and "test_secret" not in request["prompt"]
        if ctx["asta_stage"] in ("prior", "posterior"):
            assert "inventory" not in ctx and "train_preview" not in ctx and "cohort" not in ctx
            assert "Private planner prose" not in request["prompt"]
            assert "ancestor_evidence" not in ctx and "prior_votes" not in request["prompt"]
            if ctx["asta_stage"] == "prior":
                assert "executed_experiment" not in ctx
                assert "initial" not in request["prompt"] and "value_path" not in request["prompt"]
                assert (
                    "state_" + out["host_submission"]["context"]["train_sha256"]
                    not in request["prompt"]
                )
                assert "domain knowledge" in request["system"]
                assert "Use only supplied train/dev evidence" not in request["system"]
                assert all(
                    "fixed_value" not in s for s in ctx["frozen_claim"]["symbolic_states"].values()
                )
            else:
                assert ctx["executed_experiment"]["node_id"] == ctx["node_id"]
                assert "no added domain evidence" in request["system"]
        if ctx["asta_stage"] == "nomination" and ctx["parent_id"] != "root":
            assert ctx["ancestor_evidence"][-1]["node_id"] == ctx["parent_id"]
            assert "experiment" in ctx["ancestor_evidence"][-1]


@pytest.mark.parametrize(
    "kind",
    [
        "duplicate",
        "rename",
        "expanded_alias",
        "changed_program",
        "changed_parameter",
        "literal",
        "hidden_state",
        "wrong_cohort",
        "invented_ids",
        "prior_abstains",
        "bad_belief",
        "empty_reason",
        "wrapper",
    ],
)
def test_missing_or_invalid_algorithm_behavior_stays_incomplete(kind):
    def alter(stage, data, ctx):
        second = ctx["node_id"] == "hypothesis-2"
        if stage == "nomination" and second:
            if kind in ("duplicate", "rename", "expanded_alias"):
                data["expression"] = "p0+p1*normalized_0"
                if kind == "rename":
                    data.update(expression="p2+p3*normalized_0", initial={"p2": 3, "p3": 4})
                if kind == "expanded_alias":
                    data["expression"] = (
                        "p0+p1*(" + ctx["inventory"]["kernels"][0]["expression"] + ")"
                    )
            if kind == "literal":
                data["expression"] = "p0+p1*0.123*x"
            if kind == "hidden_state":
                data["fitted_state"] = 0.3
        if stage == "engineering" and second:
            if kind == "changed_program":
                data["expression"] = "p0+p1*cos(normalized_0)"
            if kind == "changed_parameter":
                data["initial"]["p2"] = 3
        if stage == "prior":
            if kind == "prior_abstains":
                data["belief"] = None
            if kind == "bad_belief":
                data["belief"] = 0.5
            if kind == "empty_reason":
                data["reason"] = ""
            if kind == "wrapper":
                return {"response": data}
        if stage == "report":
            if kind == "wrong_cohort":
                data["observed_cohort"]["training_rows"] = 6
            if kind == "invented_ids":
                data["experiment_ids"][0] = "invented"
        return data

    out = make(AstaGateway(alter)).run()
    assert out["status"] == "incomplete_method_execution", out["failure"]
    assert len(out["selection"]["nominations"]) == 3
    assert not out["ranking_authorized"]
    if kind in {"prior_abstains", "bad_belief", "empty_reason", "wrapper"}:
        assert all(n["belief_update"]["reward"] == 0 for n in out["search_tree"][1:])


def test_local_failure_is_retained_has_no_reward_and_conditions_descendant():
    def alter(stage, data, ctx):
        if stage == "nomination" and ctx["node_id"] == "hypothesis-1":
            data["expression"] = "p0+p1*log(-abs(normalized_0))"
        return data

    gateway = AstaGateway(alter)
    out = make(gateway).run()
    assert out["status"] == "complete", out["failure"]
    node = out["search_tree"][1]
    assert node["experiment"]["failures"] and node["belief_update"]["reward"] == 0
    descendant = json.loads(gateway.calls[6]["prompt"])
    assert descendant["ancestor_evidence"][0]["experiment"]["failures"]


def test_shared_parameter_pattern_and_state_identity_survive_structural_deduplication():
    e = make()
    e._initialize()
    a = e._structure(e._compile({"expression": "p0+p1*x", "initial": {"p0": 0, "p1": 1}}))
    b = e._structure(e._compile({"expression": "p2+p3*x", "initial": {"p2": 9, "p3": 4}}))
    c = e._structure(e._compile({"expression": "p0+p0*x", "initial": {"p0": 1}}))
    assert a == b and a != c


@pytest.mark.parametrize(
    "limits", [{"max_calls": 4}, {"max_fits": 1}, {"max_optimizer_evaluations": 1}]
)
def test_budget_exhaustion_preserves_slots_and_cannot_claim_complete(limits):
    out = make(limits=limits).run()
    assert out["status"] in {"failed", "incomplete_method_execution"}
    assert len(out["selection"]["nominations"]) == 3
    assert out["model_requests"] <= limits.get("max_calls", 25)
    assert out["host_submission"]["accounting"]["fitting_attempts"] <= limits.get("max_fits", 4)


def test_report_cannot_fit_and_assessment_makes_zero_model_calls(monkeypatch):
    gateway = AstaGateway()
    e = make(gateway)

    def alter(stage, data, ctx):
        if stage == "report":
            assert e.host.closed
            with pytest.raises(ValueError, match="frozen"):
                e.host.fit("p0", {"p0": 0})
        return data

    gateway.transform = alter
    out = e.run()

    def forbidden(*a, **kw):
        pytest.fail("Assessment called provider or fitted")

    monkeypatch.setattr(e.host, "fit", forbidden)
    monkeypatch.setattr(gateway, "complete", forbidden)
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


@pytest.mark.parametrize("boundary", range(43))
def test_every_committed_tree_step_restores_without_duplicate_work(tmp_path, boundary):
    gateway = AstaGateway()

    def stop(record):
        if record["type"] == "commit" and record["sequence"] // 2 == boundary:
            raise PowerLoss()

    with pytest.raises(PowerLoss):
        durable(tmp_path, gateway, stop).run()
    out = durable(tmp_path, gateway).run()
    assert out["status"] == "complete", out["failure"]
    assert len(gateway.calls) == 25
    assert out["host_submission"]["accounting"]["fitting_attempts"] == 4
    assert out["search_tree"][0]["visits"] == 4
    assert durable(tmp_path, gateway).run() == out


@pytest.mark.parametrize("call", range(1, 26))
def test_every_settled_provider_boundary_recovers_identical_payload(tmp_path, call):
    gateway = AstaGateway(crash_after=call)
    with pytest.raises(PowerLoss):
        durable(tmp_path, gateway).run()
    out = durable(tmp_path, gateway).run()
    assert out["status"] == "complete", out["failure"]
    assert len(gateway.calls) == 25 and len(gateway.recovered) == 1
    assert out["host_submission"]["accounting"]["fitting_attempts"] == 4


@pytest.mark.parametrize(
    "name", ["hypothesis-1:prior:1", "hypothesis-1:experiment", "hypothesis-1:update"]
)
def test_ambiguous_provider_or_local_work_never_replays(tmp_path, name):
    gateway = AstaGateway()

    def stop(record):
        if record["type"] == "intent" and record["name"] == name:
            raise PowerLoss()

    with pytest.raises(PowerLoss):
        durable(tmp_path, gateway, stop).run()
    count = len(gateway.calls)
    with pytest.raises(RecoveryRequired):
        durable(tmp_path, gateway).run()
    assert len(gateway.calls) == count
