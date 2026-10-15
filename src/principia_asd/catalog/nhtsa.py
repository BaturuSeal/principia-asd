"""Curator-only NHTSA complaint reconstruction and literal-TSV record audit.

Preserves the historical quote-aware decode for parity, while independently
checking every physical 51-field record. A detected merge blocks admission.
Narratives, VINs, names and contact fields are never retained or exported.
"""

import csv
import hashlib
import re
from collections import Counter, defaultdict
from datetime import date

import numpy as np

from ..io import contained, sha
from .fracture import bounded_zip
from .splits import check_units

PARSER = "nhtsa-historical-counts-record-audit-v1"
MEMBER = "COMPLAINTS_RECEIVED_2025-2026.txt"
INPUT_UNITS = {
    "lag1": "prior calendar month unique ODINO count",
    "lag3": "mean prior3monthly counts",
    "lag6": "mean prior6monthly counts",
    "month": "target calendar month1–12",
}
MONTHS = [
    f"{year:04d}-{month:02d}"
    for year in [2025, 2026]
    for month in range(1, 13)
    if (year, month) <= (2026, 7)
]
MAX_BYTES = 180_000_000
MAX_ROWS = 200_000


def parsed_date(value):
    if not re.fullmatch(r"\d{8}", value):
        return None
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:]))
    except ValueError:
        return None


def selected(fields, native_row, first_line, last_line):
    if len(fields) != 51:
        raise ValueError("NHTSA source requires 51 tab-delimited fields")
    if (
        not re.fullmatch(r"\d{1,9}", fields[0])
        or not re.fullmatch(r"\d{1,9}", fields[1])
        or fields[45] not in {"V", "T", "C", "E"}
    ):
        raise ValueError("Invalid NHTSA record identity or product type")
    make, model = fields[3], fields[4]
    if any("|" in v or "\n" in v or "\r" in v for v in [make, model]):
        raise ValueError("Ambiguous NHTSA vehicle identity")
    return {
        "native_row": native_row,
        "first_line": first_line,
        "last_line": last_line,
        "cmplid": fields[0],
        "odino": fields[1],
        "vehicle": make.strip() + "|" + model.strip(),
        "nonempty_vehicle": bool(make and model),
        "received": parsed_date(fields[16]),
        "added": parsed_date(fields[15]),
        "product": fields[45],
    }


def bounded_lines(stream):
    total, count = 0, 0
    while raw := stream.readline(10_001):
        total += len(raw)
        count += 1
        if len(raw) > 10_000 or total > MAX_BYTES or count > MAX_ROWS or b"\x00" in raw:
            raise ValueError("Oversized or invalid NHTSA text record")
        yield raw.decode("latin1")


def decode_archive(path):
    """Compare historical quote semantics with the publisher's literal TSV layout."""
    physical, legacy, spans = [], [], []
    with bounded_zip(path, max_bytes=MAX_BYTES, max_member_bytes=MAX_BYTES, max_members=1) as z:
        if z.namelist() != [MEMBER]:
            raise ValueError("Unexpected NHTSA archive member")
        info = z.getinfo(MEMBER)
        if info.compress_type not in {0, 8}:
            raise ValueError("Unsupported NHTSA archive compression")
        with z.open(MEMBER) as stream:
            for line_no, line in enumerate(bounded_lines(stream), 1):
                fields = line.rstrip("\r\n").split("\t")
                physical.append(selected(fields, line_no, line_no, line_no))
        with z.open(MEMBER) as stream:
            # Historical pandas default quote behavior is intentionally retained
            # here only for exact reproduction. Literal parsing is audited above.
            reader = csv.reader(bounded_lines(stream), delimiter="\t", strict=False)
            prior = 0
            for row_no, fields in enumerate(reader, 1):
                if sum(map(len, fields)) > 100_000:
                    raise ValueError("Oversized historical NHTSA logical record")
                row = selected(fields, row_no, prior + 1, reader.line_num)
                legacy.append(row)
                if reader.line_num > prior + 1:
                    base = physical[prior]
                    spans.append(
                        {
                            "legacy_record": row_no,
                            "first_physical_line": prior + 1,
                            "last_physical_line": reader.line_num,
                            "selected_fields_match_first_line": all(
                                row[k] == base[k]
                                for k in [
                                    "cmplid",
                                    "odino",
                                    "vehicle",
                                    "received",
                                    "added",
                                    "product",
                                ]
                            ),
                        }
                    )
                prior = reader.line_num
        if not physical or not legacy:
            raise ValueError("Empty NHTSA source")
        inventory = {
            "member": MEMBER,
            "expanded_bytes": info.file_size,
            "physical_records": len(physical),
            "historical_logical_records": len(legacy),
            "merged_record_spans": spans,
            "absorbed_physical_records": len(physical) - len(legacy),
            "physical_field_count": 51,
            "encoding": "latin1",
            "product_counts": dict(Counter(r["product"] for r in physical)),
        }
    return legacy, physical, inventory


def aggregate(rows):
    """Deduplicate ODINO per make/model, retaining the first native source record."""
    unique, exclusions, conflicts, duplicates = {}, Counter(), 0, 0
    for row in rows:
        reasons = []
        if row["product"] != "V":
            reasons.append("non_vehicle_product")
        if not row["nonempty_vehicle"]:
            reasons.append("missing_make_or_model")
        if row["received"] is None:
            reasons.append("invalid_received_date")
        exclusions.update(reasons)
        if reasons:
            continue
        if not date(2025, 1, 1) <= row["received"] < date(2027, 1, 1):
            raise ValueError("NHTSA date outside registered received-date archive")
        key = (row["odino"], row["vehicle"])
        if key in unique:
            duplicates += 1
            conflicts += row["received"] != unique[key]["received"]
        else:
            unique[key] = row
    counts, cells, early, lag_days = Counter(), defaultdict(list), Counter(), []
    for row in unique.values():
        month = row["received"].isoformat()[:7]
        key = (row["vehicle"], month)
        counts[key] += 1
        cells[key].append(row)
        if row["received"] < date(2025, 7, 1):
            early[row["vehicle"]] += 1
        if row["added"] is not None:
            lag_days.append((row["added"] - row["received"]).days)
    cohort = sorted(vehicle for vehicle, count in early.items() if count >= 6)
    diagnostics = {
        "unique_vehicle_complaints": len(unique),
        "duplicate_components_removed": duplicates,
        "duplicate_received_date_conflicts": conflicts,
        "exclusion_reason_counts": dict(exclusions),
        "cohort_vehicles": len(cohort),
        "missing_added_date": len(unique) - len(lag_days),
        "datea_minus_ldate_days": {
            "min": min(lag_days) if lag_days else None,
            "max": max(lag_days) if lag_days else None,
            "negative": sum(t < 0 for t in lag_days),
            "positive": sum(t > 0 for t in lag_days),
            "zero": sum(t == 0 for t in lag_days),
        },
    }
    return counts, cells, cohort, diagnostics


def build_rows(recipe, counts, cells, cohort):
    from .native import _registered_groups, _row, identity

    groups = MONTHS[6:]
    assignments = _registered_groups(recipe, groups)
    expected = {m: "train" if m < "2026-03" else "dev" if m < "2026-05" else "test" for m in groups}
    if assignments != expected:
        raise ValueError("NHTSA complete chronological month allocation changed")
    if not cohort or len(cohort) != len(set(cohort)):
        raise ValueError("Invalid NHTSA fixed vehicle cohort")
    source = next(a["path"] for a in recipe["assets"] if a["role"] == "complaints_archive")
    parts, lineage, unavailable, unknown, input_cells = (
        {p: [] for p in ["train", "dev", "test"]},
        [],
        0,
        0,
        {},
    )
    for vehicle in sorted(cohort):
        series = np.array([counts[(vehicle, m)] for m in MONTHS], float)
        for j in range(6, len(MONTHS)):
            month, past = MONTHS[j], series[j - 6 : j]
            start = date.fromisoformat(month + "-01")
            for m in MONTHS[j - 6 : j]:
                records = cells.get((vehicle, m), [])
                unavailable += sum(r["added"] is not None and r["added"] >= start for r in records)
                unknown += sum(r["added"] is None for r in records)
                # Hash source record coordinates; never publish individual IDs,
                # narratives or a list whose length reveals a future target count.
                cell = identity(recipe["scenario_id"], "cell", vehicle + ":" + m)
                input_cells[cell] = sha(
                    [[r["native_row"], r["first_line"], r["last_line"]] for r in records]
                )
            values = {
                "lag1": float(past[-1]),
                "lag3": float(past[-3:].mean()),
                "lag6": float(past.mean()),
                "month": float(int(month[-2:])),
            }
            row, anchor = _row(
                recipe["scenario_id"],
                vehicle + ":" + month,
                month,
                assignments[month],
                values,
                series[j],
                {
                    "source": source,
                    "member": MEMBER,
                    "vehicle": vehicle,
                    "target_month": month,
                    "prior_months": MONTHS[j - 6 : j],
                    "source_query": PARSER,
                    "input_cell_ids": [
                        identity(recipe["scenario_id"], "cell", vehicle + ":" + m)
                        for m in MONTHS[j - 6 : j]
                    ],
                },
            )
            parts[assignments[month]].append(row)
            lineage.append(anchor)
    checks = {
        "input_source_coordinate_hashes": input_cells,
        "datea_not_before_prediction_origin_references": unavailable,
        "unknown_datea_input_references": unknown,
        "prior_calendar_months_only": True,
        "online_test_history": "May counts enter June/July inputs; June counts enter July inputs; not a simultaneous three-month forecast",
    }
    return (
        parts,
        lineage,
        check_units(parts, {identity(recipe["scenario_id"], "group", g): g for g in groups}),
        checks,
    )


def source_layout(path):
    raw = path.read_bytes()
    if len(raw) > 20_000:
        raise ValueError("Oversized NHTSA layout")
    text = raw.decode("latin1")
    for marker in [
        "All the records are TAB delimited",
        "All dates are in YYYYMMDD format",
        "DATE ADDED TO FILE",
        "DATE COMPLAINT RECEIVED BY NHTSA",
        "VEHICLE_OPERATOR",
        "Last updated: April 30, 2026",
    ]:
        if marker not in text:
            raise ValueError("Changed NHTSA source layout")
    return {
        "layout_revision": "2026-04-30",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "format": "51 literal tab-delimited fields per physical record",
    }


def reconstruct_nhtsa(recipe, source_root):
    if recipe["input_units"] != INPUT_UNITS or recipe["output_units"] != "complaints/month":
        raise ValueError("NHTSA recipe units differ")
    assets = {a["role"]: a for a in recipe["assets"]}
    if len(assets) != len(recipe["assets"]) or set(assets) != {
        "complaints_archive",
        "complaints_layout",
    }:
        raise ValueError("Invalid NHTSA required asset inventory")
    layout = source_layout(contained(source_root, assets["complaints_layout"]["path"]))
    legacy, physical, inventory = decode_archive(
        contained(source_root, assets["complaints_archive"]["path"])
    )
    counts, cells, cohort, diagnostics = aggregate(legacy)
    literal_counts, _, literal_cohort, literal_diag = aggregate(physical)
    parts, lineage, split, history = build_rows(recipe, counts, cells, cohort)
    different = {k for k in set(counts) | set(literal_counts) if counts[k] != literal_counts[k]}
    validation = {
        "native_inventory": inventory,
        "source_layout": layout,
        "historical_aggregation": diagnostics,
        "literal_record_aggregation": literal_diag,
        "literal_record_equivalence": {
            "valid": not inventory["merged_record_spans"] and not different,
            "same_cohort": cohort == literal_cohort,
            "changed_vehicle_month_cells": len(different),
            "changed_fixed_cohort_cells_in_scored_months": sum(
                v in cohort and m in MONTHS[6:] for v, m in different
            ),
            "missing_unique_vehicle_complaints": literal_diag["unique_vehicle_complaints"]
            - diagnostics["unique_vehicle_complaints"],
        },
        **history,
        "local_preprocessing_fits": 0,
        "discovery_rule_fits": 0,
        "response_scope": "Unique received complaint counts, not incidence, defect probability, injuries or fleet risk",
        "availability_scope": "DATEA equals receipt date in this frozen selection but does not prove as-issued publication, daily completeness or immutable product labels",
        "excluded_fields": [
            "VIN",
            "consumer/dealer contact",
            "narrative",
            "operator name",
            "FAILDATE",
            "injuries",
            "deaths",
            "recalls",
            "investigations",
            "manufacturer communications",
        ],
    }
    return (
        parts,
        lineage,
        {
            "split_check": split,
            "nhtsa_validation": validation,
            "admission_blockers": [
                "Historical CSV quote semantics absorb physical complaint records; a corrected edition and new frozen comparison are required"
            ]
            if not validation["literal_record_equivalence"]["valid"]
            else ["Source snapshot and final scientific/rights review required"],
        },
    )
