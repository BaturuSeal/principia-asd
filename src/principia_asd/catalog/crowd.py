"""Past-only trajectory measurements for the historical crowd-condition task.

Only Time, Id-Ped, X and Y are decoded. Supplied velocity/polarization, author
summaries and future membership never enter a prediction. Track IDs are local
to each recording and cannot establish independent physical participants.
"""

import hashlib
import re
import warnings
from collections import Counter, defaultdict

import numpy as np

from ..io import contained
from .curves import _csv_rows, _number
from .fracture import bounded_zip
from .splits import check_units

HEADERS = {
    "m": ["Time(s)", "Id-Ped", "X(m)", "Y(m)", "VX(m/s)", "VY(m/s)", "Pol"],
    "cm": ["Time(s)", "Id-Ped", "X(cm)", "Y(cm)", "VX(cm/s)", "VY(cm/s)", "Pol"],
}


def recording_group(name):
    match = re.fullmatch(
        r"ExperimentalData/(Spain/A[1-9][0-9]*|Japan/C[1-9][0-9]*|Kids/D[1-9][0-9]*)/[1-9][0-9]*\.csv",
        name,
    )
    if match:
        return match[1]
    match = re.fullmatch(r"ExperimentalData/(Teenagers/B[1-9][0-9]*)\.csv", name)
    if match:
        return match[1]
    raise ValueError("Unregistered crowd recording path or condition identity")


def decode_trajectory(raw):
    if len(raw) > 20_000_000:
        raise ValueError("Oversized crowd trajectory")
    first = raw.splitlines()[0].decode("utf-8-sig").split(",") if raw else []
    units = [u for u, header in HEADERS.items() if first == header]
    if len(units) != 1:
        raise ValueError("Unexpected trajectory schema or units")
    unit = units[0]
    rows = _csv_rows(raw, HEADERS[unit])
    if len(rows) > 250_000:
        raise ValueError("Crowd trajectory exceeds bounded source row count")
    # Source quantities 4..6 remain uninterpreted, including any missing values.
    data = np.asarray([[_number(v) for v in values[:4]] for _, values in rows])
    if (
        np.any(data[:, 0] < 0)
        or np.any(data[:, 1] <= 0)
        or np.any(data[:, 1] != np.floor(data[:, 1]))
    ):
        raise ValueError("Invalid crowd timestamp or track identity")
    if np.any(data[:, 1] > 2**31 - 1):
        raise ValueError("Unbounded crowd track identity")
    lines = np.asarray([line for line, _ in rows], dtype=np.int64)
    order = np.lexsort((data[:, 0], data[:, 1]))
    data, lines = data[order], lines[order]
    if len(data) > 1 and np.any((np.diff(data[:, 1]) == 0) & (np.diff(data[:, 0]) <= 0)):
        raise ValueError("Duplicate or ambiguous per-track acquisition clock")
    if unit == "cm":
        data[:, 2:4] /= 100
    return data, lines, unit


def synchronized_positions(data, lines):
    start, stop = int(np.ceil(data[:, 0].min())), int(np.floor(data[:, 0].max()))
    ids = np.unique(data[:, 1]).astype(np.int64)
    frames = max(0, stop - start + 1)
    if frames > 86_401 or len(ids) > 2048 or frames * len(ids) > 2_000_000:
        raise ValueError("Crowd synchronization exceeds bounded frame/track allocation")
    grid = np.arange(start, stop + 1)
    x = np.full((len(grid), len(ids)), np.nan)
    y = x.copy()
    sources = np.zeros(x.shape, dtype=np.int64)
    max_age = 0.0
    for j, pid in enumerate(ids):
        mask = data[:, 1] == pid
        track, source = data[mask], lines[mask]
        k = np.searchsorted(track[:, 0], grid, side="right") - 1
        age = grid - track[np.maximum(k, 0), 0]
        valid = (k >= 0) & (age <= 1.0)
        if np.any(age[valid] < 0):
            raise ValueError("Future crowd measurement selected")
        if np.any(valid):
            max_age = max(max_age, float(age[valid].max()))
        x[valid, j], y[valid, j] = track[k[valid], 2], track[k[valid], 3]
        sources[valid, j] = source[k[valid]]
    return grid, ids, x, y, sources, max_age


def measured_statistics(x, y):
    # The empty first velocity frame and untrackable geometry are recorded by
    # the eligibility inventory. They are not imputed or treated as zeros.
    with warnings.catch_warnings(), np.errstate(invalid="ignore", divide="ignore"):
        warnings.simplefilter("ignore", RuntimeWarning)
        rx, ry = x - np.nanmean(x, axis=1)[:, None], y - np.nanmean(y, axis=1)[:, None]
        vx = np.vstack([np.full((1, x.shape[1]), np.nan), np.diff(x, axis=0)])
        vy = np.vstack([np.full((1, y.shape[1]), np.nan), np.diff(y, axis=0)])
        speed, radius = np.sqrt(vx * vx + vy * vy), np.sqrt(rx * rx + ry * ry)
        valid = (speed > 1e-3) & (radius > 1e-3)
        spin = np.divide(
            rx * vy - ry * vx, radius * speed, out=np.full_like(radius, np.nan), where=valid
        )
        polar = np.nanmean(spin, axis=1)
        return {
            "polar": polar,
            "variance": np.nanvar(spin, axis=1),
            "radius90": np.nanquantile(radius, 0.9, axis=1),
            "speed": np.nanmean(speed, axis=1),
            "count": np.sum(np.isfinite(x) & np.isfinite(y), axis=1),
            "initial": float(np.nanmean(polar[1:3])),
        }


def reconstruct_crowd(recipe, source_root):
    from .native import _registered_groups, _row, identity

    (asset,) = [a for a in recipe["assets"] if a["role"] == "crowd_trajectories"]
    parts, lineage, inventory, omitted = {p: [] for p in ("train", "dev", "test")}, [], [], []
    groups, units, units_counts = defaultdict(list), {}, Counter()
    with bounded_zip(
        contained(source_root, asset["path"]), max_bytes=180_000_000, max_member_bytes=20_000_000
    ) as archive:
        names = sorted(
            n
            for n in archive.namelist()
            if n.endswith(".csv")
            and "__MACOSX" not in n
            and "/Individual/" not in n
            and len(n.split("/")) in (3, 4)
        )
        if names != recipe["crowd_members"]:
            raise ValueError("Missing, new or unregistered crowd recording")
        for name in names:
            groups[recording_group(name)].append(name)
        assignments = _registered_groups(recipe, groups)
        for index, name in enumerate(names):
            raw = archive.read(name)
            data, lines, unit = decode_trajectory(raw)
            grid, ids, x, y, sources, max_age = synchronized_positions(data, lines)
            group, count = recording_group(name), 0
            split = assignments[group]
            units[identity(recipe["scenario_id"], "group", group)] = group
            units_counts[unit] += 1
            stats = measured_statistics(x, y) if len(grid) else None
            for t in range(4, len(grid) - 2, 2):
                values = [
                    np.mean(stats["polar"][t + 1 : t + 3]),
                    stats["polar"][t],
                    np.mean(stats["polar"][t - 1 : t + 1]),
                    stats["initial"],
                    stats["count"][t] / (np.pi * stats["radius90"][t] ** 2),
                    stats["speed"][t],
                    stats["radius90"][t],
                    stats["variance"][t],
                ]
                if not np.isfinite(values).all():
                    omitted.append(
                        {
                            "recording_index": index,
                            "origin_index": t,
                            "origin_seconds": int(grid[t]),
                            "reason": "nonfinite_history_geometry_or_two_second_response",
                            "nonfinite_value_indices": np.flatnonzero(
                                ~np.isfinite(values)
                            ).tolist(),
                        }
                    )
                    continue
                row, anchor = _row(
                    recipe["scenario_id"],
                    name + ":origin=" + str(int(grid[t])),
                    group,
                    split,
                    dict(
                        zip(
                            (
                                "p_now",
                                "p_past",
                                "p_initial",
                                "density",
                                "speed",
                                "radius90",
                                "polarization_variance",
                            ),
                            map(float, values[1:]),
                            strict=True,
                        )
                    ),
                    float(values[0]),
                    {
                        "recording_index": index,
                        "origin_index": t,
                        "origin_seconds": int(grid[t]),
                        "target_grid_indices": [t + 1, t + 2],
                    },
                )
                parts[split].append(row)
                lineage.append(anchor)
                count += 1
            inventory.append(
                {
                    "member": name,
                    "member_sha256": hashlib.sha256(raw).hexdigest(),
                    "group": group,
                    "split": split,
                    "source_rows": len(data),
                    "source_position_unit": unit,
                    "track_ids": ids.tolist(),
                    "grid_start_seconds": int(grid[0]) if len(grid) else None,
                    "grid_step_seconds": 1,
                    "frames": len(grid),
                    "source_time_range": [float(data[:, 0].min()), float(data[:, 0].max())],
                    "grid_source_rows": sources.tolist(),
                    "missing_source_row_sentinel": 0,
                    "max_held_sample_age_seconds": max_age,
                    "task_rows": count,
                    "no_task_rows_reason": "no_full_window_after_four_second_prefix"
                    if len(grid) < 7
                    else "all_windows_nonfinite"
                    if not count
                    else None,
                }
            )
    return (
        parts,
        lineage,
        {
            "split_check": check_units(parts, units),
            "measurement_asset": asset["path"],
            "recordings": inventory,
            "excluded_origins": omitted,
            "lineage_interpretation": "Grid source rows are 1-based native CSV lines, columns follow track_ids; zero denotes unavailable or >1 s stale. Each rule input uses grid rows <= origin_index; p_past/backward velocity use t-2..t, initial calibration uses frames 0..2; response uses t+1..t+2. No XY values or test responses are exported in lineage.",
            "crowd_validation": {
                "recordings": len(inventory),
                "source_position_rows": sum(r["source_rows"] for r in inventory),
                "file_qualified_tracks": sum(len(r["track_ids"]) for r in inventory),
                "conditions": len(groups),
                "source_unit_counts": dict(units_counts),
                "excluded_origins": len(omitted),
                "recordings_without_eligible_windows": [
                    r["member"] for r in inventory if not r["task_rows"]
                ],
                "duplicate_track_timestamps": 0,
                "selected_future_measurements": 0,
                "supplied_velocity_polarization_or_summary_used": False,
                "future_track_membership_used_in_predictors": False,
                "source_position_scope": "Author-released tracking coordinates, not independent video decoding; smoothing/annotation latency unverified",
                "independence_scope": "Whole country/condition groups and all recording repeats kept together; track IDs are recording-local and do not establish participant independence across conditions; one teen condition has no held-teen generalization",
                "forecast_scope": "Conditional next-two-second order from observed trajectory prefix, not causal identification or free-running crowd simulation",
            },
            "admission_blockers": [
                "Confirm tracking/preprocessing provenance, participant reuse and experiment-to-recording correspondence",
                "Complete source rights, notices and scientific contract admission",
            ],
        },
    )
