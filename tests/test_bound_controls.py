import copy

import numpy as np
import pytest

from principia_asd.engine.bound_checkpoint import DurableBoundRun, RecoveryRequired
from principia_asd.engine.bound_controls import CONTROLS, POLICY, BoundControl, fixed_plan
from principia_asd.engine.bound_search import BoundSearch
from principia_asd.evaluate.bound import evaluate_bound_nominations, verify_frozen_candidate
from principia_asd.evaluate.metrics import pareto_front
from principia_asd.io import read_json, write_json


def fixture(n=2, metric="rmse"):
    names = [f"x{i}" for i in range(n)]
    rng = np.random.default_rng(39)
    task = {
        "inputs": names,
        "output": "y",
        "metric": {"primary": metric},
        "stability": {"ranking": False},
    }

    def rows(group, size):
        values = rng.uniform(-2, 2, size=(size, n))
        return [
            {
                "sample_id": f"{group}-{i}",
                "group": group,
                **{name: float(x[j]) for j, name in enumerate(names)},
                "y": float(3 + 0.2 * x[0] + 0.1 * x[-1] ** 2),
            }
            for i, x in enumerate(values)
        ]

    return task, rows("train", 30), rows("dev", 8)


def control(method="fixed_symbolic", n=2, **kwargs):
    return BoundControl(*fixture(n), control=method, run_id="synthetic-control", **kwargs)


def assess(result):
    return evaluate_bound_nominations(
        result,
        result["nomination_freeze"]["sha256"],
        [{"x0": 0.3, "x1": 0.4, "group": "confirmation-fixture"}],
        [3.076],
        expected_result_sha256=result["sha256"],
    )


@pytest.mark.parametrize("method", CONTROLS)
def test_same_host_expanded_state_and_fixed_slots(method):
    e = control(method)
    result = e.run()
    assert result["status"] == "complete", result["failure"]
    assert result["model_requests"] == result["host_submission"]["accounting"]["api_calls"] == 0
    assert result["configuration"]["max_model_requests"] == 0
    assert len(result["selection"]["nominations"]) == 3
    assert result["policy"] == POLICY and not result["ranking_authorized"]
    f = result["host_submission"]
    for c in f["candidates"]:
        card, registry = verify_frozen_candidate(f, f["sha256"], c["candidate_id"])
        assert card == c
        simplicity = c["simplicity"]
        assert simplicity["free_parameters"] == len(c["program"]["specification"]["parameters"])
        assert simplicity["inherited_fitted_scalars"] == 0
        for state in c["program"]["states"].values():
            source = registry.artifacts[state["artifact_sha256"]]
            if state["kind"] != "fixed_scientific":
                assert source["train_sha256"] == f["context"]["train_sha256"]
    if method == "quadratic":
        c = f["candidates"][0]
        assert c["dev_error"] < 1e-7
        assert c["simplicity"]["free_parameters"] == 6
        assert c["simplicity"]["train_statistic_scalars"] == 4
    if method == "fitted_constant":
        assert f["candidates"][0]["simplicity"]["learned_scalar_count"] == 1
    assert e.run() == result


@pytest.mark.parametrize(
    "method,expected",
    [("fitted_constant", 1), ("affine", 1), ("quadratic", 1), ("fixed_symbolic", 10)],
)
def test_exact_fit_counts_and_solver_accounting(method, expected):
    result = control(method).run()
    accounting = result["host_submission"]["accounting"]
    assert accounting["fitting_attempts"] == expected
    assert accounting["structures"] == expected
    assert accounting["duplicate_requests"] == 0
    assert accounting["optimizer_evaluations"] > expected
    assert (
        sum(
            s.get("optimizer_evaluations", 0)
            for s in result["host_submission"]["source_artifacts"].values()
        )
        == accounting["optimizer_evaluations"]
    )


def test_train_statistics_and_fits_are_independent_of_development_values(monkeypatch):
    import principia_asd.engine.bound_search as search

    solver = search.least_squares
    objectives = []

    def capture_objective(fun, initial, **kwargs):
        # Inspect identical objective probes before optimization, rather than
        # mistaking platform solver roundoff for a change to the fitting data.
        values = np.asarray(initial, dtype=float)
        objectives.append((fun(values).copy(), fun(values + 0.25).copy()))
        return solver(fun, initial, **kwargs)

    monkeypatch.setattr(search, "least_squares", capture_objective)
    task, train, dev = fixture()
    changed = copy.deepcopy(dev)
    for row in changed:
        row["x0"] += 100
        row["y"] += 500
    a = BoundControl(task, train, dev, control="fixed_symbolic", run_id="a").run()
    first_objectives = objectives[:]
    objectives.clear()
    b = BoundControl(task, train, changed, control="fixed_symbolic", run_id="b").run()
    assert a["configuration"]["plan"] == b["configuration"]["plan"]
    assert len(first_objectives) == len(objectives) == 10
    for before, after in zip(first_objectives, objectives, strict=True):
        for x, y in zip(before, after, strict=True):
            np.testing.assert_array_equal(x, y)

    def statistics(r):
        return {
            k: v
            for k, v in r["host_submission"]["source_artifacts"].items()
            if v["kind"] == "train_statistic"
        }

    assert statistics(a) == statistics(b)

    def programs(r):
        return [c["program"]["specification"] for c in r["host_submission"]["candidates"]]

    for before, after in zip(programs(a), programs(b), strict=True):
        assert {k: v for k, v in before.items() if k != "parameters"} == {
            k: v for k, v in after.items() if k != "parameters"
        }
        assert before["parameters"].keys() == after["parameters"].keys()
        np.testing.assert_allclose(
            list(before["parameters"].values()),
            list(after["parameters"].values()),
            rtol=1e-8,
            atol=1e-9,
        )
    assert (
        a["host_submission"]["context"]["dev_sha256"]
        != b["host_submission"]["context"]["dev_sha256"]
    )


def test_fixed_plan_discloses_capacity_exclusions_and_all_input_identity_terms():
    e = control(n=8)
    cfg = e.configuration
    assert len(cfg["plan"]) == 33
    assert len(cfg["scheduled_plan"]) == 16
    assert len(cfg["capacity_excluded_plan"]) == 17
    assert [s["terms"] for s in cfg["plan"][1:9]] == [[["identity", i]] for i in range(8)]
    out = e.run()
    assert out["status"] == "complete"
    assert out["host_submission"]["accounting"]["fitting_attempts"] == 16
    assert all(c["inputs"] == fixture(8)[0]["inputs"] for c in out["host_submission"]["candidates"])


@pytest.mark.parametrize(
    "method,n", [("quadratic", 3), ("affine", 8), ("fixed_symbolic", 9), ("fitted_constant", 9)]
)
def test_unsupported_full_bases_keep_three_empty_slots_and_zero_fits(method, n):
    out = control(method, n).run()
    assert out["status"] == "unsupported"
    assert out["configuration"]["unsupported_reason"]
    assert out["host_submission"]["accounting"]["fitting_attempts"] == 0
    assert len(out["selection"]["nominations"]) == 3
    assert all(s["status"] == "unfilled" for s in out["selection"]["nominations"])
    result = assess(out)
    assert result["fixed_denominator"] == 3
    assert all(r["method_status"] == "unsupported" for r in result["receipts"])


def test_nonconstant_full_basis_is_not_silently_replaced_by_subset():
    task, train, dev = fixture()
    for row in train:
        row["x1"] = 1.0
    out = BoundControl(task, train, dev, control="quadratic", run_id="constant-input").run()
    assert out["status"] == "incomplete_method_execution"
    assert out["experiments"][0]["inputs"] == ["x1"]
    assert out["host_submission"]["accounting"]["fitting_attempts"] == 0
    assert all(s["status"] == "unfilled" for s in out["selection"]["nominations"])


def test_budget_failure_is_retained_without_inventing_completed_search():
    out = control(limits={"max_optimizer_evaluations": 1}).run()
    assert out["status"] == "incomplete_method_execution"
    assert out["host_submission"]["accounting"]["optimizer_evaluations"] == 1
    assert out["host_submission"]["failures"]
    assert all(r["status"] == "budget_exhausted" for r in out["experiments"])
    assert len(out["selection"]["nominations"]) == 3


def test_cancellation_retains_completed_fit_and_unfilled_slots():
    stop = {"value": False}
    e = control(
        stopped=lambda: stop["value"],
        event=lambda stage, detail: (
            stop.update(value=True) if stage == "fixed_experiment" else None
        ),
    )
    out = e.run()
    assert out["status"] == "failed"
    assert out["failure"]["type"] == "InterruptedError"
    assert out["host_submission"]["accounting"]["fitting_attempts"] == 1
    assert sum(s["status"] == "nominated" for s in out["selection"]["nominations"]) == 1


def test_numeric_failure_is_not_repaired_or_removed():
    task, train, dev = fixture(metric="log_mae")
    for row in train:
        row["y"] = -1.0
    out = BoundControl(task, train, dev, control="fitted_constant", run_id="domain").run()
    assert out["status"] == "failed"
    assert out["host_submission"]["failures"]
    assert out["host_submission"]["accounting"]["fitting_attempts"] == 1


def test_constant_is_solver_fit_not_claimed_to_be_mae_optimal_median():
    task, train, dev = fixture(metric="mae")
    for i, row in enumerate(train):
        row["y"] = 40.0 if i == 0 else 1.0
    out = BoundControl(
        task, train, dev, control="fitted_constant", run_id="squared-objective"
    ).run()
    c = out["host_submission"]["candidates"][0]
    assert c["program"]["specification"]["parameters"]["p0"] == pytest.approx(
        np.mean([r["y"] for r in train])
    )
    assert "squared residuals" in out["configuration"]["fitting_objective"]


@pytest.mark.parametrize(
    "bad",
    [
        {"max_calls": 1},
        {"max_fits": 17},
        {"max_fits": True},
        {"max_seconds": 0},
        [],
        {"max_optimizer_evaluations": 1.5},
    ],
)
def test_limits_cannot_silently_expand_or_add_provider_requests(bad):
    with pytest.raises(ValueError):
        control(limits=bad)


def test_unknown_control_rejected():
    with pytest.raises(ValueError, match="Unknown"):
        fixed_plan("tree", ["x"])


def test_leakage_rejected_before_control_execution():
    task, train, dev = fixture()
    dev[0]["group"] = "train"
    with pytest.raises(ValueError, match="leakage"):
        BoundControl(task, train, dev, control="affine", run_id="leakage")


def test_zero_fit_assessment_preserves_fixed_denominator_and_ranking_exclusion(monkeypatch):
    out = control("fitted_constant").run()

    def forbidden(*a, **kw):
        raise AssertionError("Assessment must never fit")

    monkeypatch.setattr(BoundSearch, "fit", forbidden)
    a = assess(out)
    assert a == assess(out)
    assert a["fixed_denominator"] == 3
    assert sum(r["assessment"]["status"] == "unfilled" for r in a["receipts"]) == 2
    assert a["api_calls"] == a["fitting_attempts"] == 0
    assert not a["ranking_authorized"]
    assert pareto_front([r["assessment"] for r in a["receipts"]]) == []


@pytest.mark.parametrize("target", ["configuration", "nomination_freeze", "host_submission"])
def test_mutated_artifacts_are_refused(target):
    out = control().run()
    out[target]["tampered"] = True
    with pytest.raises(ValueError, match="trusted host receipt"):
        assess(out)


class PowerLoss(BaseException):
    pass


def journal(folder, hook=lambda _: None, **kw):
    return DurableBoundRun(
        control(n=1, **kw),
        folder,
        provider_binding={"provider": "none", "api_calls": 0},
        after_record=hook,
    )


@pytest.mark.parametrize("boundary", range(7))
def test_every_committed_boundary_resumes_without_refitting(tmp_path, boundary):
    def stop(record):
        if record["type"] == "commit" and record["sequence"] // 2 == boundary:
            raise PowerLoss()

    with pytest.raises(PowerLoss):
        journal(tmp_path, stop).run()
    out = journal(tmp_path).run()
    assert out["status"] == "complete"
    assert out["host_submission"]["accounting"]["fitting_attempts"] == 5
    assert len(out["experiments"]) == 5
    assert journal(tmp_path).run() == out
    assert out["model_requests"] == 0


def test_interrupted_local_fit_stays_ambiguous_and_is_not_replayed(tmp_path):
    def stop(record):
        if record["type"] == "intent" and record["name"] == "fixed-experiment-1":
            raise PowerLoss()

    with pytest.raises(PowerLoss):
        journal(tmp_path, stop).run()
    before = {p.name: p.read_bytes() for p in (tmp_path / "checkpoints").glob("*.json")}
    with pytest.raises(RecoveryRequired, match="numerical work.*unknown"):
        journal(tmp_path).run()
    assert before == {p.name: p.read_bytes() for p in (tmp_path / "checkpoints").glob("*.json")}


def test_changed_configuration_refuses_resume(tmp_path):
    journal(tmp_path).run()
    with pytest.raises(ValueError, match="configuration changed"):
        journal(tmp_path, limits={"max_fits": 2}).run()


def test_changed_checkpoint_refuses_resume(tmp_path):
    journal(tmp_path).run()
    path = tmp_path / "checkpoints/0003.json"
    data = read_json(path)
    data["state"]["host"]["fits"] = 0
    write_json(path, data)
    with pytest.raises(ValueError, match="integrity"):
        journal(tmp_path).run()
