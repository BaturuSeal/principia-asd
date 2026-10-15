"""Curator-only LFP spectral reconstruction with explicit calibration custody.

Measured references are not reference answers. No phase-fraction/EXAFS model,
author fit or XRD calculation is a prediction input. Nominal progress uses
retrospectively known segment durations, as the historical contract declares.
"""

import hashlib
import io
import json
import re
from collections import Counter
from pathlib import PurePosixPath

import numpy as np

from ..io import contained, sha
from .fracture import NS, REL, bounded_zip
from .memristor import row_ranges
from .splits import check_units

RAW = "01_XANES/LFP/LFP_raw_0-Binning_01-194.dat"
REFERENCES = "01_XANES/LFP/LFP_references_FePO4_LiFePO4.xmu"
ASSIGNMENT = "LFP-spectra-assignment.xlsx"
CLOCK = "03_galvanostatic-potential-profiles/LFP-potential-time_curve.txt"
INPUT_UNITS = {
    "d2L": "eV⁻²",
    "dL": "eV⁻¹",
    "discharge": "binarydischarge/rest2branch",
    "e": "eVrelative7112",
    "f": "dimensionlessnominalprotocolprogress",
    "jump": "rawμ(E),dimensionless",
    "pre": "rawμ(E),dimensionless",
    "rF": "normalizedmeasuredFePO4reference",
    "rL": "normalizedmeasuredLiFePO4reference",
    "rest": "binaryrestsegment",
}
SEGMENTS = [
    ("charge", 31981, 31981, "001-107", "001-036"),
    ("rest-1", 39181, 7200, "108-131", "037-044"),
    ("discharge", 50866, 11684, "132-170", "045-057"),
    ("rest-2", 58067, 7200, "171-194", "058-065"),
]


def stored_spectra(raw, *, reference=False):
    if len(raw) > (120_000 if reference else 3_000_000):
        raise ValueError("Oversized XAS numeric source")
    lines = raw.decode("ascii").splitlines()
    header = (
        ["#", "energy_eV", "FePO4", "LiFePO4"]
        if reference
        else ["#", "energy_eV", *[f"{i:03}" for i in range(1, 195)]]
    )
    shape = (1873, 3) if reference else (2005, 195)
    if len(lines) != shape[0] + 1 or lines[0].split() != header:
        raise ValueError("XAS source identity, unit, columns or row count differ")
    if any(len(line.split()) != shape[1] for line in lines[1:]):
        raise ValueError("Missing or hidden XAS columns")
    a = np.loadtxt(io.StringIO("\n".join(lines[1:])), ndmin=2)
    if (
        a.shape != shape
        or np.isinf(a).any()
        or not np.isfinite(a[:, 0]).all()
        or np.any(np.diff(a[:, 0]) <= 0)
    ):
        raise ValueError("Invalid XAS energies or numeric measurements")
    if reference and not np.isfinite(a).all():
        raise ValueError("Missing measured reference; no interpolation across missing responses")
    if not reference and not np.allclose(a[:, 0], 6404.221 + np.arange(2005), rtol=0, atol=1e-8):
        raise ValueError("Native LFP energy grid changed")
    return a


def stored_assignment(raw):
    """Validate author-stored protocol cells, without evaluating workbook formulas."""
    from .native import _xml

    if len(raw) > 30_000:
        raise ValueError("Oversized XAS assignment workbook")
    with bounded_zip(io.BytesIO(raw), max_bytes=60_000, max_member_bytes=30_000) as z:
        sheets = _xml(z.read("xl/workbook.xml")).findall(f"{NS}sheets/{NS}sheet")
        if len(sheets) != 1 or sheets[0].get("name") != "Tabelle1":
            raise ValueError("Unexpected XAS protocol worksheet")
        links = _xml(z.read("xl/_rels/workbook.xml.rels"))
        matches = [x for x in links if x.get("Id") == sheets[0].get(REL + "id")]
        if len(matches) != 1 or matches[0].get("TargetMode") == "External":
            raise ValueError("External or ambiguous XAS protocol relationship")
        target = PurePosixPath(matches[0].get("Target", ""))
        if target.is_absolute() or ".." in target.parts or "\\" in str(target):
            raise ValueError("Unsafe XAS protocol member")
        strings = []
        if "xl/sharedStrings.xml" in z.namelist():
            strings = [
                "".join(t.text or "" for t in e.iter(NS + "t"))
                for e in _xml(z.read("xl/sharedStrings.xml")).findall(NS + "si")
            ]
        cells, seen, previous = {}, set(), 0
        for row in _xml(z.read("xl/" + str(target))).findall(f"{NS}sheetData/{NS}row"):
            number = int(row.attrib["r"])
            if number != previous + 1 or number > 6:
                raise ValueError("Changed XAS protocol source rows")
            previous = number
            for cell in row.findall(NS + "c"):
                address = cell.get("r", "")
                m = re.fullmatch(r"([A-F])([1-6])", address)
                if not m or int(m[2]) != number or address in seen:
                    raise ValueError("Ambiguous XAS protocol cell")
                seen.add(address)
                if cell.find(NS + "f") is not None:
                    raise ValueError("Formula in XAS protocol source")
                kind, value = cell.get("t", "n"), cell.findtext(NS + "v")
                if kind == "s":
                    index = int(value)
                    if not 0 <= index < len(strings):
                        raise ValueError("Invalid XAS protocol string")
                    value = strings[index]
                elif kind == "inlineStr":
                    value = "".join(t.text or "" for t in cell.iter(NS + "t"))
                elif kind != "n":
                    raise ValueError("Unsupported XAS protocol cell type")
                elif value is not None:
                    value = float(value)
                if value is not None:
                    cells[address] = value
        expected = {
            "B1": "seconds total",
            "C1": "senconds segment",
            "E1": "1xBinning spectra",
            "F1": "3x-Binning spectra",
        }
        for row, values in enumerate(SEGMENTS, 3):
            expected.update({f"{c}{row}": value for c, value in zip("ABCEF", values, strict=True)})
        if cells != expected or previous != 6:
            raise ValueError("Stored XAS protocol assignments changed")
    return [
        dict(zip(("name", "end_s", "duration_s", "unbinned", "binned"), s, strict=True))
        for s in SEGMENTS
    ]


def acquisition_clock(raw):
    if len(raw) > 6_000_000:
        raise ValueError("Oversized XAS electrochemistry log")
    lines = raw.decode("ascii").splitlines()
    if (
        len(lines) != 58089
        or lines[1].split() != ["measurement_ID", "LFP"]
        or lines[19].split()
        != "number total time segment time period voltage current capacity criterion mode".split()
        or lines[20].split() != "[1] [s] [s] [s] [V] [A] [mAh/g] [V or A] [1]".split()
    ):
        raise ValueError("Unexpected LFP clock identity, fields or units")
    if any(len(line.split()) != 9 for line in lines[21:]):
        raise ValueError("Malformed LFP clock row")
    a = np.loadtxt(io.StringIO("\n".join(lines[21:])), ndmin=2)
    if (
        a.shape != (58068, 9)
        or not np.isfinite(a).all()
        or not np.array_equal(a[:, 1], np.arange(58068))
    ):
        raise ValueError("Incomplete or nonmonotonic LFP acquisition clock")
    bounds = [0, 31982, 39182, 50867, 58068]
    blocks = []
    for i, (lo, hi) in enumerate(zip(bounds[:-1], bounds[1:], strict=True)):
        if (
            not np.all(a[lo:hi, -1] == (1, 0, 3, 0)[i])
            or np.any(np.diff(a[lo:hi, 2]) <= 0)
            or a[lo, 2] != (0, 0.5, 0, 0)[i]
            or a[hi - 1, 2] != (31981, 7199.5, 11684, 7200)[i]
        ):
            raise ValueError("LFP cycle mode or segment chronology changed")
        blocks.append(
            {
                "name": SEGMENTS[i][0],
                "source_lines": [lo + 22, hi + 21],
                "start_s": float(a[lo, 1]),
                "end_s": float(a[hi - 1, 1]),
                "segment_start_s": float(a[lo, 2]),
                "segment_end_s": float(a[hi - 1, 2]),
            }
        )
    return {
        "rows": len(a),
        "date_text": lines[0].split()[-1],
        "segments": blocks,
        "response_channels_used_as_predictors": False,
    }


def calibrated_panel(a, refs):
    """Expand permitted bands and measured reference transforms, never target fit."""
    E, re = a[:, 0], refs[:, 0]
    pre, post = (E >= 7000) & (E <= 7050), (E >= 7250) & (E <= 7300)
    rp, rq = (re >= 7000) & (re <= 7050), (re >= 7250) & (re <= 7300)
    selected = np.flatnonzero((E >= 7070) & (E <= 7200))[::5]
    if (
        len(selected) != 26
        or not all(mask.any() for mask in (pre, post, rp, rq))
        or not (re[0] <= E[selected[0]] < E[selected[-1]] <= re[-1])
    ):
        raise ValueError("Missing XAS calibration support or reference extrapolation")
    if np.any(np.isfinite(a[pre, 1:]).sum(axis=0) == 0) or np.any(
        np.isfinite(a[post, 1:]).sum(axis=0) == 0
    ):
        raise ValueError("Unavailable spectrum calibration")
    base = np.array([np.nanmean(a[pre, col]) for col in range(1, a.shape[1])])
    jump = np.array([np.nanmean(a[post, col]) for col in range(1, a.shape[1])]) - base
    rbase = np.nanmean(refs[rp, 1:], axis=0)
    rjump = np.nanmean(refs[rq, 1:], axis=0) - rbase
    if (
        not np.isfinite(jump).all()
        or np.any(jump <= 0)
        or np.any(rjump <= 0)
        or not np.isfinite(a[selected, 1:]).all()
    ):
        raise ValueError(
            "Invalid XAS calibration or missing eligible target; denominator cannot shrink"
        )
    norm = (refs[:, 1:] - rbase) / rjump
    grad = np.gradient(norm[:, 1], re)
    second = np.gradient(grad, re)
    reference = {
        "rF": np.interp(E[selected], re, norm[:, 0]),
        "rL": np.interp(E[selected], re, norm[:, 1]),
        "dL": np.interp(E[selected], re, grad),
        "d2L": np.interp(E[selected], re, second),
    }
    return (
        selected,
        base,
        jump,
        reference,
        {
            "raw_pre_rows": (np.flatnonzero(pre) + 2).tolist(),
            "raw_post_rows": (np.flatnonzero(post) + 2).tolist(),
            "reference_pre_rows": (np.flatnonzero(rp) + 2).tolist(),
            "reference_post_rows": (np.flatnonzero(rq) + 2).tolist(),
        },
    )


def original_assignments(case):
    from .native import identity

    groups = [f"triplet-{i:02d}" for i in range(65)]
    held = set(
        sorted(groups, key=lambda g: hashlib.sha256(("P100-025-v1|" + g).encode()).hexdigest())[:13]
    )
    dev = set(
        sorted(
            set(groups) - held, key=lambda g: sha(["compact-v2", case, identity(case, "group", g)])
        )[:10]
    )
    return {g: "test" if g in held else "dev" if g in dev else "train" for g in groups}


def reconstruct_xas(recipe, source_root):
    from .native import _registered_groups, _row, _unique_object, identity

    (asset,) = [a for a in recipe["assets"] if a["role"] == "xas_archive"]
    (meta,) = [a for a in recipe["assets"] if a["role"] == "source_metadata"]
    metadata = json.loads(
        contained(source_root, meta["path"]).read_bytes(), object_pairs_hook=_unique_object
    )
    if (
        metadata["id"] != 14922524
        or metadata["doi"] != "10.5281/zenodo.14922524"
        or metadata["metadata"]["license"]["id"] != "cc-by-4.0"
        or recipe["input_units"] != INPUT_UNITS
        or recipe["output_units"] != "dimensionless μ(E)"
    ):
        raise ValueError("XAS source identity, metadata license or units differ")
    assignments = _registered_groups(recipe, original_assignments(recipe["scenario_id"]))
    if assignments != original_assignments(recipe["scenario_id"]):
        raise ValueError("Historical XAS triplet allocation changed")
    with bounded_zip(
        contained(source_root, asset["path"]), max_bytes=40_000_000, max_member_bytes=9_000_000
    ) as z:
        blobs = {n: z.read(n) for n in (RAW, REFERENCES, ASSIGNMENT, CLOCK)}
        a, refs = stored_spectra(blobs[RAW]), stored_spectra(blobs[REFERENCES], reference=True)
        protocol, clock = stored_assignment(blobs[ASSIGNMENT]), acquisition_clock(blobs[CLOCK])
    selected, base, jump, reference, bands = calibrated_panel(a, refs)
    reference_lineage = []
    for k in selected:
        right = int(np.searchsorted(refs[:, 0], a[k, 0]))
        if right < 3 or right + 2 >= len(refs):
            raise ValueError("Insufficient native reference derivative support")
        reference_lineage.append(
            {
                "raw_source_row": int(k) + 2,
                "energy_eV": float(a[k, 0]),
                "interpolation_reference_rows": [right + 1, right + 2],
                "first_gradient_reference_row_range": [right, right + 3],
                "second_gradient_reference_row_range": [right - 1, right + 4],
            }
        )
    parts, lineage, spectra, units = {p: [] for p in ("train", "dev", "test")}, [], [], {}
    for col in range(1, 195):
        group = f"triplet-{(col - 1) // 3:02d}"
        split = assignments[group]
        units[identity(recipe["scenario_id"], "group", group)] = group
        phase = 0 if col <= 107 else 1 if col <= 131 else 2 if col <= 170 else 3
        midpoint = (col - 0.5) * 300
        f = (
            float(np.clip(midpoint / protocol[0]["duration_s"], 0, 1))
            if phase < 2
            else float(
                np.clip(1 - (midpoint - protocol[1]["end_s"]) / protocol[2]["duration_s"], 0, 1)
            )
        )
        spectra.append(
            {
                "spectrum": col,
                "source_column": col + 1,
                "group": group,
                "split": split,
                "phase": protocol[phase]["name"],
                "nominal_midpoint_s": midpoint,
                "missing_source_row_ranges": row_ranges(
                    (np.flatnonzero(np.isnan(a[:, col])) + 2).tolist()
                ),
                "pre_count": int(np.isfinite(a[np.array(bands["raw_pre_rows"]) - 2, col]).sum()),
                "post_count": int(np.isfinite(a[np.array(bands["raw_post_rows"]) - 2, col]).sum()),
            }
        )
        for j, k in enumerate(selected):
            values = {
                "pre": float(base[col - 1]),
                "jump": float(jump[col - 1]),
                **{name: float(value[j]) for name, value in reference.items()},
                "f": f,
                "discharge": float(phase >= 2),
                "rest": float(phase % 2),
                "e": float(a[k, 0] - 7112),
            }
            row, source = _row(
                recipe["scenario_id"],
                f"spectrum-{col:03d}-energyrow-{k + 1}",
                group,
                split,
                values,
                a[k, col],
                {"spectrum": col, "source_row": int(k) + 2},
            )
            parts[split].append(row)
            lineage.append(source)
    return (
        parts,
        lineage,
        {
            "split_check": check_units(parts, units),
            "xas_spectra": spectra,
            "xas_validation": {
                "spectra": 194,
                "native_energy_rows": len(a),
                "native_measurement_cells": a[:, 1:].size,
                "finite_native_measurements": int(np.isfinite(a[:, 1:]).sum()),
                "missing_native_measurements": int(np.isnan(a[:, 1:]).sum()),
                "reference_energy_rows": len(refs),
                "selected_energy_rows": (selected + 2).tolist(),
                "eligible_rows": len(lineage),
                "group_counts": dict(Counter(assignments.values())),
                "last_triplet_spectra": 2,
                "calibration_bands": bands,
                "reference_lineage": reference_lineage,
                "protocol": protocol,
                "acquisition_clock": clock,
                "member_hashes": {n: hashlib.sha256(b).hexdigest() for n, b in blobs.items()},
                "fit_count": 0,
                "learned_transformations": [],
                "independence_scope": "Interleaved triplets from one cell/cycle; no independent cells, chronological forecast or state-of-charge identification",
                "legacy_five_folds_not_used_in_compact_split": True,
            },
            "lineage_definition": {
                "source": asset["path"],
                "raw_member": RAW,
                "reference_member": REFERENCES,
                "spectrum": "One-based acquisition column label; worksheet/file column spectrum+1",
                "source_row": "Physical line including one header; historical energyrow is source_row-1",
                "pre_jump": "Same spectrum finite means in fixed 7000..7050 and 7250..7300 eV bands; missing cells not imputed",
                "reference_features": "Each measured reference normalized by its own bands; LiFePO4 first/second np.gradient on native nonuniform grid, then linear interpolation at target energy; no endpoint extrapolation for selected rows",
                "reference_lineage": "One-based physical reference lines including header; interpolation pair and inclusive first/second-gradient support ranges, in addition to normalization bands",
                "f": "Clipped nominal 300s acquisition midpoint / charge duration, or 1-(midpoint-rest1_end)/discharge_duration; not independently measured state of charge",
                "target": "Stored raw mu(E); never exported for test",
                "excluded": "Binned spectra, XRD calculated intensities, CIF/EXAFS fits, electrochemical voltage/current/capacity responses",
            },
            "admission_blockers": [
                "One cell/cycle and shared measured references; triplet splits do not establish independent replication",
                "Same-spectrum pre/post-edge measurements and whole-cycle durations are permitted calibration, not online forecasts",
                "Nominal spectral midpoint is not a hardware synchronization timestamp; phase-boundary triplets may mix segments",
                "Source raw mu(E) already embodies spectroscopy reduction; detector-count processing is not reconstructed",
                "Rule-only complexity excludes reference normalization, numerical gradients and interpolation; full-pipeline complexity remains unassessed",
                "Rights/notices, calibrated uncertainty and final scientific admission remain pending",
            ],
        },
    )
