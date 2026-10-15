"""Historical choice reconstruction with explicit identity and order diagnostics.

Physical row order reproduces the old tie break. It does not establish that a
tied trial was observed earlier. Ambiguities block admission, never remove rows.
"""

import re
from collections import Counter, defaultdict

import numpy as np

from ..io import contained
from .curves import _csv_rows, _number
from .splits import check_units

COLUMNS = [
    "Subject",
    "Age",
    "Sex",
    "Protocol",
    "Session",
    "Block",
    "Trial",
    "Risk+AF8-Option",
    "Risk+AF8-Prob",
    "Hidden",
    "Choice",
    "EV",
]


def _positive_integer(value, name):
    number = _number(value)
    if number <= 0 or number != int(number):
        raise ValueError("Invalid choice " + name)
    return int(number)


def reconstruct_choices(recipe, source_root):
    from .native import _registered_groups, _row, identity

    (asset,) = [a for a in recipe["assets"] if a["role"] == "risk_choices"]
    path = contained(source_root, asset["path"])
    if path.stat().st_size > 40_000_000:
        raise ValueError("Choice source exceeds bounded reader size")
    rows = _csv_rows(path.read_bytes(), COLUMNS)
    if len(rows) > 100_000:
        raise ValueError("Choice source exceeds bounded row count")
    series, subjects, exact = defaultdict(list), defaultdict(list), Counter()
    for line, values in rows:
        subject, age, sex, protocol = values[:4]
        if not re.fullmatch(r"[0-9a-f]{64}", subject):
            raise ValueError("Unresolved choice subject identity")
        if sex not in {"F", "H"} or protocol not in {"E1.1", "E1.2", "E2.2"}:
            raise ValueError("Unregistered choice protocol or sex code")
        child_age = 0 if age == "adult" else _positive_integer(age, "age")
        if child_age > 120:
            raise ValueError("Invalid choice age")
        order = tuple(
            _positive_integer(v, n) for v, n in zip(values[4:7], COLUMNS[4:7], strict=True)
        )
        reward, probability, choice = (_number(values[i]) for i in (7, 8, 10))
        if order[2] > 40 or reward < 0 or not 0 <= probability <= 1 or choice not in {0, 1}:
            raise ValueError("Choice measurement outside declared domain")
        item = {
            "line": line,
            "age": age,
            "sex": sex,
            "order": order,
            "child_age": child_age,
            "reward": reward,
            "probability": probability,
            "choice": choice,
        }
        series[subject, protocol].append(item)
        subjects[subject].append(item)
        exact[tuple(values)] += 1
    assignments = _registered_groups(recipe, subjects)
    parts, lineage, units = {p: [] for p in ("train", "dev", "test")}, [], {}
    sequence_inventory, ties, conflicts = [], [], []
    tied_choices, tied_ages, tied_sexes = 0, 0, 0
    tie_counts = Counter()
    for subject, values in sorted(subjects.items()):
        group = identity(recipe["scenario_id"], "group", subject)
        units[group] = subject
        ages, sexes = sorted({r["age"] for r in values}), sorted({r["sex"] for r in values})
        if len(ages) > 1 or len(sexes) > 1:
            conflicts.append(
                {
                    "group": group,
                    "split": assignments[subject],
                    "ages": ages,
                    "sex_codes": sexes,
                    "source_rows": [r["line"] for r in values],
                }
            )
    for index, ((subject, protocol), values) in enumerate(sorted(series.items())):
        values.sort(key=lambda r: (*r["order"], r["line"]))
        split = assignments[subject]
        sequence_inventory.append(
            {
                "group": identity(recipe["scenario_id"], "group", subject),
                "protocol": protocol,
                "split": split,
                "source_rows_in_historical_order": [r["line"] for r in values],
            }
        )
        keys = defaultdict(list)
        for r in values:
            keys[r["order"]].append(r)
        for key, duplicate in keys.items():
            if len(duplicate) < 2:
                continue
            ties.append([index, *key, [r["line"] for r in duplicate]])
            tie_counts[split] += 1
            tied_choices += len({r["choice"] for r in duplicate}) > 1
            tied_ages += len({r["age"] for r in duplicate}) > 1
            tied_sexes += len({r["sex"] for r in duplicate}) > 1
        history = []
        for r in values:
            row, anchor = _row(
                recipe["scenario_id"],
                f"row{r['line']}",
                subject,
                split,
                {
                    "reward": r["reward"],
                    "probability": r["probability"],
                    "child": int(r["age"] != "adult"),
                    "age_child": float(r["child_age"]),
                    "multi": int(protocol == "E1.2"),
                    "description": int(protocol == "E2.2"),
                    "trial_progress": r["order"][2] / 40,
                    "lag_choice": history[-1] if history else 0.5,
                    "history_mean": float(np.mean(history)) if history else 0.5,
                    "has_history": int(bool(history)),
                },
                r["choice"],
                {"source_row": r["line"], "series_index": index, "history_count": len(history)},
            )
            parts[split].append(row)
            lineage.append(anchor)
            history.append(r["choice"])
    validation = {
        "status": "preparation_defect"
        if ties or conflicts
        else "no_observed_identity_or_order_conflict",
        "source_rows": len(rows),
        "subject_ids": len(subjects),
        "subject_protocol_series": len(series),
        "repeated_order_keys": len(ties),
        "extra_rows_with_tied_order": sum(len(v[-1]) - 1 for v in ties),
        "tied_order_keys_by_split": {p: tie_counts[p] for p in parts},
        "tied_order_keys_with_conflicting_choices": int(tied_choices),
        "tied_order_keys_with_conflicting_ages": int(tied_ages),
        "tied_order_keys_with_conflicting_sexes": int(tied_sexes),
        "exact_duplicate_source_rows_beyond_first": sum(n - 1 for n in exact.values()),
        "subject_ids_with_multiple_ages": sum(len(r["ages"]) > 1 for r in conflicts),
        "subject_ids_with_multiple_sex_codes": sum(len(r["sex_codes"]) > 1 for r in conflicts),
        "source_row_tie_break_establishes_chronology": False,
        "strict_prior_history_verified": False,
        "reason": "No acquisition timestamp or visit identity; source row is a reproducibility tie break only. Repeated keys and demographic conflicts require source clarification, not automatic merging, deletion or invented identities.",
        "hidden_and_ev_used_as_inputs": False,
        "history_scope": "Within Subject and Protocol, ordered Session/Block/Trial/source row; previous held-out choices can become later inputs. Historical replay, not verified chronological prediction or free-running simulation.",
    }
    return (
        parts,
        lineage,
        {
            "split_check": check_units(parts, units),
            "choice_validation": validation,
            "measurement_asset": asset["path"],
            "lineage_interpretation": "Each source_row is a 1-based CSV line. series_index indexes history_series; history_count selects exactly that many preceding source rows from its ordered list. No current/future sequence positions included; physical chronological order remains unverified.",
            "history_series": sequence_inventory,
            "order_ties": {
                "columns": ["series_index", "session", "block", "trial", "source_rows"],
                "rows": ties,
            },
            "subject_identity_conflicts": conflicts,
            "admission_blockers": [
                "Acquisition chronology and visit/participant identity are unresolved; the asserted strict prior-choice window is not established",
                "Resolve repeated order keys and demographic conflicts under a new reviewed contract; retain this complete historical cohort",
                "Complete source rights, protocol/units and notice review before admission",
            ],
        },
    )
