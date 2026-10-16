"""Portable, hash-bound public collections; no private workspace is read."""

import re
from pathlib import Path

from ..io import contained, file_sha, read_json


def scenario_ids(root):
    edition = read_json(Path(root) / "EDITION.json")
    entries = edition.get("active_scenarios", edition.get("scenarios", []))
    ids = [entry["scenario_id"] if isinstance(entry, dict) else entry for entry in entries]
    if (
        not ids
        or len(ids) != len(set(ids))
        or any(not isinstance(sid, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", sid) for sid in ids)
    ):
        raise ValueError("Collection must declare unique, safe scenario identities")
    return ids


def bundle_packs(manifest_path, workspace=None):
    """Resolve only declared relative public paths and verify their edition hashes."""
    path = Path(manifest_path)
    if not path.is_file():
        raise ValueError("Public collection manifest is missing")
    packs = []
    ids = set()
    for item in read_json(path).get("collections", []):
        ident = item["id"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", ident) or ident in ids:
            raise ValueError("Collection IDs must be safe and unique")
        ids.add(ident)
        pack = {"id": ident}
        for field in ("data_root", "leaderboard_root"):
            relative = item[field]
            if not isinstance(relative, str) or Path(relative).is_absolute():
                raise ValueError("Collection paths must be relative to the public bundle")
            root = contained(path.parent, relative)
            if not root.is_dir() or any(p.is_symlink() for p in root.rglob("*")):
                raise ValueError("Collection root is missing or contains symbolic links")
            if file_sha(root / "EDITION.json") != item[field + "_sha256"]:
                raise ValueError("Collection edition hash changed")
            pack[field] = str(root)
        # Public bundles cannot select a private evaluator or inherit the owner's vault.
        if workspace is not None:
            pack["vault"] = str(Path(workspace) / "private-evaluator" / "collections" / ident)
        packs.append(pack)
    return packs
