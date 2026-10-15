"""Conservative read-only witnesses; absence of a match never certifies provenance."""

from __future__ import annotations

import ast

import numpy as np

from ..io import sha
from .expression import expanded, parse

AUDIT_VERSION = "literal-lineage-audit-v1"


def _negative(key):
    if key[0] == "number":
        return ("number", -key[1])
    if key[0] == "Mult":
        return ("Mult", _negative(key[1]), key[2])
    if key[0] == "negative":
        return key[1]
    return ("negative", key)


def exact_key(node):
    """Normalize only signed literals and subtraction, never fitted-value tolerances."""
    if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
        return ("number", float(node.value))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        key = exact_key(node.operand)
        return _negative(key) if isinstance(node.op, ast.USub) else key
    if isinstance(node, ast.BinOp):
        left, right = exact_key(node.left), exact_key(node.right)
        if isinstance(node.op, ast.Sub):
            return ("Add", left, _negative(right))
        return (type(node.op).__name__, left, right)
    return (
        type(node).__name__,
        tuple(
            (
                name,
                exact_key(value)
                if isinstance(value, ast.AST)
                else tuple(exact_key(v) for v in value)
                if isinstance(value, list)
                else value,
            )
            for name, value in ast.iter_fields(node)
        ),
    )


def subtrees(expression):
    return {exact_key(node) for node in ast.walk(ast.parse(expression, mode="eval"))}


def audit_expression(rule, trace, train, train_sha256):
    """Caller verifies the frozen grammar source; report witnesses, not corrected rank."""
    base = {
        "rule_id": rule["rule_id"],
        "full_learned_state_status": "not_assessed",
        "reported_free_parameters": rule.get("simplicity", {}).get("free_parameters"),
        "train_sha256": train_sha256,
        "normalization_witnesses": [],
        "prior_fit_matches": [],
        "scope": "Exact known-pattern matches only; opaque, rounded or algebraically rewritten learned state is not excluded",
    }
    if rule.get("representation") != "expression":
        return base | {"scan_status": "nonexpression_not_assessed"}
    expression = rule["expression"]
    parse(expression, rule["inputs"], list(rule.get("parameters", {})))
    keys = subtrees(expression)
    # Only host grammar origins establish the origin of the computed statistics.
    # Model-written lookalikes alone are not accepted as provenance proof.
    if rule.get("origin", "").startswith(("grammar-round-", "composition-round-", "beam-round-")):
        for name in rule["inputs"]:
            values = np.asarray([r[name] for r in train])
            if not np.issubdtype(values.dtype, np.number) or np.std(values) <= 0:
                continue
            mean = float(np.mean(values))
            scale = max(float(np.std(values)), 1e-12)
            normalized = f"({name}-{mean!r})/{scale!r}"
            if exact_key(ast.parse(normalized, mode="eval").body) in keys:
                base["normalization_witnesses"].append(
                    {
                        "input": name,
                        "mean": mean,
                        "scale": scale,
                        "statistics": 2,
                        "origin": "host_grammar_train_mean_and_population_std",
                        "source": {
                            "partition": "train",
                            "sha256": train_sha256,
                            "rows": len(train),
                        },
                        "expanded_subexpression": normalized,
                    }
                )
    seen = set()
    for index, item in enumerate(trace):
        for position, old in enumerate(item.get("diagnostics", {}).get("best", [])):
            params = old.get("parameters", {})
            old_expression = old.get("expression")
            if not params or not isinstance(old_expression, str):
                continue
            try:
                tree = parse(old_expression, rule["inputs"], list(params))
                used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} & set(params)
                if not used:
                    continue
                inlined = expanded(old_expression, params)
                key = exact_key(ast.parse(inlined, mode="eval").body)
            except (ValueError, SyntaxError):
                continue
            if key not in keys:
                continue
            program_sha = sha([old_expression, params])
            if program_sha in seen:
                continue
            seen.add(program_sha)
            # Record whether an actual saved kernel carries the same entire expression.
            kernel_matches = []
            for later_index, later in enumerate(trace[index + 1 :], index + 1):
                for kindex, kernel in enumerate(later.get("kernel_library", [])):
                    if not isinstance(kernel.get("expression"), str):
                        continue
                    if key == exact_key(ast.parse(kernel["expression"], mode="eval").body):
                        kernel_matches.append(
                            {
                                "trace_index": later_index,
                                "kernel_index": kindex,
                                "round": kernel.get("round"),
                                "model": kernel.get("model"),
                            }
                        )
            base["prior_fit_matches"].append(
                {
                    "diagnostic_trace_index": index,
                    "diagnostic_best_index": position,
                    "executed_program_sha256": program_sha,
                    "expression": old_expression,
                    "used_fitted_parameters": {k: params[k] for k in sorted(used)},
                    "expanded_subexpression": inlined,
                    "later_saved_kernel_matches": kernel_matches,
                    "interpretation": "Exact executed-fit/subexpression match; full timing and causal lineage require receipt-level review",
                }
            )
    return base | {
        "scan_status": "matched"
        if base["normalization_witnesses"] or base["prior_fit_matches"]
        else "no_exact_match_not_a_clearance"
    }
