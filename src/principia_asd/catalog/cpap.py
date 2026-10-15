"""Curator-only raw ADC reconstruction; no physiological or clinical inference.

The historical task uses fixed sample offsets, with two clock-tolerance gates.
Actual timestamps, padding, repeated clocks and acquisition anomalies stay visible.
No smoothing, resampling, peak detection, fitted calibration or flow model is used.
"""

import csv
import io
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np

from ..io import contained, sha
from .splits import check_units

SOURCE_URL = "https://www.physionet.org/content/respiratory-heartrate-dataset/1.0.0/"
TRIALS = {"PEEP", "PEEP_BH", "FEM"}
HELD = {"Subject1", "Subject4", "Subject5", "Subject7", "Subject20"}
LAGS = {"p0": 0, "p05": 5, "p10": 10, "p20": 20, "p30": 30, "p40": 40, "p50": 50}
INPUT_UNITS = {
    **dict.fromkeys([*LAGS, "di0", "de0", "di20", "de20"], "cmH2O"),
    "trial_BH": "binary",
    "trial_FEM": "binary",
}
HEADER = [
    "Time [s]",
    "Gauge Pressure",
    "Inspiratory Differential Pressure",
    "Expiratory Differential Pressure",
    "StartTime",
]


def adc_pressure(adc):
    """Published source conversion: 14-bit, 10–90% transfer, ±1 psi to cmH2O."""
    return ((np.asarray(adc, dtype=float) - 0.1 * 2**14) / (0.8 * 2**14 / 2) - 1) * 70.306957829636


def stored_trace(raw, name):
    match = re.fullmatch(r"(Subject(?:[1-9]|1[0-9]|20))_(PEEP|PEEP_BH|FEM)_raw.csv", name)
    if not match or len(raw) > 2_000_000:
        raise ValueError("Unknown or oversized CPAP acquisition")
    records = list(csv.reader(io.StringIO(raw.decode("utf-8-sig")), strict=True))
    if not records or [x.strip() for x in records[0]] != HEADER:
        raise ValueError("Unexpected CPAP columns or measurement units")
    records = records[1:]
    if not 122 <= len(records) <= 40_000 or any(len(r) != 5 for r in records):
        raise ValueError("CPAP row count or source shape differs")
    if not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]", records[0][4]):
        raise ValueError("Missing or invalid source StartTime")
    if any(r[4] for r in records[1:]):
        raise ValueError("Unexpected repeated StartTime or hidden state")
    try:
        a = np.array([[float(x) if x.strip() else np.nan for x in r[:4]] for r in records])
    except ValueError as exc:
        raise ValueError("Nonnumeric CPAP measurement") from exc
    t, adc = a[:, 0], a[:, 1:]
    if not np.isfinite(t).all() or np.isinf(adc).any():
        raise ValueError("Invalid CPAP clock or infinite ADC")
    finite = adc[np.isfinite(adc)]
    if np.any(finite != np.floor(finite)) or np.any((finite < 0) | (finite > 1_000_000)):
        raise ValueError("Noninteger or unbounded ADC data")
    valid = np.flatnonzero(t >= 0)
    if not len(valid):
        raise ValueError("No CPAP acquisition interval")
    end = int(valid[-1])
    if t[0] != 0 or np.any(t[: end + 1] < 0) or np.any(np.diff(t[: end + 1]) < 0):
        raise ValueError("Nonmonotone or ambiguous CPAP acquisition clock")
    if len(t[end + 1 :]) and (
        not np.all(t[end + 1 :] == t[end + 1]) or not np.all(adc[end + 1 :] == 0)
    ):
        raise ValueError("Negative-clock tail is not empty source padding")
    outside = np.argwhere((adc < 0) | (adc > 16383))
    summary = {
        "name": name,
        "participant": match[1],
        "trial": match[2],
        "native_rows": len(a),
        "last_acquired_row": end + 2,
        "padding_rows": len(a) - end - 1,
        "repeated_clock_intervals": int(np.sum(np.diff(t[: end + 1]) == 0)),
        "missing_adc_cells": int(np.sum(np.isnan(adc))),
        "out_of_14bit_cells": [
            {"row": int(k + 2), "column": int(c + 2), "value": float(adc[k, c])} for k, c in outside
        ],
        "clock_scope": "Native computer-clock seconds, not a uniform 100Hz time axis",
    }
    return t, adc_pressure(adc), summary


def eligible_origins(t, pressure, end):
    """Preserve the existing selection exactly; report every rejected origin."""
    accepted, excluded = [], []
    for j in range(100, end - 20, 100):
        indices = [j, j - 5, j - 10, j - 20, j - 30, j - 40, j - 50, j + 20]
        reason = None
        if not np.isfinite(pressure[indices]).all():
            reason = "nonfinite_selected_pressure"
        elif abs((t[j + 20] - t[j]) - 0.2) > 0.025:
            reason = "future_clock_tolerance"
        elif abs((t[j] - t[j - 50]) - 0.5) > 0.025:
            reason = "past_clock_tolerance"
        if reason:
            excluded.append({"origin_row": j + 2, "reason": reason})
        else:
            if np.any(t[np.array(indices[:-1])] > t[j]) or t[j + 20] <= t[j]:
                raise ValueError("Future information or nonpositive forecast interval")
            accepted.append(j)
    return accepted, excluded


def original_assignments(case):
    from .native import identity

    groups = {f"Subject{k}" for k in range(1, 21)}
    ordered = sorted(
        groups - HELD, key=lambda g: sha(["compact-v2", case, identity(case, "group", g)])
    )
    dev = set(ordered[:3])
    return {g: "test" if g in HELD else "dev" if g in dev else "train" for g in sorted(groups)}


def reconstruct_cpap(recipe, source_root):
    from .native import _registered_groups, _row, _unique_object, identity

    def asset(role):
        (result,) = [a for a in recipe["assets"] if a["role"] == role]
        return result

    meta = json.loads(
        contained(source_root, asset("source_metadata")["path"]).read_bytes(),
        object_pairs_hook=_unique_object,
    )
    readme = contained(source_root, asset("source_readme")["path"]).read_text()
    calibration = contained(source_root, asset("source_calibration")["path"]).read_text()
    required = ("P_max = 1;", "P_min = -1;", "0.1*(2^14)", "0.8*(2^14)", "70.306957829636")
    if (
        meta["source_url"] != SOURCE_URL
        or meta["source_version"] != "1.0.0; 2024-03-20"
        or "raw ADC counts" not in readme
        or not all(x in calibration for x in required)
        or recipe["input_units"] != INPUT_UNITS
        or recipe["output_units"] != "cmH2O"
    ):
        raise ValueError("CPAP identity, calibration or unit policy differs")
    sources = sorted(
        (a for a in recipe["assets"] if a["role"] == "raw_pressure"), key=lambda a: a["path"]
    )
    names = [Path(a["path"]).name for a in sources]
    expected = {f"Subject{k}_{trial}_raw.csv" for k in range(1, 21) for trial in TRIALS}
    if len(names) != 60 or set(names) != expected:
        raise ValueError("Incomplete or duplicate CPAP participant/trial panel")
    assignments = _registered_groups(recipe, {f"Subject{k}" for k in range(1, 21)})
    if assignments != original_assignments(recipe["scenario_id"]):
        raise ValueError("Historical CPAP participant allocation changed")
    parts, lineage, traces, units = {p: [] for p in ("train", "dev", "test")}, [], [], {}
    horizons, short_lags, input_anomalies, target_anomalies = [], [], [], []
    for trace_index, source in enumerate(sources):
        t, pressure, info = stored_trace(
            contained(source_root, source["path"]).read_bytes(), names[trace_index]
        )
        end = info["last_acquired_row"] - 2
        origins, excluded = eligible_origins(t, pressure, end)
        group, trial = info["participant"], info["trial"]
        split = assignments[group]
        info.update(
            {
                "source": source["path"],
                "split": split,
                "retained_origins": len(origins),
                "excluded_origins": excluded,
            }
        )
        traces.append(info)
        units[identity(recipe["scenario_id"], "group", group)] = group
        anomalous = {(c["row"], c["column"]) for c in info["out_of_14bit_cells"]}
        for j in origins:
            values = {k: float(pressure[j - lag, 0]) for k, lag in LAGS.items()}
            values.update(
                di0=float(pressure[j, 1]),
                de0=float(pressure[j, 2]),
                di20=float(pressure[j - 20, 1]),
                de20=float(pressure[j - 20, 2]),
                trial_BH=float(trial == "PEEP_BH"),
                trial_FEM=float(trial == "FEM"),
            )
            feature_cells = {(j - lag + 2, 2) for lag in LAGS.values()} | {
                (j - lag + 2, c) for lag in (0, 20) for c in (3, 4)
            }
            if anomalous & feature_cells:
                input_anomalies.append({"trace_index": trace_index, "origin_row": j + 2})
            if (j + 22, 2) in anomalous:
                target_anomalies.append({"trace_index": trace_index, "origin_row": j + 2})
            row, origin = _row(
                recipe["scenario_id"],
                Path(names[trace_index]).stem + f":row{j + 2}",
                group,
                split,
                values,
                pressure[j + 20, 0],
                {"trace_index": trace_index, "origin_row": j + 2, "target_row": j + 22},
            )
            parts[split].append(row)
            lineage.append(origin)
            horizons.append(float(t[j + 20] - t[j]))
            short_lags.append(float(t[j] - t[j - 5]))
    if not horizons:
        raise ValueError("No eligible CPAP origins")
    return (
        parts,
        lineage,
        {
            "split_check": check_units(parts, units),
            "traces": traces,
            "lineage_definition": {
                "trace_index": "Zero-based index into checks.traces, each binding a registered source path",
                "source_rows": "One-based physical CSV rows including the header",
                "input_cells": {
                    **{k: {"row_offset_from_origin": -lag, "column": 2} for k, lag in LAGS.items()},
                    "di0": {"row_offset_from_origin": 0, "column": 3},
                    "de0": {"row_offset_from_origin": 0, "column": 4},
                    "di20": {"row_offset_from_origin": -20, "column": 3},
                    "de20": {"row_offset_from_origin": -20, "column": 4},
                },
                "trial_flags": "Exact trial token in the registered source filename; no inferred respiratory phase",
                "target_column": 2,
                "clock_column": 1,
                "calibration": "((ADC - 0.1*2**14)/(0.8*2**14/2) - 1)*70.306957829636",
            },
            "cpap_validation": {
                "participants": len(assignments),
                "trials": len(traces),
                "native_rows": sum(r["native_rows"] for r in traces),
                "padding_rows": sum(r["padding_rows"] for r in traces),
                "repeated_clock_intervals": sum(r["repeated_clock_intervals"] for r in traces),
                "eligible_origins": len(horizons),
                "excluded_origins": sum(len(r["excluded_origins"]) for r in traces),
                "group_counts": dict(Counter(assignments.values())),
                "actual_horizon_s": [min(horizons), max(horizons)],
                "actual_five_sample_lag_s": [min(short_lags), max(short_lags)],
                "out_of_14bit_cells": sum(len(r["out_of_14bit_cells"]) for r in traces),
                "input_origins_with_adc_anomalies": input_anomalies,
                "target_origins_with_adc_anomalies": target_anomalies,
                "past_timestamps_not_after_origin": True,
                "fit_count": 0,
                "learned_calibrations": 0,
            },
            "admission_blockers": [
                "Nominal sample delays and 200ms horizon are clock-tolerance based, not exact fixed physical delays",
                "Within-trial origins share history; prior observations from held-out participants are permitted online inputs",
                "Source ADC calibration is fixed, but instrument uncertainty and physiological identifiability remain unassessed",
                "Final rights, scientific contract and valid measurement perturbations require review; no clinical claim",
                "Historical complexity excludes upstream ADC conversion; full-pipeline simplicity is unassessed",
            ],
        },
    )
