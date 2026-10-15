from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .io import canonical as canonical


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest(value: Any) -> str:
    return digest_bytes(canonical(value))


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_digest(root: Path) -> str:
    rows = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rows.append(
            {
                "path": str(path.relative_to(root)),
                "sha256": file_digest(path),
                "bytes": path.stat().st_size,
            }
        )
    return digest(rows)
