"""Bounded Basytec source reconstruction with causal rest-prefix measurements."""

import math
from collections import Counter

import numpy as np

from ..io import contained
from .splits import check_units

GITT = "DLR__LiGrHydra0b__20221114__GITT__25degC__Basytec.txt"
COLUMNS = "~Time[h] DataSet t-Set[h] Line Command U[V] I[A] Ah[Ah/kg] Ah-Charge Ah-Discharge Ah-Step Ah-Step[Ah/kg] Ah-Set Ah-Set[Ah/kg] T1[°C] Cyc-Count State".split()


def decode_basytec(path, *, max_rows=500_000):
    if path.stat().st_size > 80_000_000:
        raise ValueError("Basytec source exceeds bounded size")
    segments, commands, last_time, last_id = [], Counter(), -math.inf, -1
    with path.open(encoding="latin1") as stream:
        header = [next(stream, "").rstrip("\r\n") for _ in range(13)]
        if (
            header[0] != "~Resultfile from Basytec Battery Test System"
            or header[12].split() != COLUMNS
        ):
            raise ValueError("Unexpected Basytec format or measurement units")
        if (
            header[3] != "~Name of Test: Hydra.0b_A_GITTOCV-001"
            or header[4] != "~Battery: Hydra.0b_A"
        ):
            raise ValueError("Unregistered battery/test identity")
        for index, line in enumerate(stream):
            fields = line.split()
            if index >= max_rows or len(fields) != 17:
                raise ValueError("Excessive or malformed Basytec record")
            time, dataset, step = float(fields[0]), int(fields[1]), int(fields[3])
            voltage, current = float(fields[5]), float(fields[6])
            command = fields[4]
            if (
                not all(math.isfinite(v) for v in (time, voltage, current))
                or time <= last_time
                or dataset <= last_id
                or time < 0
                or step < 0
            ):
                raise ValueError("Nonfinite or nonmonotone Basytec clock/sample identity")
            if command not in {"Pause", "Charge", "Discharge", "CalcOnce"}:
                raise ValueError("Unknown Basytec command")
            if not segments or segments[-1]["command"] != command:
                segments.append({"segment": len(segments) + 1, "command": command, "rows": []})
            segments[-1]["rows"].append((index + 14, time, voltage, current, step))
            commands[command] += 1
            last_time, last_id = time, dataset
    if not segments:
        raise ValueError("Empty Basytec source")
    return segments, {
        "native_rows": sum(commands.values()),
        "command_rows": dict(commands),
        "segments": len(segments),
        "cell": "Hydra.0b_A",
        "source_units": {"time": "hours", "voltage": "V", "current": "A"},
    }


def rest_groups(segments):
    retained, omitted = [], []
    for index, segment in enumerate(segments):
        if segment["command"] != "Pause":
            continue
        if not index or segments[index - 1]["command"] not in {"Charge", "Discharge"}:
            omitted.append(
                {"segment": segment["segment"], "reason": "not_after_completed_current_command"}
            )
            continue
        records = segment["rows"]
        if any(r[3] != 0 for r in records):
            raise ValueError("Declared current-free rest contains nonzero current")
        if (records[-1][1] - records[0][1]) * 3600 < 1800:
            omitted.append({"segment": segment["segment"], "reason": "rest_duration_below_1800s"})
            continue
        retained.append((segment, segments[index - 1]))
    if not retained:
        raise ValueError("No qualifying pulse/rest groups")
    return retained, omitted


def reconstruct_battery(recipe, source_root):
    from .native import _registered_groups, _row, identity

    (asset,) = [a for a in recipe["assets"] if a["role"] == "basytec_gitt_trace"]
    path = contained(source_root, asset["path"])
    if path.name != GITT:
        raise ValueError("Unregistered GITT trace")
    segments, native = decode_basytec(path)
    groups, omitted = rest_groups(segments)
    if len(groups) != recipe["qualifying_rest_groups"]:
        raise ValueError("Pulse/rest group inventory differs from registered source")
    names = [f"pulse-{rest['segment']:04d}" for rest, _ in groups]
    assignments = _registered_groups(recipe, set(names))
    cut = int(np.floor(len(groups) * 0.8))
    if {g for g, split in assignments.items() if split == "test"} != set(names[cut:]):
        raise ValueError("Original chronological confirmation groups differ")
    parts, lineage, units = {p: [] for p in ("train", "dev", "test")}, [], {}
    inventory, missed, target_errors, prefix_times = [], [], [], []
    for name, (rest, previous) in zip(names, groups, strict=True):
        records, pulse = rest["rows"], previous["rows"]
        t = (np.array([r[1] for r in records]) - records[0][1]) * 3600
        anchors = {aim: int(np.flatnonzero(t <= aim)[-1]) for aim in (10, 60, 120)}
        if not t[anchors[10]] < t[anchors[60]] < t[anchors[120]] <= 120:
            raise ValueError("Rest calibration lacks distinct causal prefix samples")
        prefix_times.append(float(t[anchors[120]]))
        split = assignments[name]
        units[identity(recipe["scenario_id"], "group", name)] = name
        source_rows = [int(r[0]) for r in records]
        inventory.append(
            {
                "group": name,
                "partition": split,
                "rest_source_rows": [source_rows[0], source_rows[-1]],
                "rest_start_hours": records[0][1],
                "rest_end_hours": records[-1][1],
                "step_numbers": sorted({r[4] for r in records}),
                "previous_command": previous["command"],
                "pulse_source_rows": [pulse[0][0], pulse[-1][0]],
                "pulse_current_range_A": [min(r[3] for r in pulse), max(r[3] for r in pulse)],
                "prefix_source_rows": {str(a): records[i][0] for a, i in anchors.items()},
                "prefix_actual_times_s": {str(a): float(t[i]) for a, i in anchors.items()},
            }
        )
        for aim in (300, 600, 1200, 1800):
            index = int(np.argmin(abs(t - aim)))
            error = abs(float(t[index]) - aim)
            if error > 15:
                missed.append(
                    {
                        "group": name,
                        "requested_horizon_s": aim,
                        "reason": "no_native_sample_within_15s",
                    }
                )
                continue
            target_errors.append(error)
            source_row = records[index][0]
            values = {
                "t": float(t[index]),
                "t60": float(t[anchors[60]]),
                "t120": float(t[anchors[120]]),
                "u60": records[anchors[60]][2],
                "u120": records[anchors[120]][2],
                "u10": records[anchors[10]][2],
                "pulse_s": (pulse[-1][1] - pulse[0][1]) * 3600,
                "current": pulse[-1][3],
            }
            row, origin = _row(
                recipe["scenario_id"],
                f"{name}-row-{source_row}",
                name,
                split,
                values,
                records[index][2],
                {"target_source_row": source_row, "rest_group": name, "requested_horizon_s": aim},
            )
            parts[split].append(row)
            lineage.append(origin)
    bounds = {
        p: {
            "first_start_hours": min(
                g["rest_start_hours"] for g in inventory if g["partition"] == p
            ),
            "last_end_hours": max(g["rest_end_hours"] for g in inventory if g["partition"] == p),
        }
        for p in parts
    }
    return (
        parts,
        lineage,
        {
            "split_check": check_units(parts, units),
            "battery_validation": {
                **native,
                "qualifying_rest_groups": len(groups),
                "omitted_rest_segments": len(omitted),
                "eligible_rows": len(lineage),
                "missing_target_horizons": len(missed),
                "maximum_target_timing_error_s": max(target_errors),
                "prefix_120_actual_time_range_s": [min(prefix_times), max(prefix_times)],
                "merged_step_number_maximum": max(len(g["step_numbers"]) for g in inventory),
                "all_retained_rests_have_zero_current": True,
                "fitting_performed": False,
            },
            "source_trace": asset["path"],
            "block_inventory": inventory,
            "omitted_rest_segments": omitted,
            "omitted_target_horizons": missed,
            "acquisition_chronology": {
                "partition_ranges": bounds,
                "train_strictly_before_dev": bounds["train"]["last_end_hours"]
                < bounds["dev"]["first_start_hours"],
                "all_development_strictly_before_test": max(
                    bounds[p]["last_end_hours"] for p in ("train", "dev")
                )
                < bounds["test"]["first_start_hours"],
                "scope": "Actual acquisition ranges; interleaved train/dev is not prospective forward validation",
            },
            "input_lineage": "Times derive from stored Time[h] minus the first rest sample, multiplied by 3600. Prefix voltages use last samples at or before 10/60/120 seconds. Current is the final measured sample of the completed previous current command, not a constant-current or integrated-charge assumption.",
            "response_scope": "Observed voltage at nearest stored sample to fixed 300/600/1200/1800 second horizons, tolerance 15 seconds",
            "independence_scope": "Consecutive rest blocks of one half-cell; block separation is not independent-cell replication. Temperature, cycle state and longer prior histories are not predictors.",
            "excluded_source_quantities": [
                "future rest voltages",
                "later POCV run",
                "charge/cycle/state counters",
                "source-fitted scientific state",
            ],
            "admission_blockers": [
                "Single-cell block dependence and interleaved development chronology require explicit task scope",
                "Resolve catalog placeholder creator metadata and package accurate source attribution",
                "Complete rights review and justified measurement-error perturbation standards",
            ],
        },
    )
