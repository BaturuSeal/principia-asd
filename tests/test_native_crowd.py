import copy
import csv
import io
import math
import zipfile

import numpy as np
import pytest

from principia_asd.catalog.crowd import (
    HEADERS,
    decode_trajectory,
    recording_group,
    synchronized_positions,
)
from principia_asd.catalog.native import VERSION, identity, reconstruct
from principia_asd.io import file_sha


def csv_bytes(rows, unit="m", header=None):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(header if header is not None else HEADERS[unit])
    writer.writerows(rows)
    return stream.getvalue().encode()


def orbit(unit="m", end=9):
    scale = 100 if unit == "cm" else 1
    rows = []
    for i in range(end * 2 + 1):
        for pid in range(1, 5):
            angle = i / 2 * 0.15 + pid * math.pi / 2
            rows.append(
                [
                    i / 2,
                    pid,
                    2 * math.cos(angle) * scale,
                    2 * math.sin(angle) * scale,
                    "=EXCLUDED_FUTURE()",
                    "nan",
                    "nan",
                ]
            )
    return rows


def crowd(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    path = root / "crowd.zip"
    names = [
        "ExperimentalData/Spain/A1/1.csv",
        "ExperimentalData/Japan/C1/1.csv",
        "ExperimentalData/Kids/D1/1.csv",
    ]
    data = {names[0]: orbit(), names[1]: orbit("cm"), names[2]: orbit()}
    data["ExperimentalData/Spain/A1/2.csv"] = orbit(end=2)
    recipe = {
        "schema_version": VERSION,
        "scenario_id": "P100-090",
        "parser": "crowd-prefix-xy-conditions-v1",
        "assets": [{"role": "crowd_trajectories", "path": path.name}],
        "crowd_members": sorted(data),
        "group_assignments": dict(
            zip(("Spain/A1", "Japan/C1", "Kids/D1"), ("train", "dev", "test"), strict=True)
        ),
    }

    def save(modifier=None, extra=None):
        values = copy.deepcopy(data)
        if modifier:
            modifier(values)
        with zipfile.ZipFile(path, "w") as archive:
            for name, rows in values.items():
                unit = "cm" if name == names[1] else "m"
                archive.writestr(name, csv_bytes(rows, unit))
            # Other modalities and individual experiments must never be parsed or run.
            archive.writestr(
                "ExperimentalData/Individual/Trajectories/1.csv", b"NOT A CROWD DATASET"
            )
            archive.writestr(
                "ExperimentalData/calculate_averages.py",
                b"raise RuntimeError('NEVER EXECUTE SOURCE CODE')",
            )
            if extra:
                archive.writestr(*extra)
        recipe["assets"][0].update(bytes=path.stat().st_size, sha256=file_sha(path))

    save()
    return root, recipe, save, names


def test_crowd_native_units_cohort_and_lineage(tmp_path):
    root, recipe, _, names = crowd(tmp_path)
    parts, lineage, checks = reconstruct(recipe, root)
    assert {p: len(v) for p, v in parts.items()} == dict.fromkeys(("train", "dev", "test"), 2)
    assert checks["split_check"]["valid"]
    assert parts["train"][0]["sample_id"] == identity("P100-090", "sample", names[0] + ":origin=4")
    assert all("target" not in r for r in parts["test"])
    assert checks["crowd_validation"]["recordings"] == 4
    assert checks["crowd_validation"]["recordings_without_eligible_windows"] == [
        "ExperimentalData/Spain/A1/2.csv"
    ]
    for a, b in zip(parts["train"], parts["dev"], strict=True):
        for key in a.keys() - {"sample_id", "group"}:
            assert a[key] == pytest.approx(b[key], abs=1e-14)
    anchor = next(a for a in lineage if a["sample_id"] == parts["train"][0]["sample_id"])
    record = checks["recordings"][anchor["recording_index"]]
    assert record["member"] == names[0]
    assert record["grid_source_rows"][4] == [34, 35, 36, 37]
    assert anchor["target_grid_indices"] == [5, 6]
    assert record["max_held_sample_age_seconds"] == 0
    assert record["track_ids"] == [1, 2, 3, 4]
    assert not checks["crowd_validation"]["supplied_velocity_polarization_or_summary_used"]


def test_crowd_no_future_position_or_author_feature_dependency(tmp_path):
    root, recipe, save, names = crowd(tmp_path)
    before = reconstruct(recipe, root)[0]

    def mutate(data):
        for rows in data.values():
            for row in rows:
                row[4:] = [1e50, -1e50, -99]
                if row[0] > 6 and row[1] == 1:
                    row[2] *= 2

    save(mutate)
    after = reconstruct(recipe, root)[0]
    for split in ("train", "dev", "test"):
        for a, b in zip(before[split], after[split], strict=True):
            assert {k: v for k, v in a.items() if k != "target"} == {
                k: v for k, v in b.items() if k != "target"
            }
    assert before["train"][1]["target"] != after["train"][1]["target"]
    assert before["test"] == after["test"]


def test_crowd_future_only_track_cannot_increase_past_density(tmp_path):
    root, recipe, save, names = crowd(tmp_path)
    before = reconstruct(recipe, root)[0]
    save(
        lambda data: data[names[0]].extend(
            [[8, 99, 100, -100, 0, 0, 0], [9, 99, 101, -100, 0, 0, 0]]
        )
    )
    after = reconstruct(recipe, root)[0]
    for a, b in zip(before["train"], after["train"], strict=True):
        for key in a.keys() - {"sample_id", "group", "target"}:
            assert a[key] == pytest.approx(b[key], abs=1e-14)
    assert before["dev"] == after["dev"] and before["test"] == after["test"]


def test_crowd_hold_uses_no_future_and_rejects_stale_samples():
    rows = [[t, 1, t, -t, 0, 0, 0] for t in (0, 0.5, 3, 3.5)]
    data, lines, _ = decode_trajectory(csv_bytes(rows))
    grid, ids, x, y, sources, age = synchronized_positions(data, lines)
    assert grid.tolist() == [0, 1, 2, 3]
    assert ids.tolist() == [1]
    assert sources[:, 0].tolist() == [2, 3, 0, 4]
    assert math.isnan(x[2, 0]) and math.isnan(y[2, 0])
    assert x[1, 0] == 0.5 and age == 0.5


def test_crowd_nonzero_native_clock_preserves_relative_prefix(tmp_path):
    root, recipe, save, names = crowd(tmp_path)
    before = reconstruct(recipe, root)[0]

    def shift(data):
        for row in data[names[0]]:
            row[0] += 35

    save(shift)
    after, lineage, checks = reconstruct(recipe, root)
    for a, b in zip(before["train"], after["train"], strict=True):
        assert {k: v for k, v in a.items() if k != "sample_id"} == {
            k: v for k, v in b.items() if k != "sample_id"
        }
    first = after["train"][0]
    assert first["sample_id"] == identity("P100-090", "sample", names[0] + ":origin=39")
    anchor = next(a for a in lineage if a["sample_id"] == first["sample_id"])
    assert anchor["origin_index"] == 4 and anchor["origin_seconds"] == 39
    assert checks["recordings"][anchor["recording_index"]]["grid_start_seconds"] == 35


def test_crowd_nonfinite_geometry_is_recorded_not_invented(tmp_path):
    root, recipe, save, names = crowd(tmp_path)

    def stationary(data):
        data["ExperimentalData/Spain/A1/2.csv"] = [
            [r[0], r[1], math.cos(r[1]), math.sin(r[1]), 0, 0, 0] for r in orbit()
        ]

    save(stationary)
    parts, _, checks = reconstruct(recipe, root)
    assert len(parts["train"]) == 2
    assert checks["crowd_validation"]["excluded_origins"] == 2
    assert checks["recordings"][-1]["no_task_rows_reason"] == "all_windows_nonfinite"
    assert {v["origin_seconds"] for v in checks["excluded_origins"]} == {4, 6}


@pytest.mark.parametrize(
    ("column", "value"),
    [(0, -1), (0, "nan"), (1, 0), (1, 1.5), (1, 2**32), (2, "nan"), (3, "inf"), (2, "=FIT()")],
)
def test_crowd_invalid_native_measurements_rejected(column, value):
    rows = orbit()
    rows[0][column] = value
    with pytest.raises(ValueError):
        decode_trajectory(csv_bytes(rows))


def test_crowd_duplicate_clocks_and_unknown_units_rejected():
    rows = orbit()
    with pytest.raises(ValueError, match="clock"):
        decode_trajectory(csv_bytes(rows + rows[:1]))
    with pytest.raises(ValueError, match="schema or units"):
        decode_trajectory(
            csv_bytes(rows, header=["Time(s)", "Id-Ped", "X(px)", "Y(px)", "VX", "VY", "Pol"])
        )


@pytest.mark.parametrize(
    "name",
    [
        "ExperimentalData/Spain/A1.csv",
        "ExperimentalData/Spain/C1/1.csv",
        "Other/Spain/A1/1.csv",
        "ExperimentalData/Spain/A1/../1.csv",
    ],
)
def test_crowd_condition_identity_never_guessed(name):
    with pytest.raises(ValueError, match="condition identity"):
        recording_group(name)


def test_crowd_archive_and_complete_recording_guards(tmp_path):
    root, recipe, save, _ = crowd(tmp_path)
    save(extra=("ExperimentalData/../escape.csv", b"bad"))
    with pytest.raises(ValueError, match="Unsafe"):
        reconstruct(recipe, root)
    save(extra=("ExperimentalData/Spain/A2/1.csv", csv_bytes(orbit())))
    with pytest.raises(ValueError, match="unregistered crowd recording"):
        reconstruct(recipe, root)
    save()
    recipe["group_assignments"].pop("Spain/A1")
    with pytest.raises(ValueError, match="independent-unit"):
        reconstruct(recipe, root)


def test_crowd_source_mutation_and_allocation_bounds(tmp_path):
    root, recipe, _, _ = crowd(tmp_path)
    (root / "crowd.zip").write_bytes(b"mutated")
    with pytest.raises(ValueError, match="hash or size"):
        reconstruct(recipe, root)
    with pytest.raises(ValueError, match="allocation"):
        synchronized_positions(
            np.asarray([[0.0, 1.0, 0.0, 0.0], [100_000.0, 1.0, 1.0, 1.0]]), np.asarray([2, 3])
        )
