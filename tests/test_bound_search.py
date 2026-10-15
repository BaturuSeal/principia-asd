import copy
import json

import numpy as np
import pytest

from principia_asd.engine.bindings import execute_program
from principia_asd.engine.bound_search import BoundSearch
from principia_asd.evaluate.bound import evaluate_bound_candidate, verify_frozen_candidate
from principia_asd.evaluate.metrics import pareto_front
from principia_asd.io import sha


def fixture():
    task = {
        "inputs": ["x"],
        "output": "y",
        "metric": {"primary": "rmse"},
        "stability": {"relative_noise": 0.01, "ranking": False},
    }

    def rows(prefix, values):
        return [
            {"sample_id": f"{prefix}{i}", "group": prefix, "x": float(x), "y": 2.0 + 3.0 * x}
            for i, x in enumerate(values)
        ]

    return task, rows("train", np.arange(-3, 4)), rows("dev", [0.5, 1.5, 2.5])


def host(**kwargs):
    return BoundSearch(*fixture(), **kwargs)


def fit(h):
    card = h.fit("p0+p1*x", {"p0": 0, "p1": 1})
    assert card is not None, h.failures
    return card


def test_real_fit_normalize_promote_refit_freeze_and_assess():
    h = host()
    norm = h.normalization("x")
    card = h.fit("p0+p1*z", {"p0": 0, "p1": 1}, bindings=norm, kernels={"z": "(x-center)/scale"})
    kernel = h.promote(card["candidate_id"])
    second = h.fit(
        "p0+p1*K",
        {"p0": 0, "p1": 1},
        bindings=kernel["bindings"],
        kernels={"K": kernel["expression"]},
    )
    profile = second["simplicity"]
    assert profile["final_stage_parameters"] == 2
    assert profile["inherited_fitted_scalars"] == 2
    assert profile["train_statistic_scalars"] == 2
    assert profile["learned_scalar_count"] == 6
    assert profile["numeric_literal_count"] == 0
    assert profile["degrees_of_freedom"] == "not_assessed"
    assert second["dev_error"] < 1e-8
    frozen = json.loads(json.dumps(h.freeze()))
    checked, registry = verify_frozen_candidate(frozen, frozen["sha256"], second["candidate_id"])
    np.testing.assert_allclose(
        execute_program(checked["program"], {"x": np.array([5.0, 6.0])}, registry), [17, 20]
    )
    receipt = evaluate_bound_candidate(
        frozen,
        frozen["sha256"],
        second["candidate_id"],
        [{"x": 5.0, "group": "test"}, {"x": 6.0, "group": "test"}],
        [17.0, 20.0],
    )
    assert receipt["accuracy"]["primary_error"] < 1e-8
    assert receipt["fitting_attempts"] == receipt["api_calls"] == 0
    assert receipt["simplicity"] == profile
    assert pareto_front([receipt]) == []
    assert frozen["accounting"]["fitting_attempts"] == 2
    assert frozen["accounting"]["optimizer_evaluations"] > 2
    assert h.freeze() == frozen


def test_dev_changes_do_not_change_fit_or_normalization_sources():
    task, train, dev = fixture()
    altered = copy.deepcopy(dev)
    for r in altered:
        r["x"] *= 100
        r["y"] -= 100
    a, b = BoundSearch(task, train, dev), BoundSearch(task, train, altered)
    assert a.normalization("x") == b.normalization("x")
    ca, cb = fit(a), fit(b)
    assert ca["final_fit_source"] == cb["final_fit_source"]
    assert ca["program"] == cb["program"]
    assert ca["dev_error"] != cb["dev_error"]


def test_model_cannot_supply_fixed_coefficients_or_false_provenance():
    h = host()
    assert h.fit("0.123*x") is None
    assert h.fit("c*x", bindings={"c": "model-asserted-source"}) is None
    assert h.fit("c*x", bindings={"c": {"value": 1, "scope": "train"}}) is None
    assert h.fits == h.optimizer_evaluations == 0
    assert len(h.failures) == 3


def test_all_model_parameter_values_are_initial_guesses_and_actually_fitted():
    h = host()
    c = h.fit("p0+p1*x", {"p0": 500, "p1": -100})
    np.testing.assert_allclose(
        list(c["program"]["specification"]["parameters"].values()), [2, 3], atol=1e-6
    )
    assert h.fits == 1
    assert h.registry.artifacts[c["final_fit_source"]]["initial"] == {"p0": 500, "p1": -100}


def test_normalization_reads_only_declared_inputs_and_reuses_source_identity():
    h = host()
    assert h.normalization("x") == h.normalization("x")
    with pytest.raises(KeyError):
        h.normalization("y")
    task, train, dev = fixture()
    for r in train:
        r["x"] = 1
    with pytest.raises(ValueError, match="nonconstant"):
        BoundSearch(task, train, dev).normalization("x")


def test_fit_budget_and_duplicate_requests_do_not_reexecute():
    h = host(max_fits=1)
    fit(h)
    evaluations = h.optimizer_evaluations
    assert h.fit("p0+p1*x", {"p0": 0, "p1": 1}) is None
    assert h.optimizer_evaluations == evaluations
    assert h.fit("p0+p1*x*x", {"p0": 0, "p1": 1}) is None
    assert h.fits == 1
    assert "Fitting budget" in h.failures[-1]["reason"]
    assert h.freeze()["accounting"]["duplicate_requests"] == 1


def test_optimizer_budget_counts_finite_difference_calls_and_retains_failure():
    h = host(max_optimizer_evaluations=2)
    assert h.fit("p0+p1*x", {"p0": 0, "p1": 1}) is None
    f = h.freeze()
    assert f["accounting"]["optimizer_evaluations"] == 2
    assert f["accounting"]["fitting_attempts"] == 1
    assert not f["candidates"]
    assert "Optimizer evaluation budget" in f["failures"][0]["reason"]


def test_structure_budget_before_more_execution():
    h = host(max_structures=1)
    fit(h)
    with pytest.raises(RuntimeError, match="Structure budget"):
        h.fit("x")


def test_invalid_domain_is_preserved_without_promotable_state():
    h = host()
    assert h.fit("p0*log(x)", {"p0": 1}) is None
    assert h.fits == 1 and h.optimizer_evaluations == 1
    assert not any(a["kind"] == "train_fitted" for a in h.registry.artifacts.values())
    assert "Nonfinite training" in h.failures[0]["reason"]


def test_eight_parameter_limit_includes_promoted_coefficients():
    h = host()
    k = h.promote(fit(h)["candidate_id"])
    assert (
        h.fit(
            "K+" + "+".join(f"p{i}*x" for i in range(7)),
            {f"p{i}": 1 for i in range(7)},
            bindings=k["bindings"],
            kernels={"K": k["expression"]},
        )
        is None
    )
    assert h.fits == 1
    assert "eight fitted scalars" in h.failures[-1]["reason"]


def test_fixed_program_does_not_invent_fit_receipt():
    h = host()
    c = h.fit("one*x+zero", bindings={k: h.constants[k] for k in ["one", "zero"]})
    assert c["final_fit_source"] is None and h.fits == 0
    assert c["simplicity"]["fixed_scientific_scalars"] == 2
    k = h.promote(c["candidate_id"])
    assert len(k["bindings"]) == 2


@pytest.mark.parametrize("action", ["fit", "normalization", "promote"])
def test_frozen_epoch_rejects_revision(action):
    h = host()
    c = fit(h)
    h.freeze()
    with pytest.raises(ValueError, match="frozen"):
        getattr(h, action)(c["candidate_id"] if action == "promote" else "x")


@pytest.mark.parametrize("mutation", ["value", "task", "card", "source", "failures"])
def test_trusted_freeze_rejects_any_artifact_mutation(mutation):
    h = host()
    c = fit(h)
    f = h.freeze()
    expected = f["sha256"]
    if mutation == "value":
        f["candidates"][0]["program"]["execution_values"]["p0"] = 77
    elif mutation == "task":
        f["task"]["output"] = "other"
    elif mutation == "card":
        f["candidates"][0]["simplicity"]["free_parameters"] = 0
    elif mutation == "source":
        f["source_artifacts"][c["final_fit_source"]]["scope"] = "test"
    else:
        f["failures"].append({"hidden": "failure"})
    # Recomputing a self-declared hash still cannot change the externally trusted anchor.
    f["sha256"] = sha({k: v for k, v in f.items() if k != "sha256"})
    with pytest.raises(ValueError, match="trusted host freeze"):
        verify_frozen_candidate(f, expected, c["candidate_id"])


def test_final_fit_receipt_required_even_with_consistent_self_hashes():
    h = host()
    fit(h)
    f = h.freeze()
    c = f["candidates"][0]
    c["final_fit_source"] = next(
        k for k, a in f["source_artifacts"].items() if a["kind"] == "fixed_scientific"
    )
    c["candidate_id"] = sha({k: v for k, v in c.items() if k != "candidate_id"})
    f["sha256"] = sha({k: v for k, v in f.items() if k != "sha256"})
    with pytest.raises(ValueError, match="host fit"):
        verify_frozen_candidate(f, f["sha256"], c["candidate_id"])


def test_returned_cards_and_freezes_do_not_mutate_host_state():
    h = host()
    c = fit(h)
    c["program"]["specification"]["parameters"]["p0"] = 100
    f = h.freeze()
    assert f["candidates"][0]["program"]["specification"]["parameters"]["p0"] != 100
    f["candidates"].clear()
    assert len(h.freeze()["candidates"]) == 1


def test_cancellation_and_wall_time_do_not_start_fit():
    h = host(stopped=lambda: True)
    with pytest.raises(InterruptedError):
        fit(h)
    assert h.fits == 0
    h = host(max_seconds=1)
    h.started -= 2
    with pytest.raises(TimeoutError):
        fit(h)
    assert h.fits == 0


@pytest.mark.parametrize("key", ["group", "sample_id"])
def test_split_leakage_rejected(key):
    task, train, dev = fixture()
    dev[0][key] = train[0][key]
    with pytest.raises(ValueError, match="leakage"):
        BoundSearch(task, train, dev)


def test_assessment_does_not_fit_again(monkeypatch):
    h = host()
    c = fit(h)
    f = h.freeze()

    def denied(*args, **kwargs):
        raise AssertionError("Assessment must not fit")

    monkeypatch.setattr("principia_asd.engine.bound_search.least_squares", denied)
    args = (f, f["sha256"], c["candidate_id"], [{"x": 8, "group": "test"}], [26])
    assert evaluate_bound_candidate(*args) == evaluate_bound_candidate(*args)


def test_opt_in_ranking_exclusion_preserves_legacy_front():
    old = {
        "status": "valid",
        "coverage": {"fraction": 1},
        "accuracy": {"primary_error": 1},
        "simplicity": {"free_parameters": 2, "weighted_operator_count": 3},
        "stability": {"ranking": False},
    }
    new = copy.deepcopy(old)
    new["accuracy"]["primary_error"] = 0
    new["simplicity"]["ranking_authorized"] = False
    assert pareto_front([old, new]) == [old]


def test_legacy_evaluator_cannot_silently_assess_explicit_state():
    from principia_asd.evaluate.metrics import evaluate_rule, predict

    h = host()
    c = h.fit("x")  # No bindings needed: still must use the separate policy.
    with pytest.raises(ValueError, match="bound evaluator"):
        predict(c, [{"x": 1}], h.task)
    with pytest.raises(ValueError, match="bound evaluator"):
        evaluate_rule(c, [{"x": 1}], [1], h.task)


def test_cancel_during_fit_retains_attempt_and_execution_count():
    calls = 0

    def stop():
        nonlocal calls
        calls += 1
        return calls >= 3

    h = host(stopped=stop)
    with pytest.raises(InterruptedError):
        h.fit("p0+p1*x", {"p0": 0, "p1": 1})
    f = h.freeze()
    assert f["accounting"]["fitting_attempts"] == 1
    assert f["accounting"]["optimizer_evaluations"] == 1
    assert f["failures"][0]["optimizer_evaluations"] == 1
