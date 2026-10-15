"""Guarded statistical execution and numeric report provenance, not name-only conformance."""

import json

import pytest

from principia_asd.engine.search import execute_method
from principia_asd.io import sha


def fixture():
    task = {
        "task_id": "paper-fixture",
        "inputs": ["x"],
        "output": "y",
        "metric": {"primary": "mae"},
    }
    rows = [{"x": i / 10, "y": 2 + 3 * i / 10, "group": str(i // 5)} for i in range(60)]
    return task, rows[:40], rows[40:]


class PaperGateway:
    def __init__(self, fault=None):
        self.calls, self.code_calls, self.report_calls = [], 0, 0
        self.fault = fault

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        context = json.loads(kwargs["prompt"])["development_feedback"]
        role = kwargs["request_id"].split("--")[-2]
        if role == "planner":
            value = {
                "hypothesis": "An affine relation",
                "inputs": ["x"],
                "output": "y",
                "metric": "mae",
                "fit_partition": "train",
                "selection_partition": "dev",
            }
            if self.fault in {"target_alias", "test_access", "wrong_metric", "changed_endpoint"}:
                key, bad = {
                    "target_alias": ("inputs", ["x", "y"]),
                    "test_access": ("selection_partition", "test"),
                    "wrong_metric": ("metric", "rmse"),
                    "changed_endpoint": ("output", "x"),
                }[self.fault]
                value[key] = bad
        elif role == "coder":
            self.code_calls += 1
            assert context["analysis_plan"]["hypothesis"]
            value = {"expression": "p0+p1*x", "parameters": {"p0": 0, "p1": 1}}
            language = context["expression_language"]
            assert language["functions"]["minimum"]["arity"] == 2
            assert "clip" not in language["functions"]
            if self.fault == "repair_program":
                if self.code_calls == 1:
                    value["expression"] = "p0+p1*y"
                else:
                    assert context["previous_failures"][0]["failures"]
            if self.fault in {"repair_domain", "repeat_invalid_program", "repair_syntax", "repair_clip"}:
                if self.code_calls == 1:
                    value = {
                        "expression": {
                            "repair_domain": "sqrt(-1)",
                            "repeat_invalid_program": "sqrt(-1)",
                            "repair_syntax": "x +",
                            "repair_clip": "clip(x,0,1)",
                        }[self.fault],
                        "parameters": {},
                    }
                elif self.fault == "repeat_invalid_program":
                    value = {"expression": "sqrt( -1 )", "parameters": {}, "rationale": "Changed prose only"}
                elif self.fault == "repair_domain":
                    failure = context["previous_failures"][0]["failures"][0]["diagnostics"]
                    assert failure["train"]["nonfinite_outputs"] == 40
                    assert failure["dev"]["invalid_outputs"] == 20
                    assert failure["additional_fits"] == 0
                    assert not failure["private_test_access"]
        elif role == "critic":
            assert context["experiments"][-1]["result"]["dev_error"] < 1e-6
            assert context["computed_facts"]["training_rows"]["value"] == 40
            value = {
                "experiment_ids": [context["experiments"][-1]["experiment_id"]],
                "limitations": ["Synthetic fixture; development evidence only"],
            }
        else:
            assert role == "reporter"
            self.report_calls += 1
            if self.report_calls > 1:
                assert context["report_guard_feedback"]["errors"]
            value = {
                "observed_cohort": context["cohort"]["verified_counts"],
                "sections": [
                    {
                        "heading": "Results",
                        "template": "Development loss {{development_error}}, compared with {{baseline_development_error}} for the frozen training mean.",
                    }
                ],
                "limitations": ["No scientific validation of synthetic data"],
            }
            if self.fault in {"numeric_literal", "invented_quantity", "always_wrong_report"}:
                if self.report_calls == 1 or self.fault == "always_wrong_report":
                    suffix = (
                        " The p value is 0.001."
                        if self.fault == "numeric_literal"
                        else " Significance {{invented_p_value}}."
                    )
                    value["sections"][0]["template"] += suffix
        return {"text": json.dumps(value), "request_id": kwargs["request_id"]}


def test_statistical_report_is_linked_to_executed_analysis():
    gateway = PaperGateway()
    task, train, dev = fixture()
    result = execute_method("data_to_paper", task, train, dev, gateway=gateway)
    assert result["status"] == "complete" and len(result["rules"]) == 1
    assert len(gateway.calls) == 4 and result["accounting"]["fitting_attempts"] == 1
    evidence = result["method_evidence"]
    assert all(evidence["conformance"]["checks"].values())
    assert evidence["computed_facts"]["development_error"]["value"] < 1e-6
    assert evidence["computed_facts"]["training_rows"]["value"] == 40
    assert evidence["computed_facts"]["training_rows"]["lineage"]["train_records_sha256"] == sha(
        train
    )
    assert not evidence["computed_facts"]["development_error"]["lineage"]["final_test_access"]
    assert evidence["verified_report"]["valid"]
    assert "{{" not in evidence["verified_report"]["sections"][0]["text"]
    assert set(evidence["verified_report"]["computed_references"]) == {
        "development_error",
        "baseline_development_error",
    }


@pytest.mark.parametrize(
    "fault", ["target_alias", "test_access", "wrong_metric", "changed_endpoint"]
)
def test_plan_guard_blocks_leakage_and_contract_changes_before_execution(fault):
    gateway = PaperGateway(fault)
    result = execute_method("data_to_paper", *fixture(), gateway=gateway)
    assert result["status"] == "incomplete_method_execution" and not result["rules"]
    assert len(gateway.calls) == 1 and result["accounting"]["fitting_attempts"] == 0
    assert result["method_evidence"]["plan_guard_errors"]


def test_program_repair_uses_rejected_experiment_without_target_access():
    gateway = PaperGateway("repair_program")
    result = execute_method("data_to_paper", *fixture(), gateway=gateway)
    assert result["status"] == "complete" and len(gateway.calls) == 5
    experiments = result["method_evidence"]["experiments"]
    assert (
        experiments[0]["status"] == "failed_or_rejected" and experiments[0]["fitting_attempts"] == 0
    )
    assert experiments[1]["status"] == "complete" and result["accounting"]["fitting_attempts"] == 1


@pytest.mark.parametrize("fault", ["numeric_literal", "invented_quantity"])
def test_report_repairs_do_not_refit_or_change_rules(fault):
    gateway = PaperGateway(fault)
    result = execute_method("data_to_paper", *fixture(), gateway=gateway)
    assert result["status"] == "complete" and len(gateway.calls) == 5
    assert result["accounting"]["fitting_attempts"] == 1
    checks = result["method_evidence"]["report_checks"]
    assert not checks[0]["valid"] and checks[1]["valid"]


def test_persistent_uncomputed_claims_cannot_produce_ranked_rules():
    result = execute_method(
        "data_to_paper", *fixture(), gateway=PaperGateway("always_wrong_report")
    )
    assert result["status"] == "incomplete_method_execution" and not result["rules"]
    assert result["diagnostics"]["candidates"] == 1
    assert len(result["method_evidence"]["report_checks"]) == 2


@pytest.mark.parametrize("fault", ["repair_domain", "repair_syntax", "repair_clip"])
def test_domain_and_language_errors_condition_a_new_executable_repair(fault):
    gateway = PaperGateway(fault)
    result = execute_method("data_to_paper", *fixture(), gateway=gateway)
    assert result["status"] == "complete"
    assert len(gateway.calls) == 5
    assert result["accounting"]["fitting_attempts"] == 1
    assert result["method_evidence"]["experiments"][0]["status"] == "failed_or_rejected"


def test_cosmetically_changed_rejected_program_is_not_executed_again():
    result = execute_method("data_to_paper", *fixture(), gateway=PaperGateway("repeat_invalid_program"))
    assert result["status"] == "incomplete_method_execution" and not result["rules"]
    attempts = result["method_evidence"]["experiments"]
    assert not attempts[1]["structure_entered"]
    assert attempts[1]["failures"][0]["reason"].startswith("Repair repeats the rejected program")
    assert result["accounting"]["model_calls"] == 3
    assert result["accounting"]["fitting_attempts"] == 0


def test_log_metric_implies_positive_domain_and_diagnostics_add_no_executions(monkeypatch):
    import principia_asd.engine.search as backend

    task, train, dev = fixture()
    task["metric"]["primary"] = "log_mae"
    task["positive_prediction"] = False
    calls = []
    original = backend.execute

    def counted(*args, **kwargs):
        calls.append(args[0])
        return original(*args, **kwargs)

    monkeypatch.setattr(backend, "execute", counted)
    search = backend.Search(task, train, dev, capture_failure_diagnostics=True)
    assert search.add("x-2") is None
    assert len(calls) == 2 and search.fits == 0
    diagnostics = search.failures[0]["diagnostics"]
    assert diagnostics["prediction_requirements"]["strictly_positive"]
    assert diagnostics["train"]["invalid_outputs"] == 21
    assert diagnostics["dev"]["invalid_outputs"] == 0
    assert diagnostics["train"]["finite_min"] == -2
    assert len(diagnostics["train"]["first_invalid_rows"]) == 5
