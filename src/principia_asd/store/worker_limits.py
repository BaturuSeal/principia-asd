"""Machine-local worker slots shared by the application and campaign drivers."""

import fcntl
import os
import resource
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path


class WorkerCancelled(RuntimeError):
    """Cancellation before a worker slot was acquired; no scientific work ran."""


@contextmanager
def worker_slot(workspace, cancelled=lambda: False):
    root = Path(workspace) / "worker-slots"
    root.mkdir(parents=True, exist_ok=True)
    handle = None
    while handle is None:
        if cancelled():
            raise WorkerCancelled("Cancelled while waiting for a numerical worker")
        for index in range(4):
            candidate = (root / f"{index}.lock").open("a+")
            try:
                fcntl.flock(candidate, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                candidate.close()
            else:
                handle = candidate
                break
        if handle is None:
            time.sleep(0.25)
    try:
        yield
    finally:
        handle.close()


@contextmanager
def process_limits(folder, wall_seconds=2400, memory_bytes=4 * 1024**3):
    """Watch actual process RSS; a hard exit preserves unreconciled reservations."""
    done = threading.Event()
    started = time.monotonic()

    def watch():
        while not done.wait(1):
            peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            rss = peak if sys.platform == "darwin" else peak * 1024
            reason = (
                "memory limit"
                if rss > memory_bytes
                else "wall-time limit"
                if time.monotonic() - started > wall_seconds
                else None
            )
            if reason:
                (Path(folder) / "resource-limit.txt").write_text(
                    reason + " exceeded; inspect reserved requests before recovery\n"
                )
                os._exit(137)

    threading.Thread(target=watch, daemon=True).start()
    try:
        yield
    finally:
        done.set()
