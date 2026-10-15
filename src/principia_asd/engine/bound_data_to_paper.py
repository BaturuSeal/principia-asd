"""Guarded data-to-paper development protocol with host-owned fitted state.

One planned analysis, at most one failed-analysis repair, deterministic statistics,
critique and a backward-traceable report. No weak-prior fits, composition search,
private-test access or unaccounted coefficient literals. The legacy adaptation is
unchanged. A dedicated worker and a frozen live pilot are still required.
"""

from __future__ import annotations

import ast
import copy
import re
import time
from functools import partial

import numpy as np

from ..evaluate.metrics import loss, validity
from ..io import sha
from .bindings import compile_program, execute_program, verify_program
from .bound_engine import BoundEngine, development_selection
from .bound_engine_v2 import candidate_packet, failure_packet
from .data_to_paper import REVISION, SOURCE, plan_errors
from .evidence import cohort_context, exact_cohort_report, prediction_requirements
from .expression import FUNCS

POLICY = "data-to-paper-explicit-state-v1-dev"
FACT_POLICY = "bound-statistical-facts-v1-dev"
REFERENCE = re.compile(r"\{\{([a-z_]+)\}\}")
CONTRACTS = {
    "analysis_plan": {
        "hypothesis": "nonempty string",
        "inputs": "distinct subset of permitted measurements",
        "output": "exact contract output",
        "metric": "exact contract primary metric",
        "fit_partition": "train",
        "selection_partition": "dev",
        "limitations": "nonempty string array",
    },
    "analysis_program": {
        "expression": "string using only planned inputs and host state or normalized kernels",
        "initial": "p0..p7 to finite starting values, exactly the parameters used",
    },
    "statistical_review": {
        "experiment_ids": "exactly the successful analysis ID",
        "facts_sha256": "exact supplied statistics bundle hash",
        "limitations": "nonempty qualitative string array",
        "interpretation": "nonempty qualitative string; unreviewed",
    },
    "evidence_report": {
        "sections": "one to six objects with heading and template; all numbers use {{fact_name}}",
        "observed_cohort": "exact copy of cohort.verified_counts",
        "candidate_ids": "exactly all frozen nominated IDs",
        "facts_sha256": "exact supplied statistics bundle hash",
        "limitation_ids": "all supplied limitation IDs exactly once",
        "limitations": "nonempty strings with all numbers expressed as {{fact_name}}",
    },
}
ROLES = {
    "analysis_plan": "planner",
    "analysis_program": "coder",
    "analysis_repair": "coder",
    "statistical_review": "critic",
    "evidence_report": "reporter",
    "report_repair": "reporter",
}
INSTRUCTIONS = {
    "analysis_plan": "Plan one predictive statistical analysis under the fixed contract. No endpoint changes, target aliases, test access or claims of causality. Groups are contract units, not proof of independence.",
    "analysis_program": "Implement the guarded plan. Put starting coefficients only in initial, never in expression. The host fits on all train rows; dev is selection only. Use only planned inputs, their normalized kernels and supplied host states. No external fitted state, new kernels or arbitrary Python.",
    "analysis_repair": "Repair the concrete rejected or failed analysis using its recorded diagnostics. Do not repeat the unchanged expression and starting values, alter the plan, or add hidden fitted state. This is the only analysis repair.",
    "statistical_review": "Review the frozen executed analysis and computed facts for dependence, assumptions, scope and extrapolation. Cite the exact successful experiment and facts hash. Keep interpretation qualitative; no invented confidence intervals, p-values or test assessment. The analysis cannot be refitted.",
    "evidence_report": "Write a backward-traceable development report. Copy the facts hash, nominated candidate IDs and exact cohort counts. Every numeric literal in headings, section templates and limitations must use {{fact_name}}. Include {{development_error}} and {{baseline_development_error}}. Cite all supplied limitation IDs; their source prose remains unreviewed. No test, novelty or causal claim. Qualitative meaning is not validated by the number guard.",
    "report_repair": "Repair the report using the supplied guard errors. The frozen analysis, computed facts and nominations cannot change or be refitted. Preserve all limitation IDs. Use computed placeholders for every numeric literal in headings, section templates and limitations.",
}


def strings(value):
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(v, str) and bool(v.strip()) for v in value)
    )


def verified_facts(host, card):
    """Re-execute the bound program without fitting; bind statistics to full cohorts.

    The training-mean comparator is an explicitly recorded diagnostic statistic, not
    an additional candidate or optimization. Residual SD uses ddof=0 and is not a
    parameter interval or independent-sample uncertainty estimate.
    """
    if card.get("candidate_id") != sha({k: v for k, v in card.items() if k != "candidate_id"}):
        raise ValueError("Statistical candidate mutation")
    if card["context"] != host.context:
        raise ValueError("Statistical candidate context mismatch")
    if host.context != {
        "task_sha256": sha(host.task),
        "train_sha256": sha(host.train),
        "dev_sha256": sha(host.dev),
    }:
        raise ValueError("Statistical input records mutated")
    program = card["program"]
    verify_program(program, host.registry)
    source = card["final_fit_source"]
    if bool(program["specification"]["parameters"]) != bool(source):
        raise ValueError("Missing or spurious fitted-state source")
    if source:
        artifact = host.registry.artifacts[source]
        if (
            sha(artifact) != source
            or artifact["program_sha256"] != program["sha256"]
            or artifact["train_sha256"] != host.context["train_sha256"]
            or artifact["values"] != program["specification"]["parameters"]
            or artifact["kind"] != "train_fitted"
            or artifact["scope"] != "train"
        ):
            raise ValueError("Statistical fit-source binding mismatch")
    tp, dp = (execute_program(program, x, host.registry) for x in (host.X, host.D))
    if not validity(tp, host.task).all() or not validity(dp, host.task).all():
        raise ValueError("Statistical replay has invalid coverage")
    metric = host.task["metric"]["primary"]
    groups = [r["group"] for r in host.dev]
    training_error = loss(tp, host.y, metric, [r["group"] for r in host.train])
    development_error = loss(dp, host.dy, metric, groups)
    residual = dp - host.dy
    sd, mean_residual = float(np.std(residual)), float(np.mean(residual))
    for observed, expected in (
        (training_error, card["train_error"]),
        (development_error, card["dev_error"]),
        (sd, card["residuals"]["std"]),
        (mean_residual, card["residuals"]["mean"]),
    ):
        if observed != expected:
            raise ValueError("Stored diagnostic differs from deterministic statistical replay")
    mean = float(np.mean(host.y))
    comparator = {
        "kind": "train_statistic",
        "operation": "numpy_mean",
        "value": mean,
        "train_sha256": host.context["train_sha256"],
        "output": host.task["output"],
        "rows": len(host.y),
        "numpy_version": np.__version__,
        "use": "matched development diagnostic only, never a nominated rule",
    }
    comparator["sha256"] = sha(comparator)
    values = cohort_context(host)["verified_counts"] | {
        "training_error": training_error,
        "development_error": development_error,
        "baseline_development_error": loss(np.full(len(host.dev), mean), host.dy, metric, groups),
        "residual_mean": mean_residual,
        "residual_standard_deviation": sd,
        "free_parameters": program["simplicity"]["free_parameters"],
        "learned_scalars": program["simplicity"]["learned_scalar_count"],
        "preprocessing_scalars": program["simplicity"]["train_statistic_scalars"],
        "weighted_operators": program["simplicity"]["weighted_operator_count"],
    }
    bundle = {
        "policy": FACT_POLICY,
        "candidate_id": card["candidate_id"],
        "program_sha256": program["sha256"],
        "fit_source_sha256": source,
        "context": copy.deepcopy(host.context),
        "numpy_version": np.__version__,
        "metric": metric,
        "aggregation": "equal-weight group mean of point loss; square root after aggregation for rmse",
        "comparator": comparator,
        "predictions_sha256": {"train": sha(tp.tolist()), "dev": sha(dp.tolist())},
        "values": values,
        "computations": {
            "cohort_counts": "exact full partition lengths and distinct group IDs",
            "losses": "principia_asd.evaluate.metrics.loss with contract groups and metric",
            "residuals": "dev prediction minus target, numpy.mean and numpy.std(ddof=0)",
            "complexity": "verified fully expanded bound-program simplicity",
        },
        "prediction_rows": len(host.train) + len(host.dev),
        "additional_fits": 0,
        "optimizer_evaluations": 0,
        "private_test_access": False,
        "uncertainty_assessment": "not_assessed",
        "scope": "development diagnostics only; residual spread is not inferential uncertainty",
    }
    bundle["sha256"] = sha(bundle)
    return bundle


def checked_report(report, bundle, host, nominated_ids, limitation_ids):
    """Check literal provenance, exact identity and fixed coverage; not semantics."""
    errors, sections, limitations, references = [], [], [], set()
    if set(report) != set(CONTRACTS["evidence_report"]):
        errors.append("Report keys do not match the frozen contract")
    if bundle["sha256"] != sha({k: v for k, v in bundle.items() if k != "sha256"}):
        raise ValueError("Computed facts mutation")
    if report.get("facts_sha256") != bundle["sha256"]:
        errors.append("Report cites a different facts bundle")
    if not exact_cohort_report(report.get("observed_cohort"), host):
        errors.append("Reported cohort does not match executed full partitions")
    for key, expected in (("candidate_ids", nominated_ids), ("limitation_ids", limitation_ids)):
        given = report.get(key)
        if (
            not isinstance(given, list)
            or not all(isinstance(v, str) for v in given)
            or sorted(given) != sorted(expected)
        ):
            errors.append("Report must cite every " + key + " exactly once")

    def expand(text):
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            errors.append("Invalid or oversized report text")
            return ""
        refs = REFERENCE.findall(text)
        remainder = REFERENCE.sub("", text)
        if any(c.isnumeric() for c in remainder) or "{" in remainder or "}" in remainder:
            errors.append("Unlinked numeric literal or malformed computed reference")
        if any(key not in bundle["values"] for key in refs):
            errors.append("Uncomputed report quantity")
            return ""
        references.update(refs)
        return REFERENCE.sub(lambda m: str(bundle["values"][m.group(1)]), text)

    raw_sections = report.get("sections")
    if not isinstance(raw_sections, list) or not 1 <= len(raw_sections) <= 6:
        errors.append("Report needs one to six sections")
    else:
        for section in raw_sections:
            if not isinstance(section, dict) or set(section) != {"heading", "template"}:
                errors.append("Invalid section schema")
                continue
            sections.append(
                {"heading": expand(section["heading"]), "text": expand(section["template"])}
            )
    if not strings(report.get("limitations")):
        errors.append("Report needs scientific limitations")
    else:
        limitations = [expand(text) for text in report["limitations"]]
    if not {"development_error", "baseline_development_error"}.issubset(references):
        errors.append("Report omits the matched development comparison")
    return {
        "valid": not errors,
        "errors": errors,
        "sections": sections if not errors else [],
        "limitations": limitations if not errors else [],
        "computed_references": sorted(references),
        "facts_sha256": bundle["sha256"],
        "scope": "Literal-number provenance and executed identity only; qualitative meaning, spelled-out numbers, citations and causal or novelty claims remain unreviewed",
    }


class BoundDataToPaper(BoundEngine):
    policy = POLICY
    request_tag = "paper-bound-v1"

    def __init__(self, *args, limits=None, **kwargs):
        super().__init__(*args, limits={"max_calls": 6, "max_fits": 2} | (limits or {}), **kwargs)
        self.configuration.pop("sha256")
        self.configuration.update(
            method_id="data_to_paper",
            source_revision=REVISION,
            source_url=SOURCE,
            license="MIT",
            contracts_sha256=sha(CONTRACTS),
            instructions_sha256=sha(INSTRUCTIONS),
            facts_policy=FACT_POLICY,
            weak_prior_fits=0,
            rounds=0,
            local_compositions_per_round=0,
            planned_analyses=1,
            failed_analysis_repairs=1,
            report_repairs=1,
            context_policy="complete-guarded-analysis-and-statistics-v1",
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
        self._stage("paper_inventory", fitting_attempts=self.host.fits)

    def _limitations(self):
        return [
            {"id": f"{h['name']}:{i}", "text": text, "review": "not_assessed"}
            for h in self._records("paper_handoff")
            if h["name"] in ("analysis_plan", "statistical_review")
            for i, text in enumerate(h["output"].get("limitations", []))
            if isinstance(text, str)
        ]

    def _system(self, role):
        return (
            super()._system(role)
            + " Follow the data-to-paper stage_contract exactly. Only the planned analysis may be fitted. Reports use computed number references."
        )

    def _context(self, role, instruction, *, frozen=None):
        context = copy.deepcopy(super()._context(role, INSTRUCTIONS[instruction], frozen=frozen))
        context.pop("development_feedback", None)
        base = {"analysis_repair": "analysis_program", "report_repair": "evidence_report"}.get(
            instruction, instruction
        )
        stats = self._records("paper_statistics")
        context.update(
            paper_stage=instruction,
            stage_contract=copy.deepcopy(CONTRACTS[base]),
            cohort=cohort_context(self.host),
            inventory=self._inventory(),
            prediction_requirements=prediction_requirements(self.host.task),
            operator_arities={k: v[1] for k, v in FUNCS.items()},
            preceding_handoffs=self._records("paper_handoff"),
            experiments=self._records("paper_experiment"),
            computed_facts=stats[-1]["bundle"] if stats else None,
            report_guard_feedback=self._records("paper_report_guard"),
            retained_limitations=self._limitations(),
            private_test_access=False,
        )
        if frozen:
            context["frozen_evidence"]["candidates"] = [
                candidate_packet(c) for c in frozen["candidates"]
            ]
        return context

    def _handoff(self, name, frozen=None):
        role = ROLES[name]
        context_hash = sha(self._context(role, name, frozen=frozen))
        output = self._ask(role, name, frozen=frozen)
        self._stage(
            "paper_handoff",
            name=name,
            role=role,
            model=self.roles[role],
            input_sha256=context_hash,
            output=output,
            output_sha256=sha(output),
        )
        return output

    def _plan_guard(self, plan):
        errors = plan_errors(plan, self.host.task)
        if set(plan) != set(CONTRACTS["analysis_plan"]) or not strings(plan.get("limitations")):
            errors.append("Plan schema or limitations are invalid")
        self._stage("paper_plan_guard", valid=not errors, errors=errors)
        return not errors

    def _analysis(self, rule, plan, experiment_id):
        before = (
            self.host.fits,
            self.host.optimizer_evaluations,
            len(self.host.seen),
            len(self.host.failures),
            len(self.rejections),
        )
        card = None
        try:
            if set(rule) != set(CONTRACTS["analysis_program"]) or not isinstance(
                rule["initial"], dict
            ):
                raise ValueError("Analysis requires exactly expression and initial")
            program = compile_program(
                rule["expression"],
                self.host.inputs,
                rule["initial"],
                self._bindings(rule["expression"]),
                self.host.registry,
                kernels=self.kernels,
            )
            used = {
                n.id
                for n in ast.walk(ast.parse(program["expression"], mode="eval"))
                if isinstance(n, ast.Name)
            }
            if (used & set(self.host.inputs)) - set(plan["inputs"]):
                raise ValueError("Analysis uses an input excluded from the guarded plan")
            # Normalization state can reveal an unplanned measurement even without
            # its raw symbol, so validate expanded state lineage as well.
            for state in program["states"].values():
                artifact = self.host.registry.artifacts[state["artifact_sha256"]]
                if artifact.get("input") and artifact["input"] not in plan["inputs"]:
                    raise ValueError("Analysis uses state derived from an unplanned input")
            identity = sha(
                {
                    "expression": ast.dump(ast.parse(rule["expression"], mode="eval")),
                    "initial": rule["initial"],
                }
            )
            if any(e["request_identity"] == identity for e in self._records("paper_experiment")):
                raise ValueError("Analysis repair repeats the rejected program")
            card = self._fit(rule, experiment_id)
        except (ValueError, TypeError, KeyError, SyntaxError) as exc:
            self.rejections.append({"stage": experiment_id, "reason": str(exc)[:500]})
        try:
            identity = sha(
                {
                    "expression": ast.dump(ast.parse(rule.get("expression"), mode="eval")),
                    "initial": rule.get("initial"),
                }
            )
        except (ValueError, TypeError, SyntaxError):
            identity = sha(rule)
        result = {
            "experiment_id": experiment_id,
            "program": copy.deepcopy(rule),
            "program_sha256": sha(rule),
            "request_identity": identity,
            "status": "complete" if card else "failed_or_rejected",
            "structure_entered": len(self.host.seen) > before[2],
            "fitting_attempts": self.host.fits - before[0],
            "optimizer_evaluations": self.host.optimizer_evaluations - before[1],
            "failures": [failure_packet(f) for f in self.host.failures[before[3] :]],
            "rejections": copy.deepcopy(self.rejections[before[4] :]),
            "result": candidate_packet(card) if card else None,
        }
        self._stage("paper_experiment", **result)
        return result

    def _statistics(self, candidate_id):
        cpu, wall = time.process_time(), time.monotonic()
        bundle = verified_facts(self.host, self.host.candidates[candidate_id])
        self._stage(
            "paper_statistics",
            bundle=bundle,
            accounting={
                "prediction_executions": 2,
                "prediction_rows": bundle["prediction_rows"],
                "fitting_attempts": 0,
                "optimizer_evaluations": 0,
                "cpu_seconds": time.process_time() - cpu,
                "wall_seconds": time.monotonic() - wall,
                "scope": "post-freeze deterministic statistical replay, in addition to host fit accounting",
            },
        )
        return bundle

    def _review_guard(self, review, experiment_id, bundle):
        valid = (
            set(review) == set(CONTRACTS["statistical_review"])
            and review["experiment_ids"] == [experiment_id]
            and review["facts_sha256"] == bundle["sha256"]
            and strings(review["limitations"])
            and isinstance(review["interpretation"], str)
            and bool(review["interpretation"].strip())
        )
        self._stage("paper_review_guard", valid=bool(valid))
        return valid

    def _report_guard(self, report, bundle, ids):
        checked = checked_report(
            report, bundle, self.host, ids, [v["id"] for v in self._limitations()]
        )
        self._stage("paper_report_guard", **checked)
        return checked

    def run(self):
        if self.result is not None:
            return copy.deepcopy(self.result)
        failure, report, nomination, bundle = None, None, None, None
        try:
            self.step("initialize", "local", self._initialize)
            plan = self.step("analysis_plan", "provider", partial(self._handoff, "analysis_plan"))
            valid_plan = self.step("plan_guard", "local", partial(self._plan_guard, plan))
            experiment = None
            if valid_plan:
                for i, name in enumerate(("analysis_program", "analysis_repair")):
                    rule = self.step(name, "provider", partial(self._handoff, name))
                    experiment = self.step(
                        f"analysis-{i + 1}",
                        "local",
                        partial(self._analysis, rule, plan, f"analysis-{i + 1}"),
                    )
                    if experiment["result"]:
                        break
            nomination = self.step("nominate", "local", self._nominate)
            if experiment and experiment["result"]:
                cid = experiment["result"]["candidate_id"]
                bundle = self.step("computed_statistics", "local", partial(self._statistics, cid))
                ids = [
                    s["candidate_id"]
                    for s in nomination["selection"]["nominations"]
                    if s["candidate_id"]
                ]
                frozen = nomination | {"candidates": [self.host.candidates[c] for c in ids]}
                review = self.step(
                    "statistical_review",
                    "provider",
                    partial(self._handoff, "statistical_review", frozen),
                )
                self.step(
                    "review_guard",
                    "local",
                    partial(self._review_guard, review, experiment["experiment_id"], bundle),
                )
                for i, name in enumerate(("evidence_report", "report_repair")):
                    report = self.step(name, "provider", partial(self._handoff, name, frozen))
                    checked = self.step(
                        f"report_guard-{i + 1}",
                        "local",
                        partial(self._report_guard, report, bundle, ids),
                    )
                    if checked["valid"]:
                        break
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
            receipt = {
                "host_sha256": frozen["sha256"],
                "selection": selection,
                "configuration_sha256": self.configuration["sha256"],
            }
            receipt["sha256"] = sha(receipt)
            nomination = {"selection": selection, "nomination_freeze": receipt}
        guards = {
            key: self._records(stage)
            for key, stage in (
                ("plan", "paper_plan_guard"),
                ("review", "paper_review_guard"),
                ("report", "paper_report_guard"),
            )
        }
        checks = {
            "guarded_plan": bool(guards["plan"] and guards["plan"][-1]["valid"]),
            "executed_analysis": any(e["result"] for e in self._records("paper_experiment")),
            "replayed_statistics": bundle is not None,
            "critic_links_executed_statistics": bool(
                guards["review"] and guards["review"][-1]["valid"]
            ),
            "traceable_report_after_freeze": bool(
                guards["report"] and guards["report"][-1]["valid"] and self.host.closed
            ),
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
            "handoffs": self._records("paper_handoff"),
            "experiments": self._records("paper_experiment"),
            "computed_facts": bundle,
            "statistical_accounting": [r["accounting"] for r in self._records("paper_statistics")],
            "retained_limitations": self._limitations(),
            "model_requests": self.requests,
            "trace": self.trace,
            "rejections": self.rejections,
            "failure": failure,
            "report": report,
            "verified_report": guards["report"][-1] if guards["report"] else None,
            "report_review": "not_assessed",
            "ranking_authorized": False,
            "scientific_review": "not_assessed",
        }
        self.result["sha256"] = sha(self.result)
        return copy.deepcopy(self.result)
