"""Build a read-only website from public editions, never from an application workspace."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path

from .. import __version__
from ..catalog.presentation import describe_scenario, describe_task
from ..catalog.reviews import known_advisories, task_advisories
from ..io import file_sha, read_json, sha, write_json
from ..methods.registry import METHODS
from .collections import bundle_packs, scenario_ids
from .rule_view import rule_view
from .tasks import task_entries


def safe_public(value):
    """Keep scientific numbers intact; remove machine paths and private settings."""
    if isinstance(value, dict):
        return {
            k: safe_public(v)
            for k, v in value.items()
            if k
            not in {
                "env_file",
                "workspace",
                "vault",
                "api_key",
                "csrf",
                "runtime_source",
                "local_path",
            }
        }
    if isinstance(value, list):
        return [safe_public(v) for v in value]
    if isinstance(value, str):
        if re.search(r"sk-[A-Za-z0-9]{24,}", value):
            raise ValueError("Possible credential in public input")
        return re.sub(
            r"(?:/Users/|/home/|/private/|/tmp/)[^\s\"'<>;,]*", "[local path omitted]", value
        )
    return value


def verify_companion(path, *, preview):
    """Only attach a checksum-verified acceptance archive, never an arbitrary ZIP."""
    path = Path(path)
    if path.suffix != ".zip" or not path.is_file() or path.is_symlink():
        raise ValueError("Companion download must be a verified local ZIP archive")
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        manifests = [n for n in names if n.count("/") == 1 and n.endswith("/BUNDLE_MANIFEST.json")]
        if len(manifests) != 1 or len(set(names)) != len(names):
            raise ValueError("Companion archive needs one unambiguous bundle manifest")
        if sum(f.file_size for f in archive.infolist()) > 200_000_000:
            raise ValueError("Companion archive exceeds the expanded delivery limit")
        manifest = json.loads(archive.read(manifests[0]))
        if (
            manifest.get("private_targets_included") is not False
            or manifest.get("runtime_or_credentials_included") is not False
        ):
            raise ValueError("Companion archive is not cleared of private state")
        if not preview and manifest.get("public_release_allowed") is not True:
            raise ValueError("Companion archive is not authorized for publication")
        prefix = manifests[0].split("/")[0] + "/"
        entries = {e["path"]: e for e in manifest["files"]}
        expected = {prefix + n for n in entries} | {manifests[0], prefix + "SHA256SUMS"}
        if set(names) != expected:
            raise ValueError("Unmanifested companion archive entries")
        for name, entry in entries.items():
            rel = Path(name)
            if (
                rel.is_absolute()
                or ".." in rel.parts
                or any(
                    p
                    in {
                        ".credentials",
                        ".secrets",
                        "private-evaluator",
                        "private-workspace",
                        ".venv",
                        "__pycache__",
                    }
                    for p in rel.parts
                )
                or rel.name.startswith("test_targets")
                or rel.suffix in {".env", ".sqlite", ".log", ".pyc"}
            ):
                raise ValueError("Private or unsafe companion archive entry")
            info = archive.getinfo(prefix + name)
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Companion archive cannot contain symbolic links")
            raw = archive.read(info)
            if len(raw) != entry["bytes"] or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
                raise ValueError("Companion archive checksum mismatch")
    return path


def build_site(
    data_root,
    leaderboard_root,
    output,
    *,
    preview=False,
    companion_bundle=None,
    base_path="/",
    collections_manifest=None,
):
    if not re.fullmatch(r"/(?:[A-Za-z0-9_-]+/)*", base_path):
        raise ValueError("Base path must contain safe path segments and end in a slash")
    data_root, leaderboard_root, output = map(
        lambda p: Path(p).resolve(), (data_root, leaderboard_root, output)
    )
    if output.exists():
        raise ValueError("Use a new empty output path; existing site builds are immutable")
    packs = bundle_packs(collections_manifest) if collections_manifest else []
    roots = [("primary", data_root, leaderboard_root)] + [
        (pack["id"], Path(pack["data_root"]), Path(pack["leaderboard_root"])) for pack in packs
    ]
    for root in [r for _, data, boards in roots for r in (data, boards)]:
        if output.is_relative_to(root) or root.is_relative_to(output):
            raise ValueError("Site output must be separate from source editions")
        if any(p.is_symlink() for p in root.rglob("*")):
            raise ValueError("Public input editions must not contain symbolic links")
    scenarios = []
    tasks = {}
    bindings = {
        "data_edition_sha256": file_sha(data_root / "EDITION.json"),
        "leaderboard_edition_sha256": file_sha(leaderboard_root / "EDITION.json"),
        "contracts": {},
        "boards": {},
        "collections": {
            ident: {
                "data_edition_sha256": file_sha(data / "EDITION.json"),
                "leaderboard_edition_sha256": file_sha(boards / "EDITION.json"),
            }
            for ident, data, boards in roots
        },
    }
    paths = {}
    for _ident, data, _ in roots:
        for sid in scenario_ids(data):
            path = data / "scenarios" / sid
            info = read_json(path / "scenario.json")
            if sid in paths:
                if info.get("extends_scenario_sha256") != file_sha(paths[sid] / "scenario.json"):
                    raise ValueError("Scenario collection identity collision: " + sid)
            else:
                paths[sid] = path
    for sid, path in sorted(paths.items()):
        info = read_json(path / "scenario.json")
        if info["scenario_id"] != sid:
            raise ValueError("Scenario registry identity mismatch")
        entries = []
        for task_path, f in task_entries(path, None, packs=packs):
            task = describe_task(read_json(f))
            if collections_manifest:
                task["package_path"] = str(
                    task_path.relative_to(Path(collections_manifest).resolve().parent)
                )
            tasks[sid, task["task_id"]] = task
            entries.append(task)
            bindings["contracts"][sid + "/" + task["task_id"]] = file_sha(f)
        if not entries:
            raise ValueError("Scenario has no task contracts: " + sid)
        scenarios.append(
            safe_public(
                {
                    "scenario_id": sid,
                    **describe_scenario(info, entries[0]),
                    "tasks": entries,
                    "task": entries[0],
                    "domain": info.get("domain", "Scientific measurements"),
                    "rows": info.get("rows", {}),
                    "size": info.get("size", {}),
                    "limitations": info.get("limitations", []),
                    "source": info.get("source", {}),
                    "publication_authorized": info.get("publication_authorized", False),
                    "review_advisories": task_advisories(entries[0]),
                    "package_path": str(
                        path.relative_to(Path(collections_manifest).resolve().parent)
                    )
                    if collections_manifest
                    else "data/scenarios/" + sid,
                }
            )
        )
    authorized = all(
        read_json(data / "EDITION.json").get("publication_authorized") is True
        for _, data, _ in roots
    ) and all(s["publication_authorized"] is True for s in scenarios)
    if not preview and not authorized:
        raise ValueError(
            "Data redistribution is not authorized in this edition. Use --preview for local acceptance; clear source rights before public hosting."
        )
    boards = []
    board_paths = [
        (ident, root, p)
        for ident, _, root in roots
        for p in sorted((root / "scenarios").glob("*/tasks/*/leaderboard.json"))
    ]
    seen_boards = set()
    for ident, board_root, p in board_paths:
        board = read_json(p)
        key = board["scenario_id"], board["task_id"]
        if key not in tasks:
            raise ValueError("Leaderboard has no registered public task")
        if key in seen_boards:
            raise ValueError("Duplicate task leaderboard across collections")
        seen_boards.add(key)
        board["rule_presentations"] = {
            r["rule_id"]: rule_view(r.get("card", r), tasks[key]) for r in board["rules"]
        }
        boards.append(safe_public(board))
        bindings["boards"][ident + "/" + str(p.relative_to(board_root))] = file_sha(p)
    archive = verify_companion(companion_bundle, preview=preview) if companion_bundle else None
    output.mkdir(parents=True)
    assets = Path(__file__).parent
    for name in ("app.js", "explorer.js", "style.css", "explorer.css", "vendor/katex.min.js", "vendor/KATEX-LICENSE.txt"):
        (output / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(assets / name, output / name)
    html = (
        (assets / "index.html")
        .read_text()
        .replace(
            '<html lang="en">',
            f'<html lang="en" data-deployment="public" data-base-path="{base_path}">',
        )

    )
    html = html.replace('src="/', f'src="{base_path}').replace('href="/', f'href="{base_path}')
    (output / "index.html").write_text(html)
    download = None
    if archive:
        (output / "downloads").mkdir()
        shutil.copyfile(archive, output / "downloads/principia-asd.zip")
        download = {
            "url": "/downloads/principia-asd.zip",
            "sha256": file_sha(archive),
            "bytes": archive.stat().st_size,
        }
    config = {
        "version": __version__,
        "deployment": "public",
        "methods": [m.as_dict() for m in METHODS.values()],
        "data_preparation_advisories": known_advisories(),
        "companion_download": download,
        "publication_authorized": authorized,
        "preview": preview,
    }
    # Load only the chosen task's rules in the browser; the catalog stays small.
    board_index = []
    for board in boards:
        name = sha([board["scenario_id"], board["task_id"]]) + ".json"
        write_json(output / "data/tasks" / name, board)
        board_index.append(
            {
                "scenario_id": board["scenario_id"],
                "task_id": board["task_id"],
                "rule_count": len(board["rules"]),
                "data_url": "/data/tasks/" + name,
            }
        )
    for name, data in (("config", config), ("scenarios", scenarios), ("leaderboards", board_index)):
        write_json(output / "data" / (name + ".json"), data)
    receipt = {
        "schema_version": "principia-asd.static-site/1",
        "version": __version__,
        "profile": "read-only-public-catalog",
        "base_path": base_path,
        "publication_authorized": authorized,
        "preview_only": preview,
        "scenario_count": len(scenarios),
        "task_count": len(tasks),
        "rule_count": sum(len(b["rules"]) for b in boards),
        "attempt_count": sum(len(b.get("attempts", [])) for b in boards),
        "private_workspace_accessed": False,
        "provider_calls": 0,
        "bindings": bindings,
        "files": {
            str(f.relative_to(output)): file_sha(f)
            for f in sorted(output.rglob("*"))
            if f.is_file()
        },
    }
    write_json(output / "site-manifest.json", receipt, immutable=True)
    return receipt
