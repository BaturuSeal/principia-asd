"""Host-verified development evidence shared by explicit method adaptations."""

from __future__ import annotations

import numpy as np

from ..evaluate.metrics import validity
from ..io import sha


def cohort_counts(search):
    return {
        "training_rows": len(search.train),
        "development_rows": len(search.dev),
        "training_groups": len({str(row["group"]) for row in search.train}),
        "development_groups": len({str(row["group"]) for row in search.dev}),
    }


def cohort_context(search):
    return {
        "verified_counts": cohort_counts(search),
        "examples_in_prompt": min(6, len(search.train)),
        "examples_are_only_a_preview": True,
        "fitting_uses_all_training_rows": True,
        "selection_uses_all_development_rows": True,
        "groups_are_contract_units_not_proof_of_independence": True,
    }


def exact_cohort_report(value, search):
    # Canonical types matter: True is not an acceptable replacement for a count of 1.
    return isinstance(value, dict) and sha(value) == sha(cohort_counts(search))


def prediction_requirements(task):
    metric = task["metric"]["primary"]
    return {
        "finite_on_every_eligible_row": True,
        "strictly_positive": bool(task.get("positive_prediction") or metric == "log_mae"),
        "nonnegative": bool(task.get("nonnegative_prediction") or metric == "brier"),
        "at_most_one": metric == "brier",
        "metric": metric,
    }


def invalid_output_diagnostics(search, train_predictions, dev_predictions, parameters):
    """Summarize already executed predictions; no additional fit or target access."""
    result = {
        "scope": "train/dev output-domain failure only",
        "fitted_parameters": dict(parameters),
        "prediction_requirements": prediction_requirements(search.task),
        "additional_fits": 0,
        "additional_prediction_executions": 0,
        "private_test_access": False,
    }
    for label, pred, rows in [
        ("train", train_predictions, search.train),
        ("dev", dev_predictions, search.dev),
    ]:
        finite = np.isfinite(pred)
        good = validity(pred, search.task)
        values = pred[finite]
        result[label] = {
            "rows": len(rows),
            "nonfinite_outputs": int((~finite).sum()),
            "invalid_outputs": int((~good).sum()),
            "finite_min": float(values.min()) if len(values) else None,
            "finite_max": float(values.max()) if len(values) else None,
            "first_invalid_rows": [
                {"row_index": int(i), "sample_id": rows[i].get("sample_id"), "group": rows[i].get("group")}
                for i in np.flatnonzero(~good)[:5]
            ],
        }
    return result
