"""Offline installed-package protocol proof: scripted replies, real local fits.

Artifacts are engineering fixtures, not an API pilot or benchmark result.
"""

import argparse
import inspect
import json
import tempfile
from pathlib import Path

import numpy as np

from principia_asd.engine.bound_engine import BoundEngine
from principia_asd.evaluate.bound import evaluate_bound_candidate, evaluate_bound_nominations
from principia_asd.io import file_sha, write_json
from principia_asd.methods.registry import DEFAULT_ROLES
from principia_asd.runtime import now


class ScriptedGateway:
    """Simulate the exact gateway signature without a provider or credentials."""

    def __init__(self):
        self.calls = []
        self.plans = 0

    def complete(self, **request):
        self.calls.append(
            {k: request[k] for k in ["model", "request_id", "max_tokens", "temperature"]}
        )
        ctx = json.loads(request["prompt"])
        role = next(k for k, v in DEFAULT_ROLES.items() if v == request["model"])
        if role == "planner":
            source = "tanh(normalized_0)"
            if self.plans:
                best = ctx["development_feedback"]["candidates"][0]["candidate_id"]
                source = next(
                    k["name"]
                    for k in ctx["inventory"]["kernels"]
                    if k["lineage"].get("candidate_id") == best
                )
                assert ctx["development_feedback"]["earlier_round_critiques"]
            data = {
                "kernels": [
                    {"name": f"k_smooth{self.plans}", "expression": source},
                    {"name": f"k_curve{self.plans}", "expression": "normalized_0*normalized_0"},
                ],
                "rationale": "Scripted engineering fixture",
            }
            self.plans += 1
        elif role == "coder":
            data = {
                "rules": [
                    {"expression": f"p0+p1*k_smooth{self.plans - 1}", "initial": {"p0": 0, "p1": 1}}
                ]
            }
        elif role == "critic":
            data = {
                "candidate_ids": [
                    c["candidate_id"] for c in ctx["development_feedback"]["candidates"]
                ],
                "limitations": ["Synthetic data"],
                "next_hypothesis": "Reuse host fitted-state references",
            }
        else:
            data = {
                "candidate_ids": [
                    s["candidate_id"]
                    for s in ctx["frozen_evidence"]["selection"]["nominations"]
                    if s["candidate_id"]
                ],
                "limitations": ["No real model or independent scientific result"],
                "summary": "Scripted response verifies report bindings",
            }
        return {
            "model": request["model"],
            "request_id": request["request_id"],
            "text": json.dumps(data),
            "usage": {"simulated": True},
        }


def verify(workspace):
    workspace.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="bound-engine-fixture-", dir=workspace))
    task = {
        "inputs": ["x"],
        "output": "y",
        "metric": {"primary": "rmse"},
        "stability": {"ranking": False},
    }

    def rows(label, values):
        return [
            {
                "sample_id": f"{label}{i}",
                "group": label,
                "x": float(x),
                "y": float(0.4 + 0.2 * np.tanh(x / 2)),
            }
            for i, x in enumerate(values)
        ]

    gateway = ScriptedGateway()
    engine = BoundEngine(
        task,
        rows("train", range(-3, 4)),
        rows("dev", [-2.5, -0.5, 1.5]),
        gateway=gateway,
        run_id="bound-engine-fixture",
    )
    result = engine.run()
    assert result["status"] == "complete", result["failure"]
    assert all(result["conformance"].values())
    assert len(gateway.calls) == 7 and result == engine.run()
    frozen = result["host_submission"]
    receipts = []
    for slot in result["selection"]["nominations"]:
        if slot["candidate_id"]:
            args = (
                frozen,
                frozen["sha256"],
                slot["candidate_id"],
                [{"x": 1.25, "group": "synthetic-test"}],
                [0.4 + 0.2 * np.tanh(1.25 / 2)],
            )
            receipt = evaluate_bound_candidate(*args)
            assert receipt == evaluate_bound_candidate(*args)
            receipts.append(receipt)
    assert len(gateway.calls) == 7
    slots = evaluate_bound_nominations(
        result,
        result["nomination_freeze"]["sha256"],
        [{"x": 1.25, "group": "synthetic-test"}],
        [0.4 + 0.2 * np.tanh(1.25 / 2)],
        expected_result_sha256=result["sha256"],
    )
    assert slots["fixed_denominator"] == len(slots["receipts"]) == 3
    assert any(c["simplicity"]["inherited_fitted_scalars"] > 0 for c in frozen["candidates"])
    write_json(folder / "submission.json", result, immutable=True)
    write_json(folder / "assessment.json", slots, immutable=True)
    proof = {
        "checked_at": now(),
        "status": "passed_scripted_protocol_integration",
        "scope": "Scripted model responses plus real train fits; not a live API pilot or scientific trial",
        "source_is_installed_distribution": "site-packages" in inspect.getfile(BoundEngine),
        "protocol_module_sha256": file_sha(Path(inspect.getfile(BoundEngine))),
        "configuration": result["configuration"],
        "conformance": result["conformance"],
        "simulated_gateway_calls": gateway.calls,
        "real_api_calls": 0,
        "fitting_attempts": frozen["accounting"]["fitting_attempts"],
        "optimizer_evaluations": frozen["accounting"]["optimizer_evaluations"],
        "all_candidates_retained": len(frozen["candidates"]),
        "fixed_nomination_slots": len(result["selection"]["nominations"]),
        "assessed_nominations": len(receipts),
        "zero_fit_zero_api_reassessment": True,
        "historical_campaign_changed": False,
        "public_ranking_authorized": False,
        "durable_worker_verification": "docs/BOUND_RECOVERY_VERIFICATION.json",
        "ui_integration": "pending",
        "artifacts": {
            "private_fixture_folder": str(folder),
            "submission_sha256": file_sha(folder / "submission.json"),
            "assessment_sha256": file_sha(folder / "assessment.json"),
        },
    }
    write_json(Path(__file__).resolve().parents[1] / "docs/BOUND_ENGINE_VERIFICATION.json", proof)
    print(
        {
            k: v
            for k, v in proof.items()
            if k not in {"configuration", "simulated_gateway_calls", "artifacts"}
        }
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workspace",
        type=Path,
        required=True,
        help="Private engineering fixture root outside upload directories",
    )
    verify(parser.parse_args().workspace.resolve())
