"""Check inherited source evidence without changing scenario admission or licenses."""

import argparse
import hashlib
from pathlib import Path

from principia_asd.io import file_sha, read_json, write_json
from principia_asd.runtime import now


def audit(data_root, source_root, cases):
    source_root = source_root.resolve()
    reviewed = []
    for sid in cases:
        if not sid.startswith("P100-") or not sid[5:].isdigit():
            raise ValueError("Expected a registered historical scenario identity")
        path = data_root / "scenarios" / sid / "scenario.json"
        scenario = read_json(path)
        assert scenario["scenario_id"] == sid
        source = scenario["source"]
        rows = []
        for item in source.get("evidence", []):
            local = (source_root / item["source"]).resolve()
            if not local.is_relative_to(source_root):
                raise ValueError("Source evidence escapes the registered release projection")
            digest = file_sha(local) if local.is_file() else None
            row = {
                "source": item["source"],
                "expected_sha256": item["source_sha256"],
                "observed_sha256": digest,
                "hash_matches": digest == item["source_sha256"],
                "claimed_license": item.get("license"),
                "rights_url": item.get("rights_url"),
            }
            if digest and local.name == "LICENSE":
                raw = local.read_bytes()
                row["notice"] = {
                    "bytes": len(raw),
                    "git_blob_sha1": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest(),
                    "first_line": raw.decode("utf-8").splitlines()[0],
                }
            if digest and local.name == "source_record.json":
                record = read_json(local)
                metadata = record.get("metadata", {})
                row["repository_record"] = {
                    "id": record.get("id"),
                    "doi": record.get("doi"),
                    "license": metadata.get("license"),
                    "creators": [c.get("name") for c in metadata.get("creators", [])],
                    "files": [
                        {k: f.get(k) for k in ["key", "size", "checksum"]}
                        for f in record.get("files", [])
                    ],
                }
            rows.append(row)
        reviewed.append({
            "scenario_id": sid,
            "scenario_manifest_sha256": file_sha(path),
            "source_url": source.get("url"),
            "source_version": source.get("version"),
            "claimed_license": source.get("license"),
            "all_registered_source_hashes_match": bool(rows) and all(x["hash_matches"] for x in rows),
            "evidence": rows,
            "redistribution_approval": "pending",
        })
    return {
        "checked_at": now(),
        "status": "source_hashes_verified" if all(r["all_registered_source_hashes_match"] for r in reviewed) else "source_evidence_mismatch",
        "scope": "Local source bytes and inherited license metadata; not blanket rights approval or scientific admission",
        "data_edition_sha256": file_sha(data_root / "EDITION.json"),
        "reviewed_scenarios": reviewed,
        "scientific_contract_approval": "pending",
        "publication_authorized": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--cases", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.data_root, args.source_root, args.cases)
    write_json(args.output, result)
    print(result["status"], len(result["reviewed_scenarios"]))
    if result["status"] != "source_hashes_verified":
        raise SystemExit(1)
