"""Dedicated development worker. No test evaluation or leaderboard publication.

Invoke with ``python -m principia_asd.engine.bound_worker --folder PRIVATE_RUN
--settings PRIVATE_SETTINGS`` only after preparing a new engineering request.
The explicit development option uses this worker; frozen comparison drivers do not.
"""

from __future__ import annotations

import argparse
import math
import os
import time
from pathlib import Path

THREAD_VARIABLES = (
    "OPENBLAS_NUM_THREADS",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "BLIS_NUM_THREADS",
)


def validate_worker_request(folder, settings):
    from ..io import read_json

    folder = Path(folder).resolve()
    workspace = Path(settings["workspace"]).resolve()
    root = workspace / "bound-runs"
    if folder.parent != root or folder.is_symlink():
        raise ValueError(
            "Development jobs must be direct children of the private bound-runs folder"
        )
    for key in ("data_root", "leaderboard_root", "project_root"):
        if settings.get(key) and workspace.is_relative_to(Path(settings[key]).resolve()):
            raise ValueError("Mutable worker workspace must stay outside upload roots")
    request = read_json(folder / "request.json")
    if set(request) != {"scope", "run_id", "scenario_path", "roles", "limits", "attempt_cap_cny"}:
        raise ValueError("Exact development request fields required")
    if (
        request["scope"]
        not in {"engineering_only_explicit_state_v1", "engineering_only_explicit_state_v2"}
        or request["run_id"] != folder.name
    ):
        raise ValueError("Explicit engineering scope and matching run identity required")
    scenario = Path(request["scenario_path"]).resolve()
    if not (
        scenario.is_relative_to(Path(settings["data_root"]).resolve())
        or scenario.is_relative_to(workspace / "imports")
    ):
        raise ValueError("Scenario is outside the configured data edition")
    cap = request["attempt_cap_cny"]
    if type(cap) not in (float, int) or not math.isfinite(cap) or not 0 < cap <= 12:
        raise ValueError("Attempt cap must be in (0,12] CNY")
    maximum = {
        "max_calls": 32,
        "max_fits": 16,
        "max_structures": 8000,
        "max_optimizer_evaluations": 4096,
        "max_seconds": 2400,
    }
    if not isinstance(request["limits"], dict) or set(request["limits"]) - set(maximum):
        raise ValueError("Unknown worker limit")
    if any(type(v) is not int or not 1 <= v <= maximum[k] for k, v in request["limits"].items()):
        raise ValueError("Worker limit exceeds the execution envelope")
    return folder, workspace, scenario, request


def execute_worker(folder, settings):
    # This entry point is a dedicated process. Set before importing numerical libs.
    for name in THREAD_VARIABLES:
        os.environ[name] = "1"
    from threadpoolctl import threadpool_limits

    from ..io import contained, file_sha, read_csv, read_json, sha, write_json
    from ..llm.siliconflow import PRICE_SOURCE, PROFILES, SiliconFlowClient
    from ..runtime import log_event, now
    from ..store.ledger import CostLedger
    from ..store.worker_limits import process_limits, worker_slot
    from .bound_checkpoint import DurableBoundRun, RecoveryRequired
    from .bound_engine import BoundEngine
    from .bound_engine_v2 import SchemaBoundEngine

    folder, workspace, scenario, request = validate_worker_request(folder, settings)
    # Loader reads only the task contract, train and dev. There is no evaluator path.
    contract = scenario / "task-contracts/task-001.json"
    task = read_json(contract)
    train_path, dev_path = [contained(scenario, task["split"][key]) for key in ("train", "dev")]
    capabilities = read_json(workspace / "capabilities.json")
    gateway = SiliconFlowClient(
        env_file=settings.get("env_file"),
        ledger=CostLedger(workspace / "costs.sqlite", 3000),
        artifact_dir=folder / "provider",
        attempt_cap_cny=request["attempt_cap_cny"],
        capabilities=capabilities,
    )
    cls = (
        SchemaBoundEngine
        if request["scope"] == "engineering_only_explicit_state_v2"
        else BoundEngine
    )
    engine = cls(
        task,
        read_csv(train_path),
        read_csv(dev_path),
        gateway=gateway,
        run_id=request["run_id"],
        roles=request["roles"],
        limits=request["limits"],
        stopped=lambda: (folder / "cancel.requested").exists(),
        event=lambda stage, detail: log_event(folder, stage, detail),
    )
    binding = {
        "request_sha256": sha(request),
        "price_source": PRICE_SOURCE,
        "profiles": PROFILES,
        "capabilities_sha256": sha(capabilities),
        "provider_timeout_seconds": gateway.timeout,
        "attempt_cap_cny": request["attempt_cap_cny"],
        "global_cap_cny": 3000,
        "inputs": {
            "contract": file_sha(contract),
            "train": file_sha(train_path),
            "dev": file_sha(dev_path),
        },
        "numerical_threads": 1,
        "memory_bytes": 4 * 1024**3,
    }
    journal = DurableBoundRun(engine, folder, provider_binding=binding)
    try:
        with worker_slot(workspace, engine.stopped), threadpool_limits(limits=1):
            remaining = engine.limits["max_seconds"]
            if (folder / "manifest.json").exists():
                remaining -= max(0, time.time() - read_json(folder / "manifest.json")["created_at"])
            with process_limits(folder, wall_seconds=max(1, remaining)):
                result = journal.run()
        write_json(
            folder / "state.json",
            {
                "status": "cancelled"
                if (result.get("failure") or {}).get("type") == "InterruptedError"
                else result["status"],
                "finished_at": now(),
                "ranking_authorized": False,
                "result_sha256": result["sha256"],
            },
        )
        return result
    except RecoveryRequired as exc:
        write_json(
            folder / "state.json",
            {
                "status": "recovery_required",
                "reason": str(exc),
                "checked_at": now(),
                "replayed_paid_calls": 0,
            },
        )
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, required=True)
    parser.add_argument("--settings", type=Path, required=True)
    args = parser.parse_args()
    from ..io import read_json

    result = execute_worker(args.folder, read_json(args.settings))
    print({"status": result["status"], "ranking_authorized": False, "sha256": result["sha256"]})


if __name__ == "__main__":
    main()
