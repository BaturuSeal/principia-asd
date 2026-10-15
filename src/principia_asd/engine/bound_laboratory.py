"""Agent Laboratory adaptation on explicit host state, development API only.

No weak-prior fits, kernel search or hidden Engine reasoning is inherited. The
shared base supplies state bindings, provider identity checks and budget guards.
Only the two model-authored experiments are fitted. Completed legacy runs stay
under their original representation and revision.
"""

from __future__ import annotations

import ast
import copy
from functools import partial

from ..io import sha
from .bindings import compile_program
from .bound_engine import BoundEngine, development_selection
from .bound_engine_v2 import candidate_packet, failure_packet
from .evidence import cohort_context, exact_cohort_report, prediction_requirements
from .expression import FUNCS, structural_key
from .laboratory import REVISION, SOURCE

POLICY = "agent-laboratory-explicit-state-v1-dev"
STAGES = (
    "research_brief",
    "experiment_plan",
    "initial_engineering",
    "experimental_critique",
    "revised_engineering",
    "evidence_report",
)
ROLES = ("planner", "planner", "coder", "critic", "coder", "reporter")
CONTRACTS = {
    "research_brief": {
        "question": "string",
        "hypotheses": "nonempty string array",
        "limitations": "nonempty string array",
    },
    "experiment_plan": {
        "objective": "string",
        "experiments": "two string descriptions, initial and feedback revision",
        "selection_criterion": "string",
        "risks": "nonempty string array",
    },
    "initial_engineering": {
        "expression": "string",
        "initial": "p0..p7 to finite starting values; exactly the parameters used",
    },
    "experimental_critique": {
        "experiment_ids": "exactly [experiment-1]",
        "issues": "nonempty string array",
        "revision": "string",
    },
    "revised_engineering": {
        "expression": "string",
        "initial": "p0..p7 to finite starting values; exactly the parameters used",
    },
    "evidence_report": {
        "summary": "string",
        "experiment_ids": "both experiment-1 and experiment-2, exactly once",
        "candidate_ids": "all frozen nominated IDs exactly once",
        "limitations": "nonempty string array",
        "observed_cohort": "exact copy of cohort.verified_counts",
    },
}
INSTRUCTIONS = {
    "research_brief": "Review permitted local measurements and nominate competing explanations. No live literature access or invented citations.",
    "experiment_plan": "Use the preceding brief to plan two experiments. Fit on train; select on dev using the contract metric. The second experiment must use executed feedback.",
    "initial_engineering": "Implement the planned initial numerical program using inventory inputs, normalized kernels or state names. No literals inside expression, hidden transforms, new state or new kernels. Put starting coefficients only in initial; the host fits them on train.",
    "experimental_critique": "Use the actual first experiment, including failures and residuals, to specify a concrete revision. Distinguish predictive fit from mechanism.",
    "revised_engineering": "Implement the preceding critique as a structurally different program or repair a rejected first program. Renaming parameters/kernels or changing starting values is not a structural revision. The same explicit-state rules apply.",
    "evidence_report": "Report both executed experiments, including failures. Use frozen nominations only. Copy exact cohort counts, not preview length. No private-test, novelty or causality claims. Interpretation is unreviewed.",
}


def strings(value, length=None):
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(v, str) and bool(v.strip()) for v in value)
        and (length is None or len(value) == length)
    )


class BoundLaboratory(BoundEngine):
    policy = POLICY
    request_tag = "laboratory-bound-v1"

    def __init__(self, *args, limits=None, **kwargs):
        super().__init__(*args, limits={"max_calls": 6, "max_fits": 2} | (limits or {}), **kwargs)
        self.configuration.pop("sha256")
        self.configuration.update(
            method_id="agent_laboratory",
            source_revision=REVISION,
            source_url=SOURCE,
            license="MIT",
            handoff_contracts_sha256=sha(CONTRACTS),
            instructions_sha256=sha(INSTRUCTIONS),
            handoff_stages=list(STAGES),
            handoff_roles=list(ROLES),
            weak_prior_fits=0,
            rounds=0,
            local_compositions_per_round=0,
            planned_experiments=2,
            structural_revision_policy="expanded-operators-ignore-coefficient-names-v1",
            context_policy="complete-two-experiment-development-evidence-v1",
        )
        self.configuration["sha256"] = sha(self.configuration)

    def _records(self, stage):
        return [copy.deepcopy(r) for r in self.trace if r["stage"] == stage]

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
        self._stage("laboratory_inventory", fitting_attempts=self.host.fits)

    def _system(self, role):
        return super()._system(role) + (
            " You are executing a bounded Agent Laboratory adaptation, not a kernel-search loop."
            " Follow the stage_contract exactly. No additional fits or invented evidence."
        )

    def _context(self, role, instruction, *, frozen=None):
        context = copy.deepcopy(super()._context(role, INSTRUCTIONS[instruction], frozen=frozen))
        context.pop("development_feedback", None)
        context.update(
            laboratory_stage=instruction,
            stage_contract=copy.deepcopy(CONTRACTS[instruction]),
            cohort=cohort_context(self.host),
            inventory=self._inventory(),
            prediction_requirements=prediction_requirements(self.host.task),
            operator_arities={k: v[1] for k, v in FUNCS.items()},
            preceding_handoffs=self._records("laboratory_handoff"),
            experiments=self._records("laboratory_experiment"),
            evidence_scope="train/dev only; all two experiment packets and all failures retained",
            live_literature=False,
        )
        if frozen:
            context["frozen_evidence"]["candidates"] = [
                candidate_packet(c) for c in frozen["candidates"]
            ]
        return context

    def _valid_handoff(self, name, data, frozen):
        if set(data) != set(CONTRACTS[name]):
            return False
        if name in ("initial_engineering", "revised_engineering"):
            return (
                isinstance(data["expression"], str)
                and bool(data["expression"].strip())
                and isinstance(data["initial"], dict)
            )
        if name == "research_brief":
            return (
                isinstance(data["question"], str)
                and bool(data["question"].strip())
                and strings(data["hypotheses"])
                and strings(data["limitations"])
            )
        if name == "experiment_plan":
            return (
                all(
                    isinstance(data[k], str) and data[k].strip()
                    for k in ("objective", "selection_criterion")
                )
                and strings(data["experiments"], 2)
                and strings(data["risks"])
            )
        if name == "experimental_critique":
            return (
                data["experiment_ids"] == ["experiment-1"]
                and strings(data["issues"])
                and isinstance(data["revision"], str)
                and bool(data["revision"].strip())
            )
        ids = [s["candidate_id"] for s in frozen["selection"]["nominations"] if s["candidate_id"]]
        return (
            isinstance(data["summary"], str)
            and bool(data["summary"].strip())
            and strings(data["experiment_ids"], 2)
            and sorted(data["experiment_ids"]) == ["experiment-1", "experiment-2"]
            and isinstance(data["candidate_ids"], list)
            and all(isinstance(v, str) for v in data["candidate_ids"])
            and sorted(data["candidate_ids"]) == sorted(ids)
            and strings(data["limitations"])
            and exact_cohort_report(data["observed_cohort"], self.host)
        )

    def _handoff(self, name, frozen=None):
        role = ROLES[STAGES.index(name)]
        context_hash = sha(self._context(role, name, frozen=frozen))
        output = self._ask(role, name, frozen=frozen)
        self._stage(
            "laboratory_handoff",
            name=name,
            role=role,
            model=self.roles[role],
            input_sha256=context_hash,
            output=output,
            output_sha256=sha(output),
            schema_valid=bool(self._valid_handoff(name, output, frozen)),
        )
        return output

    def _structure(self, rule):
        program = compile_program(
            rule["expression"],
            self.host.inputs,
            rule["initial"],
            self._bindings(rule["expression"]),
            self.host.registry,
            kernels=self.kernels,
        )
        states = {f"bound{i}": s for i, s in enumerate(sorted(program["states"]))}

        class Canonical(ast.NodeTransformer):
            def visit_Name(self, node):
                name = (
                    "coefficient"
                    if node.id in rule["initial"]
                    else "state_" + states[node.id]
                    if node.id in states
                    else node.id
                )
                return ast.copy_location(ast.Name(id=name, ctx=ast.Load()), node)

        return structural_key(
            ast.unparse(Canonical().visit(ast.parse(program["expression"], mode="eval")))
        )

    def _experiment(self, rule, experiment_id):
        before = (
            self.host.fits,
            self.host.optimizer_evaluations,
            len(self.host.seen),
            len(self.host.failures),
            len(self.rejections),
        )
        card = self._fit(rule, experiment_id)
        try:
            structure = self._structure(rule)
        except (ValueError, TypeError, KeyError, SyntaxError):
            structure = None
        result = {
            "experiment_id": experiment_id,
            "program": copy.deepcopy(rule),
            "program_sha256": sha(rule),
            "structure_key": structure,
            "status": "complete" if card else "failed_or_not_executed",
            "structure_entered": len(self.host.seen) > before[2],
            "fitting_attempts": self.host.fits - before[0],
            "optimizer_evaluations": self.host.optimizer_evaluations - before[1],
            "failures": [failure_packet(f) for f in self.host.failures[before[3] :]],
            "rejections": copy.deepcopy(self.rejections[before[4] :]),
            "result": candidate_packet(card) if card else None,
        }
        self._stage("laboratory_experiment", **result)
        return result

    def run(self):
        if self.result is not None:
            return copy.deepcopy(self.result)
        failure, report, nomination = None, None, None
        try:
            self.step("initialize", "local", self._initialize)
            for name in STAGES[:-1]:
                output = self.step(name, "provider", partial(self._handoff, name))
                if name in ("initial_engineering", "revised_engineering"):
                    eid = "experiment-1" if name == "initial_engineering" else "experiment-2"
                    self.step(eid, "local", partial(self._experiment, output, eid))
            nomination = self.step("nominate", "local", self._nominate)
            ids = [
                s["candidate_id"]
                for s in nomination["selection"]["nominations"]
                if s["candidate_id"]
            ]
            frozen = nomination | {"candidates": [self.host.candidates[c] for c in ids]}
            report = self.step(
                "evidence_report", "provider", partial(self._handoff, "evidence_report", frozen)
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
        handoffs, experiments = (
            self._records("laboratory_handoff"),
            self._records("laboratory_experiment"),
        )
        revised = len(experiments) == 2 and (
            experiments[0]["structure_key"] != experiments[1]["structure_key"]
            and experiments[1]["structure_key"] is not None
            and (
                experiments[1]["result"] is not None or experiments[1]["optimizer_evaluations"] > 0
            )
        )
        checks = {
            "all_six_handoffs_valid": len(handoffs) == 6
            and all(h["schema_valid"] for h in handoffs),
            "two_programs_locally_checked": len(experiments) == 2
            and all(e["structure_entered"] for e in experiments),
            "feedback_conditioned_structural_revision": bool(revised),
            "at_least_one_valid_experiment": any(e["result"] for e in experiments),
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
