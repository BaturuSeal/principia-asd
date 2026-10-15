"""Content-addressed copies of source only, kept outside upload directories."""

import fcntl
import shutil
from pathlib import Path

from ..io import file_sha, read_json, sha, write_json


def runtime_snapshot(workspace):
    source = Path(__file__).resolve().parents[1]
    hashes = {str(p.relative_to(source)): file_sha(p) for p in sorted(source.rglob("*.py"))}
    digest = sha(hashes)
    root = Path(workspace) / "runtime-revisions" / digest
    target = root / "src/principia_asd"
    target.mkdir(parents=True, exist_ok=True)
    with (root / "snapshot.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for relative, checksum in hashes.items():
            dest = target / relative
            if dest.exists():
                if file_sha(dest) != checksum:
                    raise ValueError("Runtime snapshot mutation")
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / relative, dest)
        expected = {"sha256": digest, "files": hashes}
        binding = root / "binding.json"
        if binding.exists():
            if read_json(binding) != expected:
                raise ValueError("Runtime binding mutation")
        else:
            write_json(binding, expected, immutable=True)
    return root / "src"
