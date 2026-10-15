"""Real train fitting and dev selection, with explicit method-specific control flow."""

from __future__ import annotations

import itertools
import json
import time
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import least_squares

from ..evaluate.metrics import columns, loss, validity
from ..io import sha
from ..methods.registry import DEFAULT_ROLES, MODELS, get_method
from .expression import complexity, execute, parse, structural_key


class Cancelled(RuntimeError):
    pass


@dataclass
class Search:
    task: dict
    train: list
    dev: list
    event: object = lambda *args, **kwargs: None
    stopped: object = lambda: False
    max_fits: int = 1000
    max_structures: int = 8000
    max_seconds: int = 2400
    started: float = field(default_factory=time.monotonic)
    candidates: list = field(default_factory=list)
    failures: list = field(default_factory=list)
    seen: set = field(default_factory=set)
    fits: int = 0
    optimizer_evaluations: int = 0
    capture_failure_diagnostics: bool = False

    def __post_init__(self):
        self.inputs = self.task["inputs"]
        self.X = columns(self.train, self.inputs)
        self.D = columns(self.dev, self.inputs)
        self.y = np.asarray([r[self.task["output"]] for r in self.train], float)
        self.dy = np.asarray([r[self.task["output"]] for r in self.dev], float)
        self.dg = [r["group"] for r in self.dev]
        self.metric = self.task["metric"]["primary"]
        self.scale = max(float(np.std(self.y)), 1e-12)
        self.mean = float(np.mean(self.y))

    def check(self):
        if self.stopped():
            raise Cancelled("Cancelled by user; completed requests remain recorded")
        if time.monotonic() - self.started > self.max_seconds:
            raise TimeoutError("Attempt wall-time limit reached")

    def add(self, expression, parameters=None, *, fit=False, origin="local", max_parameters=8):
        self.check()
        params = dict(parameters or {})
        key = sha([expression, params, fit])
        if key in self.seen:
            if self.capture_failure_diagnostics:
                self.failures.append(
                    {
                        "expression": expression,
                        "origin": origin,
                        "reason": "Duplicate program and initial parameters; no additional fit performed",
                    }
                )
            return
        if len(self.seen) >= self.max_structures or (fit and self.fits >= self.max_fits):
            return
        self.seen.add(key)
        failure_diagnostics = None
        try:
            parse(expression, self.inputs, list(params))
            if fit and len(params) > max_parameters:
                raise ValueError("Parameter budget exceeded")
            if fit and params:
                self.fits += 1
                names = list(params)
                initial = np.asarray([params[k] for k in names], float)

                def residual(p):
                    self.check()
                    self.optimizer_evaluations += 1
                    pred = execute(
                        expression,
                        self.X,
                        dict(zip(names, map(float, p), strict=True)),
                        len(self.train),
                    )
                    if self.metric == "log_mae":
                        r = np.log(np.maximum(pred, 1e-200)) - np.log(self.y)
                    else:
                        r = (pred - self.y) / self.scale
                    return np.nan_to_num(r, nan=1e6, posinf=1e6, neginf=-1e6).clip(-1e6, 1e6)

                opt = least_squares(residual, initial, max_nfev=60)
                params = dict(zip(names, map(float, opt.x), strict=True))
            tp = execute(expression, self.X, params, len(self.train))
            dp = execute(expression, self.D, params, len(self.dev))
            if not validity(tp, self.task).all() or not validity(dp, self.task).all():
                if self.capture_failure_diagnostics:
                    from .evidence import invalid_output_diagnostics

                    failure_diagnostics = invalid_output_diagnostics(self, tp, dp, params)
                raise ValueError("Invalid output in train or development domain")
            score = loss(dp, self.dy, self.metric, self.dg)
            res = dp - self.dy
            correlations = {}
            for k, x in self.D.items():
                if np.issubdtype(x.dtype, np.number) and np.std(x) > 0 and np.std(res) > 0:
                    correlations[k] = float(np.corrcoef(x, res)[0, 1])
            card = {
                "expression": expression,
                "parameters": params,
                "inputs": self.inputs,
                "output": self.task["output"],
                "representation": "expression",
                "origin": origin,
                "dev_error": score,
                "train_error": loss(tp, self.y, self.metric, [r["group"] for r in self.train]),
                "residuals": {
                    "mean": float(np.mean(res)),
                    "std": float(np.std(res)),
                    "p90_abs": float(np.quantile(np.abs(res), 0.9)),
                    "input_correlations": correlations,
                },
                "simplicity": complexity(expression, params),
                "units": {
                    "inputs": self.task.get("input_units", {}),
                    "output": self.task.get("output_units"),
                    "status": "parameter units require scientific review; no dimensionless equivalence claim",
                },
                "parameter_uncertainty": {
                    "status": "not_assessed",
                    "reason": "No independently justified parameter uncertainty model",
                },
                "execution_status": "complete",
            }
            self.candidates.append(card)
            return card
        except (ValueError, TypeError, KeyError, ArithmeticError, SyntaxError) as e:
            failure = {"expression": expression, "origin": origin, "reason": str(e)[:500]}
            if failure_diagnostics is not None:
                failure["diagnostics"] = failure_diagnostics
            self.failures.append(failure)

    def linear(self, terms, origin="linear", max_terms=64):
        self.check()
        if self.fits >= self.max_fits:
            return
        terms = terms[:max_terms]
        self.fits += 1
        try:
            values = [execute(t, self.X, {}, len(self.train)) for t in terms]
            A = np.column_stack([np.ones(len(self.train)), *values])
            if not np.isfinite(A).all():
                raise ValueError("Invalid transform domain")
            # Train-only scaling improves conditioning; coefficients are expanded back to raw terms.
            scale = np.maximum(np.std(A, axis=0), 1e-12)
            scale[0] = 1
            coef = np.linalg.lstsq(A / scale, self.y, rcond=1e-10)[0] / scale
            params = {f"p{i}": float(v) for i, v in enumerate(coef)}
            exp = "p0" + "".join(f"+p{i + 1}*({t})" for i, t in enumerate(terms))
            if self.metric == "brier":
                exp = f"minimum(1,maximum(0,{exp}))"
            return self.add(exp, params, origin=origin)
        except (ValueError, np.linalg.LinAlgError) as e:
            self.failures.append({"terms": terms, "reason": str(e)})

    def grammar(self, extra=(), round_id=0):
        self.event(
            "composition",
            {"round": round_id, "message": "Composing and fitting explicit candidate expressions"},
        )
        numeric = [
            k for k, v in self.X.items() if np.issubdtype(v.dtype, np.number) and np.std(v) > 0
        ]
        terms = list(numeric)
        for x in numeric:
            sd = max(float(np.std(self.X[x])), 1e-12)
            mean = float(np.mean(self.X[x]))
            terms += [
                f"({x})**2",
                f"log1p(abs(({x}-{mean!r})/{sd!r}))",
                f"tanh(({x}-{mean!r})/{sd!r})",
            ]
        for a, b in itertools.combinations(numeric, 2):
            terms.append(f"{a}*{b}")
        for t in extra:
            try:
                parse(t, self.inputs)
                terms.append(t)
            except (ValueError, SyntaxError) as e:
                self.failures.append(
                    {
                        "expression": str(t)[:1000],
                        "reason": str(e),
                        "origin": "rejected_grammar_patch",
                    }
                )
        unique = {}
        for term in terms:
            unique.setdefault(structural_key(term), term)
        terms = list(unique.values())[:180]
        kept = []
        for t in terms:
            c = self.linear([t], origin=f"grammar-round-{round_id}")
            if c:
                kept.append((c["dev_error"], t))
        # Branch over several useful structures instead of relabeling one regressor.
        beam = [t for _, t in sorted(kept)[:12]]
        for a, b in itertools.combinations(beam[:8], 2):
            self.linear([a, b], origin=f"composition-round-{round_id}")
        for n in [3, 5, 7]:
            if len(beam) >= n:
                self.linear(beam[:n], origin=f"beam-round-{round_id}")
        self.event("development_feedback", self.diagnostics())

    def diagnostics(self):
        best = sorted(
            self.candidates,
            key=lambda c: (c["dev_error"], c["simplicity"]["weighted_operator_count"]),
        )[:5]
        return {
            "candidates": len(self.candidates),
            "structures": len(self.seen),
            "fitting_attempts": self.fits,
            "optimizer_evaluations": self.optimizer_evaluations,
            "best": [
                {
                    "expression": c["expression"],
                    "parameters": c["parameters"],
                    "dev_error": c["dev_error"],
                    "residuals": c.get("residuals", {}),
                }
                for c in best
            ],
            "failed_candidates": self.failures[-5:],
            "private_test_feedback": False,
        }

    def portfolio(self, n=3):
        # Selection is final before evaluation; include complexity trade-offs with structural diversity.
        ranked = sorted(
            self.candidates,
            key=lambda c: (c["dev_error"], c["simplicity"]["weighted_operator_count"]),
        )

        def dimensions(c):
            return (
                c["dev_error"],
                c["simplicity"]["weighted_operator_count"],
                c["simplicity"]["free_parameters"],
            )

        frontier = [
            c
            for c in ranked
            if not any(
                all(a <= b for a, b in zip(dimensions(other), dimensions(c), strict=True))
                and any(a < b for a, b in zip(dimensions(other), dimensions(c), strict=True))
                for other in ranked
                if other is not c
            )
        ]
        if n > 1 and frontier:
            simplest = min(
                frontier,
                key=lambda c: (
                    c["simplicity"]["weighted_operator_count"],
                    c["simplicity"]["free_parameters"],
                    c["dev_error"],
                ),
            )
            ranked = [frontier[0], simplest, *frontier, *ranked]
        selected = []
        structures = set()
        for c in ranked:
            structure = (
                sha(c["tree"])
                if c.get("representation") == "tree"
                else structural_key(c["expression"])
            )
            if structure not in structures:
                selected.append(c)
                structures.add(structure)
            if len(selected) >= n:
                break
        return selected


def decode_json(text):
    clean = text.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1].rsplit("```", 1)[0]
    data = json.loads(clean)
    if not isinstance(data, dict):
        raise ValueError("Model response must be a JSON object")
    return data


def execute_method(
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
    spec = get_method(method_id)
    if method_id in {
        "principia_engine_explicit",
        "agent_laboratory_explicit",
        "data_to_paper_explicit",
    }:
        return {
            "status": "unsupported",
            "reason": "Use the dedicated explicit-state development worker via CLI run or the UI; legacy submissions cannot represent its bound state.",
            "rules": [],
            "trace": [],
        }
    if not spec.available:
        return {"status": "unsupported", "reason": spec.reason, "rules": [], "trace": []}
    if spec.needs_llm and gateway is None:
        raise ValueError("This method requires a configured SiliconFlow gateway")
    limits = limits or {}
    roles = roles or DEFAULT_ROLES
    s = Search(
        task,
        train,
        dev,
        event,
        stopped,
        max_fits=limits.get("max_fits", 1000),
        max_seconds=limits.get("wall_seconds", 2400),
    )
    trace = []
    requests = 0
    method_evidence = None

    def stage(name, **detail):
        trace.append({"stage": name, **detail})
        event(name, detail)

    def ask(
        role,
        instruction,
        feedback=None,
        *,
        include_measurements=True,
        knowledge_scope="development_evidence_only",
    ):
        nonlocal requests
        if knowledge_scope not in {"development_evidence_only", "domain_prior"}:
            raise ValueError("Unknown model knowledge scope")
        if knowledge_scope == "domain_prior" and (
            method_id != "asta_autodiscovery" or include_measurements
        ):
            raise ValueError(
                "Domain-prior elicitation requires Asta's measurement-isolated observer"
            )
        s.check()
        if requests >= limits.get("max_calls", 32):
            raise RuntimeError("Model request budget exhausted")
        requests += 1
        model = roles[role]
        stage("model_request", role=role, model=model, request=requests)
        stats = {
            k: {"min": float(np.min(v)), "max": float(np.max(v)), "mean": float(np.mean(v))}
            for k, v in s.X.items()
            if np.issubdtype(v.dtype, np.number)
        }
        context = {
            "task": {
                k: task[k]
                for k in [
                    "task_id",
                    "inputs",
                    "output",
                    "output_units",
                    "input_units",
                    "positive_prediction",
                    "nonnegative_prediction",
                    "title",
                    "observation_window",
                    "metric",
                    "research_objective",
                ]
                if k in task
            },
            "input_statistics_train": stats,
            "target_train": {"mean": s.mean, "std": s.scale},
            "examples_train": [
                {k: r[k] for k in task["inputs"] + [task["output"]]}
                for r in train[:: max(1, len(train) // 6)][:6]
            ],
            "development_feedback": feedback,
            "instruction": instruction,
        }
        if not include_measurements:
            # Asta's hypothesis-only observer must not see the train preview, target
            # statistics or unrelated experiment results before eliciting its prior.
            for key in ("input_statistics_train", "target_train", "examples_train"):
                context.pop(key)
        result = gateway.complete(
            model=model,
            system="You are a scientific rule-discovery "
            + role
            + (
                ". Use prior domain knowledge and the frozen task/formula to express a subjective expectation before execution. This is prior elicitation, not verification of an observed result. Abstain if you cannot form a defensible expectation. Do not invent measured performance."
                if knowledge_scope == "domain_prior"
                else ". Work only from supplied development evidence."
            )
            + " Return a JSON object, no markdown. Allowed expression operators: + - * / ** abs sqrt log log1p exp sin cos tanh minimum maximum where and comparisons. Inputs must exactly match allowed names. Constants and up to 8 free parameters p0..p7 are allowed. Do not invent measurements or claim test validation.",
            prompt=json.dumps(context, allow_nan=False),
            max_tokens=1800,
            request_id=f"{run_id}--{role}--{requests}",
        )
        stage(
            "model_response",
            role=role,
            request_id=result["request_id"],
            usage=result.get("usage", {}),
        )
        return decode_json(result["text"])

    def proposal(p, origin):
        expr = p.get("expression") if isinstance(p, dict) else None
        if not isinstance(expr, str):
            s.failures.append({"origin": origin, "reason": "Proposal missing expression"})
            return None
        params = p.get("parameters", {})
        if not isinstance(params, dict) or any(
            not (k.startswith("p") and k[1:].isdigit()) or not isinstance(v, (int, float))
            for k, v in params.items()
        ):
            s.failures.append(
                {
                    "origin": origin,
                    "expression": expr,
                    "reason": 'Invalid parameter map; use a JSON object such as {"p0": 0, "p1": 1}',
                }
            )
            return None
        stage("experiment", origin=origin, expression=expr)
        return s.add(expr, params, fit=bool(params), origin=origin)

    if method_id == "mean_control":
        s.add("p0", {"p0": s.mean}, origin="training mean")
    elif method_id == "linear_control":
        s.linear(task["inputs"])
    elif method_id == "polynomial_control":
        fields = task["inputs"]
        terms = fields + [f"{a}*{b}" for a, b in itertools.combinations_with_replacement(fields, 2)]
        s.linear(fields, origin="degree-1")
        s.linear(terms, origin="degree-2")
        stage("dev_selection", candidate_count=len(s.candidates))
    elif method_id == "tree_control":
        from sklearn.tree import DecisionTreeRegressor

        best = None
        for depth in [2, 3, 4, 6]:
            s.check()
            model = DecisionTreeRegressor(
                max_depth=depth, min_samples_leaf=max(2, len(train) // 100), random_state=11
            )
            model.fit(np.column_stack(list(s.X.values())), s.y)
            pred = model.predict(np.column_stack(list(s.D.values())))
            score = loss(pred, s.dy, s.metric, s.dg)
            s.fits += 1
            if best is None or score < best[0]:
                best = (score, model)
        tr = best[1].tree_
        n = tr.node_count
        s.candidates = [
            {
                "representation": "tree",
                "expression": "Decision tree; see complete node arrays",
                "parameters": {},
                "inputs": task["inputs"],
                "output": task["output"],
                "dev_error": best[0],
                "tree": {
                    "features": task["inputs"],
                    "feature": tr.feature.tolist(),
                    "threshold": tr.threshold.tolist(),
                    "left": tr.children_left.tolist(),
                    "right": tr.children_right.tolist(),
                    "value": tr.value[:, 0, 0].tolist(),
                },
                "simplicity": {"weighted_operator_count": n, "free_parameters": n},
                "execution_status": "complete",
                "origin": "tree_reference",
            }
        ]
        stage("dev_selection", depth=best[1].max_depth)
    elif method_id == "symbolic_control":
        s.grammar()
        stage("fixed_grammar_executed", fits=s.fits)
    elif method_id == "direct" or method_id.startswith("direct_"):
        if method_id.startswith("direct_"):
            suffix = method_id.split("_", 1)[1]
            roles = dict(roles) | {
                "coder": MODELS[["deepseek", "glm", "qwen", "kimi"].index(suffix)]
            }
        proposal(
            ask(
                "coder",
                'Return ONE compact rule as {"expression": "...", "parameters": {"p0": 1}, "rationale":"..."}. Coefficients will be fitted on train. No later model repair is available.',
            ),
            "single_generation",
        )
    elif method_id == "best_of_n":
        for i in range(3):
            proposal(
                ask(
                    "coder",
                    'Return exactly {"expression":"p0+p1*INPUT", "parameters":{"p0":0,"p1":1}, "rationale":"..."}, replacing INPUT with a permitted expression. Include initial values for every parameter. Return parameters as an object, never an array. Do not access earlier proposals.',
                ),
                f"independent-{i}",
            )
        stage("dev_selection", count=3)
    elif method_id == "feedback_refinement":
        for i in range(3):
            proposal(
                ask(
                    "coder",
                    'Return a revised rule using supplied diagnostics as {"expression":"...", "parameters":{"p0":0,"p1":1}, "rationale":"..."}. Include initial values for every parameter; use an object, never an array.',
                    s.diagnostics() if i else None,
                ),
                f"revision-{i}",
            )
        stage("feedback_iterations", count=3)
    elif method_id == "tool_agent":
        tool_result = None
        for step in range(6):
            p = ask(
                "coder",
                'Choose one host action: {"action":"inspect", "offset":0} for a page of train measurements and statistics, {"action":"fit", "expression":"p0+p1*INPUT", "parameters":{"p0":0,"p1":1}} for a fit (replace INPUT and list EVERY parameter), {"action":"search", "terms":["..."]} for local composition/fitting, or {"action":"finish"} after a successful experiment. Read last_tool_result. Repeating an identical inspect yields no new evidence; execute fit or search to investigate a hypothesis. There are at most six actions.',
                s.diagnostics() | {"last_tool_result": tool_result, "actions_remaining": 6 - step},
            )
            action = p.get("action")
            stage("tool_action", action=action)
            if action == "fit":
                fitted = proposal(p, f"tool-{step}")
                tool_result = {
                    "action": "fit",
                    "success": fitted is not None,
                    "diagnostics": s.diagnostics(),
                }
            elif action == "search":
                s.grammar(p.get("terms", [])[:8], step)
                tool_result = {"action": "search", "diagnostics": s.diagnostics()}
            elif action == "inspect":
                offset = p.get("offset", 0)
                if not isinstance(offset, int) or not 0 <= offset < len(train):
                    tool_result = {
                        "action": "inspect",
                        "error": "offset must index a training observation",
                    }
                    continue
                tool_result = {
                    "action": "inspect",
                    "offset": offset,
                    "next_offset": offset + 24 if offset + 24 < len(train) else None,
                    "total_rows": len(train),
                    "rows": [
                        {k: r[k] for k in task["inputs"] + [task["output"]]}
                        for r in train[offset : offset + 24]
                    ],
                    "train_target_correlations": {
                        k: float(np.corrcoef(x, s.y)[0, 1])
                        for k, x in s.X.items()
                        if np.std(x) > 0 and np.std(s.y) > 0
                    },
                }
                stage(
                    "measurement_inventory",
                    inputs=task["inputs"],
                    rows=len(train),
                    offset=offset,
                    returned_rows=len(tool_result["rows"]),
                )
            elif action == "finish" and s.candidates:
                break
            else:
                s.failures.append(
                    {"action": action, "reason": "Unsupported action or no successful experiment"}
                )
    elif method_id == "agent_laboratory":
        from .laboratory import run_laboratory

        method_evidence = run_laboratory(s, ask, proposal, stage, roles)
    elif method_id == "data_to_paper":
        from .data_to_paper import run_data_to_paper

        method_evidence = run_data_to_paper(s, ask, proposal, stage, roles)
    elif method_id == "asta_autodiscovery":
        from .asta import run_asta

        method_evidence = run_asta(s, ask, proposal, stage, roles)
    elif method_id == "agentrxiv":
        from .agentrxiv import run_agentrxiv

        method_evidence = run_agentrxiv(s, ask, proposal, stage, roles)
    elif method_id == "principia_engine":
        library = []
        for round_id in range(2):
            drafter = "planner" if round_id == 0 else "coder"
            p = ask(
                drafter,
                'Propose a compact hypothesis-space patch: {"kernels":[{"expression":"input expression with NO free parameters", "meaning":"scientific role"}], "rules":[{"expression":"p0+p1*input", "parameters":{"p0":0,"p1":1}}], "rationale":"..."}. Up to 8 kernels and 3 rules. Revise structure from residual diagnostics, including failures.',
                s.diagnostics() if round_id else None,
            )
            fresh = []
            for k in p.get("kernels", [])[:8]:
                try:
                    parse(k["expression"], task["inputs"])
                    fresh.append(k["expression"])
                    library.append(
                        {
                            "expression": k["expression"],
                            "meaning": k.get("meaning", ""),
                            "round": round_id,
                            "model": roles[drafter],
                            "source": "live model proposal",
                        }
                    )
                except (KeyError, ValueError, SyntaxError) as e:
                    s.failures.append({"kernel": str(k)[:1000], "reason": str(e)})
            for rule in p.get("rules", [])[:3]:
                proposal(rule, f"engine-round-{round_id}")
            s.grammar(fresh, round_id)
            stage(
                "library_revision",
                round=round_id,
                retained_kernels=len(library),
                diagnostics=s.diagnostics(),
            )
            if round_id == 0:
                critique = ask(
                    "critic",
                    'Critique the development evidence; return {"limitations":[], "suggested_terms":["input-only expression"]}. Do not claim mechanism from predictive fit.',
                    s.diagnostics(),
                )
                for term in critique.get("suggested_terms", [])[:4]:
                    try:
                        parse(term, task["inputs"])
                        library.append(
                            {
                                "expression": term,
                                "meaning": "critic patch",
                                "round": round_id,
                                "model": roles["critic"],
                            }
                        )
                    except (ValueError, SyntaxError):
                        pass
                s.grammar([k["expression"] for k in library[-8:]], round_id + 1)
        report = ask(
            "reporter",
            'Return {"summary":"evidence-linked development findings", "limitations":[], "next_tests":[]}. State predictive evidence and limits; no novelty assertion.',
            s.diagnostics(),
        )
        stage("development_report", report=report, kernel_library=library[:24])
    else:
        raise ValueError("No executable implementation")
    selected = s.portfolio(
        1
        if method_id in {"mean_control", "linear_control", "polynomial_control", "tree_control"}
        or method_id.startswith("direct")
        else 3
    )
    status = "complete" if selected else "failed"
    reason = None if selected else "No valid candidate survived train/dev checks"
    if method_evidence and method_evidence["conformance"]["status"] != "complete":
        status = "incomplete_method_execution"
        reason = "The adaptation did not pass every required algorithm and evidence guard"
        selected = []
    for i, c in enumerate(selected):
        c.update(
            rule_id=f"{run_id}-rule-{i + 1}",
            task_id=task["task_id"],
            method_id=method_id,
            method_version=spec.version,
            model_ids=sorted({x["model"] for x in trace if x["stage"] == "model_request"}),
            execution_status="complete",
            scientific_review="not_assessed",
        )
    return {
        "status": status,
        "reason": reason,
        "rules": selected,
        "trace": trace,
        "failed_candidates": s.failures,
        "accounting": {
            "structures": len(s.seen),
            "fitting_attempts": s.fits,
            "optimizer_evaluations": s.optimizer_evaluations,
            "model_calls": requests,
            "wall_seconds": time.monotonic() - s.started,
        },
        "diagnostics": s.diagnostics(),
        **({"method_evidence": method_evidence} if method_evidence else {}),
    }
