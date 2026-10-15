"""Installed-package, zero-API evidence for the explicit-state Laboratory API."""

import argparse
import inspect
import json
import tempfile
from pathlib import Path

import numpy as np

from principia_asd.engine.bound_checkpoint import DurableBoundRun
from principia_asd.engine.bound_laboratory import BoundLaboratory
from principia_asd.evaluate.bound import evaluate_bound_nominations
from principia_asd.io import file_sha, write_json
from principia_asd.runtime import now


class ScriptedLaboratory:
    def __init__(self, case):
        self.case, self.calls = case, []

    def complete(self, **request):
        self.calls.append(request)
        ctx = json.loads(request["prompt"])
        stage = ctx["laboratory_stage"]
        if stage == "research_brief":
            out = {
                "question": "Does the synthetic response saturate?",
                "hypotheses": ["affine", "saturating"],
                "limitations": ["engineering fixture"],
            }
        elif stage == "experiment_plan":
            out = {
                "objective": "Check competing structures",
                "experiments": ["initial affine fit", "feedback revision"],
                "selection_criterion": "dev rmse",
                "risks": ["not independent evidence"],
            }
        elif stage == "initial_engineering":
            out = {"expression": "p0+p1*normalized_0", "initial": {"p0": 0, "p1": 1}}
            if self.case == "repair":
                out = {"expression": "0.123*x", "initial": {}}
        elif stage == "experimental_critique":
            assert ctx["experiments"][0]["experiment_id"] == "experiment-1"
            if self.case == "repair":
                assert ctx["experiments"][0]["failures"]
            out = {
                "experiment_ids": ["experiment-1"],
                "issues": ["inspect residuals or rejection"],
                "revision": "check saturation",
            }
        elif stage == "revised_engineering":
            assert ctx["preceding_handoffs"][-1]["name"] == "experimental_critique"
            out = {"expression": "p0+p1*tanh(normalized_0)", "initial": {"p0": 0, "p1": 1}}
            if self.case == "rename_only":
                out = {"expression": "p2+p3*normalized_0", "initial": {"p2": 2, "p3": 3}}
        else:
            out = {
                "summary": "Synthetic executed evidence only",
                "experiment_ids": ["experiment-1", "experiment-2"],
                "candidate_ids": [
                    s["candidate_id"]
                    for s in ctx["frozen_evidence"]["selection"]["nominations"]
                    if s["candidate_id"]
                ],
                "limitations": ["not a paid pilot or scientific result"],
                "observed_cohort": ctx["cohort"]["verified_counts"],
            }
            if self.case == "incorrect_cohort":
                out["observed_cohort"]["training_rows"] = 6
        return {
            "text": json.dumps(out),
            "model": request["model"],
            "request_id": request["request_id"],
        }


def verify(workspace, receipt):
    assert "site-packages" in inspect.getfile(BoundLaboratory)
    workspace.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="bound-laboratory-fixture-", dir=workspace))
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

    cases = []
    for case, expected in (
        ("complete", "complete"),
        ("repair", "complete"),
        ("rename_only", "incomplete_method_execution"),
        ("incorrect_cohort", "incomplete_method_execution"),
    ):
        gateway = ScriptedLaboratory(case)
        engine = BoundLaboratory(
            task,
            rows("train", range(-3, 4)),
            rows("dev", [-2.5, -0.5, 1.5]),
            gateway=gateway,
            run_id=case,
        )
        runner = DurableBoundRun(
            engine, root / case, provider_binding={"fixture": "scripted-zero-api"}
        )
        result = runner.run()
        assert result["status"] == expected, result["failure"]
        assert len(gateway.calls) == 6
        assert runner.run() == result and len(gateway.calls) == 6
        assessment = evaluate_bound_nominations(
            result,
            result["nomination_freeze"]["sha256"],
            [{"x": 0.5}],
            [0.4 + 0.2 * np.tanh(0.25)],
            expected_result_sha256=result["sha256"],
        )
        assert (
            len(assessment["receipts"]) == 3
            and assessment["api_calls"] == assessment["fitting_attempts"] == 0
        )
        write_json(root / case / "synthetic-assessment.json", assessment, immutable=True)
        cases.append(
            {
                "case": case,
                "status": expected,
                "result_sha256": result["sha256"],
                "synthetic_assessment_sha256": file_sha(root / case / "synthetic-assessment.json"),
                "fitting_attempts": result["host_submission"]["accounting"]["fitting_attempts"],
                "optimizer_evaluations": result["host_submission"]["accounting"][
                    "optimizer_evaluations"
                ],
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
        "scope": "Installed development API with scripted replies and synthetic measurements. No worker/UI enablement, real model conformance or scientific admission.",
        "cases": cases,
        "api_calls": 0,
        "accounted_cny": 0,
        "ranking_authorized": False,
        "scientific_review": "not_assessed",
        "module_sha256": file_sha(Path(inspect.getfile(BoundLaboratory))),
    }
    write_json(receipt, value, immutable=True)
    print(json.dumps(value, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    verify(args.workspace, args.receipt)
