"""Asta conformance checks use synthetic engineering fixtures, never held-out tasks."""

import json
import math

import pytest
from scipy.integrate import quad
from scipy.stats import beta

from principia_asd.engine.asta import backpropagate, belief_update, choose_parent
from principia_asd.engine.search import execute_method
from principia_asd.io import sha


def fixture():
    task = {"task_id": "synthetic-asta", "inputs": ["x"], "output": "y", "metric": {"primary": "mae"}}
    rows = [{"x": i / 10, "y": 2 + (i / 10) ** 2, "group": str(i // 5)} for i in range(40)]
    return task, rows[:30], rows[30:]


class AstaGateway:
    def __init__(self, fault=None):
        self.calls = []
        self.fault = fault
        self.priors = {}
        self.nominations = 0

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        context = json.loads(kwargs["prompt"])
        feedback = context["development_feedback"]
        if "executed_experiment" in feedback or "frozen_claim" not in feedback or "initial_proposal" in feedback:
            assert "Work only from supplied development evidence" in kwargs["system"]
            assert "Use prior domain knowledge" not in kwargs["system"]
        if "ancestor_evidence" in feedback:
            self.nominations += 1
            n = self.nominations
            if feedback["parent_id"] != "root":
                assert feedback["ancestor_evidence"][-1]["node_id"] == feedback["parent_id"]
                assert "experiment" in feedback["ancestor_evidence"][-1]
                assert "belief_update" in feedback["ancestor_evidence"][-1]
            expr = ["p0+p1*x", "p0+p1*x**2", "p0+p1*sqrt(x)", "p0+p1*x**3"][n - 1]
            if self.fault == "duplicate" and n == 4:
                expr = "p0 + p1 * x"
            if self.fault == "invalid_program" and n == 1:
                expr = "p0+p1*log(x-100)"
            output = {"hypothesis": f"Family {n}", "expression": expr, "parameters": {"p0": 0, "p1": 1}}
        elif "initial_proposal" in feedback:
            claim = feedback["frozen_claim"]
            assert self.priors[claim["node_id"]] == 2
            output = {k: feedback["initial_proposal"][k] for k in ("expression", "parameters")}
            if self.fault == "changed_structure" and claim["node_id"] == "hypothesis-1":
                output["expression"] = "p0+p1*x**4"
        elif "tree" in feedback:
            output = {"summary": "Synthetic evidence only", "experiment_ids": [f"hypothesis-{i}" for i in range(1, 5)],
                      "limitations": ["Uncalibrated model beliefs"], "observed_cohort": feedback["cohort"]["verified_counts"]}
            if self.fault == "invented_report":
                output["experiment_ids"][-1] = "unexecuted-hypothesis"
        else:
            assert not {"input_statistics_train", "target_train", "examples_train"} & context.keys()
            assert not {"ancestor_evidence", "prior_votes", "initial_proposal"} & feedback.keys()
            claim = feedback["frozen_claim"]
            node_id = claim["node_id"]
            if "executed_experiment" not in feedback:
                assert set(feedback) == {"frozen_claim"}
                assert "Use prior domain knowledge" in kwargs["system"]
                assert "Work only from supplied development evidence" not in kwargs["system"]
                assert "subjective expectation" in context["instruction"]
                assert "null if you have no defensible leaning" in context["instruction"]
                self.priors[node_id] = self.priors.get(node_id, 0) + 1
                vote = False
            else:
                experiment = feedback["executed_experiment"]
                assert experiment["claim_sha256"] == sha(claim)
                assert experiment["result"] is not None or experiment["failures"]
                vote = True
            if self.fault == "all_abstain":
                vote = None
            if self.fault == "numeric_belief":
                vote = 0.7
            output = {"belief": vote, "reason": "Synthetic observer"}
        return {"text": json.dumps(output), "request_id": kwargs["request_id"]}


def test_asta_executes_branched_evidence_conditioned_search():
    gateway = AstaGateway()
    result = execute_method("asta_autodiscovery", *fixture(), gateway=gateway)
    assert result["status"] == "complete"
    assert result["accounting"]["model_calls"] == 25
    assert result["accounting"]["fitting_attempts"] == 4
    evidence = result["method_evidence"]
    assert all(evidence["conformance"]["checks"].values())
    assert len({h["model"] for h in evidence["handoffs"]}) == 4
    assert len(evidence["search_tree"]) == 5
    assert len(evidence["search_tree"][0]["children"]) == 2
    assert any(n["parent_id"] not in (None, "root") for n in evidence["search_tree"])
    for h, call in zip(evidence["handoffs"], gateway.calls, strict=True):
        assert h["input_sha256"] == sha(json.loads(call["prompt"])["development_feedback"])
    root_reward = evidence["search_tree"][0]["reward_sum"]
    assert root_reward == pytest.approx(sum(n["belief_update"]["reward"] for n in evidence["search_tree"][1:]))
    assert root_reward > 0


def test_prior_knowledge_scope_is_restricted_and_recorded_for_all_phases():
    gateway = AstaGateway()
    result = execute_method("asta_autodiscovery", *fixture(), gateway=gateway)
    evidence = result["method_evidence"]
    assert evidence["adaptation_version"] == "asta-autodiscovery-adaptation-v2"
    priors = [h for h in evidence["handoffs"] if "_prior_" in h["stage"]]
    others = [h for h in evidence["handoffs"] if "_prior_" not in h["stage"]]
    assert len(priors) == 8 and len(others) == 17
    assert all(h["knowledge_scope"] == "domain_prior" and not h["measurement_preview_included"] for h in priors)
    assert all(h["knowledge_scope"] == "development_evidence_only" for h in others)
    # Expectation elicitation never replaces missing observed votes with a fabricated prior.
    abstained = execute_method("asta_autodiscovery", *fixture(), gateway=AstaGateway("all_abstain"))
    assert abstained["status"] == "incomplete_method_execution" and not abstained["rules"]
    assert all(n["belief_update"]["reward"] == 0 for n in abstained["method_evidence"]["search_tree"][1:])


def test_beta_kl_matches_numerical_integration_and_cumulative_counts():
    result = belief_update([False, False], [True, True])
    assert result["prior"]["alpha"] == 1 and result["prior"]["beta"] == 3
    assert result["posterior"]["alpha"] == 3 and result["posterior"]["beta"] == 3
    integral = quad(lambda x: beta.pdf(x, 3, 3) * (beta.logpdf(x, 3, 3) - beta.logpdf(x, 1, 3)), 0, 1)[0]
    assert result["reward"] == pytest.approx(integral)
    assert result["directional_shift"]
    # Becoming more certain without changing leaning is recorded, but not rewarded.
    assert belief_update([True, True], [True, True])["reward"] == 0
    assert belief_update([None, None], [True, True])["reward"] == 0
    with pytest.raises(ValueError, match="booleans"):
        belief_update([0.5], [True])


def test_widening_and_uct_use_actual_visit_and_reward_statistics():
    nodes = {"root": {"parent_id": None, "children": [], "visits": 0, "reward_sum": 0}}
    assert choose_parent(nodes)[0] == "root"
    for id in ("a", "b"):
        nodes[id] = {"parent_id": "root", "children": [], "visits": 0, "reward_sum": 0}
        nodes["root"]["children"].append(id)
        backpropagate(nodes, id, 0)
    nodes["a"]["reward_sum"] = 0.1
    nodes["b"]["reward_sum"] = 1.5
    parent, decisions = choose_parent(nodes)
    assert parent == "b"
    assert decisions[0]["uct_scores"]["b"] == pytest.approx(1.5 + math.sqrt(2 * math.log(2)))
    nodes["a"]["reward_sum"] = 2.0
    assert choose_parent(nodes)[0] == "a"
    nodes["root"]["visits"] = 5
    assert choose_parent(nodes)[0] == "root"  # Widening unlocks another branch.


@pytest.mark.parametrize("fault", ["duplicate", "changed_structure", "numeric_belief", "all_abstain", "invented_report"])
def test_missing_defining_behavior_cannot_produce_ranked_rules(fault):
    result = execute_method("asta_autodiscovery", *fixture(), gateway=AstaGateway(fault))
    assert result["status"] == "incomplete_method_execution"
    assert not result["rules"]
    assert len(result["method_evidence"]["experiments"]) == 4


def test_failed_experiment_is_retained_and_never_rewarded():
    result = execute_method("asta_autodiscovery", *fixture(), gateway=AstaGateway("invalid_program"))
    assert result["status"] == "complete"
    node = result["method_evidence"]["search_tree"][1]
    assert node["experiment"]["result"] is None
    assert node["experiment"]["failures"]
    assert node["belief_update"]["reward"] == 0
    assert node["visits"] >= 1


def test_budget_exhaustion_stops_before_another_paid_request():
    gateway = AstaGateway()
    with pytest.raises(RuntimeError, match="request budget exhausted"):
        execute_method("asta_autodiscovery", *fixture(), gateway=gateway, limits={"max_calls": 5})
    assert len(gateway.calls) == 5
