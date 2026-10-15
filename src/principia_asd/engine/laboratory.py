"""Agent Laboratory adaptation: recorded handoffs and feedback-conditioned experiments.

This is a restricted-expression, local-context adaptation, not upstream execution.
Scientific validity is assessed separately from this algorithm-conformance receipt.
"""

from __future__ import annotations

from ..io import sha
from .evidence import cohort_context, exact_cohort_report
from .expression import structural_key

REVISION = "d9017d90e329112d2a80b7712f37ee9094d2cd27"
ADAPTATION_VERSION = "agent-laboratory-adaptation-v2"
SOURCE = f"https://github.com/SamuelSchmidgall/AgentLaboratory/tree/{REVISION}"


def run_laboratory(search, ask, proposal, stage, roles):
    handoffs = []
    experiments = []

    def handoff(name, role, instruction, context, required):
        context = context | {"cohort": cohort_context(search)}
        stage("laboratory_stage", message=name.replace("_", " "), role=role, model=roles[role])
        output = ask(role, instruction, context)
        valid = all(isinstance(output.get(k), kind) and bool(output[k]) for k, kind in required)
        handoffs.append(
            {
                "stage": name,
                "role": role,
                "model": roles[role],
                "input_sha256": sha(context),
                "output": output,
                "output_sha256": sha(output),
                "schema_valid": valid,
            }
        )
        stage(
            "laboratory_handoff",
            message=name.replace("_", " "),
            valid=valid,
            output_sha256=sha(output),
        )
        return output

    def experiment(program, experiment_id):
        before = (search.fits, search.optimizer_evaluations, len(search.seen), len(search.failures))
        card = proposal(program, experiment_id)
        record = {
            "experiment_id": experiment_id,
            "program": program,
            "program_sha256": sha(program),
            "status": "complete" if card else "failed_or_not_executed",
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
        if not card and not record["failures"]:
            record["failures"] = [{"reason": "Duplicate proposal or exhausted local search budget"}]
        experiments.append(record)
        stage(
            "laboratory_experiment_result",
            message=experiment_id,
            status=record["status"],
            fitting_attempts=record["fitting_attempts"],
            optimizer_evaluations=record["optimizer_evaluations"],
        )
        return record

    brief = handoff(
        "research_brief",
        "planner",
        'Review the supplied task and train measurements. Return {"question":"...", '
        '"hypotheses":["..."], "limitations":["..."]}. Nominate competing explanations. '
        "This is a local evidence review; do not invent citations or claim live literature access.",
        {"evidence_scope": "Permitted train/development only", "live_literature": False},
        [("question", str), ("hypotheses", list)],
    )
    plan = handoff(
        "experiment_plan",
        "planner",
        "Turn the research brief into an executable two-experiment plan. Return "
        '{"objective":"...", "experiments":["initial program", "feedback-conditioned revision"], '
        '"selection_criterion":"...", "risks":["..."]}. Fit on train; select on dev. '
        "Use the contract metric; do not propose test access or a new target.",
        {"research_brief": brief},
        [("objective", str), ("experiments", list), ("selection_criterion", str)],
    )
    initial = handoff(
        "initial_engineering",
        "coder",
        'Implement the initial planned experiment as {"expression":"...", '
        '"parameters":{"p0":0,"p1":1}, "rationale":"..."}. Use only permitted numeric '
        "operators and inputs. The host fits parameters on train and executes dev predictions.",
        {"research_brief": brief, "experiment_plan": plan},
        [("expression", str)],
    )
    first = experiment(initial, "experiment-1")
    critique = handoff(
        "experimental_critique",
        "critic",
        "Critique the actual executed experiment, including failures and residual structure. "
        'Return {"experiment_ids":["experiment-1"], "issues":["..."], '
        '"revision":"specific implementable change or competing explanation"}. '
        "Describe uncertainty honestly; a good predictive fit does not identify a mechanism.",
        {"research_brief": brief, "experiment_plan": plan, "experiment": first},
        [("experiment_ids", list), ("revision", str)],
    )
    revised = handoff(
        "revised_engineering",
        "coder",
        "Execute the critique by proposing a structurally different program. Return "
        '{"expression":"...", "parameters":{"p0":0,"p1":1}, "rationale":"..."}. '
        "Repair invalid programs or test a concrete competing explanation. Merely returning "
        "the same formula or changing fitted starting coefficients is not an experiment revision.",
        {"experiment_plan": plan, "previous_experiment": first, "critique": critique},
        [("expression", str)],
    )
    experiment(revised, "experiment-2")
    report = handoff(
        "evidence_report",
        "reporter",
        'Report only these actual development experiments. Return {"summary":"...", '
        '"experiment_ids":["experiment-1","experiment-2"], "limitations":["..."], '
        '"next_tests":["..."], "observed_cohort": {"training_rows":0,"development_rows":0,'
        '"training_groups":0,"development_groups":0}}. Replace these count placeholders by '
        "EXACTLY copying cohort.verified_counts; the small examples_train preview is not the fitting cohort. "
        "Cite both experiment IDs, retain failures, and distinguish observed predictions from hypotheses. "
        "No private-test, originality or causal claim. Your prose remains an unreviewed interpretation.",
        {
            "research_brief": brief,
            "experiment_plan": plan,
            "critique": critique,
            "experiments": experiments,
            "selection": search.diagnostics(),
        },
        [("summary", str), ("experiment_ids", list), ("limitations", list)],
    )

    try:
        changed = structural_key(initial.get("expression", "")) != structural_key(
            revised.get("expression", "")
        )
    except (ValueError, SyntaxError, TypeError):
        # A rejected initial program can be repaired into a valid, executed second one.
        changed = bool(experiments[1]["result"]) and initial != revised
    checks = {
        "all_six_handoffs_valid": len(handoffs) == 6 and all(h["schema_valid"] for h in handoffs),
        "two_distinct_programs_locally_checked": all(e["structure_entered"] for e in experiments),
        "feedback_conditioned_structural_revision": changed,
        "critique_references_executed_experiment": critique.get("experiment_ids")
        == ["experiment-1"],
        "report_references_all_experiments": isinstance(report.get("experiment_ids"), list)
        and all(isinstance(x, str) for x in report["experiment_ids"])
        and sorted(report["experiment_ids"]) == ["experiment-1", "experiment-2"],
        "at_least_one_valid_experiment": any(e["result"] for e in experiments),
        "reported_cohort_matches_executed_data": exact_cohort_report(
            report.get("observed_cohort"), search
        ),
    }
    complete = all(checks.values())
    stage(
        "laboratory_conformance",
        message="Required algorithm executed" if complete else "Required algorithm incomplete",
        checks=checks,
    )
    return {
        "method_id": "agent_laboratory",
        "adaptation_version": ADAPTATION_VERSION,
        "source_url": SOURCE,
        "source_revision": REVISION,
        "license": "MIT",
        "execution_scope": "CPU numerical expression programs; controlled local context",
        "cohort": cohort_context(search),
        "handoffs": handoffs,
        "experiments": experiments,
        "conformance": {
            "status": "complete" if complete else "incomplete_method_execution",
            "checks": checks,
        },
        "scientific_review": "not_assessed",
    }
