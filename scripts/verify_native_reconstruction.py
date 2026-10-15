"""Build new private native drafts and verify portable replay without test targets."""

import argparse
import importlib
import subprocess
import sys
import tempfile
from pathlib import Path

from principia_asd.catalog.native import prepare
from principia_asd.io import contained, file_sha, read_json, sha, write_json
from principia_asd.runtime import now


def verify(
    recipes,
    source_root,
    data_root,
    candidate_root,
    replay_python,
    isolated_replay=False,
    selected_scenarios=None,
):
    paths = sorted(recipes.glob("*.raw-v1.json"))
    if selected_scenarios is not None:
        selected_scenarios = set(selected_scenarios)
        paths = [p for p in paths if read_json(p)["scenario_id"] in selected_scenarios]
        if (
            not selected_scenarios
            or {read_json(p)["scenario_id"] for p in paths} != selected_scenarios
        ):
            raise ValueError("Unknown or empty selected recipe scenarios")
    candidate_root = candidate_root.resolve()
    if any(
        candidate_root.is_relative_to(root.resolve()) for root in (source_root, data_root)
    ) or any((p / "EDITION.json").exists() for p in [candidate_root, *candidate_root.parents]):
        raise ValueError(
            "Verification candidates must stay outside source and frozen edition roots"
        )
    candidate_root.mkdir(parents=True, exist_ok=True)
    cases, results, all_assets = set(), [], {}
    for recipe_path in paths:
        recipe = read_json(recipe_path)
        case = recipe["scenario_id"]
        if case in cases:
            raise ValueError("Duplicate scenario identity")
        cases.add(case)
        scenario = contained(data_root, "scenarios/" + case)
        before = {p: file_sha(p) for p in scenario.rglob("*") if p.is_file()}
        output = contained(candidate_root, case)
        record = prepare(recipe_path, source_root, output, compare_scenario=scenario)
        environment = read_json(output / "preprocessing/environment.json")
        # Preserve the small exact reader sources outside all upload roots.
        snapshot = candidate_root / "reader-source" / record["reader_source_sha256"]
        for module, digest in environment["module_hashes"].items():
            source = Path(importlib.import_module(module).__file__)
            dest = snapshot.joinpath(*module.split(".")).with_suffix(".py")
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                if file_sha(dest) != digest:
                    raise ValueError("Existing reader snapshot changed")
            else:
                with dest.open("xb") as stream:
                    stream.write(source.read_bytes())
        with tempfile.TemporaryDirectory(prefix="native-replay-", dir=candidate_root) as folder:
            replay = Path(folder) / "result"
            command = [
                str(replay_python),
                *(["-I"] if isolated_replay else []),
                str(output / "preprocessing/prepare.py"),
                "--source-root",
                str(source_root),
                "--output-root",
                str(replay),
            ]
            subprocess.run(command, check=True, capture_output=True, text=True)
            for relative, digest in record["files"].items():
                if file_sha(contained(replay, relative)) != digest:
                    raise ValueError("Portable raw reconstruction changed: " + relative)
        after = {p: file_sha(p) for p in scenario.rglob("*") if p.is_file()}
        if before != after:
            raise ValueError("Historical scenario mutated")
        for asset in recipe["assets"]:
            all_assets[asset["path"]] = asset
        results.append(
            {
                "scenario_id": case,
                "candidate": case + "/reconstruction.json",
                "candidate_receipt_sha256": file_sha(output / "reconstruction.json"),
                "recipe_sha256": file_sha(recipe_path),
                "rows": record["rows"],
                "reader_source_sha256": record["reader_source_sha256"],
                "runtime_binding_sha256": record["runtime_binding_sha256"],
                "historical_public_parity": record["historical_public_parity"],
                "scientific_split_check": record["checks"]["split_check"],
                "admission_blockers": record["checks"].get("admission_blockers", []),
                "temporal_validation": record["checks"].get("temporal_validation"),
                "native_game_validation": record["checks"].get("game_validation"),
                "native_choice_validation": record["checks"].get("choice_validation"),
                "native_crowd_validation": record["checks"].get("crowd_validation"),
                "native_levitation_validation": record["checks"].get("levitation_validation"),
                "native_comcat_validation": record["checks"].get("comcat_validation"),
                "native_spectral_validation": record["checks"].get("spectral_validation"),
                "native_battery_validation": record["checks"].get("battery_validation"),
                "native_boiling_validation": record["checks"].get("boiling_validation"),
                "native_cpap_validation": record["checks"].get("cpap_validation"),
                "native_afm_validation": record["checks"].get("afm_validation"),
                "native_slag_validation": record["checks"].get("slag_validation"),
                "native_xas_validation": record["checks"].get("xas_validation"),
                "native_microwave_validation": record["checks"].get("microwave_validation"),
                "native_ppg_validation": record["checks"].get("ppg_validation"),
                "native_microscopy_validation": record["checks"].get("microscopy_validation"),
                "native_gwosc_validation": record["checks"].get("gwosc_validation"),
                "native_coral_validation": record["checks"].get("coral_validation"),
                "native_nhtsa_validation": record["checks"].get("nhtsa_validation"),
                "native_piaac_validation": record["checks"].get("piaac_validation"),
                "native_shed_validation": record["checks"].get("shed_validation"),
                "native_storm_validation": record["checks"].get("storm_validation"),
                "native_tomato_validation": record["checks"].get("tomato_validation"),
                "native_yeast_validation": record["checks"].get("yeast_validation"),
                "native_screw_validation": record["checks"].get("screw_validation"),
                "native_compiler_validation": record["checks"].get("compiler_validation"),
                "native_zeolite_validation": record["checks"].get("zeolite_validation"),
                "native_memristor_validation": record["checks"].get("memristor_validation"),
                "native_lubricant_validation": record["checks"].get("lubricant_validation"),
                "native_finger_friction_validation": record["checks"].get(
                    "finger_friction_validation"
                ),
                "acquisition_chronology": record["checks"].get("acquisition_chronology"),
                "native_trace_validation": {
                    "traces": len(record["checks"]["native_traces"]),
                    "measurement_rows": record["checks"]["native_measurement_rows"],
                    "inventory_sha256": sha(record["checks"]["native_traces"]),
                    "trace_values_exported_as_model_inputs": record["checks"][
                        "native_traces_exported_as_model_inputs"
                    ],
                    "response_scope": record["checks"]["response_scope"],
                }
                if "native_traces" in record["checks"]
                else None,
                "native_curve_validation": {
                    "dose_curves": len(record["checks"].get("curves", [])),
                    "recordings": len(record["checks"].get("recordings", [])),
                    "source_cells": record["checks"].get("source_cell_count"),
                    "repeated_cell_recordings": record["checks"].get(
                        "repeated_cell_recordings", []
                    ),
                    "test_recording_date": record["checks"].get("test_recording_date"),
                    "calibration_inventory_sha256": sha(
                        record["checks"].get("curves", record["checks"].get("recordings"))
                    ),
                    "independence_scope": record["checks"]["independence_scope"],
                    "response_scope": record["checks"]["response_scope"],
                }
                if "curves" in record["checks"] or "source_cell_count" in record["checks"]
                else None,
                "all_reconstructed_artifacts_replayed_exactly": True,
                "historical_scenario_files_unchanged": True,
            }
        )
    if not results:
        raise ValueError("No registered recipes")
    return {
        "checked_at": now(),
        "status": "passed",
        "scope": "Curator-only native reconstruction of historical or corrected development drafts; passing replay does not clear reported admission blockers",
        "scenarios": results,
        "registered_source_files": len(all_assets),
        "registered_source_bytes": sum(a["bytes"] for a in all_assets.values()),
        "api_calls": 0,
        "fitting_attempts": 0,
        "fitting_attempts_scope": "Discovery-rule fitting only; local calibration, detrending and scaling are itemized in native validation",
        "evaluator_vault_accessed": False,
        "replay_environment_isolated": isolated_replay,
        "test_targets_exported": False,
        "frozen_edition_replaced": False,
        "raw_acquisition_scope": "Source files include historically exposed responses; preparation does not establish new independent test evidence",
        "remaining_gate": "Complete contracts, rights and notices; native reconstruction for remaining scenarios; new versioned admission and frozen comparison",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for option in ["recipes", "source-root", "data-root", "candidate-root", "output"]:
        parser.add_argument("--" + option, type=Path, required=True)
    parser.add_argument("--replay-python", type=Path, default=Path(sys.executable))
    parser.add_argument("--isolated-replay", action="store_true")
    parser.add_argument(
        "--scenario",
        action="append",
        help="Verify only this registered scenario; repeat to select a batch",
    )
    args = parser.parse_args()
    result = verify(
        args.recipes,
        args.source_root.resolve(),
        args.data_root.resolve(),
        args.candidate_root.resolve(),
        args.replay_python,
        args.isolated_replay,
        args.scenario,
    )
    write_json(args.output, result, immutable=True)
    print(
        {
            "status": result["status"],
            "scenarios": len(result["scenarios"]),
            "api_calls": result["api_calls"],
            "receipt": str(args.output),
        }
    )
