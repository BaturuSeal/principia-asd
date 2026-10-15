import csv
import json
import math

import pytest

from principia_asd.catalog.finger_friction import (
    INPUT_UNITS,
    PARTICIPANTS,
    RAW_HEADER,
    RAW_UNITS,
    SUMMARY_HEADER,
    SUMMARY_UNITS,
    native_trials,
    original_assignments,
    reconstruct_finger_friction,
    table,
)
from principia_asd.catalog.native import identity, reconstruct
from principia_asd.io import file_sha


def write(path, rows, delimiter=","):
    with path.open("w", newline="") as stream:
        csv.writer(stream, delimiter=delimiter).writerows(rows)


def read(path, delimiter=","):
    with path.open() as stream:
        return list(csv.reader(stream, delimiter=delimiter))


def fixture(root):
    files = {
        "zenodo_record": root / "record.json",
        "participants": root / "participants.dat",
        "rheology_fit": root / "fits.dat",
        "friction_summary": root / "friction.dat",
        "raw_trials": root / "raw.dat",
        "rheology": root / "rheology.dat",
        "source_readme": root / "readme.txt",
    }
    files["zenodo_record"].write_text(
        json.dumps({"id": 15365365, "doi": "10.5281/zenodo.15365365"})
    )
    files["source_readme"].write_text(
        "Synthetic custody fixture, not an independent discovery trial"
    )
    people = [
        ["participant", "finger pad area", "SC hydration"],
        ["1", "cm^2", "a.u."],
        ["none"] * 3,
    ]
    for p in sorted(PARTICIPANTS):
        people.append([p, "3.333", "50"])
    write(files["participants"], people, "\t")
    fits = [["recipe", "sample", "K", "n-1"], ["none", "1", "mPa s^n", "1"], ["none"] * 4]
    summary = [SUMMARY_HEADER, SUMMARY_UNITS, ["none"] * 12 + [" none"]]
    raw = [RAW_HEADER, RAW_UNITS, ["none"] * 9]
    for sample in range(1, 16):
        fits.append([f"Fluid {sample}", str(sample), str(sample / 10), "-0.1"])
        for j, person in enumerate(sorted(PARTICIPANTS)):
            viscosity = (sample / 10) * 500**-0.1
            hersey = 0.2 + j * 0.01
            summary.append(
                [
                    person,
                    str(sample),
                    "1",
                    "0.03",
                    "1",
                    str(sample / 10),
                    "-0.1",
                    repr(hersey),
                    repr(viscosity),
                    repr(math.log10(hersey)),
                    repr(math.log10(viscosity)),
                    repr(0.3 + sample / 100),
                ]
            )
            for k, time in enumerate(["0", "0.1", "0.1", "", "0.3"]):
                pos = [time, "0.01", "0.02", "0.03"] if time else [""] * 4
                raw.append([str(sample), person, *pos, "-0.01", "0.05", str(0.8 + k * 0.1)])
    write(files["rheology_fit"], fits)
    write(files["friction_summary"], summary)
    write(files["raw_trials"], raw, "\t")
    rheology = [
        ["shear rate", *[f"sample {i}" for i in range(1, 16)]],
        ["1/s", *(["mPa s"] * 15)],
        ["none"] * 16,
        ["10", *(["100"] * 15)],
        ["20", "", *(["90"] * 14)],
    ]
    write(files["rheology"], rheology)
    assets = [
        {"path": p.name, "bytes": p.stat().st_size, "sha256": file_sha(p), "role": role}
        for role, p in files.items()
    ]
    for person, sample in [("ID04", 1), ("ID04", 12), ("ID08", 2), ("ID10", 11)]:
        p = root / f"HeightHersey{person}sample{sample:02}.dat"
        write(
            p,
            [
                ["time", "height", "log(Hersey number)"],
                ["s", "mm", "1"],
                ["0", "NaN", "0.3"],
                ["0.1", "2", "NaN"],
            ],
        )
        assets.append(
            {
                "path": p.name,
                "bytes": p.stat().st_size,
                "sha256": file_sha(p),
                "role": "height_hersey",
            }
        )
    recipe = {
        "schema_version": "native-reconstruction/1",
        "scenario_id": "P100-023",
        "parser": "finger-friction-participant-summary-v1",
        "assets": assets,
        "input_units": INPUT_UNITS.copy(),
        "output_units": "1",
        "group_assignments": original_assignments("P100-023", PARTICIPANTS),
    }
    return recipe, files


def test_full_panel_identities_lineage_and_missing_raw_observations(tmp_path):
    recipe, _ = fixture(tmp_path)
    parts, lineage, checks = reconstruct(recipe, tmp_path)
    assert {p: len(v) for p, v in parts.items()} == {"train": 105, "dev": 30, "test": 30}
    assert checks["split_check"]["valid"]
    v = checks["finger_friction_validation"]
    assert v["group_counts"] == {"train": 7, "dev": 2, "test": 2}
    assert v["native_force_position_rows"] == 825
    assert v["missing_clock_position_rows"] == 165
    assert v["repeated_finite_clocks"] == 165
    assert v["native_force_median_max_difference"] == 0
    assert "mPa" in v["unit_header_conflict"]
    assert not any("target" in r for r in parts["test"])
    assert {o["summary_row"] for o in lineage} == set(range(4, 169))
    ids = {r["sample_id"] for rows in parts.values() for r in rows}
    assert ids == {identity("P100-023", "sample", f"P100-023-{j:07d}") for j in range(165)}
    assert not any("normal_force_median" in r for r in checks["raw_trial_inventory"])
    assert checks["auxiliary_inventory"][-1]["used_as_predictor"] is False
    assert all(
        o["raw_trial_rows_inclusive"][1] - o["raw_trial_rows_inclusive"][0] == 4 for o in lineage
    )


def test_test_responses_tangential_force_auxiliary_values_do_not_supply_predictors(tmp_path):
    recipe, files = fixture(tmp_path)
    before = reconstruct_finger_friction(recipe, tmp_path)[0]
    rows = read(files["friction_summary"])
    for r in rows[3:]:
        if recipe["group_assignments"][r[0]] == "test":
            r[-1] = "1.6"
    write(files["friction_summary"], rows)
    rows = read(files["raw_trials"], "\t")
    for r in rows[3:]:
        r[6:8] = ["-900", "800"]
    write(files["raw_trials"], rows, "\t")
    rows = read(files["rheology"])
    rows[3][1] = "9999"
    write(files["rheology"], rows)
    assert reconstruct_finger_friction(recipe, tmp_path)[0] == before
    with pytest.raises(ValueError, match="hash or size"):
        reconstruct(recipe, tmp_path)


@pytest.mark.parametrize("mutation", ["units", "source", "split", "missing_asset", "extra_asset"])
def test_registered_contract_and_source_cannot_silently_change(tmp_path, mutation):
    recipe, files = fixture(tmp_path)
    if mutation == "units":
        recipe["input_units"]["viscosity"] = "mPa s"
    elif mutation == "source":
        files["zenodo_record"].write_text('{"id":123,"doi":"different"}')
    elif mutation == "split":
        recipe["group_assignments"]["ID03"] = "train"
    elif mutation == "missing_asset":
        recipe["assets"].pop()
    else:
        recipe["assets"].append(recipe["assets"][-1])
    with pytest.raises(ValueError):
        reconstruct_finger_friction(recipe, tmp_path)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_trial",
        "duplicate_trial",
        "source_load",
        "summary_units",
        "fit_parameters",
        "derived_viscosity",
        "derived_log",
        "nonfinite",
        "negative_speed",
        "unknown_participant",
        "hidden_column",
    ],
)
def test_summary_fields_and_complete_native_join_are_checked(tmp_path, mutation):
    recipe, files = fixture(tmp_path)
    rows = read(files["friction_summary"])
    if mutation == "missing_trial":
        rows.pop()
    elif mutation == "duplicate_trial":
        rows[-1] = rows[-2]
    elif mutation == "source_load":
        rows[3][4] = "2"
    elif mutation == "summary_units":
        rows[1][3] = "mm/s"
    elif mutation == "fit_parameters":
        rows[3][5] = "9"
    elif mutation == "derived_viscosity":
        rows[3][8] = "8"
    elif mutation == "derived_log":
        rows[3][9] = "0.5"
    elif mutation == "nonfinite":
        rows[3][-1] = "NaN"
    elif mutation == "negative_speed":
        rows[3][3] = "-1"
    elif mutation == "unknown_participant":
        rows[3][0] = "ID12"
    else:
        rows[3].append("hidden value")
    write(files["friction_summary"], rows)
    with pytest.raises(ValueError):
        reconstruct_finger_friction(recipe, tmp_path)


@pytest.mark.parametrize(
    "mutation",
    ["duplicate_person", "hydration_range", "missing_person", "area_domain", "fit_duplicate"],
)
def test_participant_and_fit_inventory_are_not_inferred_or_imputed(tmp_path, mutation):
    recipe, files = fixture(tmp_path)
    name = "rheology_fit" if mutation == "fit_duplicate" else "participants"
    sep = "," if name == "rheology_fit" else "\t"
    rows = read(files[name], sep)
    if mutation in {"duplicate_person", "fit_duplicate"}:
        rows[-1] = rows[-2]
    elif mutation == "hydration_range":
        rows[3][2] = "121"
    elif mutation == "missing_person":
        rows.pop()
    else:
        rows[3][1] = "0"
    write(files[name], rows, sep)
    with pytest.raises(ValueError):
        reconstruct_finger_friction(recipe, tmp_path)


@pytest.mark.parametrize(
    "mutation",
    ["partial_gap", "reverse", "origin", "missing_force", "force_infinite", "repeated_block"],
)
def test_raw_clock_missingness_and_trial_blocks(tmp_path, mutation):
    _, files = fixture(tmp_path)
    rows = read(files["raw_trials"], "\t")
    if mutation == "partial_gap":
        rows[6][3] = "0.1"
    elif mutation == "reverse":
        rows[5][2] = "0.01"
    elif mutation == "origin":
        rows[3][2] = "0.001"
    elif mutation == "missing_force":
        rows[3][-1] = ""
    elif mutation == "force_infinite":
        rows[3][6] = "inf"
    else:
        rows.append(rows[3])
    write(files["raw_trials"], rows, "\t")
    with pytest.raises(ValueError):
        native_trials(files["raw_trials"])


def test_bounded_native_table(tmp_path):
    path = tmp_path / "table.csv"
    path.write_bytes(b"x" * 101)
    with pytest.raises(ValueError, match="Oversized"):
        table(path, ["x"], ["m"], max_bytes=100)
    write(path, [["x"], ["m"], ["none"], ["1"], ["2"]])
    with pytest.raises(ValueError, match="row count"):
        table(path, ["x"], ["m"], max_rows=4)


@pytest.mark.parametrize(
    "mutation",
    ["height_units", "height_clock", "height_infinite", "rheology_domain", "rheology_units"],
)
def test_auxiliary_native_sources_remain_guarded_even_when_not_predictors(tmp_path, mutation):
    recipe, files = fixture(tmp_path)
    path = next(tmp_path.glob("Height*")) if mutation.startswith("height") else files["rheology"]
    rows = read(path)
    if mutation == "height_units":
        rows[1][1] = "m"
    elif mutation == "height_clock":
        rows[-1][0] = rows[-2][0]
    elif mutation == "height_infinite":
        rows[-1][1] = "inf"
    elif mutation == "rheology_domain":
        rows[-1][3] = "-1"
    else:
        rows[1][1] = "Pa s"
    write(path, rows)
    with pytest.raises(ValueError):
        reconstruct_finger_friction(recipe, tmp_path)
