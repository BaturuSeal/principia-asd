"""macOS confinement for fixed, host-authored numerical controls.

Profile design follows the small local v1.4.3 sandbox component (PROVENANCE.md).
This is not permission to run arbitrary generated Python.
"""

from __future__ import annotations

import json
import shutil
import site
import sys
from pathlib import Path

from ..io import file_sha

POLICY = "fixed-control-macos-sandbox-v1"


def runtime():
    command = shutil.which("sandbox-exec") if sys.platform == "darwin" else None
    python = Path(sys.base_prefix) / "Resources/Python.app/Contents/MacOS/Python"
    if not command or not python.is_file():
        raise ValueError("A supported macOS sandbox is required; there is no unisolated fallback")
    return {
        "sandbox": command,
        "python": str(python.resolve()),
        "python_sha256": file_sha(python),
        "base_prefix": str(Path(sys.base_prefix).resolve()),
        "site_paths": [str(Path(p).resolve()) for p in site.getsitepackages()],
        "python_version": sys.version,
    }


def profile(folder, source, workspace, binding):
    folder, source, workspace = [Path(p).resolve() for p in (folder, source, workspace)]

    def q(path):
        return json.dumps(str(path), ensure_ascii=False)

    lines = [
        "(version 1)",
        "(deny default)",
        '(import "system.sb")',
        "(deny network*)",
        "(deny process-fork)",
        "(allow sysctl-read)",
        "(allow mach-lookup)",
        f"(allow process-exec (literal {q(binding['python'])}))",
    ]
    for root in sorted(
        {
            "/System",
            "/usr",
            binding["base_prefix"],
            *binding["site_paths"],
            str(source),
            str(folder),
        }
    ):
        lines.append(f"(allow file-read* (subpath {q(root)}))")
    # The numerical semaphore is the only shared writable location.
    slots = workspace / "worker-slots"
    lines += [
        f"(allow file-read* (literal {q(source.parent / 'binding.json')}))",
        f"(allow file-read-metadata (literal {q(workspace)}))",
        f"(allow file-read* file-write* (subpath {q(slots)}))",
        f"(allow file-write* (subpath {q(folder)}))",
        f"(deny file-write* (subpath {q(folder / 'inputs')}))",
    ]
    for name in ("request.json", "launch.json", "inputs.json", "sandbox.sb"):
        lines.append(f"(deny file-write* (literal {q(folder / name)}))")
    return "\n".join(lines) + "\n"
