"""Curator-only reactor reconstruction with expanded, causal prefix calibration.

Author-reported selectivity is not raw chromatography. Source formulas and other
response channels are never evaluated or used as predictors. No fitted rule is
learned here; the disclosed prefix slope is an eight-run analytical calibration.
"""

import csv
import hashlib
import io
import json
import math
import re
from pathlib import PurePosixPath

import numpy as np

from ..io import contained, sha
from .levitation import bounded_command, decoder_binding
from .splits import check_units

RUNS = {
    "FigureS12a_reaction_Ag1-Hbeta": 1,
    "FigureS12b_reaction_Ag5-Hbeta": 5,
    "FigureS12c_FigureS13a_reaction_Ag20-Hbeta": 20,
    "FigureS13b_reaction_Ag20-Hbeta_T220": 20,
    "FigureS13c_reaction_Ag20-Hbeta_T240": 20,
    "FigureS13c_reaction_Ag20-Hbeta_T280": 20,
    "FigureS14a_reaction_Ag20-Hbeta-calc": 20,
    "FigureS14b_reaction_Ag20-Hbeta-red": 20,
}
ALIAS = "Figure1_longterm-reaction_Ag20-Hbeta"
CANONICAL = "FigureS14b_reaction_Ag20-Hbeta-red"
HELD = {"FigureS13b_reaction_Ag20-Hbeta_T220", "FigureS14a_reaction_Ag20-Hbeta-calc"}
INPUT_UNITS = {
    "elapsed_min": "min",
    "anchor_selectivity_pct": "percent",
    "prefix_slope_pct_min": "percent/min",
    "ag_wt_pct": "wt percent",
}


def archive_listing(raw):
    """Bound the complete 7z inventory and reject unsafe or ambiguous entries."""
    records, total = {}, 0
    lines = raw.decode("ascii").splitlines()
    if not 1 <= len(lines) <= 600:
        raise ValueError("Invalid zeolite archive member count")
    for line in lines:
        match = re.fullmatch(
            r"([-d])[rwx-]{9}\s+\d+\s+\S+\s+\S+\s+(\d+)\s+"
            r"[A-Za-z]{3}\s+\d+\s+[0-9:]+\s+(.+)",
            line,
        )
        if not match:
            raise ValueError("Unsafe zeolite archive member metadata")
        kind, size, name = match[1], int(match[2]), match[3].rstrip("/")
        path = PurePosixPath(name)
        if (
            path.is_absolute()
            or ".." in path.parts
            or "\\" in name
            or path.parts[0] != "zenodo raw data"
            or str(path) != name
            or not re.fullmatch(r"[A-Za-z0-9 _().+/-]+", name)
        ):
            raise ValueError("Unsafe zeolite archive member path")
        if name in records or size > 1_000_000 or (kind == "d" and size):
            raise ValueError("Duplicate or oversized zeolite archive member")
        total += size
        if total > 150_000_000:
            raise ValueError("Zeolite archive expanded size exceeds limit")
        records[name] = {"bytes": size, "directory": kind == "d"}
    return records


def read_archive(path, expected_binding, expected_members):
    binding = decoder_binding()
    if binding != expected_binding:
        raise ValueError("Zeolite archive decoder differs from frozen recipe")
    with path.open("rb") as stream:
        magic = stream.read(6)
    if path.stat().st_size > 30_000_000 or magic != b"7z\xbc\xaf\x27\x1c":
        raise ValueError("Unsupported or oversized zeolite 7z acquisition")
    records = archive_listing(
        bounded_command([binding["executable"], "-tvf", str(path)], max_bytes=150_000)
    )
    selected = {n: r for n, r in records.items() if "reaction_" in n}
    wanted = {f"zenodo raw data/{g}.txt" for g in [ALIAS, *RUNS]}
    if set(selected) != wanted or set(expected_members) != wanted:
        raise ValueError("Registered reactor inventory changed")
    for name, item in selected.items():
        if item["directory"] or item["bytes"] != expected_members[name]["bytes"]:
            raise ValueError("Registered reactor member size or type changed")
    # One bounded stdout stream avoids repeatedly decompressing the solid archive.
    size = sum(r["bytes"] for r in selected.values())
    if size > 1_000_000:
        raise ValueError("Reactor selection exceeds expanded limit")
    raw = bounded_command(
        [binding["executable"], "-xOf", str(path), "--", *selected],
        max_bytes=size,
        timeout=60,
    )
    if len(raw) != size:
        raise ValueError("Truncated reactor archive stream")
    offset, members = 0, {}
    for name, item in selected.items():
        data = raw[offset : offset + item["bytes"]]
        offset += item["bytes"]
        if hashlib.sha256(data).hexdigest() != expected_members[name]["sha256"]:
            raise ValueError("Reactor archive order or member hash changed")
        members[name] = data
    return members, {
        "archive_members": len(records),
        "archive_expanded_bytes": sum(r["bytes"] for r in records.values()),
        "selected_expanded_bytes": size,
    }


def stored_reactor(raw):
    """Decode time/DMM only; preserve missing rows and literal formula exclusion."""
    if len(raw) > 100_000:
        raise ValueError("Oversized reactor table")
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig")), delimiter="\t", strict=True))
    if not 8 <= len(rows) <= 2000 or any(len(r) != 8 for r in rows):
        raise ValueError("Malformed reactor table dimensions")
    columns, labels, units = rows[:3]
    if (
        columns != list("ABCDEFGH")
        or labels[0] not in {"Time on stream", "Laufzeit"}
        or labels[1] not in {"MeOH conversion", "Methanol conversion"}
        or labels[2:4] != ["conversion", "activity"]
        or labels[4:7] not in (["DME", "MF", "DMM"], ["S(DME)", "S(MF)", "S(DMM)"])
        or labels[7] != "Formulas"
        or units != ["min", "%", "mmol/h", "mmol/h/g_cat", "%", "%", "%", ""]
    ):
        raise ValueError("Changed reactor scientific labels or units")
    values, excluded, restarts, previous, segment = [], [], [], None, 0
    formulas = 0
    for number, row in enumerate(rows[3:], 4):
        t = float(row[0])
        if not math.isfinite(t) or t < 0:
            raise ValueError("Invalid reactor time")
        formulas += bool(row[7])
        if row[6] in {"", "--"}:
            excluded.append(number)
            continue
        y = float(row[6])
        if not math.isfinite(y) or not 0 <= y <= 100:
            raise ValueError("Invalid DMM selectivity percentage")
        if previous is not None:
            if t == previous:
                raise ValueError("Repeated finite reactor clock")
            if t < previous:
                if t != 0:
                    raise ValueError("Unexplained reactor clock reversal")
                segment += 1
                restarts.append(number)
        previous = t
        values.append((number, t, y, segment))
    if not values:
        raise ValueError("No finite reactor measurements")
    return values, {
        "source_rows": len(rows) - 3,
        "finite_response_rows": len(values),
        "missing_response_rows": excluded,
        "restart_rows": restarts,
        "literal_formula_cells_excluded": formulas,
        "time_unit": "min",
        "response_unit": "percent",
        "ignored_columns_1based": [2, 3, 4, 5, 6, 8],
    }


def prefix_forecasts(values):
    """Expanded OLS calibration uses only 120..300 min, never later responses."""
    forecasts, calibrations = [], []
    for segment in sorted({v[3] for v in values}):
        rows = [r for r in values if r[3] == segment]
        cal = [r for r in rows if r[1] <= 300]
        win = [r for r in cal if r[1] >= 120]
        late = [r for r in rows if 300 < r[1] <= 1500]
        if len(cal) < 2 or len(win) < 2 or not late:
            raise ValueError("Insufficient fixed reactor calibration or target window")
        times, responses = np.asarray([(r[1], r[2]) for r in win]).T
        centered = times - times.mean()
        denominator = np.sum(centered**2)
        if denominator <= 0:
            raise ValueError("Degenerate reactor calibration clock")
        slope = float(np.sum(centered * (responses - responses.mean())) / denominator)
        last = max(cal, key=lambda r: r[1])
        calibrations.append(
            {
                "segment": segment,
                "prefix_source_rows": [r[0] for r in cal],
                "slope_source_rows": [r[0] for r in win],
                "anchor_source_row": last[0],
                "anchor_time_min": last[1],
                "slope_time_window_min": [120, 300],
                "target_rows": len(late),
                "free_calibration_coefficients": 2,
                "calibration_formula": "sum((t-mean(t))*(y-mean(y)))/sum((t-mean(t))**2)",
            }
        )
        for number, t, response, _ in late:
            forecasts.append(
                (
                    number,
                    segment,
                    response,
                    {
                        "elapsed_min": t - last[1],
                        "anchor_selectivity_pct": last[2],
                        "prefix_slope_pct_min": slope,
                    },
                )
            )
    return forecasts, calibrations


def original_assignments(case):
    from .native import identity

    ordered = sorted(
        set(RUNS) - HELD, key=lambda g: sha(["compact-v2", case, identity(case, "group", g)])
    )
    dev = set(ordered[: max(2, len(ordered) // 5)])
    return {g: "test" if g in HELD else "dev" if g in dev else "train" for g in RUNS}


def reconstruct_zeolite(recipe, source_root):
    from .native import _registered_groups, _row, _unique_object, identity

    (asset,) = [a for a in recipe["assets"] if a["role"] == "reactor_archive"]
    (metadata,) = [a for a in recipe["assets"] if a["role"] == "zenodo_record"]
    meta = json.loads(
        contained(source_root, metadata["path"]).read_bytes(), object_pairs_hook=_unique_object
    )
    if (
        str(meta["id"]) != "15691695"
        or meta["doi"] != "10.5281/zenodo.15691695"
        or recipe["input_units"] != INPUT_UNITS
        or recipe["output_units"] != "percentage points"
    ):
        raise ValueError("Reactor source identity or unit convention differs")
    members, archive_info = read_archive(
        contained(source_root, asset["path"]), recipe["decoder_binding"], recipe["archive_members"]
    )
    decoded = {PurePosixPath(n).stem: (*stored_reactor(raw), n) for n, raw in members.items()}
    if decoded[ALIAS][0] != decoded[CANONICAL][0] or decoded[ALIAS][1] != decoded[CANONICAL][1]:
        raise ValueError("Frozen long-term reactor duplicate differs")
    assignments = _registered_groups(recipe, set(RUNS))
    if assignments != original_assignments(recipe["scenario_id"]):
        raise ValueError("Frozen whole-reactor allocation changed")
    parts, lineage, units, runs = {p: [] for p in ("train", "dev", "test")}, [], {}, []
    for group, loading in RUNS.items():
        values, info, member = decoded[group]
        forecasts, calibration = prefix_forecasts(values)
        split = assignments[group]
        units[identity(recipe["scenario_id"], "group", group)] = group
        runs.append(
            {
                "group": group,
                "split": split,
                "member": member,
                **info,
                "calibration": calibration,
                "selected_rows": len(forecasts),
                "source_label_ag_wt_pct": loading,
            }
        )
        for number, segment, response, features in forecasts:
            row, origin = _row(
                recipe["scenario_id"],
                f"{recipe['scenario_id']}:{member}:row{number}",
                group,
                split,
                {**features, "ag_wt_pct": float(loading)},
                response,
                {
                    "member": member,
                    "source_row": number,
                    "segment": segment,
                    "calibration_key": group + f":segment{segment}",
                    "response_column_1based": 7,
                },
            )
            parts[split].append(row)
            lineage.append(origin)
    return (
        parts,
        lineage,
        {
            "split_check": check_units(parts, units),
            "reactor_runs": runs,
            "zeolite_validation": {
                **archive_info,
                "distinct_runs": len(runs),
                "source_rows_distinct_runs": sum(r["source_rows"] for r in runs),
                "finite_response_rows": sum(r["finite_response_rows"] for r in runs),
                "missing_response_rows": sum(len(r["missing_response_rows"]) for r in runs),
                "restarts": sum(len(r["restart_rows"]) for r in runs),
                "analytical_prefix_calibrations": sum(len(r["calibration"]) for r in runs),
                "rule_fitting_attempts": 0,
                "duplicate_alias": {ALIAS: CANONICAL},
                "group_counts": {p: sum(r["split"] == p for r in runs) for p in parts},
                "calibration_scope": "Each run's own <=300 min responses; slope fit on 120..300 min; targets at >300..1500 min",
                "selected_response": "Author-reported DMM selectivity; no raw chromatogram recomputation",
                "no_future_or_other_response_predictors": True,
            },
            "admission_blockers": [
                "Physical run, catalyst-batch independence and acquisition dates need source review",
                "Author-reported selectivity processing and source-label Ag loading require review",
                "Eight retrospective calibrated trajectories do not establish mechanism or independent transfer",
                "Scientific contract, measurement-error stability and final rights/attribution review pending",
            ],
        },
    )
