"""Small deterministic records shared by discovery, evaluation and the local UI."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import uuid
from pathlib import Path
from typing import Any


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).encode()


def sha(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def write_json(path: Path, value: Any, *, immutable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("x") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if immutable:
            os.link(temp, path)
        else:
            temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def read_csv(path: Path, *, max_bytes: int = 30_000_000) -> list[dict]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as f:
        raw = f.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("Expanded CSV exceeds the allowed size")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise ValueError("CSV header is missing or duplicated")
    rows = []
    for item in reader:
        if None in item or any(v is None for v in item.values()):
            raise ValueError("Malformed CSV row")
        row = {}
        for k, v in item.items():
            if k in {"sample_id", "group"}:
                row[k] = v
            else:
                try:
                    row[k] = float(v)
                except (ValueError, TypeError):
                    row[k] = v
        rows.append(row)
    return rows


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    raw = stream.getvalue().encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(raw, mtime=0) if path.suffix == ".gz" else raw)


def contained(root: Path, relative: str) -> Path:
    result = (root / relative).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError("Path leaves the allowed directory")
    return result
