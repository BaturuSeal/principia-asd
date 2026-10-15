import copy
import json

import numpy as np
import pytest

from principia_asd.engine.bound_engine import BoundEngine, development_selection
from principia_asd.engine.bound_search import BoundSearch
from principia_asd.evaluate.bound import evaluate_bound_candidate, evaluate_bound_nominations
from principia_asd.evaluate.metrics import pareto_front
from principia_asd.io import sha
from principia_asd.methods.registry import DEFAULT_ROLES


def fixture():
    task = {
        "inputs": ["x"],
        "output": "y",
        "metric": {"primary": "rmse"},
        "stability": {"ranking": False},
        "test_secret": "never send to a model",
    }

    def rows(label, xs):
        return [
            {
                "sample_id": f"{label}{i}",
                "group": label,
                "x": float(x),
                "y": float(0.4 + 0.2 * np.tanh(x / 2)),
                "unpermitted": "canary",
            }
            for i, x in enumerate(xs)
        ]

    return task, rows("train", range(-3, 4)), rows("dev", [-2.5, -0.5, 1.5])


class FixtureGateway:
    """Deterministic fake model, never a scientific scored trial."""

    def __init__(self, transform=None, fail_at=None):
        self.calls = []
        self.transform, self.fail_at = transform, fail_at

    def complete(self, **request):
        self.calls.append(copy.deepcopy(request))
        if len(self.calls) == self.fail_at:
            raise RuntimeError("ambiguous provider request; do not replay")
        ctx = json.loads(request["prompt"])
        role = next(k for k, v in DEFAULT_ROLES.items() if v == request["model"])
        if role == "planner":
            round_id = sum(c["model"] == DEFAULT_ROLES["planner"] for c in self.calls) - 1
            if round_id == 0:
                source = "tanh(normalized_0)"
            else:
                best_id = ctx["development_feedback"]["candidates"][0]["candidate_id"]
                source = next(
                    k["name"]
                    for k in ctx["inventory"]["kernels"]
                    if k["lineage"].get("candidate_id") == best_id
                )
            data = {
                "kernels": [
                    {"name": f"k_smooth{round_id}", "expression": source},
                    {"name": f"k_other{round_id}", "expression": "normalized_0*normalized_0"},
                ],
                "rationale": "Synthetic protocol exercise",
            }
        elif role == "coder":
            name = [
                k["name"] for k in ctx["inventory"]["kernels"] if k["name"].startswith("k_smooth")
            ][-1]
            data = {"rules": [{"expression": f"p0+p1*{name}", "initial": {"p0": 0, "p1": 1}}]}
        elif role == "critic":
            data = {
                "candidate_ids": [
                    c["candidate_id"] for c in ctx["development_feedback"]["candidates"]
                ],
                "limitations": ["synthetic data"],
                "next_hypothesis": "Reuse the fitted state through references",
            }
        else:
            data = {
                "candidate_ids": [
                    s["candidate_id"]
                    for s in ctx["frozen_evidence"]["selection"]["nominations"]
                    if s["candidate_id"]
                ],
                "limitations": ["synthetic fixture; no independent discovery"],
                "summary": "Fixture complete",
            }
        if self.transform:
            data = self.transform(role, data, ctx)
        return {
            "text": json.dumps(data),
            "model": request["model"],
            "request_id": request["request_id"],
            "usage": {"fixture_calls": 1},
        }


def engine(gateway=None, **kwargs):
    return BoundEngine(
        *fixture(), gateway=gateway or FixtureGateway(), run_id="synthetic-protocol", **kwargs
    )


def test_four_roles_two_rounds_promoted_fit_and_frozen_selection():
    g = FixtureGateway()
    e = engine(g)
    out = e.run()
    assert out["status"] == "complete", out["failure"]
    assert len(g.calls) == 7
    assert all(out["conformance"].values())
    assert [c["model"] for c in g.calls] == [
        DEFAULT_ROLES[r] for r in ["planner", "coder", "critic"] * 2 + ["reporter"]
    ]
    assert len(out["selection"]["nominations"]) == 3
    assert any(
        c["simplicity"]["inherited_fitted_scalars"] > 0
        for c in out["host_submission"]["candidates"]
    )
    assert any(
        c["simplicity"]["train_statistic_scalars"] == 2
        for c in out["host_submission"]["candidates"]
    )
    assert (
        len(
            [
                r
                for r in out["trace"]
                if r["stage"] == "experiment" and r["origin"].startswith("composition")
            ]
        )
        == 4
    )
    assert out["nomination_freeze"]["selection"] == out["selection"]
    assert (
        sha({k: v for k, v in out["nomination_freeze"].items() if k != "sha256"})
        == out["nomination_freeze"]["sha256"]
    )
    e.run()
    assert len(g.calls) == 7  # Reusing a terminal in-memory engine dispatches nothing.
    assert json.loads(g.calls[3]["prompt"])["development_feedback"]["earlier_round_critiques"]


def test_report_is_after_freeze_and_cannot_change_nominations():
    e = engine()

    def inspect_report(role, data, ctx):
        if role == "reporter":
            assert e.host.closed
            with pytest.raises(ValueError, match="frozen"):
                e.host.fit("x")
            data["candidate_ids"] = ["invented-rule"]
        return data

    e.gateway.transform = inspect_report
    out = e.run()
    assert out["status"] == "failed"
    assert not out["conformance"]["report_links_frozen_nominations"]
    assert all(s["candidate_id"] != "invented-rule" for s in out["selection"]["nominations"])
    assert out["host_submission"]["candidates"]


def test_assessment_replays_without_model_or_fit_and_cannot_enter_legacy_front():
    g = FixtureGateway()
    out = engine(g).run()
    f = out["host_submission"]
    for nomination in out["selection"]["nominations"]:
        if nomination["candidate_id"]:
            args = (
                f,
                f["sha256"],
                nomination["candidate_id"],
                [{"x": 1.25, "group": "fixture-test"}],
                [0.4 + 0.2 * np.tanh(1.25 / 2)],
            )
            a = evaluate_bound_candidate(*args)
            assert a == evaluate_bound_candidate(*args)
            assert a["api_calls"] == a["fitting_attempts"] == 0
            assert pareto_front([a]) == []
    assert len(g.calls) == 7


def test_unpermitted_fields_and_task_metadata_never_enter_model_context():
    g = FixtureGateway()
    engine(g).run()
    for c in g.calls:
        assert "never send to a model" not in c["prompt"]
        assert "canary" not in c["prompt"]
        assert "unpermitted" not in c["prompt"]
    ctx = json.loads(g.calls[0]["prompt"])
    assert ctx["measurement_counts"] == {"train": 7, "dev": 3}
    assert len(ctx["train_preview"]) == 6


@pytest.mark.parametrize("fail_at", [1, 4, 7])
def test_ambiguous_failure_never_retried_and_partial_work_frozen(fail_at):
    g = FixtureGateway(fail_at=fail_at)
    e = engine(g)
    out = e.run()
    assert out["status"] == "failed"
    assert len(g.calls) == fail_at
    assert out["host_submission"]["candidates"]
    assert len(out["selection"]["nominations"]) == 3
    assert out == e.run()
    assert len(g.calls) == fail_at


def test_call_budget_and_exact_ids():
    g = FixtureGateway()
    out = engine(g, limits={"max_calls": 2}).run()
    assert out["status"] == "failed" and len(g.calls) == 2
    assert "budget" in out["failure"]["reason"]
    assert [c["request_id"] for c in g.calls] == [
        "synthetic-protocol--bound-v1--planner--1",
        "synthetic-protocol--bound-v1--coder--2",
    ]


def test_invalid_roles_fail_before_dispatch():
    for roles in [
        {},
        DEFAULT_ROLES | {"coder": "fallback-model"},
        {"coder": DEFAULT_ROLES["coder"]},
    ]:
        with pytest.raises(ValueError, match="Exact configured"):
            engine(roles=roles)


def test_gateway_model_substitution_is_fatal():
    class BadGateway(FixtureGateway):
        def complete(self, **request):
            return super().complete(**request) | {"model": "different"}

    g = BadGateway()
    out = engine(g).run()
    assert out["status"] == "failed" and len(g.calls) == 1
    assert "identity mismatch" in out["failure"]["reason"]


@pytest.mark.parametrize(
    "expression", ["0.123*x", "k_bad", "p0*x", "__import__('os')", "unknown_state*x"]
)
def test_invalid_kernel_cannot_bind_model_authored_state(expression):
    def alter(role, data, ctx):
        return (
            {"kernels": [{"name": "k_bad", "expression": expression}]}
            if role == "planner"
            else data
        )

    e = engine(FixtureGateway(transform=alter))
    out = e.run()
    assert "k_bad" not in e.kernels
    assert any(r["stage"] == "kernel_patch" for r in out["rejections"])


def test_false_critic_references_fail_before_second_round():
    def alter(role, data, ctx):
        if role == "critic":
            data["candidate_ids"] = ["unexecuted"]
        return data

    g = FixtureGateway(transform=alter)
    out = engine(g).run()
    assert out["status"] == "failed" and len(g.calls) == 3
    assert "executed candidate" in out["failure"]["reason"]


def test_fixed_denominator_with_no_candidates():
    selection = development_selection([])
    assert len(selection["nominations"]) == 3
    assert all(
        s["status"] == "unfilled" and s["candidate_id"] is None for s in selection["nominations"]
    )


def test_selection_uses_all_learned_scalars_not_only_final_parameters():
    h = BoundSearch(*fixture())
    a = h.fit("p0+p1*x", {"p0": 0, "p1": 1})
    k = h.promote(a["candidate_id"])
    b = h.fit("p0+p1*K", {"p0": 0, "p1": 1}, bindings=k["bindings"], kernels={"K": k["expression"]})
    a["dev_error"] = b["dev_error"] = 1.0  # Controlled selection fixture, not a run receipt.
    a["simplicity"]["weighted_operator_count"] = b["simplicity"]["weighted_operator_count"] = 3
    assert a["simplicity"]["free_parameters"] == b["simplicity"]["free_parameters"] == 2
    s = development_selection([b, a])
    assert s["frontier_ids"] == [a["candidate_id"]]
    assert s["nominations"][0]["candidate_id"] == a["candidate_id"]


def test_selection_rejects_mixed_policies():
    with pytest.raises(ValueError, match="mix"):
        development_selection([{"representation": "expression"}])


def test_shared_fixed_values_are_not_collapsed_as_one_structure():
    h = BoundSearch(*fixture())
    a = h.fit("n*x", bindings={"n": h.constants["one"]})
    b = h.fit("n*x", bindings={"n": h.constants["two"]})
    assert development_selection([a, b])["distinct_structure_count"] == 2


def test_stopped_before_run_has_zero_model_calls_and_frozen_empty_slots():
    g = FixtureGateway()
    out = engine(g, stopped=lambda: True).run()
    assert out["status"] == "failed" and not g.calls
    assert len(out["selection"]["nominations"]) == 3
    assert all(s["candidate_id"] is None for s in out["selection"]["nominations"])


def test_changed_configuration_changes_request_binding():
    a = engine()
    b = engine(limits={"max_fits": 8})
    assert a.configuration["sha256"] != b.configuration["sha256"]


def test_no_executed_revision_cannot_claim_complete_method():
    g = FixtureGateway()
    out = engine(g, limits={"max_fits": 2}).run()
    assert out["status"] == "incomplete_method_execution"
    assert out["host_submission"]["accounting"]["fitting_attempts"] == 2
    assert not out["conformance"]["two_executed_rounds"]
    assert len(out["selection"]["nominations"]) == 3


def test_payload_limit_is_explicit_and_dispatches_nothing():
    e = engine()
    e.rejections = [{"reason": "large-feedback" * 5000}]
    out = e.run()
    assert out["status"] == "failed"
    assert not e.gateway.calls
    assert "no hidden truncation" in out["failure"]["reason"]


def test_invalid_json_response_is_not_automatically_repaired():
    class InvalidJSON(FixtureGateway):
        def complete(self, **request):
            return super().complete(**request) | {"text": "not JSON"}

    g = InvalidJSON()
    out = engine(g).run()
    assert out["status"] == "failed"
    assert len(g.calls) == 1


def test_repeat_fits_do_not_fill_multiple_structural_slots():
    h = BoundSearch(*fixture())
    a = h.fit("p0+p1*x", {"p0": 0, "p1": 1})
    b = h.fit("p0+p1*x", {"p0": 3, "p1": 4})
    s = development_selection([a, b])
    assert s["all_candidate_count"] == 2 and s["distinct_structure_count"] == 1
    assert sum(v["status"] == "unfilled" for v in s["nominations"]) == 2


def test_all_nominations_assessed_under_pre_report_trusted_hash():
    out = engine().run()
    receipt = evaluate_bound_nominations(
        out,
        out["nomination_freeze"]["sha256"],
        [{"x": 1, "group": "test"}],
        [0.5],
        expected_result_sha256=out["sha256"],
    )
    assert receipt["fixed_denominator"] == len(receipt["receipts"]) == 3
    assert all(r["method_status"] == "complete" for r in receipt["receipts"])
    assert receipt["api_calls"] == receipt["fitting_attempts"] == 0


def test_empty_failed_method_keeps_all_assessment_slots():
    out = engine(stopped=lambda: True).run()
    receipt = evaluate_bound_nominations(
        out,
        out["nomination_freeze"]["sha256"],
        [{"x": 1}],
        [0.5],
        expected_result_sha256=out["sha256"],
    )
    assert len(receipt["receipts"]) == 3
    assert all(
        r["assessment"]["status"] == "unfilled" and r["method_status"] == "failed"
        for r in receipt["receipts"]
    )


@pytest.mark.parametrize(
    "field", ["selection", "host_submission", "configuration", "nomination_freeze"]
)
def test_post_freeze_nomination_mutations_are_rejected(field):
    out = engine().run()
    expected = out["nomination_freeze"]["sha256"]
    out[field]["mutation"] = True
    with pytest.raises(ValueError, match="mismatch|freeze|trusted host receipt"):
        evaluate_bound_nominations(
            out, expected, [{"x": 1}], [0.5], expected_result_sha256=out["sha256"]
        )


def test_failure_cannot_be_relabelled_as_complete_after_freeze():
    out = engine(stopped=lambda: True).run()
    expected = out["sha256"]
    out["status"] = "complete"
    out["sha256"] = sha({k: v for k, v in out.items() if k != "sha256"})
    with pytest.raises(ValueError, match="trusted host receipt"):
        evaluate_bound_nominations(
            out,
            out["nomination_freeze"]["sha256"],
            [{"x": 1}],
            [1],
            expected_result_sha256=expected,
        )
