"""Hard-exit/restart proof using installed code and a strictly mocked transport.

Creates only new private engineering fixtures. Never uses real credentials or a
network connection; the real provider adapter and isolated test ledger do execute.
"""

import argparse
import inspect
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def child(root, crash_at):
    sys.dont_write_bytecode = True
    for key in (
        "OPENBLAS_NUM_THREADS",
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        os.environ[key] = "1"
    os.environ["SILICONFLOW_API_KEY"] = "offline-engineering-fixture"
    import principia_asd.llm.siliconflow as sf
    from principia_asd.engine.bound_worker import execute_worker
    from principia_asd.io import read_json

    # Import the disclosed scripted protocol helper from the release script folder.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from verify_bound_engine import ScriptedGateway

    simulated = ScriptedGateway()
    original_complete = sf.SiliconFlowClient.complete

    def complete(self, **request):
        response = original_complete(self, **request)
        if not request.get("_recovery_only") and self.ledger.summary()["requests"] == crash_at:
            os._exit(91)  # Loss after ledger settlement but before method checkpoint.
        return response

    class Reply:
        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, *args):
            return json.dumps(self.body).encode()

    def offline_transport(request, **kwargs):
        payload = json.loads(request.data)
        context = json.loads(payload["messages"][1]["content"])
        if "development_feedback" in context:
            simulated.plans = len(context["development_feedback"]["earlier_round_critiques"])
            if payload["model"] == "deepseek-ai/DeepSeek-V4-Flash":
                simulated.plans += 1
        request_id = request.get_header("X-trace-id")
        with (root / "mock-dispatches.jsonl").open("a") as stream:
            stream.write(json.dumps({"request_id": request_id, "model": payload["model"]}) + "\n")
        result = simulated.complete(
            model=payload["model"],
            system=payload["messages"][0]["content"],
            prompt=payload["messages"][1]["content"],
            request_id=request_id,
            max_tokens=payload["max_tokens"],
            temperature=payload["temperature"],
        )
        return Reply(
            {
                "model": payload["model"],
                "usage": {"prompt_tokens": 10, "completion_tokens": 40},
                "choices": [{"message": {"content": result["text"]}, "finish_reason": "stop"}],
            }
        )

    sf.urllib.request.urlopen = offline_transport
    sf.SiliconFlowClient.complete = complete
    result = execute_worker(
        root / "private/bound-runs/recovery-fixture", read_json(root / "settings.json")
    )
    assert result["status"] == "complete", result["failure"]


def verify(workspace, protocol="v1"):
    import numpy as np

    from principia_asd.engine.bound_checkpoint import DurableBoundRun
    from principia_asd.io import file_sha, read_json, write_csv, write_json
    from principia_asd.methods.registry import DEFAULT_ROLES
    from principia_asd.runtime import now
    from principia_asd.store.ledger import CostLedger

    workspace.mkdir(parents=True, exist_ok=True)
    proofs = []
    for crash_at in (3, 7):
        root = Path(tempfile.mkdtemp(prefix=f"bound-recovery-call-{crash_at}-", dir=workspace))
        folder = root / "private/bound-runs/recovery-fixture"
        scenario = root / "data/synthetic"
        task = {
            "inputs": ["x"],
            "output": "y",
            "metric": {"primary": "rmse"},
            "stability": {"ranking": False},
            "split": {"train": "train.csv", "dev": "dev.csv"},
        }
        write_json(scenario / "task-contracts/task-001.json", task)
        for label, values in (("train", range(-3, 4)), ("dev", [-2.5, -0.5, 1.5])):
            rows = [
                {
                    "sample_id": f"{label}{i}",
                    "group": label,
                    "x": float(x),
                    "y": float(0.4 + 0.2 * np.tanh(x / 2)),
                }
                for i, x in enumerate(values)
            ]
            write_csv(scenario / f"{label}.csv", rows, ["sample_id", "group", "x", "y"])
        write_json(
            root / "settings.json",
            {
                "workspace": str(root / "private"),
                "data_root": str(root / "data"),
                "leaderboard_root": str(root / "leaderboard"),
            },
        )
        write_json(
            root / "private/capabilities.json",
            {
                v: {"state": "verified", "scope": "offline fixture only"}
                for v in DEFAULT_ROLES.values()
            },
        )
        write_json(
            folder / "request.json",
            {
                "scope": "engineering_only_explicit_state_" + protocol,
                "run_id": folder.name,
                "scenario_path": str(scenario),
                "roles": DEFAULT_ROLES,
                "limits": {},
                "attempt_cap_cny": 12,
            },
            immutable=True,
        )
        command = [
            sys.executable,
            "-B",
            "-I",
            str(Path(__file__).resolve()),
            "--child",
            str(root),
            "--crash-at",
            str(crash_at),
        ]
        for stage, expected in (("interrupted", 91), ("resumed", 0), ("completed-read", 0)):
            proc = subprocess.run(
                command if stage == "interrupted" else command[:-1] + ["-1"],
                capture_output=True,
                timeout=60,
            )
            (root / f"{stage}.log").write_bytes(proc.stdout + proc.stderr)
            assert proc.returncode == expected, (
                stage,
                proc.returncode,
                proc.stderr.decode()[-1500:],
            )
            if stage == "resumed":
                completed_hash = file_sha(folder / "result.json")
            elif stage == "completed-read":
                assert completed_hash == file_sha(folder / "result.json")
        result = read_json(folder / "result.json")["result"]
        dispatches = [
            json.loads(line) for line in (root / "mock-dispatches.jsonl").read_text().splitlines()
        ]
        assert len(dispatches) == len({r["request_id"] for r in dispatches}) == 7
        assert result["model_requests"] == 7
        assert result["policy"] == f"principia-explicit-state-protocol-{protocol}-dev"
        assert result["host_submission"]["accounting"]["fitting_attempts"] == 6
        assert result["host_submission"]["accounting"]["optimizer_evaluations"] == 46
        ledger = CostLedger(root / "private/costs.sqlite").summary()
        assert ledger["states"] == {"completed": 7}
        proofs.append(
            {
                "crash_after_settled_request": crash_at,
                "process_exit_code": 91,
                "unique_mock_dispatches": 7,
                "duplicate_dispatches": 0,
                "fits": 6,
                "optimizer_evaluations": 46,
                "immutable_completed_read": True,
                "frozen_nomination_sha256": result["nomination_freeze"]["sha256"],
                "result_sha256": completed_hash,
                "private_fixture_folder": str(root),
            }
        )
    receipt = {
        "checked_at": now(),
        "status": "passed_offline_hard_exit_recovery",
        "protocol_revision": protocol,
        "scope": "Installed dedicated worker, mocked transport, real train fitting and isolated fixture ledger; not a live model trial",
        "source_is_installed_distribution": "site-packages" in inspect.getfile(DurableBoundRun),
        "checkpoint_module_sha256": file_sha(Path(inspect.getfile(DurableBoundRun))),
        "cases": proofs,
        "real_api_calls": 0,
        "historical_campaign_changed": False,
        "public_ranking_authorized": False,
        "ui_integration": "verified separately; see docs/BOUND_INTERACTIVE_UI_VERIFICATION.json",
        "limitation": "Ambiguous calls and interrupted local fitting remain recovery_required; no refit or automatic replay",
    }
    write_json(
        Path(__file__).resolve().parents[1]
        / (
            "docs/BOUND_RECOVERY_VERIFICATION.json"
            if protocol == "v1"
            else "docs/BOUND_RECOVERY_V2_VERIFICATION.json"
        ),
        receipt,
    )
    print(json.dumps({"status": receipt["status"], "cases": len(proofs), "real_api_calls": 0}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--child", type=Path)
    parser.add_argument("--crash-at", type=int, default=-1)
    parser.add_argument("--protocol", choices=["v1", "v2"], default="v1")
    args = parser.parse_args()
    if args.child:
        child(args.child, args.crash_at)
    elif args.workspace:
        verify(args.workspace, args.protocol)
    else:
        parser.error("Supply a private fixture workspace")
