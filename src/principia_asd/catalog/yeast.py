"""Curator-only cached qPCR percentages with same-replicate early calibration.

No spreadsheet evaluation, imputation, fitting, external-link access or Cp input.
The cached percentages are author-derived abundance estimates, not viable counts.
"""

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import PurePosixPath

from ..io import contained, sha
from .fracture import NS, REL, bounded_zip
from .splits import check_units

STRAINS = ["T73", "Chr96,2", "GRE", "QA23", "Clos", "Ec1118", "NCAIM", "D245"]
SHEETS = ["HPLC", "HPLCaa", *STRAINS]
INPUT_UNITS = {
    "p22_pct": "percentage points; own replicate at22h",
    "p72_pct": "percentage points; own replicate at72h",
    "time_h": "h since inoculation",
}


def columns(strain):
    return (
        ("E", "L", "O", "F", "G")
        if strain == "GRE"
        else ("D", "K", "M" if strain == "Clos" else "N", "E", "F")
    )


def _value(cell, strings, *, formula=False):
    if cell is None:
        return None
    if not formula and cell.find(NS + "f") is not None:
        raise ValueError("Unexpected formula in yeast identity or stored ratio")
    kind, value = cell.get("t", "n"), cell.findtext(NS + "v")
    if kind == "s":
        index = int(value)
        if not 0 <= index < len(strings):
            raise ValueError("Invalid yeast shared string")
        return strings[index]
    if kind == "inlineStr":
        return "".join(t.text or "" for t in cell.iter(NS + "t"))
    if kind != "n":
        raise ValueError("Unsupported yeast cell type")
    if value is None:
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Nonfinite yeast measurement")
    return result


def _percentage(cell, row, ratio_col, pct_col, masters, strings):
    formula = cell.find(NS + "f") if cell is not None else None
    if formula is None:
        raise ValueError("Missing yeast percentage formula")
    kind = formula.get("t", "normal")
    expected = f"({ratio_col}{row}*100)/({ratio_col}{row}+1)"
    if kind not in {"normal", "shared"}:
        raise ValueError("Unsupported yeast formula kind")
    if formula.text:
        if formula.text != expected:
            raise ValueError("Percentage must use only the same-row stored qPCR ratio")
        if kind == "shared":
            si = formula.get("si")
            bounds = re.fullmatch(rf"{pct_col}([0-9]+):{pct_col}([0-9]+)", formula.get("ref", ""))
            if (
                si is None
                or si in masters
                or not bounds
                or int(bounds[1]) != row
                or not row <= int(bounds[2]) <= 17
            ):
                raise ValueError("Invalid yeast shared formula master")
            masters[si] = (row, int(bounds[2]))
    else:
        bounds = masters.get(formula.get("si"))
        if kind != "shared" or not bounds or not bounds[0] < row <= bounds[1]:
            raise ValueError("Unresolved yeast shared formula")
    value = _value(cell, strings, formula=True)
    if not isinstance(value, float) or not 0 <= value <= 100:
        raise ValueError("Invalid or missing cached yeast percentage")
    return value


def stored_qpcr(path):
    """Read bounded XML; only an exact local percentage formula is recognized."""
    from .native import _xml

    samples, ambiguities, max_error = {}, [], 0.0
    with bounded_zip(path, max_bytes=2_000_000, max_member_bytes=1_000_000) as z:
        book = _xml(z.read("xl/workbook.xml"))
        sheets = book.findall(f"{NS}sheets/{NS}sheet")
        if [s.get("name") for s in sheets] != SHEETS:
            raise ValueError("Unexpected yeast worksheet inventory")
        links = _xml(z.read("xl/_rels/workbook.xml.rels"))
        strings = []
        if "xl/sharedStrings.xml" in z.namelist():
            strings = [
                "".join(t.text or "" for t in item.iter(NS + "t"))
                for item in _xml(z.read("xl/sharedStrings.xml")).findall(NS + "si")
            ]
        for s in sheets[2:]:
            strain = s.get("name")
            if s.get("state", "visible") != "visible":
                raise ValueError("Hidden yeast measurement sheet")
            matches = [r for r in links if r.get("Id") == s.get(REL + "id")]
            if len(matches) != 1 or matches[0].get("TargetMode") == "External":
                raise ValueError("External or unresolved yeast worksheet")
            target = PurePosixPath(matches[0].get("Target", ""))
            if (
                target.is_absolute()
                or ".." in target.parts
                or "\\" in str(target)
                or not str(target).startswith("worksheets/")
            ):
                raise ValueError("Unsafe yeast worksheet relationship")
            member = "xl/" + str(target)
            tree = _xml(z.read(member))
            cells, previous = {}, 0
            for r in tree.findall(f"{NS}sheetData/{NS}row"):
                number = int(r.attrib["r"])
                if not previous < number <= 1000 or (
                    3 <= number <= 17 and r.get("hidden", "0") != "0"
                ):
                    raise ValueError("Duplicate, reordered or hidden yeast row")
                previous = number
                for cell in r.findall(NS + "c"):
                    address = cell.get("r", "")
                    m = re.fullmatch(r"[A-Z]{1,2}([1-9][0-9]*)", address)
                    if not m or int(m[1]) != number or address in cells:
                        raise ValueError("Invalid or duplicate yeast cell")
                    cells[address] = cell
            sample_col, ratio_col, pct_col, target_col, reference_col = columns(strain)
            if (
                _value(cells.get(sample_col + "2"), strings) != "Sample Name"
                or _value(cells.get(ratio_col + "2"), strings) != "Target/Ref"
            ):
                raise ValueError("Changed yeast sample/ratio header")
            chart_rows = {}
            for merge in tree.findall(f"{NS}mergeCells/{NS}mergeCell"):
                m = re.fullmatch(r"([A-Z]+)([0-9]+):([A-Z]+)([0-9]+)", merge.get("ref", ""))
                if not m:
                    raise ValueError("Invalid yeast merged-cell range")
                start, end = int(m[2]), int(m[4])
                if start <= 17 and end >= 3:
                    if m[1] != m[3] or m[1] not in ({"B", "D"} if strain == "GRE" else {"B"}):
                        raise ValueError("Merged yeast measurement or identity")
                    if m[1] == "B":
                        for row in range(start, end + 1):
                            if row in chart_rows:
                                raise ValueError("Overlapping yeast clock ranges")
                            chart_rows[row] = start
            observed, masters = {}, {}
            for address, cell in cells.items():
                if not re.fullmatch(rf"{sample_col}[0-9]+", address):
                    continue
                row = int(address[len(sample_col) :])
                name = _value(cell, strings)
                match = re.fullmatch(r"R([123])([0-9]+)", str(name))
                if not match:
                    if 3 <= row <= (16 if strain in {"Chr96,2", "Clos", "Ec1118"} else 17):
                        raise ValueError("Missing yeast sample identity")
                    continue
                if not 3 <= row <= 17:
                    raise ValueError("Unexpected extra yeast sample")
                rep, time = int(match[1]), int(match[2])
                if (rep, time) in observed:
                    raise ValueError("Duplicate yeast replicate/time identity")
                if (
                    _value(cells.get(target_col + str(row)), strings) != "BUDk"
                    or _value(cells.get(reference_col + str(row)), strings) != "BUDc"
                ):
                    raise ValueError("Changed yeast target/reference identity")
                ratio = _value(cells.get(ratio_col + str(row)), strings)
                if not isinstance(ratio, float) or ratio < 0:
                    raise ValueError("Missing or invalid stored qPCR ratio")
                pct = _percentage(
                    cells.get(pct_col + str(row)), row, ratio_col, pct_col, masters, strings
                )
                error = abs(pct - 100 * ratio / (ratio + 1))
                if error > 1e-10:
                    raise ValueError("Cached percentage disagrees with stored qPCR ratio")
                max_error = max(error, max_error)
                chart_cell = cells.get("B" + str(chart_rows.get(row, row)))
                clock = _value(chart_cell, strings)
                cm = (
                    re.fullmatch(r"\s*([0-9]+)\s*(?:h)?\s*", str(clock))
                    if isinstance(clock, str)
                    else None
                )
                chart = int(cm[1]) if cm else clock
                if not isinstance(chart, (int, float)) or chart != int(chart):
                    raise ValueError("Invalid yeast chart time")
                record = {
                    "percentage": pct,
                    "row": row,
                    "member": member,
                    "percentage_cell": pct_col + str(row),
                    "ratio_cell": ratio_col + str(row),
                    "sample_cell": address,
                    "chart_cell": "B" + str(chart_rows.get(row, row)),
                    "chart_time_h": chart,
                }
                observed[rep, time] = record
                if chart != time:
                    ambiguities.append(
                        {
                            "strain": strain,
                            "row": row,
                            "replicate": rep,
                            "sample_time_h": time,
                            "chart_time_h": chart,
                        }
                    )
            expected = 14 if strain in {"Chr96,2", "Clos", "Ec1118"} else 15
            if len(observed) != expected:
                raise ValueError("Incomplete yeast sample panel")
            samples[strain] = observed
        return (
            samples,
            ambiguities,
            {
                "cached_percentage_max_absolute_error": max_error,
                "external_references_not_followed": len(
                    book.findall(f"{NS}externalReferences/{NS}externalReference")
                ),
            },
        )


def original_assignments(case):
    from .native import identity

    seed = "principia-ASD-batch3-20260930-before-fit-v1|72strain"
    held = set(sorted(STRAINS, key=lambda s: hashlib.sha256((seed + s).encode()).hexdigest())[:2])
    dev = set(
        sorted(
            set(STRAINS) - held, key=lambda s: sha(["compact-v2", case, identity(case, "group", s)])
        )[:2]
    )
    return {s: "test" if s in held else "dev" if s in dev else "train" for s in STRAINS}


def reconstruct_yeast(recipe, source_root):
    from .native import _registered_groups, _row, _unique_object, identity

    (asset,) = [a for a in recipe["assets"] if a["role"] == "qpcr_workbook"]
    (meta,) = [a for a in recipe["assets"] if a["role"] == "source_metadata"]
    metadata = json.loads(
        contained(source_root, meta["path"]).read_bytes(), object_pairs_hook=_unique_object
    )
    if (
        metadata["id"] != 18757697
        or metadata["doi"] != "10.5281/zenodo.18757697"
        or metadata["metadata"]["license"]["id"] != "cc-by-4.0"
        or recipe["input_units"] != INPUT_UNITS
        or recipe["output_units"] != "percentage points"
    ):
        raise ValueError("Yeast source identity, recorded license or units changed")
    case = recipe["scenario_id"]
    assignments = _registered_groups(recipe, STRAINS)
    if assignments != original_assignments(case):
        raise ValueError("Historical whole-strain allocation changed")
    source, ambiguities, cache = stored_qpcr(contained(source_root, asset["path"]))
    parts, lineage, missing, units = {s: [] for s in ("train", "dev", "test")}, [], [], {}
    eligible_replicates = 0
    for strain, all_samples in source.items():
        split = assignments[strain]
        units[identity(case, "group", strain)] = strain
        samples = {k: v for k, v in all_samples.items() if k[1] == v["chart_time_h"]}
        for rep in (1, 2, 3):
            if any((rep, t) not in samples for t in (22, 72)):
                missing.append(
                    {
                        "strain": strain,
                        "replicate": rep,
                        "missing_hours": [t for t in (22, 72) if (rep, t) not in samples],
                        "excluded_later_rows": sum(r == rep and t >= 96 for r, t in samples),
                    }
                )
                continue
            eligible_replicates += 1
            early = [samples[rep, t] for t in (22, 72)]
            for (r, time), measurement in samples.items():
                if r != rep or time < 96:
                    continue
                anchor = {
                    "source": asset["path"],
                    "strain": strain,
                    "replicate": rep,
                    "response": {k: v for k, v in measurement.items() if k != "percentage"},
                    "early_measurement_cells": [e["percentage_cell"] for e in early],
                    "early_hours": [22, 72],
                    "forecast_time_h": time,
                }
                row, trace = _row(
                    case,
                    f"{strain}:row{measurement['row']}",
                    strain,
                    split,
                    {
                        "p22_pct": early[0]["percentage"],
                        "p72_pct": early[1]["percentage"],
                        "time_h": float(time),
                    },
                    measurement["percentage"],
                    anchor,
                )
                parts[split].append(row)
                lineage.append(trace)
    return (
        parts,
        lineage,
        {
            "split_check": check_units(parts, units),
            "yeast_validation": {
                **cache,
                "native_sample_rows": sum(map(len, source.values())),
                "eligible_rows": len(lineage),
                "calibrated_replicates": eligible_replicates,
                "group_counts": dict(Counter(assignments.values())),
                "missing_prefix": missing,
                "excluded_ambiguous_time": ambiguities,
                "fit_count": 0,
                "learned_transformations": [],
                "response_scope": "Author cached same-row qPCR ratio percentage, not viable count or fitness",
                "acquisition_chronology": "Native qPCR exports 2020; workbook analyses 2021/2022; public deposit 2026",
                "exposure": "Retrospective, historically audit-exposed including later percentages; not independent confirmation",
            },
            "lineage_definition": {
                "early_measurement_cells": "Own biological replicate 22h/72h cells; no same-time Cp, ratio, averages or future response inputs",
                "response": "Local percentage formula and cached value verified; test value omitted from all exported rows and lineage",
                "independent_unit": "Whole co-cultured S.cerevisiae strain across all replicates and times",
            },
            "admission_blockers": [
                "Scientific contract, rights and notices require new edition review",
                "Only eight strain groups and two test strains; early qPCR calibration required",
                "qPCR percentages are derived estimates; no competition mechanism, viability or causal fitness claim",
                "Unresolved nitrogen description and stale percentage headers; unused or explicitly disclosed",
                "Native calibration/extraction complexity and uncertainty are outside frozen rule complexity; perturbations remain diagnostic",
            ],
        },
    )
