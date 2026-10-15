from __future__ import annotations

import re

from ..engine.expression import FUNCS


def validate_contract(contract):
    if not isinstance(contract, dict):
        return ["contract must be an object"]
    errors = []
    required = {
        "task_id",
        "scenario_id",
        "inputs",
        "output",
        "split",
        "metric",
        "stability",
        "test_exposure",
    }
    errors.extend("missing:" + k for k in sorted(required - set(contract)))
    inputs = contract.get("inputs", [])
    if not isinstance(inputs, list) or not inputs or not all(isinstance(x, str) for x in inputs):
        errors.append("inputs must be a nonempty string list")
        inputs = []
    elif len(set(inputs)) != len(inputs):
        errors.append("inputs must be unique and nonempty")
    if any(
        not isinstance(x, str)
        or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", x)
        or x in FUNCS
        or x in {"sample_id", "group", contract.get("output")}
        for x in inputs
    ):
        errors.append("Inputs contain a prohibited identity, target or operator name")
    split = contract.get("split", {})
    if not isinstance(split, dict):
        split = {}
    if not all(isinstance(split.get(x), str) for x in ["train", "dev", "test"]):
        errors.append("split must define train, dev and test")
    for name in ["train", "dev", "test"]:
        value = split.get(name, "")
        if isinstance(value, str) and (value.startswith("/") or ".." in value.split("/")):
            errors.append("split path escapes scenario")
    if contract.get("metric", {}).get("primary") not in {"mae", "rmse", "brier", "log_mae"}:
        errors.append("Unsupported metric")
    if not contract.get("stability", {}).get("domain"):
        errors.append("stability.domain is required")
    if contract.get("test_exposure") not in {
        "retrospective-open-test",
        "private-test",
        "public-test",
        "local-user-split",
    }:
        errors.append("test_exposure must be explicit")
    return errors
