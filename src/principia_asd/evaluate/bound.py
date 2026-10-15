"""Zero-fit, zero-provider assessment for the explicit-state development path.

The expected freeze hash must come from trusted host storage, not model output.
These assessments are deliberately ineligible for historical or public ranking.
"""

from __future__ import annotations

import copy

from ..engine.bindings import POLICY, StateRegistry, verify_program
from ..io import sha
from .metrics import evaluate_rule

HOST_POLICY = "host-search-explicit-state-v1-dev"


def verify_frozen_candidate(frozen, expected_sha256, candidate_id):
    content = {k: v for k, v in frozen.items() if k != "sha256"}
    if frozen.get("sha256") != expected_sha256 or sha(content) != expected_sha256:
        raise ValueError("Submission does not match the trusted host freeze")
    if frozen.get("policy") != HOST_POLICY or frozen.get("binding_policy") != POLICY:
        raise ValueError("Unsupported host or binding policy")
    if sha(frozen["task"]) != frozen["context"]["task_sha256"]:
        raise ValueError("Frozen task mutation")
    candidates = frozen["candidates"]
    if len({c["candidate_id"] for c in candidates}) != len(candidates):
        raise ValueError("Duplicated candidate identity")
    matches = [c for c in candidates if c["candidate_id"] == candidate_id]
    if len(matches) != 1:
        raise ValueError("Candidate is absent from the frozen nomination set")
    card = matches[0]
    if sha({k: v for k, v in card.items() if k != "candidate_id"}) != candidate_id:
        raise ValueError("Candidate hash mismatch")
    if card["context"] != frozen["context"] or card["policy"] != HOST_POLICY:
        raise ValueError("Candidate context mismatch")
    registry = StateRegistry(frozen["source_artifacts"])
    for digest, state in card["program"]["states"].items():
        actual = registry.register(state["artifact_sha256"], state["value_path"], state["kind"])
        if actual != digest:
            raise ValueError("State identity mismatch")
        source = registry.artifacts[state["artifact_sha256"]]
        if source.get("policy") != HOST_POLICY:
            raise ValueError("Unregistered host computation policy")
        if (
            state["kind"] != "fixed_scientific"
            and source.get("train_sha256") != frozen["context"]["train_sha256"]
        ):
            raise ValueError("State belongs to another training partition")
    program = verify_program(card["program"], registry)
    if card["simplicity"] != program["simplicity"]:
        raise ValueError("Declared simplicity differs from expanded program")
    params = program["specification"]["parameters"]
    if params:
        source = registry.artifacts[card["final_fit_source"]]
        if (
            source.get("kind") != "train_fitted"
            or source.get("scope") != "train"
            or source.get("status") != "complete"
            or source.get("policy") != HOST_POLICY
            or source.get("train_sha256") != frozen["context"]["train_sha256"]
            or source.get("task_sha256") != frozen["context"]["task_sha256"]
            or source.get("values") != params
            or source.get("program_sha256") != program["sha256"]
        ):
            raise ValueError("Final coefficients are not bound to their host fit")
    elif card["final_fit_source"] is not None:
        raise ValueError("Unnecessary final fit receipt")
    if (
        card["inputs"] != frozen["task"]["inputs"]
        or card["output"] != frozen["task"]["output"]
        or program["specification"]["inputs"] != card["inputs"]
    ):
        raise ValueError("Candidate and task measurement inventories differ")
    return copy.deepcopy(card), registry


def evaluate_bound_candidate(frozen, expected_sha256, candidate_id, rows, targets):
    """Assessment after host freeze; takes no path or model and cannot update search."""
    card, _ = verify_frozen_candidate(frozen, expected_sha256, candidate_id)
    # Reuse identical numerical accuracy/stability procedures, not the old simplicity policy.
    executable = {
        "representation": "expression",
        "expression": card["program"]["expression"],
        "parameters": card["program"]["execution_values"],
    }
    receipt = evaluate_rule(executable, rows, targets, frozen["task"])
    receipt["simplicity"] = copy.deepcopy(card["program"]["simplicity"])
    receipt.update(
        {
            "evaluator_policy": HOST_POLICY,
            "candidate_id": candidate_id,
            "submission_sha256": expected_sha256,
            "ranking_authorized": False,
            "api_calls": 0,
            "fitting_attempts": 0,
            "scientific_review": "not_assessed",
        }
    )
    return receipt


def evaluate_bound_nominations(
    result, expected_nomination_sha256, rows, targets, *, expected_result_sha256
):
    """Assess every frozen slot, retaining unfilled slots and incomplete methods."""
    from ..engine.bound_asta import POLICY as ASTA_POLICY
    from ..engine.bound_controls import POLICY as CONTROL_POLICY
    from ..engine.bound_data_to_paper import POLICY as PAPER_POLICY
    from ..engine.bound_data_to_paper_v2 import POLICY as SCHEMA_PAPER_POLICY
    from ..engine.bound_engine import POLICY as PROTOCOL_POLICY
    from ..engine.bound_engine import SELECTION_POLICY
    from ..engine.bound_engine_v2 import POLICY as SCHEMA_PROTOCOL_POLICY
    from ..engine.bound_laboratory import POLICY as LABORATORY_POLICY

    if (
        result.get("sha256") != expected_result_sha256
        or sha({k: v for k, v in result.items() if k != "sha256"}) != expected_result_sha256
    ):
        raise ValueError("Completed engine result differs from trusted host receipt")
    freeze = result["nomination_freeze"]
    if (
        freeze.get("sha256") != expected_nomination_sha256
        or sha({k: v for k, v in freeze.items() if k != "sha256"}) != expected_nomination_sha256
    ):
        raise ValueError("Nominations do not match the trusted pre-report freeze")
    cfg = result["configuration"]
    if (
        cfg.get("sha256") != freeze["configuration_sha256"]
        or sha({k: v for k, v in cfg.items() if k != "sha256"}) != cfg["sha256"]
        or cfg.get("policy")
        not in {
            PROTOCOL_POLICY,
            SCHEMA_PROTOCOL_POLICY,
            CONTROL_POLICY,
            LABORATORY_POLICY,
            PAPER_POLICY,
            SCHEMA_PAPER_POLICY,
            ASTA_POLICY,
        }
        or result.get("policy") != cfg.get("policy")
    ):
        raise ValueError("Frozen protocol configuration mismatch")
    selection = freeze["selection"]
    frozen = result["host_submission"]
    if (
        result.get("selection") != selection
        or selection.get("policy") != SELECTION_POLICY
        or frozen.get("sha256") != freeze["host_sha256"]
        or sha({k: v for k, v in frozen.items() if k != "sha256"}) != freeze["host_sha256"]
        or cfg.get("host_context") != frozen["context"]
    ):
        raise ValueError("Frozen host submission or selection mismatch")
    slots = selection["nominations"]
    if len(slots) != cfg["nomination_slots"] or selection["slots"] != cfg["nomination_slots"]:
        raise ValueError("Nomination denominator changed")
    ids = [s["candidate_id"] for s in slots if s["candidate_id"] is not None]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicated nomination")
    receipts = []
    for i, slot in enumerate(slots):
        cid = slot["candidate_id"]
        if slot["slot"] != i + 1 or slot["status"] != (
            "nominated" if cid is not None else "unfilled"
        ):
            raise ValueError("Invalid fixed nomination slot")
        receipt = (
            evaluate_bound_candidate(frozen, freeze["host_sha256"], cid, rows, targets)
            if cid is not None
            else {"status": "unfilled", "candidate_id": None, "api_calls": 0, "fitting_attempts": 0}
        )
        receipts.append({"slot": i + 1, "method_status": result["status"], "assessment": receipt})
    return {
        "nomination_sha256": expected_nomination_sha256,
        "fixed_denominator": len(slots),
        "receipts": receipts,
        "ranking_authorized": False,
        "scientific_review": "not_assessed",
        "api_calls": 0,
        "fitting_attempts": 0,
    }
