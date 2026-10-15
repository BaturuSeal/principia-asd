import copy
import csv
import io
import json

import pytest

from principia_asd.catalog import zeolite
from principia_asd.catalog.native import identity, reconstruct
from principia_asd.io import file_sha


def table(offset=0):
    rows = [
        list("ABCDEFGH"),
        [
            "Time on stream",
            "MeOH conversion",
            "conversion",
            "activity",
            "DME",
            "MF",
            "DMM",
            "Formulas",
        ],
        ["min", "%", "mmol/h", "mmol/h/g_cat", "%", "%", "%", ""],
    ]
    for t in [0, 120, 180, 240, 300, 310, 320, 1510]:
        rows.append(
            [
                str(t),
                "5",
                "1",
                "10",
                "20",
                "30",
                str(10 + offset + t / 100),
                "__import__('os').abort()",
            ]
        )
    return rows


def encode(rows):
    stream = io.StringIO()
    csv.writer(stream, delimiter="\t").writerows(rows)
    return stream.getvalue().encode()


def fixture(tmp_path, monkeypatch):
    tables = {g: table(i) for i, g in enumerate(zeolite.RUNS)}
    tables[zeolite.ALIAS] = copy.deepcopy(tables[zeolite.CANONICAL])
    archive, metadata = tmp_path / "source.7z", tmp_path / "record.json"
    archive.write_bytes(b"bound source fixture")
    metadata.write_text(json.dumps({"id": 15691695, "doi": "10.5281/zenodo.15691695"}))

    def read(*args):
        return {f"zenodo raw data/{g}.txt": encode(t) for g, t in tables.items()}, {}

    monkeypatch.setattr(zeolite, "read_archive", read)
    recipe = {
        "schema_version": "native-reconstruction/1",
        "scenario_id": "P100-026",
        "parser": "zeolite-fixed-prefix-reactors-v1",
        "input_units": zeolite.INPUT_UNITS.copy(),
        "output_units": "percentage points",
        "group_assignments": zeolite.original_assignments("P100-026"),
        "decoder_binding": {},
        "archive_members": {},
        "assets": [
            {"path": f.name, "bytes": f.stat().st_size, "sha256": file_sha(f), "role": role}
            for f, role in [(archive, "reactor_archive"), (metadata, "zenodo_record")]
        ],
    }
    return recipe, tables


def test_complete_run_split_prefix_lineage_and_no_test_outputs(tmp_path, monkeypatch):
    recipe, _ = fixture(tmp_path, monkeypatch)
    parts, lineage, checks = reconstruct(recipe, tmp_path)
    assert {p: len(r) for p, r in parts.items()} == {"train": 8, "dev": 4, "test": 4}
    assert checks["split_check"]["valid"]
    v = checks["zeolite_validation"]
    assert v["distinct_runs"] == v["analytical_prefix_calibrations"] == 8
    assert v["rule_fitting_attempts"] == 0
    assert v["group_counts"] == {"train": 4, "dev": 2, "test": 2}
    actual = {r["sample_id"]: r for rows in parts.values() for r in rows}
    for origin in lineage:
        assert origin["source_row"] in [9, 10]
        assert origin["response_column_1based"] == 7
        assert origin["sample_id"] == identity(
            "P100-026", "sample", f"P100-026:{origin['member']}:row{origin['source_row']}"
        )
        row = actual[origin["sample_id"]]
        assert row["elapsed_min"] in [10, 20]
        assert row["prefix_slope_pct_min"] == pytest.approx(0.01)
        assert set(row) == {
            "sample_id",
            "group",
            *zeolite.INPUT_UNITS,
            *([] if origin["split"] == "test" else ["target"]),
        }
    assert not any("target" in r for r in parts["test"])


def test_test_response_and_other_channels_never_become_features(tmp_path, monkeypatch):
    recipe, tables = fixture(tmp_path, monkeypatch)
    before = reconstruct(recipe, tmp_path)[0]
    for group, rows in tables.items():
        for r in rows[3:]:
            for col in [1, 2, 3, 4, 5, 7]:
                r[col] = "UNTRUSTED UNSCORED VALUE"
            if group in zeolite.HELD and float(r[0]) > 300:
                r[6] = "99"
    assert reconstruct(recipe, tmp_path)[0] == before


def test_own_permitted_calibration_only_affects_same_held_run(tmp_path, monkeypatch):
    recipe, tables = fixture(tmp_path, monkeypatch)
    before = reconstruct(recipe, tmp_path)[0]
    selected = sorted(zeolite.HELD)[0]
    tables[selected][7][6] = "90"
    after = reconstruct(recipe, tmp_path)[0]
    assert before["train"] == after["train"] and before["dev"] == after["dev"]
    changed = [b for a, b in zip(before["test"], after["test"], strict=True) if a != b]
    assert len(changed) == 2
    assert all(
        r["anchor_selectivity_pct"] == 90 and r["group"] == identity("P100-026", "group", selected)
        for r in changed
    )


def test_restart_calibration_is_separate_but_split_stays_with_run(tmp_path, monkeypatch):
    recipe, tables = fixture(tmp_path, monkeypatch)
    selected = sorted(zeolite.HELD)[0]
    tables[selected].extend(table(30)[3:])
    parts, lineage, checks = reconstruct(recipe, tmp_path)
    assert len(parts["test"]) == 6
    assert checks["zeolite_validation"]["restarts"] == 1
    assert checks["zeolite_validation"]["analytical_prefix_calibrations"] == 9
    assert checks["split_check"]["valid"]
    second = [r for r in lineage if r["segment"] == 1]
    assert len(second) == 2 and all(r["split"] == "test" for r in second)
    rows = [r for r in parts["test"] if r["sample_id"] in {x["sample_id"] for x in second}]
    assert all(r["anchor_selectivity_pct"] == 43 for r in rows)


def test_missing_calibration_and_response_rows_preserve_source_coordinates():
    rows = table()
    rows[6][6] = "--"
    rows[9][6] = ""
    values, info = zeolite.stored_reactor(encode(rows))
    forecasts, calibrations = zeolite.prefix_forecasts(values)
    assert info["missing_response_rows"] == [7, 10]
    assert calibrations[0]["slope_source_rows"] == [5, 6, 8]
    assert calibrations[0]["anchor_source_row"] == 8
    assert len(forecasts) == 1 and forecasts[0][0] == 9
    assert forecasts[0][3]["prefix_slope_pct_min"] == pytest.approx(0.01)


@pytest.mark.parametrize(
    "mutation",
    [
        "units",
        "label",
        "column",
        "ragged",
        "nan",
        "negative",
        "over100",
        "clock",
        "reverse",
        "missing_time",
    ],
)
def test_source_semantics_reject_unsafe_changes(mutation):
    rows = table()
    if mutation == "units":
        rows[2][0] = "hours"
    if mutation == "label":
        rows[1][6] = "MF"
    if mutation == "column":
        rows[0][6] = "H"
    if mutation == "ragged":
        rows[5].append("extra")
    if mutation == "nan":
        rows[5][6] = "nan"
    if mutation == "negative":
        rows[5][6] = "-1"
    if mutation == "over100":
        rows[5][6] = "101"
    if mutation == "clock":
        rows[5][0] = "120"
    if mutation == "reverse":
        rows[5][0] = "110"
    if mutation == "missing_time":
        rows[5][0] = ""
    with pytest.raises(ValueError):
        zeolite.stored_reactor(encode(rows))


def test_insufficient_calibration_is_not_silently_replaced():
    rows = table()
    for r in rows[4:8]:
        r[6] = ""
    with pytest.raises(ValueError, match="Insufficient"):
        zeolite.prefix_forecasts(zeolite.stored_reactor(encode(rows))[0])


@pytest.mark.parametrize("mutation", ["alias", "allocation", "identity", "hash"])
def test_frozen_scientific_identity_guards(tmp_path, monkeypatch, mutation):
    recipe, tables = fixture(tmp_path, monkeypatch)
    if mutation == "alias":
        tables[zeolite.ALIAS][8][6] = "88"
    if mutation == "allocation":
        recipe["group_assignments"][next(iter(zeolite.RUNS))] = "test"
    if mutation == "identity":
        recipe["scenario_id"] = "P100-025"
    if mutation == "hash":
        (tmp_path / "source.7z").write_bytes(b"changed")
    with pytest.raises(ValueError):
        reconstruct(recipe, tmp_path)


def listing_line(name, size=10, kind="-"):
    return f"{kind}rwxr-xr-x  0 0 0 {size} May 26 2025 {name}\n"


@pytest.mark.parametrize(
    "mutation",
    [
        "traversal",
        "absolute",
        "symlink",
        "duplicate",
        "size",
        "wildcard",
        "directory_size",
        "escape",
    ],
)
def test_bounded_archive_inventory_rejects_unsafe_entries(mutation):
    good = listing_line("zenodo raw data/Figure.txt")
    raw = {
        "traversal": listing_line("zenodo raw data/../evil"),
        "absolute": listing_line("/zenodo raw data/Figure.txt"),
        "symlink": listing_line("zenodo raw data/Figure.txt", kind="l"),
        "duplicate": good + good,
        "size": listing_line("zenodo raw data/Figure.txt", 1_000_001),
        "wildcard": listing_line("zenodo raw data/*.txt"),
        "directory_size": listing_line("zenodo raw data/", 1, "d"),
        "escape": listing_line("zenodo raw data/a\\b"),
    }[mutation]
    with pytest.raises(ValueError):
        zeolite.archive_listing(raw.encode())


def test_archive_inventory_retains_original_order_and_sizes():
    raw = (
        listing_line("zenodo raw data/", 0, "d") + listing_line("zenodo raw data/Figure 1.txt", 24)
    ).encode()
    result = zeolite.archive_listing(raw)
    assert list(result) == ["zenodo raw data", "zenodo raw data/Figure 1.txt"]
    assert result["zenodo raw data/Figure 1.txt"] == {"bytes": 24, "directory": False}


def test_decoder_mismatch_fails_before_reading_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(zeolite, "decoder_binding", lambda: {"version": "test decoder"})
    with pytest.raises(ValueError, match="decoder differs"):
        zeolite.read_archive(tmp_path / "absent.7z", {}, {})
