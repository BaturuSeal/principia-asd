import csv
import gzip
import io
from copy import deepcopy

import pytest

from principia_asd.catalog.native import reconstruct
from principia_asd.catalog.storm import (
    INPUT_UNITS,
    OUTPUT_UNITS,
    REQUIRED,
    continuation_audit,
    decode_details,
    hashgroup,
    local_time,
    money,
)
from principia_asd.io import file_sha


def save(path, rows, fields=None):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=fields or [*REQUIRED, "EVENT_NARRATIVE", "TOR_F_SCALE"]
    )
    writer.writeheader()
    writer.writerows(rows)
    path.write_bytes(gzip.compress(stream.getvalue().encode(), mtime=0))


@pytest.fixture
def source(tmp_path):
    rows = []
    for i in range(15):
        r = dict.fromkeys([*REQUIRED, "EVENT_NARRATIVE", "TOR_F_SCALE"], "")
        r.update(
            EVENT_ID=str(1000 + i),
            EPISODE_ID=str(100 + i),
            EVENT_TYPE="Tornado",
            YEAR="2025",
            BEGIN_DATE_TIME="03-MAR-25 23:58:00",
            END_DATE_TIME="04-MAR-25 00:03:00",
            CZ_TIMEZONE="CST-6",
            TOR_LENGTH="1.2",
            TOR_WIDTH="100",
            BEGIN_LAT="35.0",
            DAMAGE_PROPERTY="0.00K" if i == 0 else "1.25M",
            WFO="AAA",
            CZ_FIPS="001",
            CZ_NAME="FIRST",
            STATE="TENNESSEE",
            EVENT_NARRATIVE="quoted\nmultiline source",
            TOR_F_SCALE="EF2",
        )
        rows.append(r)
    path = tmp_path / "source.csv.gz"
    save(path, rows)
    ordered = sorted([r["EPISODE_ID"] for r in rows], key=lambda s: hashgroup("tornado:" + s))
    assignments = {
        "episode:" + g: "test" if i < 3 else "dev" if i < 6 else "train"
        for i, g in enumerate(ordered)
    }
    recipe = {
        "schema_version": "native-reconstruction/1",
        "scenario_id": "P100-018",
        "parser": "noaa-storm-tornado-reports-v1",
        "input_units": INPUT_UNITS.copy(),
        "output_units": OUTPUT_UNITS,
        "group_assignments": assignments,
        "assets": [
            {
                "role": "storm_details",
                "path": path.name,
                "bytes": path.stat().st_size,
                "sha256": file_sha(path),
            }
        ],
    }
    return path, rows, recipe


def refresh(path, rows, recipe):
    save(path, rows)
    recipe["assets"][0].update(bytes=path.stat().st_size, sha256=file_sha(path))


def test_exact_units_midnight_zero_and_coordinates(source):
    path, _, recipe = source
    parts, lineage, checks = reconstruct(recipe, path.parent)
    assert sum(map(len, parts.values())) == 15
    assert len({x["group"] for rows in parts.values() for x in rows}) == 15
    row = parts["train"][0]
    assert row["duration_min"] == 5
    assert row["length_km"] == 1.2 * 1.609344
    assert row["width_km"] == 100 * 0.0009144
    assert all("target" not in row for row in parts["test"])
    assert checks["storm_validation"]["zero_loss_records_retained"] == 1
    assert lineage[1]["csv_physical_lines"][0] > lineage[1]["csv_record_index"]
    assert checks["split_check"]["valid"]


@pytest.mark.parametrize(
    "value,expected", [("0.00K", 0), ("1.25M", 1250000), ("2B", 2e9), ("5", 5), (".5K", 500)]
)
def test_explicit_currency_multipliers(value, expected):
    assert money(value) == expected


@pytest.mark.parametrize("value", ["", "unknown", "1..2M", "-2K", "NaN", "1e300B"])
def test_unknown_loss_never_zero(value):
    import math

    assert math.isnan(money(value))


def test_confirmation_response_and_excluded_fields_do_not_change_inputs(source):
    path, rows, recipe = source
    before, lineage, _ = reconstruct(recipe, path.parent)
    for r in rows:
        r["EVENT_NARRATIVE"] = "different future narrative"
        r["TOR_F_SCALE"] = "EF5"
        if recipe["group_assignments"]["episode:" + r["EPISODE_ID"]] == "test":
            r["DAMAGE_PROPERTY"] = "999B"
    refresh(path, rows, recipe)
    after, _, _ = reconstruct(recipe, path.parent)
    assert before == after
    assert all(
        "damage_property" not in str(x).lower() or x["response_column"] == "DAMAGE_PROPERTY"
        for x in lineage
    )


def test_missing_response_inventory_and_preeligibility_confirmation(source):
    path, rows, recipe = source
    # Remove an original held episode's response; do not replace it with another group.
    held = next(g for g, p in recipe["group_assignments"].items() if p == "test")
    for row in rows:
        if "episode:" + row["EPISODE_ID"] == held:
            row["DAMAGE_PROPERTY"] = ""
    del recipe["group_assignments"][held]
    refresh(path, rows, recipe)
    parts, _, checks = reconstruct(recipe, path.parent)
    assert len(parts["test"]) == 2
    assert checks["storm_validation"]["original_reserved_episodes"] == 3
    assert checks["storm_validation"]["exclusion_counts"] == {"damage:unavailable": 1}


@pytest.mark.parametrize(
    "field,value,match",
    [
        ("EVENT_ID", "1001", "duplicate"),
        ("EPISODE_ID", "", "EPISODE"),
        ("YEAR", "2024", "year"),
        ("CZ_TIMEZONE", "EDT-4", "timezone"),
        ("BEGIN_LAT", "100", "latitude"),
    ],
)
def test_identity_year_zone_domain_rejection(source, field, value, match):
    path, rows, recipe = source
    rows[0][field] = value
    refresh(path, rows, recipe)
    with pytest.raises(ValueError, match=match):
        reconstruct(recipe, path.parent)


def test_invalid_clock_and_geometry_retained_in_exclusions(source):
    path, rows, _ = source
    rows[0]["BEGIN_DATE_TIME"] = "not a timestamp"
    rows[1]["TOR_LENGTH"] = "0"
    rows[2]["TOR_WIDTH"] = "NaN"
    save(path, rows)
    parsed, _ = decode_details(path)
    assert parsed[0]["exclusion_reasons"] == ["duration:unavailable"]
    assert parsed[1]["exclusion_reasons"] == ["length:nonpositive"]
    assert parsed[2]["exclusion_reasons"] == ["width:unavailable"]


def test_continuation_uses_fixed_timezone_and_no_loss_values(source):
    path, rows, _ = source
    a, b = rows[:2]
    a.update(
        TOR_OTHER_WFO="BBB",
        TOR_OTHER_CZ_FIPS="002",
        TOR_OTHER_CZ_NAME="SECOND",
        TOR_OTHER_CZ_STATE="TN",
    )
    b.update(
        WFO="BBB",
        CZ_FIPS="2",
        CZ_NAME="SECOND",
        CZ_TIMEZONE="EST-5",
        BEGIN_DATE_TIME="04-MAR-25 01:03:00",
        END_DATE_TIME="04-MAR-25 01:05:00",
    )
    save(path, rows)
    parsed, _ = decode_details(path)
    result = continuation_audit(parsed, {"episode:100": "train", "episode:101": "test"})
    assert result["cross_partition_eligible_candidates"] == 1
    assert result["candidate_links"][0]["identity_status"] == "candidate_not_adjudicated"
    parsed[0]["dollars"] *= 100
    assert result == continuation_audit(parsed, {"episode:100": "train", "episode:101": "test"})


def test_ambiguous_continuation_not_silently_unique(source):
    path, rows, _ = source
    rows[0].update(
        TOR_OTHER_WFO="AAA",
        TOR_OTHER_CZ_FIPS="001",
        TOR_OTHER_CZ_NAME="FIRST",
        TOR_OTHER_CZ_STATE="TN",
        END_DATE_TIME="03-MAR-25 23:58:00",
    )
    save(path, rows)
    parsed, _ = decode_details(path)
    audit = continuation_audit(parsed, {})
    assert audit["unresolved_continuations"][0]["candidate_count"] == 14


def test_resource_bounds_duplicate_header_and_truncated_gzip(source):
    path, rows, _ = source
    with pytest.raises(ValueError, match="Oversized"):
        decode_details(path, max_bytes=50)
    with pytest.raises(ValueError, match="Excessive"):
        decode_details(path, max_rows=2)
    save(path, rows, [*REQUIRED, "EVENT_NARRATIVE", "TOR_F_SCALE", "EVENT_ID"])
    with pytest.raises(ValueError, match="duplicate"):
        decode_details(path)
    path.write_bytes(path.read_bytes()[:-5])
    with pytest.raises(EOFError):
        decode_details(path)


def test_frozen_confirmation_units_and_source_mutation(source):
    path, rows, recipe = source
    bad = deepcopy(recipe)
    first = next(g for g, p in bad["group_assignments"].items() if p == "test")
    bad["group_assignments"][first] = "dev"
    with pytest.raises(ValueError, match="confirmation"):
        reconstruct(bad, path.parent)
    bad = deepcopy(recipe)
    bad["input_units"]["length_km"] = "miles"
    with pytest.raises(ValueError, match="unit"):
        reconstruct(bad, path.parent)
    rows[0]["TOR_LENGTH"] = "20"
    save(path, rows)
    with pytest.raises(ValueError, match="hash or size"):
        reconstruct(recipe, path.parent)


def test_locale_independent_calendar_rejection():
    assert local_time("04-MAR-25 01:00:00").month == 3
    with pytest.raises(ValueError):
        local_time("31-FEB-25 01:00:00")
