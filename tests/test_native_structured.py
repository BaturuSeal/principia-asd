"""Scientific calibration, identity and custody guards for the structured readers."""

import copy
import csv
import importlib.util
import json
from pathlib import Path

import pytest

from principia_asd.catalog.native import identity, reconstruct
from principia_asd.io import file_sha


def register(path, recipe):
    recipe["assets"][0].update(bytes=path.stat().st_size, sha256=file_sha(path))


def training_fixture(tmp_path):
    root = tmp_path / "raw"
    root.mkdir()
    path = root / "histories.jsonl"
    records = []
    for width in [256, 512, 768]:
        records.append(
            {
                "model_id": f"{width}x3",
                "width": width,
                "depth": 3,
                "params": width * 1000,
                "pretrain": True,
                "cooldown": False,
                "val_loss_by_optimiser_step": {
                    "1000": 3.0,
                    "4000": 2.5,
                    "6000": 2.0,
                    "10000": 1.5,
                    "11000": None,
                    "25000": 1.0,
                },
                "global_loss": "must not become input",
                "val_loss": -999999,
            }
        )
    # A linked cooldown run is excluded before any scientific measurement is read.
    records.append({"model_id": "256x3", "pretrain": False, "cooldown": True})
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    recipe = {
        "schema_version": "native-reconstruction/1",
        "scenario_id": "P100-043",
        "parser": "gemstones-hot-trajectories-v1",
        "assets": [{"path": path.name, "role": "training_histories"}],
        "group_assignments": {"256x3": "train", "512x3": "dev", "768x3": "test"},
    }
    register(path, recipe)
    return root, path, recipe, records


def write_histories(path, recipe, records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    register(path, recipe)


def test_hot_trajectory_anchors_causally_precede_predictions_and_groups_stay_whole(tmp_path):
    root, _, recipe, _ = training_fixture(tmp_path)
    parts, lineage, checks = reconstruct(recipe, root)
    assert {p: len(r) for p, r in parts.items()} == {"train": 2, "dev": 2, "test": 2}
    assert checks["split_check"]["valid"]
    assert checks["excluded_non_hot_source_lines"] == [4]
    assert all(s["excluded_missing_steps"] == ["11000"] for s in checks["histories"])
    for rows in parts.values():
        for row in rows:
            assert row["early_tokens_B"] <= 10
            assert 10 < row["anchor_tokens_B"] <= 20 < row["tokens_B"] <= 100
            assert row["early_loss"] == 3 and row["anchor_loss"] == 2.5
            assert "global_loss" not in row and "val_loss" not in row
    assert all(item["permitted_calibration_precedes_response"] for item in lineage)
    assert all("target" not in row for row in parts["test"])
    assert parts["test"][0]["sample_id"] == identity("P100-043", "sample", "768x3|hot|step=6000")


def test_test_responses_future_checkpoints_and_summary_fields_cannot_change_inputs(tmp_path):
    root, path, recipe, records = training_fixture(tmp_path)
    before = reconstruct(recipe, root)
    records[2]["val_loss_by_optimiser_step"].update({"6000": 99999, "10000": 123456})
    for r in records[:3]:
        r["val_loss_by_optimiser_step"]["25000"] = 9999999
        r["global_loss"] = 98765
        r["val_loss"] = 23456
        r["fitted_encoder_state"] = ["arbitrary future fitted state"]
    write_histories(path, recipe, records)
    assert reconstruct(recipe, root) == before


@pytest.mark.parametrize(
    "fault",
    [
        "duplicate_architecture",
        "metadata_alias",
        "missing_anchor",
        "ambiguous_stage",
        "step_alias",
        "negative_loss",
        "missing_group",
    ],
)
def test_trajectory_rejects_ambiguous_identity_calibration_and_assignments(tmp_path, fault):
    root, path, recipe, records = training_fixture(tmp_path)
    if fault == "duplicate_architecture":
        records.append(copy.deepcopy(records[0]))
    elif fault == "metadata_alias":
        records[0]["width"] = 100
    elif fault == "missing_anchor":
        records[0]["val_loss_by_optimiser_step"].pop("4000")
    elif fault == "ambiguous_stage":
        records[0]["pretrain"] = "True"
    elif fault == "step_alias":
        records[0]["val_loss_by_optimiser_step"]["06000"] = 2.0
    elif fault == "negative_loss":
        records[0]["val_loss_by_optimiser_step"]["6000"] = -1
    elif fault == "missing_group":
        recipe["group_assignments"].pop("256x3")
    write_histories(path, recipe, records)
    with pytest.raises(ValueError):
        reconstruct(recipe, root)


def test_duplicate_checkpoint_keys_fail_instead_of_silently_overwriting(tmp_path):
    root, path, recipe, _ = training_fixture(tmp_path)
    path.write_text(path.read_text().replace('"6000": 2.0', '"6000": 9999, "6000": 2.0', 1))
    register(path, recipe)
    with pytest.raises(ValueError, match="Duplicate JSON"):
        reconstruct(recipe, root)


def fet_fixture(tmp_path):
    root = tmp_path / "raw"
    root.mkdir()
    path = root / "sweeps.csv"
    rows = [["wave0", "wave1", "wave2", "wave3"]]
    rows += [[v, *[(i + (v + 20) / 10) * 1e-6 for i in [1, 2, 3]]] for v in [-20, -10, 0, 10, 20]]
    recipe = {
        "schema_version": "native-reconstruction/1",
        "scenario_id": "P100-051",
        "parser": "fet-calibrated-sweeps-v1",
        "source_columns": rows[0],
        "assets": [{"path": path.name, "role": "fet_sweeps"}],
        "group_assignments": {"device-01": "train", "device-02": "dev", "device-03": "test"},
    }
    write_sweeps(path, recipe, rows)
    return root, path, recipe, rows


def write_sweeps(path, recipe, rows):
    with path.open("w", newline="") as stream:
        csv.writer(stream).writerows(rows)
    register(path, recipe)


def test_fet_expands_calibration_and_keeps_source_columns_and_scored_rows_separate(tmp_path):
    root, _, recipe, _ = fet_fixture(tmp_path)
    parts, lineage, checks = reconstruct(recipe, root)
    assert checks["split_check"]["units_by_partition"] == {
        "train": ["wave1"],
        "dev": ["wave2"],
        "test": ["wave3"],
    }
    assert checks["calibration_rows_excluded_from_response_cohort"] == [2, 4, 6]
    assert all(item["row"] not in item["calibration_rows"] for item in lineage)
    assert parts["test"][0]["cal_minus20_uA"] == 3
    assert parts["test"][0]["cal_zero_uA"] == pytest.approx(5)
    assert parts["test"][0]["cal_plus20_uA"] == 7
    assert parts["test"][0]["sample_id"] == identity("P100-051", "sample", "device-03:row-3")
    assert all("target" not in row for row in parts["test"])
    assert "no fabrication-batch" in checks["independence_scope"]


def test_undisclosed_fet_test_responses_cannot_change_any_exported_measurement(tmp_path):
    root, path, recipe, rows = fet_fixture(tmp_path)
    before = reconstruct(recipe, root)
    # Source rows 3 and 5 are neither disclosed anchors nor public test targets.
    rows[2][3] = 99999
    rows[4][3] = 88888
    write_sweeps(path, recipe, rows)
    assert reconstruct(recipe, root) == before


@pytest.mark.parametrize(
    "fault",
    [
        "column_alias",
        "future_column",
        "reversed_voltage",
        "missing_anchor",
        "outside_domain",
        "formula",
        "nonfinite",
        "ragged_row",
    ],
)
def test_fet_rejects_unsupported_layout_and_measurement_semantics(tmp_path, fault):
    root, path, recipe, rows = fet_fixture(tmp_path)
    if fault == "column_alias":
        rows[0][3] = "wave2"
    elif fault == "future_column":
        rows[0].append("fitted_target")
    elif fault == "reversed_voltage":
        rows[2][0] = -21
    elif fault == "missing_anchor":
        rows[3][0] = 1
    elif fault == "outside_domain":
        rows.append([30, 0, 0, 0])
    elif fault == "formula":
        rows[2][1] = "=2*B2"
    elif fault == "nonfinite":
        rows[2][1] = "nan"
    elif fault == "ragged_row":
        rows[2].pop()
    write_sweeps(path, recipe, rows)
    with pytest.raises(ValueError):
        reconstruct(recipe, root)


def test_selected_recipe_verification_rejects_unknown_identity_before_writing(tmp_path):
    script = Path(__file__).parents[1] / "scripts/verify_native_reconstruction.py"
    spec = importlib.util.spec_from_file_location("native_verifier", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = tmp_path / "must-not-be-created"
    with pytest.raises(ValueError, match="Unknown"):
        module.verify(
            tmp_path,
            tmp_path / "raw",
            tmp_path / "data",
            output,
            Path("python"),
            selected_scenarios=["P100-NOT-REGISTERED"],
        )
    assert not output.exists()
