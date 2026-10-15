"""AgentRxiv adaptation with isolated laboratories and auditable archive reuse.

An independently implemented, per-attempt archive replaces the public preprint
service. All scientific code is expanded in the bounded numerical expression AST.
"""

from __future__ import annotations

import ast
import copy
import math
import re
from collections import Counter

from ..io import sha
from .evidence import cohort_context, exact_cohort_report, prediction_requirements
from .expression import parse, structural_key
from .laboratory import ADAPTATION_VERSION as LAB_VERSION
from .laboratory import REVISION as LAB_REVISION
from .laboratory import run_laboratory

ADAPTATION_VERSION = "agentrxiv-adaptation-v1"
REVISION = "arXiv:2503.18102v1"
SOURCE = "https://arxiv.org/abs/2503.18102v1"
CONFIG = {
    "laboratories": 2,
    "initial_cycles_per_lab": 1,
    "cross_lab_followups": 1,
    "recipient": "lab-A",
    "retrieval": "cosine of lexical token counts; foreign completed reports only; top-1",
    "reuse": "expand donor formula in add/multiply composition; refit all visible parameters on train",
    "maximum_model_calls": 18,
    "maximum_program_checks": 6,
    "archive_lifetime": "one attempt; initially empty; published entries persisted in events and submission",
    "lab_execution": "sequential scheduling with separate scientific state; shared model-role configuration",
}


class PrivateArchive:
    def __init__(self, task_id):
        self.task_id = task_id
        self.entries = []

    def verify(self, entry):
        digest = sha(entry["content"])
        if (entry["sha256"] != digest or entry["report_id"] != "report-" + digest[:16]
                or entry["content"]["task_id"] != self.task_id):
            raise ValueError("Archive report mutation or wrong task")

    def publish(self, lab_id, cycle_id, evidence):
        if evidence["conformance"]["status"] != "complete":
            return None  # Incomplete work is retained outside the completed-report archive.
        content = {
            "task_id": self.task_id, "lab_id": lab_id, "cycle_id": cycle_id,
            "cohort": evidence["cohort"], "report": evidence["handoffs"][-1]["output"],
            "experiments": evidence["experiments"], "evidence_sha256": sha(evidence),
        }
        digest = sha(content)
        entry = {"report_id": "report-" + digest[:16], "sha256": digest, "content": copy.deepcopy(content)}
        self.entries.append(entry)
        return copy.deepcopy(entry)

    def retrieve(self, query, requester):
        if not isinstance(query, str) or not query.strip() or len(query) > 2000:
            raise ValueError("Archive query must be nonempty and bounded")

        def tokens(text):
            return Counter(re.findall(r"[a-z0-9_]+", text.lower()))

        q = tokens(query)
        matches = []
        for entry in self.entries:
            self.verify(entry)
            if entry["content"]["lab_id"] == requester:
                continue
            content = entry["content"]
            document = str(content["report"]) + " " + " ".join(
                str(e["program"].get("expression", "")) for e in content["experiments"]
            )
            t = tokens(document)
            norm = math.sqrt(sum(v * v for v in q.values()) * sum(v * v for v in t.values()))
            score = sum(v * t[k] for k, v in q.items()) / norm if norm else 0.0
            matches.append({"score": score, "entry": copy.deepcopy(entry)})
        return sorted(matches, key=lambda x: (-x["score"], x["entry"]["report_id"]))[:1]


def compose_from_report(entry, experiment_id, draft, inputs):
    """The source is expanded by the host, so a citation alone cannot satisfy reuse."""
    if sha(entry["content"]) != entry["sha256"]:
        raise ValueError("Retrieved report mutated before composition")
    if draft.get("source_report_id") != entry["report_id"] or draft.get("source_experiment_id") != experiment_id:
        raise ValueError("Program does not bind the retrieved report and frozen experiment")
    sources = [e for e in entry["content"]["experiments"] if e["experiment_id"] == experiment_id and e["result"]]
    if len(sources) != 1:
        raise ValueError("Selected report experiment has no successful computation")
    source = sources[0]["result"]
    parameters = dict(source["parameters"])
    extra = draft.get("extension_parameters", {})
    if not isinstance(extra, dict) or set(extra) & set(parameters):
        raise ValueError("Extension parameter bindings collide with the donor")
    parameters.update(extra)
    if len(parameters) > 8 or any(
        k not in {f"p{i}" for i in range(8)} or type(v) not in (int, float) or not math.isfinite(v)
        for k, v in parameters.items()
    ):
        raise ValueError("Invalid or excessive explicit parameter bindings")
    extension = draft.get("extension_expression")
    tree = parse(extension, inputs, list(parameters))
    if not any(isinstance(n, ast.Name) and n.id in inputs for n in ast.walk(tree)):
        raise ValueError("Extension must contain a permitted measured input, not a constant identity")
    combine = {"add": "+", "multiply": "*"}.get(draft.get("combine"))
    if combine is None:
        raise ValueError("Composition must be add or multiply")
    expression = f"({source['expression']}) {combine} ({extension})"
    parse(expression, inputs, list(parameters))
    return {"expression": expression, "parameters": parameters}, {
        "relationship": "cross_laboratory_formula_reuse",
        "source_lab_id": entry["content"]["lab_id"],
        "source_report_id": entry["report_id"], "source_report_sha256": entry["sha256"],
        "source_experiment_id": experiment_id,
        "source_fitted_program_sha256": sha([source["expression"], source["parameters"]]),
        "source_expression": source["expression"], "extension_expression": extension,
        "combine": draft["combine"],
        "parameter_policy": "Donor fitted values initialize explicit parameters; all parameters refit on train",
        "reuse_scope": "Executed structural reuse; no claim of functional benefit or independent corroboration",
    }


def run_agentrxiv(search, ask, proposal, stage, roles):
    from .search import Search

    search.capture_failure_diagnostics = True
    archive = PrivateArchive(search.task["task_id"])
    laboratories, publications, retrievals, handoffs, experiments = [], [], [], [], []

    def publish(lab_id, cycle_id, evidence):
        entry = archive.publish(lab_id, cycle_id, evidence)
        if entry:
            publications.append(entry)
            stage("archive_publication", message=f"{lab_id} published {cycle_id}", archive_entry=entry)
        return entry

    for lab_id, emphasis in [("lab-A", "Compact response models and residual structure"),
                             ("lab-B", "Competing nonlinear structures and domain constraints")]:
        child = Search(
            search.task, search.train, search.dev, event=search.event, stopped=search.stopped,
            max_fits=max(0, search.max_fits - search.fits),
            max_structures=max(0, search.max_structures - len(search.seen)),
            max_seconds=search.max_seconds, started=search.started, capture_failure_diagnostics=True,
        )
        contexts = []

        def lab_stage(name, lab_id=lab_id, **detail):
            stage(name, lab_id=lab_id, cycle_id="initial", **detail)

        def lab_ask(role, instruction, context, lab_id=lab_id, emphasis=emphasis, contexts=contexts):
            isolated = context | {"laboratory": {"lab_id": lab_id, "cycle_id": "initial",
                                                  "research_emphasis": emphasis, "visible_archive_report_ids": []}}
            contexts.append(sha(isolated))
            return ask(role, instruction, isolated)

        def lab_proposal(program, experiment_id, lab_id=lab_id, child=child, lab_stage=lab_stage):
            origin = f"{lab_id}.initial/{experiment_id}"
            expression = program.get("expression")
            parameters = program.get("parameters", {})
            if not isinstance(expression, str) or not isinstance(parameters, dict) or any(
                k not in {f"p{i}" for i in range(8)} or type(v) not in (int, float) or not math.isfinite(v)
                for k, v in parameters.items()
            ):
                child.failures.append({"origin": origin, "reason": "Invalid expression or parameter map"})
                return None
            lab_stage("experiment", origin=origin, expression=expression)
            return child.add(expression, parameters, fit=bool(parameters), origin=origin)

        evidence = run_laboratory(child, lab_ask, lab_proposal, lab_stage, roles)
        for h, actual_hash in zip(evidence["handoffs"], contexts, strict=True):
            h["local_context_sha256"] = h["input_sha256"]
            h["input_sha256"] = actual_hash
            h["lab_id"] = lab_id
        search.fits += child.fits
        search.optimizer_evaluations += child.optimizer_evaluations
        search.seen.update(sha([lab_id, key]) for key in child.seen)
        search.candidates.extend(child.candidates)
        search.failures.extend(child.failures)
        laboratories.append({"lab_id": lab_id, "cycle_id": "initial", "evidence": evidence})
        handoffs.extend(evidence["handoffs"])
        experiments.extend({"lab_id": lab_id, "cycle_id": "initial", **e} for e in evidence["experiments"])
        publish(lab_id, "initial", evidence)

    followup_handoffs, followup_experiments = [], []

    def call(name, role, instruction, context, required):
        context = context | {"cohort": cohort_context(search), "laboratory": {"lab_id": "lab-A", "cycle_id": "archive-followup"}}
        stage("agentrxiv_stage", message=name.replace("_", " "), role=role, model=roles[role])
        output = ask(role, instruction, context)
        h = {"stage": name, "lab_id": "lab-A", "role": role, "model": roles[role],
             "input_sha256": sha(context), "output": output, "output_sha256": sha(output),
             "schema_valid": all(isinstance(output.get(k), kind) and bool(output[k]) for k, kind in required)}
        handoffs.append(h)
        followup_handoffs.append(h)
        return output

    entry, plan, critique, report = None, {}, {}, {}
    if len(publications) == 2:
        query = call("archive_query", "planner",
                     'Propose a search query for completed research from the other laboratory: {"query":"..."}. '
                     "Use the task and your own report; no live literature or test feedback is available.",
                     {"own_report": publications[0]}, [("query", str)])
        try:
            matches = archive.retrieve(query.get("query"), "lab-A")
        except ValueError:
            matches = []
        if matches:
            entry = matches[0]["entry"]
            retrieval = {"requester": "lab-A", "query": query["query"], "source_lab_id": entry["content"]["lab_id"],
                         "report_id": entry["report_id"], "report_sha256": entry["sha256"],
                         "score": matches[0]["score"], "available_completed_reports": len(archive.entries)}
            retrievals.append(retrieval)
            stage("archive_retrieval", message="lab-A retrieved lab-B's completed report", **retrieval)
            valid_ids = [e["experiment_id"] for e in entry["content"]["experiments"] if e["result"]]
            plan = call("archive_followup_plan", "planner",
                        'Plan a follow-up that actually reuses a successful formula from the retrieved report. Return '
                        '{"source_report_id":"...", "source_experiment_id":"...", "rationale":"...", "followup":"..."}. '
                        "Select one listed valid experiment. The host will expand its formula in an additive or multiplicative extension. "
                        "Every coefficient will be explicit and refitted on train. This is knowledge reuse, not independent evidence.",
                        {"own_report": publications[0], "retrieved_report": entry, "valid_source_experiment_ids": valid_ids},
                        [("source_report_id", str), ("source_experiment_id", str), ("followup", str)])
            if plan.get("source_report_id") == entry["report_id"] and plan.get("source_experiment_id") in valid_ids:
                source_id = plan["source_experiment_id"]
                source = next(e["result"] for e in entry["content"]["experiments"] if e["experiment_id"] == source_id)
                engineering_context = {"frozen_followup_plan": plan, "retrieved_report": entry,
                                       "available_extension_parameters": [f"p{i}" for i in range(8) if f"p{i}" not in source["parameters"]],
                                       "prediction_requirements": prediction_requirements(search.task)}
                instruction = ('Return {"source_report_id":"...", "source_experiment_id":"...", "combine":"add", '
                               '"extension_expression":"...", "extension_parameters":{}, "rationale":"..."}. '
                               "Bind the exact frozen source. combine is add or multiply. Your extension must use permitted inputs; "
                               "new parameters must come from available_extension_parameters. Existing donor parameters may be referenced "
                               "but not rebound. The host expands the entire donor formula and fits all coefficients on train. "
                               "Keep every transformation visible. The revised experiment must use a structurally different extension.")
                for i in range(2):
                    experiment_id = f"cross-lab-{i + 1}"
                    draft = call("archive_engineering" if i == 0 else "archive_revision", "coder", instruction,
                                 engineering_context | ({"previous_experiment": followup_experiments[0], "critique": critique} if i else {}),
                                 [("source_report_id", str), ("source_experiment_id", str), ("extension_expression", str)])
                    before = (search.fits, search.optimizer_evaluations, len(search.seen), len(search.failures))
                    program, lineage, card = {}, None, None
                    try:
                        archive.verify(entry)
                        program, lineage = compose_from_report(entry, source_id, draft, search.inputs)
                        card = proposal(program, experiment_id)
                        if card:
                            card["source_lineage"] = lineage
                    except (ValueError, TypeError, SyntaxError, KeyError) as exc:
                        search.failures.append({"origin": experiment_id, "reason": str(exc)})
                    e = {"experiment_id": experiment_id, "program": program, "draft": draft, "program_sha256": sha(program),
                         "status": "complete" if card else "failed_or_not_executed", "source_lineage": lineage,
                         "structure_entered": len(search.seen) > before[2], "fitting_attempts": search.fits - before[0],
                         "optimizer_evaluations": search.optimizer_evaluations - before[1], "failures": search.failures[before[3]:],
                         "result": {k: card[k] for k in ("expression", "parameters", "train_error", "dev_error", "residuals", "simplicity")}
                         if card else None}
                    followup_experiments.append(e)
                    experiments.append({"lab_id": "lab-A", "cycle_id": "archive-followup", **e})
                    stage("archive_followup_experiment", message=experiment_id, status=e["status"], source_lineage=lineage)
                    if i == 0:
                        critique = call("archive_experimental_critique", "critic",
                                        'Review the executed follow-up using the source report and actual diagnostics. Return '
                                        '{"source_report_id":"...", "experiment_ids":["cross-lab-1"], "revision":"..."}. '
                                        "Propose a different extension; retain the frozen source binding. Keep failures and uncertainty explicit.",
                                        {"retrieved_report": entry, "experiment": e},
                                        [("source_report_id", str), ("experiment_ids", list), ("revision", str)])
                report = call("archive_evidence_report", "reporter",
                              'Return {"summary":"...", "source_report_id":"...", "experiment_ids":["cross-lab-1","cross-lab-2"], '
                              '"limitations":["..."], "observed_cohort":{"training_rows":0,"development_rows":0,"training_groups":0,"development_groups":0}}. '
                              "Copy cohort.verified_counts exactly. Identify both actual experiments and the retrieved report; retain failures. "
                              "Report reuse without claiming improvement, novelty or independent corroboration. Prose remains unreviewed.",
                              {"retrieved_report": entry, "experiments": followup_experiments},
                              [("summary", str), ("source_report_id", str), ("experiment_ids", list), ("limitations", list)])

    try:
        changed = len(followup_experiments) == 2 and structural_key(followup_experiments[0]["program"]["expression"]) != structural_key(followup_experiments[1]["program"]["expression"])
    except (ValueError, TypeError, SyntaxError, KeyError):
        changed = False
    checks = {
        "two_initial_laboratories_complete": all(x["evidence"]["conformance"]["status"] == "complete" for x in laboratories),
        "foreign_completed_report_retrieved": len(retrievals) == 1 and retrievals[0]["source_lab_id"] == "lab-B",
        "all_eighteen_handoffs_valid": len(handoffs) == 18 and all(h["schema_valid"] for h in handoffs),
        "two_followup_programs_expanded_and_checked": len(followup_experiments) == 2 and all(e["source_lineage"] and e["structure_entered"] for e in followup_experiments),
        "followup_structurally_revised": changed,
        "valid_cross_lab_experiment": any(e["result"] for e in followup_experiments),
        "critique_binds_archive_and_experiment": bool(entry) and critique.get("source_report_id") == entry["report_id"] and critique.get("experiment_ids") == ["cross-lab-1"],
        "report_binds_archive_and_experiments": bool(entry) and report.get("source_report_id") == entry["report_id"] and report.get("experiment_ids") == ["cross-lab-1", "cross-lab-2"],
        "reported_cohort_matches_executed_data": exact_cohort_report(report.get("observed_cohort"), search),
    }
    conformance = {"status": "complete" if all(checks.values()) else "incomplete_method_execution", "checks": checks}
    followup = {"lab_id": "lab-A", "cycle_id": "archive-followup", "cohort": cohort_context(search),
                "handoffs": followup_handoffs, "experiments": followup_experiments, "conformance": conformance}
    publish("lab-A", "archive-followup", followup)
    for item in archive.entries:
        archive.verify(item)
    stage("agentrxiv_conformance", message=conformance["status"], checks=checks)
    return {
        "method_id": "agentrxiv", "adaptation_version": ADAPTATION_VERSION,
        "source_url": SOURCE, "source_revision": REVISION,
        "laboratory_source_revision": LAB_REVISION, "laboratory_adaptation_version": LAB_VERSION,
        "license": "Independent MIT implementation; Agent Laboratory MIT notice; paper attribution",
        "configuration": dict(CONFIG), "cohort": cohort_context(search),
        "laboratories": laboratories, "archive": publications, "retrievals": retrievals,
        "handoffs": handoffs, "experiments": experiments, "followup": followup,
        "conformance": conformance, "scientific_review": "not_assessed",
    }
