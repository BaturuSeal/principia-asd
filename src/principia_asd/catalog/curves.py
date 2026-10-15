"""Curator-only calibrated biological response curves from registered CSV sources."""

import csv
import io
import math
import re
from collections import defaultdict

import numpy as np

from ..io import contained
from .fracture import bounded_zip
from .splits import check_units


def _number(value):
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Non-numeric stored curve measurement") from exc
    if not math.isfinite(result):
        raise ValueError("Nonfinite stored curve measurement")
    return result


def _csv_rows(raw, expected_headers):
    reader = csv.reader(io.StringIO(raw.decode("utf-8-sig")), strict=True)
    if next(reader, None) != expected_headers:
        raise ValueError("Unexpected native curve columns")
    rows = []
    for line, row in enumerate(reader, 2):
        if len(row) != len(expected_headers) or any("\n" in v or "\r" in v for v in row):
            raise ValueError("Ragged native curve row")
        rows.append((line, row))
    if not rows:
        raise ValueError("Empty native curve source")
    return rows


def reconstruct_kinase(recipe, source_root):
    from .native import _registered_groups, _row, identity

    (asset,) = [a for a in recipe["assets"] if a["role"] == "kinase_curves"]
    header = recipe["source_columns"]
    if len(header) != 21 or header[0] != "Time (min)" or any(header[10:]):
        raise ValueError("Unexpected kinase measurement inventory")
    labels = []
    for name in header[1:10]:
        match = re.fullmatch(r"BS ([0-9]+(?:,[0-9]+)?)uM", name)
        if not match:
            raise ValueError("Unresolved kinase dose or concentration units")
        dose = _number(match[1].replace(",", "."))
        if dose <= 0:
            raise ValueError("Nonpositive kinase concentration")
        labels.append(format(dose, "g"))
    if len(set(labels)) != len(labels):
        raise ValueError("Aliased kinase dose identity")
    rows = _csv_rows(contained(source_root, asset["path"]).read_bytes(), header)
    missing_times = [line for line, row in rows if row[0] == "--"]
    if any(any(v != "--" for v in row[1:10]) for _, row in rows if row[0] == "--"):
        raise ValueError("Observed kinase response has no time coordinate")
    rows = [(line, row) for line, row in rows if row[0] != "--"]
    times = [_number(r[0]) for _, r in rows]
    if any(b <= a for a, b in zip(times, times[1:], strict=False)):
        raise ValueError("Repeated or nonmonotone kinase time coordinate")
    assignments = _registered_groups(recipe, {"dose-" + g for g in labels})
    parts, lineage, units, summaries = {p: [] for p in ("train", "dev", "test")}, [], {}, []
    for column, label in enumerate(labels, 1):
        group = "dose-" + label
        split = assignments[group]
        units[identity(recipe["scenario_id"], "group", group)] = group
        measured, missing = {}, list(missing_times)
        for (line, row), time in zip(rows, times, strict=True):
            if row[column] == "--":
                missing.append(line)
                continue
            measured[time] = (line, _number(row[column]))
        if not all(t in measured for t in [3.0, 4.5, 6.0]):
            raise ValueError("Missing early kinase calibration measurement")
        (r3, f3), (r45, f45), (r6, f6) = (measured[t] for t in [3.0, 4.5, 6.0])
        velocity, curvature = (f6 - f45) / 1.5, (f6 - 2 * f45 + f3) / 2.25
        forecasts = [(time, line, value) for time, (line, value) in measured.items() if time > 7.5]
        if not forecasts:
            raise ValueError("No measured kinase forecast responses")
        summaries.append(
            {
                "column": header[column],
                "group": group,
                "missing_marker": "--",
                "missing_source_rows": sorted(missing),
                "observed_forecast_rows": len(forecasts),
                "calibration_rows": [r3, r45, r6],
            }
        )
        for time, line, response in forecasts:
            row, source = _row(
                recipe["scenario_id"],
                f"src-{label}-row{line}",
                group,
                split,
                {
                    "concentration_uM": float(label),
                    "time_min": time,
                    "calibration_F6": f6,
                    "calibration_v6": velocity,
                    "calibration_curvature": curvature,
                },
                response,
                {
                    "source": asset["path"],
                    "row": line,
                    "time_column": header[0],
                    "response_column": header[column],
                    "dose_uM": float(label),
                    "calibration_rows": [r3, r45, r6],
                    "calibration_times_min": [3.0, 4.5, 6.0],
                    "expanded_calibration": {
                        "v6": "(F6-F4.5)/1.5",
                        "curvature": "(F6-2*F4.5+F3)/2.25",
                    },
                    "calibration_precedes_forecast": 6.0 < time,
                },
            )
            parts[split].append(row)
            lineage.append(source)
    return (
        parts,
        lineage,
        {
            "split_check": check_units(parts, units),
            "curves": summaries,
            "rows_without_time_or_response": missing_times,
            "independence_scope": "Complete dose curves; biological replicate identifiers and independently repeated assays are unavailable",
            "response_scope": "Source fluorescence values; no raw optical acquisition, mechanistic identification or causal validation",
        },
    )


def reconstruct_neuronal(recipe, source_root):
    from .native import _registered_groups, _row, identity

    (asset,) = [a for a in recipe["assets"] if a["role"] == "neuronal_archive"]
    member = recipe["archive_member"]
    header = recipe["source_columns"]
    if len(header) != len(set(header)) or set(header) != {
        "filename",
        "sweep",
        "applied current",
        "spike count",
        "stimulus range",
        "Measurement ID",
        "date",
        "Stiffness",
        "div",
        "Condition",
        "dish",
        "cell",
        "frequency",
        "use for FI (manually confirmed)",
    }:
        raise ValueError("Unexpected neuronal source measurement inventory")
    with bounded_zip(
        contained(source_root, asset["path"]),
        max_bytes=10_000_000,
        max_member_bytes=5_000_000,
        max_members=256,
    ) as archive:
        native_rows = _csv_rows(archive.read(member), header)
    cells = defaultdict(list)
    for line, values in native_rows:
        item = dict(zip(header, values, strict=True))
        if (
            not item["filename"]
            or not re.fullmatch(r"20[0-9]{6}", item["date"])
            or not item["dish"]
            or not item["cell"]
        ):
            raise ValueError("Missing cell/date/dish identity")
        if item["Stiffness"] not in {"0.1kPa", "10kPa"} or item["Condition"] not in {
            "P1 KD",
            "Control",
        }:
            raise ValueError("Unrecognized neuronal experimental condition")
        quality = item["use for FI (manually confirmed)"].strip()
        if quality not in {"y", "n", ""}:
            raise ValueError("Unrecognized source quality flag")
        sweep, current, count = (
            _number(item[k]) for k in ("sweep", "applied current", "spike count")
        )
        if sweep < 0 or not sweep.is_integer() or count < 0 or not count.is_integer():
            raise ValueError("Invalid sweep identity or stored spike count")
        cells[item["filename"]].append(
            {
                "line": line,
                "metadata": item,
                "sweep": int(sweep),
                "current": current,
                "count": count,
                "quality": quality,
            }
        )
    units, grouped, source_cells = {}, {}, {}
    for cell, records in cells.items():
        metadata = {
            tuple(r["metadata"][k] for k in ["date", "dish", "cell", "Stiffness", "Condition"])
            for r in records
        }
        if len(metadata) != 1 or len({r["sweep"] for r in records}) != len(records):
            raise ValueError("Ambiguous cell linkage or repeated sweep identity")
        date, dish, native_cell, stiffness, condition = next(iter(metadata))
        entry = source_cells.setdefault(
            (date, dish, native_cell), {"condition": (stiffness, condition), "recordings": []}
        )
        if entry["condition"] != (stiffness, condition):
            raise ValueError("Repeated cell recordings have inconsistent conditions")
        entry["recordings"].append(cell)
        grouped[cell] = date + ":" + dish
    assignments = _registered_groups(recipe, set(grouped.values()))
    final_date = max(r["metadata"]["date"] for rows in cells.values() for r in rows)
    if any(
        (group.split(":", 1)[0] == final_date) != (split == "test")
        for group, split in assignments.items()
    ):
        raise ValueError("Neuronal test partition must retain the complete final recording date")
    parts, lineage, summaries = {p: [] for p in ("train", "dev", "test")}, [], []
    for cell, records in sorted(cells.items()):
        records.sort(key=lambda r: r["sweep"])
        group = grouped[cell]
        split = assignments[group]
        units[identity(recipe["scenario_id"], "group", group)] = group
        calibration = [r for r in records if r["current"] <= 10]
        future = [r for r in records if r["current"] > 10 and r["quality"] == "y"]
        if (
            not calibration
            or not future
            or any(r["quality"] != "y" for r in calibration)
            or max(r["sweep"] for r in calibration) >= min(r["sweep"] for r in future)
        ):
            raise ValueError(
                "Calibration is missing, unapproved or not a strictly preceding sweep prefix"
            )
        cal_mean = float(np.mean([r["count"] for r in calibration]))
        cal_last = calibration[-1]["count"]
        summaries.append(
            {
                "recording": cell,
                "cell": records[0]["metadata"]["cell"],
                "dish_group": group,
                "calibration_sweeps": [r["sweep"] for r in calibration],
                "calibration_rows": [r["line"] for r in calibration],
                "forecast_rows": len(future),
                "excluded_by_source_quality_rows": [
                    r["line"] for r in records if r["quality"] != "y"
                ],
            }
        )
        for r in future:
            metadata = r["metadata"]
            row, source = _row(
                recipe["scenario_id"],
                f"{cell}:sweep{r['sweep']}",
                group,
                split,
                {
                    "current": r["current"],
                    "soft": float(metadata["Stiffness"] == "0.1kPa"),
                    "kd": float(metadata["Condition"] == "P1 KD"),
                    "cal_mean": cal_mean,
                    "cal_last": cal_last,
                },
                r["count"],
                {
                    "source": asset["path"],
                    "member": member,
                    "row": r["line"],
                    "response_column": "spike count",
                    "recording": cell,
                    "cell": metadata["cell"],
                    "sweep": r["sweep"],
                    "dish_group": group,
                    "calibration_rows": [v["line"] for v in calibration],
                    "calibration_sweeps": [v["sweep"] for v in calibration],
                    "calibration_current_threshold_pA": 10,
                    "calibration_precedes_forecast": True,
                    "expanded_calibration": {
                        "cal_mean": "arithmetic mean of preceding <=10 pA counts",
                        "cal_last": "last preceding <=10 pA count",
                    },
                    "quality": "Author-marked y; no new response-based filtering",
                },
            )
            parts[split].append(row)
            lineage.append(source)
    return (
        parts,
        lineage,
        {
            "split_check": check_units(parts, units),
            "recordings": summaries,
            "source_cell_count": len(source_cells),
            "test_recording_date": final_date,
            "repeated_cell_recordings": [
                {"date": k[0], "dish": k[1], "cell": k[2], "recordings": v["recordings"]}
                for k, v in sorted(source_cells.items())
                if len(v["recordings"]) > 1
            ],
            "independence_scope": "Whole culture dishes within recording dates; repeated sweeps/cells in one dish are not independent experimental units",
            "response_scope": "Author-derived spike counts and manual source quality flags; voltage recordings and spike detector independently unverified",
        },
    )
