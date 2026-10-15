"""A bounded Asta adaptation: evidence-conditioned tree search and belief rewards.

Independent implementation of the attributed MCTS/Beta-belief mechanism. These
LLM beliefs guide development search; they are not scientific probabilities.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.special import betaln, digamma

from ..evaluate.metrics import loss
from ..io import sha
from .evidence import cohort_context, exact_cohort_report, prediction_requirements
from .expression import parse, structural_key

REVISION = "effa4be80f94e234d3d926f4f24b6aa6064d10e7"
ADAPTATION_VERSION = "asta-autodiscovery-adaptation-v2"
SOURCE = f"https://github.com/allenai/asta-autodiscovery/tree/{REVISION}"
CONFIG = {
    "hypothesis_nodes": 4,
    "widening_k": 1.0,
    "widening_alpha": 0.5,
    "uct_exploration": 1.0,
    "belief_samples_per_phase": 2,
    "beta_base": [1.0, 1.0],
    "evidence_weight": 1.0,
    "reward": "directional_beta_kl",
    "belief_threshold": 0.5,
    "maximum_model_calls": 25,
    "maximum_program_checks": 4,
    "deduplication": "canonical_expression_structure; no semantic-equivalence claim",
    "prior_policy": "domain-knowledge expectation; no measurements or planner prose; abstention retained",
    "posterior_policy": "recorded experiment only; no prior votes or added domain evidence",
    "conformance_policy": "at least one non-abstained vote per phase for every valid experiment",
}


def belief_update(prior_votes, evidence_votes):
    """Beta counts follow paper equations 1-4; abstentions add no evidence."""
    if any(v is not None and type(v) is not bool for v in prior_votes + evidence_votes):
        raise ValueError("Belief samples must be booleans or null, never probabilities")
    a, b = CONFIG["beta_base"]
    a += sum(v is True for v in prior_votes)
    b += sum(v is False for v in prior_votes)
    c = a + sum(v is True for v in evidence_votes)
    d = b + sum(v is False for v in evidence_votes)
    before, after = a / (a + b), c / (c + d)
    kl = max(0.0, float(
        betaln(a, b) - betaln(c, d)
        + (c - a) * digamma(c) + (d - b) * digamma(d)
        + (a + b - c - d) * digamma(c + d)
    ))
    observed = any(v is not None for v in prior_votes) and any(
        v is not None for v in evidence_votes
    )
    shift = observed and (before - 0.5) * (after - 0.5) <= 0 and before != after
    return {
        "prior": {"alpha": a, "beta": b, "mean": before, "votes": prior_votes},
        "posterior": {"alpha": c, "beta": d, "mean": after, "votes": evidence_votes},
        "kl_posterior_to_prior": kl,
        "directional_shift": shift,
        "sufficient_nonabstained_samples": observed,
        "reward": kl if shift else 0.0,
        "calibration": "not_assessed",
    }


def choose_parent(nodes):
    """Return an expansion node and the actual widening/UCT decisions taken."""
    current, decisions = "root", []
    while True:
        node = nodes[current]
        children = node["children"]
        threshold = CONFIG["widening_k"] * node["visits"] ** CONFIG["widening_alpha"]
        decision = {
            "node_id": current, "visits": node["visits"], "children": list(children),
            "widening_threshold": threshold,
        }
        if not children or len(children) < threshold:
            decisions.append(decision | {"action": "expand"})
            return current, decisions
        scores = {}
        for child_id in children:
            child = nodes[child_id]
            # Each node receives its own execution visit before another selection.
            scores[child_id] = child["reward_sum"] / child["visits"] + CONFIG[
                "uct_exploration"
            ] * math.sqrt(2 * math.log(max(1, node["visits"])) / child["visits"])
        selected = max(children, key=lambda child_id: scores[child_id])
        decisions.append(decision | {"action": "descend", "uct_scores": scores, "selected": selected})
        current = selected


def backpropagate(nodes, node_id, reward):
    path = []
    while node_id is not None:
        node = nodes[node_id]
        node["visits"] += 1
        node["reward_sum"] += reward
        path.append({"node_id": node_id, "visits": node["visits"], "reward_sum": node["reward_sum"]})
        node_id = node["parent_id"]
    return path


def run_asta(search, ask, proposal, stage, roles):
    search.capture_failure_diagnostics = True
    handoffs, experiments, selections = [], [], []
    nodes = {"root": {"node_id": "root", "parent_id": None, "children": [], "visits": 0, "reward_sum": 0.0}}
    seen_structures = set()
    baseline_error = loss(np.full(len(search.dev), search.mean), search.dy, search.metric, search.dg)

    def call(name, role, instruction, context, *, observer=False, prior=False):
        stage("asta_stage", message=name.replace("_", " "), role=role, model=roles[role])
        scope = "domain_prior" if prior else "development_evidence_only"
        output = ask(role, instruction, context, include_measurements=not observer, knowledge_scope=scope)
        handoffs.append({
            "stage": name, "role": role, "model": roles[role],
            "input_sha256": sha(context), "output": output, "output_sha256": sha(output),
            "measurement_preview_included": not observer,
            "knowledge_scope": scope,
        })
        return output

    def sample_beliefs(node_id, phase, context):
        votes, valid = [], True
        for index in range(CONFIG["belief_samples_per_phase"]):
            output = call(
                f"{node_id}_{phase}_{index + 1}", "critic",
                'Independently assess the frozen operational predictive claim. Return '
                '{"belief":true,"reason":"..."}. It MUST be a JSON boolean or null, not a probability. '
                + ("Before this experiment runs, use prior domain knowledge and the task/formula to state your subjective expectation: "
                   "true if you lean toward the claim, false if you lean against it, null if you have no defensible leaning. "
                   "An expectation does not assert that the unseen development result was observed. Lack of execution evidence "
                   "alone does not prohibit a prior expectation. Do not infer results from the planner's choice of formula or invent measurements. "
                   if phase == "prior" else "Use only the recorded experiment: true for support, false for counterevidence, "
                   "null when evidence is insufficient. A failed execution is not evidence of a scientific refutation. ")
                + "Do not infer causality or novelty. Other observer samples are unavailable.",
                context, observer=True, prior=phase == "prior",
            )
            sample_ok = "belief" in output and (output["belief"] is None or type(output["belief"]) is bool)
            valid &= sample_ok
            votes.append(output.get("belief") if sample_ok else None)
            handoffs[-1]["schema_valid"] = sample_ok
        return votes, valid

    for i in range(CONFIG["hypothesis_nodes"]):
        search.check()
        node_id = f"hypothesis-{i + 1}"
        parent, decisions = choose_parent(nodes)
        selections.append({"iteration": i + 1, "parent_id": parent, "decisions": decisions})
        stage("asta_selection", message=f"Expand {parent}", decisions=decisions)
        ancestors = []
        cursor = parent
        while cursor != "root":
            ancestor = nodes[cursor]
            ancestors.append({"node_id": cursor, "hypothesis": ancestor["hypothesis"],
                              "experiment": ancestor["experiment"], "belief_update": ancestor["belief_update"]})
            cursor = ancestor["parent_id"]
        draft = call(
            f"{node_id}_nomination", "planner",
            'Nominate ONE new explanatory formula family as {"hypothesis":"...", '
            '"expression":"...", "parameters":{"p0":0,"p1":1}, "rationale":"..."}. '
            "Use all permitted train context and the supplied ancestor experiments, including failures. "
            "For a descendant, develop a specific follow-up to its parent. For a root branch, propose "
            "a competing structure. Do not repeat an existing expression. The operational claim is "
            "strictly lower development loss than a training-mean predictor, NOT mechanism or novelty. "
            "The formula structure will freeze before belief elicitation and cannot be repaired within this node.",
            {"cohort": cohort_context(search), "parent_id": parent, "ancestor_evidence": list(reversed(ancestors)),
             "existing_expressions": [e["program"].get("expression") for e in experiments],
             "prediction_requirements": prediction_requirements(search.task)},
        )
        hypothesis_valid, unique, structure = True, False, None
        try:
            parameters = draft.get("parameters", {})
            if not isinstance(parameters, dict) or len(parameters) > 8 or any(
                k not in {f"p{j}" for j in range(8)} or type(v) not in (int, float)
                or not math.isfinite(v) for k, v in parameters.items()
            ):
                raise ValueError("Invalid initial parameter map")
            if not isinstance(draft.get("hypothesis"), str) or not draft["hypothesis"].strip():
                raise ValueError("Missing hypothesis")
            parse(draft.get("expression"), search.inputs, list(parameters))
            structure = structural_key(draft["expression"])
            unique = structure not in seen_structures
            seen_structures.add(structure)
        except (ValueError, TypeError, SyntaxError):
            hypothesis_valid = False
        # The prior is isolated from planner prose, data previews and ancestor outcomes.
        frozen_claim = {
            "node_id": node_id, "expression": draft.get("expression"),
            "parameter_names": sorted(draft.get("parameters", {})) if isinstance(draft.get("parameters", {}), dict) else [],
            "operational_claim": "This expression, fitted only on train, has strictly lower dev loss than the train-mean predictor",
            "metric": search.metric, "scope": "development predictive evidence only",
        }
        prior_votes, prior_valid = sample_beliefs(node_id, "prior", {"frozen_claim": frozen_claim})
        program = call(
            f"{node_id}_engineering", "coder",
            'Implement the frozen family as {"expression":"...", "parameters":{"p0":0,"p1":1}}. '
            "Copy its expression structure and parameter names exactly. Choose finite initial values for "
            "the host's unconstrained training fit. Do not change the hypothesis after the prior was elicited. "
            "All native transformations must remain in the expression; no hidden fitted state or clipping functions.",
            {"frozen_claim": frozen_claim, "initial_proposal": draft, "cohort": cohort_context(search),
             "prediction_requirements": prediction_requirements(search.task)},
        )
        try:
            binding_valid = (hypothesis_valid and unique
                             and structure == structural_key(program.get("expression"))
                             and isinstance(program.get("parameters", {}), dict)
                             and sorted(program.get("parameters", {})) == frozen_claim["parameter_names"]
                             and all(type(v) in (int, float) and math.isfinite(v)
                                     for v in program.get("parameters", {}).values()))
        except (ValueError, TypeError, SyntaxError):
            binding_valid = False
        before = (search.fits, search.optimizer_evaluations, len(search.seen), len(search.failures))
        if binding_valid:
            card = proposal(program, node_id)
        else:
            card = None
            search.failures.append({"origin": node_id, "expression": program.get("expression"),
                                    "reason": "Invalid or repeated hypothesis, or program changed its frozen structure/parameters"})
        experiment = {
            "experiment_id": node_id, "program": program, "program_sha256": sha(program),
            "claim_sha256": sha(frozen_claim), "binding_valid": binding_valid,
            "status": "complete" if card else "failed_or_not_executed",
            "structure_entered": len(search.seen) > before[2],
            "fitting_attempts": search.fits - before[0],
            "optimizer_evaluations": search.optimizer_evaluations - before[1],
            "failures": search.failures[before[3]:],
            "result": {k: card[k] for k in ("expression", "parameters", "train_error", "dev_error", "residuals", "simplicity")}
            if card else None,
            "comparator_dev_error": baseline_error,
            "operational_claim_supported": card["dev_error"] < baseline_error if card else None,
        }
        experiments.append(experiment)
        stage("asta_experiment", message=node_id, status=experiment["status"],
              fitting_attempts=experiment["fitting_attempts"], dev_error=card["dev_error"] if card else None)
        post_votes, post_valid = sample_beliefs(
            node_id, "posterior", {"frozen_claim": frozen_claim, "executed_experiment": experiment},
        )
        belief = belief_update(prior_votes, post_votes)
        belief["samples_schema_valid"] = prior_valid and post_valid
        # Failures and invalid elicitation never earn an artificial surprise bonus.
        if not card or not belief["samples_schema_valid"]:
            belief["reward"] = 0.0
            belief["reward_exclusion"] = "Failed experiment or malformed belief samples"
        nodes[node_id] = {"node_id": node_id, "parent_id": parent, "children": [], "visits": 0,
                          "reward_sum": 0.0, "hypothesis": draft, "frozen_claim": frozen_claim,
                          "hypothesis_valid": hypothesis_valid, "unique_structure": unique,
                          "experiment": experiment, "belief_update": belief}
        nodes[parent]["children"].append(node_id)
        updates = backpropagate(nodes, node_id, belief["reward"])
        stage("asta_belief_update", message=node_id, belief_update=belief, ancestor_updates=updates)

    report = call(
        "evidence_report", "reporter",
        'Summarize the actual search as {"summary":"...", "experiment_ids":["hypothesis-1",'
        '"hypothesis-2","hypothesis-3","hypothesis-4"], "limitations":["..."], '
        '"observed_cohort":{"training_rows":0,"development_rows":0,"training_groups":0,"development_groups":0}}. '
        "Copy cohort.verified_counts exactly. Retain negative/failed experiments. Belief reward is an "
        "uncalibrated search heuristic, not accuracy, significance, novelty or scientific validation.",
        {"cohort": cohort_context(search), "tree": list(nodes.values()), "selection": search.diagnostics()},
    )
    leaves = [n for k, n in nodes.items() if k != "root"]
    checks = {
        "four_hypotheses_with_distinct_frozen_structures": len(leaves) == 4 and all(n["hypothesis_valid"] and n["unique_structure"] for n in leaves),
        "branching_and_descendant_executed": len(nodes["root"]["children"]) >= 2
        and any(n["parent_id"] != "root" and n["experiment"]["structure_entered"] for n in leaves),
        "progressive_widening_and_uct_used": any(d["action"] == "descend" for s in selections for d in s["decisions"]),
        "all_frozen_programs_locally_checked": all(e["binding_valid"] and e["structure_entered"] for e in experiments),
        "all_belief_samples_well_formed": all(n["belief_update"]["samples_schema_valid"] for n in leaves),
        "valid_experiments_have_observed_belief_updates": all(n["belief_update"]["sufficient_nonabstained_samples"] for n in leaves if n["experiment"]["result"]),
        "at_least_one_valid_experiment": any(e["result"] for e in experiments),
        "all_rewards_propagated": nodes["root"]["visits"] == 4,
        "report_references_all_experiments": report.get("experiment_ids") == [e["experiment_id"] for e in experiments],
        "reported_cohort_matches_executed_data": exact_cohort_report(report.get("observed_cohort"), search),
    }
    complete = all(checks.values())
    stage("asta_conformance", message="Required algorithm executed" if complete else "Required algorithm incomplete", checks=checks)
    return {
        "method_id": "asta_autodiscovery", "adaptation_version": ADAPTATION_VERSION,
        "source_url": SOURCE, "source_revision": REVISION, "license": "Apache-2.0",
        "configuration": dict(CONFIG), "cohort": cohort_context(search),
        "execution_scope": "Four-node CPU expression search; fixed task; development evidence only",
        "search_tree": list(nodes.values()), "selection_history": selections,
        "handoffs": handoffs, "experiments": experiments,
        "conformance": {"status": "complete" if complete else "incomplete_method_execution", "checks": checks},
        "scientific_review": "not_assessed",
    }
