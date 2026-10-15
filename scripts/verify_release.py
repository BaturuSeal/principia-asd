"""Verify engineering artifacts without conflating them with scientific release approval."""

import argparse
import re
from pathlib import Path

from principia_asd.catalog.audit import audit_root, expanded_size
from principia_asd.catalog.reviews import task_advisories
from principia_asd.io import file_sha, read_json, sha, write_json
from principia_asd.runtime import now
from principia_asd.store.ledger import CostLedger


def verify(settings):
    project = Path(__file__).resolve().parents[1]
    data = Path(settings["data_root"])
    boards = Path(settings["leaderboard_root"])
    vault = Path(settings["vault"])
    errors = []
    audit = audit_root(data)
    if not audit["valid"]:
        errors.append("Scenario packaging/separation audit failed")
    expanded = []
    preparation_advisories = []
    for row in audit["scenarios"]:
        sid = row["scenario_id"]
        preparation_advisories.extend(task_advisories(read_json(data / "scenarios" / sid / "task-contracts/task-001.json")))
        private = vault / sid / "test_targets.csv.gz"
        size = row.get("expanded_public_bytes", 0) + (
            expanded_size(private) if private.exists() else 0
        )
        if size > 10_000_000:
            errors.append(sid + " exceeds expanded size cap including targets")
        expanded.append({"scenario_id": sid, "expanded_bytes_including_targets": size})
    files = []
    generated_receipts = {
        project / "docs/DATA_VALIDATION.json",
        project / "docs/EXPANDED_SIZES.json",
        project / "RELEASE_RECEIPT.json",
        boards / "receipts/release-verification.json",
    }
    for root in [project, data, boards]:
        for path in root.rglob("*"):
            if not path.is_file() or ".git" in path.relative_to(root).parts:
                continue
            rel = path.relative_to(root)
            parts = rel.parts
            if any(
                p
                in {
                    ".venv",
                    "__pycache__",
                    ".pytest_cache",
                    ".ruff_cache",
                    ".secrets",
                    ".credentials",
                    "private-evaluator",
                    "local-workspace",
                }
                for p in parts
            ) or path.suffix in {".pyc", ".sqlite", ".log", ".env"}:
                errors.append("Nonrelease file: " + str(rel))
            if path.name.startswith("test_targets"):
                errors.append("Protected targets in upload root: " + str(rel))
            if path.suffix in {".py", ".md", ".json", ".js", ".html", ".css", ".toml", ".txt"}:
                if re.search(r"sk-[A-Za-z0-9]{24,}", path.read_text(errors="replace")):
                    errors.append("Possible credential in " + str(rel))
            if path in generated_receipts:
                # These files are replaced below; hashing their prior contents would make
                # the receipt describe a pre-verification tree rather than the release.
                continue
            files.append(
                {
                    "root": root.name,
                    "path": str(rel),
                    "sha256": file_sha(path),
                    "bytes": path.stat().st_size,
                }
            )
    coverage = (
        read_json(boards / "exports/coverage.json")
        if (boards / "exports/coverage.json").exists()
        else {}
    )
    rows = (
        read_json(boards / "exports/all-rules.json")
        if (boards / "exports/all-rules.json").exists()
        else []
    )
    attempts = (
        read_json(boards / "exports/all-attempts.json")
        if (boards / "exports/all-attempts.json").exists()
        else []
    )
    if len(attempts) != coverage.get("assigned_attempt_denominator"):
        errors.append("Assigned denominator mismatch")
    task_paths = {}
    edition = read_json(boards / "EDITION.json") if (boards / "EDITION.json").exists() else {}
    for path in (boards / "scenarios").glob("*/tasks/*/leaderboard.json"):
        board = read_json(path)
        if board.get("campaign_id") != edition.get("campaign_id"):
            continue
        key = (board["scenario_id"], board["task_id"])
        if key in task_paths:
            errors.append("Duplicate task leaderboard: " + str(key))
        task_paths[key] = path.parent
    for row in rows:
        task_path = task_paths.get((row["scenario_id"], row["task_id"]))
        if task_path is None:
            errors.append("Missing task leaderboard: " + row["task_id"])
            continue
        rule = task_path / "rules" / row["rule_id"]
        card = read_json(rule / "rule-card.json")
        expected = card.pop("rule_sha256", None)
        if sha(card) != expected:
            errors.append("Rule hash mismatch: " + row["rule_id"])
        if (
            not (rule / "program/expression.json").exists()
            or not (rule / "evaluation-receipt.json").exists()
            or not (rule / "index.html").exists()
        ):
            errors.append("Missing reproducible artifact: " + row["rule_id"])
    versions = [
        read_json(path)["version"]
        for path in [data / "EDITION.json", boards / "EDITION.json"]
        if path.exists()
    ]
    from principia_asd import __version__

    compatibility = read_json(project / "configs/edition-compatibility.json")
    expected = [compatibility["data_version"], compatibility["leaderboard_version"]]
    if versions != expected or compatibility["software_version"] != __version__:
        errors.append("Software/data edition compatibility mismatch")
    for key, root in [("data", data), ("leaderboard", boards)]:
        if file_sha(root / "EDITION.json") != compatibility[key + "_edition_sha256"]:
            errors.append("Compatible edition hash changed: " + key)
    costs = CostLedger(Path(settings["workspace"]) / "costs.sqlite").summary()
    if costs["accounted_cny"] > 3000:
        errors.append("Global cap exceeded")
    required = [
        "exports/all-rules.json",
        "exports/all-rules.csv",
        "exports/all-attempts.json",
        "exports/coverage.json",
        "index.html",
        "assets/report.css",
    ]
    if any(not (boards / p).exists() for p in required):
        errors.append("Missing canonical export")
    wheels = list((project / "dist").glob("*.whl"))
    if len(wheels) != 1:
        errors.append("Expected one current wheel")
    receipt = {
        "version": __version__,
        "checked_at": now(),
        "engineering_status": "passed" if not errors else "failed",
        "errors": errors,
        "scenario_count": audit["scenario_count"],
        "preparation_advisories": preparation_advisories,
        "leaderboard_coverage": coverage,
        "costs": costs,
        "wheel": {"name": wheels[0].name, "sha256": file_sha(wheels[0])}
        if len(wheels) == 1
        else None,
        "files_sha256": sha(sorted(files, key=lambda item: (item["root"], item["path"]))),
        "files_sha256_excludes_generated_receipts": sorted(
            str(path.relative_to(project if path.is_relative_to(project) else boards))
            for path in generated_receipts
        ),
        "public_release_allowed": False,
        "release_ready": False,
        "open_gates": [
            "Source-rights and scientific contract approval",
            "Source-specific split review and new versioned corrections for known preparation defects",
            "Portable source-bound raw-data reconstruction",
            "Learned-state lineage and complete rule-complexity accounting",
            "Complete required adapter conformance",
            "Remaining adapter pilot and frozen comparison coverage",
            "Strong-model scientific review",
        ],
        "expansion_track": "Continue toward 100 quality-admitted scenarios without an exact-count gate for the first edition",
        "scientific_review": "not_assessed",
        "checks_scope": "Packaging, source/target separation, content hashes, artifact links, denominator, cost cap and version consistency; not scientific validity or independent novelty",
    }
    write_json(project / "docs/DATA_VALIDATION.json", audit)
    write_json(project / "docs/EXPANDED_SIZES.json", expanded)
    write_json(project / "RELEASE_RECEIPT.json", receipt)
    write_json(boards / "receipts/release-verification.json", receipt)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", type=Path, required=True)
    a = parser.parse_args()
    result = verify(read_json(a.settings))
    print(__import__("json").dumps(result, indent=2))
    if result["errors"]:
        raise SystemExit(1)
