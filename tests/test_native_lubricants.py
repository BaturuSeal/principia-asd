import copy
import csv
import io
import json
import zipfile

import pytest

from principia_asd.catalog.lubricants import (
    INPUT_UNITS,
    LABELS,
    SERIES,
    SPEEDS,
    original_assignments,
    reconstruct_lubricants,
    stored_curves,
)
from principia_asd.catalog.native import identity, reconstruct
from principia_asd.io import file_sha


def table(kind, *, width=6):
    rows = [[""] * width for _ in range(49)]
    rows[0][0] = "hBN nanoparticles"
    rows[1][0] = "measurement 02-06/2025"
    rows[4][0] = "EHD5 experimental device (optial tribometer)"
    rows[6][0] = "Ball-on disk configuration"
    rows[7][1:3] = ["Slide-to-roll ratio (SRR):", "-20%"]
    rows[10][1:3] = ["Test temperature:", "26,2 +/-0,4 °C"]
    for i in (12, 16):
        rows[i][1:5] = LABELS[kind]
    materials = (
        ("BK7 glass", "Steel (100Cr6)") if kind == "concentration" else ("Sklo", "Ocel (100Cr6)")
    )
    rows[13][:5] = ["Material 1", *([materials[0]] * 4)]
    rows[14][:5] = ["Material 2", *([materials[1]] * 4)]
    rows[15][:5] = ["Pressure", *(["550 MPa"] * 4)]
    rows[17][:2] = ["Speed, mm/s", "Coefficient of friction, Ft/Fn, (-)"]
    indices = {g: i for i, g in enumerate(["PEG", "P5", "P2", "P1", "N", "NS", "PCH", "NG"])}
    for k, speed in enumerate(SPEEDS):
        rows[k + 18][0] = str(speed)
        for j, group in enumerate(SERIES[kind][0], 1):
            extra = 0.0007 if kind == "functionalization" and group == "P5" else 0
            rows[k + 18][j] = repr(0.003 + k * 0.001 + indices[group] * 0.0001 + extra)
    for k in range(45, 49):
        rows[k][4:6] = ["source uncertainty only", "3.1%"]
    return rows


def encode(rows):
    stream = io.StringIO()
    csv.writer(stream).writerows(rows)
    return stream.getvalue().encode("utf-8-sig")


def save(path, tables):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for kind, rows in tables.items():
            z.writestr(f"dataset/CoF dataset {kind}.csv", encode(rows))
        z.writestr("dataset/author-fitted-summary.csv", "excluded from all features")


def fixture(tmp_path):
    tables = {kind: table(kind) for kind in SERIES}
    archive = tmp_path / "dataset.zip"
    save(archive, tables)
    metadata = tmp_path / "record.json"
    metadata.write_text(json.dumps({"id": 17864405, "doi": "10.5281/zenodo.17864405"}))
    recipe = {
        "schema_version": "native-reconstruction/1",
        "scenario_id": "P100-030",
        "parser": "hbn-calibrated-formulation-curves-v1",
        "input_units": INPUT_UNITS.copy(),
        "output_units": "dimensionless",
        "group_assignments": original_assignments(
            "P100-030", {g for groups, _ in SERIES.values() for g in groups}
        ),
        "duplicate_aliases": {
            "functionalization:PEG": "concentration:PEG",
            "suppliers:PEG": "concentration:PEG",
            "suppliers:P5": "concentration:P5",
        },
        "assets": [
            {"path": p.name, "bytes": p.stat().st_size, "sha256": file_sha(p), "role": role}
            for p, role in [(archive, "lubricant_archive"), (metadata, "zenodo_record")]
        ],
    }
    return recipe, tables, archive


def test_complete_cohort_whole_formulation_allocation_and_endpoint_lineage(tmp_path):
    recipe, tables, _ = fixture(tmp_path)
    parts, lineage, checks = reconstruct(recipe, tmp_path)
    assert {p: len(rows) for p, rows in parts.items()} == {"train": 60, "dev": 24, "test": 24}
    assert checks["split_check"]["valid"]
    v = checks["lubricant_validation"]
    assert (v["stored_curves"], v["distinct_curves"], v["formulations"]) == (12, 9, 8)
    assert v["curve_counts"] == {"train": 5, "dev": 2, "test": 2}
    assert v["group_counts"] == {"train": 4, "dev": 2, "test": 2}
    by_id = {r["sample_id"]: r for rows in parts.values() for r in rows}
    for origin in lineage:
        row = by_id[origin["sample_id"]]
        kind, group = origin["curve"].split(":")
        col = origin["column_1based"] - 1
        assert 31 <= origin["source_row"] <= 42
        assert row["boundary_cof"] == float(tables[kind][42][col])
        assert row["highspeed_cof"] == float(tables[kind][18][col])
        assert row["group"] == identity("P100-030", "group", group)
        assert row["sample_id"] == identity(
            "P100-030",
            "sample",
            f"P100-030:{origin['member']}:row{origin['source_row']}:column{col + 1}",
        )
        assert row["speed_mm_s"] <= 10 and row["speed_mm_s"] > 0.2
        assert origin["source_row"] not in origin["calibration_rows"].values()
    assert not any("target" in row for row in parts["test"])
    # Different curves with the same formulation are not independent split units.
    p5 = [r for r in parts["train"] if r["group"] == identity("P100-030", "group", "P5")]
    assert len(p5) == 24
    assert len({r["highspeed_cof"] for r in p5}) == 2


def test_scored_test_responses_and_unscored_interior_never_enter_inputs(tmp_path):
    recipe, tables, archive = fixture(tmp_path)
    original = reconstruct_lubricants(recipe, tmp_path)[0]
    for kind, rows in tables.items():
        for j, group in enumerate(SERIES[kind][0], 1):
            for i in range(19, 30):  # unscored high-speed interior, not endpoints
                rows[i][j] = str(float(rows[i][j]) + 0.5)
            if group in {"NS", "NG"}:
                for i in range(30, 42):
                    rows[i][j] = str(float(rows[i][j]) + 0.25)
    save(archive, tables)
    assert reconstruct_lubricants(recipe, tmp_path)[0] == original
    with pytest.raises(ValueError, match="hash or size"):
        reconstruct(recipe, tmp_path)


def test_permitted_test_calibration_affects_only_its_own_curve(tmp_path):
    recipe, tables, archive = fixture(tmp_path)
    original = reconstruct_lubricants(recipe, tmp_path)[0]
    tables["suppliers"][42][4] = "0.09"
    save(archive, tables)
    updated = reconstruct_lubricants(recipe, tmp_path)[0]
    assert updated["train"] == original["train"]
    assert updated["dev"] == original["dev"]
    changed = [(a, b) for a, b in zip(original["test"], updated["test"], strict=True) if a != b]
    assert len(changed) == 12
    assert all(b["boundary_cof"] == 0.09 and a.keys() == b.keys() for a, b in changed)


@pytest.mark.parametrize("mutation", ["break_alias", "new_alias", "cross_formulation_alias"])
def test_duplicate_changes_cannot_select_new_cohort(tmp_path, mutation):
    recipe, tables, archive = fixture(tmp_path)
    if mutation == "break_alias":
        tables["functionalization"][25][1] = "0.1234"
    elif mutation == "new_alias":
        for i in range(18, 43):
            tables["functionalization"][i][2] = tables["concentration"][i][2]
    else:
        for i in range(18, 43):
            tables["suppliers"][i][4] = tables["concentration"][i][3]
    save(archive, tables)
    with pytest.raises(ValueError, match="duplicate curve aliases"):
        reconstruct_lubricants(recipe, tmp_path)


def test_wide_spreadsheet_export_allows_only_empty_padding():
    rows = table("suppliers", width=16383)
    values, info = stored_curves(encode(rows), "suppliers")
    assert values.shape == (25, 5)
    assert info["empty_padding_cells_excluded"] == 49 * (16383 - 6)
    rows[48][-1] = "hidden output"
    with pytest.raises(ValueError, match="hidden"):
        stored_curves(encode(rows), "suppliers")


@pytest.mark.parametrize(
    "mutation",
    [
        "units",
        "labels",
        "pressure",
        "material",
        "temperature",
        "ratio",
        "missing_speed",
        "reordered_speed",
        "calibration_speed",
        "nonfinite",
        "negative",
        "extra_column",
        "ragged",
    ],
)
def test_source_semantics_and_measurement_integrity_reject_changes(mutation):
    rows = table("functionalization")
    if mutation == "units":
        rows[17][0] = "Speed, m/s"
    elif mutation == "labels":
        rows[16][4] = "different material"
    elif mutation == "pressure":
        rows[15][3] = "450 MPa"
    elif mutation == "material":
        rows[13][1] = "Steel"
    elif mutation == "temperature":
        rows[10][2] = "298 K"
    elif mutation == "ratio":
        rows[7][2] = "20%"
    elif mutation == "missing_speed":
        rows[20][0] = ""
    elif mutation == "reordered_speed":
        rows[25], rows[26] = rows[26], rows[25]
    elif mutation == "calibration_speed":
        rows[42][0] = "0.3"
    elif mutation == "nonfinite":
        rows[30][2] = "nan"
    elif mutation == "negative":
        rows[30][2] = "-0.01"
    elif mutation == "extra_column":
        rows[30][5] = "0.5"
    elif mutation == "ragged":
        rows[30].pop()
    with pytest.raises(ValueError):
        stored_curves(encode(rows), "functionalization")


@pytest.mark.parametrize("mutation", ["units", "source", "test_allocation", "missing_group"])
def test_fixed_identity_unit_and_partition_contract(tmp_path, mutation):
    recipe, _, _ = fixture(tmp_path)
    recipe = copy.deepcopy(recipe)
    if mutation == "units":
        recipe["input_units"]["speed_mm_s"] = "m/s"
    elif mutation == "source":
        (tmp_path / "record.json").write_text(json.dumps({"id": 123, "doi": "different source"}))
    elif mutation == "test_allocation":
        recipe["group_assignments"]["NS"] = "train"
    else:
        recipe["group_assignments"].pop("P5")
    with pytest.raises(ValueError):
        reconstruct_lubricants(recipe, tmp_path)


def test_bounded_table_and_archive(tmp_path):
    with pytest.raises(ValueError, match="oversized"):
        stored_curves(b"x" * 1_000_001, "concentration")
    rows = table("concentration") + [[""] * 6 for _ in range(80)]
    with pytest.raises(ValueError, match="dimensions"):
        stored_curves(encode(rows), "concentration")
    recipe, _, archive = fixture(tmp_path)
    with zipfile.ZipFile(archive, "a") as z:
        z.writestr("../evaluator/canary", "forbidden member")
    with pytest.raises(ValueError):
        reconstruct_lubricants(recipe, tmp_path)


def test_source_uncertainty_is_inventory_not_fitted_noise_or_training_feature(tmp_path):
    recipe, tables, archive = fixture(tmp_path)
    original = reconstruct_lubricants(recipe, tmp_path)
    tables["concentration"][45][5] = "changed diagnostic resolution"
    save(archive, tables)
    after = reconstruct_lubricants(recipe, tmp_path)
    assert original[:2] == after[:2]
    assert original[2]["source_tables"] != after[2]["source_tables"]
