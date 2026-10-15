"""Curator-only torque-prefix reconstruction with proved same-hole history timing."""

import csv
import hashlib
import io
import json
import re
from collections import Counter, defaultdict
from datetime import datetime

import numpy as np

from ..io import contained, sha
from .fracture import bounded_zip
from .splits import check_units

PARSER = "screw-native-causal-torque-prefix-v1"
FIELDS = "run_id file_name class_value workpiece_id workpiece_date workpiece_usage workpiece_result workpiece_location scenario_condition scenario_exception".split()
STEP_NAMES = ("Finding", "Thread forming", "Pre-tightening", "Tightening 1.4")
INPUT_UNITS = {
    **dict.fromkeys(
        "early finding first_y gradient_proxy mean_past_y prev_early prev_gradient prev_y roughness".split(),
        "Nm",
    ),
    **dict.fromkeys(["has_history", "left"], "binary indicator"),
    **dict.fromkeys(["history_gap", "usage"], "cycle count"),
}


class Unavailable(ValueError):
    """A retained native acquisition cannot supply the fixed measurement window."""


def labels(raw):
    if len(raw) > 3_000_000:
        raise ValueError("Oversized native operation inventory")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8")))
    if reader.fieldnames != FIELDS:
        raise ValueError("Unexpected operation metadata columns")
    rows = list(reader)
    if not 1 <= len(rows) <= 12500:
        raise ValueError("Invalid operation inventory size")
    seen, holes, classes = set(), defaultdict(set), defaultdict(set)
    for i, r in enumerate(rows):
        if set(r) != set(FIELDS) or any(v is None for v in r.values()):
            raise ValueError("Malformed operation metadata row")
        if not re.fullmatch(r"[1-9][0-9]*", r["run_id"]) or r["run_id"] in seen:
            raise ValueError("Duplicate or invalid operation identity")
        seen.add(r["run_id"])
        if (
            r["file_name"] != f"Ch_{int(r['run_id']):012d}.json"
            or not re.fullmatch(r"[0-9]{14}", r["workpiece_id"])
            or not re.fullmatch(r"[0-9]{3}_[a-z-]+", r["class_value"])
            or r["workpiece_location"] not in {"left", "right"}
            or r["workpiece_result"] not in {"OK", "NOK"}
        ):
            raise ValueError("Invalid workpiece or source file identity")
        if not re.fullmatch(r"(?:[0-9]|1[0-9]|2[0-4])", r["workpiece_usage"]):
            raise ValueError("Invalid native reuse count")
        r["usage"] = int(r["workpiece_usage"])
        r["wallclock"] = (
            datetime.strptime(r["workpiece_date"], "%Y-%m-%d %H:%M:%S") - datetime(1970, 1, 1)
        ).total_seconds()
        r["labels_row"] = i + 2
        r["member"] = "json/" + r["class_value"] + "/" + r["file_name"]
        key = (r["workpiece_id"], r["workpiece_location"])
        if r["usage"] in holes[key]:
            raise ValueError("Duplicate same-hole reuse")
        holes[key].add(r["usage"])
        classes[r["workpiece_id"]].add(r["class_value"])
    if any(len(v) != 1 for v in classes.values()):
        raise ValueError("Workpiece spans surface conditions")
    if any(v != set(range(25)) for v in holes.values()) or any(
        (w, s) not in holes for w in classes for s in ("left", "right")
    ):
        raise ValueError("Incomplete native workpiece panel")
    return rows


def assignments(case, rows):
    from .native import identity

    by_class = defaultdict(set)
    for r in rows:
        by_class[r["class_value"]].add(r["workpiece_id"])
    held = set()
    for cl, ids in by_class.items():
        ordered = sorted(
            ids,
            key=lambda w: hashlib.sha256(
                ("principia-gpt6-pilot-v1|" + cl + "|" + w).encode()
            ).hexdigest(),
        )
        held.update(ordered[: max(1, len(ordered) // 5)])
    available = set.union(*by_class.values()) - held
    dev = set(
        sorted(available, key=lambda g: sha(["compact-v2", case, identity(case, "group", g)]))[
            : max(1, len(available) // 5)
        ]
    )
    return {
        w: "test" if w in held else "dev" if w in dev else "train"
        for w in set.union(*by_class.values())
    }


def decode(raw, op):
    from .native import _unique_object

    if len(raw) > 1_500_000:
        raise ValueError("Oversized native screw record")
    d = json.loads(
        raw,
        object_pairs_hook=_unique_object,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON constant")),
    )
    if (
        d["format"] != "channel"
        or d["torque unit"] != "Nm"
        or d["MCE factor"] != 1
        or d["MCE"] != [{"Transducer function": "primary", "measuring": "direct", "factor": 1}]
    ):
        raise ValueError("Unexpected native torque units or calibration")
    if any(
        str(d[k]) != op[v]
        for k, v in [
            ("cycle", "run_id"),
            ("id code", "workpiece_id"),
            ("date", "workpiece_date"),
            ("result", "workpiece_result"),
        ]
    ):
        raise ValueError("Native JSON and labels identity mismatch")
    steps = d["tightening steps"]
    if not steps or len(steps) > 4 or tuple(s["name"] for s in steps) != STEP_NAMES[: len(steps)]:
        raise ValueError("Duplicate or out-of-order native steps")
    arrays, points, repeated = {}, 0, 0
    for s in steps:
        g = s["graph"]
        columns = [g[k + " values"] for k in ("angle", "torque", "time")]
        if (
            any(not isinstance(c, list) or not 1 <= len(c) <= 2000 for c in columns)
            or len({len(c) for c in columns}) != 1
        ):
            raise ValueError("Malformed native graph shape")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) for c in columns for v in c):
            raise ValueError("Nonnumeric native measurement")
        a = np.asarray(columns, float)
        if not np.isfinite(a).all() or np.any(a[2] < 0) or np.any(np.diff(a[2]) < 0):
            raise ValueError("Invalid acquisition values or clock")
        arrays[s["name"]] = a
        points += a.shape[1]
        repeated += int(np.sum(np.diff(a[2]) == 0))
    duration = float(d["total time"])
    if not np.isfinite(duration) or duration < 0:
        raise ValueError("Invalid operation duration")
    duration = max(duration, max(float(a[2].max()) for a in arrays.values()))
    return arrays, duration, points, repeated


def forward(a):
    if a.shape[1] < 10:
        raise Unavailable("malformed_graph")
    keep = np.r_[True, a[0, 1:] > np.maximum.accumulate(a[0])[:-1]]
    idx = np.flatnonzero(keep)
    x = a[0, keep] - a[0, 0]
    return x, a[1, keep], a[2, keep], idx


def mean_window(x, y, lo, hi):
    if x[-1] < hi:
        raise Unavailable("insufficient_angle_coverage")
    xx = np.r_[lo, x[(x > lo) & (x < hi)], hi]
    if len(xx) < 4 or np.diff(xx).max() > 35:
        raise Unavailable("sparse_angle_window")
    return float(np.trapezoid(np.interp(xx, x, y), xx) / (hi - lo))


def measurements(arrays):
    if "Thread forming" not in arrays:
        raise Unavailable("missing_thread_forming")
    a = arrays["Thread forming"]
    crossings = np.flatnonzero(a[0] - a[0, 0] >= 250)
    if not len(crossings):
        raise Unavailable("insufficient_angle_coverage")
    trigger = int(crossings[0])
    px, py, pt, _ = forward(a[:, : trigger + 1])
    fx, fy, ft, _ = forward(arrays["Finding"])
    x, y, t, idx = forward(a)
    if fx[-1] <= 0 or arrays["Finding"][2].max() > pt[-1] + 1e-9:
        raise ValueError("Finding unavailable at prediction trigger")
    values = {
        "early": mean_window(px, py, 0, 250),
        "finding": float(np.trapezoid(fy, fx) / fx[-1]),
        "gradient_proxy": mean_window(px, py, 100, 250) - mean_window(px, py, 0, 100),
        "roughness": float(np.std(py[px <= 250])),
    }
    response = mean_window(x, y, 700, 1300)
    last = int(np.searchsorted(x, 1300))
    timing = {
        "trigger_index": trigger,
        "target_end_index": int(idx[last]),
        "trigger_s": float(pt[-1]),
        "target_end_s": float(t[last]),
        "trigger_latency_s": float(pt[-1] - np.interp(250, px, pt)),
        "angle_overshoot_deg": float(px[-1] - 250),
        "discarded_nonforward_samples": int(a.shape[1] - len(x)),
    }
    if timing["target_end_s"] <= timing["trigger_s"]:
        raise ValueError("Response window is not later than prediction")
    return values, response, timing


def reconstruct_screw(recipe, source_root):
    from .native import _registered_groups, _row, _unique_object, identity

    (asset,) = [a for a in recipe["assets"] if a["role"] == "screw_archive"]
    (meta,) = [a for a in recipe["assets"] if a["role"] == "source_metadata"]
    info = json.loads(
        contained(source_root, meta["path"]).read_bytes(), object_pairs_hook=_unique_object
    )
    if (
        info["source_version"] != "16031381"
        or info["license_or_terms"] != "cc-by-4.0"
        or recipe["input_units"] != INPUT_UNITS
        or recipe["output_units"] != "Nm"
    ):
        raise ValueError("Screw source identity, license or units differ")
    valid, excluded, counts, points, repeats = [], [], Counter(), 0, 0
    with bounded_zip(
        contained(source_root, asset["path"]),
        max_bytes=310_000_000,
        max_member_bytes=3_000_000,
        max_members=12502,
    ) as z:
        ops = labels(z.read("labels.csv"))
        if set(z.namelist()) != {"labels.csv", "README.md"} | {o["member"] for o in ops}:
            raise ValueError("Unmatched source operations or archive members")
        groups = assignments(recipe["scenario_id"], ops)
        if _registered_groups(recipe, groups) != groups:
            raise ValueError("Registered whole-workpiece allocation differs")
        member_hashes = {
            n: hashlib.sha256(z.read(n)).hexdigest() for n in ["labels.csv", "README.md"]
        }
        for op in ops:
            raw = z.read(op["member"])
            a, duration, n, r = decode(raw, op)
            points += n
            repeats += r
            counts[op["workpiece_result"]] += 1
            try:
                values, response, timing = measurements(a)
            except Unavailable as exc:
                excluded.append(
                    {"labels_row": op["labels_row"], "run_id": op["run_id"], "reason": str(exc)}
                )
                continue
            valid.append(
                {
                    **op,
                    "values": values,
                    "response": response,
                    "timing": timing,
                    "duration": duration,
                }
            )
    parts, lineage, units = {p: [] for p in ("train", "dev", "test")}, [], {}
    histories, margins = defaultdict(list), []
    for op in sorted(
        valid,
        key=lambda r: (
            r["workpiece_id"],
            r["workpiece_location"],
            r["workpiece_date"],
            r["run_id"],
        ),
    ):
        w, v = op["workpiece_id"], dict(op["values"])
        past = histories[w, op["workpiece_location"]]
        prev = past[-1] if past else None
        margin = None
        if prev:
            margin = (op["wallclock"] - op["duration"] - 1 + op["timing"]["trigger_s"]) - (
                prev["wallclock"] + prev["timing"]["target_end_s"] + 1
            )
            if op["usage"] <= prev["usage"] or margin <= 0:
                raise ValueError("Prior same-hole response not proven available")
            margins.append(margin)
        v.update(
            {
                "usage": float(op["usage"]),
                "left": float(op["workpiece_location"] == "left"),
                "has_history": float(bool(past)),
                "prev_y": prev["response"] if prev else v["early"],
                "prev_early": prev["values"]["early"] if prev else v["early"],
                "prev_gradient": prev["values"]["gradient_proxy"] if prev else v["gradient_proxy"],
                "first_y": past[0]["response"] if past else v["early"],
                "mean_past_y": float(np.mean([r["response"] for r in past]))
                if past
                else v["early"],
                "history_gap": float(op["usage"] - prev["usage"]) if prev else 0.0,
            }
        )
        row, anchor = _row(
            recipe["scenario_id"],
            op["run_id"],
            w,
            groups[w],
            v,
            op["response"],
            {
                "labels_row": op["labels_row"],
                "trigger_index": op["timing"]["trigger_index"],
                "target_end_index": op["timing"]["target_end_index"],
                "previous_labels_row": prev["labels_row"] if prev else None,
                "first_labels_row": past[0]["labels_row"] if past else None,
                "history_count": len(past),
            },
        )
        parts[groups[w]].append(row)
        lineage.append(anchor)
        units[identity(recipe["scenario_id"], "group", w)] = w
        past.append(op)
    diagnostics = {
        "operations": len(ops),
        "workpieces": len(groups),
        "eligible_operations": len(valid),
        "unavailable_operations": len(excluded),
        "source_measurement_points": points,
        "repeated_clock_intervals": repeats,
        "quality_counts": dict(counts),
        "eligible_quality_counts": dict(Counter(r["workpiece_result"] for r in valid)),
        "surface_conditions": sorted({r["class_value"] for r in ops}),
        "exclusion_reasons": dict(Counter(e["reason"] for e in excluded)),
        "history_links": len(margins),
        "minimum_conservative_history_margin_s": min(margins, default=None),
        "maximum_sampled_trigger_latency_s": max(r["timing"]["trigger_latency_s"] for r in valid),
        "maximum_angle_overshoot_deg": max(r["timing"]["angle_overshoot_deg"] for r in valid),
        "discarded_nonforward_samples": sum(
            r["timing"]["discarded_nonforward_samples"] for r in valid
        ),
        "historical_targets_used_only_after_completed_same_hole_operations": True,
        "target_exported": False,
    }
    return (
        parts,
        lineage,
        {
            "split_check": check_units(parts, units),
            "screw_validation": diagnostics,
            "excluded_operations": excluded,
            "source_member_hashes": member_hashes,
            "lineage_schema": "labels_row is the 1-based CSV row including header; it identifies native JSON member. Indices are zero-based source graph samples. Previous/first row links and history_count reconstruct the complete eligible past chain.",
            "admission_blockers": [
                "Rights/notice and scientific admission pending",
                "Source wall-clock timezone and start/completion semantics unspecified; conservative two-sided duration bounds used",
                "Same-hole online history includes already completed test-operation responses; not one-shot unseen-workpiece or free-running evaluation",
                "Rule complexity excludes native feature extraction and sensor costs; perturbations remain diagnostic",
            ],
        },
    )
