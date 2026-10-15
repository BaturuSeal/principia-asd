"""Curator-only SHED public-use reconstruction with upstream imputation audit.

Reproduces historical respondent/state custody without exporting test targets,
survey weights, imputation flags or unselected survey answers to discovery.
"""

import csv
import hashlib
import math
import re
from collections import Counter

from ..io import contained
from .fracture import bounded_zip
from .splits import check_units

PARSER = "shed-native-state-respondent-custody-v1"
MEMBER = "public2025.csv"
INPUT_UNITS = {
    "income_proxy": "thousands USD/year bracket proxy",
    "household_size": "persons",
    "shock": "no paid/profit work lastmonth (D1A0) binary, not jobloss",
    "age": "years",
}
OUTPUT_UNITS = "binary EF3_h"
INCOME = dict(
    zip(
        [
            "Less than $10,000",
            "$10,000 to $24,999",
            "$25,000 to $49,999",
            "$50,000 to $74,999",
            "$75,000 to $99,999",
            "$100,000 to $149,999",
            "$150,000 or more",
        ],
        [5, 17.5, 37.5, 62.5, 87.5, 125, 175],
        strict=True,
    )
)
STATES = set(
    "ak al ar az ca co ct dc de fl ga hi ia id il in ks ky la ma md me mi mn mo ms mt nc nd ne nh nj nm nv ny oh ok or pa ri sc sd tn tx ut va vt wa wi wv wy".split()
)
FIELDS = (
    "shedid",
    "EF3_h",
    "D1A",
    "ppinc7",
    "pphhsize",
    "ppage",
    "weight",
    "ppstaten",
    "EF3_h_iflag",
    "D1A_iflag",
    "field_month",
    "field_day",
)
MAX_BYTES = 55_000_000
MAX_ROWS = 20_000


def hashgroup(value):
    return int(hashlib.sha256(("principia100-batch7:" + value).encode()).hexdigest()[:16], 16)


def bounded_lines(stream):
    total = 0
    while raw := stream.readline(100_001):
        total += len(raw)
        if len(raw) > 100_000 or total > MAX_BYTES or b"\x00" in raw:
            raise ValueError("Oversized or invalid SHED source line")
        yield raw.decode("utf-8")


def numeric(value, *, integer=False):
    if value in {"", "."}:
        return None
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?", value):
        raise ValueError("Unrecognized SHED numeric code")
    n = float(value)
    if not math.isfinite(n) or (integer and n != int(n)):
        raise ValueError("Nonfinite or invalid SHED numeric value")
    return n


def decode_archive(path):
    selected, seen, states, reasons, flags, weights, dates = (
        [],
        set(),
        set(),
        Counter(),
        Counter(),
        [],
        Counter(),
    )
    with bounded_zip(path, max_bytes=MAX_BYTES, max_member_bytes=MAX_BYTES, max_members=1) as z:
        if z.namelist() != [MEMBER] or z.getinfo(MEMBER).compress_type not in {0, 8}:
            raise ValueError("Unregistered SHED archive member or compression")
        with z.open(MEMBER) as stream:
            reader = csv.reader(bounded_lines(stream), strict=True)
            header = next(reader, [])
            if (
                len(header) != 815
                or len(set(header)) != len(header)
                or not set(FIELDS) <= set(header)
            ):
                raise ValueError("Unexpected SHED public-use schema")
            indexes = {k: header.index(k) for k in FIELDS}
            for row_no, cells in enumerate(reader, 2):
                if row_no > MAX_ROWS + 1 or reader.line_num != row_no or len(cells) != len(header):
                    raise ValueError("Invalid SHED record count, width or physical-line boundary")
                r = {k: cells[i] for k, i in indexes.items()}
                sid = r["shedid"]
                if not re.fullmatch(r"[1-9][0-9]{8}", sid) or sid in seen:
                    raise ValueError("Missing, ambiguous or duplicate SHED respondent")
                seen.add(sid)
                state = r["ppstaten"]
                if state and state not in STATES:
                    raise ValueError("Unrecognized SHED state code")
                if state:
                    states.add(state)
                for k in ["EF3_h", "D1A"]:
                    if r[k] not in {"Yes", "No", "", "."} or r[k + "_iflag"] not in {"0", "1"}:
                        raise ValueError("Unknown SHED response or imputation flag")
                    flags[k] += int(r[k + "_iflag"])
                if r["ppinc7"] not in {*INCOME, "", "."}:
                    raise ValueError("Unknown SHED income bracket")
                age, size, weight = (
                    numeric(r["ppage"], integer=True),
                    numeric(r["pphhsize"], integer=True),
                    numeric(r["weight"]),
                )
                month, day = (
                    numeric(r["field_month"], integer=True),
                    numeric(r["field_day"], integer=True),
                )
                if month != 10 or day is None or not 17 <= day <= 28:
                    raise ValueError("SHED field date outside registered 2025 acquisition")
                dates[str(int(day))] += 1
                excluded = []
                for k in ["EF3_h", "D1A"]:
                    if r[k] not in {"Yes", "No"}:
                        excluded.append("missing_" + k)
                if r["ppinc7"] not in INCOME:
                    excluded.append("missing_income")
                if age is None or not 18 <= age <= 100:
                    excluded.append("invalid_or_missing_age")
                if size is None or not 1 <= size <= 20:
                    excluded.append("invalid_or_missing_household_size")
                if weight is None or weight <= 0:
                    excluded.append("nonpositive_or_missing_weight")
                if not state:
                    excluded.append("missing_state")
                reasons.update(excluded)
                if excluded:
                    continue
                weights.append(weight)
                selected.append(
                    {
                        "sid": sid,
                        "source_row": row_no,
                        "state": state,
                        "income_proxy": float(INCOME[r["ppinc7"]]),
                        "household_size": size,
                        "age": age,
                        "shock": float(r["D1A"] == "No"),
                        "target": float(r["EF3_h"] == "Yes"),
                        "target_imputed": int(r["EF3_h_iflag"]),
                        "work_imputed": int(r["D1A_iflag"]),
                    }
                )
        if not selected:
            raise ValueError("No eligible SHED respondents")
        return selected, {
            "source_records": len(seen),
            "eligible_records": len(selected),
            "excluded_records": len(seen) - len(selected),
            "source_columns": len(header),
            "native_expanded_bytes": z.getinfo(MEMBER).file_size,
            "states_before_eligibility": sorted(states),
            "duplicate_respondents": 0,
            "exclusion_reason_counts_nonexclusive": dict(sorted(reasons.items())),
            "source_imputation_counts": dict(flags),
            "field_days_october_2025": dict(sorted(dates.items())),
            "eligible_weights": {
                "min": min(weights),
                "max": max(weights),
                "distinct": len(set(weights)),
            },
        }


def build_rows(recipe, records, states):
    from .native import _registered_groups, _row, identity

    if not states or len(set(states)) != len(states) or not set(states) <= STATES:
        raise ValueError("Invalid SHED pre-eligibility state inventory")
    assignments = _registered_groups(recipe, {"state:" + s for s in states})
    held = set(
        sorted(states, key=lambda s: hashgroup("SHED-state:" + s))[: max(1, len(states) // 5)]
    )
    if {g[6:] for g, split in assignments.items() if split == "test"} != held:
        raise ValueError("Original SHED confirmation states changed")
    parts, lineage, seen = {p: [] for p in ("train", "dev", "test")}, [], set()
    imputed = {p: {"target": 0, "work_input": 0} for p in parts}
    for r in records:
        if r["sid"] in seen:
            raise ValueError("Repeated SHED respondent in reconstructed records")
        seen.add(r["sid"])
        group = "state:" + r["state"]
        split = assignments[group]
        row, anchor = _row(
            recipe["scenario_id"],
            r["sid"],
            group,
            split,
            {k: r[k] for k in ["income_proxy", "household_size", "shock", "age"]},
            r["target"],
            {"source_row": r["source_row"], "member": MEMBER},
        )
        parts[split].append(row)
        lineage.append(anchor)
        imputed[split]["target"] += r["target_imputed"]
        imputed[split]["work_input"] += r["work_imputed"]
    units = {identity(recipe["scenario_id"], "group", g): g for g in assignments}
    return parts, lineage, check_units(parts, units), imputed


def reconstruct_shed(recipe, source_root):
    if recipe["input_units"] != INPUT_UNITS or recipe["output_units"] != OUTPUT_UNITS:
        raise ValueError("SHED recipe units differ")
    assets = {a["role"]: a for a in recipe["assets"]}
    if len(assets) != len(recipe["assets"]) or set(assets) != {"respondents_archive", "codebook"}:
        raise ValueError("Unexpected SHED registered asset roles")
    records, inventory = decode_archive(
        contained(source_root, assets["respondents_archive"]["path"])
    )
    parts, lineage, split, imputed = build_rows(
        recipe, records, inventory["states_before_eligibility"]
    )
    return (
        parts,
        lineage,
        {
            "split_check": split,
            "measurement_asset": assets["respondents_archive"]["path"],
            "lineage_interpretation": "1-based physical CSV row in public2025.csv; only ppinc7,pphhsize,D1A,ppage are predictors; fixed income proxies and No-work indicator, no fitted transform. Targets and individual imputation flags are not exported in lineage.",
            "shed_validation": {
                "native_inventory": inventory,
                "imputed_cells_by_partition": imputed,
                "income_bracket_proxies_thousand_usd": INCOME,
                "local_preprocessing_fits": 0,
                "discovery_rule_fits": 0,
                "upstream_imputation_training_scope_verified": False,
                "source_quality_flags_used_for_selection": False,
                "compact_weighting": "Unweighted within-state Brier; equal mean across states",
                "legacy_weighting": "Within-state sample_weight from weight; absent from compact scoring",
                "scope": "Contemporaneous association with a stated hypothetical expense response; profile variables were collected separately, not prospective distress or an income intervention",
                "nonwork_scope": "D1A No means no pay/profit work last month, not job loss or an exogenous shock",
                "individual_survey_weights_or_imputation_flags_exported": False,
            },
            "admission_blockers": [
                "Upstream response/input imputation is present; its fitted donor/model scope and cross-partition independence are unverified",
                "Compact scoring omits survey weights; population estimates and design-based uncertainty are not established",
                "Review source rights/notices, profile timing, group dependence and scientific contract before admission",
            ],
        },
    )
