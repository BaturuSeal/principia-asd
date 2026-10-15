"""Installed-package, zero-provider synthetic control and hard-exit proof.

Writes synthetic artifacts to a private folder; these are not benchmark trials.
Run with the separately installed verification interpreter and ``-I``.
"""

import argparse
import inspect
import os
import subprocess
import sys
import tempfile
from pathlib import Path

for variable in (
    "OPENBLAS_NUM_THREADS",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "BLIS_NUM_THREADS",
):
    os.environ[variable] = "1"

import numpy as np  # noqa: E402

from principia_asd.engine.bound_checkpoint import DurableBoundRun  # noqa: E402
from principia_asd.engine.bound_controls import CONTROLS, BoundControl  # noqa: E402
from principia_asd.engine.bound_search import BoundSearch  # noqa: E402
from principia_asd.evaluate.bound import evaluate_bound_nominations  # noqa: E402
from principia_asd.io import file_sha, read_json, write_json  # noqa: E402
from principia_asd.runtime import now  # noqa: E402


def fixture(quadratic=False):
    rng = np.random.default_rng(39)
    task = {
        "inputs": ["x0", "x1"],
        "output": "y",
        "metric": {"primary": "rmse"},
        "stability": {"ranking": False},
    }

    def rows(group, count):
        return [
            {
                "sample_id": f"{group}-{i}",
                "group": group,
                "x0": float(a),
                "x1": float(b),
                "y": float(3 + 0.2 * a + 0.1 * (b * b if quadratic else b)),
            }
            for i, (a, b) in enumerate(rng.uniform(-2, 2, size=(count, 2)))
        ]

    return task, rows("train", 30), rows("dev", 8)


def runner(folder, control="fixed_symbolic", quadratic=False, crash=None):
    def boundary(record):
        if record["type"] == "commit" and record["name"] == crash:
            os._exit(73)

    return DurableBoundRun(
        BoundControl(*fixture(quadratic), control=control, run_id=folder.name),
        folder,
        provider_binding={
            "provider": "none",
            "api_calls": 0,
            "scope": "synthetic engineering fixture",
        },
        after_record=boundary,
    )


def verify(workspace, receipt):
    workspace.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="bound-controls-fixture-", dir=workspace))
    assert "site-packages" in inspect.getfile(BoundControl), "Use an installed interpreter with -I"
    outcomes = []
    for quadratic in (False, True):
        for method in CONTROLS:
            run = folder / f"{'quadratic' if quadratic else 'affine'}-{method}"
            result = runner(run, method, quadratic).run()
            assert result["status"] == "complete", result["failure"]
            assert runner(run, method, quadratic).run() == result
            outcomes.append((run, result, quadratic))
    # Every fixture submission is frozen before synthetic confirmation assessment.
    freeze = {run.name: result["sha256"] for run, result, _ in outcomes}
    write_json(folder / "submission-freeze.json", freeze, immutable=True)

    original_fit = BoundSearch.fit

    def forbidden_fit(*args, **kwargs):
        raise AssertionError("Reassessment attempted a fit")

    BoundSearch.fit = forbidden_fit
    counts = {
        "fitting_attempts": 0,
        "optimizer_evaluations": 0,
        "candidates": 0,
        "slots": 0,
        "nominations": 0,
    }
    try:
        for run, result, quadratic in outcomes:
            args = (
                result,
                result["nomination_freeze"]["sha256"],
                [{"x0": 0.3, "x1": 0.4, "group": "synthetic-test"}],
                [3.076 if quadratic else 3.1],
            )
            assessment = evaluate_bound_nominations(*args, expected_result_sha256=freeze[run.name])
            assert assessment == evaluate_bound_nominations(
                *args, expected_result_sha256=freeze[run.name]
            )
            assert assessment["fixed_denominator"] == 3 and not assessment["ranking_authorized"]
            write_json(run / "assessment.json", assessment, immutable=True)
            counts["slots"] += 3
            counts["nominations"] += sum(
                s["status"] == "nominated" for s in result["selection"]["nominations"]
            )
            counts["candidates"] += len(result["host_submission"]["candidates"])
            for key in ("fitting_attempts", "optimizer_evaluations"):
                counts[key] += result["host_submission"]["accounting"][key]
    finally:
        BoundSearch.fit = original_fit

    recoveries = []
    for boundary in ("fixed-experiment-2", "nominate"):
        run = folder / f"recovery-{boundary}"
        cmd = [sys.executable, "-I", str(Path(__file__).resolve()), "--child", str(run)]
        child = subprocess.run(
            [*cmd, "--crash", boundary], capture_output=True, text=True, timeout=60
        )
        assert child.returncode == 73, child.stderr
        resumed = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        assert resumed.returncode == 0, resumed.stderr
        result = read_json(run / "result.json")["result"]
        assert result["status"] == "complete"
        assert result["host_submission"]["accounting"]["fitting_attempts"] == 10
        assert result["model_requests"] == 0
        assert runner(run).run() == result
        recoveries.append(
            {
                "boundary": boundary,
                "result_sha256": result["sha256"],
                "fitting_attempts": 10,
                "repeated_completed_work": 0,
            }
        )

    proof = {
        "checked_at": now(),
        "status": "passed_installed_synthetic_controls",
        "scope": "Synthetic offline fixtures only; not live model or scientific performance evidence",
        "source_is_installed_distribution": True,
        "module_sha256": file_sha(Path(inspect.getfile(BoundControl))),
        "real_api_calls": 0,
        "outcomes": 8,
        "complete": 8,
        **counts,
        "hard_exit_recovery": recoveries,
        "zero_fit_reassessment": True,
        "fixed_nomination_denominator": 24,
        "public_ranking_authorized": False,
        "historical_campaign_changed": False,
        "scientific_review": "not_assessed",
        "dedicated_worker_and_comparison_admission": "pending",
        "artifacts": {
            "private_fixture_folder": str(folder),
            "submission_freeze_sha256": file_sha(folder / "submission-freeze.json"),
        },
    }
    write_json(receipt, proof, immutable=True)
    print({k: v for k, v in proof.items() if k != "artifacts"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--child", type=Path)
    parser.add_argument("--crash")
    args = parser.parse_args()
    if args.child:
        runner(args.child, crash=args.crash).run()
    else:
        if not args.workspace or not args.receipt:
            parser.error("--workspace and --receipt are required for verification")
        verify(args.workspace, args.receipt)
