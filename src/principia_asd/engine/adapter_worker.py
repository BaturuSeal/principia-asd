"""Trusted explicit-expression worker; credentials belong to the host gateway.

No generated Python is executed. The expression interpreter has no file/network
operations. This does not authorize arbitrary-code execution or public ranking.
"""

from __future__ import annotations

import os
import time
from pathlib import Path


def execute_worker(folder, *, adapter, entrypoint):
    from .bound_worker import THREAD_VARIABLES

    for key in THREAD_VARIABLES:
        os.environ[key] = "1"
    from threadpoolctl import threadpool_limits

    from ..adapter_jobs import engine_class, specification, verify_binding
    from ..io import contained, read_csv, read_json, sha, write_json
    from ..llm.siliconflow import PRICE_SOURCE, PROFILES, SiliconFlowClient
    from ..runtime import log_event, now
    from ..store.ledger import CostLedger
    from ..store.worker_limits import process_limits, worker_slot
    from .bound_checkpoint import DurableBoundRun, RecoveryRequired

    spec = specification(adapter)
    folder = Path(folder).resolve()
    config, request, settings = verify_binding(folder, adapter=adapter, check_environment=True)
    if (
        Path(entrypoint).resolve()
        != Path(config["runtime_source"]) / (spec["worker_module"].replace(".", "/") + ".py")
        or Path(__file__).resolve()
        != Path(config["runtime_source"]) / "principia_asd/engine/adapter_worker.py"
    ):
        raise ValueError("Worker must use its exact frozen copied runtime")
    if (
        config["provider"]["profiles"]
        != {m: PROFILES[m] for m in sorted(set(request["roles"].values()))}
        or config["provider"]["price_source"] != PRICE_SOURCE
    ):
        raise ValueError("Frozen model/pricing profile changed")
    workspace = Path(settings["workspace"])

    def stopped():
        return (folder / "cancel.requested").exists()

    started = time.monotonic()
    remaining = request["limits"]["max_seconds"]
    if (folder / "manifest.json").exists():
        remaining -= max(0, time.time() - read_json(folder / "manifest.json")["created_at"])
    try:
        with (
            process_limits(folder, wall_seconds=max(1, remaining)),
            worker_slot(workspace, stopped),
            threadpool_limits(limits=1),
        ):
            inputs = read_json(folder / "inputs.json")
            task = read_json(contained(folder, inputs["contract"]["path"]))
            capabilities = read_json(folder / "capabilities.json")
            gateway = SiliconFlowClient(
                env_file=settings.get("env_file"),
                ledger=CostLedger(workspace / "costs.sqlite", 3000),
                artifact_dir=folder / "provider",
                attempt_cap_cny=request["attempt_cap_cny"],
                capabilities=capabilities,
            )
            engine = engine_class(adapter)(
                task,
                read_csv(contained(folder, inputs["train"]["path"])),
                read_csv(contained(folder, inputs["dev"]["path"])),
                gateway=gateway,
                run_id=request["run_id"],
                roles=request["roles"],
                limits=request["limits"],
                stopped=stopped,
                event=lambda stage, detail: log_event(folder, stage, detail),
            )
            engine.host.started = started
            if (
                engine.configuration["sha256"] != config["configuration_sha256"]
                or engine.configuration["sha256"] != request["configuration_sha256"]
            ):
                raise ValueError("Frozen scientific configuration changed")
            journal = DurableBoundRun(
                engine,
                folder,
                provider_binding={
                    "launch_sha256": config["sha256"],
                    "capabilities_sha256": sha(capabilities),
                    "provider_timeout_seconds": gateway.timeout,
                    "profiles": config["provider"],
                    "inputs_sha256": config["inputs_sha256"],
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
