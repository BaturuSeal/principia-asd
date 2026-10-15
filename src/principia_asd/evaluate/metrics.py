"""Candidate-blind, deterministic metrics. No provider imports or calls."""

from __future__ import annotations

import math

import numpy as np

from ..engine.expression import complexity, execute


def point_loss(pred, truth, metric):
    pred = np.asarray(pred, float)
    truth = np.asarray(truth, float)
    if pred.shape != truth.shape or not len(truth):
        raise ValueError("Empty or mismatched cohort")
    if metric == "mae":
        return np.abs(pred - truth)
    if metric in {"rmse", "brier"}:
        return (pred - truth) ** 2
    if metric == "log_mae":
        if np.any(pred <= 0) or np.any(truth <= 0):
            raise ValueError("Log loss requires positive predictions and targets")
        return np.abs(np.log(pred) - np.log(truth))
    raise ValueError("Unsupported primary metric: " + str(metric))


def loss(pred, truth, metric="mae", groups=None):
    values = point_loss(pred, truth, metric)
    if not np.isfinite(values).all():
        raise ValueError("Nonfinite loss")
    if groups is None:
        result = float(np.mean(values))
    else:
        # Every declared group has equal weight. Partial cohorts never get ranked.
        grouped = {}
        for g, v in zip(groups, values, strict=True):
            grouped.setdefault(str(g), []).append(float(v))
        result = float(np.mean([np.mean(v) for v in grouped.values()]))
    return math.sqrt(result) if metric == "rmse" else result


def columns(rows, inputs):
    return {name: np.asarray([r[name] for r in rows]) for name in inputs}


def validity(pred, contract):
    good = np.isfinite(pred)
    if contract.get("positive_prediction") or contract["metric"]["primary"] == "log_mae":
        good &= pred > 0
    if contract.get("nonnegative_prediction"):
        good &= pred >= 0
    if contract["metric"]["primary"] == "brier":
        good &= (pred >= 0) & (pred <= 1)
    return good


def predict(rule, rows, contract):
    if rule.get("representation") == "bound_expression_v1":
        raise ValueError("Explicit-state rules require the bound evaluator and trusted freeze")
    if rule.get("representation") == "tree":
        tree = rule["tree"]

        def node(r, i=0):
            while tree["left"][i] != -1:
                i = (
                    tree["left"][i]
                    if float(r[tree["features"][tree["feature"][i]]]) <= tree["threshold"][i]
                    else tree["right"][i]
                )
            return tree["value"][i]

        return np.asarray([node(r) for r in rows], float)
    return execute(
        rule["expression"], columns(rows, contract["inputs"]), rule.get("parameters", {}), len(rows)
    )


def stability_profile(rule, rows, contract):
    cfg = contract["stability"]
    rng = np.random.default_rng(771)
    # Diagnostic sampling is disclosed and never changes predictive coverage.
    idx = (
        np.arange(len(rows))
        if len(rows) <= 512
        else np.sort(rng.choice(len(rows), 512, replace=False))
    )
    subset = [rows[i] for i in idx]
    altered = []
    for row in subset:
        r = dict(row)
        for k in contract["inputs"]:
            bounds = cfg.get("input_ranges", {}).get(k)
            if bounds and isinstance(row[k], (int, float)):
                sigma = (bounds[1] - bounds[0]) * cfg.get("relative_noise", 0.01)
                r[k] = float(np.clip(float(row[k]) + rng.normal(0, sigma), *bounds))
        altered.append(r)
    try:
        base = predict(rule, subset, contract)
        pert = predict(rule, altered, contract)
        valid = np.isfinite(base) & np.isfinite(pert)
        scale = max(float(cfg.get("output_scale", 1)), 1e-12)
        sensitivity = np.abs(pert[valid] - base[valid]) / scale
        return {
            "mean_relative_sensitivity": float(np.mean(sensitivity)) if len(sensitivity) else None,
            "invalid_output_rate": float(1 - np.mean(valid)),
            "samples": len(subset),
            "population_rows": len(rows),
            "ranking": bool(cfg.get("ranking", False)),
            "scope": cfg.get("scope", "diagnostic"),
            "perturbation_labels_available": False,
        }
    except (ValueError, KeyError, ArithmeticError):
        return {
            "mean_relative_sensitivity": None,
            "invalid_output_rate": 1.0,
            "samples": len(subset),
            "population_rows": len(rows),
            "ranking": False,
            "scope": "diagnostic evaluation failed",
        }


def evaluate_rule(rule, rows, targets, contract):
    if rule.get("representation") == "bound_expression_v1":
        raise ValueError("Explicit-state rules require the bound evaluator and trusted freeze")
    if len(rows) != len(targets) or not rows:
        raise ValueError("Cohort length mismatch")
    if not np.isfinite(np.asarray(targets, float)).all():
        raise ValueError("Preparation defect: invalid target")
    metric = contract["metric"]["primary"]
    groups = [r.get("group", "cohort") for r in rows]
    try:
        pred = predict(rule, rows, contract)
        good = validity(pred, contract)
    except (ValueError, KeyError, ArithmeticError, TypeError):
        pred = np.full(len(rows), np.nan)
        good = np.zeros(len(rows), bool)
    covered = int(good.sum())
    full = covered == len(rows)
    primary = loss(pred, targets, metric, groups) if full else None
    by_group = []
    if full:
        for g in sorted(set(groups)):
            ids = np.asarray([x == g for x in groups])
            by_group.append(
                {
                    "group": g,
                    "rows": int(ids.sum()),
                    "error": loss(pred[ids], np.asarray(targets)[ids], metric),
                }
            )
    if rule.get("representation") == "tree":
        simp = {
            "weighted_operator_count": len(rule["tree"]["value"]),
            "free_parameters": len(rule["tree"]["value"])
            + sum(i != -2 for i in rule["tree"]["feature"]),
            "learned_state_bytes": len(str(rule["tree"]).encode()),
            "expanded_expression": "complete tree in Rule Card",
            "scope": "predictive reference, not a compact scientific formula",
        }
    else:
        simp = complexity(rule["expression"], rule.get("parameters"))
    return {
        "status": "valid" if full else "invalid",
        "accuracy": {
            "primary": metric,
            "primary_error": primary,
            "aggregation": "equal_group_mean",
            "mae": loss(pred, targets, "mae", groups) if full else None,
            "rmse": loss(pred, targets, "rmse", groups) if full else None,
            "invalid_output_rate": 1 - covered / len(rows),
        },
        "simplicity": simp,
        "stability": stability_profile(rule, rows, contract),
        "coverage": {"eligible": len(rows), "predicted": covered, "fraction": covered / len(rows)},
        "by_group": by_group,
        "uncertainty": {
            "status": "not_assessed",
            "reason": "No independent replicate uncertainty model admitted; group errors are descriptive",
        },
        "predictions": [float(v) if math.isfinite(v) else None for v in pred],
    }


def pareto_front(receipts, accuracy_key="primary_error"):
    valid = [
        r
        for r in receipts
        if r.get("status") in {"complete", "valid"}
        and r.get("coverage", {}).get("fraction") == 1
        and r.get("accuracy", {}).get(accuracy_key) is not None
        and r.get("accuracy_gate", True)
        and r.get("ranking_authorized", True)
        and r.get("simplicity", {}).get("ranking_authorized", True)
    ]

    def values(r):
        v = [
            r["accuracy"][accuracy_key],
            r["simplicity"]["weighted_operator_count"],
            r["simplicity"]["free_parameters"],
        ]
        if r["stability"].get("ranking"):
            s = r["stability"].get("mean_relative_sensitivity")
            v.append(float("inf") if s is None else s)
        return v

    return sorted(
        [
            c
            for c in valid
            if not any(
                len(values(o)) == len(values(c))
                and all(a <= b for a, b in zip(values(o), values(c), strict=True))
                and any(a < b for a, b in zip(values(o), values(c), strict=True))
                for o in valid
                if o is not c
            )
        ],
        key=lambda r: r["accuracy"][accuracy_key],
    )
