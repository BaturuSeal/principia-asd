"""Curator-only NOAA tornado-report reconstruction; no meteorological forecast.

Damage is a reported estimate. Continuation fields audit dependence only and are
never prediction inputs. Source responses remain outside exported test tables.
"""

import csv
import gzip
import hashlib
import io
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta

import numpy as np

from ..io import contained, sha
from .splits import check_units

INPUT_UNITS = {
    "duration_min": "minutes event duration",
    "latitude": "degrees north",
    "length_km": "km path length",
    "month": "calendar1–12",
    "width_km": "km maximum path width",
}
OUTPUT_UNITS = "ln(1+property damage in USD)"
REQUIRED = (
    "EVENT_ID EPISODE_ID EVENT_TYPE YEAR BEGIN_DATE_TIME END_DATE_TIME CZ_TIMEZONE "
    "TOR_LENGTH TOR_WIDTH BEGIN_LAT DAMAGE_PROPERTY WFO CZ_FIPS CZ_NAME STATE "
    "TOR_OTHER_WFO TOR_OTHER_CZ_STATE TOR_OTHER_CZ_FIPS TOR_OTHER_CZ_NAME"
).split()
MONTHS = {m: i + 1 for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split())}
ZONES = {"EST-5": -5, "CST-6": -6, "MST-7": -7, "PST-8": -8}


def local_time(value):
    """Explicit English source format; independent of process locale/timezone."""
    match = re.fullmatch(r"(\d{2})-([A-Z]{3})-(\d{2}) (\d{2}):(\d{2}):(\d{2})", value)
    if not match or match[2] not in MONTHS:
        raise ValueError("Unsupported storm timestamp")
    day, month, year, hour, minute, second = match.groups()
    return datetime(2000 + int(year), MONTHS[month], int(day), int(hour), int(minute), int(second))


def money(value):
    # Unknown/malformed losses are unavailable, never converted to zero.
    match = re.fullmatch(r"(\d+(?:\.\d*)?|\.\d+)([KMB]?)", value.strip().upper())
    if not match:
        return math.nan
    result = float(match[1]) * {"": 1, "K": 1e3, "M": 1e6, "B": 1e9}[match[2]]
    return result if math.isfinite(result) else math.nan


def number(value):
    try:
        result = float(value)
    except ValueError:
        return math.nan
    return result if math.isfinite(result) else math.nan


def decode_details(path, *, max_bytes=80_000_000, max_rows=100_000):
    """Bound expansion before decoding; CSV record coordinates survive quoted newlines."""
    with gzip.open(path, "rb") as stream:
        raw = stream.read(max_bytes + 1)
    if len(raw) > max_bytes or b"\x00" in raw:
        raise ValueError("Oversized or NUL-containing storm CSV")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8"), newline=""), strict=True)
    fields = reader.fieldnames
    if not fields or len(fields) != len(set(fields)) or not set(REQUIRED) <= set(fields):
        raise ValueError("Missing or duplicate storm source fields")
    seen, rows, total, prior_line = set(), [], 0, reader.line_num
    for record_index, record in enumerate(reader, 2):
        total += 1
        if total > max_rows or None in record or any(v is None for v in record.values()):
            raise ValueError("Excessive or malformed storm record")
        event = record["EVENT_ID"]
        if not re.fullmatch(r"[1-9]\d*", event) or event in seen:
            raise ValueError("Invalid or duplicate source EVENT_ID")
        seen.add(event)
        begin_line, end_line = prior_line + 1, reader.line_num
        prior_line = end_line
        if record["EVENT_TYPE"] != "Tornado":
            continue
        if not re.fullmatch(r"[1-9]\d*", record["EPISODE_ID"]):
            raise ValueError("Invalid tornado EPISODE_ID")
        if record["YEAR"] != "2025" or record["CZ_TIMEZONE"] not in ZONES:
            raise ValueError("Unregistered tornado source year or timezone")
        try:
            start, end = local_time(record["BEGIN_DATE_TIME"]), local_time(record["END_DATE_TIME"])
        except ValueError:
            start = end = None
        length, width, lat = [number(record[k]) for k in ("TOR_LENGTH", "TOR_WIDTH", "BEGIN_LAT")]
        dollars = money(record["DAMAGE_PROPERTY"])
        duration = (end - start).total_seconds() / 60 if start is not None else math.nan
        reasons = []
        for key, value in {
            "damage": dollars,
            "length": length,
            "width": width,
            "duration": duration,
            "latitude": lat,
        }.items():
            if not math.isfinite(value):
                reasons.append(key + ":unavailable")
        for key, value in (("length", length), ("width", width)):
            if math.isfinite(value) and value <= 0:
                reasons.append(key + ":nonpositive")
        if math.isfinite(duration) and duration < 0:
            reasons.append("duration:negative")
        if math.isfinite(lat) and not -90 <= lat <= 90:
            raise ValueError("Storm latitude outside physical domain")
        if start is not None and (start.year != 2025 or end.year not in {2025, 2026}):
            raise ValueError("Storm timestamp/source year mismatch")
        rows.append(
            {
                "record": {k: record[k] for k in REQUIRED},
                "record_index": record_index,
                "csv_lines": [begin_line, end_line],
                "start": start,
                "end": end,
                "dollars": dollars,
                "values": {
                    "length_km": length * 1.609344,
                    "width_km": width * 0.0009144,
                    "duration_min": duration,
                    "latitude": lat,
                    "month": float(start.month) if start is not None else math.nan,
                },
                "exclusion_reasons": reasons,
            }
        )
    if not rows:
        raise ValueError("No tornado source records")
    return rows, {"source_records": total, "expanded_csv_bytes": len(raw), "source_fields": fields}


def hashgroup(value):
    return int(hashlib.sha256(("principia100-batch7:" + value).encode()).hexdigest()[:16], 16)


def continuation_audit(rows, assignments):
    """Conservative candidate links, not invented global tornado identities.

    Match subsequent office/county/name and an exact local-standard-time boundary
    converted using the stored fixed offset. State abbreviation is retained but
    not silently equated with the source's full state name. No response matching.
    """
    starts, links, unresolved = defaultdict(list), [], []
    for row in rows:
        r = row["record"]
        if row["start"] is not None:
            key = (
                r["WFO"],
                r["CZ_FIPS"].lstrip("0"),
                r["CZ_NAME"],
                row["start"] - timedelta(hours=ZONES[r["CZ_TIMEZONE"]]),
            )
            starts[key].append(row)
    for row in rows:
        r = row["record"]
        if not any(
            r[k]
            for k in (
                "TOR_OTHER_WFO",
                "TOR_OTHER_CZ_STATE",
                "TOR_OTHER_CZ_FIPS",
                "TOR_OTHER_CZ_NAME",
            )
        ):
            continue
        end = row["end"] - timedelta(hours=ZONES[r["CZ_TIMEZONE"]]) if row["end"] else None
        key = (r["TOR_OTHER_WFO"], r["TOR_OTHER_CZ_FIPS"].lstrip("0"), r["TOR_OTHER_CZ_NAME"], end)
        peers = [p for p in starts.get(key, []) if p["record"]["EVENT_ID"] != r["EVENT_ID"]]
        if len(peers) != 1:
            unresolved.append({"event_id": r["EVENT_ID"], "candidate_count": len(peers)})
        for peer in peers:
            q = peer["record"]
            split_a = assignments.get("episode:" + r["EPISODE_ID"])
            split_b = assignments.get("episode:" + q["EPISODE_ID"])
            links.append(
                {
                    "event_id": r["EVENT_ID"],
                    "candidate_event_id": q["EVENT_ID"],
                    "episodes": [r["EPISODE_ID"], q["EPISODE_ID"]],
                    "partitions": [split_a, split_b],
                    "both_eligible": not row["exclusion_reasons"] and not peer["exclusion_reasons"],
                    "cross_partition": split_a is not None
                    and split_b is not None
                    and split_a != split_b,
                    "subsequent_state_abbreviation": r["TOR_OTHER_CZ_STATE"],
                    "candidate_state_name": q["STATE"],
                    "identity_status": "candidate_not_adjudicated",
                }
            )
    return {
        "candidate_links": links,
        "unresolved_continuations": unresolved,
        "cross_partition_eligible_candidates": sum(
            x["cross_partition"] and x["both_eligible"] for x in links
        ),
        "scope": "Office/county/name and exact timezone-adjusted boundary candidates; state/name/track adjudication remains required; no inferred independence",
    }


def reconstruct_storm(recipe, source_root):
    from .native import _registered_groups, _row, identity

    if recipe["input_units"] != INPUT_UNITS or recipe["output_units"] != OUTPUT_UNITS:
        raise ValueError("Storm recipe unit mismatch")
    (asset,) = [a for a in recipe["assets"] if a["role"] == "storm_details"]
    rows, summary = decode_details(contained(source_root, asset["path"]))
    eligible = [r for r in rows if not r["exclusion_reasons"]]
    groups = {"episode:" + r["record"]["EPISODE_ID"] for r in eligible}
    assignments = _registered_groups(recipe, groups)
    # Original held episodes were selected BEFORE eligibility; preserve that order.
    all_groups = sorted(
        {r["record"]["EPISODE_ID"] for r in rows}, key=lambda s: hashgroup("tornado:" + s)
    )
    held = {"episode:" + g for g in all_groups[: max(1, len(all_groups) // 5)]}
    if {g for g, split in assignments.items() if split == "test"} != held & groups:
        raise ValueError("Original storm confirmation episode allocation changed")
    parts, lineage = {p: [] for p in ("train", "dev", "test")}, []
    case = recipe["scenario_id"]
    for item in eligible:
        r = item["record"]
        group = "episode:" + r["EPISODE_ID"]
        split = assignments[group]
        result, origin = _row(
            case,
            r["EVENT_ID"],
            group,
            split,
            item["values"],
            float(np.log1p(item["dollars"])),
            {
                "source": asset["path"],
                "csv_record_index": item["record_index"],
                "csv_physical_lines": item["csv_lines"],
                "event_id": r["EVENT_ID"],
                "episode_id": r["EPISODE_ID"],
                "input_columns": [
                    "TOR_LENGTH",
                    "TOR_WIDTH",
                    "BEGIN_DATE_TIME",
                    "END_DATE_TIME",
                    "BEGIN_LAT",
                ],
                "response_column": "DAMAGE_PROPERTY",
                "local_standard_timezone": r["CZ_TIMEZONE"],
                "operations": {
                    "length_km": "TOR_LENGTH * 1.609344",
                    "width_km": "TOR_WIDTH * 0.0009144",
                    "duration_min": "local END minus BEGIN in minutes",
                    "month": "BEGIN calendar month",
                    "target": "log1p(parsed reported USD); train/dev only",
                },
            },
        )
        parts[split].append(result)
        lineage.append(origin)
    exclusions = [
        {
            "event_id": r["record"]["EVENT_ID"],
            "record_index": r["record_index"],
            "reasons": r["exclusion_reasons"],
        }
        for r in rows
        if r["exclusion_reasons"]
    ]
    links = continuation_audit(rows, assignments)
    summary.update(
        {
            "tornado_records": len(rows),
            "eligible_records": len(eligible),
            "source_episodes_before_eligibility": len(all_groups),
            "original_reserved_episodes": len(held),
            "eligible_episodes": len(groups),
            "partitions": dict(Counter(assignments.values())),
            "zero_loss_records_retained": sum(r["dollars"] == 0 for r in eligible),
            "exclusion_counts": dict(
                Counter(reason for r in exclusions for reason in r["reasons"])
            ),
            "exclusions": exclusions,
            "eligibility_inventory_sha256": sha(exclusions),
            "continuation_audit": links,
            "fit_count": 0,
            "learned_transformations": [],
            "source_observation_year": 2025,
            "source_snapshot_date": "2026-08-19",
            "source_timezone_counts": dict(Counter(r["record"]["CZ_TIMEZONE"] for r in rows)),
            "independence_scope": "Whole recorded episodes, not confirmed independent tornadoes/outbreaks; shared region/year/reporting process",
            "response_scope": "Retrospective post-event diagnosis of reported loss; not forecast or true insured/economic loss",
        }
    )
    return (
        parts,
        lineage,
        {
            "split_check": check_units(parts, {identity(case, "group", g): g for g in groups}),
            "storm_validation": summary,
            "admission_blockers": [
                "Continuation candidates and broader outbreak dependence require scientific adjudication",
                "Unknown loss exclusions and recorded zeros do not establish complete economic losses",
                "Source rights/notice packaging and retrospective scientific admission remain pending",
            ],
        },
    )
