"""Curator-only hBN curve reconstruction with explicit two-point calibration.

Published curves are not independent raw force acquisitions. Duplicate columns
are checked against a frozen alias map; they never define a new selected cohort.
"""

import csv
import hashlib
import io
import json

import numpy as np

from ..io import contained, sha
from .fracture import bounded_zip
from .splits import check_units

SERIES = {
    "concentration": (["PEG", "P5", "P2", "P1"], [0, 5, 2, 1]),
    "functionalization": (["PEG", "P5", "N", "NS"], [0, 5, 5, 5]),
    "suppliers": (["PEG", "P5", "PCH", "NG"], [0, 5, 5, 5]),
}
LABELS = {
    "concentration": [
        "PEG400",
        "PEG400 + 5 wt.% hBN pure",
        "PEG400 + 2 wt.% hBN pure",
        "PEG400 + 1 wt.% hBN pure",
    ],
    "functionalization": [
        "PEG400",
        "PEG400 + 5wt. % hBN pure",
        "PEG400 + 5wt. % hBN N",
        "PEG400 + 5wt. % hBN N+S",
    ],
    "suppliers": [
        "PEG400",
        "PEG400 + 5wt. % hBN pure",
        "PEG400 + 5wt. % hBN PCH",
        "PEG400 + 5wt. % hBN NG",
    ],
}
SPEEDS = [
    500,
    361,
    261,
    188,
    136,
    98,
    71,
    51,
    37,
    27,
    19.2,
    13.9,
    10,
    7.2,
    5.2,
    3.8,
    2.7,
    1.96,
    1.41,
    1.02,
    0.74,
    0.53,
    0.38,
    0.28,
    0.2,
]
INPUT_UNITS = {
    "speed_mm_s": "mm/s",
    "boundary_cof": "dimensionless",
    "highspeed_cof": "dimensionless",
    "concentration_wt_pct": "wt percent",
}


def stored_curves(raw, kind):
    """Read the measured curve block, retaining source metadata and row positions."""
    if kind not in SERIES or len(raw) > 1_000_000:
        raise ValueError("Unknown or oversized hBN curve table")
    rows, width, padding = [], None, 0
    for row in csv.reader(io.StringIO(raw.decode("utf-8-sig")), strict=True):
        if len(rows) >= 128 or not 6 <= len(row) <= 16384:
            raise ValueError("Excessive or malformed hBN table dimensions")
        if width is None:
            width = len(row)
        if len(row) != width or any(cell.strip() for cell in row[6:]):
            raise ValueError("Ragged table or hidden hBN measurement columns")
        padding += len(row) - 6
        rows.append([cell.strip() for cell in row[:6]])
    if len(rows) < 49 or any(row[5] for row in rows[:43]):
        raise ValueError("Missing metadata or extra hBN measurement column")
    if (
        rows[0][0] != "hBN nanoparticles"
        or rows[4][0] != "EHD5 experimental device (optial tribometer)"
        or rows[6][0] != "Ball-on disk configuration"
        or rows[7][1:3] != ["Slide-to-roll ratio (SRR):", "-20%"]
        or rows[10][1] != "Test temperature:"
        or not rows[10][2].endswith("°C")
        or rows[12][1:5] != LABELS[kind]
        or rows[16][1:5] != LABELS[kind]
        or rows[13][0] != "Material 1"
        or rows[14][0] != "Material 2"
        or rows[15][0] not in {"Pressure", "Tlak"}
        or rows[15][1:5] != ["550 MPa"] * 4
        or rows[17][:5] != ["Speed, mm/s", "Coefficient of friction, Ft/Fn, (-)", "", "", ""]
    ):
        raise ValueError("Changed hBN scientific header, labels, units or test configuration")
    expected_materials = (
        ("BK7 glass", "Steel (100Cr6)") if kind == "concentration" else ("Sklo", "Ocel (100Cr6)")
    )
    if any(rows[13 + i][1:5] != [v] * 4 for i, v in enumerate(expected_materials)):
        raise ValueError("Changed hBN contact materials")
    values = np.asarray([[float(cell) for cell in row[:5]] for row in rows[18:43]], dtype="<f8")
    if not np.isfinite(values).all() or np.any(values[:, 1:] < 0):
        raise ValueError("Nonfinite or negative coefficient of friction")
    if values[:, 0].tolist() != SPEEDS:
        raise ValueError("Changed or incomplete descending speed grid and calibration endpoints")
    return values, {
        "source_rows": len(rows),
        "source_columns": width,
        "empty_padding_cells_excluded": padding,
        "measurement_rows_inclusive": [19, 43],
        "measurement_period": rows[1][0],
        "temperature_source_text": rows[10][2],
        "slide_to_roll_ratio": rows[7][2],
        "contact_materials": list(expected_materials),
        "contact_pressure": "550 MPa",
        "uncertainty_source_text": [row[4:6] for row in rows[45:49]],
        "extra_summary_rows_not_used": max(0, len(rows) - 49),
    }


def original_assignments(case, groups):
    from .native import identity

    if groups != {"PEG", "P5", "P2", "P1", "N", "NS", "PCH", "NG"}:
        raise ValueError("Changed registered hBN formulation inventory")
    held = {"NS", "NG"}
    ordered = sorted(
        groups - held, key=lambda g: sha(["compact-v2", case, identity(case, "group", g)])
    )
    dev = set(ordered[:2])
    return {g: "test" if g in held else "dev" if g in dev else "train" for g in groups}


def reconstruct_lubricants(recipe, source_root):
    from .native import _registered_groups, _row, _unique_object, identity

    (asset,) = [a for a in recipe["assets"] if a["role"] == "lubricant_archive"]
    (metadata,) = [a for a in recipe["assets"] if a["role"] == "zenodo_record"]
    meta = json.loads(
        contained(source_root, metadata["path"]).read_bytes(), object_pairs_hook=_unique_object
    )
    if (
        str(meta["id"]) != "17864405"
        or meta["doi"] != "10.5281/zenodo.17864405"
        or recipe["input_units"] != INPUT_UNITS
        or recipe["output_units"] != "dimensionless"
    ):
        raise ValueError("Changed hBN source identity or measurement units")
    tables, curves, aliases, seen, inventory = [], {}, {}, {}, []
    with bounded_zip(
        contained(source_root, asset["path"]), max_bytes=40_000_000, max_member_bytes=5_000_000
    ) as z:
        for kind, (groups, concentrations) in SERIES.items():
            member = f"dataset/CoF dataset {kind}.csv"
            raw = z.read(member)
            values, info = stored_curves(raw, kind)
            info.update({"member": member, "sha256": hashlib.sha256(raw).hexdigest()})
            tables.append(info)
            for col, (group, concentration) in enumerate(
                zip(groups, concentrations, strict=True), 1
            ):
                label = f"{kind}:{group}"
                array = values[:, [0, col]].copy()
                digest = hashlib.sha256(array.tobytes()).hexdigest()
                if digest in seen:
                    aliases[label] = seen[digest]
                else:
                    seen[digest] = label
                curves[label] = (array, member, col + 1, group, concentration)
                inventory.append(
                    {
                        "curve": label,
                        "formulation": group,
                        "member": member,
                        "column_1based": col + 1,
                        "stored_curve_sha256": digest,
                    }
                )
    if aliases != recipe["duplicate_aliases"]:
        raise ValueError("Frozen duplicate curve aliases changed; source review required")
    groups = {c[3] for label, c in curves.items() if label not in aliases}
    assignments = _registered_groups(recipe, groups)
    if assignments != original_assignments(recipe["scenario_id"], groups):
        raise ValueError("Frozen formulation allocation changed")
    parts, lineage, units = {p: [] for p in ("train", "dev", "test")}, [], {}
    for label, (array, member, column, group, concentration) in curves.items():
        if label in aliases:
            continue
        split = assignments[group]
        units[identity(recipe["scenario_id"], "group", group)] = group
        for k, (speed, response) in enumerate(array):
            if not 0.2 < speed <= 10:
                continue
            row, origin = _row(
                recipe["scenario_id"],
                f"{recipe['scenario_id']}:{member}:row{k + 19}:column{column}",
                group,
                split,
                {
                    "speed_mm_s": float(speed),
                    "boundary_cof": float(array[-1, 1]),
                    "highspeed_cof": float(array[0, 1]),
                    "concentration_wt_pct": float(concentration),
                },
                float(response),
                {
                    "curve": label,
                    "member": member,
                    "source_row": k + 19,
                    "column_1based": column,
                    "calibration_rows": {"boundary_cof": 43, "highspeed_cof": 19},
                    "calibration_speeds_mm_s": {"boundary_cof": 0.2, "highspeed_cof": 500},
                },
            )
            parts[split].append(row)
            lineage.append(origin)
    return (
        parts,
        lineage,
        {
            "split_check": check_units(parts, units),
            "lubricant_validation": {
                "stored_curves": len(curves),
                "distinct_curves": len(curves) - len(aliases),
                "stored_response_cells_including_duplicates": 25 * len(curves),
                "formulations": len(groups),
                "duplicate_aliases": aliases,
                "group_counts": {p: sum(v == p for v in assignments.values()) for p in parts},
                "curve_counts": {
                    p: sum(
                        label not in aliases and assignments[c[3]] == p
                        for label, c in curves.items()
                    )
                    for p in parts
                },
                "scored_speed_rows_per_curve": 12,
                "scored_speed_range_mm_s": [0.28, 10],
                "calibration_separate_from_scored_responses": True,
                "fitting_performed": False,
                "unrepresented_highspeed_interior_rows_per_curve": 11,
            },
            "source_tables": tables,
            "curve_inventory": inventory,
            "independence_scope": "Whole formulation separation; physical acquisition and batch identities are not supplied. Two distinct P5 curves stay together. Shared controls do not establish replication.",
            "response_scope": "Published CoF curves and two observed endpoints; calibrated within-setup shape transfer, not prospective unmeasured-lubricant prediction or native force reconstruction.",
            "admission_blockers": [
                "Physical repetitions, preprocessing and source uncertainty model need contract review",
                "Different table temperatures and repeated controls limit independence claims",
                "Final rights, attribution and admission remain pending; retrospective exposed responses",
            ],
        },
    )
