"""Curator reconstruction of participant-fluid summaries with native trace custody.

Hersey and viscosity inputs are author-derived, not independent measurements.
Raw clocks and missing positions are audited, never imputed into a new endpoint.
"""

import csv
import hashlib
import io
import json
import math
import re

import numpy as np

from ..io import contained, sha
from .splits import check_units

SUMMARY_HEADER = [
    "participant",
    "sample",
    "material",
    "velocity",
    "Fz",
    "prefactor",
    "exponent",
    "HrVeltkamp",
    "eta(gamma)",
    "log(Hr Veltkamp)",
    "log(eta)",
    "CoF",
]
SUMMARY_UNITS = ["none", "none", "none", "m/s", "N", "Pa s^n", "none", "1", "Pa s", "1", "1", "1"]
RAW_HEADER = ["sample", "participant", "time(s)", "x(m)", "y(m)", "z(m)", "Fx", "Fy", "Fz"]
RAW_UNITS = ["none", "none", "s", "m", "m", "m", "N", "N", "N"]
INPUT_UNITS = {
    "H": "dimensionless; author Hersey calibration",
    "viscosity": "Pa s at 500 s^-1; author rheology fit",
    "speed": "m/s",
    "load": "N",
    "hydration": "corneometer instrument units",
    "area": "cm^2",
}
PARTICIPANTS = {f"ID{i:02d}" for i in range(1, 12)}


def table(path, header, units, *, delimiter=",", max_bytes=100_000, max_rows=1000, comments=True):
    """Bound native tables; the one documented extra comment cell is not data."""
    if path.stat().st_size > max_bytes:
        raise ValueError("Oversized finger-friction table")
    rows = list(
        csv.reader(
            io.StringIO(path.read_text(encoding="utf-8-sig")), delimiter=delimiter, strict=True
        )
    )
    if len(rows) > max_rows or len(rows) < (4 if comments else 3):
        raise ValueError("Unexpected finger-friction row count")
    if rows[0] != header or rows[1] != units:
        raise ValueError("Changed finger-friction columns or units")
    if comments and len(rows[2]) != len(header):
        if header != SUMMARY_HEADER or rows[2][len(header) :] != [" none"]:
            raise ValueError("Unexpected finger-friction comment columns")
    start = 3 if comments else 2
    if any(len(row) != len(header) for row in rows[start:]):
        raise ValueError("Ragged or hidden finger-friction data columns")
    return list(enumerate(rows[start:], start + 1))


def finite(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Nonfinite finger-friction measurement")
    return number


def trial_key(participant, sample):
    if (
        participant not in PARTICIPANTS
        or not re.fullmatch(r"[1-9][0-9]?", sample)
        or not 1 <= int(sample) <= 15
    ):
        raise ValueError("Unknown participant or fluid identity")
    return participant, int(sample)


def original_assignments(case, groups):
    from .native import identity

    if groups != PARTICIPANTS:
        raise ValueError("Changed full participant inventory")
    held = set(
        sorted(
            groups, key=lambda x: hashlib.sha256(("P100-ASD-B4-20261001:" + x).encode()).hexdigest()
        )[:2]
    )
    dev = set(
        sorted(groups - held, key=lambda x: sha(["compact-v2", case, identity(case, "group", x)]))[
            :2
        ]
    )
    return {g: "test" if g in held else "dev" if g in dev else "train" for g in groups}


def native_trials(path):
    rows = table(
        path, RAW_HEADER, RAW_UNITS, delimiter="\t", max_bytes=16_000_000, max_rows=300_000
    )
    trials, previous = {}, None
    for line, r in rows:
        key = trial_key(r[1], r[0])
        if key != previous:
            if key in trials:
                raise ValueError("Repeated disjoint source trial block")
            trials[key] = {
                "start_row": line,
                "last_row": line,
                "forces": [],
                "finite_times": [],
                "missing_position_rows": [],
                "rows": 0,
            }
            previous = key
        trial = trials[key]
        trial["last_row"] = line
        trial["rows"] += 1
        absent = [cell == "" for cell in r[2:6]]
        if any(absent):
            if not all(absent):
                raise ValueError("Partial clock/position missingness has changed")
            trial["missing_position_rows"].append(line)
        else:
            values = list(map(finite, r[2:6]))
            trial["finite_times"].append(values[0])
        force = list(map(finite, r[6:]))
        trial["forces"].append(force[2])
    result = {}
    for key, trial in trials.items():
        times = np.asarray(trial["finite_times"])
        if not len(times) or times[0] != 0 or np.any(np.diff(times) < 0):
            raise ValueError("Unknown raw trial origin or reversed clock")
        result[key] = {
            "participant": key[0],
            "sample": key[1],
            "source_rows_inclusive": [trial["start_row"], trial["last_row"]],
            "rows": trial["rows"],
            "missing_clock_position_rows": len(trial["missing_position_rows"]),
            "missing_clock_position_rows_sha256": sha(trial["missing_position_rows"]),
            "repeated_finite_clocks": int((np.diff(times) == 0).sum()),
            "time_range_s": [float(times[0]), float(times[-1])],
            "normal_force_median": float(np.median(trial["forces"])),
        }
    return result


def auxiliary_inventory(assets, source_root, keys):
    inventory = []
    for asset in assets:
        path = contained(source_root, asset["path"])
        if asset["role"] == "height_hersey":
            match = re.fullmatch(r"HeightHersey(ID[0-9]{2})sample([0-9]{2})\.dat", path.name)
            if not match or (match[1], int(match[2])) not in keys:
                raise ValueError("Unmapped height/Hersey source identity")
            rows = table(
                path,
                ["time", "height", "log(Hersey number)"],
                ["s", "mm", "1"],
                comments=False,
                max_rows=5000,
            )
            values = np.asarray([[float(x) for x in r] for _, r in rows])
            if (
                not np.isfinite(values[:, 0]).all()
                or np.any(np.diff(values[:, 0]) <= 0)
                or np.isinf(values).any()
            ):
                raise ValueError("Invalid auxiliary height clock or infinity")
            inventory.append(
                {
                    "file": path.name,
                    "rows": len(rows),
                    "header_rows": 2,
                    "missing_height": int(np.isnan(values[:, 1]).sum()),
                    "missing_log_hersey": int(np.isnan(values[:, 2]).sum()),
                    "used_as_predictor": False,
                }
            )
        elif asset["role"] == "rheology":
            header = ["shear rate", *[f"sample {i}" for i in range(1, 16)]]
            rows = table(path, header, ["1/s", *(["mPa s"] * 15)])
            values = np.asarray([[finite(x) if x else np.nan for x in r] for _, r in rows])
            if (
                not np.isfinite(values[:, 0]).all()
                or np.any(np.diff(values[:, 0]) <= 0)
                or np.any(values <= 0)
            ):
                raise ValueError("Invalid rheology domain or shear coordinates")
            inventory.append(
                {
                    "file": path.name,
                    "rows": len(rows),
                    "fluids": 15,
                    "missing_viscosity_cells": int(np.isnan(values[:, 1:]).sum()),
                    "viscosity_unit": "mPa s",
                    "used_as_predictor": False,
                }
            )
    return inventory


def reconstruct_finger_friction(recipe, source_root):
    from .native import _registered_groups, _row, _unique_object, identity

    by_role = {}
    for asset in recipe["assets"]:
        by_role.setdefault(asset["role"], []).append(contained(source_root, asset["path"]))
    if {k: len(v) for k, v in by_role.items()} != {
        "zenodo_record": 1,
        "participants": 1,
        "rheology_fit": 1,
        "friction_summary": 1,
        "raw_trials": 1,
        "rheology": 1,
        "height_hersey": 4,
        "source_readme": 1,
    }:
        raise ValueError("Incomplete or ambiguous registered finger-friction sources")
    meta = json.loads(by_role["zenodo_record"][0].read_bytes(), object_pairs_hook=_unique_object)
    if (
        str(meta["id"]) != "15365365"
        or meta["doi"] != "10.5281/zenodo.15365365"
        or recipe["input_units"] != INPUT_UNITS
        or recipe["output_units"] != "1"
    ):
        raise ValueError("Changed finger-friction source identity or units")
    people = {}
    for line, r in table(
        by_role["participants"][0],
        ["participant", "finger pad area", "SC hydration"],
        ["1", "cm^2", "a.u."],
        delimiter="\t",
    ):
        area, hydration = map(finite, r[1:])
        if r[0] in people or r[0] not in PARTICIPANTS or area <= 0 or not 0 <= hydration <= 120:
            raise ValueError("Invalid or duplicate participant measurement")
        people[r[0]] = {"area": area, "hydration": hydration, "source_row": line}
    assignments = _registered_groups(recipe, set(people))
    if assignments != original_assignments(recipe["scenario_id"], set(people)):
        raise ValueError("Frozen participant allocation changed")
    fits = {}
    for line, r in table(
        by_role["rheology_fit"][0], ["recipe", "sample", "K", "n-1"], ["none", "1", "mPa s^n", "1"]
    ):
        sample = trial_key("ID01", r[1])[1]
        if sample in fits:
            raise ValueError("Duplicate rheology fit identity")
        fits[sample] = (*map(finite, r[2:]), line)
    if set(fits) != set(range(1, 16)):
        raise ValueError("Incomplete rheology fit inventory")
    raw = native_trials(by_role["raw_trials"][0])
    parts, lineage, units, keys = {p: [] for p in ("train", "dev", "test")}, [], {}, set()
    max_load_difference = max_fit_difference = 0.0
    for index, (line, r) in enumerate(
        table(by_role["friction_summary"][0], SUMMARY_HEADER, SUMMARY_UNITS)
    ):
        key = trial_key(r[0], r[1])
        if key in keys or key not in raw or r[2] not in {"1", "2", "3"}:
            raise ValueError("Duplicate or unmapped participant-fluid summary")
        keys.add(key)
        speed, load, prefactor, exponent, hersey, viscosity, log_h, log_eta, response = map(
            finite, r[3:]
        )
        if min(speed, load, prefactor, hersey, viscosity) <= 0 or response < 0:
            raise ValueError("Invalid summary measurement domain")
        fit = fits[key[1]]
        if (prefactor, exponent) != fit[:2]:
            raise ValueError("Author rheology fit and summary parameters disagree")
        fit_difference = abs(viscosity - prefactor * 500**exponent)
        if not math.isclose(viscosity, prefactor * 500**exponent, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("Author viscosity transformation differs")
        if not math.isclose(log_h, math.log10(hersey), abs_tol=1e-12) or not math.isclose(
            log_eta, math.log10(viscosity), abs_tol=1e-12
        ):
            raise ValueError("Author log fields disagree")
        load_difference = abs(load - raw[key]["normal_force_median"])
        if not math.isclose(load, raw[key]["normal_force_median"], rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("Published load does not equal native trial median")
        max_load_difference = max(max_load_difference, load_difference)
        max_fit_difference = max(max_fit_difference, fit_difference)
        person, split = people[key[0]], assignments[key[0]]
        units[identity(recipe["scenario_id"], "group", key[0])] = key[0]
        row, origin = _row(
            recipe["scenario_id"],
            f"P100-023-{index:07d}",
            key[0],
            split,
            {
                "H": hersey,
                "viscosity": viscosity,
                "speed": speed,
                "load": load,
                "hydration": person["hydration"],
                "area": person["area"],
            },
            response,
            {
                "participant": key[0],
                "sample": key[1],
                "summary_row": line,
                "summary_columns_1based": {
                    "H": 8,
                    "viscosity": 9,
                    "speed": 4,
                    "load": 5,
                    "target": 12,
                },
                "participant_row": person["source_row"],
                "participant_columns_1based": {"area": 2, "hydration": 3},
                "author_fit_row": fit[2],
                "raw_trial_rows_inclusive": raw[key]["source_rows_inclusive"],
            },
        )
        parts[split].append(row)
        lineage.append(origin)
    expected = {(p, s) for p in PARTICIPANTS for s in range(1, 16)}
    if keys != expected or set(raw) != expected:
        raise ValueError("Incomplete participant-fluid panel or unmatched native trials")
    # Native forces are curator checks, not copied raw response fields in the draft.
    inventory = [
        {k: v for k, v in raw[key].items() if k != "normal_force_median"} for key in sorted(raw)
    ]
    return (
        parts,
        lineage,
        {
            "split_check": check_units(parts, units),
            "raw_trial_inventory": inventory,
            "auxiliary_inventory": auxiliary_inventory(recipe["assets"], source_root, keys),
            "finger_friction_validation": {
                "participants": len(people),
                "fluids_per_participant": 15,
                "summary_rows": len(keys),
                "raw_trials": len(raw),
                "native_force_position_rows": sum(v["rows"] for v in raw.values()),
                "missing_clock_position_rows": sum(
                    v["missing_clock_position_rows"] for v in raw.values()
                ),
                "repeated_finite_clocks": sum(v["repeated_finite_clocks"] for v in raw.values()),
                "trials_with_repeated_clocks": sum(
                    v["repeated_finite_clocks"] > 0 for v in raw.values()
                ),
                "native_force_median_max_difference": max_load_difference,
                "author_viscosity_transform_max_difference": max_fit_difference,
                "group_counts": {p: sum(v == p for v in assignments.values()) for p in parts},
                "unit_header_conflict": "Rheology fit K header says mPa s^n; identical prefactors in friction summary say Pa s^n. Raw rheology viscosities say mPa s. No silent conversion or refitting.",
                "fitting_performed": False,
            },
            "admission_blockers": [
                "Resolve fitted-parameter unit conflict and provenance of author Hersey calibration",
                "Published speed/CoF preprocessing is not independently reconstructed; raw clock gaps and repeats remain",
                "Same fluid panel and substrate; no new material/system or causal-physics claim",
                "Rights/notices, scientific contract and perturbation standard remain pending",
            ],
        },
    )
