import copy
import io
import json
import zipfile
from xml.etree import ElementTree as ET

import numpy as np
import pytest

from principia_asd.catalog.memristor import (
    MEMBERS,
    original_assignments,
    reconstruct_memristor,
    row_ranges,
    stored_traces,
)
from principia_asd.catalog.native import NS, REL, identity, reconstruct
from principia_asd.io import file_sha


def label(column):
    value = ""
    while column:
        column, last = divmod(column - 1, 26)
        value = chr(65 + last) + value
    return value


def workbook(arrays, *, mutation=None, trailing=False):
    sheet = ET.Element(NS + "worksheet")
    data = ET.SubElement(sheet, NS + "sheetData")
    for i in range(len(arrays[0])):
        row = ET.SubElement(data, NS + "row", r=str(i + 1))
        for j, array in enumerate(arrays):
            for k in range(2):
                value = array[i, k]
                if np.isnan(value):
                    continue
                c = ET.SubElement(row, NS + "c", r=label(2 * j + k + 1) + str(i + 1))
                ET.SubElement(c, NS + "v").text = repr(float(value))
    if trailing:
        for i in range(len(arrays[0]), len(arrays[0]) + 3):
            row = ET.SubElement(data, NS + "row", r=str(i + 1))
            c = ET.SubElement(row, NS + "c", r=f"B{i + 1}", t="inlineStr")
            ET.SubElement(ET.SubElement(c, NS + "is"), NS + "t").text = "--"
    if mutation:
        mutation(sheet)
    book = ET.Element(NS + "workbook")
    ET.SubElement(
        ET.SubElement(book, NS + "sheets"), NS + "sheet", {"name": "Sheet1", REL + "id": "rId1"}
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/workbook.xml", ET.tostring(book))
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',
        )
        z.writestr("xl/worksheets/sheet1.xml", ET.tostring(sheet))
    return output.getvalue()


def array(j=0, n=120):
    x = 0.006 + 0.01 * np.arange(n)
    x[100:] = 0.996 - 0.01 * np.arange(n - 100)
    y = np.arange(n) * 1e-8 + j * 1e-9 - 2e-7
    return np.column_stack([x, y])


def save_archive(path, arrays):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for (_, name), collection in zip(MEMBERS, arrays, strict=True):
            z.writestr(name, workbook(collection, trailing=True))
        z.writestr("dataset/author-fitted-model.ssc", "Never executed or used")


def fixture(tmp_path):
    arrays = [[array(j + comp * 100) for j in range(50)] for comp in range(2)]
    arrays[1][4] = arrays[1][3].copy()
    path = tmp_path / "dataset.zip"
    save_archive(path, arrays)
    metadata = tmp_path / "record.json"
    metadata.write_text(
        json.dumps(
            {"id": 17278410, "doi": "10.5281/zenodo.17278410", "metadata": {"version": "v1"}}
        )
    )
    groups = {f"{prefix}-device-{j:02d}" for prefix in ("I", "Br") for j in range(1, 51)} - {
        "Br-device-05"
    }
    recipe = {
        "schema_version": "native-reconstruction/1",
        "scenario_id": "P100-022",
        "parser": "perovskite-forming-traces-v1",
        "stored_pairs_per_trace": 120,
        "duplicate_aliases": {"Br-device-05": "Br-device-04"},
        "input_units": {"voltage_V": "V", "bromine_rich": "indicator"},
        "output_units": "microampere",
        "group_assignments": original_assignments("P100-022", groups),
        "assets": [
            {"path": p.name, "bytes": p.stat().st_size, "sha256": file_sha(p), "role": role}
            for p, role in [(path, "memristor_archive"), (metadata, "zenodo_record")]
        ],
    }
    return recipe, arrays, path


def test_whole_trace_partition_duplicate_map_exact_lineage_and_signed_current(tmp_path):
    recipe, _, _ = fixture(tmp_path)
    parts, lineage, checks = reconstruct(recipe, tmp_path)
    assert {p: len(rows) for p, rows in parts.items()} == {"train": 6080, "dev": 1425, "test": 1900}
    v = checks["memristor_validation"]
    assert v["distinct_stored_traces"] == 99
    assert v["stored_pairs_including_duplicate"] == 12000
    assert v["group_counts"] == {"train": 64, "dev": 15, "test": 20}
    assert checks["split_check"]["valid"]
    assert checks["workbooks"][0]["explicit_missing_markers"] == 3
    assert checks["workbooks"][0]["missing_pair_row_ranges_inclusive"][0] == [[121, 123]]
    assert "absent" in checks["workbooks"][0]["unit_headers"]
    assert not any("target" in r for r in parts["test"])
    assert any(r["target"] < 0 for r in parts["train"])
    assert min(r["source_row"] for r in lineage) == 6
    assert max(r["source_row"] for r in lineage) == 100
    first = next(
        r
        for rows in parts.values()
        for r in rows
        if r["sample_id"]
        == identity("P100-022", "sample", "P100-022:dataset/Figure 3(a).xlsx:row6:columns1-2")
    )
    assert first["voltage_V"] == 0.056
    if "target" in first:
        assert first["target"] == pytest.approx(-0.15)
    assert v["negative_selected_currents"] > 0


def test_later_sweep_and_confirmation_responses_never_supply_prediction_inputs(tmp_path):
    recipe, arrays, path = fixture(tmp_path)
    before = reconstruct_memristor(recipe, tmp_path)[0]
    for comp, prefix in enumerate(["I", "Br"]):
        for j, a in enumerate(arrays[comp]):
            a[100:, 1] += 0.0003
            g = f"{prefix}-device-{j + 1:02d}"
            canonical = recipe["duplicate_aliases"].get(g, g)
            if recipe["group_assignments"][canonical] == "test":
                a[:100, 1] += 0.0002
    save_archive(path, arrays)
    assert reconstruct_memristor(recipe, tmp_path)[0] == before
    with pytest.raises(ValueError, match="hash or size"):
        reconstruct(recipe, tmp_path)


@pytest.mark.parametrize(
    "mutation", ["break_alias", "new_duplicate", "cross_composition_duplicate"]
)
def test_response_changes_cannot_relearn_a_different_duplicate_cohort(tmp_path, mutation):
    recipe, arrays, path = fixture(tmp_path)
    if mutation == "break_alias":
        arrays[1][4][-1, 1] += 0.001
    elif mutation == "new_duplicate":
        arrays[0][1] = arrays[0][0].copy()
    else:
        arrays[1][0] = arrays[0][0].copy()
    save_archive(path, arrays)
    with pytest.raises(ValueError, match="duplicate aliases"):
        reconstruct_memristor(recipe, tmp_path)


@pytest.mark.parametrize("mutation", ["test_allocation", "length", "unit", "source_id", "revision"])
def test_source_units_and_frozen_cohort_cannot_silently_change(tmp_path, mutation):
    recipe, _, _ = fixture(tmp_path)
    if mutation == "test_allocation":
        g = next(g for g, v in recipe["group_assignments"].items() if v == "test")
        recipe["group_assignments"][g] = "train"
    elif mutation == "length":
        recipe["stored_pairs_per_trace"] = 119
    elif mutation == "unit":
        recipe["output_units"] = "ampere"
    else:
        p = tmp_path / "record.json"
        m = json.loads(p.read_text())
        if mutation == "source_id":
            m["id"] = 17278409
        else:
            m["metadata"]["version"] = "v2"
        p.write_text(json.dumps(m))
    with pytest.raises(ValueError):
        reconstruct_memristor(recipe, tmp_path)


@pytest.mark.parametrize(
    "kind",
    [
        "formula",
        "nonfinite",
        "wrong_row",
        "duplicate_cell",
        "extra_column",
        "row_gap",
        "row_duplicate",
        "unsupported_type",
        "numeric_string_formula",
    ],
)
def test_invalid_native_cells_and_hidden_fitted_state_are_rejected(kind):
    def mutate(sheet):
        rows = sheet.find(NS + "sheetData")
        cell = rows[0][0]
        if kind == "formula":
            ET.SubElement(cell, NS + "f").text = "reference!A1"
        elif kind == "nonfinite":
            cell.find(NS + "v").text = "inf"
        elif kind == "wrong_row":
            cell.set("r", "A2")
        elif kind == "duplicate_cell":
            rows[0].append(copy.deepcopy(cell))
        elif kind == "extra_column":
            cell.set("r", "C1")
        elif kind == "row_gap":
            rows.remove(rows[1])
        elif kind == "row_duplicate":
            rows[1].set("r", "1")
        elif kind == "unsupported_type":
            cell.set("t", "b")
        else:
            cell.set("t", "str")
            cell.find(NS + "v").text = "=1+1"

    with pytest.raises((ValueError, TypeError)):
        stored_traces(workbook([array()], mutation=mutate), devices=1)


@pytest.mark.parametrize(
    "kind",
    ["reverse_prefix", "negative_voltage", "excess_voltage", "short_branch", "too_many_rows"],
)
def test_branch_and_resource_bounds(kind):
    a = array()
    if kind == "reverse_prefix":
        a[50, 0] = a[49, 0]
    elif kind == "negative_voltage":
        a[0, 0] = -0.001
    elif kind == "excess_voltage":
        a[99, 0] = 1.1
    elif kind == "short_branch":
        a = a[:99]
    with pytest.raises(ValueError):
        stored_traces(workbook([a]), devices=1, max_rows=119 if kind == "too_many_rows" else 5000)


def test_missing_pairs_keep_physical_rows_without_fabricated_samples():
    a = array()
    a[110, 1] = np.nan
    arrays, rows, info = stored_traces(workbook([a], trailing=True), devices=1)
    assert len(arrays[0]) == 119 and rows[0][110] == 112
    assert info["missing_pair_row_ranges_inclusive"] == [[[111, 111], [121, 123]]]
    assert row_ranges([1, 2, 4, 7, 8]) == [[1, 2], [4, 4], [7, 8]]


@pytest.mark.parametrize("target", ["../outside.xml", "/outside.xml"])
def test_unsafe_worksheet_relationship_rejected(target):
    source = workbook([array()])
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(source)) as z, zipfile.ZipFile(out, "w") as w:
        for name in z.namelist():
            value = z.read(name)
            if name.endswith("workbook.xml.rels"):
                value = value.replace(b"worksheets/sheet1.xml", target.encode())
            w.writestr(name, value)
    with pytest.raises(ValueError, match="Unsafe"):
        stored_traces(out.getvalue(), devices=1)
