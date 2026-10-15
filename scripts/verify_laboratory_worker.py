"""Hard-exit proof of the frozen Laboratory worker, using mocked transport only."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def child(folder, crash_at, *, adapter="laboratory", case="complete", crash_local=None):
    launch = json.loads((folder / "launch.json").read_text())
    sys.path.insert(0, launch["runtime_source"])
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    os.environ["SILICONFLOW_API_KEY"] = "synthetic-offline-worker-fixture"
    import principia_asd.llm.siliconflow as sf

    if adapter == "laboratory":
        from verify_bound_laboratory import ScriptedLaboratory

        from principia_asd.engine.laboratory_worker import execute_worker

        simulated = ScriptedLaboratory(case)
    elif adapter == "paper":
        from verify_bound_data_to_paper import ScriptedPaper

        if launch["policy"] == "engineering_only_data_to_paper_explicit_v2":
            from principia_asd.engine.paper_v2_worker import execute_worker
        elif launch["policy"] == "engineering_only_data_to_paper_explicit_v1":
            from principia_asd.engine.paper_worker import execute_worker
        else:
            raise ValueError("Unknown Paper worker binding")

        simulated = ScriptedPaper(case)
    elif adapter == "asta":
        from verify_bound_asta import ScriptedAsta

        from principia_asd.engine.asta_worker import execute_worker

        simulated = ScriptedAsta(case)
    else:
        raise ValueError("Unknown verification adapter")
    if crash_local:
        from principia_asd.engine.bound_checkpoint import DurableBoundRun

        append = DurableBoundRun._append

        def local_exit(self, record):
            result = append(self, record)
            if record["type"] == "intent" and record["name"] == crash_local:
                os._exit(92)
            return result

        DurableBoundRun._append = local_exit
    original_complete = sf.SiliconFlowClient.complete

    def complete(self, **request):
        response = original_complete(self, **request)
        if not request.get("_recovery_only") and self.ledger.summary()["requests"] == crash_at:
            os._exit(91)
        return response

    class Reply:
        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def read(self, *a):
            return json.dumps(self.body).encode()

    def transport(request, **kwargs):
        payload = json.loads(request.data)
        rid = request.get_header("X-trace-id")
        with (folder / "mock-dispatches.jsonl").open("a") as f:
            f.write(json.dumps({"request_id": rid, "model": payload["model"]}) + "\n")
        result = simulated.complete(
            model=payload["model"],
            system=payload["messages"][0]["content"],
            prompt=payload["messages"][1]["content"],
            request_id=rid,
        )
        return Reply(
            {
                "model": payload["model"],
                "usage": {"prompt_tokens": 10, "completion_tokens": 40},
                "choices": [{"message": {"content": result["text"]}, "finish_reason": "stop"}],
            }
        )

    sf.urllib.request.urlopen = transport
    sf.SiliconFlowClient.complete = complete
    result = execute_worker(folder)
    expected = (
        "incomplete_method_execution"
        if (adapter == "paper" and case == "incorrect_report")
        or (
            adapter == "asta"
            and case
            in {
                "abstention",
                "changed_claim",
                "wrong_report",
                "forbidden_file",
                "forbidden_network",
                "forbidden_write",
            }
        )
        else "complete"
    )
    assert result["status"] == expected, result["failure"]


def fixture(root):
    import numpy as np

    from principia_asd.io import write_csv, write_json
    from principia_asd.llm.siliconflow import PROFILES

    settings = {
        "workspace": str(root / "private"),
        "project_root": str(root / "project"),
        "data_root": str(root / "data"),
        "leaderboard_root": str(root / "boards"),
        "vault": str(root / "vault"),
    }
    scenario = root / "data/scenarios/SYNTHETIC"
    task = {
        "scenario_id": "SYNTHETIC",
        "inputs": ["x"],
        "output": "y",
        "metric": {"primary": "rmse"},
        "stability": {"ranking": False},
        "split": {"train": "train.csv", "dev": "dev.csv", "test": "MUST_NOT_READ.csv"},
    }
    write_json(scenario / "task-contracts/task-001.json", task)
    for label, xs in (("train", range(-3, 4)), ("dev", [-2.5, -0.5, 1.5])):
        rows = [
            {
                "sample_id": f"{label}{i}",
                "group": label,
                "x": float(x),
                "y": float(0.4 + 0.2 * np.tanh(x / 2)),
            }
            for i, x in enumerate(xs)
        ]
        write_csv(scenario / f"{label}.csv", rows, list(rows[0]))
    write_json(
        root / "private/capabilities.json",
        {
            m: {"state": "verified", "generation": p, "scope": "mocked fixture only"}
            for m, p in PROFILES.items()
        },
    )
    return settings, scenario


def verify(workspace, receipt):
    import inspect

    from principia_asd import bound_jobs, laboratory_jobs
    from principia_asd.io import file_sha, write_json
    from principia_asd.runtime import now
    from principia_asd.store.ledger import CostLedger

    workspace.mkdir(parents=True, exist_ok=True)
    proofs = []
    for crash_at in (3, 6):
        root = Path(tempfile.mkdtemp(prefix=f"laboratory-recovery-{crash_at}-", dir=workspace))
        settings, scenario = fixture(root)
        folder = laboratory_jobs.prepare(settings, scenario)
        command = [
            sys.executable,
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
            ("completed-read", -1, 0),
        ):
            proc = subprocess.run(command + [str(point)], capture_output=True, timeout=60)
            (root / (phase + ".log")).write_bytes(proc.stdout + proc.stderr)
            assert proc.returncode == expected, proc.stderr.decode()[-1800:]
            if phase == "resumed":
                digest = file_sha(folder / "result.json")
            if phase == "completed-read":
                assert digest == file_sha(folder / "result.json")
        config, _, _ = laboratory_jobs.verify_binding(folder, check_environment=True)
        result = laboratory_jobs.verify_finished(folder, config)
        bound_jobs.launch(folder)  # verified terminal read; no process or paid replay
        dispatches = [
            json.loads(s) for s in (folder / "mock-dispatches.jsonl").read_text().splitlines()
        ]
        ledger = CostLedger(root / "private/costs.sqlite").summary()
        assert (
            len(dispatches) == len({d["request_id"] for d in dispatches}) == ledger["requests"] == 6
        )
        assert result["host_submission"]["accounting"]["fitting_attempts"] == 2
        proofs.append(
            {
                "crash_after_settled_request": crash_at,
                "unique_mock_dispatches": 6,
                "duplicate_dispatches": 0,
                "fitting_attempts": 2,
                "optimizer_evaluations": result["host_submission"]["accounting"][
                    "optimizer_evaluations"
                ],
                "fixed_slots": 3,
                "result_sha256": result["sha256"],
                "terminal_read_unchanged": file_sha(folder / "result.json") == digest,
            }
        )
    value = {
        "checked_at": now(),
        "status": "passed",
        "source_is_installed_distribution": "site-packages" in inspect.getfile(laboratory_jobs),
        "scope": "Frozen copied worker, real provider accounting with synthetic transport, hard process exits and verified cache recovery. No live API or scientific ranking.",
        "cases": proofs,
        "real_api_calls": 0,
        "ranking_authorized": False,
        "scientific_review": "not_assessed",
        "jobs_module_sha256": file_sha(Path(inspect.getfile(laboratory_jobs))),
    }
    write_json(receipt, value, immutable=True)
    print(json.dumps(value, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", type=Path)
    parser.add_argument("--crash-at", type=int, default=-1)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    if args.child:
        child(args.child, args.crash_at)
    else:
        verify(args.workspace, args.receipt)
