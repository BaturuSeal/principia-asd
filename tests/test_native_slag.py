import json
import zipfile
from copy import deepcopy
from xml.etree import ElementTree as ET

import pytest

from principia_asd.catalog.fracture import NS, REL
from principia_asd.catalog.native import reconstruct
from principia_asd.catalog.slag import (
    INPUT_UNITS,
    LABELS,
    MIXES,
    SHEETS,
    original_assignments,
    reconstruct_slag,
    stored_penetration,
)
from principia_asd.io import file_sha


def letters(n):
    text = ""
    while n:
        n, r = divmod(n - 1, 26)
        text = chr(65 + r) + text
    return text


def workbook():
    book = ET.Element(NS + "workbook")
    sheets = ET.SubElement(book, NS + "sheets")
    for i, name in enumerate(SHEETS, 1):
        ET.SubElement(sheets, NS + "sheet", {"name": name, REL + "id": f"rId{i}"})
    links = ET.Element("Relationships")
    ET.SubElement(links, "Relationship", {"Id": "rId2", "Target": "worksheets/sheet2.xml"})
    sheet = ET.Element(NS + "worksheet")
    data = ET.SubElement(sheet, NS + "sheetData")
    for k in range(1, 608):
        row = ET.SubElement(data, NS + "row", {"r": str(k)})
        values = {}
        if k == 1:
            values = {3 + i * 6: label for i, label in enumerate(LABELS)}
        elif k == 2:
            values = {
                3 + i * 6 + off: f"T={age}" for i in range(9) for off, age in ((0, 0), (3, 30))
            }
        elif k == 3:
            values = {2: "time"}
            for i in range(9):
                values.update(
                    {
                        3 + i * 6 + j: n
                        for j, n in enumerate(
                            ["NF1 (N)", "NF2 (N)", "NF0 (N)", "NF1 (N)", "NF2 (N)", "NF30 (N)"]
                        )
                    }
                )
        elif k <= 603:
            values = {2: k - 3}
            values.update({c: (k - 10) * c / 1000 for c in range(3, 57)})
        elif k == 604:
            values = {27: "Incomplete"}
        for c, v in values.items():
            cell = ET.SubElement(row, NS + "c", {"r": f"{letters(c)}{k}"})
            if isinstance(v, str):
                cell.set("t", "inlineStr")
                ET.SubElement(ET.SubElement(cell, NS + "is"), NS + "t").text = v
            else:
                ET.SubElement(cell, NS + "v").text = str(v)
                if c >= 3 and (c - 3) % 6 in (2, 5):
                    ET.SubElement(cell, NS + "f").text = "UNTRUSTED_SOURCE_FORMULA()"
    merge = ET.SubElement(sheet, NS + "mergeCells")
    ET.SubElement(merge, NS + "mergeCell", {"ref": "AA604:AF607"})
    return {
        "xl/workbook.xml": book,
        "xl/_rels/workbook.xml.rels": links,
        "xl/worksheets/sheet2.xml": sheet,
    }


@pytest.fixture(scope="module")
def original():
    return workbook()


def save(tmp_path, entries):
    path = tmp_path / "rheology.xlsx"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, node in entries.items():
            z.writestr(name, ET.tostring(node))
    return path


def cell(entries, address):
    return entries["xl/worksheets/sheet2.xml"].find(f".//{NS}c[@r='{address}']")


def recipe(tmp_path, original):
    path = save(tmp_path, original)
    meta = tmp_path / "metadata.json"
    meta.write_text(
        json.dumps(
            {
                "id": 17092152,
                "doi": "10.5281/zenodo.17092152",
                "metadata": {"license": {"id": "cc-by-4.0"}},
            }
        )
    )
    return {
        "schema_version": "native-reconstruction/1",
        "scenario_id": "P100-055",
        "parser": "slag-mixture-penetration-traces-v1",
        "input_units": INPUT_UNITS.copy(),
        "output_units": "N",
        "group_assignments": original_assignments("P100-055"),
        "assets": [
            {"path": p.name, "role": role, "sha256": file_sha(p), "bytes": p.stat().st_size}
            for p, role in [(path, "rheology_workbook"), (meta, "source_metadata")]
        ],
    }


def test_exact_cohort_units_quality_and_no_test_targets(tmp_path, original):
    parts, lineage, checks = reconstruct(recipe(tmp_path, original), tmp_path)
    assert {s: len(v) for s, v in parts.items()} == {"train": 12000, "dev": 4800, "test": 4800}
    assert len(lineage) == 21600 and checks["split_check"]["valid"]
    assert all("target" not in row for row in parts["test"])
    assert set(parts["train"][0]) == {
        "sample_id",
        "group",
        "ratio",
        "water",
        "age_min",
        "time_s",
        "target",
    }
    assert any(r["target"] < 0 for r in parts["train"])
    assert checks["slag_validation"]["source_quality_flags"][0]["rows_retained"] == 2400
    assert checks["slag_validation"]["rights_evidence"]["status"] == "conflict_requires_review"
    assert len(checks["slag_traces"]) == 36
    for group in MIXES:
        traces = [t for t in checks["slag_traces"] if t["mixture"] == group]
        assert len({t["split"] for t in traces}) == 1
        assert {(t["age_min"], t["batch_label"]) for t in traces} == {
            (a, b) for a in (0, 30) for b in (1, 2)
        }


@pytest.mark.parametrize("split", ["train", "test"])
def test_force_cannot_change_predictors_and_test_force_not_exported(tmp_path, original, split):
    r = recipe(tmp_path, original)
    before, _, _ = reconstruct_slag(r, tmp_path)
    group = next(g for g, s in r["group_assignments"].items() if s == split)
    changed = deepcopy(original)
    col = letters(3 + MIXES.index(group) * 6)
    cell(changed, col + "4").find(NS + "v").text = "-9999"
    save(tmp_path, changed)
    after, _, _ = reconstruct_slag(r, tmp_path)
    def strip(parts):
        return {
            s: [{k: v for k, v in row.items() if k != "target"} for row in rows]
            for s, rows in parts.items()
        }
    assert strip(before) == strip(after)
    assert (before != after) == (split == "train")


def test_cached_averages_and_other_response_sheets_are_never_inputs(tmp_path, original):
    r = recipe(tmp_path, original)
    before = reconstruct_slag(r, tmp_path)
    changed = deepcopy(original)
    cell(changed, "E4").find(NS + "v").text = "not-a-number"
    cell(changed, "E4").find(NS + "f").text = "EXTERNAL_SECRET()"
    changed["xl/worksheets/sheet3.xml"] = ET.Element("untrusted-fitted-model")
    save(tmp_path, changed)
    assert reconstruct_slag(r, tmp_path) == before


@pytest.mark.parametrize(
    "change",
    [
        "formula",
        "nan",
        "missing",
        "string",
        "clock",
        "unit",
        "mixture",
        "age",
        "quality",
        "duplicate_cell",
        "wrong_cell_row",
        "duplicate_row",
        "missing_row",
        "extra_row",
        "merge",
        "external",
        "traversal",
        "ambiguous_sheet",
    ],
)
def test_invalid_native_panel_rejected_without_shrinking_denominator(tmp_path, original, change):
    entries = deepcopy(original)
    sheet = entries["xl/worksheets/sheet2.xml"]
    row = sheet.find(f"{NS}sheetData/{NS}row[@r='4']")
    measured = cell(entries, "C4")
    if change == "formula":
        ET.SubElement(measured, NS + "f").text = "FITTED()"
    elif change == "nan":
        measured.find(NS + "v").text = "NaN"
    elif change == "missing":
        row.remove(measured)
    elif change == "string":
        measured.set("t", "str")
    elif change == "clock":
        cell(entries, "B4").find(NS + "v").text = "2"
    elif change in {"unit", "mixture", "age", "quality"}:
        address = {"unit": "C3", "mixture": "C1", "age": "C2", "quality": "AA604"}[change]
        cell(entries, address).find(f"{NS}is/{NS}t").text = "changed"
    elif change == "duplicate_cell":
        row.append(deepcopy(measured))
    elif change == "wrong_cell_row":
        measured.set("r", "C5")
    elif change == "duplicate_row":
        sheet.find(NS + "sheetData").append(deepcopy(row))
    elif change == "missing_row":
        sheet.find(NS + "sheetData").remove(row)
    elif change == "extra_row":
        ET.SubElement(sheet.find(NS + "sheetData"), NS + "row", {"r": "608"})
    elif change == "merge":
        sheet.find(f"{NS}mergeCells/{NS}mergeCell").set("ref", "C4:D5")
    elif change == "external":
        entries["xl/_rels/workbook.xml.rels"][0].set("TargetMode", "External")
    elif change == "traversal":
        entries["xl/_rels/workbook.xml.rels"][0].set("Target", "../secret.xml")
    elif change == "ambiguous_sheet":
        entries["xl/workbook.xml"].find(NS + "sheets")[1].set("name", "wrong")
    with pytest.raises(ValueError):
        stored_penetration(save(tmp_path, entries))


@pytest.mark.parametrize("change", ["unit", "split", "license", "source_hash"])
def test_registered_contract_and_hash_custody(tmp_path, original, change):
    r = recipe(tmp_path, original)
    if change == "unit":
        r["input_units"]["time_s"] = "s"
    elif change == "split":
        r["group_assignments"][MIXES[0]] = "train"
    elif change == "license":
        m = tmp_path / "metadata.json"
        doc = json.loads(m.read_text())
        doc["metadata"]["license"]["id"] = "CC0"
        m.write_text(json.dumps(doc))
    else:
        r["assets"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError):
        (reconstruct if change == "source_hash" else reconstruct_slag)(r, tmp_path)
