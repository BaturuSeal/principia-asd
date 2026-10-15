"""Historical fermentation reconstruction with explicit, non-repairing clock audit.

The published nominal cultivation clock differs from some acquisition timestamps.
Keep this diagnostic reconstruction separate from a future corrected task contract.
"""

import re
from collections import Counter, defaultdict
from datetime import datetime

import numpy as np

from ..io import contained
from .curves import _csv_rows, _number
from .splits import check_units


def reconstruct_fermentation(recipe, source_root):
    from .native import _registered_groups, _row, identity

    (asset,) = [a for a in recipe["assets"] if a["role"] == "fermentation_history"]
    header = recipe["source_columns"]
    if len(header) != len(set(header)) or not {"date", "batch_id", "hh", "hx"} <= set(header):
        raise ValueError("Ambiguous fermentation measurement columns")
    batches = defaultdict(list)
    for line, values in _csv_rows(contained(source_root, asset["path"]).read_bytes(), header):
        row = dict(zip(header, values, strict=True))
        if not re.fullmatch(r"[1-9][0-9]*", row["batch_id"]):
            raise ValueError("Unresolved source batch identity")
        try:
            stamp = datetime.strptime(row["date"], "%Y/%m/%d %H:%M")
        except ValueError as exc:
            raise ValueError("Invalid source acquisition timestamp") from exc
        hh, value = _number(row["hh"]), _number(row["hx"])
        if hh < 0:
            raise ValueError("Negative source cultivation clock")
        batches[row["batch_id"]].append({"row": line, "time": hh, "value": value, "stamp": stamp})
    observations, summaries, repeated_clocks = [], [], []
    for group, raw in batches.items():
        if any(b["stamp"] <= a["stamp"] for a, b in zip(raw, raw[1:], strict=False)):
            raise ValueError("Duplicate or reversed fermentation acquisition timestamps")
        # Match the original pandas single-key default argsort, including clock ties.
        # Exact NumPy and reader bindings are required for historical replay.
        indexes = np.argsort(np.asarray([r["time"] for r in raw]), kind="quicksort")
        rows = [raw[int(i)] for i in indexes]
        ties = defaultdict(list)
        for row in raw:
            ties[row["time"]].append(row["row"])
        repeated_clocks.extend(
            {"batch": group, "nominal_hh": t, "source_rows": lines}
            for t, lines in ties.items()
            if len(lines) > 1
        )
        eligible, excluded = 0, []
        for j in range(6, len(rows) - 6):
            past, current, future = rows[j - 6], rows[j], rows[j + 6]
            if current["time"] - past["time"] != 6 or future["time"] - current["time"] != 6:
                excluded.append(current["row"])
                continue
            observations.append((group, past, current, future))
            eligible += 1
        summaries.append(
            {
                "batch": group,
                "source_rows": len(raw),
                "eligible_rows": eligible,
                "start": raw[0]["stamp"].isoformat(),
                "end": raw[-1]["stamp"].isoformat(),
                "excluded_origins_without_nominal_six_row_windows": excluded,
                "boundary_source_rows": [
                    r["row"] for i, r in enumerate(rows) if i < 6 or i >= len(rows) - 6
                ],
            }
        )
    assignments = _registered_groups(recipe, {g for g, *_ in observations})
    parts, lineage, units = {p: [] for p in ("train", "dev", "test")}, [], {}
    lag_counts, horizon_counts, violations = Counter(), Counter(), []
    calendars = defaultdict(lambda: {"starts": [], "origins": [], "targets": []})
    for batch in summaries:
        if batch["eligible_rows"]:
            calendars[assignments[batch["batch"]]]["starts"].append(batch["start"])
    for index, (group, past, current, future) in enumerate(observations):
        split = assignments[group]
        units[identity(recipe["scenario_id"], "group", group)] = group
        lag = int((current["stamp"] - past["stamp"]).total_seconds())
        horizon = int((future["stamp"] - current["stamp"]).total_seconds())
        lag_counts[lag] += 1
        horizon_counts[horizon] += 1
        row, source = _row(
            recipe["scenario_id"],
            f"P100-086-{index:07}",
            group,
            split,
            {
                "time_h": current["time"],
                "current": current["value"],
                "slope6": (current["value"] - past["value"]) / 6,
            },
            future["value"],
            {
                "source": asset["path"],
                "past_row": past["row"],
                "origin_row": current["row"],
                "target_row": future["row"],
                "batch": group,
                "origin_timestamp": current["stamp"].isoformat(),
                "lag_seconds": lag,
                "horizon_seconds": horizon,
            },
        )
        parts[split].append(row)
        lineage.append(source)
        calendars[split]["origins"].append(current["stamp"].isoformat())
        calendars[split]["targets"].append(future["stamp"].isoformat())
        if lag != 21600 or horizon != 21600:
            violations.append(
                {
                    "sample_id": row["sample_id"],
                    "split": split,
                    "past_row": past["row"],
                    "origin_row": current["row"],
                    "target_row": future["row"],
                    "lag_seconds": lag,
                    "horizon_seconds": horizon,
                }
            )
    boundaries = []
    for earlier, later in [("train", "dev"), ("dev", "test"), ("train", "test")]:
        left, right = calendars[earlier], calendars[later]
        if not left["starts"] or not right["starts"]:
            raise ValueError("Empty fermentation partition")
        boundaries.append(
            {
                "earlier": earlier,
                "later": later,
                "batch_starts_strictly_ordered": max(left["starts"]) < min(right["starts"]),
                "all_targets_before_next_origins": max(left["targets"]) < min(right["origins"]),
                "latest_earlier_batch_start": max(left["starts"]),
                "earliest_later_batch_start": min(right["starts"]),
                "latest_earlier_target": max(left["targets"]),
                "earliest_later_origin": min(right["origins"]),
            }
        )
    blockers = []
    if violations:
        blockers.append(
            "Nominal six-hour rows include different timestamp horizons; requires a new reviewed task contract/cohort"
        )
    if any(not r["batch_starts_strictly_ordered"] for r in boundaries):
        blockers.append("Development batches are not chronologically separated")
    if any(not r["all_targets_before_next_origins"] for r in boundaries):
        blockers.append(
            "Acquisition windows overlap; batch-start ordering is not strict prospective time separation"
        )
    return (
        parts,
        lineage,
        {
            "split_check": check_units(parts, units),
            "admission_blockers": blockers,
            "source_batches": summaries,
            "duplicate_nominal_clocks": repeated_clocks,
            "temporal_validation": {
                "valid": not blockers,
                "nominal_lag_and_horizon_hours": 6,
                "timestamp_lag_seconds_counts": {str(k): v for k, v in sorted(lag_counts.items())},
                "timestamp_horizon_seconds_counts": {
                    str(k): v for k, v in sorted(horizon_counts.items())
                },
                "clock_disagreement_rows": len(violations),
                "clock_disagreements": violations,
                "partition_boundaries": boundaries,
                "source_clock_ties_are_not_merged": True,
                "policy": "Historical diagnostic reconstruction; no relabeling, retiming, interpolation or silent cohort repair",
            },
            "response_scope": "Published hx potency values, original units undocumented; conditional on observed potency assays, not a validated inline soft sensor",
            "independence_scope": "Whole production batches at one facility; calendar overlap and shared production conditions preclude an independent-batch scientific claim",
        },
    )
