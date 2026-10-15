"""Opt-in model protocol over host-owned explicit state; never replaces v5.

Development API only: a dedicated durable worker and a new pilot freeze are
required before enabling this method in the product or public comparisons.
"""

from __future__ import annotations

import ast
import copy
import json
import re
import time
from functools import partial

from ..io import sha
from ..methods.registry import DEFAULT_ROLES, MODELS
from .bindings import compile_program
from .bound_search import BoundSearch
from .expression import structural_key

POLICY = "principia-explicit-state-protocol-v1-dev"
SELECTION_POLICY = "dev-loss-expanded-operations-learned-scalars-v1-dev"


def development_selection(candidates, slots=3):
    """Retain a fixed slot denominator; select only on executed dev diagnostics."""
    if type(slots) is not int or not 1 <= slots <= 3:
        raise ValueError("One to three predeclared nomination slots required")
    cards = list(candidates)
    if any(c.get("representation") != "bound_expression_v1" for c in cards):
        raise ValueError("Cannot mix legacy and explicit-state selection policies")

    def dimensions(c):
        return (
            c["dev_error"],
            c["simplicity"]["weighted_operator_count"],
            c["simplicity"]["learned_scalar_count"],
        )

    # Repeated fits of one structure do not create additional nominations.
    structures = {}
    for c in sorted(cards, key=lambda c: (*dimensions(c), c["candidate_id"])):
        tree = ast.parse(c["program"]["expression"], mode="eval")
        states = {f"bound{i}": s for i, s in enumerate(sorted(c["program"]["states"]))}
        names = {}

        class StateKind(ast.NodeTransformer):
            def visit_Name(self, node, states=states, names=names, card=c):
                if node.id not in states:
                    return node
                if node.id not in names:
                    state = card["program"]["states"][states[node.id]]
                    kind = state["kind"]
                    names[node.id] = (
                        f"fixed_{sha(state['value'])}"
                        if kind == "fixed_scientific"
                        else f"{kind}_{len(names)}"
                    )
                return ast.copy_location(ast.Name(id=names[node.id], ctx=ast.Load()), node)

        key = structural_key(ast.unparse(StateKind().visit(tree)))
        structures.setdefault(key, c)
    ranked = list(structures.values())
    frontier = [
        c
        for c in ranked
        if not any(
            all(a <= b for a, b in zip(dimensions(o), dimensions(c), strict=True))
            and any(a < b for a, b in zip(dimensions(o), dimensions(c), strict=True))
            for o in ranked
            if o is not c
        )
    ]
    ordering = frontier + [c for c in ranked if c not in frontier]
    selected = ordering[:slots]
    return {
        "policy": SELECTION_POLICY,
        "slots": slots,
        "selection_scope": "train/dev only",
        "dimensions": ["dev_error", "expanded_weighted_operator_count", "learned_scalar_count"],
        "all_candidate_count": len(cards),
        "distinct_structure_count": len(ranked),
        "frontier_ids": [c["candidate_id"] for c in frontier],
        "nominations": [
            {
                "slot": i + 1,
                "candidate_id": selected[i]["candidate_id"] if i < len(selected) else None,
                "status": "nominated" if i < len(selected) else "unfilled",
            }
            for i in range(slots)
        ],
        "ranking_authorized": False,
    }


class BoundEngine:
    """Two complete planner/coder/critic cycles, then an evidence-linked report."""

    policy = POLICY
    request_tag = "bound-v1"

    def __init__(
        self,
        task,
        train,
        dev,
        *,
        gateway,
        run_id,
        roles=None,
        limits=None,
        stopped=lambda: False,
        event=lambda *args: None,
        step=None,
    ):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", run_id):
            raise ValueError("A stable explicit run identity is required")
        roles = copy.deepcopy(DEFAULT_ROLES if roles is None else roles)
        if set(roles) != set(DEFAULT_ROLES) or any(v not in MODELS for v in roles.values()):
            raise ValueError("Exact configured model IDs for all four roles required; no fallback")
        cfg = {
            "max_calls": 7,
            "max_fits": 16,
            "max_structures": 8000,
            "max_optimizer_evaluations": 4096,
            "max_seconds": 2400,
        }
        if limits and set(limits) - set(cfg):
            raise ValueError("Unknown resource limit")
        cfg.update(limits or {})
        if type(cfg["max_calls"]) is not int or not 1 <= cfg["max_calls"] <= 32:
            raise ValueError("Model request cap must be in 1..32")
        if not 1 <= len(task["inputs"]) <= 8:
            raise ValueError("Development protocol supports one to eight numeric inputs")
        self.host = BoundSearch(
            task, train, dev, stopped=stopped, **{k: v for k, v in cfg.items() if k != "max_calls"}
        )
        self.gateway, self.run_id, self.roles, self.limits = gateway, run_id, roles, cfg
        self.event, self.stopped = event, stopped
        self.step = step or (lambda name, kind, action: action())
        self.kernels, self.references, self.kernel_sources = {}, {}, {}
        self.trace, self.rejections, self.rounds = [], [], []
        self.requests, self.result = 0, None
        self.configuration = {
            "policy": self.policy,
            "roles": roles,
            "limits": cfg,
            "rounds": 2,
            "nomination_slots": 3,
            "max_tokens": 1800,
            "weak_prior_fits": 2,
            "local_compositions_per_round": 2,
            "temperature": 0.25,
            "host_context": self.host.context,
            "selection_policy": SELECTION_POLICY,
        }
        self.configuration["sha256"] = sha(self.configuration)

    def _stage(self, stage, **detail):
        record = {"stage": stage, **copy.deepcopy(detail)}
        self.trace.append(record)
        self.event(stage, copy.deepcopy(detail))

    def _register_references(self, refs):
        for digest in refs.values():
            self.host.registry.resolve(digest)
            self.references[f"state_{digest}"] = digest

    def _bindings(self, expression, kernels=None):
        kernels = self.kernels if kernels is None else kernels
        used, visited_nodes = set(), 0

        def visit(text, stack=()):
            nonlocal visited_nodes
            if not isinstance(text, str) or len(text) > 12000 or len(stack) > 24:
                raise ValueError("Kernel expansion limit")
            for node in ast.walk(ast.parse(text, mode="eval")):
                visited_nodes += 1
                if visited_nodes > 800:
                    raise ValueError("Kernel dependency expansion limit")
                if isinstance(node, ast.Name):
                    if node.id in kernels:
                        if node.id in stack:
                            raise ValueError("Recursive kernel")
                        visit(kernels[node.id], (*stack, node.id))
                    elif node.id in self.references:
                        used.add(node.id)

        visit(expression)
        return {name: self.references[name] for name in sorted(used)}

    def _inventory(self):
        return {
            "inputs": self.host.inputs,
            "states": {
                name: self.host.registry.resolve(digest) for name, digest in self.references.items()
            },
            "kernels": [
                {"name": name, "expression": expr, "lineage": self.kernel_sources[name]}
                for name, expr in sorted(self.kernels.items())
            ],
        }

    def _initialize(self):
        self._register_references(self.host.constants)
        for i, name in enumerate(self.host.inputs):
            try:
                refs = self.host.normalization(name)
            except ValueError as e:
                self.rejections.append({"stage": "normalization", "input": name, "reason": str(e)})
                continue
            self._register_references(refs)
            key = f"normalized_{i}"
            if key in self.host.inputs:
                raise ValueError("Input collides with protocol primitive namespace")
            self.kernels[key] = f"({name}-state_{refs['center']})/state_{refs['scale']}"
            self.kernel_sources[key] = {"kind": "host_train_normalization", "input": name}
        # A fixed weak-prior allocation, never selected using test evidence.
        self.host.fit("p0", {"p0": 0})
        self.host.fit(f"p0+p1*{self.host.inputs[0]}", {"p0": 0, "p1": 1})
        self._stage(
            "weak_prior_fits", candidates=len(self.host.candidates), fitting_attempts=self.host.fits
        )

    def _feedback(self):
        selected = development_selection(self.host.candidates.values())
        ids = [r["candidate_id"] for r in selected["nominations"] if r["candidate_id"]]
        return {
            "selection": selected,
            "candidates": [self.host.candidates[k] for k in ids],
            "failures": copy.deepcopy(self.host.failures),
            "rejected_patches": self.rejections,
            "fitting_attempts": self.host.fits,
            "optimizer_evaluations": self.host.optimizer_evaluations,
            "earlier_round_critiques": copy.deepcopy(self.rounds),
            "test_feedback_available": False,
        }

    def _context(self, role, instruction, *, frozen=None):
        task = {
            k: self.host.task[k]
            for k in ["inputs", "output", "input_units", "output_units", "metric", "title"]
            if k in self.host.task
        }
        context = {
            "policy": self.policy,
            "configuration_sha256": self.configuration["sha256"],
            "task": task,
            "instruction": instruction,
        }
        if frozen is None:
            context.update(
                {
                    "inventory": self._inventory(),
                    "development_feedback": self._feedback(),
                    "measurement_counts": {
                        "train": len(self.host.train),
                        "dev": len(self.host.dev),
                    },
                    "train_preview": [
                        {k: r[k] for k in self.host.inputs + [self.host.task["output"]]}
                        for r in self.host.train[:6]
                    ],
                    "preview_scope": "first at most six train rows, not the fitting cohort",
                }
            )
        else:
            context["frozen_evidence"] = frozen
        return context

    def _system(self, role):
        return (
            "You are the "
            + role
            + " in an experimental scientific rule engine. Return one JSON object. "
            "Use only supplied train/dev evidence. All kernel/rule literals are forbidden; use host state names, "
            "input names and existing kernels. Numeric values are allowed only as parameter initial guesses "
            "p0..p7, which the host fits. Operators: + - * / ** abs sqrt log log1p exp sin cos tanh minimum maximum where. "
            "Provenance is host-controlled. Never invent a reference or claim test validation, causality or novelty."
        )

    def _ask(self, role, instruction, *, frozen=None):
        if self.stopped():
            raise InterruptedError("Cancelled before provider dispatch")
        if time.monotonic() - self.host.started > self.limits["max_seconds"]:
            raise TimeoutError("Attempt wall-time limit reached before provider dispatch")
        if frozen is None:
            self.host._check()
        if self.requests >= self.limits["max_calls"]:
            raise RuntimeError("Model request budget exhausted")
        context = self._context(role, instruction, frozen=frozen)
        prompt = json.dumps(context, allow_nan=False, sort_keys=True)
        system = self._system(role)
        if len((system + prompt).encode()) > 48000:
            raise ValueError("Protocol context exceeds gateway limit; no hidden truncation")
        self.requests += 1
        request_id = f"{self.run_id}--{self.request_tag}--{role}--{self.requests}"
        self._stage(
            "model_request",
            role=role,
            model=self.roles[role],
            request_id=request_id,
            context_sha256=sha(context),
            prompt_bytes=len(prompt.encode()),
        )
        response = self.gateway.complete(
            model=self.roles[role],
            system=system,
            prompt=prompt,
            max_tokens=1800,
            temperature=0.25,
            request_id=request_id,
        )
        if response.get("model") != self.roles[role] or response.get("request_id") != request_id:
            raise ValueError("Response identity mismatch; no model substitution")
        text = response["text"]
        if not isinstance(text, str) or len(text.encode()) > 64000:
            raise ValueError("Oversized model protocol response")
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("Model protocol requires an object")
        self._stage(
            "model_response",
            role=role,
            request_id=request_id,
            data=data,
            usage=response.get("usage", {}),
        )
        return data

    def _patch(self, data, round_id):
        if (
            set(data) - {"kernels", "rationale"}
            or not isinstance(data.get("kernels"), list)
            or len(data["kernels"]) > 3
        ):
            raise ValueError("Planner must propose at most three kernels and optional rationale")
        accepted = []
        for item in data["kernels"]:
            try:
                if not isinstance(item, dict) or set(item) != {"name", "expression"}:
                    raise ValueError(
                        "Kernel requires exactly name and expression; no model-authored state"
                    )
                name, expr = item["name"], item["expression"]
                if not isinstance(name, str) or not re.fullmatch(r"k_[A-Za-z0-9]{1,30}", name):
                    raise ValueError(
                        "Model kernel name must start k_ and have an alphanumeric suffix"
                    )
                if name in self.kernels or name in self.host.inputs or len(self.kernels) >= 24:
                    raise ValueError("Kernel is not a new name or library capacity reached")
                proposed = self.kernels | {name: expr}
                bindings = self._bindings(name, proposed)
                compile_program(
                    name, self.host.inputs, {}, bindings, self.host.registry, kernels=proposed
                )
                self.kernels[name] = expr
                self.kernel_sources[name] = {"kind": "model_structure", "round": round_id}
                accepted.append(name)
            except (ValueError, TypeError, KeyError, SyntaxError) as e:
                self.rejections.append(
                    {
                        "stage": "kernel_patch",
                        "round": round_id,
                        "proposal": copy.deepcopy(item),
                        "reason": str(e)[:300],
                    }
                )
        self._stage("kernel_patch", round=round_id, accepted=accepted)
        return accepted

    def _fit(self, rule, origin):
        if (
            not isinstance(rule, dict)
            or set(rule) != {"expression", "initial"}
            or not isinstance(rule["initial"], dict)
        ):
            self.rejections.append(
                {"stage": origin, "reason": "Rule requires exactly expression and initial map"}
            )
            return None
        try:
            bindings = self._bindings(rule["expression"])
            card = self.host.fit(
                rule["expression"], rule["initial"], bindings=bindings, kernels=self.kernels
            )
        except (ValueError, TypeError, KeyError, SyntaxError) as e:
            self.rejections.append(
                {"stage": origin, "proposal": copy.deepcopy(rule), "reason": str(e)[:300]}
            )
            card = None
        self._stage(
            "experiment",
            origin=origin,
            candidate_id=card["candidate_id"] if card else None,
            fitting_attempts=self.host.fits,
            optimizer_evaluations=self.host.optimizer_evaluations,
        )
        return card

    def _experiments(self, code, accepted, round_id):
        if set(code) != {"rules"} or not isinstance(code["rules"], list) or len(code["rules"]) > 2:
            raise ValueError("Coder must return at most two rule specifications")
        before = self.host.fits
        for rule in code["rules"]:
            self._fit(rule, f"coder-round-{round_id}")
        for name in accepted[:2]:
            self._fit(
                {"expression": f"p0+p1*{name}", "initial": {"p0": 0, "p1": 1}},
                f"composition-round-{round_id}",
            )
        feedback = self._feedback()
        for slot in feedback["selection"]["nominations"]:
            cid = slot["candidate_id"]
            name = f"fitted_{cid[:16]}" if cid else None
            if cid and name not in self.kernels and len(self.kernels) < 24:
                patch = self.host.promote(cid)
                self._register_references(patch["bindings"])
                self.kernels[name] = patch["expression"]
                self.kernel_sources[name] = {"kind": "host_promoted_fit", "candidate_id": cid}
        return {"feedback": feedback, "fitting_attempts": self.host.fits - before}

    def _critique(self, critique, experiments, accepted, round_id):
        visible_ids = {c["candidate_id"] for c in experiments["feedback"]["candidates"]}
        if (
            set(critique) != {"candidate_ids", "limitations", "next_hypothesis"}
            or not isinstance(critique["candidate_ids"], list)
            or not all(
                isinstance(cid, str) and cid in visible_ids for cid in critique["candidate_ids"]
            )
            or not isinstance(critique["limitations"], list)
            or not all(isinstance(v, str) for v in critique["limitations"])
            or not isinstance(critique["next_hypothesis"], str)
        ):
            raise ValueError("Critic must reference executed candidate IDs with limitations")
        self.rounds.append(
            {
                "round": round_id,
                "new_kernels": accepted,
                "fitting_attempts": experiments["fitting_attempts"],
                "critique": critique,
            }
        )
        self._stage("development_critique", **self.rounds[-1])

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
        failure, report = None, None
        selection, nomination_freeze = None, None
        try:
            self.step("initialize", "local", self._initialize)
            for round_id in range(2):
                plan = self.step(
                    f"plan-{round_id}",
                    "provider",
                    lambda: self._ask(
                        "planner",
                        "Propose up to three new reusable kernels as {kernels:[{name,expression}],rationale:string}. Revise from executed failures and critic feedback. Keep all fitted state references intact.",
                    ),
                )
                accepted = self.step(
                    f"patch-{round_id}", "local", partial(self._patch, plan, round_id)
                )
                code = self.step(
                    f"code-{round_id}",
                    "provider",
                    lambda: self._ask(
                        "coder",
                        "Propose up to two rules as {rules:[{expression,initial:{p0:0,p1:1}}]}. Use the current kernels and existing promoted fitted programs where scientifically justified.",
                    ),
                )
                experiments = self.step(
                    f"experiments-{round_id}",
                    "local",
                    partial(self._experiments, code, accepted, round_id),
                )
                critique = self.step(
                    f"critic-{round_id}",
                    "provider",
                    lambda: self._ask(
                        "critic",
                        "Return {candidate_ids:[IDs actually present in development feedback],limitations:[strings],next_hypothesis:string}. Explain competing structures and failed tests; do not supply numerical test feedback.",
                    ),
                )
                self.step(
                    f"critique-{round_id}",
                    "local",
                    partial(self._critique, critique, experiments, accepted, round_id),
                )
            nomination = self.step("nominate", "local", self._nominate)
            selection, nomination_freeze = nomination["selection"], nomination["nomination_freeze"]
            selected_ids = [
                s["candidate_id"] for s in selection["nominations"] if s["candidate_id"]
            ]
            report = self.step(
                "report",
                "provider",
                lambda: self._ask(
                    "reporter",
                    "Return {candidate_ids:[all nominated IDs],limitations:[strings],summary:string}. Cite the frozen evidence only; no changes to rules or nomination. Scientific novelty and impact are not assessed.",
                    frozen={
                        "nomination_freeze": nomination_freeze,
                        "selection": selection,
                        "candidates": [self.host.candidates[c] for c in selected_ids],
                    },
                ),
            )
            if (
                set(report) != {"candidate_ids", "limitations", "summary"}
                or not isinstance(report["candidate_ids"], list)
                or len(report["candidate_ids"]) != len(selected_ids)
                or set(report["candidate_ids"]) != set(selected_ids)
                or not isinstance(report["summary"], str)
                or not isinstance(report["limitations"], list)
                or not all(isinstance(v, str) for v in report["limitations"])
            ):
                raise ValueError("Report does not match all frozen nominations")
        except Exception as e:
            if getattr(e, "recovery_required", False):
                raise
            failure = {
                "type": getattr(e, "original_type", type(e).__name__),
                "reason": str(e)[:300],
            }
            self._stage("stopped", **failure)
        selection = selection or development_selection(self.host.candidates.values())
        frozen = self.host.freeze()
        if nomination_freeze is None:
            nomination_freeze = {
                "host_sha256": frozen["sha256"],
                "selection": copy.deepcopy(selection),
                "configuration_sha256": self.configuration["sha256"],
            }
            nomination_freeze["sha256"] = sha(nomination_freeze)
        conformance = {
            "two_executed_rounds": len(self.rounds) == 2
            and all(r["fitting_attempts"] > 0 for r in self.rounds),
            "kernel_search_executed": any(r["new_kernels"] for r in self.rounds),
            "report_links_frozen_nominations": report is not None and failure is None,
        }
        status = (
            "failed"
            if failure
            else "complete"
            if all(conformance.values())
            else "incomplete_method_execution"
        )
        self.result = {
            "policy": self.policy,
            "status": status,
            "configuration": self.configuration,
            "host_submission": frozen,
            "selection": selection,
            "conformance": conformance,
            "nomination_freeze": nomination_freeze,
            "model_requests": self.requests,
            "trace": self.trace,
            "rejections": self.rejections,
            "failure": failure,
            "report": report,
            "report_review": "not_assessed",
            "ranking_authorized": False,
            "scientific_review": "not_assessed",
        }
        self.result["sha256"] = sha(self.result)
        return copy.deepcopy(self.result)
