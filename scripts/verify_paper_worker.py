"""Hard-exit verification of the data-to-paper worker with synthetic transport."""

import argparse
import inspect
import json
import subprocess
import tempfile
from pathlib import Path


def helper():
    # Script helpers are engineering fixtures, never injected into copied methods.
    import importlib.util

    path = Path(__file__).with_name("verify_laboratory_worker.py")
    spec = importlib.util.spec_from_file_location("laboratory_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify(workspace, receipt, *, protocol="v1"):
    from principia_asd import bound_jobs

    if protocol == "v2":
        from principia_asd import paper_v2_jobs as paper_jobs
    else:
        from principia_asd import paper_jobs
    from principia_asd.io import file_sha, read_json, write_json
    from principia_asd.runtime import now
    from principia_asd.store.ledger import CostLedger

    assert "site-packages" in inspect.getfile(paper_jobs)
    workspace.mkdir(parents=True, exist_ok=True)
    proofs = []
    for crash_at in (2, 4, 6):
        root = Path(tempfile.mkdtemp(prefix=f"paper-recovery-{crash_at}-", dir=workspace))
        settings, scenario = helper().fixture(root)
        folder = paper_jobs.prepare(settings, scenario)
        cfg = read_json(folder / "launch.json")
        command = [
            cfg["interpreter"],
            "-I",
            "-B",
            str(Path(__file__).resolve()),
            "--child",
            str(folder),
            "--case",
            "both_repairs",
            "--crash-at",
        ]
        for phase, point, expected in (
            ("interrupted", crash_at, 91),
            ("resumed", -1, 0),
            ("terminal", -1, 0),
        ):
            proc = subprocess.run(command + [str(point)], capture_output=True, timeout=60)
            (root / (phase + ".log")).write_bytes(proc.stdout + proc.stderr)
            assert proc.returncode == expected, proc.stderr.decode()[-1800:]
            if phase == "resumed":
                digest = file_sha(folder / "result.json")
            if phase == "terminal":
                assert digest == file_sha(folder / "result.json")
        config, _, _ = paper_jobs.verify_binding(folder, check_environment=True)
        result = paper_jobs.verify_finished(folder, config)
        bound_jobs.launch(folder)
        calls = [
            json.loads(line) for line in (folder / "mock-dispatches.jsonl").read_text().splitlines()
        ]
        ledger = CostLedger(root / "private/costs.sqlite").summary()
        assert len(calls) == len({r["request_id"] for r in calls}) == ledger["requests"] == 6
        assert (
            result["status"] == "complete"
            and result["host_submission"]["accounting"]["fitting_attempts"] == 1
        )
        assert len(result["statistical_accounting"]) == 1 and result["verified_report"]["valid"]
        proofs.append(
            {
                "crash_after_settled_request": crash_at,
                "unique_mock_dispatches": 6,
                "duplicate_dispatches": 0,
                "fitting_attempts": 1,
                "optimizer_evaluations": result["host_submission"]["accounting"][
                    "optimizer_evaluations"
                ],
                "fixed_slots": 3,
                "nominations": 1,
                "facts_sha256": result["computed_facts"]["sha256"],
                "result_sha256": result["sha256"],
                "terminal_read_unchanged": file_sha(folder / "result.json") == digest,
            }
        )
    value = {
        "checked_at": now(),
        "status": "passed",
        "protocol": protocol,
        "source_is_installed_distribution": True,
        "scope": "Frozen copied worker and real ledger/cache code with synthetic transport; hard exits during conditional repairs and post-freeze review recover exactly. No live API or ranking.",
        "cases": proofs,
        "real_api_calls": 0,
        "ranking_authorized": False,
        "scientific_review": "not_assessed",
        "jobs_module_sha256": file_sha(Path(inspect.getfile(paper_jobs))),
    }
    write_json(receipt, value, immutable=True)
    print(json.dumps(value, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", type=Path)
    parser.add_argument("--crash-at", type=int, default=-1)
    parser.add_argument("--case", default="complete")
    parser.add_argument("--crash-local")
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--protocol", choices=["v1", "v2"], default="v1")
    args = parser.parse_args()
    if args.child:
        helper().child(
            args.child, args.crash_at, adapter="paper", case=args.case, crash_local=args.crash_local
        )
    else:
        verify(args.workspace, args.receipt, protocol=args.protocol)
