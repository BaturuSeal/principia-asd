"""Curator-only CARBCOMN penetration traces, never author-computed averages.

Keep mixture, age and batch lineage. The historical `time_s` field remains an
unresolved native index, not an asserted SI clock. No fitting or interpolation.
"""

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import PurePosixPath

from ..io import contained, sha
from .fracture import NS, REL, bounded_zip
from .memristor import column_number
from .splits import check_units

SHEET = "Slow penetration_Normal Force"
SHEETS = ["Flow table tests", SHEET, "Slow penetration_yield stress", "Queeze flow_Stress-strain"]
MIXES = [f"{a:.1f}_{w:.2f}" for a in (0.5, 0.7, 1.0) for w in (0.25, 0.30, 0.35)]
LABELS = ["Mix-" + m if m != "0.5_0.35" else "Mix-0.5_035" for m in MIXES]
INPUT_UNITS = {
    "age_min": "min since mixing; 0 or 30",
    "ratio": "mix-design ratio encoded in author mixture label",
    "time_s": "native penetration clock index; unit unspecified",
    "water": "water ratio encoded in author mixture label",
}


def stored_penetration(path):
    """Decode only stored measurements; formula/cached average columns are ignored."""
    from .native import _xml

    with bounded_zip(path, max_bytes=9_000_000, max_member_bytes=4_000_000) as z:
        sheets = _xml(z.read("xl/workbook.xml")).findall(f"{NS}sheets/{NS}sheet")
        if [s.get("name") for s in sheets] != SHEETS:
            raise ValueError("Unexpected slag worksheet inventory")
        links = _xml(z.read("xl/_rels/workbook.xml.rels"))
        matches = [r for r in links if r.get("Id") == sheets[1].get(REL + "id")]
        if len(matches) != 1 or matches[0].get("TargetMode") == "External":
            raise ValueError("Unresolved or external slag worksheet")
        target = PurePosixPath(matches[0].get("Target", ""))
        if target.is_absolute() or ".." in target.parts or "\\" in str(target):
            raise ValueError("Unsafe slag worksheet relationship")
        member = "xl/" + str(target)
        strings = []
        if "xl/sharedStrings.xml" in z.namelist():
            strings = [
                "".join(t.text or "" for t in item.iter(NS + "t"))
                for item in _xml(z.read("xl/sharedStrings.xml")).findall(NS + "si")
            ]
        tree = _xml(z.read(member))
        for merge in tree.findall(f"{NS}mergeCells/{NS}mergeCell"):
            m = re.fullmatch(r"[A-Z]+([0-9]+):[A-Z]+([0-9]+)", merge.get("ref", ""))
            if not m or (int(m[1]) <= 603 and int(m[2]) >= 4):
                raise ValueError("Merged or ambiguous slag measurement cells")
        rows, previous = {}, 0
        for row in tree.findall(f"{NS}sheetData/{NS}row"):
            number = int(row.attrib["r"])
            if number != previous + 1 or number > 607:
                raise ValueError("Missing, duplicate, reordered or extra slag source row")
            previous = number
            cells, seen = {}, set()
            for cell in row.findall(NS + "c"):
                match = re.fullmatch(r"([A-Z]+)([1-9][0-9]*)", cell.get("r", ""))
                if not match:
                    raise ValueError("Invalid slag cell address")
                col = column_number(match[1])
                if int(match[2]) != number or col in seen or not 2 <= col <= 56:
                    raise ValueError("Duplicate, mismatched or extra slag cell")
                seen.add(col)
                if 4 <= number <= 603 and col >= 3 and (col - 3) % 6 in (2, 5):
                    continue  # NF0/NF30 averages: neither values nor formulas enter the task.
                if cell.find(NS + "f") is not None:
                    raise ValueError("Formula in measured slag cell or identity")
                kind, value = cell.get("t", "n"), cell.findtext(NS + "v")
                if kind == "s":
                    index = int(value)
                    if not 0 <= index < len(strings):
                        raise ValueError("Invalid slag shared string")
                    value = strings[index]
                elif kind == "inlineStr":
                    value = "".join(t.text or "" for t in cell.iter(NS + "t"))
                elif kind not in {"n", "str"}:
                    raise ValueError("Unsupported slag cell type")
                if value is not None:
                    if 4 <= number <= 603:
                        if kind != "n":
                            raise ValueError("Nonnumeric slag measurement")
                        value = float(value)
                        if not math.isfinite(value):
                            raise ValueError("Nonfinite slag measurement; no implicit imputation")
                    cells[col] = value
            rows[number] = cells
        if previous != 607:
            raise ValueError("Incomplete slag workbook extent")
        expected = {1: {}, 2: {}, 3: {2: "time"}}
        names = ["NF1 (N)", "NF2 (N)", "NF0 (N)", "NF1 (N)", "NF2 (N)", "NF30 (N)"]
        for i, label in enumerate(LABELS):
            start = 3 + i * 6
            expected[1][start] = label
            expected[2].update({start: "T=0", start + 3: "T=30"})
            expected[3].update({start + j: name for j, name in enumerate(names)})
        if any(rows[k] != v for k, v in expected.items()):
            raise ValueError("Slag mixture, age, batch or force-unit header changed")
        # The source explicitly flags this mixture; never silently drop the note or its rows.
        if rows[604] != {27: "Incomplete"} or any(rows[k] for k in (605, 606, 607)):
            raise ValueError("Slag source quality annotation changed")
        columns = {2} | {3 + i * 6 + j for i in range(9) for j in (0, 1, 3, 4)}
        for number in range(4, 604):
            if rows[number].keys() != columns or rows[number][2] != number - 3:
                raise ValueError("Incomplete measurement panel or changed slag clock")
        return rows, member


def original_assignments(case):
    from .native import identity

    held = set(
        sorted(
            MIXES, key=lambda g: hashlib.sha256(("P100-ASD-B4-20261001:" + g).encode()).hexdigest()
        )[:2]
    )
    dev = set(
        sorted(
            set(MIXES) - held, key=lambda g: sha(["compact-v2", case, identity(case, "group", g)])
        )[:2]
    )
    return {g: "test" if g in held else "dev" if g in dev else "train" for g in MIXES}


def reconstruct_slag(recipe, source_root):
    from .native import _registered_groups, _row, _unique_object, identity

    (asset,) = [a for a in recipe["assets"] if a["role"] == "rheology_workbook"]
    (meta,) = [a for a in recipe["assets"] if a["role"] == "source_metadata"]
    metadata = json.loads(
        contained(source_root, meta["path"]).read_bytes(), object_pairs_hook=_unique_object
    )
    if (
        metadata["id"] != 17092152
        or metadata["doi"] != "10.5281/zenodo.17092152"
        or metadata["metadata"]["license"]["id"] != "cc-by-4.0"
        or recipe["input_units"] != INPUT_UNITS
        or recipe["output_units"] != "N"
    ):
        raise ValueError("Slag source identity, recorded metadata license or units differ")
    assignments = _registered_groups(recipe, MIXES)
    if assignments != original_assignments(recipe["scenario_id"]):
        raise ValueError("Historical whole-mixture allocation changed")
    measurements, member = stored_penetration(contained(source_root, asset["path"]))
    parts, lineage, traces, units = {s: [] for s in ("train", "dev", "test")}, [], [], {}
    serial = 0
    for i, group in enumerate(MIXES):
        ratio, water = map(float, group.split("_"))
        split = assignments[group]
        units[identity(recipe["scenario_id"], "group", group)] = group
        for age, offset in ((0, 0), (30, 3)):
            for rep in (0, 1):
                col = 3 + i * 6 + offset + rep
                trace = len(traces)
                traces.append(
                    {
                        "source": asset["path"],
                        "member": member,
                        "mixture": group,
                        "source_label": LABELS[i],
                        "age_min": age,
                        "batch_label": rep + 1,
                        "force_column": col,
                        "clock_column": 2,
                        "source_rows": [4, 603],
                        "split": split,
                        "quality_flag": "Incomplete" if group == "0.7_0.30" else None,
                    }
                )
                for number in range(4, 604):
                    row, source = _row(
                        recipe["scenario_id"],
                        f"P100-055-{serial:07}",
                        group,
                        split,
                        {
                            "ratio": ratio,
                            "water": water,
                            "age_min": float(age),
                            "time_s": measurements[number][2],
                        },
                        measurements[number][col],
                        {"trace_index": trace, "source_row": number},
                    )
                    parts[split].append(row)
                    lineage.append(source)
                    serial += 1
    return (
        parts,
        lineage,
        {
            "split_check": check_units(parts, units),
            "slag_traces": traces,
            "lineage_definition": {
                "trace_index": "Zero-based checks.slag_traces entry with one-based force/clock columns",
                "source_row": "One-based physical worksheet row",
                "target": "Stored individual NF1/NF2 force in N; never exported for test",
                "inputs": "Mixture label ratios, declared age 0/30 min, and native clock index only",
                "excluded": "Batch identity, all force/average/yield-stress values, other response sheets and fitted states",
            },
            "slag_validation": {
                "mixtures": 9,
                "individual_traces": len(traces),
                "samples_per_trace": 600,
                "eligible_rows": len(lineage),
                "group_counts": dict(Counter(assignments.values())),
                "excluded_average_cells": 10800,
                "fit_count": 0,
                "learned_transformations": [],
                "time_unit": "unresolved native index; historical field name time_s retained",
                "source_quality_flags": [
                    {
                        "mixture": "0.7_0.30",
                        "cell": "AA604",
                        "text": "Incomplete",
                        "scope": "Merged AA604:AF607 spans both ages and batches; reason unspecified",
                        "rows_retained": 2400,
                    }
                ],
                "label_alias": {"Mix-0.5_035": "0.5_0.35"},
                "workbook_mixture_missing_from_pdf_appendix": "1.0_0.25",
                "rights_evidence": {
                    "metadata": "CC BY 4.0",
                    "methods_pdf_page_1": "CC BY-NC-SA 4.0",
                    "status": "conflict_requires_review",
                },
                "independence_scope": "Nine mixture formulations; repeated time points and batches remain within mixture, not 21600 independent experiments",
            },
            "admission_blockers": [
                "Methods PDF and repository metadata conflict on source license; no redistribution authorization inferred",
                "Mixture 0.7_0.30 is source-flagged Incomplete; reason and affected measurements require clarification",
                "Workbook mixture 1.0_0.25 is absent from the source methods appendix",
                "Native clock unit and sampling interval are not established; no physical-rate claims",
                "Mixture labels omit varying admixtures and effective/total water distinctions; no causal identification",
                "Independent replication, valid perturbations and final scientific admission remain unassessed",
            ],
        },
    )
