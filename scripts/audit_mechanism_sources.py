"""Supplement frozen local packages with checked source evidence, without rewriting them."""

import argparse
from pathlib import Path

from principia_asd.catalog.audit import audit_root
from principia_asd.io import file_sha, read_json, sha, write_json


def audit(data, raw, output):
    registry_file = raw / "_benchmark_100/CATALOG.json"
    registry = {r["case_id"]: r for r in read_json(registry_file)}
    packaging = audit_root(data)
    reviewed = []
    for folder in sorted((data / "scenarios").iterdir()):
        sid = folder.name
        meta = registry[sid]
        native = raw / meta["local_folder"]
        preparation = read_json(folder / "provenance/preparation.json")
        assert preparation["registry_entry_sha256"] == sha(meta)
        sources = []
        for asset in preparation["sources"]:
            root = raw if asset["path"].startswith("_benchmark_100/") else native
            path = root / asset["path"]
            assert path.resolve().is_relative_to(raw.resolve())
            assert file_sha(path) == asset["sha256"]
            sources.append({"source": str(path.relative_to(raw)), "sha256": asset["sha256"]})
        evidence = []
        for path in sorted((native / "context").glob("*.json")):
            record = read_json(path)
            terms = (
                record.get("license")
                or record.get("metadata", {}).get("license")
                or record.get("data", {}).get("latestVersion", {}).get("license")
            )
            if terms:
                evidence.append(
                    {"source": str(path.relative_to(raw)), "sha256": file_sha(path), "terms": terms}
                )
        license_file = native / "raw/LICENSE"
        if license_file.is_file():
            text = license_file.read_text()
            assert "MIT License" in text
            evidence.append(
                {
                    "source": str(license_file.relative_to(raw)),
                    "sha256": file_sha(license_file),
                    "terms": "MIT",
                    "notice": text,
                }
            )
        assert evidence, sid + " has no checked local rights record"
        reviewed.append(
            {
                "scenario_id": sid,
                "scenario_sha256": file_sha(folder / "scenario.json"),
                "contract_sha256": file_sha(folder / "task-contracts/task-001.json"),
                "native_sources": sources,
                "rights_evidence": evidence,
                "claimed_license": meta["license_or_terms"],
                "source_url": meta["source_url"],
                "scientific_admission": "local_research_preview",
                "redistribution_approval": "pending",
            }
        )
    technical = all(
        not (set(r["errors"]) - {"Missing source rights evidence"}) for r in packaging["scenarios"]
    )
    receipt = {
        "data_edition_sha256": file_sha(data / "EDITION.json"),
        "registry_sha256": file_sha(registry_file),
        "technical_packaging_checks_pass": technical,
        "source_bytes_and_rights_records_verified": len(reviewed) == 8,
        "legacy_audit": packaging,
        "metadata_limitation": "The frozen scenario source objects omit the legacy evidence array. This separate receipt binds checked source records to every scenario hash; it does not rewrite experimental inputs or grant publication permission.",
        "scenarios": reviewed,
        "publication_authorized": False,
        "scope": "Exact local source identity, license metadata, sample and group separation, size and hashes. Not an independent scientific or legal certification.",
    }
    write_json(output, receipt)
    assert technical
    print(
        {
            "scenarios": len(reviewed),
            "technical_checks": technical,
            "source_records": True,
            "publication": "pending",
        }
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for key in ["data", "raw", "output"]:
        parser.add_argument("--" + key, type=Path, required=True)
    a = parser.parse_args()
    audit(a.data, a.raw, a.output)
