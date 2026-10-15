"""Private, append-only checkpoints for the opt-in explicit-state protocol.

Committed local work is restored, never refitted. A crashed provider boundary may
consume only a settled cached response. An interrupted local operation is blocked:
its unknown numerical work is not silently repeated or reported as zero work.
"""

from __future__ import annotations

import copy
import fcntl
import math
import platform
import time
from pathlib import Path

import numpy as np
import scipy

from ..io import file_sha, read_json, sha, write_json
from .bindings import StateRegistry, verify_program

CHECKPOINT_POLICY = "explicit-state-checkpoints-v1-dev"
ENGINE_FIELDS = (
    "kernels",
    "references",
    "kernel_sources",
    "trace",
    "rejections",
    "rounds",
    "requests",
)
HOST_FIELDS = (
    "candidates",
    "failures",
    "fits",
    "optimizer_evaluations",
    "duplicate_requests",
    "closed",
)


class RecoveryRequired(RuntimeError):
    recovery_required = True


class RecordedStepFailure(RuntimeError):
    def __init__(self, record):
        self.original_type = record["type"]
        super().__init__(record["reason"])


def runtime_binding():
    root = Path(__file__).resolve().parents[1]
    return {
        "sources_sha256": sha(
            {str(p.relative_to(root)): file_sha(p) for p in sorted(root.rglob("*.py"))}
        ),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "machine": platform.machine(),
        "system": platform.system(),
    }


def _snapshot(engine):
    h = engine.host
    return {
        "engine": {k: copy.deepcopy(getattr(engine, k)) for k in ENGINE_FIELDS},
        "host": {k: copy.deepcopy(getattr(h, k)) for k in HOST_FIELDS},
        "seen": sorted(h.seen),
        "artifacts": copy.deepcopy(h.registry.artifacts),
        "states": copy.deepcopy(h.registry.records),
        "frozen": copy.deepcopy(h._frozen),
        "cpu_seconds": time.process_time() - h.cpu_started,
        "wall_seconds": time.monotonic() - h.started,
    }


def _restore(engine, state, created_at):
    h = engine.host
    registry = StateRegistry(state["artifacts"])
    for digest, record in state["states"].items():
        if (
            registry.register(record["artifact_sha256"], record["value_path"], record["kind"])
            != digest
        ):
            raise ValueError("Checkpoint state reference mismatch")
    for digest, card in state["host"]["candidates"].items():
        if digest != sha({k: v for k, v in card.items() if k != "candidate_id"}):
            raise ValueError("Checkpoint candidate mutation")
        if card["context"] != h.context:
            raise ValueError("Checkpoint candidate context mismatch")
        verify_program(card["program"], registry)
    for k, v in state["host"].items():
        if k not in HOST_FIELDS:
            raise ValueError("Unknown checkpoint host state")
        setattr(h, k, copy.deepcopy(v))
    for k, v in state["engine"].items():
        if k not in ENGINE_FIELDS:
            raise ValueError("Unknown checkpoint engine state")
        setattr(engine, k, copy.deepcopy(v))
    h.registry, h.seen, h._frozen = registry, set(state["seen"]), copy.deepcopy(state["frozen"])
    for seconds in (state["cpu_seconds"], state["wall_seconds"]):
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError("Invalid checkpoint accounting")
    # Downtime consumes the original wall-time envelope, never a fresh allowance.
    h.started = time.monotonic() - max(time.time() - created_at, state["wall_seconds"])
    h.cpu_started = time.process_time() - state["cpu_seconds"]


class DurableBoundRun:
    """Host-owned JSON journal; one lock per run. No pickle or model-supplied state.

    provider_binding must identify the frozen capability, prices and gateway
    configuration without credentials. This is an engineering API, not admission
    to the main registry or authorization to replace historical comparisons.
    """

    def __init__(self, engine, folder, *, provider_binding, after_record=lambda record: None):
        if not isinstance(provider_binding, dict) or not provider_binding:
            raise ValueError("An explicit provider configuration binding is required")
        self.engine, self.folder = engine, Path(folder)
        self.binding = {
            "policy": CHECKPOINT_POLICY,
            "run_id": engine.run_id,
            "configuration": engine.configuration,
            "runtime": runtime_binding(),
            "provider": copy.deepcopy(provider_binding),
        }
        self.after_record = after_record
        self.records, self.committed, self.pending = [], [], None
        self.cursor, self.active = 0, False

    def _append(self, record):
        value = {
            **record,
            "sequence": len(self.records),
            "previous_sha256": self.records[-1]["sha256"] if self.records else sha(self.manifest),
            "at": time.time(),
            "state": _snapshot(self.engine),
        }
        value["sha256"] = sha(value)
        write_json(
            self.folder / "checkpoints" / f"{len(self.records):04}.json", value, immutable=True
        )
        self.records.append(value)
        # Hook is only for fault-injection tests. Disk commit precedes the callback.
        self.after_record(copy.deepcopy(value))
        return value

    def _load(self):
        path = self.folder / "manifest.json"
        if path.exists():
            self.manifest = read_json(path)
            if self.manifest["binding"] != self.binding:
                raise ValueError("Frozen run context/runtime/provider configuration changed")
        else:
            if (self.folder / "checkpoints").exists() or (self.folder / "result.json").exists():
                raise ValueError("Orphaned checkpoints without a manifest")
            self.manifest = {"binding": self.binding, "created_at": time.time()}
            write_json(path, self.manifest, immutable=True)
        previous = sha(self.manifest)
        for i, path in enumerate(sorted((self.folder / "checkpoints").glob("*.json"))):
            record = read_json(path)
            if (
                path.name != f"{i:04}.json"
                or record["sequence"] != i
                or record["previous_sha256"] != previous
                or record["sha256"] != sha({k: v for k, v in record.items() if k != "sha256"})
                or record["at"] < self.manifest["created_at"]
                or record["at"] > time.time()
            ):
                raise ValueError("Checkpoint chain, clock or content integrity failed")
            if record["type"] == "intent" and self.pending is None:
                self.pending = record
            elif record["type"] == "commit" and self.pending is not None:
                if (record["name"], record["kind"]) != (self.pending["name"], self.pending["kind"]):
                    raise ValueError("Checkpoint operation mismatch")
                self.committed.append(record)
                self.pending = None
            else:
                raise ValueError("Invalid checkpoint transition")
            self.records.append(record)
            previous = record["sha256"]
        if self.records:
            _restore(self.engine, self.records[-1]["state"], self.manifest["created_at"])

    def step(self, name, kind, action):
        if not self.active:
            raise RuntimeError("Checkpoint execution requires the exclusive run lock")
        if self.cursor < len(self.committed):
            saved = self.committed[self.cursor]
            self.cursor += 1
            if (saved["name"], saved["kind"]) != (name, kind):
                raise ValueError("Checkpoint algorithm order changed")
            if saved.get("error"):
                raise RecordedStepFailure(saved["error"])
            return copy.deepcopy(saved["output"])
        recovering = self.pending is not None
        if recovering:
            if (self.pending["name"], self.pending["kind"]) != (name, kind):
                raise RecoveryRequired("Interrupted operation does not match the frozen algorithm")
            if kind != "provider":
                raise RecoveryRequired(
                    "Interrupted local operation; numerical work since last checkpoint is unknown. "
                    "Preserve this attempt; do not refit or reset its accounting."
                )
        else:
            self.pending = self._append({"type": "intent", "name": name, "kind": kind})
        original = self.engine.gateway
        if recovering:

            class CacheOnly:
                def complete(self, **request):
                    try:
                        return original.recover_completed(**request)
                    except Exception as exc:
                        raise RecoveryRequired(
                            "Provider boundary has no verified settled response; no request replayed: "
                            + type(exc).__name__
                        ) from exc

            self.engine.gateway = CacheOnly()
        output, error = None, None
        try:
            output = action()
        except RecoveryRequired:
            raise
        except Exception as exc:
            error = {"type": type(exc).__name__, "reason": str(exc)[:300]}
        finally:
            self.engine.gateway = original
        saved = self._append(
            {"type": "commit", "name": name, "kind": kind, "output": output, "error": error}
        )
        self.committed.append(saved)
        self.pending, self.cursor = None, self.cursor + 1
        if error:
            raise RecordedStepFailure(error)
        return output

    def run(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        with (self.folder / "worker.lock").open("a+") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RecoveryRequired(
                    "Another worker owns this run; no duplicate launched"
                ) from exc
            self.active = True
            try:
                self.records, self.committed, self.pending, self.cursor = [], [], None, 0
                self._load()
                result_path = self.folder / "result.json"
                if result_path.exists():
                    saved = read_json(result_path)
                    if saved["checkpoint_sha256"] != self.records[-1]["sha256"] or saved["result"][
                        "sha256"
                    ] != sha({k: v for k, v in saved["result"].items() if k != "sha256"}):
                        raise ValueError("Frozen result or checkpoint changed")
                    return copy.deepcopy(saved["result"])
                self.engine.step = self.step
                result = self.engine.run()
                write_json(
                    result_path,
                    {"result": result, "checkpoint_sha256": self.records[-1]["sha256"]},
                    immutable=True,
                )
                return result
            finally:
                self.active = False
