import copy

import pytest

from principia_asd.catalog.battery import (
    COLUMNS,
    GITT,
    decode_basytec,
    reconstruct_battery,
    rest_groups,
)
from principia_asd.catalog.native import identity, reconstruct
from principia_asd.io import file_sha


def contents(rows):
    header = [
        "~Resultfile from Basytec Battery Test System",
        "~Date and Time of Data Converting: fixture",
        "~",
        "~Name of Test: Hydra.0b_A_GITTOCV-001",
        "~Battery: Hydra.0b_A",
        "~Testplan: fixture",
        "~Testchannel: fixture",
        "~Start of Test: fixture",
        "~End of Test: fixture",
        "~Operator (Test):",
        "~Operator (Data converting):",
        "~",
        " ".join(COLUMNS),
    ]
    return ("\n".join(header + [" ".join(map(str, r)) for r in rows]) + "\n").encode("latin1")


def fixture(tmp_path):
    rows = []

    def add(second, command, voltage, current, step=1):
        rows.append(
            [
                second / 3600,
                len(rows) + 1,
                0,
                step,
                command,
                voltage,
                current,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                25,
                1,
                0,
            ]
        )

    add(0, "CalcOnce", 3, 0)
    add(1, "Pause", 3, 0)
    for j in range(10):
        start = 100 + j * 2300
        add(
            start,
            "Charge" if j % 2 == 0 else "Discharge",
            3 + j * 0.001,
            0.2 if j % 2 == 0 else -0.2,
        )
        add(
            start + 10,
            "Charge" if j % 2 == 0 else "Discharge",
            3 + j * 0.001,
            0.19 if j % 2 == 0 else -0.19,
        )
        for t in [0, 9, 55, 110, 300, 600, 1200, 1800, 2000]:
            add(start + 20 + t, "Pause", 3 + j * 0.001 + t * 0.00001, 0, step=2 if t < 120 else 3)
    path = tmp_path / GITT
    path.write_bytes(contents(rows))
    groups, _ = rest_groups(decode_basytec(path)[0])
    names = [f"pulse-{g['segment']:04d}" for g, _ in groups]
    assignment = {
        g: "test" if j >= 8 else "dev" if j in [1, 3] else "train" for j, g in enumerate(names)
    }
    extra = tmp_path / "later-pocv.txt"
    extra.write_text("excluded future run")
    recipe = {
        "schema_version": "native-reconstruction/1",
        "scenario_id": "P100-049",
        "parser": "basytec-gitt-rest-prefix-v1",
        "qualifying_rest_groups": 10,
        "group_assignments": assignment,
        "assets": [
            {
                "role": "basytec_gitt_trace",
                "path": GITT,
                "bytes": path.stat().st_size,
                "sha256": file_sha(path),
            },
            {
                "role": "excluded_later_pocv",
                "path": extra.name,
                "bytes": extra.stat().st_size,
                "sha256": file_sha(extra),
            },
        ],
    }
    return recipe, rows


def test_native_clock_prefix_units_grouping_and_history(tmp_path):
    recipe, rows = fixture(tmp_path)
    parts, lineage, checks = reconstruct(recipe, tmp_path)
    assert {p: len(v) for p, v in parts.items()} == {"train": 24, "dev": 8, "test": 8}
    assert checks["split_check"]["valid"]
    assert checks["battery_validation"]["merged_step_number_maximum"] == 2
    assert checks["battery_validation"]["missing_target_horizons"] == 0
    assert checks["battery_validation"]["omitted_rest_segments"] == 1
    assert checks["acquisition_chronology"]["all_development_strictly_before_test"]
    assert not checks["acquisition_chronology"]["train_strictly_before_dev"]
    assert all("target" not in r for r in parts["test"])
    assert len(lineage) == 40
    first = parts["train"][0]
    assert first["t"] == pytest.approx(300)
    assert first["pulse_s"] == pytest.approx(10)
    assert first["t60"] == pytest.approx(55)
    assert first["t120"] == pytest.approx(110)
    assert first["current"] == 0.19
    assert first["u10"] == 3.00009
    assert first["u60"] == 3.00055
    assert first["sample_id"] == identity("P100-049", "sample", "pulse-0004-row-22")
    assert checks["block_inventory"][0]["prefix_source_rows"] == {"10": 19, "60": 20, "120": 21}
    assert checks["block_inventory"][0]["pulse_current_range_A"] == [0.19, 0.2]


def test_future_response_and_unused_columns_do_not_change_inputs(tmp_path):
    recipe, rows = fixture(tmp_path)
    before = reconstruct_battery(recipe, tmp_path)[0]
    # Targets from the last two blocks; no prefix value is changed.
    for row in rows:
        if row[4] == "Pause" and row[0] * 3600 >= 100 + 8 * 2300 + 20 + 300:
            # Alter only rows later than each 120s prefix.
            local = (row[0] * 3600 - 120) % 2300
            if local > 200:
                row[5] += 900
        row[7:14] = [99] * 7
    (tmp_path / GITT).write_bytes(contents(rows))
    (tmp_path / "later-pocv.txt").write_text("arbitrary future source mutation")
    assert reconstruct_battery(recipe, tmp_path)[0] == before
    with pytest.raises(ValueError, match="hash or size"):
        reconstruct(recipe, tmp_path)


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_time",
        "backward_time",
        "duplicate_dataset",
        "noninteger_dataset",
        "nan_time",
        "inf_voltage",
        "nan_current",
        "unknown_command",
        "wrong_shape",
        "wrong_cell",
        "wrong_units",
        "wrong_test",
        "blank_row",
    ],
)
def test_bad_native_trace_fails(tmp_path, mutation):
    _, rows = fixture(tmp_path)
    if mutation == "duplicate_time":
        rows[5][0] = rows[4][0]
    elif mutation == "backward_time":
        rows[5][0] = -1
    elif mutation == "duplicate_dataset":
        rows[5][1] = rows[4][1]
    elif mutation == "noninteger_dataset":
        rows[5][1] = 1.2
    elif mutation == "nan_time":
        rows[5][0] = float("nan")
    elif mutation == "inf_voltage":
        rows[5][5] = float("inf")
    elif mutation == "nan_current":
        rows[5][6] = float("nan")
    elif mutation == "unknown_command":
        rows[5][4] = "FitState"
    elif mutation == "wrong_shape":
        rows[5].append(888)
    raw = contents(rows)
    if mutation == "wrong_cell":
        raw = raw.replace(b"~Battery: Hydra.0b_A", b"~Battery: other")
    elif mutation == "wrong_units":
        raw = raw.replace(b"U[V]", b"U[mV]")
    elif mutation == "wrong_test":
        raw = raw.replace(b"Hydra.0b_A_GITTOCV-001", b"Hydra_other")
    elif mutation == "blank_row":
        raw += b"\n"
    path = tmp_path / GITT
    path.write_bytes(raw)
    with pytest.raises(ValueError):
        decode_basytec(path)


def test_row_and_file_bounds(tmp_path):
    fixture(tmp_path)
    path = tmp_path / GITT
    with pytest.raises(ValueError, match="Excessive"):
        decode_basytec(path, max_rows=8)
    with path.open("r+b") as stream:
        stream.truncate(80_000_001)
    with pytest.raises(ValueError, match="bounded"):
        decode_basytec(path)


def test_nonzero_rest_current_is_not_silently_called_current_free(tmp_path):
    recipe, rows = fixture(tmp_path)
    rows[5][6] = 1e-9
    (tmp_path / GITT).write_bytes(contents(rows))
    with pytest.raises(ValueError, match="current-free"):
        reconstruct_battery(recipe, tmp_path)


@pytest.mark.parametrize("mutation", ["test_groups", "inventory", "missing_group", "source_file"])
def test_frozen_rest_allocation_and_source_binding(tmp_path, mutation):
    recipe, _ = fixture(tmp_path)
    if mutation == "test_groups":
        selected = next(g for g, s in recipe["group_assignments"].items() if s == "test")
        recipe["group_assignments"][selected] = "train"
    elif mutation == "inventory":
        recipe["qualifying_rest_groups"] = 11
    elif mutation == "missing_group":
        recipe["group_assignments"].pop(next(iter(recipe["group_assignments"])))
    elif mutation == "source_file":
        recipe["assets"][0]["path"] = "other.txt"
    with pytest.raises(ValueError):
        reconstruct_battery(recipe, tmp_path)


def test_missing_horizon_is_retained_in_diagnostics(tmp_path):
    recipe, rows = fixture(tmp_path)
    # Drop the first 600s target sample without changing rest duration or pulse identity.
    rows.pop(9)
    (tmp_path / GITT).write_bytes(contents(rows))
    parts, _, checks = reconstruct_battery(recipe, tmp_path)
    assert sum(len(x) for x in parts.values()) == 39
    assert checks["battery_validation"]["missing_target_horizons"] == 1
    assert checks["omitted_target_horizons"][0]["requested_horizon_s"] == 600


def test_short_and_unlinked_rests_remain_in_inventory(tmp_path):
    fixture(tmp_path)
    segments, _ = decode_basytec(tmp_path / GITT)
    source = copy.deepcopy(segments)
    source[3]["rows"] = source[3]["rows"][:4]
    groups, omitted = rest_groups(source)
    assert len(groups) == 9
    assert {r["reason"] for r in omitted} == {
        "rest_duration_below_1800s",
        "not_after_completed_current_command",
    }


def test_distinct_prefix_samples_required(tmp_path):
    recipe, rows = fixture(tmp_path)
    # First rest keeps only origin before 300s, so the 10/60/120 anchors coincide.
    del rows[5:8]
    (tmp_path / GITT).write_bytes(contents(rows))
    with pytest.raises(ValueError, match="distinct causal"):
        reconstruct_battery(recipe, tmp_path)
