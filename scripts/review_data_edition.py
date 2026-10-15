"""Read-only source verification and explicit, versioned scientific split review.

This does not approve licenses, inspect confirmation outputs, run models, change
the frozen edition, or decide admission from filenames or numeric case folders.
"""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from principia_asd.catalog.splits import (
    check_chronology,
    check_units,
    latest_development_groups,
    repartition_development,
)
from principia_asd.io import contained, file_sha, read_csv, read_json, sha, write_csv, write_json
from principia_asd.runtime import now


def legacy_group(case, label):
    # Exact published migration identity, never a numeric-folder join.
    value = json.dumps([case, "group", str(label)], sort_keys=True, allow_nan=False).encode()
    return "group-" + hashlib.sha256(value).hexdigest()[:24]


def review_split(case, partitions, info, source_root):
    if case == "P100-012":
        relative = "scenarios/12_semiconductor_nist_hafnia_wafer/raw/CHIPS-6-02-25-00-set/README.txt"
        evidence = [e for e in info["source"]["evidence"] if e["source"] == relative]
        if len(evidence) != 1 or file_sha(contained(source_root, relative)) != evidence[0]["source_sha256"]:
            raise ValueError("Missing or changed registered deposition identity source")
        # Documented deposition membership: original README lines 44-50.
        units = {legacy_group(case, f"wafer-{i:02}"): f"deposition-{(i - 1) // 3 + 1}"
                 for i in range(1, 13)}
        before = check_units(partitions, units)
        candidate = repartition_development(partitions, {g for g, u in units.items() if u == "deposition-3"})
        after = check_units(candidate, units)
        return {
            "review_id": "deposition-batch-separation-v1",
            "source_evidence": {"path": relative, "sha256": evidence[0]["source_sha256"],
                                "scope": "README deposition membership, lines 44-50; aggregation remains wafer-level"},
            "finding": "Two deposition batches cross train/dev despite the contract declaring deposition batch as the split unit",
            "original": before, "candidate": after,
            "candidate_policy": "Deposition 1 and 2 train; deposition 3 dev; original deposition 4 test unchanged",
        }, candidate
    if case == "P100-062":
        args = {"time_column": "t", "stream_columns": ("high", "drive")}
        before = check_chronology(partitions, **args)
        groups = latest_development_groups(partitions, **args)
        candidate = repartition_development(partitions, groups)
        after = check_chronology(candidate, **args)
        return {
            "review_id": "per-stream-forward-block-separation-v1",
            "source_evidence": {"scope": "Declared forward timing contract; permitted time and drive columns only; no test outputs"},
            "finding": "The low-current stream contains training observations later than its development block",
            "original": before, "candidate": after,
            "candidate_policy": "Last complete pre-test block of each current stream is dev; earlier blocks train; original test unchanged",
        }, candidate
    return {"review_status": "not_assessed", "reason": "No source-specific split-semantic check registered yet"}, None


def save_candidate(destination, case, original, candidate, review, bindings, input_hashes):
    if not review["candidate"]["valid"]:
        raise ValueError("Candidate failed explicit split checks")
    original_development = sorted(original["train"] + original["dev"], key=lambda r: r["sample_id"])
    candidate_development = sorted(candidate["train"] + candidate["dev"], key=lambda r: r["sample_id"])
    if original_development != candidate_development or original["test"] != candidate["test"]:
        raise ValueError("Candidate changed observations, target values, or test inputs")
    manifest = {
        "status": "draft_not_admitted", "scenario_id": case, "bindings": bindings,
        "policy": review["candidate_policy"], "checks": review["candidate"],
        "source_input_hashes": input_hashes,
        "development_observations_sha256": sha(original_development),
        "test_inputs_sha256": input_hashes["test"],
        "test_outputs_accessed": False, "api_calls": 0,
        "scope": "Proposed train/dev correction only; not a complete scenario or approved edition; requires new frozen comparison",
    }
    target = destination / case
    if target.exists():
        existing = read_json(target / "candidate.json")
        for name, digest in existing["files"].items():
            if file_sha(contained(target, name)) != digest:
                raise ValueError("Existing candidate mutated")
        if {k: v for k, v in existing.items() if k != "files"} != manifest:
            raise ValueError("Existing candidate has different bindings")
        return existing
    target.mkdir(parents=True)
    for split in ("train", "dev"):
        rows = candidate[split]
        write_csv(target / f"{split}.csv.gz", rows, list(rows[0]))
    manifest["files"] = {f.name: file_sha(f) for f in sorted(target.glob("*.csv.gz"))}
    write_json(target / "candidate.json", manifest, immutable=True)
    return manifest


def review_edition(data_root, source_root, candidate_root=None):
    data_root, source_root = Path(data_root).resolve(), Path(source_root).resolve()
    if candidate_root:
        candidate_root = Path(candidate_root).resolve()
        if any(candidate_root.is_relative_to(root) for root in (data_root, source_root)):
            raise ValueError("Candidate artifacts must stay outside frozen data/source roots")
    edition_path = data_root / "EDITION.json"
    edition = read_json(edition_path)
    ids = [item["scenario_id"] for item in edition["active_scenarios"]]
    if len(ids) != len(set(ids)) or len(ids) != edition["active_scenario_count"]:
        raise ValueError("Invalid edition denominator")
    results, source_count, source_bytes = [], 0, 0
    for case in ids:
        folder = contained(data_root, f"scenarios/{case}")
        info, task = read_json(folder / "scenario.json"), read_json(folder / "task-contracts/task-001.json")
        if info["scenario_id"] != case or task["scenario_id"] != case or info["source"]["historical_case"] != case:
            raise ValueError("Registry-aligned identity mismatch")
        bindings = {"edition_sha256": file_sha(edition_path), "scenario_sha256": file_sha(folder / "scenario.json"),
                    "contract_sha256": file_sha(folder / "task-contracts/task-001.json")}
        evidence = []
        for e in info["source"]["evidence"]:
            path = contained(source_root, e["source"])
            exists = path.is_file()
            observed = file_sha(path) if exists else None
            size = path.stat().st_size if exists else 0
            source_count += 1
            source_bytes += size
            evidence.append({"source": e["source"], "expected_sha256": e["source_sha256"],
                             "observed_sha256": observed, "bytes": size,
                             "hash_matches": observed == e["source_sha256"],
                             "claimed_license": e["license"], "rights_url": e.get("rights_url")})
        parts = {s: read_csv(contained(folder, task["split"][s])) for s in ("train", "dev", "test")}
        input_hashes = {s: file_sha(contained(folder, task["split"][s])) for s in parts}
        semantic, candidate = review_split(case, parts, info, source_root)
        if candidate is not None and candidate_root:
            save_candidate(candidate_root, case, parts, candidate, semantic, bindings, input_hashes)
        results.append({"scenario_id": case, "title": info["title"], "bindings": bindings,
                        "source_input_hashes": input_hashes,
                        "source_hashes_verified": bool(evidence) and all(e["hash_matches"] for e in evidence),
                        "claimed_license": info["source"]["license"], "source_evidence": evidence,
                        "redistribution_approval": "pending", "scientific_admission": "pending",
                        "split_semantics": semantic,
                        "reconstruction": {"scenario_local_executable": any((folder / "preprocessing").glob("*.py")),
                                           "current_route": "Project curate_v2.py depends on private inherited preparation artifacts"}})
    defects = [r["scenario_id"] for r in results if "original" in r["split_semantics"]
               and not r["split_semantics"]["original"]["valid"]]
    return {"checked_at": now(), "edition_sha256": file_sha(edition_path),
            "registered_scenarios": len(ids), "source_files": source_count, "source_bytes": source_bytes,
            "source_verified_scenarios": sum(r["source_hashes_verified"] for r in results),
            "split_preparation_defects": defects,
            "split_semantics_not_assessed": sum(r["split_semantics"].get("review_status") == "not_assessed" for r in results),
            "license_claim_counts": dict(Counter(r["claimed_license"] for r in results)),
            "scenario_local_reconstruction_scripts": sum(r["reconstruction"]["scenario_local_executable"] for r in results),
            "publication_authorized": False, "test_outputs_accessed": False, "api_calls": 0,
            "scope": "Registered source identities and bytes; two explicit split-semantic reviews. Hash matches do not establish rights or scientific admission. No scores changed or attempts excluded.",
            "scenarios": results}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data-root", type=Path, required=True)
    p.add_argument("--source-root", type=Path, required=True)
    p.add_argument("--candidate-root", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result = review_edition(args.data_root, args.source_root, args.candidate_root)
    if any(args.output.resolve().is_relative_to(root.resolve()) for root in (args.data_root, args.source_root)):
        raise ValueError("Review output must stay outside frozen data/source roots")
    write_json(args.output, result)
    print(json.dumps({k: v for k, v in result.items() if k != "scenarios"}, indent=2))
