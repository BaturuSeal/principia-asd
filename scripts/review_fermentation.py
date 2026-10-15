"""Read-only historical cohort parity and timestamp audit; never evaluate a rule."""

import argparse
from pathlib import Path

from principia_asd.catalog.native import compare_public, reconstruct
from principia_asd.io import contained, file_sha, read_json, sha, write_json
from principia_asd.runtime import now


def review(recipe_path, source_root, data_root):
    recipe = read_json(recipe_path)
    if recipe["scenario_id"] != "P100-086":
        raise ValueError("This review only supports the registered fermentation case")
    scenario = contained(data_root, "scenarios/P100-086")
    task = read_json(scenario / "task-contracts/task-001.json")
    if sha(task) != recipe["historical_contract_sha256"]:
        raise ValueError("Historical task contract changed")
    before = {str(p.relative_to(scenario)): file_sha(p) for p in scenario.rglob("*") if p.is_file()}
    parts, _, checks = reconstruct(recipe, source_root)
    parity = compare_public(parts, scenario)
    after = {str(p.relative_to(scenario)): file_sha(p) for p in scenario.rglob("*") if p.is_file()}
    if before != after:
        raise ValueError("Frozen scenario mutated during read-only review")
    return {
        "checked_at": now(),
        "review_id": "fermentation-acquisition-clock-v1",
        "scenario_id": "P100-086",
        "task_id": task["task_id"],
        "status": "preparation_defect" if checks["admission_blockers"] else "timing_checks_passed",
        "contract_sha256": sha(task),
        "recipe_sha256": file_sha(recipe_path),
        "source_assets": recipe["assets"],
        "source_input_hashes": {p: file_sha(contained(scenario, task["split"][p])) for p in parts},
        "source_batches": len(checks["source_batches"]),
        "eligible_batches": sum(b["eligible_rows"] > 0 for b in checks["source_batches"]),
        "source_rows": sum(b["source_rows"] for b in checks["source_batches"]),
        "no_eligible_window_batches": [
            b for b in checks["source_batches"] if not b["eligible_rows"]
        ],
        "repeated_nominal_clock_batches": len(
            {r["batch"] for r in checks["duplicate_nominal_clocks"]}
        ),
        "split_group_check": checks["split_check"],
        "temporal_validation": checks["temporal_validation"],
        "admission_blockers": checks["admission_blockers"],
        "historical_public_parity": parity,
        "historical_files_unchanged": True,
        "raw_source_scope": "Historically public acquisitions contain responses; this curator audit is not independent blind validation",
        "api_calls": 0,
        "fitting_attempts": 0,
        "evaluator_vault_accessed": False,
        "quantitative_scores_changed": False,
        "next_action": "Keep the fixed historical cohort; review actual timestamp-based targets, boundary purging and train/dev chronology in a separately versioned contract before any new scored campaign",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for name in ["recipe", "source-root", "data-root", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if any(
        args.output.resolve().is_relative_to(p.resolve())
        for p in (args.source_root, args.data_root)
    ):
        raise ValueError("Audit receipt must be outside frozen source and scenario roots")
    result = review(args.recipe, args.source_root, args.data_root)
    write_json(args.output, result, immutable=True)
    print(
        {
            "status": result["status"],
            "scenario": result["scenario_id"],
            "clock_disagreement_rows": result["temporal_validation"]["clock_disagreement_rows"],
            "api_calls": 0,
            "output": str(args.output),
        }
    )
