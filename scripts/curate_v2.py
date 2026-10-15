"""Rebuild compact contracts from registered, hash-bound local measurements.

Existing editions are archived, never silently overwritten. No model calls.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import shutil
from pathlib import Path

from principia_asd.io import file_sha, read_json, sha, write_csv, write_json


def opaque(case, kind, value):
    return (
        kind
        + "-"
        + hashlib.sha256(
            json.dumps([case, kind, str(value)], sort_keys=True, allow_nan=False).encode()
        ).hexdigest()[:24]
    )


def table(path):
    with gzip.open(path, "rt") as f:
        return list(csv.DictReader(f))


def expanded_size(path):
    return len(gzip.decompress(path.read_bytes())) if path.suffix == ".gz" else path.stat().st_size


def build(base):
    old = base.parent
    prepared = old / "benchmarks/Principia-100-leaderboard/ASD-baselines/prepared-inputs"
    curator = prepared.parent / "curator"
    source = old / "local-datas/_benchmark_100"
    truth = old / "local-truths-gpt6/principia-100/tasks"
    catalog = read_json(source / "CATALOG.json")
    rights = read_json(source / "LICENSE_REGISTER.json")
    out = base / "datas/ASD-Scenarios-26Oct10"
    vault = base / "private-evaluator/ASD-Scenarios-26Oct10/edition-v2"
    edition = out / "EDITION.json"
    if edition.exists() and read_json(edition).get("edition_id") == "compact-v2":
        raise RuntimeError("Edition is immutable; use a new version to curate again")
    archive = base / "private-evaluator/ASD-Scenarios-26Oct10/audit-archive/retired-public-v1"
    if out.exists():
        archive.parent.mkdir(parents=True, exist_ok=True)
        if archive.exists():
            raise RuntimeError("Archive destination already exists")
        shutil.move(str(out), archive)
    out.mkdir(parents=True)
    vault.mkdir(parents=True, exist_ok=True)
    audits = []
    admitted = []
    for item in catalog:
        case = item["case_id"]
        packet = prepared / case
        audit = {
            "scenario_id": case,
            "title": item["title"],
            "domain": item["domain"],
            "status": "pending_review",
        }
        try:
            if case in {"P100-005", "P100-008", "P100-044", "P100-096", "P100-098"}:
                raise ValueError(
                    "Certificate/adequacy or unresolved supplement: no compatible prediction contract admitted"
                )
            part = read_json(packet / "participant.json")
            fields = part["permitted_inputs"]
            if "target" in fields or any(not f.isidentifier() or f.startswith("_") for f in fields):
                raise ValueError("Invalid permitted input names")
            for asset in read_json(packet / "manifest.json")["files"]:
                if file_sha(packet / asset["path"]) != asset["sha256"]:
                    raise ValueError("Prepared file hash mismatch")
            lic = item.get("license_or_terms", "")
            permitted = any(
                t in lic.lower()
                for t in [
                    "cc by 4.0",
                    "cc-by-4.0",
                    "cc0",
                    "public domain",
                    "public-domain",
                    "public data",
                    "public-use data",
                    "apache license",
                    "mit",
                ]
            )
            if not permitted:
                raise ValueError("Redistribution terms need source-specific review")
            rr = [x for x in rights if x.get("case_id") == case and x.get("rights_evidence_url")]
            if not rr:
                raise ValueError("No source rights evidence link in the local register")
            development = table(packet / "development.csv.gz")
            test = table(packet / "inputs.csv.gz")
            if len(development) < 40 or len(test) < 10:
                raise ValueError("Too few development or test measurements for this edition")
            if part["metric_kind"] not in {"mae", "rmse", "brier", "log_mae"}:
                raise ValueError("Task-specific metric adapter not validated yet")
            for row in development + test:
                for k in fields + (["target"] if "target" in row else []):
                    if not math.isfinite(float(row[k])):
                        raise ValueError("Nonfinite numeric measurement")
            td = truth / part["task_id"]
            obs = table(td / "data/observations.csv.gz")
            tx = table(td / "data/inputs.csv.gz")
            by_id = {opaque(case, "sample", r["sample_id"]): r for r in obs}
            x_by_id = {opaque(case, "sample", r["sample_id"]): r for r in tx}
            if len(by_id) != len(obs) or len(test) != len(by_id):
                raise ValueError("Reference identity or cohort mismatch")
            targets = []
            for row in test:
                oid = row["sample_id"]
                y = by_id.get(oid)
                x = x_by_id.get(oid)
                if not y or not x or not math.isfinite(float(y["target"])):
                    raise ValueError("Missing protected target identity")
                for f in fields:
                    if not math.isclose(float(row[f]), float(x[f]), rel_tol=1e-10, abs_tol=1e-12):
                        raise ValueError("Identity-based input reconstruction mismatch")
                if row["group"] != opaque(case, "group", y["group"]):
                    raise ValueError("Group identity mismatch")
                targets.append(
                    {"sample_id": oid, "group": row["group"], "target": float(y["target"])}
                )
            dg = {r["group"] for r in development}
            tg = {r["group"] for r in test}
            if dg & tg:
                raise ValueError(
                    "Development and confirmation groups overlap; requires task-specific chronological admission"
                )
            if len(dg) < 6:
                raise ValueError(
                    "Fewer than six development groups; retained as a diagnostic candidate"
                )
            if {r["sample_id"] for r in development} & {r["sample_id"] for r in test}:
                raise ValueError("Sample leakage")
            # Temporal group labels are available only to the curator, never inferred from opaque hashes.
            native = curator / case / "native-anchors.csv.gz"
            original_groups = (
                {opaque(case, "group", r["group"]): r["group"] for r in table(native)}
                if native.exists()
                else {}
            )
            temporal = any(
                w in part["independent_unit"].lower()
                for w in ["forward", "rolling", "month", "site-day"]
            )
            if temporal:
                if not dg <= original_groups.keys():
                    raise ValueError("Missing original groups for temporal splitting")
                import re

                def clock(g, original_groups=original_groups):
                    dates = re.findall(r"20\d{2}[-/]\d{2}(?:[-/]\d{2})?", original_groups[g])
                    if not dates:
                        raise ValueError("Unresolved temporal group order")
                    return dates[0], original_groups[g]

                ordered = sorted(dg, key=clock)
                cutoff = clock(ordered[-max(2, len(ordered) // 5)])[0]
                dev_groups = {g for g in dg if clock(g)[0] >= cutoff}
                split_policy = (
                    "latest complete development time blocks; original confirmation unchanged"
                )
            else:
                ordered = sorted(dg, key=lambda g: sha(["compact-v2", case, g]))
                dev_groups = set(ordered[: max(2, len(ordered) // 5)])
                split_policy = (
                    "deterministic whole independent-unit groups; original confirmation unchanged"
                )
            train = [r for r in development if r["group"] not in dev_groups]
            dev = [r for r in development if r["group"] in dev_groups]
            if min(len(train), len(dev)) < 10:
                raise ValueError("Insufficient train/dev coverage after grouping")
            weights = read_json(td / "task.json").get("aggregation", {})
            if part["metric_kind"] == "log_mae" and any(
                float(r["target"]) <= 0 for r in development + targets
            ):
                raise ValueError("Nonpositive target for log loss")
            payload_bytes = sum(len(json.dumps(r)) for r in train + dev + test + targets)
            if payload_bytes > 12_000_000:
                raise ValueError(
                    "Expanded compact package exceeds size budget; needs separate principled compaction"
                )
            p = out / "scenarios" / case
            cols = ["sample_id", "group", *fields]
            write_csv(p / "public/train.csv.gz", train, cols + ["target"])
            write_csv(p / "public/dev.csv.gz", dev, cols + ["target"])
            write_csv(p / "public/test_inputs.csv.gz", test, cols)
            write_csv(
                vault / case / "test_targets.csv.gz", targets, ["sample_id", "group", "target"]
            )
            evidence = [
                {
                    "source": x["path"],
                    "source_sha256": x["sha256"],
                    "license": x["license_or_terms"],
                    "rights_url": x["rights_evidence_url"],
                    "citation_url": x.get("citation_url"),
                }
                for x in rr
            ]
            contract = {
                "schema_version": "principia-asd.task-contract/2.0",
                "version": "1.0.0rc2",
                "scenario_id": case,
                "task_id": case + ".compact.v2",
                "title": part["target"],
                "inputs": fields,
                "input_units": part["input_units"],
                "output": "target",
                "output_units": part["target_units"],
                "output_description": part["target"],
                "observation_window": part["observation_window"],
                "split": {
                    "train": "public/train.csv.gz",
                    "dev": "public/dev.csv.gz",
                    "test": "public/test_inputs.csv.gz",
                    "policy": split_policy,
                    "independent_unit": part["independent_unit"],
                },
                "metric": {
                    "primary": part["metric_kind"],
                    "aggregation": "equal_group_mean",
                    "historical_aggregation": weights,
                },
                "positive_prediction": part.get("positive_prediction", False),
                "nonnegative_prediction": part.get("nonnegative_prediction", False),
                "stability": {
                    "domain": "observed training range",
                    "relative_noise": 0.01,
                    "ranking": False,
                    "scope": "diagnostic only; measurement error distribution not independently established",
                },
                "coverage": {"required_fraction": 1.0},
                "accuracy_gate": {
                    "policy": "no worse than frozen train-mean predictor on identical test cohort",
                    "ratio": 1.0,
                },
                "test_exposure": "retrospective-open-test",
                "custody": "test outputs accessible only to evaluator; not independent new evidence",
                "preprocessing": {
                    "learned_transformations": [],
                    "measurements": "inherited native measurements and permitted calibrated features; see source lineage",
                },
                "source_task": part["task_id"],
                "source_contract_sha256": part["raw_contract_sha256"],
                "limits": {"portfolio_size": 3, "max_expression_nodes": 160, "max_parameters": 8},
                "assessment_scope": "retrospective predictive rule comparison; mechanism and novelty not established",
            }
            write_json(p / "task-contracts/task-001.json", contract)
            split = {
                "policy": split_policy,
                "partitions": {
                    name: {
                        "rows": len(rows),
                        "groups": len({r["group"] for r in rows}),
                        "sample_ids_sha256": sha([r["sample_id"] for r in rows]),
                        "group_ids_sha256": sha(sorted({r["group"] for r in rows})),
                    }
                    for name, rows in [("train", train), ("dev", dev), ("test", test)]
                },
                "identity_join": "verified opaque reference sample_id and all allowed input values",
                "disjoint_samples": True,
                "disjoint_groups": True,
            }
            write_json(p / "split-manifest.json", split)
            write_json(
                p / "preprocessing/environment.json",
                {
                    "python": ">=3.11",
                    "transforms": "no learned transformations applied",
                    "upstream_prepared_manifest_sha256": file_sha(packet / "manifest.json"),
                    "source_inputs_sha256": file_sha(td / "data/inputs.csv.gz"),
                },
            )
            (p / "preprocessing/README.md").write_text(
                "Source-native prepared quantities; no new numerical values generated. Reconstruct using scripts/curate_v2.py with the preserved local Principia source registry. Original raw data is not needed to run this compact package. SHA256SUMS pins all public content. Inputs retain the legacy task calibration and timing restrictions.\n"
            )
            info = {
                "schema_version": "principia-asd.scenario/2.0",
                "version": "1.0.0rc2",
                "scenario_id": case,
                "title": item["title"],
                "domain": item["domain"],
                "status": "retrospective_local_admitted",
                "source": {
                    "url": item["source_url"],
                    "version": item["source_version"],
                    "historical_case": case,
                    "license": lic,
                    "evidence": evidence,
                },
                "description": part["target"],
                "independent_unit": part["independent_unit"],
                "input_units": part["input_units"],
                "output_units": part["target_units"],
                "modalities": item["modalities"],
                "measurement_representation": "traceable numeric features; native raw modalities not included in this compact track",
                "limitations": [
                    part["observation_window"],
                    "Historical source and target exposure; retrospective only",
                    "Source-license evidence inherited from local register; publication audit pending",
                ],
                "publication_authorized": False,
                "rights_status": "source_terms_documented_pending_final_review",
                "rows": {k: len(v) for k, v in [("train", train), ("dev", dev), ("test", test)]},
                "split": split,
            }
            write_json(p / "scenario.json", info)
            expanded = sum(expanded_size(f) for f in p.rglob("*") if f.is_file()) + expanded_size(
                vault / case / "test_targets.csv.gz"
            )
            if expanded > 10_000_000:
                raise ValueError("Expanded scenario including evaluator targets exceeds 10 MB")
            info["size"] = {
                "expanded_bytes_including_targets": expanded,
                "public_bytes": sum(f.stat().st_size for f in p.rglob("*") if f.is_file()),
                "limit_bytes": 10_000_000,
            }
            write_json(p / "scenario.json", info)
            checks = {str(f.relative_to(p)): file_sha(f) for f in p.rglob("*") if f.is_file()}
            write_json(p / "checksums.json", checks)
            write_json(
                vault / case / "evaluator-manifest.json",
                {
                    "task_id": contract["task_id"],
                    "target_sha256": file_sha(vault / case / "test_targets.csv.gz"),
                    "input_sha256": file_sha(p / "public/test_inputs.csv.gz"),
                    "contract_sha256": file_sha(p / "task-contracts/task-001.json"),
                    "identity_join": True,
                },
            )
            audit.update(
                status="retrospective_local_admitted",
                rows=info["rows"],
                groups={k: v["groups"] for k, v in split["partitions"].items()},
                expanded_bytes=expanded,
                license=lic,
            )
            admitted.append(info)
        except (ValueError, KeyError, FileNotFoundError, StopIteration) as exc:
            audit.update(status="pending_review", reason=str(exc))
            p = out / "scenarios" / case
            if p.exists():
                rejected = vault / "rejected-packages" / case
                rejected.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(p), rejected)
        audits.append(audit)
    write_json(
        out / "EDITION.json",
        {
            "version": "1.0.0rc2",
            "edition_id": "compact-v2",
            "status": "local_research_release_candidate",
            "publication_authorized": False,
            "historical_count": 100,
            "active_scenario_count": len(admitted),
            "active_scenarios": [
                {
                    "scenario_id": i["scenario_id"],
                    "title": i["title"],
                    "domain": i["domain"],
                    "rows": i["rows"],
                }
                for i in admitted
            ],
        },
    )
    write_json(out / "validation/admission-audit.json", audits)
    (out / "README.md").write_text(
        f"# Compact scenario edition\n\n{len(admitted)} locally admitted, grouped, retrospective scenarios from 100 audited historical cases. Each package is under 10 MB expanded, including protected outputs. Publication remains gated on final rights review. Runtime uses only bundled compact tables. Test targets stay outside this directory.\n"
    )
    (out / "LICENSES.md").write_text(
        "# Source licenses\n\nEach scenario.json records the original source license and evidence URLs. This edition does not override upstream terms. Final redistribution review remains open; do not publish until publication_authorized is true.\n"
    )
    print(
        json.dumps(
            {
                "admitted": len(admitted),
                "ids": [x["scenario_id"] for x in admitted],
                "pending": 100 - len(admitted),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--base", type=Path, required=True)
    build(p.parse_args().base)
