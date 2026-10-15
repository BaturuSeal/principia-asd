"""Versioned response-format clarification; scientific workflow/guards are inherited."""

import copy

from ..io import sha
from .bound_data_to_paper import CONTRACTS, BoundDataToPaper

POLICY = "data-to-paper-explicit-state-v2-dev"
FORMAT_POLICY = "flat-stage-json-v2"
FORMAT_RULES = [
    "Return exactly one flat JSON object whose top-level keys equal stage_contract. No markdown.",
    "Do not wrap the object in analysis_plan, analysis_program, result, output or the stage name.",
    "No additional keys, including policy, stage, configuration_sha256, planned_model or notes.",
    "response_example illustrates field placement only, not a recommended scientific model. Replace every angle-bracket placeholder; choose your own hypothesis and expression.",
    "The plan contains only its seven declared fields. Do not put a formula or parameter values in the planning response; the coder supplies them in the next stage.",
    "The formula literal ban applies to expression fields. Initial guesses, exact cohort counts and exact supplied metadata are allowed in their declared JSON fields.",
    "Reports express all numerical claims in headings, templates and limitations with {{fact_name}} placeholders; copy cohort counts and evidence IDs exactly in metadata fields.",
]


class SchemaBoundDataToPaper(BoundDataToPaper):
    policy = POLICY
    request_tag = "paper-bound-v2"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.configuration.pop("sha256")
        self.configuration.update(
            response_format_policy=FORMAT_POLICY,
            response_format_rules_sha256=sha(FORMAT_RULES),
        )
        self.configuration["sha256"] = sha(self.configuration)

    def _system(self, role):
        return super()._system(role) + " " + " ".join(FORMAT_RULES)

    def _context(self, role, instruction, *, frozen=None):
        context = super()._context(role, instruction, frozen=frozen)
        base = {"analysis_repair": "analysis_program", "report_repair": "evidence_report"}.get(
            instruction, instruction
        )
        if base == "analysis_plan":
            example = {
                "hypothesis": "<your predictive hypothesis>",
                "inputs": ["<chosen permitted input name; repeat for each chosen input>"],
                "output": self.host.task["output"],
                "metric": self.host.task["metric"]["primary"],
                "fit_partition": "train",
                "selection_partition": "dev",
                "limitations": ["<specific scope or dependence limitation>"],
            }
        elif base == "analysis_program":
            example = {
                "expression": "p0+p1*<chosen permitted input or existing normalized kernel>",
                "initial": {"p0": 0, "p1": 1},
            }
        elif base == "statistical_review":
            example = {
                "experiment_ids": [
                    e["experiment_id"] for e in context["experiments"] if e["result"]
                ],
                "facts_sha256": context["computed_facts"]["sha256"],
                "limitations": ["<specific scientific limitation of the executed analysis>"],
                "interpretation": "<qualitative interpretation of the supplied evidence>",
            }
        else:
            example = {
                "sections": [
                    {
                        "heading": "Development comparison",
                        "template": "Development loss {{development_error}} versus training-mean comparator {{baseline_development_error}}. <your qualitative interpretation>",
                    }
                ],
                "observed_cohort": copy.deepcopy(context["cohort"]["verified_counts"]),
                "candidate_ids": [
                    s["candidate_id"]
                    for s in frozen["selection"]["nominations"]
                    if s["candidate_id"]
                ],
                "facts_sha256": context["computed_facts"]["sha256"],
                "limitation_ids": [v["id"] for v in context["retained_limitations"]],
                "limitations": [
                    "<scientific limitation; use computed references for every numerical claim>"
                ],
            }
        assert set(example) == set(CONTRACTS[base])
        context.update(
            response_format_policy=FORMAT_POLICY,
            response_rules=copy.deepcopy(FORMAT_RULES),
            response_example=example,
            exact_top_level_keys=sorted(CONTRACTS[base]),
        )
        return context
