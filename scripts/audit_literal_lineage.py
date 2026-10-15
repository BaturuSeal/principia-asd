"""Audit every frozen assignment without fitting, evaluation targets, API calls or reranking."""

import argparse
import sys
from collections import Counter
from pathlib import Path

import numpy as np

import principia_asd.engine.lineage_audit as auditor
from principia_asd.engine.lineage_audit import AUDIT_VERSION, audit_expression
from principia_asd.io import contained, file_sha, read_csv, read_json, write_json
from principia_asd.runtime import now

REVIEWED_GRAMMAR_SHA256 = "92a716d6ad71dfe8f9f5ff02866a45fba97b3cbeb61681afa55197c2025f1c37"


def audit(workspace, campaign_id):
    campaign = contained(workspace / "campaigns", campaign_id)
    manifest_path = campaign / "manifest.json"
    manifest = read_json(manifest_path)
    if manifest["source_hashes"].get("engine/search.py") != REVIEWED_GRAMMAR_SHA256:
        raise ValueError("This frozen grammar source has not been reviewed for this audit version")
    freeze = read_json(campaign / "submission-freeze.json")
    if file_sha(manifest_path) != freeze["manifest_sha256"]:
        raise ValueError("Campaign manifest mutation")
    jobs = manifest["jobs"]
    if len({j["run_id"] for j in jobs}) != len(jobs) or set(freeze["submissions"]) != {
        j["run_id"] for j in jobs
    }:
        raise ValueError("Frozen assigned denominator mismatch")
    runtime = Path(read_json(campaign / "launch.json")["runtime_source"]) / "principia_asd"
    for name, expected in manifest["source_hashes"].items():
        if file_sha(contained(runtime, name)) != expected:
            raise ValueError("Frozen runtime mutation")
    rows, attempts, inputs = [], [], {}
    for job in jobs:
        folder = contained(workspace / "runs", job["run_id"])
        bound = read_json(folder / "submission-freeze.json")
        if file_sha(folder / "submission.json") != freeze["submissions"][job["run_id"]]:
            raise ValueError("Campaign submission binding mutation")
        if (
            file_sha(folder / "submission.json") != bound["submission_sha256"]
            or file_sha(folder / "manifest.json") != bound["manifest_sha256"]
        ):
            raise ValueError("Run binding mutation")
        result = read_json(folder / "submission.json")
        run_manifest = read_json(folder / "manifest.json")
        request = read_json(folder / "request.json")
        scenario = Path(request["scenario_path"])
        train_path = contained(scenario, result["contract"]["split"]["train"])
        expected = run_manifest["input_hashes"]["train"]
        if file_sha(train_path) != expected:
            raise ValueError("Training source mutation")
        if expected not in inputs:
            inputs[expected] = read_csv(train_path)
        attempts.append(
            {
                "run_id": job["run_id"],
                "method_id": job["method_id"],
                "scenario_id": job["scenario_id"],
                "status": result["status"],
                "rules": len(result["rules"]),
                "submission_sha256": bound["submission_sha256"],
            }
        )
        for rule in result["rules"]:
            rows.append(
                audit_expression(rule, result.get("trace", []), inputs[expected], expected)
                | {
                    "method_id": job["method_id"],
                    "scenario_id": job["scenario_id"],
                    "submission_sha256": bound["submission_sha256"],
                }
            )
    summary = {
        "attempts": len(attempts),
        "attempt_status_counts": dict(Counter(a["status"] for a in attempts)),
        "rules": len(rows),
        "expression_rules": sum(r["scan_status"] != "nonexpression_not_assessed" for r in rows),
        "known_grammar_normalization_rules": sum(bool(r["normalization_witnesses"]) for r in rows),
        "exact_prior_fit_match_rules": sum(bool(r["prior_fit_matches"]) for r in rows),
        "either_match_rules": sum(r["scan_status"] == "matched" for r in rows),
        "by_method": {},
    }
    for method in sorted({a["method_id"] for a in attempts}):
        selected = [r for r in rows if r["method_id"] == method]
        summary["by_method"][method] = {
            "assigned": sum(a["method_id"] == method for a in attempts),
            "rules": len(selected),
            "normalization_matches": sum(bool(r["normalization_witnesses"]) for r in selected),
            "prior_fit_matches": sum(bool(r["prior_fit_matches"]) for r in selected),
        }
    return {
        "audit_version": AUDIT_VERSION,
        "checked_at": now(),
        "status": "completed_with_open_lineage",
        "campaign_id": campaign_id,
        "manifest_sha256": file_sha(manifest_path),
        "submission_freeze_sha256": file_sha(campaign / "submission-freeze.json"),
        "frozen_search_source_sha256": manifest["source_hashes"]["engine/search.py"],
        "audit_module_sha256": file_sha(Path(auditor.__file__)),
        "audit_script_sha256": file_sha(Path(__file__)),
        "audit_python": sys.version.split()[0],
        "audit_numpy": np.__version__,
        "api_calls": 0,
        "fitting_attempts": 0,
        "evaluator_targets_accessed": False,
        "scores_or_rankings_changed": False,
        "full_learned_state_status": "not_assessed",
        "limits": "Exact pattern audit is a lower bound; unrecorded/rounded/rewritten state remains unresolved. Engineering cohorts are separate.",
        "summary": summary,
        "attempts": attempts,
        "rules": rows,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--campaign", required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    result = audit(a.workspace, a.campaign)
    write_json(a.output, result, immutable=True)
    print(__import__("json").dumps(result["summary"], indent=2))
