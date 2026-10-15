"""A separately identified interface revision; scientific search is inherited.

The v1 runtime and completed cohorts remain immutable. This version supplies the
actual role grammar and a declared, hash-linked projection of development evidence.
It does not truncate messages, refit candidates, or read evaluation data.
"""

from __future__ import annotations

import copy

from ..io import sha
from .bound_engine import BoundEngine
from .expression import FUNCS

POLICY = "principia-explicit-state-protocol-v2-dev"
CONTEXT_POLICY = "complete-inventory-compact-evidence-v1"
CONTRACTS = {
    "planner": {
        "top_level": {
            "kernels": "array of zero to three kernel objects",
            "rationale": "optional string",
        },
        "kernel_exact_fields": {
            "name": "string matching ^k_[A-Za-z0-9]{1,30}$",
            "expression": "string",
        },
        "rules": [
            "Put rationale only at the top level; never add fields inside a kernel object.",
            "The suffix after k_ contains letters/digits only, no underscores or punctuation.",
            "A kernel is parameter-free: p0 through p7 cannot appear. The coder fits coefficients around kernels in a rule draft.",
            "Use only input names, inventory state names and existing kernels. No numerical literals, newly invented state, or recursive definitions.",
            "Choose new names; all names and definitions in the current inventory remain fixed.",
        ],
        "example": {
            "kernels": [{"name": "k_curve", "expression": "tanh(INPUT_OR_EXISTING_KERNEL)"}],
            "rationale": "A development hypothesis",
        },
    },
    "coder": {
        "top_level": {"rules": "array of zero to two rule objects"},
        "rule_exact_fields": {
            "expression": "string",
            "initial": "map of p0..p7 to finite numerical starting values",
        },
        "rules": [
            "All parameters in the expression must be declared in initial; do not declare unused parameters.",
            "Numerical literals are allowed only in initial, not inside expression.",
            "A rule may use fitted parameters, existing inventory kernels, state names and input names. It may not define new kernels.",
            "At most eight combined final-stage and inherited fitted coefficients. Train-statistic scalars are also counted separately.",
            "Do not repeat an identical expression and initial map; duplicate requests are not new experiments.",
        ],
        "example": {
            "rules": [
                {"expression": "p0+p1*INPUT_OR_EXISTING_KERNEL", "initial": {"p0": 0, "p1": 1}}
            ]
        },
    },
    "critic": {
        "top_level": {
            "candidate_ids": "array of IDs from development_feedback.candidates",
            "limitations": "array of strings",
            "next_hypothesis": "string",
        },
        "rules": [
            "Reference executed candidates only; the archive index is not the selected evidence packet.",
            "Retain failures and uncertainty. Critique may inform the next planner but cannot change fitted state.",
        ],
    },
    "reporter": {
        "top_level": {
            "candidate_ids": "array containing each nominated ID exactly once",
            "limitations": "array of strings",
            "summary": "string",
        },
        "rules": [
            "Use frozen_evidence only. All three nomination slots remain fixed, including unfilled slots.",
            "Do not change nominations or claim private-test performance, novelty or causality.",
        ],
    },
}


def candidate_packet(card):
    """Lossless numeric diagnostics; repeated full programs remain hash-linked."""
    return {
        k: copy.deepcopy(card[k])
        for k in (
            "candidate_id",
            "train_error",
            "dev_error",
            "residuals",
            "parameter_uncertainty",
            "execution_status",
            "final_fit_source",
        )
    } | {
        "expression": card["program"]["specification"]["expression"],
        "parameters": copy.deepcopy(card["program"]["specification"]["parameters"]),
        "program_sha256": card["program"]["sha256"],
        "simplicity": {
            k: copy.deepcopy(v) for k, v in card["simplicity"].items() if k != "expanded_expression"
        },
    }


def failure_packet(failure):
    request = failure["request"]
    return {
        "full_record_sha256": sha(failure),
        "expression": request["expression"],
        "initial": copy.deepcopy(request["initial"]),
        "request_sha256": sha(request),
        "reason": failure["reason"],
        "optimizer_evaluations": failure["optimizer_evaluations"],
    }


def rejection_packet(rejection):
    value = {k: copy.deepcopy(v) for k, v in rejection.items() if k != "proposal"}
    value["full_record_sha256"] = sha(rejection)
    if "proposal" in rejection:
        proposal = rejection["proposal"]
        if isinstance(proposal, dict):
            value["proposal"] = {
                k: copy.deepcopy(v)
                for k, v in proposal.items()
                if k in ("name", "expression", "initial")
            }
            value["extra_fields"] = sorted(set(proposal) - {"name", "expression", "initial"})
        else:
            value["proposal"] = copy.deepcopy(proposal)
    return value


class SchemaBoundEngine(BoundEngine):
    policy = POLICY
    request_tag = "bound-v2"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.configuration.pop("sha256")
        self.configuration.update(
            context_policy=CONTEXT_POLICY, role_contracts_sha256=sha(CONTRACTS)
        )
        self.configuration["sha256"] = sha(self.configuration)

    def _system(self, role):
        return super()._system(role) + (
            " Follow role_contract exactly. No extra object fields. The planner's kernels are parameter-free; "
            "the coder's rule drafts declare fitted p-parameters in initial. Kernel names must match "
            "^k_[A-Za-z0-9]{1,30}$, with no underscore after the k_ prefix. "
            "The context policy is a declared compact representation, not the full artifact archive. "
            "Do not paste numeric values from diagnostics into a formula. Reuse their inventory state names."
        )

    def _context(self, role, instruction, *, frozen=None):
        context = super()._context(role, instruction, frozen=frozen)
        context["role_contract"] = copy.deepcopy(CONTRACTS[role])
        context["operator_arities"] = {k: v[1] for k, v in FUNCS.items()}
        context["context_projection"] = {
            "policy": CONTEXT_POLICY,
            "scope": "All measurement names, state bindings and kernel definitions; fixed dev-selected candidate packets plus complete archive index; every failed experiment and rejected patch.",
            "omitted_duplicate_fields": [
                "repeated full program/specification copies",
                "repeated expanded numeric expression strings",
                "repeated source-artifact bodies",
                "extra invalid patch fields (names and original record hash retained)",
            ],
            "full_records": "Host checkpoint and frozen submission retain original records. No retrieval tool is implied; this method uses the declared projection.",
            "overflow_policy": "Fail before dispatch above the unchanged 48000-byte limit; never silently truncate or drop records.",
        }
        if frozen is not None:
            context["frozen_evidence"] = {
                "nomination_freeze": copy.deepcopy(frozen["nomination_freeze"]),
                "selection": copy.deepcopy(frozen["selection"]),
                "candidates": [candidate_packet(c) for c in frozen["candidates"]],
            }
            # Formula names remain interpretable to the reporter, including fitted state.
            context["inventory"] = self._inventory()
        else:
            feedback = context["development_feedback"]
            feedback["candidates"] = [candidate_packet(c) for c in feedback["candidates"]]
            feedback["failures"] = [failure_packet(f) for f in self.host.failures]
            feedback["rejected_patches"] = [rejection_packet(r) for r in self.rejections]
            feedback["candidate_archive"] = [
                {
                    k: copy.deepcopy(c[k])
                    for k in ("candidate_id", "train_error", "dev_error", "execution_status")
                }
                for _, c in sorted(self.host.candidates.items())
            ]
            feedback["record_counts"] = {
                "candidates": len(self.host.candidates),
                "candidate_packets": len(feedback["candidates"]),
                "failures": len(self.host.failures),
                "rejected_patches": len(self.rejections),
            }
            feedback["full_records_sha256"] = {
                "candidates": sha(self.host.candidates),
                "failures": sha(self.host.failures),
                "rejected_patches": sha(self.rejections),
            }
        return context
