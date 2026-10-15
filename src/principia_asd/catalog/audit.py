"""Inspect expanded package size, hashes and group/identity partition separation."""

import gzip
from pathlib import Path

from ..contracts.schema import validate_contract
from ..io import contained, file_sha, read_csv, read_json, write_json
from ..runtime import validate_data


def expanded_size(path, limit=10_000_000):
    if path.suffix != ".gz":
        return path.stat().st_size
    with gzip.open(path, "rb") as stream:
        return len(stream.read(limit + 1))


def audit_root(root: Path, *, max_bytes=10_000_000):
    root = Path(root)
    if (root / "scenarios").is_dir():
        root = root / "scenarios"
    results = []
    for folder in sorted(root.iterdir()):
        if not (folder / "scenario.json").is_file():
            continue
        errors = []
        try:
            info = read_json(folder / "scenario.json")
            task = read_json(folder / "task-contracts/task-001.json")
            errors.extend(validate_contract(task))
            if info["scenario_id"] != folder.name or task["scenario_id"] != folder.name:
                errors.append("Registry/scenario identity mismatch")
            files = [f for f in folder.rglob("*") if f.is_file()]
            expanded = sum(expanded_size(f, max_bytes) for f in files)
            if expanded > max_bytes:
                errors.append("Expanded public package exceeds limit")
            checks = (
                read_json(folder / "checksums.json") if (folder / "checksums.json").exists() else {}
            )
            if not checks:
                errors.append("Missing immutable file checksums")
            for name, value in checks.items():
                if file_sha(contained(folder, name)) != value:
                    errors.append("Content hash mismatch: " + name)
            partitions = {}
            for name in ["train", "dev", "test"]:
                rows = read_csv(contained(folder, task["split"][name]), max_bytes=max_bytes)
                validate_data(rows, task, targets=name != "test")
                partitions[name] = rows
            for a, b in [("train", "dev"), ("train", "test"), ("dev", "test")]:
                if {r["sample_id"] for r in partitions[a]} & {
                    r["sample_id"] for r in partitions[b]
                }:
                    errors.append(a + "/" + b + " sample leakage")
                if {r["group"] for r in partitions[a]} & {r["group"] for r in partitions[b]}:
                    errors.append(a + "/" + b + " group leakage")
            source = info.get("source", {})
            if not source.get("license") or not source.get("evidence"):
                errors.append("Missing source rights evidence")
            results.append(
                {
                    "scenario_id": folder.name,
                    "valid": not errors,
                    "errors": errors,
                    "expanded_public_bytes": expanded,
                    "rows": {k: len(v) for k, v in partitions.items()},
                    "publication_authorized": info.get("publication_authorized", False),
                }
            )
        except (ValueError, KeyError, TypeError, FileNotFoundError) as exc:
            results.append({"scenario_id": folder.name, "valid": False, "errors": [str(exc)]})
    return {
        "scenario_count": len(results),
        "valid": bool(results) and all(r["valid"] for r in results),
        "scenarios": results,
        "scope": "Packaging, hashes and separation only; source rights and scientific semantics require separate review",
    }


def write_audit(root, output):
    value = audit_root(root)
    write_json(Path(output), value)
    return value
