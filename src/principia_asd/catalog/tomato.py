"""Curator-only stored tomato phenotypes, with explicit plant/measurement custody.

No image feature extraction, spreadsheet execution, imputation or fitted state.
The source's fluorescence indices are derived measurements, not independent sensors.
"""

import math
import re
from collections import Counter, defaultdict
from pathlib import PurePosixPath

from ..io import contained, read_json
from .fracture import NS, REL, bounded_zip
from .splits import check_units

INPUT_UNITS = {
    "area": "source AREA_MM scale; only relative/log descriptor used",
    "drought": "drought-treatment indicator",
    "high_stress": "source second stress-level indicator; no invented dose units",
    "ngrdi": "dimensionless RGB index",
    "npq": "dimensionless author NPQ_Lss",
    "rfd": "dimensionless author Rfd_Lss",
    "salt": "salt-treatment indicator",
    "tiny": "cultivar indicator",
}
PHENOTYPES = {
    "A": "DAS",
    "B": "DAG",
    "C": "Sampling",
    "D": "Plant ID",
    "F": "Cultivar",
    "G": "AREA_MM",
    "W": "NGRDI",
    "Y": "QY_max",
    "Z": "NPQ_Lss",
    "AA": "Rfd_Lss",
}
METADATA = {
    "A": "Measuring Date",
    "B": "DAG",
    "C": "DAS",
    "D": "Experiment ID",
    "E": "Round Order",
    "F": "Plant ID",
    "G": "Treatment",
    "H": "Genotype",
}
GENOTYPES = {"Micro-Tom", "Tiny Tim"}
TREATMENTS = {"Ctrl", "Salt 01", "Salt 02", "Drought 01", "Drought 02"}


def stored_table(path, name, header_row, columns):
    """Bounded XML reader. Reject formulas/hidden/merged selected measurements."""
    from .native import _xml

    with bounded_zip(path, max_bytes=2_000_000, max_member_bytes=1_000_000) as z:
        book = _xml(z.read("xl/workbook.xml"))
        sheets = book.findall(f"{NS}sheets/{NS}sheet")
        if len(sheets) != 1 or sheets[0].get("name") != name:
            raise ValueError("Changed tomato worksheet inventory")
        if sheets[0].get("state", "visible") != "visible":
            raise ValueError("Hidden tomato worksheet")
        links = _xml(z.read("xl/_rels/workbook.xml.rels"))
        matches = [r for r in links if r.get("Id") == sheets[0].get(REL + "id")]
        if len(matches) != 1 or matches[0].get("TargetMode") == "External":
            raise ValueError("Unresolved or external tomato worksheet")
        target = PurePosixPath(matches[0].get("Target", ""))
        if (
            target.is_absolute()
            or ".." in target.parts
            or "\\" in str(target)
            or not str(target).startswith("worksheets/")
        ):
            raise ValueError("Unsafe tomato worksheet relationship")
        member = "xl/" + str(target)
        tree = _xml(z.read(member))
        selected_indices = {
            sum((ord(ch) - 64) * 26**i for i, ch in enumerate(reversed(col))) for col in columns
        }
        for col in tree.findall(f"{NS}cols/{NS}col"):
            if col.get("hidden", "0") != "0" and any(
                int(col.get("min", "0")) <= index <= int(col.get("max", "0"))
                for index in selected_indices
            ):
                raise ValueError("Hidden tomato measurement column")
        if tree.findall(f"{NS}mergeCells/{NS}mergeCell"):
            raise ValueError("Merged tomato measurements are unsupported")
        strings = []
        if "xl/sharedStrings.xml" in z.namelist():
            strings = [
                "".join(t.text or "" for t in item.iter(NS + "t"))
                for item in _xml(z.read("xl/sharedStrings.xml")).findall(NS + "si")
            ]
        out, previous, header = {}, 0, None
        for r in tree.findall(f"{NS}sheetData/{NS}row"):
            number = int(r.attrib["r"])
            if not previous < number <= 1000 or r.get("hidden", "0") != "0":
                raise ValueError("Duplicate, reordered, hidden or excessive tomato row")
            previous = number
            if number < header_row:
                continue
            row, seen = {}, set()
            for c in r.findall(NS + "c"):
                address = c.get("r", "")
                match = re.fullmatch(r"([A-Z]{1,2})([1-9][0-9]*)", address)
                if not match or int(match[2]) != number or address in seen:
                    raise ValueError("Invalid or duplicate tomato cell")
                seen.add(address)
                col = match[1]
                if col not in columns:
                    continue
                if c.find(NS + "f") is not None:
                    raise ValueError("Formula in selected tomato cell")
                kind, v = c.get("t", "n"), c.findtext(NS + "v")
                if kind == "s":
                    index = int(v)
                    if not 0 <= index < len(strings):
                        raise ValueError("Invalid tomato shared string")
                    value = strings[index]
                elif kind == "inlineStr":
                    value = "".join(t.text or "" for t in c.iter(NS + "t"))
                elif kind == "n":
                    value = None if v is None else float(v)
                    if value is not None and not math.isfinite(value):
                        raise ValueError("Nonfinite tomato measurement")
                else:
                    raise ValueError("Unsupported tomato cell type")
                row[col] = value
            if number == header_row:
                header = row
                if row != columns:
                    raise ValueError("Changed tomato measurement headers")
            elif row:
                out[number] = row
        if header is None or not out:
            raise ValueError("Missing tomato measurement table")
        return out, member


def _number(value, label, *, integer=False):
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or (integer and value != int(value))
    ):
        raise ValueError("Invalid tomato " + label)
    return value


def reconstruct_tomato(recipe, source_root):
    from .native import _registered_groups, _row, identity

    case = recipe["scenario_id"]
    if (
        recipe["input_units"] != INPUT_UNITS
        or recipe["output_units"] != "dimensionless quantum yield"
    ):
        raise ValueError("Changed tomato unit declarations")
    assets = {a["role"]: a for a in recipe["assets"]}
    if len(assets) != len(recipe["assets"]) or set(assets) != {
        "phenotype_workbook",
        "metadata_workbook",
        "source_metadata",
    }:
        raise ValueError("Invalid tomato source inventory")
    meta = read_json(contained(source_root, assets["source_metadata"]["path"]))
    if (
        str(meta.get("id")) != "20638584"
        or meta.get("doi") != "10.5281/zenodo.20638584"
        or meta["metadata"]["license"]["id"] != "cc-by-4.0"
    ):
        raise ValueError("Changed tomato source identity or rights metadata")
    phenotypes, member = stored_table(
        contained(source_root, assets["phenotype_workbook"]["path"]), "Sheet1", 3, PHENOTYPES
    )
    metadata, meta_member = stored_table(
        contained(source_root, assets["metadata_workbook"]["path"]), "Index", 1, METADATA
    )
    plants, measurements, batches = {}, {}, defaultdict(set)
    for number, r in metadata.items():
        plant, cultivar, treatment = r.get("F"), r.get("H"), r.get("G")
        if (
            not isinstance(plant, str)
            or not plant.strip()
            or cultivar not in GENOTYPES
            or treatment not in TREATMENTS
        ):
            raise ValueError("Unknown tomato plant, cultivar or treatment")
        age = _number(r.get("B"), "metadata DAG", integer=True)
        day = _number(r.get("C"), "metadata DAS", integer=True)
        experiment = _number(r.get("D"), "experiment identity", integer=True)
        _number(r.get("E"), "round order", integer=True)
        _number(r.get("A"), "native acquisition date")
        descriptor = (cultivar, treatment, experiment)
        if plant in plants and plants[plant] != descriptor:
            raise ValueError("Conflicting tomato plant identity or assignment")
        plants[plant] = descriptor
        key = (plant, day)
        if key in measurements:
            raise ValueError("Ambiguous tomato plant/day acquisition")
        measurements[key] = (number, age)
        batches[str(int(experiment))].add(cultivar)
    assignments = _registered_groups(recipe, plants)
    parts, lineage, exclusions, age_conflicts = (
        {p: [] for p in ("train", "dev", "test")},
        [],
        [],
        [],
    )
    seen, observed = set(), set()
    for number, r in phenotypes.items():
        plant = r.get("D")
        if plant not in plants:
            raise ValueError("Unregistered tomato phenotype plant")
        cultivar, treatment, experiment = plants[plant]
        day = _number(r.get("A"), "phenotype DAS", integer=True)
        age = _number(r.get("B"), "phenotype DAG", integer=True)
        key = (plant, day)
        if key in seen or key not in measurements or r.get("F") != cultivar:
            raise ValueError("Duplicate, unlinked or conflicting tomato phenotype")
        seen.add(key)
        meta_row, meta_age = measurements[key]
        if age != meta_age:
            age_conflicts.append(
                {
                    "phenotype_row": number,
                    "metadata_row": meta_row,
                    "phenotype_DAG": age,
                    "metadata_DAG": meta_age,
                }
            )
        if r.get("C") not in {"Before", "No", "Midpoint", "Endpoint"}:
            raise ValueError("Unknown tomato sampling annotation")
        missing = [c for c in ["Y", "Z", "AA", "W", "G"] if r.get(c) is None]
        if missing:
            exclusions.append({"row": number, "missing_columns": missing})
            continue
        for c in ["Y", "Z", "AA", "W", "G"]:
            _number(r[c], "numeric phenotype")
        if not 0 <= r["Y"] <= 1 or r["G"] <= 0:
            raise ValueError("Invalid tomato quantum yield or area domain")
        observed.add(plant)
        split = assignments[plant]
        row, trace = _row(
            case,
            f"{plant}:native-row{number}",
            plant,
            split,
            {
                "npq": r["Z"],
                "rfd": r["AA"],
                "ngrdi": r["W"],
                "area": r["G"],
                "tiny": float(cultivar == "Tiny Tim"),
                "salt": float(treatment.startswith("Salt")),
                "drought": float(treatment.startswith("Drought")),
                "high_stress": float(treatment.endswith("02")),
            },
            r["Y"],
            {
                "source": assets["phenotype_workbook"]["path"],
                "member": member,
                "row": number,
                "plant": plant,
                "input_cells": {
                    k: f"{v}{number}"
                    for k, v in {"npq": "Z", "rfd": "AA", "ngrdi": "W", "area": "G"}.items()
                },
                "response_cell": f"Y{number}",
                "metadata_source": assets["metadata_workbook"]["path"],
                "metadata_member": meta_member,
                "metadata_row": meta_row,
                "metadata_indicator_cells": [f"G{meta_row}", f"H{meta_row}"],
                "sampling": r["C"],
                "source_DAS": day,
                "source_DAG": age,
                "metadata_DAG": meta_age,
                "experiment_id": int(experiment),
            },
        )
        parts[split].append(row)
        lineage.append(trace)
    if seen != measurements.keys() or observed != plants.keys():
        raise ValueError("Unmatched tomato source observations or empty plant group")
    return (
        parts,
        lineage,
        {
            "split_check": check_units(parts, {identity(case, "group", g): g for g in plants}),
            "tomato_validation": {
                "native_phenotype_rows": len(phenotypes),
                "native_metadata_rows": len(metadata),
                "eligible_rows": len(lineage),
                "plants": len(plants),
                "plant_counts_by_split": dict(Counter(assignments.values())),
                "excluded_incomplete_rows": exclusions,
                "age_annotation_conflicts": age_conflicts,
                "acquisition_experiments_and_cultivars": {
                    k: sorted(v) for k, v in sorted(batches.items())
                },
                "fit_count": 0,
                "learned_transformations": [],
                "image_extraction_performed": False,
                "response_scope": "Author-derived QY_max predicted from contemporaneous source-derived measurements; fluorescence calibration and shared quantities not independently verified",
                "exposure": "Retrospective and historically audit-exposed; no independent confirmation",
            },
            "lineage_definition": {
                "identity": "Exact plant ID and one-to-one stored plant/DAS match; DAS retained as a source label, not an independently verified clock",
                "response": "Stored same-row QY_max; no target value in test rows or lineage",
                "inputs": "Only selected contemporaneous table measurements and known cultivar/treatment; no imputation or image extraction",
                "independent_unit": "Whole plant across repeated sampling; experiment/cultivar shared across splits",
            },
            "admission_blockers": [
                "Source-rights, attribution and scientific-contract review remain pending",
                "Image extraction, fluorescence shared-quantity dependence and calibration provenance are not verified",
                "Age annotations disagree; timing is not a predictor and no longitudinal forecast is established",
                "Two acquisition experiments align with cultivars; plant holdout does not establish site, experiment or cultivar transfer",
                "Full preprocessing complexity and measurement-noise stability remain unassessed",
            ],
        },
    )
