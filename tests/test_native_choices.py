import copy
import csv

import pytest

from principia_asd.catalog.choices import COLUMNS
from principia_asd.catalog.native import VERSION, identity, reconstruct
from principia_asd.io import file_sha


def choices(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    path = root / "choices.csv"
    subjects = [f"{i:064x}" for i in range(1, 4)]
    rows = []
    for person in subjects:
        for protocol in ("E1.1", "E1.2"):
            for trial in (3, 1, 4, 2):  # Physical row order differs from trial order.
                rows.append(
                    [
                        person,
                        "adult",
                        "H",
                        protocol,
                        "1",
                        "1",
                        str(trial),
                        "4",
                        ".5",
                        "nan",
                        str(trial % 2),
                        "=EXCLUDED()",
                    ]
                )
    recipe = {
        "schema_version": VERSION,
        "scenario_id": "P100-089",
        "parser": "risk-choice-identity-order-audit-v1",
        "assets": [{"role": "risk_choices", "path": path.name}],
        "group_assignments": dict(zip(subjects, ("train", "dev", "test"), strict=True)),
    }

    def save(modifier=None):
        values = copy.deepcopy(rows)
        if modifier:
            modifier(values)
        with path.open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(COLUMNS)
            writer.writerows(values)
        recipe["assets"][0].update(bytes=path.stat().st_size, sha256=file_sha(path))

    save()
    return root, recipe, save, subjects


def test_choice_parity_and_exact_lineage(tmp_path):
    root, recipe, _, subjects = choices(tmp_path)
    parts, lineage, checks = reconstruct(recipe, root)
    assert {p: len(v) for p, v in parts.items()} == dict.fromkeys(("train", "dev", "test"), 8)
    assert checks["split_check"]["valid"]
    assert all("target" not in r for r in parts["test"])
    first = parts["train"][:4]
    assert [r["sample_id"] for r in first] == [
        identity("P100-089", "sample", f"row{n}") for n in (3, 5, 2, 4)
    ]
    assert [r["target"] for r in first] == [1, 0, 1, 0]
    assert [r["lag_choice"] for r in first] == [0.5, 1, 0, 1]
    assert [r["history_mean"] for r in first] == [0.5, 1, 0.5, 2 / 3]
    assert parts["train"][4]["has_history"] == 0  # Different protocol, new history.
    series = checks["history_series"][0]
    assert series["group"] == identity("P100-089", "group", subjects[0])
    assert series["source_rows_in_historical_order"] == [3, 5, 2, 4]
    assert [r["history_count"] for r in lineage[:4]] == [0, 1, 2, 3]
    assert not checks["choice_validation"]["strict_prior_history_verified"]


def test_choice_future_and_test_response_boundary(tmp_path):
    root, recipe, save, _ = choices(tmp_path)
    before, _, _ = reconstruct(recipe, root)
    # Flip trial 3 in the test subject's first protocol. It affects only trial 4's inputs.
    save(lambda rows: rows[16].__setitem__(10, "0"))
    after, _, _ = reconstruct(recipe, root)
    assert before["train"] == after["train"] and before["dev"] == after["dev"]
    assert before["test"][:3] == after["test"][:3]
    assert before["test"][3]["lag_choice"] != after["test"][3]["lag_choice"]
    assert before["test"][4:] == after["test"][4:]
    assert all("target" not in r for r in after["test"])


def test_choice_ties_are_retained_and_fail_admission(tmp_path):
    root, recipe, save, _ = choices(tmp_path)

    def duplicate(rows):
        row = copy.deepcopy(rows[0])
        row[10] = "0"  # Different response at identical subject/protocol/session/block/trial.
        rows.extend([row, copy.deepcopy(rows[0])])

    save(duplicate)
    parts, _, checks = reconstruct(recipe, root)
    assert len(parts["train"]) == 10
    audit = checks["choice_validation"]
    assert audit["status"] == "preparation_defect"
    assert audit["repeated_order_keys"] == 1
    assert audit["extra_rows_with_tied_order"] == 2
    assert audit["tied_order_keys_with_conflicting_choices"] == 1
    assert audit["exact_duplicate_source_rows_beyond_first"] == 1
    assert not audit["source_row_tie_break_establishes_chronology"]
    assert checks["order_ties"]["rows"] == [[0, 1, 1, 3, [2, 26, 27]]]
    assert len(checks["admission_blockers"]) == 3


def test_choice_identity_conflicts_cannot_be_renamed_away(tmp_path):
    root, recipe, save, _ = choices(tmp_path)

    def conflict(rows):
        rows[0][1] = "9"
        rows[1][2] = "F"

    save(conflict)
    parts, _, checks = reconstruct(recipe, root)
    audit = checks["choice_validation"]
    assert len(parts["train"]) == 8
    assert audit["status"] == "preparation_defect"
    assert audit["subject_ids"] == 3
    assert audit["subject_ids_with_multiple_ages"] == 1
    assert audit["subject_ids_with_multiple_sex_codes"] == 1
    assert checks["split_check"]["valid"]  # Identifier separation alone is insufficient.


@pytest.mark.parametrize(("column", "value"), [(9, "=FORBIDDEN()"), (11, "nan"), (2, "F")])
def test_choice_excluded_columns_never_change_inputs(tmp_path, column, value):
    root, recipe, save, _ = choices(tmp_path)
    before = reconstruct(recipe, root)[0]
    save(lambda rows: rows[0].__setitem__(column, value))
    assert reconstruct(recipe, root)[0] == before


@pytest.mark.parametrize(
    ("column", "value"),
    [
        (0, "unknown"),
        (1, "-1"),
        (1, "2.5"),
        (1, "121"),
        (2, "unknown"),
        (3, "E2.1"),
        (4, "0"),
        (5, "1.2"),
        (6, "41"),
        (7, "nan"),
        (7, "-1"),
        (8, "1.1"),
        (10, ".5"),
    ],
)
def test_choice_malformed_measurement_is_rejected(tmp_path, column, value):
    root, recipe, save, _ = choices(tmp_path)
    save(lambda rows: rows[0].__setitem__(column, value))
    with pytest.raises(ValueError):
        reconstruct(recipe, root)


def test_choice_source_mutation_and_unregistered_group_rejected(tmp_path):
    root, recipe, _, subjects = choices(tmp_path)
    recipe["group_assignments"].pop(subjects[0])
    with pytest.raises(ValueError, match="independent-unit"):
        reconstruct(recipe, root)
    (root / "choices.csv").write_text("altered")
    with pytest.raises(ValueError, match="hash or size"):
        reconstruct(recipe, root)
