"""Guarded, backward-traceable data-to-paper adaptation for numeric task contracts."""

from __future__ import annotations

import re

import numpy as np

from ..evaluate.metrics import loss
from ..io import sha
from .evidence import cohort_context, exact_cohort_report, prediction_requirements
from .expression import FUNCS, parse, structural_key

REVISION = "81df14c4b9600466e645c3b2b336cc54daa3df3a"
ADAPTATION_VERSION = "data-to-paper-adaptation-v2"
SOURCE = f"https://github.com/Technion-Kishony-lab/data-to-paper/tree/{REVISION}"
REFERENCE = re.compile(r"\{\{([a-z_]+)\}\}")


def program_identity(program):
    expression = program.get("expression")
    try:
        structure = structural_key(expression)
    except (SyntaxError, ValueError, TypeError):
        structure = ["unparsed", expression]
    return sha([structure, program.get("parameters", {})])


def plan_errors(plan, task):
    errors = []
    fields = plan.get("inputs")
    if (
        not isinstance(fields, list)
        or not fields
        or not all(isinstance(x, str) for x in fields)
        or len(set(fields)) != len(fields)
        or not set(fields).issubset(task["inputs"])
    ):
        errors.append("Plan inputs must be distinct permitted measurements")
    for key, expected in {
        "output": task["output"],
        "metric": task["metric"]["primary"],
        "fit_partition": "train",
        "selection_partition": "dev",
    }.items():
        if plan.get(key) != expected:
            errors.append("Plan changes the contract's " + key)
    if not isinstance(plan.get("hypothesis"), str) or not plan["hypothesis"].strip():
        errors.append("Plan needs an explicit predictive hypothesis")
    return errors


def computed_facts(search, card):
    cohort = cohort_context(search)["verified_counts"]
    lineage = {
        "train_records_sha256": sha(search.train),
        "development_records_sha256": sha(search.dev),
        "fitted_program_sha256": sha(
            {"expression": card["expression"], "parameters": card["parameters"]}
        ),
        "metric": search.metric,
        "final_test_access": False,
    }
    values = cohort | {
        "training_error": card["train_error"],
        "development_error": card["dev_error"],
        "baseline_development_error": loss(
            np.full(len(search.dev), search.mean), search.dy, search.metric, search.dg
        ),
        "residual_standard_deviation": card["residuals"]["std"],
        "free_parameters": len(card["parameters"]),
    }
    return {
        key: {
            "value": value,
            "scope": "development only",
            "computation": "principia_asd.engine.data_to_paper.computed_facts:" + key,
            "lineage": lineage,
        }
        for key, value in values.items()
    }


def check_report(report, facts, search):
    """Expand only computed references; unlinked numeric literals never enter the report."""
    errors, rendered, referenced = [], [], set()
    if not exact_cohort_report(report.get("observed_cohort"), search):
        errors.append("Reported cohort does not match the executed data")
    sections = report.get("sections")
    if not isinstance(sections, list) or not 1 <= len(sections) <= 6:
        return {
            "valid": False,
            "errors": errors + ["Report needs one to six sections"],
            "sections": [],
        }
    for section in sections:
        if not isinstance(section, dict):
            errors.append("Report section must be an object")
            continue
        heading, template = section.get("heading"), section.get("template")
        if not isinstance(heading, str) or not isinstance(template, str) or len(template) > 4000:
            errors.append("Report heading/template is invalid or too large")
            continue
        refs = REFERENCE.findall(template)
        remainder = REFERENCE.sub("", template)
        if re.search(r"[0-9]", heading + remainder) or "{" in remainder or "}" in remainder:
            errors.append("Unlinked numeric literal or malformed computed reference")
        if any(ref not in facts for ref in refs):
            errors.append("Report cites an uncomputed quantity")
            continue
        referenced.update(refs)
        rendered.append(
            {
                "heading": heading,
                "text": REFERENCE.sub(lambda match: str(facts[match.group(1)]["value"]), template),
                "computed_references": sorted(set(refs)),
            }
        )
    if not {"development_error", "baseline_development_error"}.issubset(referenced):
        errors.append("Report omits the matched development comparison")
    if not isinstance(report.get("limitations"), list) or not report["limitations"]:
        errors.append("Report must retain scientific limitations")
    return {
        "valid": not errors,
        "errors": errors,
        "sections": rendered if not errors else [],
        "computed_references": sorted(referenced),
        "scope": "Numeric-literal provenance and exact cohort counts; qualitative meaning remains unreviewed",
    }


def run_data_to_paper(search, ask, proposal, stage, roles):
    handoffs, experiments = [], []
    cohort = cohort_context(search)
    search.capture_failure_diagnostics = True
    language = {
        "functions": {name: {"arity": info[1]} for name, info in FUNCS.items()},
        "operators": ["+", "-", "*", "/", "**", "<", "<=", ">", ">=", "==", "!="],
        "parameter_fitting": "Unconstrained least-squares; initial parameter signs are not bounds",
        "prediction_requirements": prediction_requirements(search.task),
        "domain_notes": [
            "Use only listed functions; clipping can be written as minimum(upper,maximum(lower,value))",
            "A negative base to a noninteger power is invalid over the real numbers",
            "log requires positive arguments; log1p requires arguments above negative one",
            "where evaluates both branches; it does not protect invalid intermediate operations",
            "A valid domain repair needs scientific justification; numerical clipping alone does not establish it",
        ],
    }

    def handoff(name, role, instruction, context):
        context = context | {"cohort": cohort}
        stage("paper_stage", message=name.replace("_", " "), role=role, model=roles[role])
        output = ask(role, instruction, context)
        handoffs.append(
            {
                "stage": name,
                "role": role,
                "model": roles[role],
                "input_sha256": sha(context),
                "output_sha256": sha(output),
                "output": output,
                "schema_valid": True,
            }
        )
        return output

    checks = {
        "analysis_plan_guard": False,
        "executed_analysis": False,
        "critic_received_executed_analysis": False,
        "traceable_report_guard": False,
    }
    evidence = {
        "method_id": "data_to_paper",
        "adaptation_version": ADAPTATION_VERSION,
        "source_url": SOURCE,
        "source_revision": REVISION,
        "license": "MIT",
        "execution_scope": "Controlled numeric analysis and traceable development report; no live literature or full paper",
        "cohort": cohort,
        "handoffs": handoffs,
        "experiments": experiments,
        "scientific_review": "not_assessed",
        "analysis_uncertainty": "not_assessed",
    }

    def finish():
        complete = all(checks.values())
        evidence["conformance"] = {
            "status": "complete" if complete else "incomplete_method_execution",
            "checks": checks,
        }
        stage(
            "paper_conformance",
            message="Required analysis and numeric provenance executed"
            if complete
            else "Required analysis/report guards incomplete",
            checks=checks,
        )
        return evidence

    stage(
        "paper_measurement_inventory",
        message="Inventory computed from full train/dev partitions",
        cohort=cohort,
        inputs=search.inputs,
    )
    plan = handoff(
        "analysis_plan",
        "planner",
        'Plan one predictive statistical analysis of the fixed task. Return {"hypothesis":"...", '
        '"inputs":["permitted input"], "output":"exact task output", "metric":"exact primary metric", '
        '"fit_partition":"train", "selection_partition":"dev", "limitations":["..."]}. '
        "Use measured inputs only; the declared grouping is not proof of independent observations. "
        "No endpoint changes, final-test access, p-values or causal identification.",
        {
            "measurement_inventory": {
                "inputs": search.inputs,
                "units": search.task.get("input_units", {}),
                "output_units": search.task.get("output_units"),
                "evidence_window": search.task.get("observation_window"),
            }
        },
    )
    errors = plan_errors(plan, search.task)
    evidence["plan_guard_errors"] = errors
    checks["analysis_plan_guard"] = not errors
    handoffs[-1]["schema_valid"] = not errors
    stage("paper_plan_guard", message="Analysis plan checked against the contract", errors=errors)
    if errors:
        return finish()

    # Repair is allowed only when the initial executable analysis fails its guards.
    for attempt in range(2):
        program = handoff(
            "analysis_program" if attempt == 0 else "analysis_repair",
            "coder",
            'Implement the guarded plan as {"expression":"...", "parameters":{"p0":0,"p1":1}, '
            '"rationale":"..."}. Use only the planned inputs. The host fits on every training row, '
            "then computes equal-group development loss. If a previous program failed, repair that "
            "concrete error using its invalid counts, ranges and fitted parameters. Log loss requires "
            "strictly positive outputs even if positive_prediction is false. Use only expression_language "
            "functions. Do not repeat an unchanged rejected program or change only its explanation. "
            "Do not include external fitted state or use development rows for fitting.",
            {"analysis_plan": plan, "expression_language": language, "previous_failures": experiments},
        )
        before = (search.fits, search.optimizer_evaluations, len(search.seen), len(search.failures))
        try:
            parse(program.get("expression"), plan["inputs"], list(program.get("parameters", {})))
            if experiments:
                previous = experiments[-1]["program"]
                if program_identity(program) == program_identity(previous):
                    raise ValueError("Repair repeats the rejected program; no additional fit performed")
            card = proposal(program, f"guarded-analysis-{attempt + 1}")
        except (ValueError, TypeError, SyntaxError) as exc:
            search.failures.append({"origin": "analysis_guard", "reason": str(exc)[:500]})
            card = None
        experiments.append(
            {
                "experiment_id": f"analysis-{attempt + 1}",
                "program": program,
                "program_sha256": sha(program),
                "status": "complete" if card else "failed_or_rejected",
                "structure_entered": len(search.seen) > before[2],
                "fitting_attempts": search.fits - before[0],
                "optimizer_evaluations": search.optimizer_evaluations - before[1],
                "failures": search.failures[before[3] :],
                "result": {
                    k: card[k]
                    for k in (
                        "expression",
                        "parameters",
                        "train_error",
                        "dev_error",
                        "residuals",
                        "simplicity",
                    )
                }
                if card
                else None,
            }
        )
        stage(
            "paper_analysis_guard",
            message=experiments[-1]["experiment_id"],
            status=experiments[-1]["status"],
            failures=experiments[-1]["failures"],
        )
        if card:
            checks["executed_analysis"] = True
            break
    if not checks["executed_analysis"]:
        return finish()

    facts = computed_facts(search, card)
    evidence["computed_facts"] = facts
    critique = handoff(
        "statistical_review",
        "critic",
        "Review this executed statistical analysis for dependence, extrapolation, assumptions and "
        'unjustified interpretation. Return {"experiment_ids":["the actual successful analysis ID"], '
        '"limitations":["..."], "interpretation":"qualitative, unreviewed"}. '
        "Retain unfavorable evidence. No invented intervals, p-values or test assessment.",
        {"analysis_plan": plan, "experiments": experiments, "computed_facts": facts},
    )
    checks["critic_received_executed_analysis"] = critique.get("experiment_ids") == [
        experiments[-1]["experiment_id"]
    ]
    handoffs[-1]["schema_valid"] = checks["critic_received_executed_analysis"]
    reports = []
    for attempt in range(2):
        report = handoff(
            "evidence_report" if attempt == 0 else "report_repair",
            "reporter",
            'Write a backward-traceable development report. Return {"sections":[{"heading":"Results", '
            '"template":"The development loss is {{development_error}}; the matched training-mean comparator '
            'loss is {{baseline_development_error}}."}], "observed_cohort": {"training_rows":0,'
            '"development_rows":0,"training_groups":0,"development_groups":0}, "limitations":["..."]}. '
            "Copy observed_cohort EXACTLY from cohort.verified_counts. Use {{fact_name}} for EVERY numeric "
            "literal in section headings/text; never write literal numbers or formula coefficients there. "
            "The host resolves facts to exact executed values. Include both development_error and "
            "baseline_development_error. Qualitative interpretation remains unreviewed; retain the critique. "
            "If guard errors are supplied, repair the report without changing or refitting the analysis.",
            {
                "analysis_plan": plan,
                "computed_facts": facts,
                "statistical_review": critique,
                "report_guard_feedback": reports[-1] if reports else None,
            },
        )
        checked = check_report(report, facts, search)
        handoffs[-1]["schema_valid"] = checked["valid"]
        reports.append({"attempt": attempt + 1, "report_sha256": sha(report), **checked})
        stage(
            "paper_report_guard",
            message="Computed references and cohort checked",
            valid=checked["valid"],
            errors=checked["errors"],
        )
        if checked["valid"]:
            checks["traceable_report_guard"] = True
            break
    evidence["report_checks"] = reports
    evidence["verified_report"] = reports[-1]
    return finish()
