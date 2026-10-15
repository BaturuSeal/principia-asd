import csv
import io
from copy import deepcopy

import pytest

from principia_asd.catalog.piaac import (
    COUNTRIES,
    FIELDS,
    INPUT_UNITS,
    OUTPUT_UNITS,
    block,
    bounded_lines,
    build_rows,
    decode,
    number,
    reconstruct_piaac,
)


def source(tmp_path, rows, country="USA", header=None):
    header = header or [*FIELDS, *[f"unused{i}" for i in range(2483 - len(FIELDS))]]
    p = tmp_path / (country + ".csv")
    with p.open("w", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(header)
        for i, overrides in enumerate(rows, 1):
            row = dict.fromkeys(header, ".")
            row.update(
                SEQID=str(i),
                CNTRYID=COUNTRIES[country],
                CNTRYID_E=COUNTRIES[country],
                AGEG5LFS="3",
                YRSQUALC2="12",
                EARNHRDCLC2="8",
                SPFWT0="1.5",
            )
            row.update(overrides)
            w.writerow([row[k] for k in header])
    return p


def recipe():
    return {
        "scenario_id": "P100-039",
        "input_units": INPUT_UNITS,
        "output_units": OUTPUT_UNITS,
        "assets": [{"role": c + "_respondents", "path": c + ".csv"} for c in COUNTRIES],
        "group_assignments": {
            c + ":respondentblock" + str(i): "test" if i < 2 else "dev" if i == 2 else "train"
            for c in COUNTRIES
            for i in range(10)
        },
    }


def complete_records(tmp_path):
    records = []
    for c in COUNTRIES:
        seen = {}
        for i in range(1, 500):
            seen.setdefault(block(c, str(i)), str(i))
        rows = [{"SEQID": seen[i]} for i in range(10)]
        selected, _ = decode(source(tmp_path, rows, c), c)
        records.extend(selected)
    return records


def test_native_age_ordinal_boundary_and_earnings_definition(tmp_path):
    rows, inv = decode(
        source(
            tmp_path,
            [{"AGEG5LFS": "3", "EARNHRDCLC2": "7"}, {"AGEG5LFS": "10", "EARNHRDCLC2": "8"}],
        ),
        "USA",
    )
    assert [r["age"] for r in rows] == [27, 62.5]
    assert [r["target"] for r in rows] == [0, 1]
    assert [r["source_row"] for r in rows] == [2, 3]
    assert inv["source_columns"] == 2483 and inv["eligible_records"] == 2


def test_complete_case_exclusions_are_inventoried_not_imputed(tmp_path):
    _, inv = decode(
        source(
            tmp_path,
            [
                {},
                {"AGEG5LFS": "2"},
                {"YRSQUALC2": ".r"},
                {"EARNHRDCLC2": ".v"},
                {"SPFWT0": "0"},
                {"YRSQUALC2": "31", "SPFWT0": "-1"},
            ],
        ),
        "USA",
    )
    assert inv["source_records"] == 6 and inv["excluded_records"] == 5
    assert inv["exclusion_reason_counts_nonexclusive"]["nonpositive_final_weight"] == 2
    assert inv["missing_codes"] == {"EARNHRDCLC2:.v": 1, "YRSQUALC2:.r": 1}


@pytest.mark.parametrize(
    "field,value", [("AGEG5LFS", ".A"), ("YRSQUALC2", ".D"), ("EARNHRDCLC2", ".V"), ("SPFWT0", ".")]
)
def test_documented_missing_codes(field, value):
    assert number(value, field) is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("AGEG5LFS", "2.5"),
        ("AGEG5LFS", "11"),
        ("EARNHRDCLC2", "0"),
        ("EARNHRDCLC2", "99"),
        ("YRSQUALC2", "-1"),
        ("SPFWT0", "NaN"),
        ("SPFWT0", "1e999"),
        ("SPFWT0", ".v"),
        ("YRSQUALC2", "unknown"),
    ],
)
def test_invalid_categories_and_unrecognized_missing_codes_fail(field, value):
    with pytest.raises(ValueError):
        number(value, field)


@pytest.mark.parametrize(
    "override",
    [{"SEQID": "01"}, {"SEQID": "1.0"}, {"SEQID": "."}, {"CNTRYID": "392"}, {"CNTRYID_E": "392"}],
)
def test_respondent_and_country_identity_guard(tmp_path, override):
    with pytest.raises(ValueError):
        decode(source(tmp_path, [override]), "USA")


def test_duplicate_respondent_even_in_ineligible_rows_rejected(tmp_path):
    with pytest.raises(ValueError, match="duplicate"):
        decode(source(tmp_path, [{}, {"SEQID": "1", "AGEG5LFS": "1"}]), "USA")


def test_unused_assessments_and_positive_weights_do_not_enter_predictors(tmp_path):
    a, ai = decode(source(tmp_path, [{}]), "USA")
    b, bi = decode(source(tmp_path, [{"unused1": "HIDDEN-ASSESSMENT", "SPFWT0": "20000"}]), "USA")
    assert a == b and ai["eligible_final_weight"] != bi["eligible_final_weight"]
    assert "HIDDEN" not in str(b) and not bi["plausible_values_used"]


def test_exact_custody_respondent_blocks_and_source_lineage(tmp_path):
    records = complete_records(tmp_path)
    parts, lineage, split = build_rows(recipe(), records)
    assert {p: len(rs) for p, rs in parts.items()} == {"train": 14, "dev": 2, "test": 4}
    assert split["valid"] and all("target" not in r for r in parts["test"])
    assert all(set(r) == {"sample_id", "group", "education", "age", "japan"} for r in parts["test"])
    assert all(
        "SEQID" not in str(a) and "target" not in a and "SPFWT0" not in str(a) for a in lineage
    )
    other = deepcopy(records)
    for row in other:
        if row["bucket"] < 2:
            row["target"] = 1 - row["target"]
    assert build_rows(recipe(), other) == (parts, lineage, split)


def test_same_seqid_in_two_countries_is_not_same_respondent(tmp_path):
    a = decode(source(tmp_path, [{}], "USA"), "USA")[0][0]
    b = decode(source(tmp_path, [{}], "Japan"), "Japan")[0][0]
    assert a["seqid"] == b["seqid"] and a["country"] != b["country"]


def test_hash_is_the_frozen_historical_algorithm():
    import hashlib

    for c in COUNTRIES:
        assert (
            block(c, "123")
            == int(
                hashlib.sha256(("principia100-batch7:PIAAC:" + c + ":123").encode()).hexdigest()[
                    :16
                ],
                16,
            )
            % 10
        )


@pytest.mark.parametrize("mutation", ["test", "missing", "duplicate", "hash"])
def test_complete_panel_and_confirmation_preserved(tmp_path, mutation):
    records, rec = complete_records(tmp_path), recipe()
    if mutation == "test":
        rec["group_assignments"]["USA:respondentblock0"] = "train"
    if mutation == "missing":
        records.pop()
    if mutation == "duplicate":
        records.append(records[0])
    if mutation == "hash":
        records[0]["bucket"] = (records[0]["bucket"] + 1) % 10
    with pytest.raises(ValueError):
        build_rows(rec, records)


def test_multiline_quoted_fields_rejected_for_physical_row_custody(tmp_path):
    with pytest.raises(ValueError, match="physical-line"):
        decode(source(tmp_path, [{"unused1": "line1\nline2"}]), "USA")


def test_bounded_schema_and_line_guards(tmp_path):
    with pytest.raises(ValueError, match="schema"):
        decode(source(tmp_path, [{}], header=[*FIELDS, "another"]), "USA")
    for data in [b"x" * 100001, b"a\x00b"]:
        with pytest.raises(ValueError):
            list(bounded_lines(io.BytesIO(data)))


def test_recipe_units_and_asset_roles_are_explicit(tmp_path):
    rec = recipe()
    rec["output_units"] = "USD"
    with pytest.raises(ValueError, match="units"):
        reconstruct_piaac(rec, tmp_path)
    rec["output_units"] = OUTPUT_UNITS
    with pytest.raises(ValueError, match="roles"):
        reconstruct_piaac(rec, tmp_path)
