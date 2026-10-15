"""Curator-only PIAAC respondent custody; no population or causal inference.

Decodes five selected numeric fields from the registered public-use CSV files.
Source weights determine historical eligibility but are not compact predictors
or current scoring weights. Plausible values never enter the reconstruction.
"""

import csv
import hashlib
import math
import re
from collections import Counter

from ..io import contained
from .splits import check_units

PARSER = "piaac-native-respondent-deciles-v1"
INPUT_UNITS = {
    "education": "source derived years of formal education",
    "age": "fixed midpoint of published five-year age bin; final60–65midpoint62.5",
    "japan": "country indicator",
}
OUTPUT_UNITS = "binary EARNHRDCLC2>=8"
MIDPOINTS = (17.5, 22, 27, 32, 37, 42, 47, 52, 57, 62.5)
COUNTRIES = {"USA": "840", "Japan": "392"}
FIELDS = ("SEQID", "CNTRYID", "CNTRYID_E", "AGEG5LFS", "YRSQUALC2", "EARNHRDCLC2", "SPFWT0")
MISSING = {
    "AGEG5LFS": {".", ".a", ".b", ".n"},
    "YRSQUALC2": {".", ".d", ".n", ".r", ".v"},
    "EARNHRDCLC2": {".", ".v"},
    "SPFWT0": {"."},
}
MAX_BYTES = 55_000_000
MAX_ROWS = 10_000


def number(value, field):
    if value.lower() in MISSING[field]:
        return None
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?", value):
        raise ValueError("Unknown PIAAC missing or numeric code: " + field)
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Nonfinite PIAAC value")
    if field in {"AGEG5LFS", "EARNHRDCLC2"} and (result != int(result) or not 1 <= result <= 10):
        raise ValueError("Invalid PIAAC ordinal category")
    if field == "YRSQUALC2" and not 0 <= result <= 99:
        raise ValueError("Invalid PIAAC education value")
    return result


def block(country, seqid):
    key = "principia100-batch7:PIAAC:" + country + ":" + seqid
    return int(hashlib.sha256(key.encode()).hexdigest()[:16], 16) % 10


def bounded_lines(stream):
    total = 0
    while raw := stream.readline(100_001):
        total += len(raw)
        if len(raw) > 100_000 or total > MAX_BYTES or b"\x00" in raw:
            raise ValueError("Oversized or invalid PIAAC source line")
        yield raw.decode("utf-8")


def decode(path, country):
    if country not in COUNTRIES or path.stat().st_size > MAX_BYTES:
        raise ValueError("Unknown or oversized PIAAC country source")
    selected, seen, excluded, missing, weights = [], set(), Counter(), Counter(), []
    with path.open("rb") as stream:
        reader = csv.reader(bounded_lines(stream), delimiter=";", strict=True)
        header = next(reader, [])
        if len(header) != 2483 or len(set(header)) != len(header) or not set(FIELDS) <= set(header):
            raise ValueError("Unexpected PIAAC public-use schema")
        indexes = {field: header.index(field) for field in FIELDS}
        for row_no, cells in enumerate(reader, 2):
            if row_no > MAX_ROWS + 1 or reader.line_num != row_no or len(cells) != len(header):
                raise ValueError("Invalid PIAAC record width, count or physical-line boundary")
            r = {k: cells[i] for k, i in indexes.items()}
            seqid = r["SEQID"]
            if not re.fullmatch(r"[1-9][0-9]{0,8}", seqid) or seqid in seen:
                raise ValueError("Missing, ambiguous or duplicate PIAAC respondent identity")
            seen.add(seqid)
            if any(r[k] != COUNTRIES[country] for k in ["CNTRYID", "CNTRYID_E"]):
                raise ValueError("PIAAC country identity mismatch")
            values = {k: number(r[k], k) for k in MISSING}
            reasons = []
            for k, value in values.items():
                if value is None:
                    missing[k + ":" + r[k].lower()] += 1
                    reasons.append("missing_" + k)
            age, edu, decile, weight = (values[k] for k in MISSING)
            if age is not None and age < 3:
                reasons.append("age_below_25")
            if edu is not None and edu > 30:
                reasons.append("education_above_30")
            if weight is not None and weight <= 0:
                reasons.append("nonpositive_final_weight")
            excluded.update(reasons)
            if reasons:
                continue
            selected.append(
                {
                    "seqid": seqid,
                    "source_row": row_no,
                    "country": country,
                    "bucket": block(country, seqid),
                    "education": edu,
                    "age": MIDPOINTS[int(age) - 1],
                    "target": float(decile >= 8),
                }
            )
            weights.append(weight)
    if not selected:
        raise ValueError("No eligible PIAAC respondents")
    return selected, {
        "country": country,
        "source_records": len(seen),
        "source_columns": len(header),
        "eligible_records": len(selected),
        "excluded_records": len(seen) - len(selected),
        "exclusion_reason_counts_nonexclusive": dict(sorted(excluded.items())),
        "missing_codes": dict(sorted(missing.items())),
        "eligible_final_weight": {
            "min": min(weights),
            "max": max(weights),
            "distinct": len(set(weights)),
        },
        "selected_columns": list(FIELDS),
        "survey_weights_exported": False,
        "plausible_values_used": False,
        "duplicate_respondents": 0,
    }


def build_rows(recipe, records):
    from .native import _registered_groups, _row, identity

    groups = {c + ":respondentblock" + str(i) for c in COUNTRIES for i in range(10)}
    assignments = _registered_groups(recipe, groups)
    for c in COUNTRIES:
        for i in range(10):
            if (assignments[c + ":respondentblock" + str(i)] == "test") != (i in {0, 1}):
                raise ValueError("Original PIAAC confirmation block changed")
    sources = {a["role"]: a["path"] for a in recipe["assets"]}
    parts, lineage, identities, used = {p: [] for p in ("train", "dev", "test")}, [], set(), set()
    for r in records:
        c, seqid = r["country"], r["seqid"]
        if c not in COUNTRIES or r["bucket"] != block(c, seqid):
            raise ValueError("PIAAC respondent block differs from fixed identity hash")
        label = c + ":" + seqid
        if label in identities:
            raise ValueError("Repeated PIAAC respondent across records")
        identities.add(label)
        group = c + ":respondentblock" + str(r["bucket"])
        used.add(group)
        split = assignments[group]
        row, anchor = _row(
            recipe["scenario_id"],
            label,
            group,
            split,
            {"education": r["education"], "age": r["age"], "japan": float(c == "Japan")},
            r["target"],
            {
                "source": sources[c + "_respondents"],
                "source_row": r["source_row"],
                "input_columns": ["YRSQUALC2", "AGEG5LFS", "CNTRYID"],
                "transform": "fixed age-bin midpoint; country indicator; no fitted transform",
            },
        )
        parts[split].append(row)
        lineage.append(anchor)
    if used != groups:
        raise ValueError("Incomplete PIAAC respondent block coverage")
    return (
        parts,
        lineage,
        check_units(parts, {identity(recipe["scenario_id"], "group", g): g for g in groups}),
    )


def reconstruct_piaac(recipe, source_root):
    if recipe["input_units"] != INPUT_UNITS or recipe["output_units"] != OUTPUT_UNITS:
        raise ValueError("PIAAC recipe units differ")
    assets = {a["role"]: a for a in recipe["assets"]}
    if len(assets) != len(recipe["assets"]) or set(assets) != {
        "USA_respondents",
        "Japan_respondents",
        "international_codebook",
        "derived_codebook",
    }:
        raise ValueError("Unexpected PIAAC registered asset roles")
    records, inventories = [], []
    for country in COUNTRIES:
        rows, inventory = decode(
            contained(source_root, assets[country + "_respondents"]["path"]), country
        )
        records.extend(rows)
        inventories.append(inventory)
    parts, lineage, split = build_rows(recipe, records)
    return (
        parts,
        lineage,
        {
            "split_check": split,
            "piaac_validation": {
                "native_inventory": inventories,
                "whole_respondent_blocks": 20,
                "age_midpoints": list(MIDPOINTS),
                "country_values": COUNTRIES,
                "respondent_identity_overlap": 0,
                "original_confirmation_buckets": [0, 1],
                "local_preprocessing_fits": 0,
                "discovery_rule_fits": 0,
                "compact_weighting": "unweighted Brier within each hash block; equal mean across blocks",
                "legacy_weighting": "within-block final survey weight; not retained in compact scoring",
                "survey_design_variance_established": False,
                "scope": "Complete-case contemporaneous association with country-relative wage/salary earnings deciles; no absolute wages, prospective earnings, survey-population or causal inference",
                "source_derivations": "Coarsened ages, years assigned from completed education, country earnings deciles and final weights already derived upstream",
                "excluded_fields": [
                    "plausible values",
                    "replicate weights",
                    "absolute earnings",
                    "occupation",
                    "assessment responses",
                    "unselected background variables",
                ],
            },
            "admission_blockers": [
                "Review compact unweighted versus historical survey-weighted estimands; no survey-population or design-variance claims",
                "Whole respondent/hash-block separation does not reconstruct survey clusters, time ordering or country-held-out transfer",
                "Resolve source rights/notices, upstream derivations and final scientific contract before admission",
            ],
        },
    )
