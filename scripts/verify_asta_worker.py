"""Installed Asta worker hard-exit proof; synthetic transport, zero live calls."""

import argparse
import importlib.util
import inspect
import json
import subprocess
import tempfile
from pathlib import Path


def helper():
    path = Path(__file__).with_name("verify_laboratory_worker.py")
    spec = importlib.util.spec_from_file_location("asta_worker_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify(workspace, receipt):
    from principia_asd import asta_jobs, bound_jobs
    from principia_asd.io import file_sha, read_json, write_json
    from principia_asd.runtime import now
    from principia_asd.store.ledger import CostLedger

    assert "site-packages" in inspect.getfile(asta_jobs)
    workspace.mkdir(parents=True, exist_ok=True)
    proofs = []
    # Freeze, observers, engineering, posteriors and post-nomination reporting.
    for crash_at in (1, 3, 4, 6, 25):
        root = Path(tempfile.mkdtemp(prefix=f"asta-recovery-{crash_at}-", dir=workspace))
        settings, scenario = helper().fixture(root)
        folder = asta_jobs.prepare(settings, scenario)
        cfg = read_json(folder / "launch.json")
        command = [
            cfg["interpreter"],
            "-I",
            "-B",
            str(Path(__file__).resolve()),
            "--child",
            str(folder),
            "--crash-at",
        ]
        for phase, point, expected in (
            ("interrupted", crash_at, 91),
            ("resumed", -1, 0),
            ("terminal", -1, 0),
        ):
            proc = subprocess.run(command + [str(point)], capture_output=True, timeout=90)
            (root / (phase + ".log")).write_bytes(proc.stdout + proc.stderr)
            assert proc.returncode == expected, proc.stderr.decode()[-2000:]
            if phase == "resumed":
                digest = file_sha(folder / "result.json")
            if phase == "terminal":
                assert digest == file_sha(folder / "result.json")
        config, _, _ = asta_jobs.verify_binding(folder, check_environment=True)
        result = asta_jobs.verify_finished(folder, config)
        bound_jobs.launch(folder)
        calls = [json.loads(s) for s in (folder / "mock-dispatches.jsonl").read_text().splitlines()]
        ledger = CostLedger(root / "private/costs.sqlite").summary()
        assert len(calls) == len({r["request_id"] for r in calls}) == ledger["requests"] == 25
        assert result["status"] == "complete"
        assert result["host_submission"]["accounting"]["fitting_attempts"] == 4
        assert result["search_tree"][0]["visits"] == 4
        assert len(result["selection"]["nominations"]) == 3
        proofs.append(
            {
                "crash_after_settled_request": crash_at,
                "unique_mock_dispatches": 25,
                "duplicate_dispatches": 0,
                "fitting_attempts": 4,
                "optimizer_evaluations": result["host_submission"]["accounting"][
                    "optimizer_evaluations"
                ],
                "fixed_slots": 3,
                "tree_visits": 4,
                "result_sha256": result["sha256"],
                "terminal_read_unchanged": file_sha(folder / "result.json") == digest,
            }
        )
    value = {
        "checked_at": now(),
        "status": "passed",
        "source_is_installed_distribution": True,
        "scope": "Frozen copied expression worker and real ledger/cache code with synthetic transport. Hard exits recover unique requests, experiments and tree updates. This trusted provider worker is not an arbitrary-code sandbox; generated expressions cannot access files or network.",
        "cases": proofs,
        "real_api_calls": 0,
        "ranking_authorized": False,
        "scientific_review": "not_assessed",
        "jobs_module_sha256": file_sha(Path(inspect.getfile(asta_jobs))),
    }
    write_json(receipt, value, immutable=True)
    print(json.dumps(value, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", type=Path)
    parser.add_argument("--crash-at", type=int, default=-1)
    parser.add_argument("--crash-local")
    parser.add_argument("--case", default="complete")
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    if args.child:
        helper().child(
            args.child, args.crash_at, adapter="asta", case=args.case, crash_local=args.crash_local
        )
    else:
        verify(args.workspace, args.receipt)
