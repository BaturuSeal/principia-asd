import csv
from datetime import datetime, timedelta

import pytest

from principia_asd.catalog.native import VERSION, reconstruct
from principia_asd.io import file_sha, sha, write_csv, write_json


def fermentation(tmp_path):
    root = tmp_path / "sources"
    root.mkdir()
    path = root / "process.csv"
    header = ["date", "batch_id", "hh", "hx", "undocumented_sensor"]
    rows = []
    for group in range(1, 4):
        start = datetime(2022, 1, 1) + timedelta(days=3 * group)
        for hour in range(25):
            rows.append(
                [
                    (start + timedelta(hours=hour)).strftime("%Y/%m/%d %H:%M"),
                    str(group),
                    str(hour),
                    str(group * 100 + 2 * hour),
                    "hidden state",
                ]
            )
    recipe = {
        "schema_version": VERSION,
        "scenario_id": "P100-086",
        "parser": "fermentation-historical-clock-audit-v1",
        "source_columns": header,
        "group_assignments": {"1": "train", "2": "dev", "3": "test"},
        "assets": [{"role": "fermentation_history", "path": path.name}],
    }

    def save():
        with path.open("w", newline="") as stream:
            csv.writer(stream).writerows([header, *rows])
        recipe["assets"][0].update(sha256=file_sha(path), bytes=path.stat().st_size)

    save()
    return root, recipe, rows, save


def test_fermentation_reconstruction_checks_real_clocks_and_full_batches(tmp_path):
    root, recipe, _, _ = fermentation(tmp_path)
    parts, lineage, checks = reconstruct(recipe, root)
    assert {p: len(r) for p, r in parts.items()} == {"train": 13, "dev": 13, "test": 13}
    assert checks["split_check"]["valid"]
    assert checks["temporal_validation"]["valid"]
    assert checks["admission_blockers"] == []
    assert all(r["slope6"] == 2 for rs in parts.values() for r in rs)
    assert all(r["lag_seconds"] == r["horizon_seconds"] == 21600 for r in lineage)
    assert lineage[0]["past_row"] == 2
    assert lineage[0]["origin_row"] == 8
    assert lineage[0]["target_row"] == 14
    assert all("target" not in row for row in parts["test"])


def test_nominal_six_hour_horizon_is_never_silently_equated_to_timestamp_hours(tmp_path):
    root, recipe, rows, save = fermentation(tmp_path)
    rows[-1][0] = (
        datetime.strptime(rows[-1][0], "%Y/%m/%d %H:%M") - timedelta(minutes=30)
    ).strftime("%Y/%m/%d %H:%M")
    save()
    parts, lineage, checks = reconstruct(recipe, root)
    temporal = checks["temporal_validation"]
    assert temporal["clock_disagreement_rows"] == 1
    assert temporal["timestamp_horizon_seconds_counts"] == {"19800": 1, "21600": 38}
    assert not temporal["valid"]
    assert len(parts["test"]) == 13  # Historical denominator is preserved.
    assert lineage[-1]["horizon_seconds"] == 19800
    assert "new reviewed task contract" in checks["admission_blockers"][0]


def test_interleaved_batch_split_is_reported_not_repaired(tmp_path):
    root, recipe, _, _ = fermentation(tmp_path)
    recipe["group_assignments"].update({"1": "dev", "2": "train"})
    _, _, checks = reconstruct(recipe, root)
    assert checks["split_check"]["valid"]  # Group separation alone is insufficient.
    assert not checks["temporal_validation"]["valid"]
    assert any("not chronologically separated" in r for r in checks["admission_blockers"])
    assert not checks["temporal_validation"]["partition_boundaries"][0][
        "batch_starts_strictly_ordered"
    ]


def test_calendar_window_overlap_is_distinct_from_batch_start_order(tmp_path):
    root, recipe, rows, save = fermentation(tmp_path)
    # Shift dev to 18 hours after train's start, while keeping all clocks ordered per batch.
    for row in rows[25:50]:
        stamp = datetime.strptime(row[0], "%Y/%m/%d %H:%M") - timedelta(hours=54)
        row[0] = stamp.strftime("%Y/%m/%d %H:%M")
    save()
    _, _, checks = reconstruct(recipe, root)
    boundary = checks["temporal_validation"]["partition_boundaries"][0]
    assert boundary["batch_starts_strictly_ordered"]
    assert not boundary["all_targets_before_next_origins"]
    assert any("Acquisition windows overlap" in r for r in checks["admission_blockers"])


def test_future_terminal_response_and_undocumented_fields_do_not_change_inputs(tmp_path):
    root, recipe, rows, save = fermentation(tmp_path)
    before = reconstruct(recipe, root)[0]
    rows[-1][3] = "9000"
    for row in rows:
        row[4] = "=hidden_target_transform"
    save()
    assert reconstruct(recipe, root)[0] == before


def test_duplicate_nominal_hours_are_retained_as_clock_evidence(tmp_path):
    root, recipe, rows, save = fermentation(tmp_path)
    rows[-1][2] = rows[-2][2]
    save()
    _, _, checks = reconstruct(recipe, root)
    assert checks["duplicate_nominal_clocks"] == [
        {"batch": "3", "nominal_hh": 23, "source_rows": [75, 76]}
    ]
    assert checks["temporal_validation"]["source_clock_ties_are_not_merged"]
    assert checks["source_batches"][-1]["source_rows"] == 25


def test_clock_review_is_bound_to_contract_and_preserves_all_public_data(tmp_path):
    from scripts.review_fermentation import review

    root, recipe, _, _ = fermentation(tmp_path)
    parts, _, _ = reconstruct(recipe, root)
    data = tmp_path / "edition"
    scenario = data / "scenarios/P100-086"
    task = {
        "task_id": "clock-fixture",
        "scenario_id": "P100-086",
        "split": {p: f"public/{p}.csv.gz" for p in parts},
    }
    write_json(scenario / "task-contracts/task-001.json", task)
    for p, rows in parts.items():
        write_csv(scenario / task["split"][p], rows, list(rows[0]))
    recipe["historical_contract_sha256"] = sha(task)
    rp = tmp_path / "recipe.json"
    write_json(rp, recipe)
    before = {p: file_sha(p) for p in data.rglob("*") if p.is_file()}
    result = review(rp, root, data)
    assert result["status"] == "timing_checks_passed"
    assert result["source_batches"] == result["eligible_batches"] == 3
    assert not result["evaluator_vault_accessed"]
    assert not result["quantitative_scores_changed"]
    assert result["historical_public_parity"]["status"] == "passed"
    assert before == {p: file_sha(p) for p in data.rglob("*") if p.is_file()}
    task["task_id"] = "different-contract"
    write_json(scenario / "task-contracts/task-001.json", task)
    with pytest.raises(ValueError, match="contract changed"):
        review(rp, root, data)


@pytest.mark.parametrize(
    "defect",
    [
        "duplicate_stamp",
        "reversed_stamp",
        "bad_stamp",
        "bad_batch",
        "negative_clock",
        "nan",
        "formula",
        "ragged",
        "column_alias",
        "unregistered_group",
    ],
)
def test_fermentation_refuses_ambiguous_or_invalid_sources(tmp_path, defect):
    root, recipe, rows, save = fermentation(tmp_path)
    if defect == "duplicate_stamp":
        rows[1][0] = rows[0][0]
    elif defect == "reversed_stamp":
        rows[0][0], rows[1][0] = rows[1][0], rows[0][0]
    elif defect == "bad_stamp":
        rows[0][0] = "not a date"
    elif defect == "bad_batch":
        rows[0][1] = "01"
    elif defect == "negative_clock":
        rows[0][2] = "-1"
    elif defect in {"nan", "formula"}:
        rows[0][3] = "NaN" if defect == "nan" else "=SUM(D1:D2)"
    elif defect == "ragged":
        rows[0].pop()
    elif defect == "column_alias":
        recipe["source_columns"][-1] = "hx"
    else:
        recipe["group_assignments"].pop("3")
    save()
    with pytest.raises(ValueError):
        reconstruct(recipe, root)
