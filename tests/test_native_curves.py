import copy
import csv
import io
import zipfile

import pytest

from principia_asd.catalog.native import VERSION, reconstruct
from principia_asd.io import file_sha


def kinase(tmp_path):
    header = ["Time (min)"] + [f"BS {i}uM" for i in range(1, 10)] + [""] * 11
    rows = [
        [str(t)] + [str(j * 10 + 2 * t - 30) for j in range(9)] + ["--"] * 11
        for t in [0, 1.5, 3, 4.5, 6, 7.5, 9, 10.5, 12, 13.5]
    ]
    rows[7][1] = "--"
    rows += [["--"] * 21, ["90"] + ["--"] * 20]
    root = tmp_path / "sources"
    root.mkdir()
    path = root / "curves.csv"
    recipe = {
        "schema_version": VERSION,
        "scenario_id": "P100-074",
        "parser": "src-kinase-calibrated-curves-v1",
        "source_columns": header,
        "group_assignments": {
            f"dose-{i}": ("train" if i < 4 else "dev" if i < 7 else "test") for i in range(1, 10)
        },
        "assets": [{"role": "kinase_curves", "path": path.name}],
    }

    def save():
        with path.open("w", newline="") as stream:
            csv.writer(stream).writerows([header, *rows])
        recipe["assets"][0].update(sha256=file_sha(path), bytes=path.stat().st_size)

    save()
    return root, recipe, rows, save


def neuronal(tmp_path):
    header = [
        "filename",
        "sweep",
        "applied current",
        "spike count",
        "stimulus range",
        "Measurement ID",
        "date",
        "Stiffness",
        "div",
        "Condition",
        "dish",
        "cell",
        "frequency",
        "use for FI (manually confirmed)",
    ]
    rows = []
    groups = {}
    for j, split in enumerate(["train", "dev", "test"]):
        date, dish = f"2025010{j + 1}", f"D{j + 1}"
        groups[date + ":" + dish] = split
        for cell in ["C1", "C2"]:
            for sweep in [0, 5, 2, 4, 1, 3]:  # Source order is not acquisition order.
                values = [
                    f"{date}_{dish}_{cell}.abf",
                    str(sweep),
                    str([-10, 0, 10, 14, 18, 22][sweep]),
                    str(sweep),
                    "0:1",
                    "m1",
                    date,
                    "0.1kPa",
                    "7",
                    "Control",
                    dish,
                    cell,
                    "not an input; target-derived",
                    "y",
                ]
                rows.append(dict(zip(header, values, strict=True)))
    root = tmp_path / "sources"
    root.mkdir()
    path = root / "records.zip"
    recipe = {
        "schema_version": VERSION,
        "scenario_id": "P100-076",
        "parser": "neuronal-prefix-curves-v1",
        "source_columns": header,
        "archive_member": "data/curves.csv",
        "group_assignments": groups,
        "assets": [{"role": "neuronal_archive", "path": path.name}],
    }

    def save():
        text = io.StringIO(newline="")
        writer = csv.DictWriter(text, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(recipe["archive_member"], text.getvalue())
        recipe["assets"][0].update(sha256=file_sha(path), bytes=path.stat().st_size)

    save()
    return root, recipe, rows, save


def test_kinase_reconstruction_keeps_units_missing_rows_and_negative_baselines(tmp_path):
    root, recipe, _, _ = kinase(tmp_path)
    parts, lineage, checks = reconstruct(recipe, root)
    assert {p: len(r) for p, r in parts.items()} == {"train": 11, "dev": 12, "test": 12}
    assert checks["split_check"]["valid"]
    assert checks["rows_without_time_or_response"] == [12]
    assert checks["curves"][0]["missing_source_rows"] == [9, 12, 13]
    assert parts["train"][0]["target"] < 0
    assert all(
        r["calibration_v6"] == 2 and r["calibration_curvature"] == 0
        for rows in parts.values()
        for r in rows
    )
    assert all(r["calibration_rows"] == [4, 5, 6] and r["row"] >= 8 for r in lineage)
    assert all("target" not in r for r in parts["test"])


def test_kinase_heldout_responses_and_unregistered_columns_do_not_change_inputs(tmp_path):
    root, recipe, rows, save = kinase(tmp_path)
    before = reconstruct(recipe, root)[0]
    for row in rows:
        row[10:] = ["hidden fitted state"] * 11
        if row[0] != "--" and float(row[0]) > 7.5:
            for i in [7, 8, 9]:
                if row[i] != "--":
                    row[i] = str(float(row[i]) + 1234)
    save()
    assert reconstruct(recipe, root)[0] == before


@pytest.mark.parametrize(
    "defect", ["time", "missing_time", "calibration", "nan", "formula", "dose", "units", "width"]
)
def test_kinase_rejects_ambiguous_or_invalid_measurements(tmp_path, defect):
    root, recipe, rows, save = kinase(tmp_path)
    if defect == "time":
        rows[1][0] = "0"
    elif defect == "missing_time":
        rows[-2][1] = "2"
    elif defect == "calibration":
        rows[4][1] = "--"
    elif defect in {"nan", "formula"}:
        rows[6][1] = "NaN" if defect == "nan" else "=2*B1"
    elif defect == "dose":
        recipe["source_columns"][2] = "BS 01uM"
    elif defect == "units":
        recipe["source_columns"][1] = "BS 1mM"
    else:
        rows[1].pop()
    save()
    with pytest.raises(ValueError):
        reconstruct(recipe, root)


def test_neuronal_calibration_uses_sweep_order_and_preserves_whole_dishes(tmp_path):
    root, recipe, _, _ = neuronal(tmp_path)
    parts, lineage, checks = reconstruct(recipe, root)
    assert {p: len(r) for p, r in parts.items()} == {"train": 6, "dev": 6, "test": 6}
    assert checks["split_check"]["valid"]
    assert checks["source_cell_count"] == 6
    assert len(checks["recordings"]) == 6
    assert all(r["cal_mean"] == 1 and r["cal_last"] == 2 for rs in parts.values() for r in rs)
    assert lineage[0]["row"] == 7  # Sweep 3 occurs later physically than sweep 5.
    assert lineage[0]["calibration_rows"] == [2, 6, 4]
    assert all(r["calibration_sweeps"] == [0, 1, 2] for r in lineage)
    assert all("target" not in r for r in parts["test"])


def test_neuronal_future_counts_and_derived_frequency_never_change_inputs(tmp_path):
    root, recipe, rows, save = neuronal(tmp_path)
    before = reconstruct(recipe, root)[0]
    for row in rows:
        row["frequency"] = "unavailable hidden target"
        if row["date"] == "20250103" and int(row["sweep"]) >= 3:
            row["spike count"] = "999"
    save()
    assert reconstruct(recipe, root)[0] == before


def test_neuronal_repeated_cell_recordings_remain_in_one_partition(tmp_path):
    root, recipe, rows, save = neuronal(tmp_path)
    repeat = copy.deepcopy(rows[:6])
    for row in repeat:
        row["filename"] = "repeated.abf"
    rows.extend(repeat)
    save()
    parts, _, checks = reconstruct(recipe, root)
    assert len(parts["train"]) == 9
    assert checks["source_cell_count"] == 6
    assert len(checks["recordings"]) == 7
    assert checks["repeated_cell_recordings"] == [
        {
            "date": "20250101",
            "dish": "D1",
            "cell": "C1",
            "recordings": ["20250101_D1_C1.abf", "repeated.abf"],
        }
    ]
    for row in repeat:
        row["Condition"] = "P1 KD"
    save()
    with pytest.raises(ValueError, match="inconsistent conditions"):
        reconstruct(recipe, root)


def test_neuronal_retains_author_exclusions_with_explicit_lineage(tmp_path):
    root, recipe, rows, save = neuronal(tmp_path)
    rows[1]["use for FI (manually confirmed)"] = "n"
    save()
    parts, _, checks = reconstruct(recipe, root)
    assert len(parts["train"]) == 5
    assert checks["recordings"][0]["excluded_by_source_quality_rows"] == [3]


def test_neuronal_recipe_cannot_move_final_date_into_training(tmp_path):
    root, recipe, _, _ = neuronal(tmp_path)
    recipe["group_assignments"]["20250101:D1"] = "test"
    recipe["group_assignments"]["20250103:D3"] = "train"
    with pytest.raises(ValueError, match="complete final recording date"):
        reconstruct(recipe, root)


@pytest.mark.parametrize(
    "defect",
    [
        "repeat_sweep",
        "future_cal",
        "quality",
        "missing_id",
        "condition",
        "cell",
        "count",
        "nan",
        "formula",
        "missing_group",
    ],
)
def test_neuronal_rejects_leakage_ambiguous_identity_and_invalid_counts(tmp_path, defect):
    root, recipe, rows, save = neuronal(tmp_path)
    if defect == "repeat_sweep":
        rows[1]["sweep"] = "0"
    elif defect == "future_cal":
        rows[1]["applied current"] = "0"
    elif defect == "quality":
        rows[0]["use for FI (manually confirmed)"] = "n"
    elif defect == "missing_id":
        rows[0]["filename"] = ""
    elif defect == "condition":
        rows[0]["Condition"] = "unknown"
    elif defect == "cell":
        rows[0]["cell"] = "C9"
    elif defect in {"count", "nan", "formula"}:
        rows[0]["spike count"] = {"count": "0.5", "nan": "NaN", "formula": "=B1"}[defect]
    else:
        recipe["group_assignments"].pop("20250101:D1")
    save()
    with pytest.raises(ValueError):
        reconstruct(recipe, root)
