"""Train-only shared-parameter fitting and development selection of equation systems."""

from __future__ import annotations

import copy
import json
import time

import numpy as np
from scipy.optimize import least_squares

from ..evaluate.metrics import columns, loss, validity
from ..io import sha
from .equations import (
    UNITS,
    VERSION,
    execute_system,
    expanded_expression,
    mathematical_signature,
    system_complexity,
    validate,
)


def run_equations(
    method_id,
    task,
    train,
    dev,
    *,
    gateway=None,
    roles=None,
    event=lambda *args: None,
    stopped=lambda: False,
    run_id="run",
    limits=None,
):
    from .search import Cancelled, decode_json

    limits = limits or {}
    units = task.get("quantity_units", {})
    if not all(k in units for k in [*task["inputs"], task["output"]]):
        return {
            "status": "unsupported",
            "reason": "Equation-system search needs reviewed quantity_units for every input and output. Existing untyped tasks remain available to the scalar methods.",
            "rules": [],
            "trace": [],
        }
    templates = task.get("equation_templates", [])
    if method_id == "equation_search" and not templates:
        return {
            "status": "unsupported",
            "reason": "No sourced equation templates are registered for this task; use the adaptive equation-system method or provide a reviewed template library.",
            "rules": [],
            "trace": [],
        }
    start = time.monotonic()
    cpu_start = time.process_time()
    records, failures, trace, seen = [], [], [], set()
    mathematical_forms = set()
    accounting = {
        "fitting_attempts": 0,
        "optimizer_evaluations": 0,
        "residual_evaluations": 0,
        "failed_fits": 0,
        "model_requests": 0,
        "restarts": 0,
        "structures": 0,
    }
    max_fits = min(int(limits.get("max_fits", 16)), int(limits.get("experiments", 16)), 16)
    x = columns(train, task["inputs"])
    xd = columns(dev, task["inputs"])
    y = np.asarray([r[task["output"]] for r in train], float)
    yd = np.asarray([r[task["output"]] for r in dev], float)
    groups, gd = [r["group"] for r in train], [r["group"] for r in dev]
    metric = task["metric"]["primary"]
    protocol_v2 = task.get("equation_protocol") == "multi-role-equations-v2"
    role_handoffs = []
    counts = {g: groups.count(g) for g in set(groups)}
    weights = np.sqrt([len(train) / len(counts) / counts[g] for g in groups])
    scale = max(float(np.std(y)), 1e-12)

    def check():
        if stopped():
            raise Cancelled("Equation search cancelled; prior requests are retained")
        if time.monotonic() - start > min(limits.get("wall_seconds", 2400), 2400):
            raise TimeoutError("Equation search wall-time budget exhausted")

    def log(stage, **detail):
        trace.append({"stage": stage, **detail})
        event(stage, detail)

    def fit(system, origin):
        check()
        digest = sha(system)
        if digest in seen:
            if protocol_v2:
                failures.append(
                    {
                        "name": system.get("name"),
                        "system_sha256": digest,
                        "reason": "Duplicate expanded mathematical structure; exact repeated proposal retained without refitting",
                    }
                )
            return
        if accounting["fitting_attempts"] >= max_fits:
            failures.append(
                {
                    "name": system.get("name"),
                    "system_sha256": digest,
                    "reason": "Fitting budget exhausted; proposal retained without execution",
                }
            )
            return
        seen.add(digest)
        accounting["structures"] += 1
        try:
            validate(system, task)
            if protocol_v2:
                identity = mathematical_signature(system)
                if identity in mathematical_forms:
                    raise ValueError(
                        "Duplicate expanded mathematical structure; renaming or refactoring does not create a new hypothesis"
                    )
                mathematical_forms.add(identity)
            names = list(system["parameters"])
            if not names:
                raise ValueError("Search templates must declare at least one fitted parameter")
            p = system["parameters"]
            # Log coordinates improve scaling of strictly positive physical quantities.
            log_coordinates = np.asarray([p[k]["bounds"][0] > 0 for k in names])
            bounds = np.asarray([p[k]["bounds"] for k in names], float).T
            initial = np.asarray([p[k]["initial"] for k in names], float)
            for i in np.flatnonzero(log_coordinates):
                bounds[:, i] = np.log(bounds[:, i])
                initial[i] = np.log(initial[i])

            def unpack(z):
                v = np.array(z, copy=True)
                v[log_coordinates] = np.exp(v[log_coordinates])
                return {k: float(np.clip(v[i], *p[k]["bounds"])) for i, k in enumerate(names)}

            best = None
            for restart in range(2):
                if accounting["fitting_attempts"] >= max_fits:
                    break
                accounting["fitting_attempts"] += 1
                accounting["restarts"] += int(restart > 0)
                evaluations = 0

                def residual(z):
                    nonlocal evaluations
                    check()
                    evaluations += 1
                    accounting["residual_evaluations"] += 1
                    if evaluations > 2400:
                        raise ValueError("Per-fit residual evaluation budget exhausted")
                    pred = execute_system(system, x, unpack(z), task, checked=True)
                    if not validity(pred, task).all():
                        raise ValueError("Invalid training prediction")
                    delta = np.log(pred) - np.log(y) if metric == "log_mae" else (pred - y) / scale
                    return delta * weights

                z = (
                    initial
                    if restart == 0
                    else np.clip(initial + (bounds[1] - bounds[0]) * 0.07, bounds[0], bounds[1])
                )
                try:
                    opt = least_squares(residual, z, bounds=bounds, x_scale="jac", max_nfev=200)
                    accounting["optimizer_evaluations"] += opt.nfev
                    if not opt.success:
                        raise ValueError("Optimizer did not converge: " + opt.message)
                    score = float(np.mean(residual(opt.x) ** 2))
                    if best is None or score < best[0]:
                        best = (score, opt, unpack(opt.x))
                except ValueError as exc:
                    accounting["failed_fits"] += 1
                    failures.append(
                        {
                            "system_sha256": digest,
                            "name": system["name"],
                            "restart": restart,
                            "reason": str(exc),
                            "residual_evaluations": evaluations,
                        }
                    )
            if best is None:
                raise ValueError("No converged training fit")
            _, opt, values = best
            pred = execute_system(system, xd, values, task, checked=True)
            if not validity(pred, task).all():
                raise ValueError("Invalid development prediction")
            singular = np.linalg.svd(opt.jac, compute_uv=False)
            rank = int(np.linalg.matrix_rank(opt.jac))
            quantity_values = execute_system(
                system, xd, values, task, intermediates=True, checked=True
            )
            residuals = pred - yd
            strata = {}
            for key in task["inputs"]:
                unique = np.unique(xd[key])
                edges = np.unique(np.quantile(xd[key], [0, 0.25, 0.5, 0.75, 1]))
                bins = []
                for i in range(max(0, len(edges) - 1)):
                    mask = (xd[key] >= edges[i]) & (
                        (xd[key] <= edges[i + 1])
                        if i == len(edges) - 2
                        else (xd[key] < edges[i + 1])
                    )
                    if mask.any():
                        bins.append(
                            {
                                "range": [float(edges[i]), float(edges[i + 1])],
                                "rows": int(mask.sum()),
                                "residual_bias": float(residuals[mask].mean()),
                                "mae": float(np.abs(residuals[mask]).mean()),
                            }
                        )
                strata[key] = {"unique_values": len(unique), "bins": bins}
            card = {
                "rule_id": f"{run_id}-system-{len(records) + 1}",
                "representation": VERSION,
                "equation_system": copy.deepcopy(system),
                "parameters": values,
                "expression": expanded_expression(system),
                "quantity_units": task["quantity_units"],
                "inputs": task["inputs"],
                "output": task["output"],
                "task_id": task["task_id"],
                "method_id": method_id,
                "method_version": "equation-search-v2" if protocol_v2 else "equation-search-v1",
                "model_ids": sorted(set(roles.values()))
                if protocol_v2 and method_id == "equation_agent"
                else [roles["coder"]]
                if method_id == "equation_agent"
                else [],
                "origin": origin,
                "dev_error": loss(pred, yd, metric, gd),
                "train_error": loss(
                    execute_system(system, x, values, task, checked=True), y, metric, groups
                ),
                "simplicity": system_complexity(system, values),
                "identifiability": {
                    "scope": "Local training Jacobian in optimization coordinates; no confidence interval or global identifiability claim",
                    "rank": rank,
                    "parameters": len(names),
                    "rank_deficient": rank < len(names),
                    "condition_number": float(singular[0] / singular[-1])
                    if singular[-1] > 0
                    else None,
                },
                "development_diagnostics": {
                    "residual_bias": float(np.mean(residuals)),
                    "residual_rmse": float(np.sqrt(np.mean(residuals**2))),
                    "input_strata": strata,
                    "groups": [
                        {
                            "group": g,
                            "loss": loss(
                                pred[np.asarray(gd) == g], yd[np.asarray(gd) == g], metric
                            ),
                        }
                        for g in sorted(set(gd))
                    ],
                    "intermediate_ranges": {
                        k: [float(v.min()), float(v.max())] for k, v in quantity_values.items()
                    },
                },
                "fit_recipe": {
                    "objective": "equal-group squared log residual"
                    if metric == "log_mae"
                    else "equal-group squared standardized residual",
                    "optimizer": "scipy least_squares",
                    "max_nfev_per_restart": 200,
                    "log_coordinate_parameters": [
                        k for i, k in enumerate(names) if log_coordinates[i]
                    ],
                    "training_rows": len(train),
                    "development_rows": len(dev),
                    "selection": "development only",
                },
                "scientific_status": "mechanism_hypothesis; not independently validated",
            }
            records.append(card)
            log(
                "equation_fitted",
                name=system["name"],
                equations=len(system["nodes"]),
                dev_error=card["dev_error"],
                rank=rank,
            )
        except (ValueError, KeyError, SyntaxError, TypeError, OverflowError) as exc:
            failures.append(
                {
                    "system_sha256": digest,
                    "name": system.get("name", "Unnamed proposal"),
                    "reason": str(exc),
                }
            )
            log("equation_rejected", name=system.get("name", "Unnamed proposal"), reason=str(exc))

    for system in templates[:4]:
        fit(system, "Sourced scientific template; host-fitted shared parameters")
    if method_id == "equation_agent":

        def diagnostics(record):
            detail = copy.deepcopy(record["development_diagnostics"])
            groups = sorted(detail.pop("groups"), key=lambda g: g["loss"])
            detail["group_summary"] = {
                "total_groups": len(groups),
                "preview_policy": "Lowest and highest three development losses; complete groups remain in the candidate artifact",
                "preview": groups[:3] + groups[max(3, len(groups) - 3) :],
                "median_loss": float(np.median([g["loss"] for g in groups])),
            }
            return detail

        if protocol_v2 and (
            not roles or not {"planner", "coder", "critic", "reporter"} <= roles.keys()
        ):
            raise ValueError("The multi-role equation protocol requires four explicit model roles")

        def handoff(role, instructions, packet):
            check()
            if accounting["model_requests"] >= int(limits.get("max_calls", 32)):
                raise ValueError("Multi-role equation protocol model-call limit exhausted")
            accounting["model_requests"] += 1
            log("equation_handoff", role=role)
            answer = gateway.complete(
                model=roles[role],
                system=instructions
                + " Return compact JSON with summary, hypotheses, limitations and recommended_changes fields. Keep the entire answer below 200 words; at most two short items per field. Do not reproduce the supplied equations or numerical tables. Use only the supplied train/development evidence. No test feedback exists. Known model families are priors, not new discoveries. Never claim identified mechanisms or significance.",
                prompt=json.dumps(packet, allow_nan=False),
                max_tokens=int(limits.get("equation_role_tokens", 3000)),
                request_id=f"{run_id}--equations--{role}",
            )
            role_handoffs.append(
                {
                    "role": role,
                    "model": roles[role],
                    "text": answer["text"],
                    "status": "model_interpretation_unreviewed",
                }
            )

        if protocol_v2:
            handoff(
                "planner",
                "Plan two discriminating, physically interpretable equation hypotheses. Identify assumptions, unmeasured intermediates, and explicit simpler countermodels. Suggest only unit-consistent changes with at most eight shared parameters.",
                {
                    "task": {
                        k: task.get(k)
                        for k in [
                            "description",
                            "inputs",
                            "output",
                            "quantity_units",
                            "variable_descriptions",
                            "split_policy",
                        ]
                    },
                    "seed_fits": [
                        {
                            "name": r["equation_system"]["name"],
                            "dev_error": r["dev_error"],
                            "diagnostics": diagnostics(r),
                            "identifiability": r["identifiability"],
                        }
                        for r in records
                    ],
                    "templates": templates,
                },
            )
        for round_id in range(min(2, int(limits.get("max_calls", limits.get("model_calls", 32))))):
            check()
            if accounting["fitting_attempts"] >= max_fits:
                break
            context = {
                "task": {k: task[k] for k in ["inputs", "output", "quantity_units", "metric"]},
                "variable_descriptions": task.get("variable_descriptions", {}),
                "template_examples": templates[:2],
                "schema_version": VERSION,
                "train_rows": len(train),
                "dev_rows": len(dev),
                "train_preview": [
                    {k: train[i][k] for k in [*task["inputs"], task["output"]]}
                    for i in np.linspace(0, len(train) - 1, min(6, len(train)), dtype=int)
                ],
                "fitted_systems": [
                    {
                        k: diagnostics(r) if k == "development_diagnostics" else r[k]
                        for k in [
                            "equation_system",
                            "parameters",
                            "dev_error",
                            "development_diagnostics",
                            "identifiability",
                        ]
                    }
                    for r in sorted(records, key=lambda v: v["dev_error"])[:4]
                ],
                "candidate_inventory": [
                    {"name": r["equation_system"]["name"], "dev_error": r["dev_error"]}
                    for r in records
                ],
                "context_policy": "Four lowest-development-loss fitted graphs; every candidate in the score inventory; last eight failures; six evenly spaced source-row examples and complete input ranges. Full records retained locally.",
                "rejections": failures[-8:],
                "rejection_count": len(failures),
                "round": round_id + 1,
                "role_handoffs": role_handoffs,
                "training_ranges": {
                    k: [float(x[k].min()), float(x[k].max())] for k in task["inputs"]
                },
                "description": task.get("description", ""),
                "allowed_units": sorted(UNITS),
            }
            accounting["model_requests"] += 1
            if accounting["model_requests"] > int(limits.get("max_calls", 32)):
                raise ValueError("Model-call limit exhausted")
            log("equation_proposal", round=round_id + 1)
            response = gateway.complete(
                model=roles["coder"],
                system=(
                    "Propose up to two physically motivated connected equation systems as JSON {systems:[...]}. "
                    "Use the exact schema of the templates: version, name, assumptions (list), parameters (mapping of initial,bounds,unit,meaning), "
                    "constants (mapping of value,unit,meaning,source), nodes (ordered list of id,expression,unit,meaning), output (node id). "
                    "Every intermediate must have a defensible scientific interpretation. Use only permitted measurements; never targets or fitted hidden arrays. "
                    "At most 8 shared parameters, 24 nodes. Constants except 0,1,2,3,4,6 must be explicit and sourced. "
                    "Functions: exp,log,log1p,sqrt,abs,sin,cos,tanh,minimum,maximum,where. "
                    "Units are checked; transcendental arguments must be dimensionless. Coefficients fit on train, selection uses dev. "
                    "Revise mechanisms using residuals and failures; do not just rename a polynomial. Declare assumptions, uncertainty and literature priors. "
                    "No test feedback is available. Return no more than two systems and no executable Python."
                ),
                prompt=json.dumps(context, allow_nan=False),
                max_tokens=int(
                    limits.get("equation_proposal_tokens", 4096 if protocol_v2 else 3500)
                ),
                request_id=f"{run_id}--equations--{round_id + 1}",
            )
            try:
                proposals = decode_json(response["text"])["systems"]
                if not isinstance(proposals, list):
                    raise ValueError("systems must be a list")
                for system in proposals[:2]:
                    fit(system, f"Model-proposed equation system, development round {round_id + 1}")
            except (ValueError, KeyError, TypeError) as exc:
                failures.append({"round": round_id + 1, "reason": str(exc)})
            if protocol_v2 and round_id == 0:
                handoff(
                    "critic",
                    "Critique the executed hypotheses. Locate residual regimes, parameter nonidentifiability and unit/domain risks. Recommend one concrete mechanistic revision and one simpler alternative; do not reward complexity by itself.",
                    {
                        "planning": role_handoffs,
                        "candidates": [
                            {
                                "system": r["equation_system"],
                                "diagnostics": diagnostics(r),
                                "dev_error": r["dev_error"],
                                "identifiability": r["identifiability"],
                            }
                            for r in records
                        ],
                        "failures": failures,
                    },
                )
        if protocol_v2:
            handoff(
                "reporter",
                "Write a concise development-only interpretation of the tested competing mechanisms, what the intermediate quantities mean, and what remains unidentified. Distinguish sourced priors from model revisions. Quote only supplied numerical diagnostics; no final-test claims.",
                {
                    "candidates": [
                        {
                            "name": r["equation_system"]["name"],
                            "origin": r["origin"],
                            "train_error": r["train_error"],
                            "dev_error": r["dev_error"],
                            "identifiability": r["identifiability"],
                        }
                        for r in records
                    ],
                    "failures": failures,
                },
            )
    # Preserve every candidate and failure. Nominate distinct structures on dev only.
    ordered = sorted(
        records, key=lambda r: (r["dev_error"], r["simplicity"]["weighted_operator_count"])
    )
    nominated = []
    for r in ordered:
        if not any(
            o["dev_error"] <= r["dev_error"]
            and o["simplicity"]["weighted_operator_count"]
            <= r["simplicity"]["weighted_operator_count"]
            for o in nominated
        ):
            nominated.append(r)
    nominated = nominated[:3]
    model_candidates = [r for r in records if r["origin"].startswith("Model-proposed")]
    conformant = method_id != "equation_agent" or bool(model_candidates)
    if not conformant:
        nominated = []
    accounting["wall_seconds"] = time.monotonic() - start
    accounting["cpu_seconds"] = time.process_time() - cpu_start
    return {
        "status": "incomplete_method_execution"
        if not conformant
        else "complete"
        if nominated
        else "failed",
        "rules": nominated,
        "reason": (
            "No model-proposed equation system passed validation and fitting; seed-template fits remain in the candidate archive"
            if not conformant
            else None
            if nominated
            else "No valid converged equation system"
        ),
        "trace": trace,
        "accounting": accounting,
        "method_evidence": {
            "version": "equation-search-v2" if protocol_v2 else "equation-search-v1",
            "role_handoffs": role_handoffs,
            "candidates": records,
            "failures": failures,
            "selection": "Development error / expanded complexity Pareto portfolio, at most three structures",
            "scope": "Sourced templates and optional model revisions; physical meanings are hypotheses, not causal verification",
        },
    }
