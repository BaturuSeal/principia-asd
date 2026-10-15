"""Installed API verification using synthetic measurements and scripted replies."""

import argparse
import inspect
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np

from principia_asd.engine.bound_checkpoint import DurableBoundRun
from principia_asd.engine.bound_data_to_paper import BoundDataToPaper, verified_facts
from principia_asd.evaluate.bound import evaluate_bound_nominations
from principia_asd.io import file_sha, write_json
from principia_asd.runtime import now


class ScriptedPaper:
    def __init__(self, case):
        self.case, self.calls = case, []

    def complete(self, **request):
        self.calls.append(request)
        c = json.loads(request["prompt"])
        stage = c["paper_stage"]
        if stage == "analysis_plan":
            out = {
                "hypothesis": "Affine response",
                "inputs": ["x"],
                "output": "y",
                "metric": "rmse",
                "fit_partition": "train",
                "selection_partition": "dev",
                "limitations": ["synthetic observations"],
            }
            if self.case == "invalid_plan":
                out["selection_partition"] = "test"
        elif stage in ("analysis_program", "analysis_repair"):
            out = {"expression": "p0+p1*normalized_0", "initial": {"p0": 0, "p1": 1}}
            if stage == "analysis_program" and self.case in {"analysis_repair", "both_repairs"}:
                out = {"expression": "0.123*x", "initial": {}}
            if stage == "analysis_repair":
                assert c["experiments"][0]["rejections"]
        elif stage == "statistical_review":
            out = {
                "experiment_ids": [c["experiments"][-1]["experiment_id"]],
                "facts_sha256": c["computed_facts"]["sha256"],
                "limitations": ["not independent scientific evidence"],
                "interpretation": "development diagnostics only",
            }
        else:
            out = {
                "sections": [
                    {
                        "heading": "Results",
                        "template": "Loss {{development_error}} versus mean comparator {{baseline_development_error}}.",
                    }
                ],
                "observed_cohort": c["cohort"]["verified_counts"],
                "candidate_ids": [
                    s["candidate_id"]
                    for s in c["frozen_evidence"]["selection"]["nominations"]
                    if s["candidate_id"]
                ],
                "facts_sha256": c["computed_facts"]["sha256"],
                "limitation_ids": [v["id"] for v in c["retained_limitations"]],
                "limitations": ["Train groups {{training_groups}}; independence unreviewed."],
            }
            if self.case in {"report_repair", "both_repairs"} and stage == "evidence_report":
                out["sections"][0]["template"] += " Invented value 0.2."
            if self.case == "incorrect_report":
                out["observed_cohort"]["training_rows"] = 6
            if stage == "report_repair":
                assert c["report_guard_feedback"][-1]["errors"]
        return {
            "text": json.dumps(out),
            "model": request["model"],
            "request_id": request["request_id"],
        }


def verify(workspace, receipt):
    assert "site-packages" in inspect.getfile(BoundDataToPaper)
    workspace.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="bound-paper-fixture-", dir=workspace))
    task = {
        "inputs": ["x"],
        "output": "y",
        "metric": {"primary": "rmse"},
        "stability": {"ranking": False},
    }

    def rows(label, xs):
        return [
            {
                "sample_id": f"{label}{i}",
                "group": label,
                "x": float(x),
                "y": float(0.4 + 0.2 * np.tanh(x / 2)),
            }
            for i, x in enumerate(xs)
        ]

    results = []
    for case, expected in (
        ("complete", "complete"),
        ("analysis_repair", "complete"),
        ("report_repair", "complete"),
        ("incorrect_report", "incomplete_method_execution"),
        ("invalid_plan", "incomplete_method_execution"),
    ):
        gateway = ScriptedPaper(case)
        engine = BoundDataToPaper(
            task,
            rows("train", range(-3, 4)),
            rows("dev", [-2.5, -0.5, 1.5]),
            gateway=gateway,
            run_id=case,
        )
        runner = DurableBoundRun(
            engine, root / case, provider_binding={"fixture": "scripted-zero-api"}
        )
        with patch("socket.socket", side_effect=AssertionError("Network forbidden in fixture")):
            result = runner.run()
            assert result["status"] == expected, result["failure"]
            original_calls = len(gateway.calls)
            with (
                patch.object(gateway, "complete", side_effect=AssertionError("Provider replay")),
                patch.object(engine.host, "fit", side_effect=AssertionError("Unexpected refit")),
            ):
                assert runner.run() == result and len(gateway.calls) == original_calls
                if result["computed_facts"]:
                    assert (
                        verified_facts(engine.host, next(iter(engine.host.candidates.values())))
                        == result["computed_facts"]
                    )
                assessment = evaluate_bound_nominations(
                    result,
                    result["nomination_freeze"]["sha256"],
                    [{"x": 0.5}],
                    [0.4 + 0.2 * np.tanh(0.25)],
                    expected_result_sha256=result["sha256"],
                )
            assert len(assessment["receipts"]) == 3
            assert assessment["api_calls"] == assessment["fitting_attempts"] == 0
            write_json(root / case / "synthetic-assessment.json", assessment, immutable=True)
        results.append(
            {
                "case": case,
                "status": expected,
                "result_sha256": result["sha256"],
                "assessment_sha256": file_sha(root / case / "synthetic-assessment.json"),
                "fitting_attempts": result["host_submission"]["accounting"]["fitting_attempts"],
                "optimizer_evaluations": result["host_submission"]["accounting"][
                    "optimizer_evaluations"
                ],
                "statistics": result["computed_facts"]["sha256"]
                if result["computed_facts"]
                else None,
                "statistical_prediction_rows": sum(
                    a["prediction_rows"] for a in result["statistical_accounting"]
                ),
                "fixed_slots": 3,
                "nominations": sum(
                    s["candidate_id"] is not None for s in result["selection"]["nominations"]
                ),
                "scripted_responses": len(gateway.calls),
            }
        )
    value = {
        "checked_at": now(),
        "status": "passed",
        "cases": results,
        "scope": "Installed development API, synthetic assistant-produced fixtures and scripted replies. Not worker/UI enablement, live-model conformance or scientific evidence.",
        "module_sha256": file_sha(Path(inspect.getfile(BoundDataToPaper))),
        "network_denied": True,
        "api_calls": 0,
        "accounted_cny": 0,
        "ranking_authorized": False,
        "scientific_review": "not_assessed",
    }
    write_json(receipt, value, immutable=True)
    print(json.dumps(value, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    verify(args.workspace, args.receipt)
