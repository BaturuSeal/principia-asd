import csv
import io
import zipfile
from copy import deepcopy

import pytest

from principia_asd.catalog.shed import (
    FIELDS,
    INCOME,
    INPUT_UNITS,
    MEMBER,
    OUTPUT_UNITS,
    STATES,
    bounded_lines,
    build_rows,
    decode_archive,
    hashgroup,
    numeric,
    reconstruct_shed,
)


def archive(tmp_path, rows, *, member=MEMBER, header=None, extra=False):
    header = header or [*FIELDS, *[f"unused{i}" for i in range(815 - len(FIELDS))]]
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(header)
    for i, values in enumerate(rows):
        row = dict.fromkeys(header, "")
        row.update(
            shedid=str(202500001 + i),
            EF3_h="No",
            D1A="Yes",
            ppinc7="$50,000 to $74,999",
            pphhsize="3",
            ppage="40",
            weight="1",
            ppstaten="ca",
            EF3_h_iflag="0",
            D1A_iflag="0",
            field_month="10",
            field_day="18",
        )
        row.update(values)
        writer.writerow([row[k] for k in header])
    path = tmp_path / "source.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(member, out.getvalue())
        if extra:
            z.writestr("unknown.csv", "unexpected")
    return path


def recipe(states):
    ordered = sorted(states, key=lambda s: hashgroup("SHED-state:" + s))
    held = set(ordered[: max(1, len(states) // 5)])
    dev = next(s for s in ordered if s not in held)
    return {
        "scenario_id": "P100-015",
        "input_units": INPUT_UNITS,
        "output_units": OUTPUT_UNITS,
        "assets": [
            {"role": "respondents_archive", "path": "source.zip"},
            {"role": "codebook", "path": "codebook.pdf"},
        ],
        "group_assignments": {
            "state:" + s: "test" if s in held else "dev" if s == dev else "train" for s in states
        },
    }


def panel(tmp_path):
    rows = [{"ppstaten": s} for s in sorted(STATES)]
    records, inv = decode_archive(archive(tmp_path, rows))
    return records, inv, recipe(inv["states_before_eligibility"])


def test_income_brackets_expand_to_fixed_proxies_not_measured_income(tmp_path):
    rows, inv = decode_archive(archive(tmp_path, [{"ppinc7": s} for s in INCOME]))
    assert [r["income_proxy"] for r in rows] == [5, 17.5, 37.5, 62.5, 87.5, 125, 175]
    assert inv["source_records"] == 7 and inv["excluded_records"] == 0
    assert [r["source_row"] for r in rows] == list(range(2, 9))


def test_nonwork_is_complement_of_paid_work_not_jobloss(tmp_path):
    rows, _ = decode_archive(archive(tmp_path, [{"D1A": "No", "EF3_h": "Yes"}, {}]))
    assert [(r["shock"], r["target"]) for r in rows] == [(1, 1), (0, 0)]


def test_imputed_answers_preserved_and_separately_counted(tmp_path):
    rows, inv = decode_archive(archive(tmp_path, [{"D1A_iflag": "1"}, {"EF3_h_iflag": "1"}]))
    assert len(rows) == 2 and inv["source_imputation_counts"] == {"D1A": 1, "EF3_h": 1}
    assert rows[0]["work_imputed"] == 1 and rows[1]["target_imputed"] == 1


def test_missingness_and_nonpositive_weight_do_not_get_imputed(tmp_path):
    rows, inv = decode_archive(
        archive(
            tmp_path,
            [
                {},
                {"EF3_h": "."},
                {"D1A": ""},
                {"ppinc7": "."},
                {"weight": "0"},
                {"ppage": "17"},
                {"pphhsize": "21"},
                {"ppstaten": ""},
            ],
        )
    )
    assert len(rows) == 1 and inv["excluded_records"] == 7
    assert sum(inv["exclusion_reason_counts_nonexclusive"].values()) == 7


@pytest.mark.parametrize("value", ["NaN", "inf", "1e999", "unknown", " 1"])
def test_invalid_numeric_data_fails(value):
    with pytest.raises(ValueError):
        numeric(value)


def test_integer_numeric_guard_and_documented_empty_codes():
    assert numeric(".") is None and numeric("") is None and numeric("1.5") == 1.5
    with pytest.raises(ValueError):
        numeric("1.5", integer=True)


@pytest.mark.parametrize(
    "mutation",
    [
        {"shedid": "202500001.0"},
        {"shedid": "0202500001"},
        {"EF3_h": "Maybe"},
        {"D1A_iflag": "2"},
        {"ppinc7": "$200,000 or more"},
        {"ppstaten": "CA"},
        {"field_month": "11"},
        {"field_day": "29"},
        {"ppage": "40.5"},
    ],
)
def test_source_id_categories_flags_and_clock_guards(tmp_path, mutation):
    with pytest.raises(ValueError):
        decode_archive(archive(tmp_path, [mutation]))


def test_duplicate_id_rejected_even_if_second_row_ineligible(tmp_path):
    with pytest.raises(ValueError, match="duplicate"):
        decode_archive(archive(tmp_path, [{}, {"shedid": "202500001", "weight": "0"}]))


def test_confirmation_selection_uses_full_source_state_inventory(tmp_path):
    records, inv, rec = panel(tmp_path)
    parts, _, split, _ = build_rows(rec, records, inv["states_before_eligibility"])
    assert split["valid"] and {p: len(rows) for p, rows in parts.items()} == {
        "train": 40,
        "dev": 1,
        "test": 10,
    }
    dropped = next(r for r in records if rec["group_assignments"]["state:" + r["state"]] == "test")
    remainder = [r for r in records if r is not dropped]
    reduced = build_rows(rec, remainder, inv["states_before_eligibility"])[0]
    assert len(reduced["test"]) == 9 and reduced["train"] == parts["train"]
    with pytest.raises(ValueError):
        build_rows(
            rec, remainder, [s for s in inv["states_before_eligibility"] if s != dropped["state"]]
        )


def test_test_targets_and_individual_flags_never_exported(tmp_path):
    records, inv, rec = panel(tmp_path)
    for r in records:
        r["target_imputed"] = 1
    parts, lineage, split, flags = build_rows(rec, records, inv["states_before_eligibility"])
    assert flags["test"]["target"] == 10 and split["valid"]
    assert all("target" not in r and "target_imputed" not in r for r in parts["test"])
    assert all(set(a) == {"sample_id", "split", "source_row", "member"} for a in lineage)
    other = deepcopy(records)
    for r in other:
        if rec["group_assignments"]["state:" + r["state"]] == "test":
            r["target"] = 1 - r["target"]
    assert build_rows(rec, other, inv["states_before_eligibility"]) == (
        parts,
        lineage,
        split,
        flags,
    )


def test_excluded_answers_and_weights_do_not_change_measurements(tmp_path):
    a, ai = decode_archive(archive(tmp_path, [{}]))
    b, bi = decode_archive(
        archive(tmp_path, [{"unused1": "HIDDEN FINANCIAL ANSWER", "weight": "3.4"}])
    )
    assert a == b and ai["eligible_weights"] != bi["eligible_weights"]
    assert "HIDDEN" not in str(b)


def test_unknown_confirmation_and_repeated_rows_rejected(tmp_path):
    records, inv, rec = panel(tmp_path)
    with pytest.raises(ValueError, match="Repeated"):
        build_rows(rec, records + records[:1], inv["states_before_eligibility"])
    key = next(g for g, s in rec["group_assignments"].items() if s == "test")
    rec["group_assignments"][key] = "train"
    with pytest.raises(ValueError, match="confirmation"):
        build_rows(rec, records, inv["states_before_eligibility"])


@pytest.mark.parametrize(
    "kwargs",
    [
        {"member": "../public2025.csv"},
        {"member": "other.csv"},
        {"extra": True},
        {"header": list(FIELDS)},
    ],
)
def test_unsafe_archive_and_schema_rejected(tmp_path, kwargs):
    with pytest.raises(ValueError):
        decode_archive(archive(tmp_path, [{}], **kwargs))


def test_multiline_or_oversized_sources_rejected(tmp_path):
    with pytest.raises(ValueError, match="physical-line"):
        decode_archive(archive(tmp_path, [{"unused1": "line1\nline2"}]))
    for b in [b"x" * 100001, b"null\x00byte"]:
        with pytest.raises(ValueError):
            list(bounded_lines(io.BytesIO(b)))


def test_recipe_units_and_roles_cannot_silently_change(tmp_path):
    rec = recipe(["ca", "fl", "ny", "tx", "wa"])
    rec["output_units"] = "income"
    with pytest.raises(ValueError, match="units"):
        reconstruct_shed(rec, tmp_path)
    rec["output_units"] = OUTPUT_UNITS
    rec["assets"].pop()
    with pytest.raises(ValueError, match="roles"):
        reconstruct_shed(rec, tmp_path)
