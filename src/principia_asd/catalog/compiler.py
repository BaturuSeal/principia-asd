"""Curator reconstruction of recorded compiler timings, conditional on a Qiskit pilot."""

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import PurePosixPath

from ..io import contained, sha
from .fracture import bounded_zip
from .splits import check_units

PARSER = "benchpress-recorded-pilot-timings-v1"
SDKS = ("qiskit", "tket", "bqskit", "staq")
INFO_KEYS = {
    "qiskit": "qiskit_info",
    "tket": "pytket_info",
    "bqskit": "bqskit_info",
    "staq": "staq_info",
}
INPUT_UNITS = {
    "is_bqskit": "SDK indicator,elseStaq",
    "is_tket": "SDK indicator",
    "load_seconds": "Qiskit QASM loading seconds",
    "pilot_depth": "Qiskit output two-qubit depth",
    "pilot_gates": "Qiskit output two-qubit gate count",
    "pilot_seconds": "seconds Qiskit calibration cost",
    "qubits": "input qubit count",
}
EXPOSED = {"mod", "tof", "rc_adder", "adder", "qpt", "partial_tof"}


def member(sdk):
    return f"published_results/transpilation/{sdk}_device.json"


def family(filename):
    p = PurePosixPath(filename)
    if p.name != filename or p.suffix != ".qasm" or len(filename) > 150:
        raise ValueError("Unsafe or unsupported circuit identifier")
    # Historical grouping removes numeric tokens anywhere, not only a final suffix.
    result = re.sub(r"[_-]?\d+", "", p.stem).lower()
    if not result:
        raise ValueError("Empty circuit family")
    return result


def original_assignments(case, filenames):
    from .native import identity

    groups = sorted(
        set(map(family, filenames)),
        key=lambda g: int(
            hashlib.sha256(("principia100-batch7:compiler-family:" + g).encode()).hexdigest()[:16],
            16,
        ),
    )
    held = set([g for g in groups if g not in EXPOSED][: max(1, len(groups) // 5)])
    available = set(groups) - held
    dev = set(
        sorted(available, key=lambda g: sha(["compact-v2", case, identity(case, "group", g)]))[
            : max(1, len(available) // 5)
        ]
    )
    return {g: "test" if g in held else "dev" if g in dev else "train" for g in groups}


def number(v, *, positive=False, integer=False):
    if (
        isinstance(v, bool)
        or not isinstance(v, (int, float))
        or not math.isfinite(v)
        or (v <= 0 if positive else v < 0)
        or (integer and int(v) != v)
    ):
        raise ValueError("Invalid native compiler timing/count")
    return v


def timing(b):
    stats = b["stats"]
    mean = number(stats["mean"], positive=True)
    low, high = number(stats["min"], positive=True), number(stats["max"], positive=True)
    rounds = number(stats["rounds"], positive=True, integer=True)
    number(stats["stddev"])
    if (
        not low <= mean <= high
        or stats["iterations"] != 1
        or not math.isclose(
            number(stats["total"], positive=True), mean * rounds, rel_tol=1e-9, abs_tol=1e-12
        )
        or b["options"].get("timer") != "perf_counter"
    ):
        raise ValueError("Unresolved timing aggregation or timer")
    return mean


def decode_report(raw, sdk):
    from .native import _unique_object

    if len(raw) > 3_000_000:
        raise ValueError("Oversized native compiler report")

    def bad_constant(value):
        raise ValueError("Nonfinite JSON constant: " + value)

    d = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=bad_constant)
    rows = d["benchmarks"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 500 or d["version"] != "4.0.0":
        raise ValueError("Unsupported benchmark report version or shape")
    commit = d["commit_info"]
    if (
        commit["project"] != "benchpress"
        or commit["dirty"] is not False
        or not re.fullmatch(r"[0-9a-f]{40}", commit["id"])
    ):
        raise ValueError("Unbound source benchmark revision")
    dumps = d["test_dumps"]
    counts = d["test_status_counts"]
    if (
        set(dumps) != set(counts)
        or any(len(v) != counts[k] for k, v in dumps.items())
        or counts["passed"] != len(rows)
    ):
        raise ValueError("Source test status inventory differs")
    named, seen = {}, set()
    for idx, b in enumerate(rows):
        full = b["fullname"]
        if full in seen or full not in dumps["passed"]:
            raise ValueError("Duplicate or nonpassed native benchmark")
        seen.add(full)
        params = b.get("params") or {}
        if "filename" not in params:
            continue
        fn = params["filename"]
        family(fn)
        if (
            set(params) != {"filename"}
            or fn in named
            or not full.endswith("[" + fn + "]")
            or not full.startswith(sdk + "_gym/device_transpile/")
        ):
            raise ValueError("Ambiguous circuit join or SDK identity")
        timing(b)
        e = b["extra_info"]
        number(e["input_num_qubits"], positive=True, integer=True)
        if sdk == "qiskit":
            for key in ("output_gate_count_2q", "output_depth_2q"):
                number(e[key], integer=True)
            number(e["qasm_load_time"])
        named[fn] = (idx, b)
    return d, named


def reconstruct_compiler(recipe, source_root):
    from .native import _registered_groups, _row, _unique_object, identity

    (asset,) = [a for a in recipe["assets"] if a["role"] == "compiler_archive"]
    (meta,) = [a for a in recipe["assets"] if a["role"] == "source_metadata"]
    m = json.loads(
        contained(source_root, meta["path"]).read_bytes(), object_pairs_hook=_unique_object
    )
    if (
        m["id"] != 14977295
        or m["doi"] != "10.5281/zenodo.14977295"
        or m["metadata"]["license"]["id"] != "cc-by-4.0"
        or recipe["input_units"] != INPUT_UNITS
        or recipe["output_units"] != "seconds"
    ):
        raise ValueError("Compiler source identity, license or units differ")
    docs, named, hashes = {}, {}, {}
    with bounded_zip(
        contained(source_root, asset["path"]), max_bytes=16_000_000, max_member_bytes=3_000_000
    ) as z:
        for sdk in SDKS:
            raw = z.read(member(sdk))
            hashes[member(sdk)] = hashlib.sha256(raw).hexdigest()
            docs[sdk], named[sdk] = decode_report(raw, sdk)
    if any(sorted(named[s]) != recipe["completed_circuits"][s] for s in SDKS):
        raise ValueError("Registered completed circuit cohort changed; no silent selection")
    pilot = named["qiskit"]
    groups = original_assignments(recipe["scenario_id"], pilot)
    if _registered_groups(recipe, groups) != groups:
        raise ValueError("Historical circuit-family allocation changed")
    cpu = docs["qiskit"]["machine_info"]["cpu"]["brand_raw"]
    if cpu != "AMD Ryzen 9 7900 12-Core Processor" or any(
        d["machine_info"]["cpu"]["brand_raw"] != cpu for d in docs.values()
    ):
        raise ValueError("Native CPU identity mismatch")
    parts, lineage, units = {p: [] for p in ("train", "dev", "test")}, [], {}
    missing = []
    for sdk in SDKS[1:]:
        if not set(named[sdk]) <= set(pilot):
            raise ValueError("SDK benchmark has no matching pilot")
        for fn in sorted(set(pilot) - set(named[sdk])):
            statuses = [
                state
                for state, items in docs[sdk]["test_dumps"].items()
                for name in items
                if name.endswith("[" + fn + "]")
            ]
            if len(statuses) != 1 or statuses[0] not in {"failed", "xfailed", "skipped"}:
                raise ValueError("Unaccounted missing native compiler outcome")
            missing.append(
                {
                    "sdk": sdk,
                    "filename": fn,
                    "family": family(fn),
                    "status": statuses[0],
                    "measurement_imputed": False,
                }
            )
        for fn, (idx, b) in named[sdk].items():
            pi, p = pilot[fn]
            e = p["extra_info"]
            if e["input_num_qubits"] != b["extra_info"]["input_num_qubits"]:
                raise ValueError("Circuit input-qubit join mismatch")
            group = family(fn)
            split = groups[group]
            units[identity(recipe["scenario_id"], "group", group)] = group
            row, anchor = _row(
                recipe["scenario_id"],
                sdk + ":" + fn,
                group,
                split,
                {
                    "pilot_seconds": float(p["stats"]["mean"]),
                    "qubits": float(e["input_num_qubits"]),
                    "pilot_gates": float(e["output_gate_count_2q"]),
                    "pilot_depth": float(e["output_depth_2q"]),
                    "load_seconds": float(e["qasm_load_time"]),
                    "is_tket": float(sdk == "tket"),
                    "is_bqskit": float(sdk == "bqskit"),
                },
                b["stats"]["mean"],
                {
                    "source": asset["path"],
                    "member": member(sdk),
                    "benchmark_index": idx,
                    "target_field": "stats.mean",
                    "filename": fn,
                    "family": group,
                    "pilot_member": member("qiskit"),
                    "pilot_benchmark_index": pi,
                    "pilot_fields": [
                        "stats.mean",
                        "extra_info.input_num_qubits",
                        "extra_info.output_gate_count_2q",
                        "extra_info.output_depth_2q",
                        "extra_info.qasm_load_time",
                    ],
                },
            )
            parts[split].append(row)
            lineage.append(anchor)
    source_reports = {
        sdk: {
            "member": member(sdk),
            "benchmarks": len(d["benchmarks"]),
            "named_circuits": len(named[sdk]),
            "other_benchmarks_excluded": len(d["benchmarks"]) - len(named[sdk]),
            "revision": d["commit_info"]["id"],
            "run_date": d["datetime"],
            "versions": d[INFO_KEYS[sdk]],
            "status_counts": d["test_status_counts"],
            "recorded_round_range": [
                min(b["stats"]["rounds"] for _, b in named[sdk].values()),
                max(b["stats"]["rounds"] for _, b in named[sdk].values()),
            ],
        }
        for sdk, d in docs.items()
    }
    return (
        parts,
        lineage,
        {
            "split_check": check_units(parts, units),
            "compiler_validation": {
                "source_reports": source_reports,
                "member_hashes": hashes,
                "cpu_brand": cpu,
                "family_inventory": {
                    g: sorted(fn for fn in pilot if family(fn) == g) for g in sorted(groups)
                },
                "group_counts": dict(Counter(groups.values())),
                "matched_successful_pairs": len(lineage),
                "missing_pairs": missing,
                "pilot_unique_circuits": len(pilot),
                "pilot_total_measured_round_seconds": sum(
                    p["stats"]["total"] for _, p in pilot.values()
                ),
                "pilot_qasm_load_seconds": sum(
                    p["extra_info"]["qasm_load_time"] for _, p in pilot.values()
                ),
                "pilot_cost_scope": "Recorded timing rounds plus separate load summary, not independent end-to-end wall cost",
                "family_rule": "Remove all optional-delimiter numeric tokens anywhere in the stem; not syntax-verified circuit equivalence",
                "legacy_five_folds_not_used_in_compact_split": True,
                "fit_count": 0,
                "learned_transformations": [],
            },
            "admission_blockers": [
                "Conditional on successful runs and a completed Qiskit pilot; unavailable SDK outcomes are not scored failure predictions",
                "Different recorded dates and Benchpress/SDK revisions; CPU identity is not full hardware/load/environment matching",
                "Filename-derived family grouping is not a verified semantic circuit taxonomy; original circuit QASM is not part of selected sources",
                "Recorded aggregate timing statistics, not repeated raw durations or independently rerun compiler experiments",
                "Diagnostic software timing task, not pre-compilation prediction or quantum-device performance",
                "Rights/notices, independent scientific value and calibrated perturbations require admission review",
            ],
        },
    )
