"""Assemble separate public code/data and operator-only evaluator deliveries.

The targets directory is selected by the frozen data registry, never by a broad
copy of private workspace contents. No environment, key or historical job is copied.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import zipfile
from pathlib import Path

from principia_asd import __version__
from principia_asd.io import file_sha, read_json, write_json
from principia_asd.web.public_site import build_site

EXCLUDED = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".DS_Store",
    "__MACOSX",
    "build",
    ".credentials",
    ".secrets",
    "private-workspace",
    "private-evaluator",
    "local-workspace",
}
PROJECT_DIRS = {
    "src",
    "tests",
    "configs",
    "docs",
    "scripts",
    "deploy",
    "examples",
    "third-party-notices",
}
PROJECT_FILES = {
    "pyproject.toml",
    "README.md",
    "LICENSE",
    "PROVENANCE.md",
    ".gitignore",
    "REPRODUCIBILITY.md",
}
VERIFY = '''"""Verify this unpacked public release without installing dependencies."""
import hashlib
import json
from pathlib import Path
root = Path(__file__).resolve().parent
manifest = json.loads((root / "BUNDLE_MANIFEST.json").read_text())
errors=[]
for item in manifest["files"]:
    path=root/item["path"]
    if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
        errors.append(item["path"]+": missing or unsafe");continue
    raw=path.read_bytes()
    if len(raw)!=item["bytes"] or hashlib.sha256(raw).hexdigest()!=item["sha256"]:
        errors.append(item["path"]+": checksum mismatch")
print(json.dumps({"status":"failed" if errors else "passed","files":len(manifest["files"]),"errors":errors},indent=2))
raise SystemExit(bool(errors))
'''


def copy_clean(source, destination):
    for f in sorted(source.rglob("*")):
        rel = f.relative_to(source)
        if any(s in EXCLUDED or s.endswith(".egg-info") for s in rel.parts):
            continue
        if f.is_symlink():
            raise ValueError("Symlink in public source: " + str(rel))
        if not f.is_file():
            continue
        if f.name.startswith("test_targets") or f.suffix in {".env", ".sqlite", ".log", ".pyc"}:
            raise ValueError("Private/mutable public payload: " + str(rel))
        raw = f.read_bytes()
        if re.search(rb"sk-[A-Za-z0-9]{24,}", raw):
            raise ValueError("Potential secret in public source: " + str(rel))
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)


def entries(root):
    return [
        {"path": str(f.relative_to(root)), "bytes": f.stat().st_size, "sha256": file_sha(f)}
        for f in sorted(root.rglob("*"))
        if f.is_file()
    ]


def build(project, data, boards, vault, output, wheel):
    if output.exists():
        raise FileExistsError("Choose a new immutable delivery directory")
    public = output / "public-release"
    public.mkdir(parents=True)
    for name in PROJECT_DIRS:
        if (project / name).is_dir():
            copy_clean(project / name, public / name)
    for name in PROJECT_FILES:
        shutil.copyfile(project / name, public / name)
    # These are historical operator entry points, not portable public commands.
    for name in ("start_local.py", "status.py", "build_acceptance_bundle.py"):
        (public / "scripts" / name).unlink(missing_ok=True)
    copy_clean(data, public / "data")
    copy_clean(boards, public / "leaderboards")
    (public / "dist").mkdir()
    shutil.copyfile(wheel, public / "dist" / wheel.name)
    (public / "VERIFY.py").write_text(VERIFY)
    (public / ".gitignore").write_text(
        (public / ".gitignore").read_text()
        + "\n*.env\n.credentials/\nprivate-workspace/\n!configs/runtime-constraints.txt\n"
    )
    # Fix documentation navigation in the portable projection only. Canonical data/results are byte-preserved.
    for f in [*public.glob("*.md"), *(public / "docs").rglob("*.md")]:
        text = f.read_text()
        if f.parent == public:
            text = text.replace(
                "../../leaderboards/Scenarios-rules-26Oct10/", "leaderboards/"
            ).replace("../../datas/ASD-Scenarios-26Oct10/", "data/")
        else:
            depth = len(f.parent.relative_to(public).parts)
            text = text.replace(
                "../../../leaderboards/Scenarios-rules-26Oct10/", "../" * depth + "leaderboards/"
            ).replace("../../../datas/ASD-Scenarios-26Oct10/", "../" * depth + "data/")
        f.write_text(text)
    authorization = {
        "schema_version": "principia-asd.deployment-authorization/1",
        "date": "2026-10-15",
        "software_version": __version__,
        "destination": "https://atlas.chipflow.net/web/asd-test/",
        "scope": "owner-requested public research preview and private operator evaluator",
        "source": "Explicit user request in this chat on 2026-10-15",
        "third_party_rights_certified": False,
        "scientific_admission_certified": False,
        "frozen_publication_flags_modified": False,
        "personal_runs_hosted": False,
    }
    write_json(public / "DEPLOYMENT_AUTHORIZATION.json", authorization)
    write_json(output / "DEPLOYMENT_AUTHORIZATION.json", authorization)
    payload = entries(public)
    manifest = {
        "delivery": "principia-asd-" + __version__,
        "version": __version__,
        "private_targets_included": False,
        "runtime_or_credentials_included": False,
        "public_release_allowed": True,
        "release_scope": "owner-authorized research preview; source-rights and scientific review pending",
        "expanded_bytes": sum(f["bytes"] for f in payload),
        "files": payload,
    }
    write_json(public / "BUNDLE_MANIFEST.json", manifest, immutable=True)
    (public / "SHA256SUMS").write_text(
        "".join(f"{f['sha256']}  {f['path']}\n" for f in entries(public))
    )
    archive = output / "principia-asd-public-release.zip"
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in sorted(public.rglob("*")):
            if f.is_file():
                info = zipfile.ZipInfo(
                    "public-release/" + str(f.relative_to(public)),
                    date_time=(2026, 10, 15, 0, 0, 0),
                )
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                z.writestr(info, f.read_bytes())
    archive.with_suffix(".zip.sha256").write_text(file_sha(archive) + "  " + archive.name + "\n")
    private = output / "private-evaluator"
    private.mkdir(mode=0o700)
    for item in read_json(data / "EDITION.json")["active_scenarios"]:
        sid = item["scenario_id"] if isinstance(item, dict) else item
        if not re.fullmatch(r"P100-\d{3}", sid):
            raise ValueError("Unsafe registry entry")
        for name in ("test_targets.csv.gz", "evaluator-manifest.json"):
            source = vault / sid / name
            dest = private / "targets" / sid / name
            dest.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            shutil.copyfile(source, dest)
            dest.chmod(0o600)
    (private / "README.md").write_text("""# Operator-only evaluator custody

This directory contains the protected targets for the 40 registered examples. It is a sibling of public-release and public-site, never a descendant of either. Do not upload it to GitHub, attach it to the companion ZIP, or serve it over HTTP. No user imports, API keys, logs, paid-request receipts or mutable jobs are included.

The evaluator implementation is the same versioned `principia_asd.evaluate` package in public-release. Install its wheel in a separate server environment. Administrative CLI evaluation uses private settings with `vault` pointing to this directory's `targets/`; set `workspace` to a separate private output directory and `data_root` to public-release/data. Run `principia-asd evaluate --help` for the frozen-run interface. No HTTP evaluator endpoint is provided. A missing or mismatched freeze/contract must fail, never be repaired by changing canonical files.

New visitor runs remain on their computers; the server does not collect them for evaluation. Existing historical receipts remain unchanged. Exact historical replay additionally requires the original frozen runtime and private run artifacts, which are deliberately not copied into this lean deployment. These protected retrospective outcomes do not become independent evidence by being hosted privately.

On the server, the directory is owned by ubuntu with directory mode 0700 and file mode 0600. The nginx account must not be able to read it. Use SSH for operator access; do not add a public API or route to the vault. Back up target content with the same custody restrictions.
""")
    write_json(
        private / "PRIVATE_MANIFEST.json",
        {
            "software_version": __version__,
            "data_edition_sha256": file_sha(data / "EDITION.json"),
            "scenario_count": 40,
            "files": entries(private),
        },
        immutable=True,
    )
    for f in private.rglob("*"):
        f.chmod(0o700 if f.is_dir() else 0o600)
    receipt = build_site(
        data,
        boards,
        output / "public-site",
        preview=True,
        companion_bundle=archive,
        base_path="/web/asd-test/",
    )
    write_json(
        output / "ASSEMBLY.json",
        {
            "software_version": __version__,
            "public_archive_sha256": file_sha(archive),
            "public_files": len(payload),
            "private_scenarios": 40,
            "static_site": receipt,
        },
        immutable=True,
    )
    return {
        "output": str(output),
        "public_archive_bytes": archive.stat().st_size,
        "public_files": len(payload),
        "scenarios": receipt["scenario_count"],
        "rules": receipt["rule_count"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("project", "data", "boards", "vault", "output", "wheel"):
        parser.add_argument("--" + name, type=Path, required=True)
    a = parser.parse_args()
    print(json.dumps(build(**vars(a)), indent=2))
