import copy

import pytest

from principia_asd.catalog.splits import (
    check_chronology,
    check_units,
    latest_development_groups,
    repartition_development,
)


def row(sample, group, t=0, stream=0):
    return {"sample_id": sample, "group": group, "t": t, "stream": stream, "target": t * 2}


def test_aggregation_groups_do_not_establish_independent_split_units():
    parts = {"train": [row("a", "wafer-a")], "dev": [row("b", "wafer-b")],
             "test": [row("c", "wafer-c")]}
    mapping = {"wafer-a": "batch-1", "wafer-b": "batch-1", "wafer-c": "batch-2"}
    result = check_units(parts, mapping)
    assert not result["valid"]
    assert result["shared_split_units"] == {"batch-1": ["dev", "train"]}
    del mapping["wafer-c"]
    assert check_units(parts, mapping)["unmapped_groups"] == ["wafer-c"]


def test_chronological_repair_is_per_stream_whole_group_and_preserves_every_value():
    parts = {"train": [row("a", "a", 1), row("b", "b", 4), row("e", "e", 11, 1)],
             "dev": [row("c", "c", 2), row("f", "f", 12, 1)],
             "test": [row("d", "d", 5), row("g", "g", 13, 1)]}
    original = copy.deepcopy(parts)
    args = {"time_column": "t", "stream_columns": ["stream"]}
    assert not check_chronology(parts, **args)["valid"]
    chosen = latest_development_groups(parts, **args)
    assert chosen == {"b", "f"}
    fixed = repartition_development(parts, chosen)
    assert check_chronology(fixed, **args)["valid"]
    assert fixed["test"] is parts["test"]
    assert sorted(fixed["train"] + fixed["dev"], key=lambda r: r["sample_id"]) == sorted(
        parts["train"] + parts["dev"], key=lambda r: r["sample_id"])
    assert parts == original


def test_equal_boundary_and_missing_stream_partition_are_not_ordered():
    parts = {"train": [row("a", "a", 1), row("d", "d", 0, 1)],
             "dev": [row("b", "b", 1)], "test": [row("c", "c", 3)]}
    result = check_chronology(parts, time_column="t", stream_columns=["stream"])
    assert not result["valid"]
    assert all(r["violations"] for r in result["streams"])


@pytest.mark.parametrize("corruption", ["overlapping_blocks", "nonfinite_time", "shared_group"])
def test_ambiguous_temporal_blocks_refuse_automatic_repair(corruption):
    parts = {"train": [row("a", "a", 1), row("b", "a", 2)],
             "dev": [row("c", "b", 3)], "test": [row("d", "c", 5)]}
    if corruption == "overlapping_blocks":
        parts["dev"][0]["t"] = 2
    elif corruption == "nonfinite_time":
        parts["dev"][0]["t"] = float("nan")
    else:
        parts["train"][1]["stream"] = 1
    with pytest.raises(ValueError):
        latest_development_groups(parts, time_column="t", stream_columns=["stream"])


def test_candidate_persistence_rejects_mutation(tmp_path):
    from scripts.review_data_edition import save_candidate

    parts = {"train": [row("a", "a")], "dev": [row("b", "b")], "test": [row("c", "c")]}
    review = {"candidate": {"valid": True}, "candidate_policy": "fixture"}
    paths = {"train": "a", "dev": "b", "test": "c"}
    saved = save_candidate(tmp_path, "fixture", parts, parts, review, {}, paths)
    assert save_candidate(tmp_path, "fixture", parts, parts, review, {}, paths) == saved
    (tmp_path / "fixture/train.csv.gz").write_bytes(b"altered")
    with pytest.raises(ValueError, match="mutated"):
        save_candidate(tmp_path, "fixture", parts, parts, review, {}, paths)


def test_candidate_cannot_change_observations_or_test_inputs(tmp_path):
    from scripts.review_data_edition import save_candidate

    parts = {"train": [row("a", "a")], "dev": [row("b", "b")], "test": [row("c", "c")]}
    changed = copy.deepcopy(parts)
    changed["dev"][0]["target"] = 8
    with pytest.raises(ValueError, match="changed observations"):
        save_candidate(tmp_path, "fixture", parts, changed,
                       {"candidate": {"valid": True}, "candidate_policy": "fixture"}, {}, {"test": "x"})
