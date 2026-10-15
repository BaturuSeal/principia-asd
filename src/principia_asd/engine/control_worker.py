"""Frozen-source bootstrap for sandboxed fixed controls; no provider or evaluator."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def execute(folder):
    # This file is invoked by absolute snapshot path under Python -I.
    folder = Path(folder).resolve()
    launch = json.loads((folder / "launch.json").read_text())
    source = Path(launch["runtime_source"]).resolve()
    if Path(__file__).resolve() != source / "principia_asd/engine/control_worker.py":
        raise ValueError("Worker must execute its original source snapshot")
    sys.path[:0] = [str(source), *launch["environment"]["site_paths"]]
    for key in (
        "OPENBLAS_NUM_THREADS",
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "BLIS_NUM_THREADS",
    ):
        os.environ[key] = "1"
    from threadpoolctl import threadpool_limits

    from principia_asd.control_jobs import verify_binding
    from principia_asd.engine.bound_checkpoint import DurableBoundRun, RecoveryRequired
    from principia_asd.engine.bound_controls import BoundControl
    from principia_asd.io import contained, read_csv, read_json, write_json
    from principia_asd.runtime import log_event, now
    from principia_asd.store.worker_limits import WorkerCancelled, process_limits, worker_slot

    config, request = verify_binding(folder)
    inputs = read_json(folder / "inputs.json")

    def cancelled():
        return (folder / "cancel.requested").exists()

    # The watchdog covers slot waiting and input loading as well as numerical work.
    with process_limits(
        folder, wall_seconds=request["limits"]["max_seconds"], memory_bytes=config["memory_bytes"]
    ):
        try:
            with worker_slot(request["workspace"], cancelled), threadpool_limits(limits=1):
                task = read_json(contained(folder, inputs["contract"]["path"]))
                train, dev = [
                    read_csv(contained(folder, inputs[k]["path"])) for k in ("train", "dev")
                ]
                control = BoundControl(
                    task,
                    train,
                    dev,
                    control=request["control"],
                    run_id=folder.name,
                    limits=request["limits"],
                    stopped=cancelled,
                    event=lambda stage, detail: log_event(folder, stage, detail),
                )
                if control.configuration["sha256"] != request["configuration_sha256"]:
                    raise ValueError("Prepared control configuration differs from staged inputs")
                journal = DurableBoundRun(
                    control,
                    folder,
                    provider_binding={
                        "provider": "none",
                        "launch_sha256": config["sha256"],
                        "api_calls": 0,
                    },
                )
                result = journal.run()
            write_json(
                folder / "state.json",
                {
                    "status": "cancelled"
                    if (result.get("failure") or {}).get("type") == "InterruptedError"
                    else result["status"],
                    "finished_at": now(),
                    "result_sha256": result["sha256"],
                    "ranking_authorized": False,
                    "api_calls": 0,
                },
            )
            return result
        except (RecoveryRequired, WorkerCancelled) as exc:
            write_json(
                folder / "state.json",
                {
                    "status": "cancelled"
                    if isinstance(exc, WorkerCancelled)
                    else "recovery_required",
                    "reason": str(exc),
                    "checked_at": now(),
                    "api_calls": 0,
                },
            )
            raise


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Expected one private control run folder")
    execute(sys.argv[1])
