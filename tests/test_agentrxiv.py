"""Cross-lab use must be executed, provenance-bound and numerically accounted."""

import copy
import json

import pytest
from test_laboratory import LaboratoryGateway, fixtures

from principia_asd.engine.agentrxiv import PrivateArchive, compose_from_report
from principia_asd.engine.expression import complexity
from principia_asd.engine.search import execute_method
from principia_asd.io import sha


class AgentRxivGateway:
    def __init__(self, fault=None):
        self.calls = []
        self.fault = fault
        self.labs = {"lab-A": LaboratoryGateway(), "lab-B": LaboratoryGateway(
            "invented_evidence" if fault == "incomplete_donor" else None)}

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        f = json.loads(kwargs["prompt"])["development_feedback"]
        identity = f["laboratory"]
        if identity["cycle_id"] == "initial":
            lab = identity["lab_id"]
            assert not identity["visible_archive_report_ids"]
            assert "retrieved_report" not in f
            response = self.labs[lab].complete(**kwargs)
            output = json.loads(response["text"])
            if lab == "lab-B":
                if len(self.labs[lab].calls) == 3:
                    output["expression"] = "p0+p1*sqrt(x+1)"
                if len(self.labs[lab].calls) == 5:
                    output["expression"] = "p0+p1*x**3"
            if "selection" in f:
                assert f["selection"]["structures"] == 2  # No other lab's numerical state.
                assert len(f["experiments"]) == 2
        elif "retrieved_report" not in f:
            assert f["own_report"]["content"]["lab_id"] == "lab-A"
            output = {"query": "nonlinear response curvature"}
        else:
            entry = f["retrieved_report"]
            assert entry["content"]["lab_id"] == "lab-B"
            assert sha(entry["content"]) == entry["sha256"]
            ref = {"source_report_id": entry["report_id"], "source_experiment_id": "experiment-2"}
            if "valid_source_experiment_ids" in f:
                output = ref | {"followup": "Add a measured-input correction", "rationale": "Synthetic reuse"}
            elif "frozen_followup_plan" in f:
                revised = "previous_experiment" in f
                output = ref | {"combine": "add", "extension_expression": "p2*x**2" if revised else "p2*x",
                                "extension_parameters": {"p2": 0.1}}
                if self.fault == "wrong_source":
                    output["source_report_id"] = "unretrieved-report"
                if self.fault == "constant_extension":
                    output["extension_expression"] = "0"
                if self.fault == "no_revision":
                    output["extension_expression"] = "p2*x"
            elif "experiment" in f:
                output = {"source_report_id": entry["report_id"], "experiment_ids": ["cross-lab-1"], "revision": "Use curvature"}
            else:
                output = {"summary": "Actual reused family", "source_report_id": entry["report_id"],
                          "experiment_ids": ["cross-lab-1", "cross-lab-2"], "limitations": ["Synthetic"],
                          "observed_cohort": f["cohort"]["verified_counts"]}
                if self.fault == "unbound_report":
                    output["source_report_id"] = "unretrieved-report"
        return {"text": json.dumps(output), "request_id": kwargs["request_id"]}


def test_two_isolated_labs_then_executed_archive_reuse():
    gateway = AgentRxivGateway()
    events = []
    result = execute_method("agentrxiv", *fixtures(), gateway=gateway, event=lambda k, v: events.append((k, v)))
    assert result["status"] == "complete"
    assert result["accounting"]["model_calls"] == 18
    assert result["accounting"]["fitting_attempts"] == 6
    assert result["accounting"]["structures"] == 6
    e = result["method_evidence"]
    assert all(e["conformance"]["checks"].values())
    assert len(e["laboratories"]) == 2 and len(e["archive"]) == 3
    assert len({h["model"] for h in e["handoffs"]}) == 4
    for h, request in zip(e["handoffs"], gateway.calls, strict=True):
        assert h["input_sha256"] == sha(json.loads(request["prompt"])["development_feedback"])
    assert e["retrievals"][0]["report_sha256"] == e["archive"][1]["sha256"]
    pub_index = max(i for i, (stage, _) in enumerate(events) if stage == "archive_publication" and i < next(j for j, (s, _) in enumerate(events) if s == "archive_retrieval"))
    assert pub_index < next(i for i, (s, _) in enumerate(events) if s == "archive_followup_experiment")
    source = e["archive"][1]["content"]["experiments"][1]["result"]
    for experiment in e["followup"]["experiments"]:
        program = experiment["program"]
        assert source["expression"] in program["expression"]
        assert set(program["parameters"]) == {"p0", "p1", "p2"}
        assert experiment["fitting_attempts"] == 1 and experiment["optimizer_evaluations"] > 0
        assert complexity(program["expression"], program["parameters"])["weighted_operator_count"] > source["simplicity"]["weighted_operator_count"]
        assert experiment["source_lineage"]["source_report_sha256"] == e["archive"][1]["sha256"]
    assert result["accounting"]["optimizer_evaluations"] == sum(x["optimizer_evaluations"] for x in e["experiments"])


@pytest.mark.parametrize("fault", ["wrong_source", "constant_extension", "no_revision", "unbound_report", "incomplete_donor"])
def test_missing_real_archive_use_retains_incomplete_outcome(fault):
    gateway = AgentRxivGateway(fault)
    result = execute_method("agentrxiv", *fixtures(), gateway=gateway)
    assert result["status"] == "incomplete_method_execution"
    assert not result["rules"]
    if fault == "incomplete_donor":
        assert result["accounting"]["model_calls"] == 12
        assert not result["method_evidence"]["retrievals"]
        assert len(result["method_evidence"]["archive"]) == 1


def test_shared_fit_budget_and_request_budget_are_not_reset_per_lab():
    result = execute_method("agentrxiv", *fixtures(), gateway=AgentRxivGateway(), limits={"max_fits": 4})
    assert result["accounting"]["fitting_attempts"] == 4
    assert result["status"] == "incomplete_method_execution"
    gateway = AgentRxivGateway()
    with pytest.raises(RuntimeError, match="request budget exhausted"):
        execute_method("agentrxiv", *fixtures(), gateway=gateway, limits={"max_calls": 7})
    assert len(gateway.calls) == 7


def test_archive_resets_between_tasks_and_detects_mutation():
    task, train, dev = fixtures()
    first = execute_method("agentrxiv", task, train, dev, gateway=AgentRxivGateway())["method_evidence"]
    second = execute_method("agentrxiv", task | {"task_id": "another-task"}, train, dev, gateway=AgentRxivGateway())["method_evidence"]
    assert {e["content"]["task_id"] for e in second["archive"]} == {"another-task"}
    assert not {e["report_id"] for e in first["archive"]} & {e["report_id"] for e in second["archive"]}
    archive = PrivateArchive(task["task_id"])
    archive.entries = copy.deepcopy(first["archive"][:2])
    match = archive.retrieve("curvature", "lab-A")[0]["entry"]
    assert match["content"]["lab_id"] == "lab-B"
    match["content"]["report"]["summary"] = "tampered outside stored archive"
    assert archive.retrieve("curvature", "lab-A")
    with pytest.raises(ValueError, match="mutation"):
        archive.verify(match)
    archive.entries[0]["content"]["report"]["summary"] = "tampered stored archive"
    with pytest.raises(ValueError, match="mutation"):
        archive.retrieve("curvature", "lab-A")


def test_composition_rejects_hidden_or_colliding_state_and_target_inputs():
    result = execute_method("agentrxiv", *fixtures(), gateway=AgentRxivGateway())
    entry = result["method_evidence"]["archive"][1]
    valid = {"source_report_id": entry["report_id"], "source_experiment_id": "experiment-2", "combine": "add",
             "extension_expression": "p2*x", "extension_parameters": {"p2": 1}}
    with pytest.raises(ValueError, match="collide"):
        compose_from_report(entry, "experiment-2", valid | {"extension_parameters": {"p0": 1}}, ["x"])
    with pytest.raises(ValueError, match="Undeclared input"):
        compose_from_report(entry, "experiment-2", valid | {"extension_expression": "p2*y"}, ["x"])
    tampered = copy.deepcopy(entry)
    tampered["content"]["report"]["summary"] = "changed"
    with pytest.raises(ValueError, match="mutated"):
        compose_from_report(tampered, "experiment-2", valid, ["x"])
