import json
import zipfile
from copy import deepcopy
from xml.etree import ElementTree as E

import pytest

from principia_asd.catalog.fracture import NS, REL
from principia_asd.catalog.native import identity, reconstruct
from principia_asd.catalog.tomato import INPUT_UNITS, METADATA, PHENOTYPES, stored_table
from principia_asd.io import file_sha


def book(name, header, columns, records):
    workbook = E.Element(NS + "workbook")
    sheets = E.SubElement(workbook, NS + "sheets")
    E.SubElement(sheets, NS + "sheet", {"name": name, REL + "id": "rId1"})
    links = E.Element("Relationships")
    E.SubElement(links, "Relationship", {"Id": "rId1", "Target": "worksheets/sheet1.xml"})
    tree = E.Element(NS + "worksheet")
    data = E.SubElement(tree, NS + "sheetData")
    for row_id, values in [(header, columns), *records]:
        row = E.SubElement(data, NS + "row", {"r": str(row_id)})
        for column, value in values.items():
            cell = E.SubElement(row, NS + "c", {"r": column + str(row_id)})
            if isinstance(value, str):
                cell.set("t", "inlineStr")
                E.SubElement(E.SubElement(cell, NS + "is"), NS + "t").text = value
            elif value is not None:
                E.SubElement(cell, NS + "v").text = str(value)
    return {
        "xl/workbook.xml": workbook,
        "xl/_rels/workbook.xml.rels": links,
        "xl/worksheets/sheet1.xml": tree,
    }


@pytest.fixture
def tables():
    rows, metadata = [], []
    for i in range(6):
        for day in (0, 7):
            num = len(rows)
            cultivar = "Micro-Tom" if i < 3 else "Tiny Tim"
            rows.append(
                (
                    num + 4,
                    {
                        "A": day,
                        "B": day + 23,
                        "C": "Before" if day == 0 else "Midpoint",
                        "D": f"plant-{i}",
                        "F": cultivar,
                        "G": 4000 + i,
                        "W": 0.2,
                        "Y": 0.8,
                        "Z": 1 + i / 10,
                        "AA": 3 + i / 10,
                        "AB": "unused-later-assay",
                    },
                )
            )
            metadata.append(
                (
                    num + 2,
                    {
                        "A": 45000 + day,
                        "B": day + 22,
                        "C": day,
                        "D": 114 if i < 3 else 121,
                        "E": day + 1,
                        "F": f"plant-{i}",
                        "G": "Ctrl" if i % 3 == 0 else "Salt 01" if i % 3 == 1 else "Drought 02",
                        "H": cultivar,
                    },
                )
            )
    return book("Sheet1", 3, PHENOTYPES, rows), book("Index", 1, METADATA, metadata)


def cell(table, address):
    return table["xl/worksheets/sheet1.xml"].find(f".//{NS}c[@r='{address}']")


def text_cell(table, address, value):
    cell(table, address).find(f"{NS}is/{NS}t").text = value


def number_cell(table, address, value):
    cell(table, address).find(NS + "v").text = str(value)


def save(tmp_path, tables):
    for name, table in zip(["phenotypes.xlsx", "metadata.xlsx"], tables, strict=True):
        with zipfile.ZipFile(tmp_path / name, "w", zipfile.ZIP_DEFLATED) as z:
            for key, value in table.items():
                z.writestr(key, E.tostring(value))
    (tmp_path / "source.json").write_text(
        json.dumps(
            {
                "id": 20638584,
                "doi": "10.5281/zenodo.20638584",
                "metadata": {"license": {"id": "cc-by-4.0"}},
            }
        )
    )
    return {
        "schema_version": "native-reconstruction/1",
        "scenario_id": "P100-036",
        "parser": "tomato-stored-phenotype-custody-v1",
        "input_units": INPUT_UNITS.copy(),
        "output_units": "dimensionless quantum yield",
        "group_assignments": {f"plant-{i}": ["train", "dev", "test"][i % 3] for i in range(6)},
        "assets": [
            {
                "path": name,
                "bytes": (tmp_path / name).stat().st_size,
                "sha256": file_sha(tmp_path / name),
                "role": role,
            }
            for name, role in [
                ("phenotypes.xlsx", "phenotype_workbook"),
                ("metadata.xlsx", "metadata_workbook"),
                ("source.json", "source_metadata"),
            ]
        ],
    }


def test_exact_custody_indicators_and_age_disagreement(tmp_path, tables):
    parts, lineage, checks = reconstruct(save(tmp_path, tables), tmp_path)
    assert {k: len(v) for k, v in parts.items()} == {"train": 4, "dev": 4, "test": 4}
    assert checks["split_check"]["valid"] and len(lineage) == 12
    report = checks["tomato_validation"]
    assert report["plants"] == 6 and len(report["age_annotation_conflicts"]) == 12
    assert report["acquisition_experiments_and_cultivars"] == {
        "114": ["Micro-Tom"],
        "121": ["Tiny Tim"],
    }
    assert report["fit_count"] == 0 and not report["image_extraction_performed"]
    assert parts["dev"][0]["salt"] == 1 and parts["test"][0]["high_stress"] == 1
    assert parts["train"][2]["tiny"] == 1
    assert parts["train"][0]["sample_id"] == identity("P100-036", "sample", "plant-0:native-row4")
    assert "target" not in parts["test"][0] and "target" not in lineage[0]


def test_test_targets_and_unused_assays_cannot_enter_inputs(tmp_path, tables):
    before = reconstruct(save(tmp_path, tables), tmp_path)
    changed = deepcopy(tables)
    for row in [8, 9, 14, 15]:
        number_cell(changed[0], "Y" + str(row), 0.1729)
    for row in range(4, 16):
        E.SubElement(cell(changed[0], "AB" + str(row)), NS + "f").text = "Y4*100"
    after = reconstruct(save(tmp_path, changed), tmp_path)
    assert before == after
    assert "0.1729" not in json.dumps(after)


@pytest.mark.parametrize(
    "change,match",
    [
        ("formula", "Formula"),
        ("target_formula", "Formula"),
        ("header", "headers"),
        ("cultivar", "conflicting"),
        ("treatment", "Unknown"),
        ("assignment", "Conflicting"),
        ("day", "Ambiguous"),
        ("unmatched", "unlinked"),
        ("duplicate", "Duplicate"),
        ("hidden", "hidden"),
        ("nan", "Nonfinite"),
        ("domain", "domain"),
        ("zero_area", "domain"),
        ("string_measurement", "numeric phenotype"),
        ("external", "external"),
        ("traversal", "Unsafe"),
        ("merged", "Merged"),
        ("cell_identity", "Invalid or duplicate"),
        ("invalid_shared_string", "shared string"),
    ],
)
def test_reject_unsafe_or_ambiguous_sources(tmp_path, tables, change, match):
    a, b = tables
    if change in {"formula", "target_formula"}:
        E.SubElement(cell(a, "Z4" if change == "formula" else "Y4"), NS + "f").text = "Y4"
    elif change == "header":
        text_cell(a, "Z3", "QY_max")
    elif change == "cultivar":
        text_cell(a, "F4", "Tiny Tim")
    elif change == "treatment":
        text_cell(b, "G2", "Salt 03")
    elif change == "assignment":
        text_cell(b, "G3", "Salt 01")
    elif change == "day":
        number_cell(b, "C3", 0)
    elif change == "unmatched":
        number_cell(a, "A4", 99)
    elif change == "duplicate":
        number_cell(a, "A5", 0)
    elif change == "hidden":
        a["xl/worksheets/sheet1.xml"].find(f".//{NS}row[@r='4']").set("hidden", "1")
    elif change == "nan":
        number_cell(a, "Z4", "nan")
    elif change == "domain":
        number_cell(a, "Y4", 1.1)
    elif change == "zero_area":
        number_cell(a, "G4", 0)
    elif change == "string_measurement":
        c = cell(a, "Z4")
        c.set("t", "inlineStr")
        E.SubElement(E.SubElement(c, NS + "is"), NS + "t").text = "1.0"
    elif change == "external":
        a["xl/_rels/workbook.xml.rels"][0].set("TargetMode", "External")
    elif change == "traversal":
        a["xl/_rels/workbook.xml.rels"][0].set("Target", "../secret.xml")
    elif change == "merged":
        E.SubElement(
            E.SubElement(a["xl/worksheets/sheet1.xml"], NS + "mergeCells"),
            NS + "mergeCell",
            {"ref": "Y4:Y5"},
        )
    elif change == "cell_identity":
        cell(a, "Z4").set("r", "Z5")
    elif change == "invalid_shared_string":
        c = cell(a, "Z4")
        c.set("t", "s")
        c.find(NS + "v").text = "-1"
    with pytest.raises(ValueError, match=match):
        reconstruct(save(tmp_path, tables), tmp_path)


def test_explicit_missing_source_measurement_is_not_imputed(tmp_path, tables):
    c = cell(tables[0], "Z4")
    c.remove(c.find(NS + "v"))
    parts, _, checks = reconstruct(save(tmp_path, tables), tmp_path)
    assert len(parts["train"]) == 3
    assert checks["tomato_validation"]["excluded_incomplete_rows"] == [
        {"row": 4, "missing_columns": ["Z"]}
    ]


def test_registered_source_hashes_units_and_partitions(tmp_path, tables):
    recipe = save(tmp_path, tables)
    recipe["input_units"]["area"] = "unverified mm2"
    with pytest.raises(ValueError, match="unit"):
        reconstruct(recipe, tmp_path)
    recipe = save(tmp_path, tables)
    del recipe["group_assignments"]["plant-1"]
    with pytest.raises(ValueError, match="independent-unit"):
        reconstruct(recipe, tmp_path)
    recipe = save(tmp_path, tables)
    (tmp_path / "metadata.xlsx").write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash or size"):
        reconstruct(recipe, tmp_path)


def test_bounded_worksheet_size(tmp_path, tables):
    save(tmp_path, tables)
    path = tmp_path / "phenotypes.xlsx"
    with zipfile.ZipFile(path, "a") as z:
        z.writestr("large", b"x" * 2_000_001)
    with pytest.raises(ValueError, match="[Oo]versized|[Ll]imit|[Bb]ound"):
        stored_table(path, "Sheet1", 3, PHENOTYPES)


def test_hidden_measurement_column(tmp_path, tables):
    cols = E.SubElement(tables[0]["xl/worksheets/sheet1.xml"], NS + "cols")
    E.SubElement(cols, NS + "col", {"min": "25", "max": "27", "hidden": "1"})
    with pytest.raises(ValueError, match="Hidden.*column"):
        reconstruct(save(tmp_path, tables), tmp_path)
