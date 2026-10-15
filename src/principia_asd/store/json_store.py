from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..hashing import digest, file_digest
from ..io import contained, write_json


class JsonStore:
    """Small immutable-record store used by the release and leaderboard exporters."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def write(self, relative: str, value: dict[str, Any], *, immutable: bool = True) -> Path:
        path = contained(self.root, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        if immutable and path.exists():
            old = json.loads(path.read_text())
            if old != value:
                raise FileExistsError(f"immutable record already exists: {path}")
            return path
        write_json(path, value, immutable=immutable)
        return path

    def seal(self) -> dict[str, Any]:
        rows = []
        for path in sorted(
            p for p in self.root.rglob("*") if p.is_file() and not p.name.endswith(".tmp")
        ):
            rows.append(
                {
                    "path": str(path.relative_to(self.root)),
                    "sha256": file_digest(path),
                    "bytes": path.stat().st_size,
                }
            )
        return {"files": rows, "tree_sha256": digest(rows)}
