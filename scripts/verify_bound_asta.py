"""Installed explicit-state Asta proof with scripted transport and synthetic data."""

import argparse
import copy
import inspect
import json
import tempfile
from pathlib import Path

import numpy as np

from principia_asd.engine.bound_asta import BoundAsta
from principia_asd.engine.bound_checkpoint import DurableBoundRun
from principia_asd.evaluate.bound import evaluate_bound_nominations
from principia_asd.io import file_sha, sha, write_json
from principia_asd.runtime import now


class ScriptedAsta:
    def __init__(self, case):
        self.case, self.calls = case, []

    def complete(self, **request):
        self.calls.append(request)
        ctx = json.loads(request["prompt"])
        phase, node = ctx["asta_stage"], ctx["node_id"]
        if phase == "nomination":
            expressions = [
                "p0+p1*normalized_0",
                "p0+p1*tanh(normalized_0)",
                "p0+p1*normalized_0*normalized_0",
                "p0+p1*sin(normalized_0)",
            ]
            out = {
                "hypothesis": "Synthetic numerical branch",
                "expression": expressions[int(node[-1]) - 1],
                "initial": {"p0": 0, "p1": 1},
                "rationale": "Engineering fixture only",
            }
            if self.case == "domain_failure" and node == "hypothesis-1":
                out["expression"] = "p0+p1*log(-abs(normalized_0))"
            forbidden = {
                "forbidden_file": "open('MUST_NOT_READ.csv').read()",
                "forbidden_network": "__import__('socket').socket()",
                "forbidden_write": "open('MUST_NOT_WRITE', 'w').write('x')",
            }
            if self.case in forbidden and node == "hypothesis-1":
                out["expression"] = forbidden[self.case]
        elif phase == "engineering":
            out = copy.deepcopy(ctx["frozen_program"])
            if self.case == "changed_claim" and node == "hypothesis-2":
                out["expression"] = "p0+p1*cos(normalized_0)"
        elif phase in ("prior", "posterior"):
            assert "inventory" not in ctx and "train_preview" not in ctx
            if phase == "prior":
                assert "executed_experiment" not in ctx
            out = {"belief": phase == "posterior", "reason": "Scripted synthetic belief"}
            if self.case == "abstention" and phase == "prior":
                out["belief"] = None
        else:
            out = {
                "summary": "Retain all synthetic outcomes",
                "experiment_ids": [f"hypothesis-{i + 1}" for i in range(4)],
                "candidate_ids": [
                    s["candidate_id"]
                    for s in ctx["frozen_evidence"]["selection"]["nominations"]
                    if s["candidate_id"]
                ],
                "limitations": ["Engineering fixture, not a scientific result"],
                "observed_cohort": ctx["cohort"]["verified_counts"],
            }
            if self.case == "wrong_report":
                out["observed_cohort"]["training_rows"] = 6
        return {
            "text": json.dumps(out),
            "model": request["model"],
            "request_id": request["request_id"],
        }


def verify(workspace, receipt):
    assert "site-packages" in inspect.getfile(BoundAsta)
    workspace.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="bound-asta-fixture-", dir=workspace))
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
    for case in ("complete", "domain_failure", "abstention", "changed_claim", "wrong_report"):
        gateway = ScriptedAsta(case)
        engine = BoundAsta(
            task,
            rows("train", range(-3, 4)),
            rows("dev", [-2.5, -0.5, 1.5]),
            gateway=gateway,
            run_id=case,
        )
        runner = DurableBoundRun(
            engine, root / case, provider_binding={"fixture": "scripted-zero-api"}
        )
        out = runner.run()
        expected = (
            "complete" if case in ("complete", "domain_failure") else "incomplete_method_execution"
        )
        assert out["status"] == expected, out["failure"]
        assert len(gateway.calls) == 25
        assert runner.run() == out and len(gateway.calls) == 25
        assert out["search_tree"][0]["visits"] == 4
        assessment = evaluate_bound_nominations(
            out,
            out["nomination_freeze"]["sha256"],
            [{"x": 0.5}],
            [0.4 + 0.2 * np.tanh(0.25)],
            expected_result_sha256=out["sha256"],
        )
        assert len(assessment["receipts"]) == 3
        assert assessment["api_calls"] == assessment["fitting_attempts"] == 0
        write_json(root / case / "synthetic-assessment.json", assessment, immutable=True)
        maximum = max(len((c["system"] + c["prompt"]).encode()) for c in gateway.calls)
        cases.append(
            {
                "case": case,
                "status": expected,
                "result_sha256": out["sha256"],
                "synthetic_assessment_sha256": sha(assessment),
                "fitting_attempts": out["host_submission"]["accounting"]["fitting_attempts"],
                "optimizer_evaluations": out["host_submission"]["accounting"][
                    "optimizer_evaluations"
                ],
                "failed_numerical_fits": len(out["host_submission"]["failures"]),
                "nominations": sum(
                    s["candidate_id"] is not None for s in out["selection"]["nominations"]
                ),
                "fixed_slots": 3,
                "scripted_responses": 25,
                "root_visits": out["search_tree"][0]["visits"],
                "root_reward": out["search_tree"][0]["reward_sum"],
                "max_synthetic_payload_bytes": maximum,
            }
        )
    value = {
        "checked_at": now(),
        "status": "passed",
        "cases": cases,
        "scope": "Installed API, scripted transport and synthetic data only. No live model, worker, UI or scientific conformance claim.",
        "api_calls": 0,
        "accounted_cny": 0,
        "ranking_authorized": False,
        "scientific_review": "not_assessed",
        "module_sha256": file_sha(Path(inspect.getfile(BoundAsta))),
    }
    write_json(receipt, value, immutable=True)
    print(json.dumps(value, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    verify(args.workspace, args.receipt)
