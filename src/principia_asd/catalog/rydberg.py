"""Curator reconstruction of the registered ion-readout spectral grid.

Source grid coordinates are not asserted to be independent instrument samples.
No optical response, fitted line shape or RF calibration becomes a predictor.
"""

import csv
import io
import json
import math
from pathlib import Path

import numpy as np

from ..io import contained, sha
from .splits import check_units

FILENAME = "FIG3b_IonSpectra_with_ProbeRabiFrequency.csv"
HEADER = ["delta_c/2pi (MHz)", "Omega_p/2pi (MHz)", "Ion Amplitude (arb. units)"]


def decode_grid(raw, *, max_rows=400_000):
    """Decode a bounded complete rectangular grid, retaining physical CSV rows."""
    if len(raw) > 16_000_000:
        raise ValueError("Spectral grid exceeds bounded source size")
    reader = csv.reader(io.StringIO(raw.decode("utf-8-sig")), strict=True)
    if next(reader, None) != HEADER or reader.line_num != 1:
        raise ValueError("Unexpected spectral columns or frequency/amplitude units")
    records = []
    for index, row in enumerate(reader):
        if index >= max_rows or len(row) != 3 or reader.line_num != index + 2:
            raise ValueError("Excessive, multiline or malformed spectral row")
        x, rabi = (float(v) for v in row[:2])
        if not math.isfinite(x) or not math.isfinite(rabi) or rabi <= 0:
            raise ValueError("Invalid detuning or Rabi coordinate")
        # Missing/nonfinite amplitudes remain explicit exclusions, not imputed zeros.
        y = float(row[2]) if row[2].strip() else math.nan
        records.append((x, rabi, y))
    if not records:
        raise ValueError("Empty spectral grid")
    array = np.asarray(records, dtype=float)
    detuning, rabi = np.unique(array[:, 0]), np.unique(array[:, 1])
    if len(detuning) < 2 or len(rabi) < 2 or len(array) != len(detuning) * len(rabi):
        raise ValueError("Incomplete or duplicated Cartesian spectral grid")
    # The source is detuning-major, then increasing Rabi; do not reorder row identities.
    shape = (len(detuning), len(rabi))
    if not np.array_equal(
        array[:, 0].reshape(shape), np.broadcast_to(detuning[:, None], shape)
    ) or not np.array_equal(array[:, 1].reshape(shape), np.broadcast_to(rabi[None, :], shape)):
        raise ValueError("Repeated, reordered or inconsistent spectral coordinates")
    return array, detuning, rabi


def original_assignments(case, groups):
    from .native import identity

    held = {"rabi-block-06", "rabi-block-09"}
    if not held <= groups:
        raise ValueError("Missing registered confirmation Rabi blocks")
    development = groups - held
    ordered = sorted(
        development, key=lambda g: sha(["compact-v2", case, identity(case, "group", g)])
    )
    dev = set(ordered[: max(2, len(ordered) // 5)])
    return {g: "test" if g in held else "dev" if g in dev else "train" for g in groups}


def reconstruct_rydberg(recipe, source_root):
    from .native import _registered_groups, _row, _unique_object, identity

    (asset,) = [a for a in recipe["assets"] if a["role"] == "ion_spectral_grid"]
    if Path(asset["path"]).name != FILENAME:
        raise ValueError("Unregistered ion spectrum source")
    (metadata,) = [a for a in recipe["assets"] if a["role"] == "nist_source_record"]
    meta = json.loads(
        contained(source_root, metadata["path"]).read_bytes(), object_pairs_hook=_unique_object
    )
    if meta["doi"] != "doi:10.18434/mds2-3951" or meta["version"] != recipe["source_version"]:
        raise ValueError("NIST source identity or revision differs")
    components = [c for c in meta["components"] if c.get("filepath") == FILENAME]
    if (
        len(components) != 1
        or components[0]["checksum"]["algorithm"]["tag"] != "sha256"
        or components[0]["checksum"]["hash"] != asset["sha256"]
        or components[0]["size"] != asset["bytes"]
    ):
        raise ValueError("NIST source record does not bind the selected spectrum")
    array, detuning, rabi = decode_grid(contained(source_root, asset["path"]).read_bytes())
    if [len(detuning), len(rabi)] != recipe["source_grid_shape"] or len(rabi) != 300:
        raise ValueError("Source spectral inventory differs from registered grid")
    groups = {f"rabi-block-{j // 30:02d}" for j in range(len(rabi))}
    assignments = _registered_groups(recipe, groups)
    if assignments != original_assignments(recipe["scenario_id"], groups):
        raise ValueError("Registered Rabi allocation differs from historical metadata rule")
    parts, lineage, units = {p: [] for p in ("train", "dev", "test")}, [], {}
    in_domain = np.flatnonzero(abs(array[:, 0]) <= 60)
    if not len(in_domain):
        raise ValueError("No spectral samples in the fixed detuning domain")
    excluded, counts = [], {g: 0 for g in groups}
    for index in in_domain:
        source_row = int(index) + 2
        x, omega, response = array[index]
        coordinate_index = int(index) % len(rabi)
        group = f"rabi-block-{coordinate_index // 30:02d}"
        if not math.isfinite(response):
            excluded.append({"source_row": source_row, "reason": "nonfinite_source_response"})
            continue
        split = assignments[group]
        units[identity(recipe["scenario_id"], "group", group)] = group
        row, origin = _row(
            recipe["scenario_id"],
            f"{recipe['scenario_id']}:{FILENAME}:row{source_row}",
            group,
            split,
            {"detuning_MHz": float(x), "rabi_MHz": float(omega)},
            response,
            {"source_row": source_row, "rabi_index0": coordinate_index},
        )
        parts[split].append(row)
        lineage.append(origin)
        counts[group] += 1
    if not all(counts.values()):
        raise ValueError("An assigned spectral block has no eligible response")
    summaries = []
    for j in range(0, len(rabi), 30):
        group = f"rabi-block-{j // 30:02d}"
        summaries.append(
            {
                "group": group,
                "partition": assignments[group],
                "rabi_index0_range": [j, j + 29],
                "rabi_MHz_range": [float(rabi[j]), float(rabi[j + 29])],
                "eligible_rows": counts[group],
            }
        )
    return (
        parts,
        lineage,
        {
            "split_check": check_units(parts, units),
            "spectral_validation": {
                "source_grid_rows": len(array),
                "detuning_coordinates": len(detuning),
                "rabi_coordinates": len(rabi),
                "selected_detuning_coordinates": int(np.sum(abs(detuning) <= 60)),
                "eligible_rows": len(lineage),
                "nonfinite_response_rows_in_domain": len(excluded),
                "nonfinite_response_rows_total": int(np.sum(~np.isfinite(array[:, 2]))),
                "outside_domain_rows": len(array) - len(in_domain),
                "detuning_MHz_range": [float(detuning[0]), float(detuning[-1])],
                "rabi_MHz_range": [float(rabi[0]), float(rabi[-1])],
                "coordinate_order": "detuning-major, then increasing probe Rabi frequency",
                "group_counts": {p: sum(s == p for s in assignments.values()) for p in parts},
                "physical_cells_documented": 1,
                "instrument_sampling_or_grid_interpolation": "not_resolved",
                "fitting_performed": False,
            },
            "source_grid": asset["path"],
            "column_inventory": HEADER,
            "lineage_definition": "One-based physical CSV row; columns 1/2 are permitted coordinates and column 3 is response. Rabi index is sorted source-grid index, not an independent experiment ID.",
            "block_inventory": summaries,
            "excluded_rows": excluded,
            "frequency_convention": "Stored delta_c/(2*pi) and Omega_p/(2*pi) in MHz; no extra 2*pi or calibration transformation",
            "excluded_source_quantities": [
                "optical/EIT responses",
                "other ionization branches",
                "fitted linewidth/amplitude summaries",
                "RF calibration fits",
                "noise and sensitivity summaries",
            ],
            "response_scope": "Stored ion-readout amplitude grid in arbitrary units, within |detuning| <= 60 MHz; not an independently calibrated electric-field measurement",
            "independence_scope": "Contiguous coordinate blocks in one cell; separation is not independent-cell, time or instrument replication. Source grid-generation processing remains unresolved.",
            "recommended_edition_role": "pending_source_processing_and_scientific_review",
            "admission_blockers": [
                "Resolve the relationship of the dense coordinate grid to original measured scans and any interpolation",
                "One-cell coordinate holdout does not establish independent apparatus or mechanistic evidence",
                "Complete rights/notices and justified perturbation standards",
            ],
        },
    )
