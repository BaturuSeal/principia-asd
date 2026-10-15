"""Asta's bounded tree search on explicit host state; development API only.

The local v2 adaptation supplies widening, UCT, Beta updates and propagation.
This module supplies a separately versioned protocol, not Engine compositions.
All persistent algorithm state is in the shared append-only checkpoint trace.
"""

from __future__ import annotations

import ast
import copy
from functools import partial

import numpy as np

from ..evaluate.metrics import loss
from ..io import sha
from .asta import CONFIG, REVISION, SOURCE, backpropagate, belief_update, choose_parent
from .bindings import compile_program
from .bound_engine import BoundEngine, development_selection
from .bound_engine_v2 import candidate_packet, failure_packet
from .bound_search import HOST_POLICY
from .evidence import cohort_context, exact_cohort_report, prediction_requirements
from .expression import FUNCS, structural_key

POLICY = "asta-explicit-state-v1-dev"
CONTRACTS = {
    "nomination": {
        "hypothesis": "nonempty string",
        "expression": "one expression using inputs, inventory kernels or states; no literals",
        "initial": "exact p0..p7 parameters with finite initial values",
        "rationale": "nonempty string",
    },
    "prior": {"belief": "JSON boolean or null", "reason": "nonempty string"},
    "engineering": {
        "expression": "exact frozen expression string",
        "initial": "exact frozen parameter names; finite starting values may change",
    },
    "posterior": {"belief": "JSON boolean or null", "reason": "nonempty string"},
    "report": {
        "summary": "nonempty string",
        "experiment_ids": "hypothesis-1 through hypothesis-4, each exactly once in order",
        "candidate_ids": "every frozen nominated candidate ID exactly once",
        "limitations": "nonempty array of nonempty strings",
        "observed_cohort": "exact copy of cohort.verified_counts",
    },
}
INSTRUCTIONS = {
    "nomination": "Nominate one distinct formula family. Use actual ancestor experiments and failures for a descendant; propose a competing structure at the root. Freeze before observers. No additional kernels, fitted state or hidden transforms. The claim concerns strictly lower dev loss than the train-mean comparator, not mechanism.",
    "prior": "Before execution, use domain knowledge and the symbolic frozen claim for a subjective expectation. True means leaning toward it, false means against it; null is a retained abstention. Lack of observed measurements alone does not prohibit an expectation. Do not invent measurements or infer results from planner selection. Other observers and planner prose are unavailable.",
    "engineering": "Copy frozen_program.expression exactly and retain exactly its parameter names. Supply finite starting guesses only in initial; the host fits on train. Do not repair or change the frozen hypothesis, invent state, or supply literals inside expression.",
    "posterior": "Use only the recorded experiment for evidence about the frozen claim: true for support, false for counterevidence, null for insufficient evidence. Failed execution is not scientific refutation. Prior votes and other observer samples are unavailable.",
    "report": "Summarize every experiment including failures, using frozen nominations and exact cohort counts. Belief reward is an uncalibrated search heuristic, not significance or scientific probability. No test, novelty or causal claims. Do not revise frozen work.",
}


def _text(value):
    return isinstance(value, str) and bool(value.strip())


class BoundAsta(BoundEngine):
    policy = POLICY
    request_tag = "asta-bound-v1"

    def __init__(self, *args, limits=None, **kwargs):
        super().__init__(*args, limits={"max_calls": 25, "max_fits": 4} | (limits or {}), **kwargs)
        self.configuration.pop("sha256")
        self.configuration.update(
            method_id="asta_autodiscovery",
            source_revision=REVISION,
            source_url=SOURCE,
            license="Apache-2.0",
            algorithm=copy.deepcopy(CONFIG),
            handoff_contracts_sha256=sha(CONTRACTS),
            instructions_sha256=sha(INSTRUCTIONS),
            weak_prior_fits=0,
            rounds=0,
            local_compositions_per_round=0,
            planned_experiments=4,
            context_policy="isolated-symbolic-prior-and-recorded-posterior-v1",
            structure_policy="expanded-operators-shared-parameters-and-state-identities-v1",
        )
        self.configuration["sha256"] = sha(self.configuration)

    def _records(self, stage):
        return [copy.deepcopy(r) for r in self.trace if r["stage"] == stage]

    def _record(self, stage, node_id):
        return next(r for r in self._records(stage) if r["node_id"] == node_id)

    def _initialize(self):
        self.host._check()
        self._register_references(self.host.constants)
        for i, name in enumerate(self.host.inputs):
            try:
                refs = self.host.normalization(name)
            except ValueError as exc:
                self.rejections.append(
                    {"stage": "normalization", "input": name, "reason": str(exc)}
                )
                continue
            self._register_references(refs)
            key = f"normalized_{i}"
            if key in self.host.inputs:
                raise ValueError("Input collides with protocol primitive namespace")
            self.kernels[key] = f"({name}-state_{refs['center']})/state_{refs['scale']}"
            self.kernel_sources[key] = {"kind": "host_train_normalization", "input": name}
        mean = float(np.mean(self.host.y))
        # Comparator-only state is counted and retained but is not a fitted candidate.
        refs = self.host._register(
            {
                "kind": "train_statistic",
                "scope": "train",
                "status": "complete",
                "policy": HOST_POLICY,
                "operation": "numpy_mean_training_response",
                "numpy_version": np.__version__,
                "train_sha256": self.host.context["train_sha256"],
                "output": self.host.task["output"],
                "rows": len(self.host.y),
                "values": {"mean": mean},
            }
        )
        self._stage(
            "asta_comparator",
            state_id=refs["mean"],
            train_mean=mean,
            dev_error=loss(
                np.full(len(self.host.dy), mean),
                self.host.dy,
                self.host.task["metric"]["primary"],
                [r["group"] for r in self.host.dev],
            ),
        )

    def _tree(self):
        nodes = {
            "root": {
                "node_id": "root",
                "parent_id": None,
                "children": [],
                "visits": 0,
                "reward_sum": 0.0,
            }
        }
        for event in self._records("asta_update"):
            node = copy.deepcopy(event["node"])
            nodes[node["node_id"]] = node
            nodes[node["parent_id"]]["children"].append(node["node_id"])
            backpropagate(nodes, node["node_id"], node["belief_update"]["reward"])
        return nodes

    def _select(self, node_id):
        parent, decisions = choose_parent(self._tree())
        result = {"node_id": node_id, "parent_id": parent, "decisions": decisions}
        self._stage("asta_selection", **result)
        return result

    def _compile(self, rule):
        if not isinstance(rule.get("initial"), dict) or set(rule["initial"]) - {
            f"p{i}" for i in range(8)
        }:
            raise ValueError("Initial values must declare only p0 through p7")
        return compile_program(
            rule["expression"],
            self.host.inputs,
            rule["initial"],
            self._bindings(rule["expression"]),
            self.host.registry,
            kernels=self.kernels,
        )

    def _structure(self, program):
        parameters = program["specification"]["parameters"]
        states = {f"bound{i}": s for i, s in enumerate(sorted(program["states"]))}
        renamed = {}

        class Canonical(ast.NodeTransformer):
            def visit_Name(self, node):
                if node.id in parameters:
                    renamed.setdefault(node.id, f"coefficient_{len(renamed)}")
                    name = renamed[node.id]
                elif node.id in states:
                    name = "state_" + states[node.id]
                else:
                    name = node.id
                return ast.copy_location(ast.Name(id=name, ctx=ast.Load()), node)

        return structural_key(
            ast.unparse(Canonical().visit(ast.parse(program["expression"], mode="eval")))
        )

    def _symbolic_claim(self, node_id, program):
        """No fitted values, train statistics, preview rows or planner prose to priors."""
        mapping, descriptions = {}, {}
        for i, digest in enumerate(sorted(program["states"])):
            state = program["states"][digest]
            source = self.host.registry.artifacts[state["artifact_sha256"]]
            alias = f"symbolic_state_{i}"
            mapping[f"bound{i}"] = alias
            descriptions[alias] = {
                "kind": state["kind"],
                "operation": source["operation"],
                "component": state["value_path"][-1],
            }
            if "input" in source:
                descriptions[alias]["input"] = source["input"]
            if state["kind"] == "fixed_scientific":
                descriptions[alias]["fixed_value"] = state["value"]

        class Symbolic(ast.NodeTransformer):
            def visit_Name(self, node):
                return ast.copy_location(
                    ast.Name(id=mapping.get(node.id, node.id), ctx=ast.Load()), node
                )

        return {
            "node_id": node_id,
            "expanded_symbolic_expression": ast.unparse(
                Symbolic().visit(ast.parse(program["expression"], mode="eval"))
            ),
            "parameter_names": sorted(program["specification"]["parameters"]),
            "symbolic_states": descriptions,
            "operational_claim": "Fitted on train, this expression has strictly lower dev loss than the train-mean predictor",
            "scope": "development predictive evidence only",
        }

    def _freeze_claim(self, node_id, draft):
        valid, structure, symbolic, reason = True, None, None, None
        try:
            if set(draft) != set(CONTRACTS["nomination"]) or not all(
                _text(draft[k]) for k in ("hypothesis", "rationale")
            ):
                raise ValueError(
                    "Nomination requires exact flat fields and nonempty hypothesis/rationale"
                )
            program = self._compile(draft)
            structure = self._structure(program)
            symbolic = self._symbolic_claim(node_id, program)
        except (ValueError, TypeError, KeyError, SyntaxError) as exc:
            valid, reason = False, str(exc)[:300]
        unique = structure is not None and structure not in {
            r["structure_key"] for r in self._records("asta_claim")
        }
        claim = {
            "node_id": node_id,
            "draft": copy.deepcopy(draft),
            "program": {k: copy.deepcopy(draft.get(k)) for k in ("expression", "initial")},
            "valid": valid,
            "unique": unique,
            "structure_key": structure,
            "symbolic_claim": symbolic
            or {"node_id": node_id, "status": "invalid_unexecutable_claim"},
            "reason": reason,
            "context": copy.deepcopy(self.host.context),
        }
        claim["sha256"] = sha(claim)
        self._stage("asta_claim", **claim)
        return claim

    def _system(self, role):
        phase = self._request_phase
        if phase in ("prior", "posterior"):
            return (
                "You are an isolated belief observer in a bounded Asta adaptation. Return one flat JSON object "
                "with exactly belief (boolean or null) and reason (nonempty string). No other keys. "
                + (
                    "Prior expectations may use domain knowledge; do not require observations to express a defensible leaning. "
                    if phase == "prior"
                    else "Use only the supplied executed experiment; no added domain evidence. "
                )
                + "No claims of calibrated probability, causality, novelty or test validation."
            )
        return (
            super()._system(role)
            + " This is bounded Asta tree search. Return exactly stage_contract fields as one flat object; no wrappers or extra fields."
        )

    def _context(self, role, instruction, *, frozen=None):
        node_id, phase, sample = instruction.split(":")
        task = {
            k: copy.deepcopy(self.host.task[k])
            for k in ("inputs", "output", "input_units", "output_units", "title")
            if k in self.host.task
        }
        task["metric"] = self.host.task["metric"]["primary"]
        context = {
            "policy": self.policy,
            "asta_stage": phase,
            "node_id": node_id,
            "sample": sample,
            "task": task,
            "instruction": INSTRUCTIONS[phase],
            "stage_contract": copy.deepcopy(CONTRACTS[phase]),
        }
        if phase in ("prior", "posterior"):
            context["frozen_claim"] = self._record("asta_claim", node_id)["symbolic_claim"]
            if phase == "posterior":
                context["executed_experiment"] = self._record("asta_experiment", node_id)
            return context
        context.update(
            cohort=cohort_context(self.host),
            inventory=self._inventory(),
            operator_arities={k: v[1] for k, v in FUNCS.items()},
            prediction_requirements=prediction_requirements(self.host.task),
        )
        if phase == "report":
            context.update(
                frozen_evidence=copy.deepcopy(frozen),
                search_tree=list(self._tree().values()),
                selection_history=self._records("asta_selection"),
            )
            return context
        context["train_preview"] = [
            {k: r[k] for k in self.host.inputs + [self.host.task["output"]]}
            for r in self.host.train[:6]
        ]
        context["preview_scope"] = "first at most six train rows; all rows used by host"
        if phase == "engineering":
            context["frozen_program"] = self._record("asta_claim", node_id)["program"]
        else:
            parent = self._record("asta_selection", node_id)["parent_id"]
            nodes, ancestors, cursor = self._tree(), [], parent
            while cursor != "root":
                node = nodes[cursor]
                ancestors.append(
                    {k: node[k] for k in ("node_id", "hypothesis", "experiment", "belief_update")}
                )
                cursor = node["parent_id"]
            context.update(
                parent_id=parent,
                ancestor_evidence=list(reversed(ancestors)),
                existing_expressions=[
                    r["program"]["expression"] for r in self._records("asta_claim")
                ],
            )
        return context

    def _handoff(self, node_id, phase, sample="0", frozen=None):
        role = {
            "nomination": "planner",
            "engineering": "coder",
            "prior": "critic",
            "posterior": "critic",
            "report": "reporter",
        }[phase]
        instruction = f"{node_id}:{phase}:{sample}"
        self._request_phase = phase
        context = self._context(role, instruction, frozen=frozen)
        output = self._ask(role, instruction, frozen=frozen)
        valid = set(output) == set(CONTRACTS[phase])
        if phase in ("prior", "posterior"):
            valid &= (
                "belief" in output
                and (output["belief"] is None or type(output["belief"]) is bool)
                and _text(output.get("reason"))
            )
        elif phase == "report":
            ids = [
                s["candidate_id"] for s in frozen["selection"]["nominations"] if s["candidate_id"]
            ]
            candidates = output.get("candidate_ids")
            valid &= (
                output.get("experiment_ids") == [f"hypothesis-{i + 1}" for i in range(4)]
                and isinstance(candidates, list)
                and all(isinstance(v, str) for v in candidates)
                and sorted(candidates) == sorted(ids)
                and _text(output.get("summary"))
                and isinstance(output.get("limitations"), list)
                and bool(output["limitations"])
                and all(_text(v) for v in output["limitations"])
                and exact_cohort_report(output.get("observed_cohort"), self.host)
            )
        self._stage(
            "asta_handoff",
            node_id=node_id,
            phase=phase,
            sample=sample,
            role=role,
            model=self.roles[role],
            input_sha256=sha(context),
            output=output,
            output_sha256=sha(output),
            schema_valid=bool(valid),
        )
        return output

    def _experiment(self, node_id, code):
        claim = self._record("asta_claim", node_id)
        before = (
            self.host.fits,
            self.host.optimizer_evaluations,
            len(self.host.seen),
            len(self.host.failures),
            len(self.rejections),
        )
        valid = False
        try:
            valid = (
                claim["valid"]
                and claim["unique"]
                and set(code) == {"expression", "initial"}
                and code["expression"] == claim["program"]["expression"]
                and sorted(code["initial"]) == sorted(claim["program"]["initial"])
                and self._structure(self._compile(code)) == claim["structure_key"]
            )
        except (ValueError, TypeError, KeyError, SyntaxError):
            pass
        card = self._fit(code, node_id) if valid else None
        if not valid:
            self.rejections.append(
                {"stage": node_id, "reason": "Invalid/repeated claim or changed frozen program"}
            )
        comparator = self._records("asta_comparator")[0]
        result = {
            "node_id": node_id,
            "experiment_id": node_id,
            "program": copy.deepcopy(code),
            "program_sha256": sha(code),
            "claim_sha256": claim["sha256"],
            "binding_valid": bool(valid),
            "status": "complete" if card else "failed_or_not_executed",
            "structure_entered": len(self.host.seen) > before[2],
            "fitting_attempts": self.host.fits - before[0],
            "optimizer_evaluations": self.host.optimizer_evaluations - before[1],
            "failures": [failure_packet(f) for f in self.host.failures[before[3] :]],
            "rejections": copy.deepcopy(self.rejections[before[4] :]),
            "result": candidate_packet(card) if card else None,
            "comparator_dev_error": comparator["dev_error"],
            "comparator_state_id": comparator["state_id"],
            "operational_claim_supported": card["dev_error"] < comparator["dev_error"]
            if card
            else None,
        }
        self._stage("asta_experiment", **result)
        exhausted = next(
            (f["reason"] for f in result["failures"] if "budget reached" in f["reason"]),
            None,
        )
        if exhausted:
            raise RuntimeError(exhausted)
        return result

    def _update(self, node_id):
        claims = self._record("asta_claim", node_id)
        samples = [
            r
            for r in self._records("asta_handoff")
            if r["node_id"] == node_id and r["phase"] in ("prior", "posterior")
        ]
        votes = {
            phase: [
                s["output"].get("belief") if s["schema_valid"] else None
                for s in samples
                if s["phase"] == phase
            ]
            for phase in ("prior", "posterior")
        }
        belief = belief_update(votes["prior"], votes["posterior"])
        belief["samples_schema_valid"] = len(samples) == 4 and all(
            s["schema_valid"] for s in samples
        )
        experiment = self._record("asta_experiment", node_id)
        if not experiment["result"] or not belief["samples_schema_valid"]:
            belief["reward"] = 0.0
            belief["reward_exclusion"] = "Failed experiment or malformed observer response"
        node = {
            "node_id": node_id,
            "parent_id": self._record("asta_selection", node_id)["parent_id"],
            "children": [],
            "visits": 0,
            "reward_sum": 0.0,
            "hypothesis": copy.deepcopy(claims["draft"]),
            "claim_sha256": claims["sha256"],
            "valid_claim": claims["valid"],
            "unique_structure": claims["unique"],
            "experiment": experiment,
            "belief_update": belief,
        }
        self._stage("asta_update", node=node)
        return node

    def run(self):
        if self.result is not None:
            return copy.deepcopy(self.result)
        failure, report, nomination = None, None, None
        try:
            self.step("initialize", "local", self._initialize)
            for i in range(4):
                node = f"hypothesis-{i + 1}"
                self.step(f"{node}:select", "local", partial(self._select, node))
                draft = self.step(
                    f"{node}:nomination", "provider", partial(self._handoff, node, "nomination")
                )
                self.step(f"{node}:freeze", "local", partial(self._freeze_claim, node, draft))
                for sample in ("1", "2"):
                    self.step(
                        f"{node}:prior:{sample}",
                        "provider",
                        partial(self._handoff, node, "prior", sample),
                    )
                code = self.step(
                    f"{node}:engineering", "provider", partial(self._handoff, node, "engineering")
                )
                self.step(f"{node}:experiment", "local", partial(self._experiment, node, code))
                for sample in ("1", "2"):
                    self.step(
                        f"{node}:posterior:{sample}",
                        "provider",
                        partial(self._handoff, node, "posterior", sample),
                    )
                self.step(f"{node}:update", "local", partial(self._update, node))
            nomination = self.step("nominate", "local", self._nominate)
            ids = [
                s["candidate_id"]
                for s in nomination["selection"]["nominations"]
                if s["candidate_id"]
            ]
            frozen = nomination | {
                "candidates": [candidate_packet(self.host.candidates[c]) for c in ids]
            }
            report = self.step(
                "report", "provider", partial(self._handoff, "report", "report", "0", frozen)
            )
        except Exception as exc:
            if getattr(exc, "recovery_required", False):
                raise
            failure = {
                "type": getattr(exc, "original_type", type(exc).__name__),
                "reason": str(exc)[:300],
            }
            self._stage("stopped", **failure)
        frozen = self.host.freeze()
        if nomination is None:
            selection = development_selection(self.host.candidates.values())
            freeze = {
                "host_sha256": frozen["sha256"],
                "selection": selection,
                "configuration_sha256": self.configuration["sha256"],
            }
            freeze["sha256"] = sha(freeze)
            nomination = {"selection": selection, "nomination_freeze": freeze}
        nodes = self._tree()
        leaves = [v for k, v in nodes.items() if k != "root"]
        experiments, handoffs = self._records("asta_experiment"), self._records("asta_handoff")
        checks = {
            "four_distinct_frozen_hypotheses": len(leaves) == 4
            and all(n["valid_claim"] and n["unique_structure"] for n in leaves),
            "branching_and_descendant_executed": len(nodes["root"]["children"]) >= 2
            and any(
                n["parent_id"] != "root" and n["experiment"]["structure_entered"] for n in leaves
            ),
            "progressive_widening_and_uct_used": any(
                d["action"] == "descend"
                for s in self._records("asta_selection")
                for d in s["decisions"]
            ),
            "all_frozen_programs_checked": len(experiments) == 4
            and all(e["binding_valid"] and e["structure_entered"] for e in experiments),
            "well_formed_handoffs": len(handoffs) == 25
            and all(h["schema_valid"] for h in handoffs),
            "valid_experiments_observed_beliefs": all(
                n["belief_update"]["sufficient_nonabstained_samples"]
                for n in leaves
                if n["experiment"]["result"]
            ),
            "at_least_one_valid_experiment": any(e["result"] for e in experiments),
            "all_rewards_propagated": nodes["root"]["visits"] == 4,
            "report_after_nomination_freeze": report is not None and self.host.closed,
        }
        self.result = {
            "policy": self.policy,
            "status": "failed"
            if failure
            else "complete"
            if all(checks.values())
            else "incomplete_method_execution",
            "configuration": self.configuration,
            "host_submission": frozen,
            **nomination,
            "conformance": checks,
            "search_tree": list(nodes.values()),
            "selection_history": self._records("asta_selection"),
            "handoffs": handoffs,
            "experiments": experiments,
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
