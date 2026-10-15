"""Curator-only AFM export reconstruction, with paired instrument-header custody.

No DMT fitting, image interpretation, reference constants or evaluator access.
The exported force conversion is checked, not fitted or replaced.
"""

from __future__ import annotations

import hashlib
import json
import re
import stat
import zipfile
from collections import Counter
from pathlib import PurePosixPath

import numpy as np

from ..io import contained, sha
from .splits import check_units

HEADER = [
    "Calc_Ramp_Ex_nm",
    "Calc_Ramp_Rt_nm",
    "Defl_nm_Ex",
    "Defl_nm_Rt",
    "Defl_pN_Ex",
    "Defl_pN_Rt",
]
SURFACES = {"CA Flat": 4, "CA Low Roughness": 4, "CA High Roughness": 5}
INPUT_UNITS = {"x": "dimensionless", "base": "nN", "amp": "nN", "progress": "dimensionless"}
SOURCE_URL = "https://zenodo.org/records/20281797"


def member_identity(name):
    p = PurePosixPath(name)
    if (
        len(p.parts) != 3
        or p.parts[0] != "NFFA DESY Raw data"
        or p.parts[1] not in SURFACES
        or not re.fullmatch(
            r"23080[47]_CA_(?:Flat|Low|high)\.0_[0-9]{5}\.pfc-[A-F0-9]+_ForceCurveIndex_[0-9]+\.spm\.txt",
            p.name,
        )
    ):
        raise ValueError("Unregistered AFM curve identity")
    prefix = {
        "CA Flat": "230804_CA_Flat",
        "CA Low Roughness": "230804_CA_Low",
        "CA High Roughness": "230807_CA_high",
    }[p.parts[1]]
    if not p.name.startswith(prefix + "."):
        raise ValueError("AFM surface and acquisition identity differ")
    return p.name, p.parts[1]


def archive_members(archive):
    items = archive.infolist()
    names = [a.filename for a in items]
    if (
        len(items) > 200
        or len(names) != len(set(names))
        or sum(a.file_size for a in items) > 10_000_000
        or any(a.file_size > 3_000_000 for a in items)
    ):
        raise ValueError("Duplicate or oversized AFM archive")
    for a in items:
        p = PurePosixPath(a.filename)
        if (
            p.is_absolute()
            or ".." in p.parts
            or "\\" in a.filename
            or a.flag_bits & 1
            or stat.S_ISLNK(a.external_attr >> 16)
        ):
            raise ValueError("Unsafe AFM archive member")
    members = sorted(n for n in names if n.endswith(".txt"))
    groups = [member_identity(n) for n in members]
    if Counter(s for _, s in groups) != SURFACES or len({g for g, _ in groups}) != len(groups):
        raise ValueError("Incomplete or ambiguous AFM surface/curve panel")
    if any(n[:-4] not in names for n in members):
        raise ValueError("Missing paired AFM instrument file")
    return members, {"members": len(items), "expanded_bytes": sum(a.file_size for a in items)}


def instrument_header(raw):
    if len(raw) > 100_000 or raw.count(b"\\*File list end\r\n") != 1:
        raise ValueError("Missing, ambiguous or oversized AFM instrument header")
    # Bruker headers contain legacy degree symbols; numeric calibration fields are ASCII.
    header = raw.split(b"\\*File list end\r\n")[0].decode("latin1")
    if not header.startswith("\\*Force file list\r\n"):
        raise ValueError("Unexpected AFM instrument format")

    def one(pattern):
        values = re.findall(pattern, header, flags=re.MULTILINE)
        if len(values) != 1:
            raise ValueError("Ambiguous AFM instrument calibration")
        return values[0]

    spring = float(one(r"^\\Spring Constant: ([0-9.]+)\r?$"))
    sensitivity = float(one(r"^\\@Sens\. DeflSens: V ([0-9.]+) nm/V\r?$"))
    force_sensitivity = float(one(r"^\\@Sens\. ForceDeflSens: V ([0-9.]+) nN/V\r?$"))
    date = one(r"^\\Date: ([^\r\n]+)\r?$")
    if not (0 < spring < 100 and 0 < sensitivity < 200 and 0 < force_sensitivity < 10_000):
        raise ValueError("Invalid AFM instrument calibration")
    if not np.isclose(force_sensitivity, spring * sensitivity, rtol=2e-6, atol=0):
        raise ValueError("Inconsistent force and deflection calibration")
    return {
        "spring_constant_N_per_m": spring,
        "deflection_sensitivity_nm_per_V": sensitivity,
        "force_sensitivity_nN_per_V": force_sensitivity,
        "acquired_at_text": date,
        "binary_measurements_decoded": False,
    }


def stored_curve(raw, calibration):
    if len(raw) > 100_000:
        raise ValueError("Oversized AFM text export")
    lines = raw.decode("ascii").splitlines()
    if not lines or lines[0].split() != HEADER or len(lines) != 129:
        raise ValueError("Unexpected AFM export columns, units or row count")
    tokens = [r.split() for r in lines[1:]]
    if any(len(r) != 6 for r in tokens):
        raise ValueError("Invalid AFM row shape or hidden field")
    try:
        a = np.array(tokens, dtype=float)
    except ValueError as exc:
        raise ValueError("Nonnumeric AFM measurement") from exc
    if not np.isfinite(a).all():
        raise ValueError("Nonfinite AFM measurement; no implicit imputation")
    if (
        a[0, 0] != 0
        or abs(a[-1, 1]) > 1e-5
        or np.any(np.diff(a[:, 0]) <= 0)
        or np.any(np.diff(a[:, 1]) >= 0)
        or not np.allclose(a[:, 0] + a[:, 1], a[0, 1], rtol=1e-6, atol=1e-5)
    ):
        raise ValueError("Invalid AFM approach/retraction ramp")
    # Fixed instrument constant; no regression or force-dependent curve filtering.
    converted = a[:, 2:4] * calibration["spring_constant_N_per_m"] * 1000
    if not np.allclose(converted, a[:, 4:6], rtol=2e-6, atol=0.03):
        raise ValueError("Force export disagrees with instrument spring constant")
    return a


def calibrated_features(a):
    """Use only completed approach and the permitted first five retraction points."""
    approach, retract = a[:, 4] / 1000, a[:, 5] / 1000
    base = float(np.mean(approach[:10]))
    crossings = np.flatnonzero(approach >= base + 5)
    if not len(crossings):
        raise ValueError("Missing fixed 5nN approach crossing")
    cross = int(crossings[0])
    origin, maximum = float(a[cross, 0]), float(a[0, 1])
    if maximum <= origin:
        raise ValueError("Degenerate AFM calibrated coordinate")
    peak = float(np.mean(retract[:5]))
    return [
        {
            "x": float((a[k, 1] - origin) / (maximum - origin)),
            "base": base,
            "amp": peak - base,
            "progress": float(k / (len(a) - 1)),
        }
        for k in range(16, len(a))
    ], cross


def original_assignments(case, members):
    from .native import identity

    held = {
        min(
            (n for n in members if member_identity(n)[1] == surface),
            key=lambda n: hashlib.sha256(("P100-084-v1|" + n).encode()).hexdigest(),
        )
        for surface in SURFACES
    }
    names = {PurePosixPath(n).name: n for n in members}
    ordered = sorted(
        (g for g, n in names.items() if n not in held),
        key=lambda g: sha(["compact-v2", case, identity(case, "group", g)]),
    )
    dev = set(ordered[:2])
    return {
        g: "test" if n in held else "dev" if g in dev else "train" for g, n in sorted(names.items())
    }


def reconstruct_afm(recipe, source_root):
    from .native import _registered_groups, _row, _unique_object, identity

    (asset,) = [a for a in recipe["assets"] if a["role"] == "afm_archive"]
    (meta,) = [a for a in recipe["assets"] if a["role"] == "source_metadata"]
    metadata = json.loads(
        contained(source_root, meta["path"]).read_bytes(), object_pairs_hook=_unique_object
    )
    if (
        metadata["id"] != 20281797
        or metadata["doi"] != "10.5281/zenodo.20281797"
        or metadata["metadata"]["license"]["id"] != "cc-by-4.0"
        or recipe["input_units"] != INPUT_UNITS
        or recipe["output_units"] != "nN"
    ):
        raise ValueError("AFM source identity, license or unit policy differs")
    parts, lineage, traces, units = {s: [] for s in ("train", "dev", "test")}, [], [], {}
    with zipfile.ZipFile(contained(source_root, asset["path"])) as archive:
        members, inventory = archive_members(archive)
        if members != recipe["curve_members"]:
            raise ValueError("AFM native member inventory changed")
        assignments = _registered_groups(recipe, [member_identity(n)[0] for n in members])
        if assignments != original_assignments(recipe["scenario_id"], members):
            raise ValueError("Historical AFM curve allocation changed")
        for index, name in enumerate(members):
            raw, binary = archive.read(name), archive.read(name[:-4])
            header = instrument_header(binary)
            a = stored_curve(raw, header)
            features, crossing = calibrated_features(a)
            group, surface = member_identity(name)
            split = assignments[group]
            units[identity(recipe["scenario_id"], "group", group)] = group
            traces.append(
                {
                    "source": asset["path"],
                    "member": name,
                    "paired_binary_member": name[:-4],
                    "export_sha256": hashlib.sha256(raw).hexdigest(),
                    "instrument_sha256": hashlib.sha256(binary).hexdigest(),
                    "surface": surface,
                    "split": split,
                    "measurement_rows": len(a),
                    "calibration_approach_rows": list(range(2, 12)),
                    "first_5nN_crossing_row": crossing + 2,
                    "calibration_retraction_rows": list(range(2, 7)),
                    "target_rows": [18, 129],
                    "calibration": header,
                }
            )
            for k, values in enumerate(features, 16):
                row, source = _row(
                    recipe["scenario_id"],
                    group + f"-row-{k + 2}",
                    group,
                    split,
                    values,
                    a[k, 5] / 1000,
                    {"curve_index": index, "source_row": k + 2},
                )
                parts[split].append(row)
                lineage.append(source)
    by_surface = {s: sorted({t["split"] for t in traces if t["surface"] == s}) for s in SURFACES}
    sensitivity = sorted({t["calibration"]["deflection_sensitivity_nm_per_V"] for t in traces})
    return (
        parts,
        lineage,
        {
            "split_check": check_units(parts, units),
            "afm_traces": traces,
            "lineage_definition": {
                "curve_index": "Zero-based index in checks.afm_traces",
                "source_row": "One-based physical text row, including column header",
                "x": "(column 2 at row - column 1 at first 5nN approach crossing) / (column 2 at row 2 - same crossing coordinate)",
                "base": "mean(column 5 at rows 2..11) / 1000",
                "amp": "mean(column 6 at rows 2..6) / 1000 - base",
                "progress": "(source_row-2)/127; coordinate fraction, not measured physical time",
                "target": "column 6 at source_row / 1000; never exported for test",
                "excluded_predictors": "Retraction deflection, late retraction force, images, source-fitted modulus and adhesion maps",
            },
            "afm_validation": {
                "curves": len(traces),
                "source_rows": sum(t["measurement_rows"] for t in traces),
                "eligible_rows": len(lineage),
                "group_counts": dict(Counter(assignments.values())),
                "archive": inventory,
                "surface_counts": SURFACES,
                "surface_partition_overlap": by_surface,
                "deflection_sensitivity_nm_per_V": sensitivity,
                "readme_deflection_sensitivity_nm_per_V": 86.5,
                "readme_sensitivity_matches_headers": all(
                    abs(s - 86.5) < 0.01 for s in sensitivity
                ),
                "force_deflection_relation_checked_without_fitting": True,
                "readme_scope": "Bound source README says 86.5nm/V; instrument headers retained without reinterpretation",
                "fit_count": 0,
                "learned_transformations": [],
                "late_response_used_in_inputs": False,
                "independence_scope": "Distinct locations within three surface specimens/acquisitions; not independent batches",
            },
            "admission_blockers": [
                "README and per-curve instrument deflection sensitivities require source reconciliation",
                "Same surfaces/acquisitions span partitions; curve-held-out prediction is not specimen or batch transfer",
                "Author-calibrated text exports retained; binary signal decoding and export processing not independently reproduced",
                "Only permitted approach and early retraction calibrate inputs; no cell response, modulus or mechanism claim",
                "Full-pipeline complexity, instrument uncertainty, valid perturbations, rights/notices and scientific admission remain unassessed",
            ],
        },
    )
