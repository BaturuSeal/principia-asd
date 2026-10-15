"""Versioned host fitting path for explicit state; not a replacement v5 method.

The model-facing interface accepts structures and existing host references only.
All final parameters are fitted on train. Promotion retains their source identity.
"""

from __future__ import annotations

import ast
import copy
import time

import numpy as np
import scipy
from scipy.optimize import least_squares

from ..evaluate.metrics import columns, loss, validity
from ..io import sha
from .bindings import POLICY, StateRegistry, compile_program, execute_program

HOST_POLICY = "host-search-explicit-state-v1-dev"


class BoundSearch:
    """Small, train/dev-only integration API, with no provider or filesystem access."""

    def __init__(
        self,
        task,
        train,
        dev,
        *,
        max_fits=16,
        max_structures=8000,
        max_optimizer_evaluations=4096,
        max_seconds=2400,
        stopped=lambda: False,
    ):
        from ..runtime import train_contract, validate_data

        validate_data(train, task)
        validate_data(dev, task)
        if task["output"] in task["inputs"]:
            raise ValueError("Output cannot be an input")
        for key in ["sample_id", "group"]:
            if {r[key] for r in train} & {r[key] for r in dev}:
                raise ValueError("Train/dev identity or group leakage")
        if any(
            type(v) is not int or v < 1
            for v in [max_fits, max_structures, max_optimizer_evaluations, max_seconds]
        ):
            raise ValueError("Positive integer resource limits required")
        self.task = train_contract(copy.deepcopy(task), train)
        self.train, self.dev = copy.deepcopy(train), copy.deepcopy(dev)
        self.inputs = list(task["inputs"])
        self.X, self.D = columns(self.train, self.inputs), columns(self.dev, self.inputs)
        self.y = np.asarray([r[task["output"]] for r in self.train], float)
        self.dy = np.asarray([r[task["output"]] for r in self.dev], float)
        self.context = {
            "task_sha256": sha(self.task),
            "train_sha256": sha(self.train),
            "dev_sha256": sha(self.dev),
        }
        self.limits = dict(
            max_fits=max_fits,
            max_structures=max_structures,
            max_optimizer_evaluations=max_optimizer_evaluations,
            max_seconds=max_seconds,
        )
        self.registry = StateRegistry({})
        self.candidates, self.failures, self.seen = {}, [], set()
        self.fits = self.optimizer_evaluations = self.duplicate_requests = 0
        self.started, self.stopped, self.closed = time.monotonic(), stopped, False
        self.cpu_started = time.process_time()
        self._frozen = None
        self.constants = self._register(
            {
                "kind": "fixed_scientific",
                "scope": "fixed",
                "status": "complete",
                "policy": HOST_POLICY,
                "operation": "structural_constant_inventory_v1",
                "values": {"zero": 0.0, "one": 1.0, "two": 2.0},
                "meaning": "Arithmetic identities, squared terms and binary probability bounds",
            }
        )

    def _check(self):
        if self.closed:
            raise ValueError("Inquiry is frozen; assessment cannot revise this epoch")
        if self.stopped():
            raise InterruptedError("Cancelled; completed fits are retained")
        if time.monotonic() - self.started > self.limits["max_seconds"]:
            raise TimeoutError("Host search wall-time limit reached")

    def _register(self, artifact):
        digest = sha(artifact)
        self.registry.artifacts[digest] = copy.deepcopy(artifact)
        return {
            k: self.registry.register(digest, ["values", k], artifact["kind"])
            for k in artifact["values"]
        }

    def normalization(self, input_name):
        """Compute input statistics from train only; no externally supplied values."""
        self._check()
        x = self.X[input_name]
        mean, std = float(np.mean(x)), float(np.std(x))
        if not np.isfinite([mean, std]).all() or std <= 0:
            raise ValueError("Normalization requires finite, nonconstant train measurements")
        return self._register(
            {
                "kind": "train_statistic",
                "scope": "train",
                "status": "complete",
                "policy": HOST_POLICY,
                "operation": "numpy_mean_std_ddof0",
                "train_sha256": self.context["train_sha256"],
                "input": input_name,
                "rows": len(x),
                "numpy_version": np.__version__,
                "values": {"center": mean, "scale": std},
            }
        )

    def fit(self, expression, initial=None, *, bindings=None, kernels=None):
        """Fit every supplied pN; reject unbound literals before any optimizer call."""
        self._check()
        initial, bindings, kernels = dict(initial or {}), dict(bindings or {}), dict(kernels or {})
        request = {
            "expression": expression,
            "initial": initial,
            "bindings": bindings,
            "kernels": kernels,
        }
        key = sha(request)
        if key in self.seen:
            self.duplicate_requests += 1
            return None
        if len(self.seen) >= self.limits["max_structures"]:
            raise RuntimeError("Structure budget reached")
        self.seen.add(key)
        before = self.optimizer_evaluations
        try:
            template = compile_program(
                expression, self.inputs, initial, bindings, self.registry, kernels=kernels
            )
            params = template["specification"]["parameters"]
            opt = None
            if params:
                if self.fits >= self.limits["max_fits"]:
                    raise RuntimeError("Fitting budget reached")
                self.fits += 1
                names = list(params)

                def residual(values):
                    self._check()
                    if self.optimizer_evaluations >= self.limits["max_optimizer_evaluations"]:
                        raise RuntimeError("Optimizer evaluation budget reached")
                    self.optimizer_evaluations += 1
                    program = compile_program(
                        expression,
                        self.inputs,
                        dict(zip(names, map(float, values), strict=True)),
                        bindings,
                        self.registry,
                        kernels=kernels,
                    )
                    pred = execute_program(program, self.X, self.registry)
                    if not np.isfinite(pred).all():
                        raise ValueError("Nonfinite training domain during fitting")
                    if self.task["metric"]["primary"] == "log_mae":
                        if np.any(pred <= 0) or np.any(self.y <= 0):
                            raise ValueError(
                                "Log fitting requires positive predictions and targets"
                            )
                        return np.log(pred) - np.log(self.y)
                    return (pred - self.y) / max(float(np.std(self.y)), 1e-12)

                opt = least_squares(residual, list(params.values()), max_nfev=60)
                if not opt.success:
                    raise ValueError("Optimizer did not converge; failed attempt retained")
                params = dict(zip(names, map(float, opt.x), strict=True))
            program = compile_program(
                expression, self.inputs, params, bindings, self.registry, kernels=kernels
            )
            tp, dp = (execute_program(program, x, self.registry) for x in [self.X, self.D])
            if not validity(tp, self.task).all() or not validity(dp, self.task).all():
                raise ValueError("Invalid train or dev output; no candidate retained")
            fit_source = None
            if params:
                source = {
                    "kind": "train_fitted",
                    "scope": "train",
                    "status": "complete",
                    "policy": HOST_POLICY,
                    "operation": "scipy_least_squares_trf",
                    "train_sha256": self.context["train_sha256"],
                    "task_sha256": self.context["task_sha256"],
                    "request_sha256": key,
                    "template_sha256": template["sha256"],
                    "program_sha256": program["sha256"],
                    "initial": initial,
                    "values": params,
                    "optimizer_status": int(opt.status),
                    "optimizer_evaluations": self.optimizer_evaluations - before,
                    "objective": "train log squared residuals"
                    if self.task["metric"]["primary"] == "log_mae"
                    else "train squared residuals standardized by train target std",
                    "folds": 1,
                    "restarts": 0,
                    "max_nfev": 60,
                    "scipy_version": scipy.__version__,
                    "numpy_version": np.__version__,
                }
                self._register(source)
                fit_source = sha(source)
            residuals = dp - self.dy
            card = {
                "representation": "bound_expression_v1",
                "policy": HOST_POLICY,
                "program": program,
                "final_fit_source": fit_source,
                "expression": program["expression"],
                "inputs": self.inputs,
                "output": self.task["output"],
                "simplicity": program["simplicity"],
                "train_error": loss(
                    tp, self.y, self.task["metric"]["primary"], [r["group"] for r in self.train]
                ),
                "dev_error": loss(
                    dp, self.dy, self.task["metric"]["primary"], [r["group"] for r in self.dev]
                ),
                "residuals": {"mean": float(np.mean(residuals)), "std": float(np.std(residuals))},
                "parameter_uncertainty": "not_assessed",
                "execution_status": "complete",
                "context": self.context,
            }
            digest = sha(card)
            card["candidate_id"] = digest
            self.candidates[digest] = copy.deepcopy(card)
            return copy.deepcopy(card)
        except (InterruptedError, TimeoutError) as e:
            self.failures.append(
                {
                    "request": request,
                    "reason": str(e),
                    "optimizer_evaluations": self.optimizer_evaluations - before,
                }
            )
            raise
        except (ValueError, TypeError, KeyError, SyntaxError, ArithmeticError, RuntimeError) as e:
            self.failures.append(
                {
                    "request": request,
                    "reason": str(e)[:500],
                    "optimizer_evaluations": self.optimizer_evaluations - before,
                }
            )
            return None

    def promote(self, candidate_id):
        """Return an input/state-only kernel; never serialize fitted values as literals."""
        self._check()
        card = self.candidates[candidate_id]
        program = card["program"]
        refs = {f"bound{i}": digest for i, digest in enumerate(sorted(program["states"]))}
        source = card["final_fit_source"]
        for name in program["specification"]["parameters"]:
            refs[name] = self.registry.register(source, ["values", name], "train_fitted")
        names = {symbol: f"state_{digest}" for symbol, digest in refs.items()}

        class Rename(ast.NodeTransformer):
            def visit_Name(self, node):
                return (
                    ast.copy_location(ast.Name(id=names[node.id], ctx=ast.Load()), node)
                    if node.id in names
                    else node
                )

        expression = ast.unparse(Rename().visit(ast.parse(program["expression"], mode="eval")))
        bindings = {names[name]: digest for name, digest in refs.items()}
        compile_program(expression, self.inputs, {}, bindings, self.registry)
        return {"expression": expression, "bindings": bindings, "source_candidate": candidate_id}

    def freeze(self):
        """Freeze the complete candidate set, including failures; no test access."""
        if self._frozen is None:
            self.closed = True
            record = {
                "policy": HOST_POLICY,
                "binding_policy": POLICY,
                "context": self.context,
                "task": self.task,
                "limits": self.limits,
                "source_artifacts": self.registry.artifacts,
                "candidates": list(self.candidates.values()),
                "failures": self.failures,
                "accounting": {
                    "structures": len(self.seen),
                    "fitting_attempts": self.fits,
                    "optimizer_evaluations": self.optimizer_evaluations,
                    "duplicate_requests": self.duplicate_requests,
                    "cpu_seconds": time.process_time() - self.cpu_started,
                    "cpu_scope": "current process; run in a dedicated bounded worker",
                    "wall_seconds": time.monotonic() - self.started,
                    "api_calls": 0,
                },
                "ranking_authorized": False,
                "scope": "development host integration",
            }
            record["sha256"] = sha(record)
            self._frozen = copy.deepcopy(record)
        return copy.deepcopy(self._frozen)
