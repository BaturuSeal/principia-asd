import io
import zipfile
from copy import deepcopy
from datetime import date

import pytest

from principia_asd.catalog.nhtsa import (
    INPUT_UNITS,
    MEMBER,
    MONTHS,
    aggregate,
    bounded_lines,
    build_rows,
    decode_archive,
    parsed_date,
    reconstruct_nhtsa,
    selected,
    source_layout,
)


def fields(oid, received="20250101", narrative="ordinary", product="V", vehicle=("MAKE", "MODEL")):
    f = [""] * 51
    for k, v in {
        0: str(oid),
        1: str(oid),
        3: vehicle[0],
        4: vehicle[1],
        5: "2020",
        15: received,
        16: received,
        19: narrative,
        45: product,
    }.items():
        f[k] = v
    return f


def archive(tmp_path, rows, member=MEMBER):
    p = tmp_path / "complaints.zip"
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(member, "".join("\t".join(r) + "\r\n" for r in rows).encode("latin1"))
    return p


def source_rows():
    rows = []
    for j, m in enumerate(MONTHS):
        for n in range(1 if j else 6):
            f = fields(100 * j + n + 1, m.replace("-", "") + "01")
            rows.append(selected(f, len(rows) + 1, len(rows) + 1, len(rows) + 1))
    return rows


def recipe():
    return {
        "scenario_id": "P100-019",
        "assets": [{"role": "complaints_archive", "path": "raw/complaints.zip"}],
        "input_units": INPUT_UNITS,
        "output_units": "complaints/month",
        "group_assignments": {
            m: "train" if m < "2026-03" else "dev" if m < "2026-05" else "test" for m in MONTHS[6:]
        },
    }


def test_literal_record_boundary_detects_historical_merged_complaints(tmp_path):
    p = archive(tmp_path, [fields(1, narrative='"start'), fields(2, narrative='end"'), fields(3)])
    legacy, physical, inv = decode_archive(p)
    assert len(legacy) == 2 and len(physical) == 3
    assert inv["absorbed_physical_records"] == 1
    assert inv["merged_record_spans"] == [
        {
            "legacy_record": 1,
            "first_physical_line": 1,
            "last_physical_line": 2,
            "selected_fields_match_first_line": True,
        }
    ]
    assert aggregate(legacy)[3]["unique_vehicle_complaints"] == 2
    assert aggregate(physical)[3]["unique_vehicle_complaints"] == 3
    assert legacy[1]["native_row"] == 2 and legacy[1]["first_line"] == 3
    assert not any("narrative" in r or "VIN" in r for r in legacy + physical)


def test_balanced_quotes_and_unused_sensitive_fields_do_not_enter_measurements(tmp_path):
    f = fields(1, narrative='"balanced words"')
    f[14] = "PRIVATE-VIN"
    f[41] = "PRIVATE-PHONE"
    f[50] = "PRIVATE-NAME"
    legacy, physical, inv = decode_archive(archive(tmp_path, [f]))
    assert legacy == physical and not inv["merged_record_spans"]
    assert "PRIVATE" not in str(legacy)
    f[19] = "a different story"
    f[14] = "OTHER-VIN"
    f[50] = "OTHER-NAME"
    assert decode_archive(archive(tmp_path, [f]))[0] == legacy


def test_global_component_dedup_first_record_and_conflicting_dates():
    rows = source_rows()
    duplicate = deepcopy(rows[0])
    duplicate["native_row"] = 999
    duplicate["received"] = date(2026, 7, 1)
    counts, cells, cohort, diag = aggregate(rows + [duplicate])
    assert (
        diag["duplicate_components_removed"] == 1 and diag["duplicate_received_date_conflicts"] == 1
    )
    assert counts[("MAKE|MODEL", "2025-01")] == 6 and counts[("MAKE|MODEL", "2026-07")] == 1
    assert cohort == ["MAKE|MODEL"] and cells[("MAKE|MODEL", "2025-01")][0]["native_row"] == 1


def test_model_year_and_component_not_distinct_count_units():
    f = fields(1)
    g = fields(1)
    g[5] = "2021"
    g[11] = "ANOTHER COMPONENT"
    rows = [selected(a, i, i, i) for i, a in enumerate([f, g], 1)]
    assert aggregate(rows)[3]["unique_vehicle_complaints"] == 1
    g[4] = "OTHER MODEL"
    rows[1] = selected(g, 2, 2, 2)
    assert aggregate(rows)[3]["unique_vehicle_complaints"] == 2


def test_fixed_pre_july_cohort_does_not_include_future_only_vehicle():
    rows = source_rows()
    for n in range(10):
        rows.append(
            selected(
                fields(9000 + n, "20260701", vehicle=("FUTURE", "ONLY")),
                9000 + n,
                9000 + n,
                9000 + n,
            )
        )
    assert aggregate(rows)[2] == ["MAKE|MODEL"]


def test_exact_monthly_lags_custody_and_complete_month_splits():
    counts, cells, cohort, _ = aggregate(source_rows())
    parts, lineage, split, history = build_rows(recipe(), counts, cells, cohort)
    assert {p: len(rs) for p, rs in parts.items()} == {"train": 8, "dev": 2, "test": 3}
    assert split["valid"] and all("target" not in r for r in parts["test"])
    assert (
        parts["train"][0]["lag1"] == 1
        and parts["train"][0]["lag3"] == 1
        and parts["train"][0]["lag6"] == pytest.approx(11 / 6)
    )
    assert all(max(a["prior_months"]) < a["target_month"] for a in lineage)
    assert history["datea_not_before_prediction_origin_references"] == 0
    assert len(history["input_source_coordinate_hashes"]) == 18
    assert all(len(s) == 64 for s in history["input_source_coordinate_hashes"].values())


def test_terminal_response_never_changes_predictors_but_observed_history_does():
    counts, cells, cohort, _ = aggregate(source_rows())
    before, anchors, _, _ = build_rows(recipe(), counts, cells, cohort)
    changed = counts.copy()
    changed[("MAKE|MODEL", "2026-07")] += 4
    after, other, _, _ = build_rows(recipe(), changed, cells, cohort)
    assert before == after and anchors == other
    changed[("MAKE|MODEL", "2026-05")] += 3
    after, _, _, _ = build_rows(recipe(), changed, cells, cohort)
    assert before["train"] == after["train"] and before["dev"] == after["dev"]
    assert before["test"][0] == after["test"][0]
    assert after["test"][1]["lag1"] == 4 and after["test"][2]["lag3"] == 2


def test_zero_complaint_months_not_dropped():
    rows = [r for r in source_rows() if r["received"] != date(2025, 8, 1)]
    counts, cells, cohort, _ = aggregate(rows)
    parts, _, _, _ = build_rows(recipe(), counts, cells, cohort)
    assert len(parts["train"]) == 8 and parts["train"][1]["target"] == 0
    assert parts["train"][2]["lag1"] == 0


def test_added_date_not_assumed_available_and_invalid_dates_accounted():
    rows = source_rows()
    rows[0]["added"] = date(2026, 1, 1)
    rows[1]["added"] = None
    counts, cells, cohort, diag = aggregate(rows)
    _, _, _, h = build_rows(recipe(), counts, cells, cohort)
    assert diag["missing_added_date"] == 1 and diag["datea_minus_ldate_days"]["positive"] == 1
    assert (
        h["datea_not_before_prediction_origin_references"] == 1
        and h["unknown_datea_input_references"] == 1
    )
    rows[2]["received"] = None
    assert aggregate(rows)[3]["exclusion_reason_counts"]["invalid_received_date"] == 1


@pytest.mark.parametrize("value", ["20250230", "not-date", "2025111", ""])
def test_missing_or_malformed_source_dates(value):
    assert parsed_date(value) is None


@pytest.mark.parametrize("kind", ["test", "dev", "unknown"])
def test_frozen_month_policy_cannot_change(kind):
    counts, cells, cohort, _ = aggregate(source_rows())
    r = recipe()
    if kind == "test":
        r["group_assignments"]["2026-05"] = "dev"
    elif kind == "dev":
        r["group_assignments"]["2026-03"] = "train"
    else:
        r["group_assignments"]["2026-08"] = "test"
    with pytest.raises(ValueError, match="allocation|assignments"):
        build_rows(r, counts, cells, cohort)


@pytest.mark.parametrize("kind", ["field_count", "id", "product", "vehicle"])
def test_selected_column_schema_and_identity_rejected(kind):
    f = fields(1)
    if kind == "field_count":
        f.pop()
    elif kind == "id":
        f[1] = "bad-id"
    elif kind == "product":
        f[45] = "UNKNOWN"
    else:
        f[3] = "AMBIGUOUS|MAKE"
    with pytest.raises(ValueError):
        selected(f, 1, 1, 1)


def test_out_of_registered_year_and_units_rejected():
    rows = source_rows()
    rows[0]["received"] = date(2024, 12, 1)
    with pytest.raises(ValueError, match="outside registered"):
        aggregate(rows)
    r = recipe()
    r["input_units"] = {}
    with pytest.raises(ValueError, match="units"):
        reconstruct_nhtsa(r, None)


@pytest.mark.parametrize("raw", [b"x" * 10001, b"null\x00record\n"])
def test_bounded_text_rejects_oversized_or_nul(raw):
    with pytest.raises(ValueError, match="Oversized or invalid"):
        list(bounded_lines(io.BytesIO(raw)))


@pytest.mark.parametrize("name", ["../escape.txt", "other.txt"])
def test_archive_path_and_member_inventory(tmp_path, name):
    with pytest.raises(ValueError, match="Unsafe|Unexpected"):
        decode_archive(archive(tmp_path, [fields(1)], member=name))


def test_duplicate_archive_member_rejected(tmp_path):
    p = archive(tmp_path, [fields(1)])
    with zipfile.ZipFile(p, "a") as z:
        with pytest.warns(UserWarning):
            z.writestr(MEMBER, "")
    with pytest.raises(ValueError, match="Duplicate|oversized"):
        decode_archive(p)


def test_source_layout_meaning_and_revision_guard(tmp_path):
    p = tmp_path / "layout.txt"
    p.write_text(
        "All the records are TAB delimited\nAll dates are in YYYYMMDD format\nDATE ADDED TO FILE\nDATE COMPLAINT RECEIVED BY NHTSA\nVEHICLE_OPERATOR\nLast updated: April 30, 2026"
    )
    assert source_layout(p)["layout_revision"] == "2026-04-30"
    p.write_text(p.read_text().replace("DATE COMPLAINT RECEIVED", "DATE INCIDENT OCCURRED"))
    with pytest.raises(ValueError, match="Changed"):
        source_layout(p)


def test_empty_source_cannot_masquerade_as_zero_counts(tmp_path):
    with pytest.raises(ValueError, match="Empty"):
        decode_archive(archive(tmp_path, []))
