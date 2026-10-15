import csv
import io
import json

import pytest

from principia_asd.catalog.cpap import (
    HEADER,
    INPUT_UNITS,
    SOURCE_URL,
    TRIALS,
    adc_pressure,
    eligible_origins,
    original_assignments,
    reconstruct_cpap,
    stored_trace,
)
from principia_asd.catalog.native import identity, reconstruct
from principia_asd.io import file_sha


def cells():
    return (
        [HEADER.copy()]
        + [
            [str(j / 100), str(8192 + j), "8193", "8194", "10:01:02" if j == 0 else ""]
            for j in range(401)
        ]
        + [["-0.01", "0", "0", "0", ""] for _ in range(3)]
    )


def encode(rows):
    stream = io.StringIO()
    csv.writer(stream).writerows(rows)
    return stream.getvalue().encode()


def fixture(tmp_path):
    assets = []
    for subject in range(1, 21):
        for trial in sorted(TRIALS):
            path = tmp_path / f"Subject{subject}_{trial}_raw.csv"
            path.write_bytes(encode(cells()))
            assets.append((path, "raw_pressure"))
    meta = tmp_path / "metadata.json"
    meta.write_text(json.dumps({"source_url": SOURCE_URL, "source_version": "1.0.0; 2024-03-20"}))
    readme = tmp_path / "README.txt"
    readme.write_text("Files with raw ADC counts")
    code = tmp_path / "calibration.m"
    code.write_text("P_max = 1; P_min = -1; 0.1*(2^14); 0.8*(2^14); 70.306957829636")
    assets += [(meta, "source_metadata"), (readme, "source_readme"), (code, "source_calibration")]
    return {
        "schema_version": "native-reconstruction/1",
        "scenario_id": "P100-032",
        "parser": "cpap-raw-adc-delay-traces-v1",
        "input_units": INPUT_UNITS.copy(),
        "output_units": "cmH2O",
        "group_assignments": original_assignments("P100-032"),
        "assets": [
            {"path": p.name, "role": r, "bytes": p.stat().st_size, "sha256": file_sha(p)}
            for p, r in assets
        ],
    }


def test_known_adc_endpoints_and_midpoint_are_fixed_not_fitted():
    # Source transmitter's specified 10%, 50%, 90% transfer, ±1psi range.
    assert adc_pressure([0.1 * 16384, 8192, 0.9 * 16384]) == pytest.approx(
        [-70.306957829636, 0, 70.306957829636], abs=1e-12
    )


def test_complete_panel_and_compact_lineage_keep_subjects_together(tmp_path):
    recipe = fixture(tmp_path)
    parts, lineage, checks = reconstruct(recipe, tmp_path)
    assert {s: len(r) for s, r in parts.items()} == {"train": 108, "dev": 27, "test": 45}
    assert not any("target" in r for r in parts["test"])
    assert checks["split_check"]["valid"]
    assert checks["cpap_validation"]["group_counts"] == {"test": 5, "train": 12, "dev": 3}
    assert checks["cpap_validation"]["native_rows"] == 60 * 404
    assert checks["cpap_validation"]["padding_rows"] == 180
    assert len(lineage) == 180
    assert lineage[0]["origin_row"] == 102 and lineage[0]["target_row"] == 122
    assert checks["traces"][lineage[0]["trace_index"]]["name"] == "Subject10_FEM_raw.csv"
    assert parts["train"][0]["p50"] == pytest.approx(float(adc_pressure(8242)))
    for split, rows in parts.items():
        assert {r["group"] for r in rows} == {
            identity("P100-032", "group", g)
            for g, s in recipe["group_assignments"].items()
            if s == split
        }


def test_later_response_cannot_change_an_earlier_input_or_fixed_cohort(tmp_path):
    recipe = fixture(tmp_path)
    before, _, _ = reconstruct_cpap(recipe, tmp_path)
    p = tmp_path / "Subject1_PEEP_raw.csv"
    rows = cells()
    rows[121][1] = "14000"  # Zero-based measurement 120: first target, not an earlier input.
    p.write_bytes(encode(rows))
    after, _, _ = reconstruct_cpap(recipe, tmp_path)
    assert before == after  # Held-out target is never exported; no later origin uses this offset.


def test_raw_source_change_rejected_by_registered_hash_before_reading(tmp_path):
    recipe = fixture(tmp_path)
    p = tmp_path / "Subject1_PEEP_raw.csv"
    p.write_bytes(p.read_bytes().replace(b"8193", b"8195", 1))
    with pytest.raises(ValueError, match="source hash"):
        reconstruct(recipe, tmp_path)


def test_training_target_change_does_not_become_a_predictor(tmp_path):
    recipe = fixture(tmp_path)
    before, _, _ = reconstruct_cpap(recipe, tmp_path)
    rows = cells()
    rows[121][1] = "14000"
    (tmp_path / "Subject10_FEM_raw.csv").write_bytes(encode(rows))
    after, _, _ = reconstruct_cpap(recipe, tmp_path)
    first_before, first_after = before["train"][0], after["train"][0]
    assert first_before["target"] != first_after["target"]
    assert {k: v for k, v in first_before.items() if k != "target"} == {
        k: v for k, v in first_after.items() if k != "target"
    }


def test_clock_gates_preserve_exclusions_and_actual_delay():
    rows = cells()
    # Mutate only the target clock, leaving an ordered acquisition.
    rows[121][0] = "1.209"  # Accepted 209ms rather than fabricated exact 200ms.
    t, p, info = stored_trace(encode(rows), "Subject1_PEEP_raw.csv")
    origins, excluded = eligible_origins(t, p, info["last_acquired_row"] - 2)
    assert origins == [100, 200, 300] and excluded == []
    assert t[120] - t[100] == pytest.approx(0.209)
    t[220] = 2.23  # Validation of the tolerance family independently of parsing.
    assert eligible_origins(t, p, 400)[1] == [
        {"origin_row": 202, "reason": "future_clock_tolerance"}
    ]


def test_missing_source_pressure_excludes_explicit_origin_without_imputation():
    rows = cells()
    rows[121][2] = ""
    t, p, info = stored_trace(encode(rows), "Subject1_PEEP_raw.csv")
    origins, excluded = eligible_origins(t, p, info["last_acquired_row"] - 2)
    assert origins == [200, 300]
    assert excluded == [{"origin_row": 102, "reason": "nonfinite_selected_pressure"}]
    assert info["missing_adc_cells"] == 1


def test_adc_anomaly_is_retained_and_its_use_reported(tmp_path):
    recipe = fixture(tmp_path)
    rows = cells()
    rows[1][2] = "818217"
    rows[101][1] = "17000"
    rows[121][1] = "18000"
    (tmp_path / "Subject1_FEM_raw.csv").write_bytes(encode(rows))
    _, _, checks = reconstruct_cpap(recipe, tmp_path)
    a = checks["cpap_validation"]
    assert a["out_of_14bit_cells"] == 3
    assert len(a["input_origins_with_adc_anomalies"]) == 1
    assert len(a["target_origins_with_adc_anomalies"]) == 1
    assert a["eligible_origins"] == 180  # No silent cleaning or denominator shrinkage.


def test_duplicate_clock_retained_but_earlier_than_origin():
    rows = cells()
    rows[2][0] = "0"
    t, p, info = stored_trace(encode(rows), "Subject1_PEEP_raw.csv")
    assert info["repeated_clock_intervals"] == 1
    assert eligible_origins(t, p, 400)[0] == [100, 200, 300]


@pytest.mark.parametrize(
    "row,column,value",
    [
        (0, 1, "Gauge Pressure [cmH2O]"),
        (1, 4, "not-a-clock"),
        (2, 4, "10:01:03"),
        (1, 0, "nan"),
        (1, 1, "inf"),
        (1, 1, "-1"),
        (1, 1, "8192.5"),
        (1, 1, "1000001"),
        (2, 0, "-0.1"),
        (101, 0, "0.98"),
        (402, 1, "1"),
        (403, 0, "-0.02"),
    ],
)
def test_schema_clock_padding_and_numeric_corruption_rejected(row, column, value):
    rows = cells()
    rows[row][column] = value
    with pytest.raises(ValueError):
        stored_trace(encode(rows), "Subject1_PEEP_raw.csv")


@pytest.mark.parametrize(
    "name",
    [
        "Subject01_PEEP_raw.csv",
        "Subject21_PEEP_raw.csv",
        "Subject1_OTHER_raw.csv",
        "../Subject1_PEEP_raw.csv",
    ],
)
def test_unregistered_identity_rejected(name):
    with pytest.raises(ValueError):
        stored_trace(encode(cells()), name)


@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "assignment", "units", "metadata", "calibration"]
)
def test_incomplete_panel_wrong_units_or_scientific_source_rejected(tmp_path, mutation):
    recipe = fixture(tmp_path)
    if mutation == "missing":
        recipe["assets"].pop(0)
    elif mutation == "duplicate":
        recipe["assets"].append(recipe["assets"][0])
    elif mutation == "assignment":
        recipe["group_assignments"]["Subject1"] = "train"
    elif mutation == "units":
        recipe["input_units"]["p0"] = "Pa"
    elif mutation == "metadata":
        (tmp_path / "metadata.json").write_text(
            json.dumps({"source_url": SOURCE_URL, "source_version": "2.0.0"})
        )
    elif mutation == "calibration":
        (tmp_path / "calibration.m").write_text("different calibration")
    with pytest.raises(ValueError):
        reconstruct_cpap(recipe, tmp_path)


def test_bounded_input_and_extra_columns_rejected():
    with pytest.raises(ValueError, match="oversized"):
        stored_trace(b"x" * 2_000_001, "Subject1_PEEP_raw.csv")
    rows = cells()
    rows[20].append("hidden fitted state")
    with pytest.raises(ValueError, match="shape"):
        stored_trace(encode(rows), "Subject1_PEEP_raw.csv")


def test_past_window_tolerance_and_future_information_guard():
    t, p, _ = stored_trace(encode(cells()), "Subject1_PEEP_raw.csv")
    t[250] = 2.46
    assert eligible_origins(t, p, 400)[1] == [{"origin_row": 302, "reason": "past_clock_tolerance"}]
    t[95] = 1.01
    with pytest.raises(ValueError, match="Future information"):
        eligible_origins(t, p, 400)
