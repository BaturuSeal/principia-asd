"""Algorithm conformance: feedback dependencies and actual numerical program execution."""

import json

import pytest

from principia_asd.engine.search import execute_method
from principia_asd.io import sha


def fixtures():
    task = {
        "task_id": "synthetic-laboratory",
        "inputs": ["x"],
        "output": "y",
        "metric": {"primary": "mae"},
    }
    rows = [{"x": i / 10, "y": 2 + (i / 10) ** 2, "group": str(i // 5)} for i in range(40)]
    return task, rows[:30], rows[30:]


class LaboratoryGateway:
    def __init__(self, fault=None):
        self.calls = []
        self.fault = fault

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        n = len(self.calls)
        feedback = json.loads(kwargs["prompt"])["development_feedback"]
        assert feedback["cohort"]["verified_counts"] == {
            "training_rows": 30,
            "development_rows": 10,
            "training_groups": 6,
            "development_groups": 2,
        }
        assert feedback["cohort"]["examples_in_prompt"] == 6
        assert feedback["cohort"]["examples_are_only_a_preview"]
        replies = [
            {"question": "Linear or quadratic?", "hypotheses": ["linear", "quadratic"]},
            {
                "objective": "Compare shapes",
                "experiments": ["linear", "revise"],
                "selection_criterion": "development MAE",
            },
            {"expression": "p0+p1*x", "parameters": {"p0": 0, "p1": 1}},
            {"experiment_ids": ["experiment-1"], "revision": "Test curvature"},
            {"expression": "p0+p1*x**2", "parameters": {"p0": 0, "p1": 1}},
            {
                "summary": "Executed development comparison",
                "experiment_ids": ["experiment-1", "experiment-2"],
                "limitations": ["Synthetic engineering fixture; no scientific discovery claim"],
                "observed_cohort": feedback["cohort"]["verified_counts"],
            },
        ]
        if n == 2:
            assert feedback["research_brief"] == replies[0]
        if n == 3:
            assert feedback["experiment_plan"] == replies[1]
        if n == 4:
            assert feedback["experiment"]["experiment_id"] == "experiment-1"
            if self.fault == "invalid_initial":
                assert feedback["experiment"]["failures"]
            else:
                assert feedback["experiment"]["result"]["dev_error"] > 0
                assert feedback["experiment"]["optimizer_evaluations"] > 0
        if n == 5:
            assert feedback["critique"] == replies[3]
            assert feedback["previous_experiment"]["program"]
        if n == 6:
            assert len(feedback["experiments"]) == 2
            assert feedback["selection"]["private_test_feedback"] is False
        output = replies[n - 1]
        if n == 3 and self.fault == "invalid_initial":
            output = {"expression": "open('/private/canary')", "parameters": {}}
        if n == 5 and self.fault == "no_revision":
            output = replies[2]
        if n == 6 and self.fault == "invented_evidence":
            output = output | {"experiment_ids": ["experiment-1", "unexecuted-3"]}
        if n == 6 and self.fault == "malformed_evidence":
            output = output | {"experiment_ids": [None, 1]}
        if n == 6 and self.fault == "preview_as_cohort":
            output = output | {"observed_cohort": output["observed_cohort"] | {"training_rows": 6}}
        return {"text": json.dumps(output), "request_id": kwargs["request_id"]}


def test_laboratory_executes_handoffs_and_revision():
    gateway = LaboratoryGateway()
    result = execute_method("agent_laboratory", *fixtures(), gateway=gateway)
    assert result["status"] == "complete"
    assert result["accounting"]["model_calls"] == 6
    assert result["accounting"]["fitting_attempts"] == 2
    evidence = result["method_evidence"]
    assert evidence["conformance"]["status"] == "complete"
    assert all(evidence["conformance"]["checks"].values())
    assert len({h["model"] for h in evidence["handoffs"]}) == 4
    for handoff, call in zip(evidence["handoffs"], gateway.calls, strict=True):
        assert handoff["input_sha256"] == sha(json.loads(call["prompt"])["development_feedback"])
        assert handoff["output_sha256"] == sha(handoff["output"])
    assert evidence["experiments"][1]["result"]["dev_error"] < 1e-6
    assert result["rules"][0]["method_version"] == "agent-laboratory-adaptation-v2"


@pytest.mark.parametrize(
    "fault", ["no_revision", "invented_evidence", "malformed_evidence", "preview_as_cohort"]
)
def test_incomplete_algorithm_cannot_generate_ranked_rules(fault):
    result = execute_method("agent_laboratory", *fixtures(), gateway=LaboratoryGateway(fault))
    assert result["status"] == "incomplete_method_execution"
    assert not result["rules"]
    assert result["method_evidence"]["experiments"]


def test_failed_experiment_is_retained_and_used_for_repair():
    result = execute_method(
        "agent_laboratory", *fixtures(), gateway=LaboratoryGateway("invalid_initial")
    )
    assert result["status"] == "complete"
    evidence = result["method_evidence"]
    assert evidence["experiments"][0]["result"] is None
    assert evidence["experiments"][0]["failures"]
    assert evidence["experiments"][1]["result"]["dev_error"] < 1e-6
    assert result["failed_candidates"]


def test_exhausted_budget_does_not_fabricate_stages_or_replay_calls():
    gateway = LaboratoryGateway()
    with pytest.raises(RuntimeError, match="request budget exhausted"):
        execute_method("agent_laboratory", *fixtures(), gateway=gateway, limits={"max_calls": 3})
    assert len(gateway.calls) == 3
