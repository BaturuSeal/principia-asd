"""Fixed development controls using the Engine's explicit-state numerical host.

These are new protocols, not replacements for the historical controls. They have
no provider interface or test access. Public ranking and product-worker admission
require a separately frozen, symmetric comparison.
"""

from __future__ import annotations

import copy
import re
from functools import partial

from ..io import sha
from .bound_engine import SELECTION_POLICY, development_selection
from .bound_search import HOST_POLICY, BoundSearch

POLICY = "fixed-controls-explicit-state-v1-dev"
CONTROLS = ("fitted_constant", "affine", "quadratic", "fixed_symbolic")
MAXIMUM = {
    "max_fits": 16,
    "max_structures": 8000,
    "max_optimizer_evaluations": 4096,
    "max_seconds": 2400,
}


def fixed_plan(control, inputs):
    """Return the complete grammar before looking at train/dev measurements.

    Terms contain input indices, not hidden fitted values. Affine/quadratic
    controls always use the full basis; an oversized basis is unsupported.
    """
    if control not in CONTROLS:
        raise ValueError("Unknown explicit-state control")
    if not 1 <= len(inputs) <= 8:
        return [], "Development controls support one to eight inputs; none were dropped"

    def candidate(name, terms):
        return {"name": name, "terms": terms, "free_parameters": 1 + len(terms)}

    constant = candidate("fitted_constant", [])
    identity = [["identity", i] for i in range(len(inputs))]
    if control == "fitted_constant":
        return [constant], None
    if control == "affine":
        if 1 + len(inputs) > 8:
            return [], "Full affine basis exceeds the eight fitted-parameter limit"
        return [candidate("full_affine", identity)], None
    if control == "quadratic":
        pairs = [["product", i, j] for i in range(len(inputs)) for j in range(i, len(inputs))]
        if 1 + len(identity) + len(pairs) > 8:
            return [], "Full degree-two basis exceeds the eight fitted-parameter limit"
        return [candidate("full_quadratic", identity + pairs)], None
    # Predeclared ordering, with complete plan and capacity exclusions disclosed.
    # Every input's identity term precedes the first nonlinear univariate term.
    plan = [constant]
    if 2 <= len(inputs) <= 7:
        plan.append(candidate("full_affine", identity))
    for transform in ("identity", "square", "tanh", "abs"):
        for i in range(len(inputs)):
            plan.append(candidate(f"{transform}_input_{i}", [[transform, i]]))
    return plan, None


class BoundControl:
    """One fixed search pass, then three frozen development nomination slots.

    Uses the same solver, loss, scalar binding and selector as BoundEngine. Its
    numerical envelope is a ceiling, not a claim of equal actual compute. This
    in-process API is not an OS sandbox or an RSS limiter. Use dedicated-process
    resource controls before admission to a real comparison.
    """

    policy = POLICY

    def __init__(
        self,
        task,
        train,
        dev,
        *,
        control,
        run_id,
        limits=None,
        stopped=lambda: False,
        event=lambda *args: None,
        step=None,
    ):
        if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", run_id):
            raise ValueError("A stable explicit run identity is required")
        cfg = dict(MAXIMUM)
        if limits is not None and (not isinstance(limits, dict) or set(limits) - set(cfg)):
            raise ValueError("Unknown control resource limit")
        cfg.update(limits or {})
        if any(type(v) is not int or not 1 <= v <= MAXIMUM[k] for k, v in cfg.items()):
            raise ValueError("Control limit exceeds the shared numerical envelope")
        plan, unsupported = fixed_plan(control, task["inputs"])
        self.host = BoundSearch(task, train, dev, stopped=stopped, **cfg)
        self.run_id, self.limits = run_id, cfg
        self.event, self.stopped = event, stopped
        self.step = step or (lambda name, kind, action: action())
        # Fields shared by the append-only host journal; no provider is constructed.
        self.gateway, self.requests, self.result = None, 0, None
        self.kernels, self.references, self.kernel_sources = {}, {}, {}
        self.trace, self.rejections, self.rounds = [], [], []
        bound = min(len(plan), cfg["max_fits"], cfg["max_structures"])
        self.configuration = {
            "policy": POLICY,
            "control": control,
            "host_policy": HOST_POLICY,
            "host_context": self.host.context,
            "limits": cfg,
            "max_model_requests": 0,
            "nomination_slots": 3,
            "selection_policy": SELECTION_POLICY,
            "initialization": "p0=1, all slope coefficients=0; fixed before measurements",
            "preprocessing": "train-only mean/std ddof=0, expanded and state-counted",
            "fitting_objective": "same BoundSearch standardized squared residuals; log residuals for log_mae",
            "plan": plan,
            "scheduled_plan": plan[:bound],
            "capacity_excluded_plan": plan[bound:],
            "unsupported_reason": unsupported,
            "ranking_authorized": False,
        }
        self.configuration["sha256"] = sha(self.configuration)

    def _stage(self, stage, **detail):
        record = {"stage": stage, **copy.deepcopy(detail)}
        self.trace.append(record)
        self.event(stage, copy.deepcopy(detail))

    def _initialize(self):
        self.host._check()
        indices = sorted(
            {
                i
                for spec in self.configuration["scheduled_plan"]
                for term in spec["terms"]
                for i in term[1:]
            }
        )
        for i in indices:
            name = self.host.inputs[i]
            try:
                refs = self.host.normalization(name)
            except ValueError as exc:
                self.rejections.append(
                    {"stage": "normalization", "input": name, "reason": str(exc)}
                )
                continue
            for digest in refs.values():
                alias = f"state_{digest}"
                if alias in self.host.inputs:
                    raise ValueError("Input collides with explicit-state reference namespace")
                self.references[alias] = digest
            self.kernels[f"z{i}"] = f"({name}-state_{refs['center']})/state_{refs['scale']}"
            self.kernel_sources[f"z{i}"] = {"input": name, "kind": "host_train_normalization"}
        self._stage("fixed_plan_initialized", scheduled=len(self.configuration["scheduled_plan"]))

    def _experiment(self, spec):
        self.host._check()
        indices = sorted({i for term in spec["terms"] for i in term[1:]})
        missing = [self.host.inputs[i] for i in indices if f"z{i}" not in self.kernels]
        if missing:
            outcome = {
                "name": spec["name"],
                "status": "rejected",
                "reason": "Unavailable train normalization",
                "inputs": missing,
            }
            self.rejections.append(outcome)
        elif self.host.optimizer_evaluations >= self.limits["max_optimizer_evaluations"]:
            outcome = {
                "name": spec["name"],
                "status": "budget_exhausted",
                "reason": "Shared optimizer evaluation cap",
            }
        else:
            terms = []
            for term in spec["terms"]:
                transform, i, *rest = term
                z = f"({self.kernels[f'z{i}']})"
                terms.append(
                    f"({z}*({self.kernels[f'z{rest[0]}']}))"
                    if transform == "product"
                    else f"({z}*{z})"
                    if transform == "square"
                    else f"{transform}({z})"
                    if transform in ("tanh", "abs")
                    else z
                )
            expression = "p0" + "".join(f"+p{i + 1}*({term})" for i, term in enumerate(terms))
            bindings = {
                name: value for name, value in self.references.items() if name in expression
            }
            initial = {f"p{i}": 1.0 if i == 0 else 0.0 for i in range(spec["free_parameters"])}
            card = self.host.fit(expression, initial, bindings=bindings)
            outcome = {
                "name": spec["name"],
                "status": "complete"
                if card
                else (
                    "budget_exhausted"
                    if self.host.optimizer_evaluations >= self.limits["max_optimizer_evaluations"]
                    else "failed"
                ),
                "candidate_id": card["candidate_id"] if card else None,
                "fitting_attempts": self.host.fits,
                "optimizer_evaluations": self.host.optimizer_evaluations,
            }
        self.rounds.append(copy.deepcopy(outcome))
        self._stage("fixed_experiment", **outcome)
        return outcome

    def _nominate(self):
        selection = development_selection(self.host.candidates.values())
        frozen = self.host.freeze()
        nomination = {
            "host_sha256": frozen["sha256"],
            "selection": copy.deepcopy(selection),
            "configuration_sha256": self.configuration["sha256"],
        }
        nomination["sha256"] = sha(nomination)
        self._stage("submission_frozen", nomination_freeze=nomination)
        return {"selection": selection, "nomination_freeze": nomination}

    def run(self):
        if self.result is not None:
            return copy.deepcopy(self.result)
        failure = None
        try:
            self.step("initialize", "local", self._initialize)
            for i, spec in enumerate(self.configuration["scheduled_plan"]):
                self.step(f"fixed-experiment-{i}", "local", partial(self._experiment, spec))
        except Exception as exc:
            if getattr(exc, "recovery_required", False):
                raise
            failure = {
                "type": getattr(exc, "original_type", type(exc).__name__),
                "reason": str(exc)[:300],
            }
            self._stage("stopped", **failure)
        nominated = self.step("nominate", "local", self._nominate)
        complete = len(self.rounds) == len(self.configuration["scheduled_plan"]) and all(
            r["status"] in {"complete", "failed"} for r in self.rounds
        )
        status = (
            "failed"
            if failure
            else "unsupported"
            if self.configuration["unsupported_reason"]
            else "incomplete_method_execution"
            if not complete
            else "complete"
            if self.host.candidates
            else "failed"
        )
        self.result = {
            "policy": POLICY,
            "status": status,
            "configuration": self.configuration,
            "host_submission": self.host.freeze(),
            **nominated,
            "conformance": {
                "scheduled_plan_executed": complete,
                "fixed_grammar": True,
                "provider_requests": 0,
            },
            "model_requests": 0,
            "trace": copy.deepcopy(self.trace),
            "rejections": copy.deepcopy(self.rejections),
            "experiments": copy.deepcopy(self.rounds),
            "failure": failure,
            "ranking_authorized": False,
            "scientific_review": "not_assessed",
        }
        self.result["sha256"] = sha(self.result)
        return copy.deepcopy(self.result)
