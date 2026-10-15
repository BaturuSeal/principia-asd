"""Native traces, stored measurements and exact repeat-specimen custody."""

import copy
import io
import zipfile
from xml.sax.saxutils import escape

import numpy as np
import pytest

from principia_asd.catalog.fracture import (
    HEADERS,
    SUMMARY,
    TRACE_PREFIX,
    bounded_zip,
    canonical_specimen,
    decode_trace,
    stored_summary,
)
from principia_asd.catalog.native import prepare, reconstruct
from principia_asd.io import file_sha, read_csv, write_json


def trace_bytes(*, altered_load=0.0):
    # Blank source separators are explicit lineage, not discarded source positions.
    rows = ["-2 -3 0 0 0", f"1 {4 + altered_load} 0.1 0.1 0.2", "", "2 1 0.2 0.2 0.1"]
    return (
        "Wed Oct 25 10:15:07 2023\r\n\r\nNumber of Points = 3\r\n"
        + "\t".join(HEADERS)
        + "\r\n"
        + "\r\n".join(rows)
        + "\r\n"
    ).encode("cp1252")


def book_bytes(
    *,
    formula=False,
    bad_units=False,
    bad_geometry=False,
    target_shift=0.0,
    hidden_state=4,
    repeated_sheet=False,
    missing_header=False,
):
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    buffer = io.BytesIO()
    headers = {
        "A": "Sample ID",
        "B": "B\n(µm)",
        "C": "W\n(µm)",
        "D": "L\n(µm)",
        "E": "a\n(µm)",
        "G": "Pb2\n(mN)",
        "I": "b\n(µm)",
    }
    if bad_units:
        headers["G"] = "Pb2\n(N)"
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr(
            "xl/workbook.xml",
            f'<workbook {ns} xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            '<sheet name="Crack arrest present " r:id="rId1"/><sheet name="Crack arrest absent " r:id="rId2"/></sheets></workbook>',
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
            f'<Relationship Id="rId2" Target="worksheets/sheet{1 if repeated_sheet else 2}.xml"/></Relationships>',
        )
        for j, labels in enumerate([["C1", "2_C1", "C2"], ["C3"]], 1):
            first = (
                '<row r="1">'
                + "".join(
                    f'<c r="{k}1" t="inlineStr"><is><t>{escape(v)}</t></is></c>'
                    for k, v in headers.items()
                )
                + "</row>"
            )
            if missing_header:
                first = ""
            records = []
            for row, label in enumerate(labels, 3):
                response = 0.2 + (target_shift if label == "C3" else 0)
                values = {
                    "B": 2.5,
                    "C": 2.0,
                    "D": 10.0,
                    "E": 5 if bad_geometry else 0.5,
                    "G": response,
                    "I": 2.0,
                }
                cells = f'<c r="A{row}" t="inlineStr"><is><t>{label}</t></is></c>'
                for key, val in values.items():
                    formula_xml = "<f>AVERAGE(G1:G2)</f>" if formula and key == "G" else ""
                    cells += f'<c r="{key}{row}">{formula_xml}<v>{val}</v></c>'
                cells += f'<c r="J{row}"><f>FITTED_SOURCE_CORRECTION()</f><v>{hidden_state}</v></c>'
                records.append(f'<row r="{row}">{cells}</row>')
            z.writestr(
                f"xl/worksheets/sheet{j}.xml",
                f"<worksheet {ns}><sheetData>"
                + first
                + "".join(records)
                + "</sheetData></worksheet>",
            )
    return buffer.getvalue()


def fixture(tmp_path, **options):
    root = tmp_path / "sources"
    root.mkdir()
    path = root / "native.zip"
    write_archive(path, **options)
    recipe = {
        "schema_version": "native-reconstruction/1",
        "scenario_id": "P100-054",
        "parser": "microfracture-geometry-traces-v1",
        "group_assignments": {"C1": "train", "C2": "dev", "C3": "test"},
        "assets": [
            {
                "path": path.name,
                "role": "fracture_archive",
                "bytes": path.stat().st_size,
                "sha256": file_sha(path),
            }
        ],
    }
    return root, path, recipe


def write_archive(path, *, missing_trace=False, alias_trace=False, altered_load=0, **kwargs):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(SUMMARY, book_bytes(**kwargs))
        for label in ["C1", "2_C1", "C2", "C3"]:
            if missing_trace and label == "C3":
                continue
            z.writestr(TRACE_PREFIX + label + ".txt", trace_bytes(altered_load=altered_load))
        if alias_trace:
            z.writestr(TRACE_PREFIX + "nested/C1.txt", trace_bytes())


def test_trace_retains_negative_loads_discontinuities_and_exact_source_lines():
    array, meta = decode_trace(trace_bytes())
    np.testing.assert_equal(array[:, 0], [-2, 1, 2])
    np.testing.assert_equal(array[:, 1], [-3, 4, 1])
    assert meta["rows"] == 3 and meta["headers"] == HEADERS
    assert meta["blank_separator_lines"] == [7]
    assert meta["line_segments"] == [
        {"first_source_line": 5, "last_source_line": 6, "first_array_row": 0, "last_array_row": 1},
        {"first_source_line": 8, "last_source_line": 8, "first_array_row": 2, "last_array_row": 2},
    ]
    assert not meta["failure_event_identified"] and not meta["fitting_performed"]


@pytest.mark.parametrize("fault", ["units", "count", "clock", "nonfinite", "comment", "columns"])
def test_trace_rejects_unreliable_native_measurements(fault):
    raw = trace_bytes()
    if fault == "units":
        raw = raw.replace(b"Load (\xb5N)", b"Load (mN)")
    elif fault == "count":
        raw = raw.replace(b"Points = 3", b"Points = 4")
    elif fault == "clock":
        raw = raw.replace(b"2 1 0.2", b"2 1 0.1")
    elif fault == "nonfinite":
        raw = raw.replace(b"2 1 0.2", b"2 nan 0.2")
    elif fault == "comment":
        raw = raw.replace(b"-2 -3 0 0 0", b"#2 -3 0 0 0")
    elif fault == "columns":
        raw = raw.replace(b"-2 -3 0 0 0", b"-2 -3 0 0")
    with pytest.raises(ValueError):
        decode_trace(raw)


@pytest.mark.parametrize(
    "fault", ["formula", "bad_units", "bad_geometry", "repeated_sheet", "missing_header"]
)
def test_workbook_requires_stored_measurements_legitimate_geometry_and_units(fault):
    with pytest.raises(ValueError):
        stored_summary(book_bytes(**{fault: True}))


def test_fitted_workbook_columns_are_excluded_without_affecting_measurements():
    assert stored_summary(book_bytes(hidden_state=999999)) == stored_summary(
        book_bytes(hidden_state=4)
    )
    for label, expected in [("2_D18", "D18"), ("E39-2", "E39"), ("2_D22", "D22")]:
        assert canonical_specimen(label) == expected
    with pytest.raises(ValueError):
        canonical_specimen("author-fitted-curve")


def test_raw_trace_matching_preserves_repeats_and_never_substitutes_trace_peak(tmp_path):
    root, path, recipe = fixture(tmp_path)
    parts, lineage, checks = reconstruct(recipe, root)
    assert {k: len(v) for k, v in parts.items()} == {"train": 2, "dev": 1, "test": 1}
    assert checks["split_check"]["units_by_partition"] == {
        "train": ["C1"],
        "dev": ["C2"],
        "test": ["C3"],
    }
    assert parts["train"][0]["target"] == 0.2  # not trace maximum 4 uN or its mN conversion
    assert checks["native_measurement_rows"] == 12
    assert not checks["native_traces_exported_as_model_inputs"]
    assert all("target" not in r for r in parts["test"])
    assert all("Crack arrest" not in str(r) for r in lineage)
    write_archive(path, target_shift=999999, hidden_state=777, altered_load=222)
    recipe["assets"][0].update(bytes=path.stat().st_size, sha256=file_sha(path))
    # Undisclosed Pb2, raw force histories and fitted author columns cannot change inputs.
    assert reconstruct(recipe, root)[0] == parts


@pytest.mark.parametrize("fault", ["missing_trace", "alias_trace"])
def test_trace_and_summary_identity_join_is_exact(tmp_path, fault):
    root, _, recipe = fixture(tmp_path, **{fault: True})
    with pytest.raises(ValueError, match="identities differ"):
        reconstruct(recipe, root)


def test_archive_expansion_and_path_guards_are_enforced():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("../escape", "x")
    with pytest.raises(ValueError, match="Unsafe"):
        with bounded_zip(io.BytesIO(buffer.getvalue()), max_bytes=100, max_member_bytes=100):
            pass
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("data", "12345")
    with pytest.raises(ValueError, match="oversized"):
        with bounded_zip(io.BytesIO(buffer.getvalue()), max_bytes=4, max_member_bytes=10):
            pass


def test_fracture_draft_omits_test_responses_and_native_arrays(tmp_path):
    root, _, recipe = fixture(tmp_path)
    source = tmp_path / "recipe.json"
    write_json(source, recipe)
    output = tmp_path / "draft"
    receipt = prepare(source, root, output)
    assert receipt["api_calls"] == receipt["fitting_attempts"] == 0
    assert (
        "principia_asd.catalog.fracture"
        in __import__("json").loads((output / "preprocessing/environment.json").read_text())[
            "module_hashes"
        ]
    )
    assert not any("target" in row for row in read_csv(output / "public/test_inputs.csv.gz"))
    assert {f.name for f in (output / "public").iterdir()} == {
        "train.csv.gz",
        "dev.csv.gz",
        "test_inputs.csv.gz",
    }
    assert not list(output.rglob("*.txt")) and not list(output.rglob("*.xlsx"))
    wrong = copy.deepcopy(recipe)
    wrong["group_assignments"]["2_C1"] = "dev"
    with pytest.raises(ValueError, match="assignments"):
        reconstruct(wrong, root)
