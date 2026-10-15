import json
import zipfile
from copy import deepcopy
from xml.etree import ElementTree as ET

import pytest

from principia_asd.catalog.fracture import NS, REL
from principia_asd.catalog.native import identity, reconstruct
from principia_asd.catalog.yeast import (
    INPUT_UNITS,
    SHEETS,
    STRAINS,
    columns,
    original_assignments,
    reconstruct_yeast,
    stored_qpcr,
)
from principia_asd.io import file_sha


def workbook():
    book = ET.Element(NS + "workbook")
    sheets = ET.SubElement(book, NS + "sheets")
    links = ET.Element("Relationships")
    entries = {"xl/workbook.xml": book, "xl/_rels/workbook.xml.rels": links}
    external = ET.SubElement(book, NS + "externalReferences")
    ET.SubElement(external, NS + "externalReference", {REL + "id": "external"})
    # Deliberately nonexistent external source. Reading it would fail the fixture.
    ET.SubElement(
        links,
        "Relationship",
        {
            "Id": "external",
            "TargetMode": "External",
            "Target": "https://invalid.test/do-not-follow.xlsx",
        },
    )
    for i, name in enumerate(SHEETS, 1):
        ET.SubElement(sheets, NS + "sheet", {"name": name, REL + "id": f"rId{i}"})
        if i < 3:
            continue  # Unrelated HPLC sheets are deliberately absent.
        ET.SubElement(
            links, "Relationship", {"Id": f"rId{i}", "Target": f"worksheets/sheet{i}.xml"}
        )
        sheet = ET.Element(NS + "worksheet")
        data = ET.SubElement(sheet, NS + "sheetData")
        merges = ET.SubElement(sheet, NS + "mergeCells")
        entries[f"xl/worksheets/sheet{i}.xml"] = sheet
        sample, ratio, pct, target, reference = columns(name)

        def add(row, col, value, formula=None):
            c = ET.SubElement(row, NS + "c", {"r": col + row.get("r")})
            if isinstance(value, str):
                c.set("t", "inlineStr")
                ET.SubElement(ET.SubElement(c, NS + "is"), NS + "t").text = value
            else:
                ET.SubElement(c, NS + "v").text = str(value)
            if formula:
                text, attrs = formula
                ET.SubElement(c, NS + "f", attrs).text = text

        header = ET.SubElement(data, NS + "row", {"r": "2"})
        add(header, sample, "Sample Name")
        add(header, ratio, "Target/Ref")
        times = {
            "T73": [22, 72, 96, 260, 336],
            "Chr96,2": [22, 72, 96, 216, 260],
            "GRE": [22, 72, 96, 336, 432],
            "QA23": [22, 72, 168, 384, 504],
            "Clos": [22, 72, 96, 260, 336],
            "Ec1118": [22, 72, 168, 432, 504],
            "NCAIM": [22, 72, 96, 216, 260],
            "D245": [22, 72, 96, 216, 336],
        }[name]
        number = 3
        last = 16 if name in {"Chr96,2", "Clos", "Ec1118"} else 17
        for time in times:
            first = number
            for rep in [1, 3, 2] if name == "GRE" and time == 432 else [1, 2, 3]:
                if (name, rep, time) in {("Chr96,2", 2, 72), ("Clos", 1, 22), ("Ec1118", 2, 22)}:
                    continue
                row = ET.SubElement(data, NS + "row", {"r": str(number)})
                if number == first:
                    clock = 500 if name == "Ec1118" and time == 504 else time
                    add(row, "B", f"{clock} h " if name == "GRE" else clock)
                add(row, sample, f"R{rep}{time}")
                add(row, target, "BUDk")
                add(row, reference, "BUDc")
                value = 0.5 + rep / 10 + time / 1000
                add(row, ratio, value)
                formula = (
                    (
                        f"({ratio}{number}*100)/({ratio}{number}+1)",
                        {"t": "shared", "si": "0", "ref": f"{pct}3:{pct}{last}"},
                    )
                    if number == 3
                    else (None, {"t": "shared", "si": "0"})
                )
                if number == 7:
                    formula = (f"({ratio}7*100)/({ratio}7+1)", {})
                add(row, pct, 100 * value / (value + 1), formula)
                number += 1
            ET.SubElement(merges, NS + "mergeCell", {"ref": f"B{first}:B{number - 1}"})
    return entries


@pytest.fixture(scope="module")
def original():
    return workbook()


def save(tmp_path, entries):
    path = tmp_path / "qpcr.xlsx"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, tree in entries.items():
            z.writestr(name, ET.tostring(tree))
    return path


def sheet(entries, strain="T73"):
    return entries[f"xl/worksheets/sheet{STRAINS.index(strain) + 3}.xml"]


def cell(entries, address, strain="T73"):
    return sheet(entries, strain).find(f".//{NS}c[@r='{address}']")


def set_percentage(entries, row, ratio, strain="T73"):
    _, rc, pc, _, _ = columns(strain)
    cell(entries, rc + str(row), strain).find(NS + "v").text = str(ratio)
    cell(entries, pc + str(row), strain).find(NS + "v").text = str(100 * ratio / (ratio + 1))


def recipe(tmp_path, entries):
    path = save(tmp_path, entries)
    meta = tmp_path / "metadata.json"
    meta.write_text(
        json.dumps(
            {
                "id": 18757697,
                "doi": "10.5281/zenodo.18757697",
                "metadata": {"license": {"id": "cc-by-4.0"}},
            }
        )
    )
    return {
        "schema_version": "native-reconstruction/1",
        "scenario_id": "P100-072",
        "parser": "yeast-native-calibrated-qpcr-v1",
        "input_units": INPUT_UNITS.copy(),
        "output_units": "percentage points",
        "group_assignments": original_assignments("P100-072"),
        "assets": [
            {"path": p.name, "role": role, "sha256": file_sha(p), "bytes": p.stat().st_size}
            for p, role in [(path, "qpcr_workbook"), (meta, "source_metadata")]
        ],
    }


def test_exact_panel_pairing_exclusions_and_external_reference(tmp_path, original):
    parts, lineage, checks = reconstruct(recipe(tmp_path, original), tmp_path)
    assert {s: len(v) for s, v in parts.items()} == {"train": 25, "dev": 18, "test": 18}
    assert checks["split_check"]["valid"] and len(lineage) == 61
    audit = checks["yeast_validation"]
    assert audit["native_sample_rows"] == 117 and audit["calibrated_replicates"] == 21
    assert (
        len(audit["missing_prefix"]) == 3
        and sum(r["excluded_later_rows"] for r in audit["missing_prefix"]) == 8
    )
    assert len(audit["excluded_ambiguous_time"]) == 3
    assert audit["external_references_not_followed"] == 1
    assert audit["fit_count"] == 0 and audit["learned_transformations"] == []
    assert all("target" not in r for r in parts["test"])
    assert "percentage" not in json.dumps(lineage).replace("percentage_cell", "")
    gre = next(
        r for r in parts["dev"] if r["sample_id"] == identity("P100-072", "sample", "GRE:row16")
    )
    ratio = 0.5 + 3 / 10 + 22 / 1000
    assert gre["p22_pct"] == 100 * ratio / (ratio + 1)  # Biological rep3, not row-position rep2.


@pytest.mark.parametrize("strain", ["T73", "NCAIM"])
def test_later_response_cannot_change_predictors(tmp_path, original, strain):
    r = recipe(tmp_path, original)
    before, _, _ = reconstruct_yeast(r, tmp_path)
    edited = deepcopy(original)
    set_percentage(edited, 9, 20, strain)
    save(tmp_path, edited)
    after, _, _ = reconstruct_yeast(r, tmp_path)
    assert [
        {k: v for k, v in row.items() if k != "target"} for rows in before.values() for row in rows
    ] == [
        {k: v for k, v in row.items() if k != "target"} for rows in after.values() for row in rows
    ]
    if strain == "T73":
        assert before == after
    else:
        assert before != after


def test_early_calibration_changes_only_own_replicate(tmp_path, original):
    r = recipe(tmp_path, original)
    before, _, _ = reconstruct_yeast(r, tmp_path)
    edited = deepcopy(original)
    set_percentage(edited, 3, 20)
    save(tmp_path, edited)
    after, _, _ = reconstruct_yeast(r, tmp_path)
    assert before["train"] == after["train"] and before["dev"] == after["dev"]
    changed = [a["sample_id"] for a, b in zip(before["test"], after["test"], strict=True) if a != b]
    assert set(changed) == {identity("P100-072", "sample", f"T73:row{row}") for row in [9, 12, 15]}


@pytest.mark.parametrize(
    "fault",
    [
        "formula_future",
        "formula_external",
        "cache",
        "ratio_formula",
        "nonfinite",
        "sample_duplicate",
        "cell_duplicate",
        "hidden",
        "target_reference",
        "clock_merge",
        "shared_missing",
        "shared_range",
        "external_sheet",
        "traversal",
        "missing_sample",
    ],
)
def test_reject_corrupted_measurement_or_lineage(tmp_path, original, fault):
    entries = deepcopy(original)
    if fault.startswith("formula_"):
        cell(entries, "N3").find(NS + "f").text = (
            "(K9*100)/(K9+1)" if fault == "formula_future" else "[1]Sheet!A1"
        )
    elif fault == "cache":
        cell(entries, "N3").find(NS + "v").text = "99"
    elif fault == "ratio_formula":
        ET.SubElement(cell(entries, "K3"), NS + "f").text = "K9"
    elif fault == "nonfinite":
        cell(entries, "K3").find(NS + "v").text = "NaN"
    elif fault == "sample_duplicate":
        cell(entries, "D4").find(f"{NS}is/{NS}t").text = "R122"
    elif fault == "cell_duplicate":
        sheet(entries).find(f"{NS}sheetData/{NS}row[@r='3']").append(deepcopy(cell(entries, "D3")))
    elif fault == "hidden":
        sheet(entries).find(f"{NS}sheetData/{NS}row[@r='3']").set("hidden", "1")
    elif fault == "target_reference":
        cell(entries, "E3").find(f"{NS}is/{NS}t").text = "BUDc"
    elif fault == "clock_merge":
        sheet(entries).find(f"{NS}mergeCells/{NS}mergeCell").set("ref", "B3:N5")
    elif fault == "shared_missing":
        cell(entries, "N4").find(NS + "f").set("si", "99")
    elif fault == "shared_range":
        cell(entries, "N3").find(NS + "f").set("ref", "N3:N4")
    elif fault in {"external_sheet", "traversal"}:
        link = entries["xl/_rels/workbook.xml.rels"].find("Relationship[@Id='rId3']")
        link.set("TargetMode", "External") if fault == "external_sheet" else link.set(
            "Target", "../secret.xml"
        )
    elif fault == "missing_sample":
        sheet(entries).find(f"{NS}sheetData/{NS}row[@r='3']").remove(cell(entries, "D3"))
    with pytest.raises(ValueError):
        stored_qpcr(save(tmp_path, entries))


def test_source_hash_and_split_mutation_rejected(tmp_path, original):
    r = recipe(tmp_path, original)
    r["group_assignments"]["T73"] = "train"
    with pytest.raises(ValueError, match="allocation"):
        reconstruct(r, tmp_path)
    r = recipe(tmp_path, original)
    (tmp_path / "qpcr.xlsx").write_bytes(b"modified")
    with pytest.raises(ValueError):
        reconstruct(r, tmp_path)
