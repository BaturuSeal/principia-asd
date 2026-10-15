import copy
import json

import numpy as np
import pytest
from test_bound_checkpoint import PowerLoss
from test_bound_engine import fixture

from principia_asd.engine.bound_checkpoint import DurableBoundRun, RecoveryRequired
from principia_asd.engine.bound_data_to_paper import (
    BoundDataToPaper,
    checked_report,
    verified_facts,
)
from principia_asd.evaluate.bound import evaluate_bound_nominations
from principia_asd.evaluate.metrics import loss
from principia_asd.io import sha


class PaperGateway:
    """Deterministic fixture. Replies are not real model or scientific evidence."""

    def __init__(self, transform=None, crash_after=None):
        self.calls, self.receipts, self.recovered = [], {}, []
        self.transform, self.crash_after = transform, crash_after

    def complete(self, **request):
        assert request["request_id"] not in self.receipts, "paid call replayed"
        self.calls.append(copy.deepcopy(request))
        c = json.loads(request["prompt"])
        stage = c["paper_stage"]
        if stage == "analysis_plan":
            out = {
                "hypothesis": "Affine response",
                "inputs": ["x"],
                "output": "y",
                "metric": "rmse",
                "fit_partition": "train",
                "selection_partition": "dev",
                "limitations": ["synthetic observations"],
            }
        elif stage in ("analysis_program", "analysis_repair"):
            out = {"expression": "p0+p1*normalized_0", "initial": {"p0": 0, "p1": 1}}
        elif stage == "statistical_review":
            out = {
                "experiment_ids": [c["experiments"][-1]["experiment_id"]],
                "facts_sha256": c["computed_facts"]["sha256"],
                "limitations": ["independence not established"],
                "interpretation": "development only",
            }
        else:
            out = {
                "sections": [
                    {
                        "heading": "Results",
                        "template": "Development loss {{development_error}} and matched mean comparator {{baseline_development_error}}.",
                    }
                ],
                "observed_cohort": c["cohort"]["verified_counts"],
                "candidate_ids": [
                    s["candidate_id"]
                    for s in c["frozen_evidence"]["selection"]["nominations"]
                    if s["candidate_id"]
                ],
                "facts_sha256": c["computed_facts"]["sha256"],
                "limitation_ids": [v["id"] for v in c["retained_limitations"]],
                "limitations": [
                    "Only {{development_groups}} declared groups; dependence unreviewed."
                ],
            }
        if self.transform:
            out = self.transform(stage, out, c)
        response = {
            "text": json.dumps(out),
            "model": request["model"],
            "request_id": request["request_id"],
        }
        self.receipts[request["request_id"]] = (sha(request), response)
        if len(self.calls) == self.crash_after:
            self.crash_after = None
            raise PowerLoss()
        return response

    def recover_completed(self, **request):
        digest, response = self.receipts[request["request_id"]]
        assert sha(request) == digest
        self.recovered.append(request["request_id"])
        return copy.deepcopy(response)


def make(gateway=None, data=None, **kwargs):
    return BoundDataToPaper(
        *(data or fixture()), gateway=gateway or PaperGateway(), run_id="paper-fixture", **kwargs
    )


def test_staged_analysis_has_no_hidden_fits_and_every_number_has_a_bound_source():
    g = PaperGateway()
    e = make(g)
    out = e.run()
    assert out["status"] == "complete", out["failure"]
    assert all(out["conformance"].values())
    assert out["host_submission"]["accounting"]["fitting_attempts"] == 1
    assert len(out["host_submission"]["candidates"]) == 1
    assert len(g.calls) == 4
    assert [h["name"] for h in out["handoffs"]] == [
        "analysis_plan",
        "analysis_program",
        "statistical_review",
        "evidence_report",
    ]
    assert out["configuration"]["weak_prior_fits"] == 0
    bundle = out["computed_facts"]
    assert bundle == verified_facts(e.host, next(iter(e.host.candidates.values())))
    assert bundle["additional_fits"] == bundle["optimizer_evaluations"] == 0
    assert bundle["prediction_rows"] == 10
    assert out["statistical_accounting"][0]["prediction_executions"] == 2
    assert out["statistical_accounting"][0]["prediction_rows"] == 10
    assert bundle["values"]["preprocessing_scalars"] == 2
    assert bundle["values"]["free_parameters"] == 2
    assert bundle["values"]["learned_scalars"] == 4
    assert len(out["selection"]["nominations"]) == 3
    assert sum(s["status"] == "unfilled" for s in out["selection"]["nominations"]) == 2
    assert out["verified_report"]["valid"] and not out["ranking_authorized"]
    for i, request in enumerate(g.calls):
        context = json.loads(request["prompt"])
        assert out["handoffs"][i]["input_sha256"] == sha(context)
        assert context["preceding_handoffs"] == out["handoffs"][:i]
        assert "test_secret" not in request["prompt"] and "canary" not in request["prompt"]
    assert json.loads(g.calls[2]["prompt"])["experiments"] == out["experiments"]
    assert json.loads(g.calls[3]["prompt"])["computed_facts"] == bundle
    assert e.run() == out and len(g.calls) == 4


@pytest.mark.parametrize(
    "key,value",
    [
        ("inputs", ["y"]),
        ("output", "x"),
        ("metric", "mae"),
        ("selection_partition", "test"),
        ("fit_partition", "dev"),
        ("limitations", []),
        ("extra", "state"),
    ],
)
def test_bad_plan_stops_before_code_and_preserves_empty_denominator(key, value):
    def alter(stage, out, context):
        if stage == "analysis_plan":
            out[key] = value
        return out

    g = PaperGateway(alter)
    result = make(g).run()
    assert result["status"] == "incomplete_method_execution"
    assert len(g.calls) == 1
    assert result["host_submission"]["accounting"]["fitting_attempts"] == 0
    assert all(s["status"] == "unfilled" for s in result["selection"]["nominations"])


@pytest.mark.parametrize(
    "expression", ["0.4*x", "y", "unknown_state*x", "log(-abs(x))", "__import__('os')", "x +"]
)
def test_failed_analysis_repaired_once_from_real_diagnostics(expression):
    def alter(stage, out, context):
        if stage == "analysis_program":
            return {"expression": expression, "initial": {}}
        if stage == "analysis_repair":
            assert context["experiments"][0]["rejections"] or context["experiments"][0]["failures"]
        return out

    g = PaperGateway(alter)
    result = make(g).run()
    assert result["status"] == "complete", result["failure"]
    assert len(result["experiments"]) == 2 and len(g.calls) == 5
    assert result["experiments"][0]["result"] is None
    assert result["experiments"][1]["result"]


@pytest.mark.parametrize("kind", ["raw", "normalized", "state"])
def test_expanded_program_cannot_use_unplanned_measurement_or_its_fitted_statistics(kind):
    task, train, dev = fixture()
    task["inputs"].append("z")
    for rows in (train, dev):
        for row in rows:
            row["z"] = row["x"] ** 2

    def alter(stage, out, context):
        if stage in ("analysis_program", "analysis_repair"):
            expr = "z" if kind == "raw" else "normalized_1"
            if kind == "state":
                refs = context["inventory"]["kernels"][1]["expression"]
                expr = refs.split("state_")[1].split(")")[0]
                expr = "state_" + expr
            return {"expression": "p0*" + expr, "initial": {"p0": 1}}
        return out

    result = make(PaperGateway(alter), (task, train, dev)).run()
    assert result["status"] == "incomplete_method_execution", result["failure"]
    assert result["host_submission"]["accounting"]["fitting_attempts"] == 0
    assert all(
        "unplanned" in e["rejections"][0]["reason"] or "excluded" in e["rejections"][0]["reason"]
        for e in result["experiments"]
    )


def test_duplicate_failed_expression_cannot_trigger_another_optimizer_run():
    def alter(stage, out, context):
        if stage in ("analysis_program", "analysis_repair"):
            return {
                "expression": "p0*log(-abs(x))"
                if stage == "analysis_program"
                else "p0 * log( -abs(x))",
                "initial": {"p0": 1},
            }
        return out

    out = make(PaperGateway(alter)).run()
    assert out["status"] == "incomplete_method_execution"
    assert out["host_submission"]["accounting"]["fitting_attempts"] == 1
    assert (
        out["experiments"][1]["rejections"][0]["reason"]
        == "Analysis repair repeats the rejected program"
    )


@pytest.mark.parametrize(
    "fault",
    [
        "literal",
        "unicode",
        "limitation_number",
        "unknown_fact",
        "malformed",
        "missing_comparison",
        "wrong_cohort",
        "wrong_hash",
        "wrong_ids",
        "missing_limitation",
        "empty_limitations",
        "extra_key",
        "section_schema",
    ],
)
def test_report_guards_reject_unlinked_or_missing_evidence_without_refitting(fault):
    def alter(stage, out, context):
        if stage in ("evidence_report", "report_repair"):
            if fault in ("literal", "unicode", "unknown_fact", "malformed", "missing_comparison"):
                out["sections"][0]["template"] = {
                    "literal": "Loss is 0.3",
                    "unicode": "Loss is １２",
                    "unknown_fact": "{{invented}}",
                    "malformed": "{development_error}",
                    "missing_comparison": "{{development_error}}",
                }[fault]
            elif fault == "limitation_number":
                out["limitations"] = ["Only 3 rows"]
            elif fault == "wrong_cohort":
                out["observed_cohort"]["training_rows"] = 6
            elif fault == "wrong_hash":
                out["facts_sha256"] = "invented"
            elif fault == "wrong_ids":
                out["candidate_ids"] = []
            elif fault == "missing_limitation":
                out["limitation_ids"] = []
            elif fault == "empty_limitations":
                out["limitations"] = []
            elif fault == "extra_key":
                out["fit"] = "again"
            elif fault == "section_schema":
                out["sections"] = ["bad"]
        return out

    out = make(PaperGateway(alter)).run()
    assert out["status"] == "incomplete_method_execution", out["failure"]
    assert out["model_requests"] == 5
    assert out["host_submission"]["accounting"]["fitting_attempts"] == 1
    assert not out["verified_report"]["valid"] and not out["verified_report"]["sections"]


def test_report_only_repair_receives_errors_and_cannot_refit():
    e = make()

    def alter(stage, out, context):
        if stage == "evidence_report":
            out["sections"][0]["heading"] = "Results 1"
        if stage in ("statistical_review", "evidence_report", "report_repair"):
            assert e.host.closed
            with pytest.raises(ValueError, match="frozen"):
                e.host.fit("p0", {"p0": 0})
        if stage == "report_repair":
            assert context["report_guard_feedback"][-1]["errors"]
        return out

    e.gateway.transform = alter
    out = e.run()
    assert out["status"] == "complete"
    assert (
        out["model_requests"] == 5 and out["host_submission"]["accounting"]["fitting_attempts"] == 1
    )


@pytest.mark.parametrize(
    "field", ["experiment_ids", "facts_sha256", "limitations", "interpretation"]
)
def test_critic_must_link_executed_evidence(field):
    def alter(stage, out, context):
        if stage == "statistical_review":
            out[field] = [] if field.endswith("s") else ""
        return out

    result = make(PaperGateway(alter)).run()
    assert result["status"] == "incomplete_method_execution", result["failure"]
    assert not result["conformance"]["critic_links_executed_statistics"]


def test_group_matched_statistics_and_train_only_comparator():
    task, train, dev = fixture()
    dev[0]["group"] = "dev-second"
    e = make(data=(task, train, dev))
    result = e.run()
    facts = result["computed_facts"]
    baseline = np.full(len(dev), np.mean([r["y"] for r in train]))
    expected = loss(baseline, np.array([r["y"] for r in dev]), "rmse", [r["group"] for r in dev])
    assert facts["values"]["baseline_development_error"] == expected
    assert facts["comparator"]["train_sha256"] == e.host.context["train_sha256"]
    assert facts["values"]["development_groups"] == 2


@pytest.mark.parametrize(
    "kind", ["candidate", "source", "diagnostic", "facts", "missing_source", "input"]
)
def test_statistical_and_fitted_state_mutation_detected(kind):
    e = make()
    out = e.run()
    card = copy.deepcopy(next(iter(e.host.candidates.values())))
    if kind == "candidate":
        card["dev_error"] += 1
    if kind == "diagnostic":
        card["dev_error"] += 1
        card["candidate_id"] = sha({k: v for k, v in card.items() if k != "candidate_id"})
    if kind == "source":
        e.host.registry.artifacts[card["final_fit_source"]]["values"]["p0"] += 1
    if kind == "missing_source":
        card["final_fit_source"] = None
        card["candidate_id"] = sha({k: v for k, v in card.items() if k != "candidate_id"})
    if kind == "input":
        e.host.train[0]["x"] += 1
    if kind == "facts":
        out["computed_facts"]["values"]["development_error"] += 1
        with pytest.raises(ValueError, match="mutation"):
            checked_report(out["report"], out["computed_facts"], e.host, [], [])
    else:
        with pytest.raises(ValueError):
            verified_facts(e.host, card)


def durable(path, gateway, hook=lambda r: None):
    return DurableBoundRun(
        make(gateway), path, provider_binding={"fixture": "zero-api"}, after_record=hook
    )


@pytest.mark.parametrize("boundary", range(11))
def test_each_commit_recovers_without_refits_or_provider_replay(tmp_path, boundary):
    g = PaperGateway()

    def stop(record):
        if record["type"] == "commit" and record["sequence"] // 2 == boundary:
            raise PowerLoss()

    with pytest.raises(PowerLoss):
        durable(tmp_path, g, stop).run()
    out = durable(tmp_path, g).run()
    assert out["status"] == "complete", out["failure"]
    assert out["host_submission"]["accounting"]["fitting_attempts"] == 1 and len(g.calls) == 4
    assert durable(tmp_path, g).run() == out


@pytest.mark.parametrize("call", range(1, 5))
def test_cached_settled_call_recovers_exact_payload(tmp_path, call):
    g = PaperGateway(crash_after=call)
    with pytest.raises(PowerLoss):
        durable(tmp_path, g).run()
    out = durable(tmp_path, g).run()
    assert out["status"] == "complete", out["failure"]
    assert len(g.calls) == 4 and len(g.recovered) == 1


@pytest.mark.parametrize("name", ["analysis_program", "analysis-1", "computed_statistics"])
def test_unknown_work_is_not_replayed(tmp_path, name):
    g = PaperGateway()

    def stop(record):
        if record["type"] == "intent" and record["name"] == name:
            raise PowerLoss()

    with pytest.raises(PowerLoss):
        durable(tmp_path, g, stop).run()
    count = len(g.calls)
    with pytest.raises(RecoveryRequired):
        durable(tmp_path, g).run()
    assert len(g.calls) == count


@pytest.mark.parametrize("limits", [{"max_calls": 2}, {"max_optimizer_evaluations": 1}])
def test_limits_preserve_failure_and_three_slots(limits):
    out = make(limits=limits).run()
    assert out["status"] in ("failed", "incomplete_method_execution")
    assert len(out["selection"]["nominations"]) == 3
    assert out["model_requests"] <= limits.get("max_calls", 6)


def test_zero_api_assessment_and_cancel(monkeypatch):
    e = make()
    out = e.run()

    def forbidden(*args, **kwargs):
        pytest.fail("assessment refitted or called a provider")

    monkeypatch.setattr(e.host, "fit", forbidden)
    monkeypatch.setattr(e.gateway, "complete", forbidden)
    receipt = evaluate_bound_nominations(
        out,
        out["nomination_freeze"]["sha256"],
        [{"x": 0.5}],
        [0.45],
        expected_result_sha256=out["sha256"],
    )
    assert receipt["fixed_denominator"] == len(receipt["receipts"]) == 3
    assert receipt["api_calls"] == receipt["fitting_attempts"] == 0
    stopped = make(stopped=lambda: True).run()
    assert stopped["status"] == "failed" and stopped["model_requests"] == 0


@pytest.mark.parametrize(
    "boundary", ["analysis_repair", "analysis-2", "report_repair", "report_guard-2"]
)
def test_conditional_repairs_restore_without_new_calls_or_fits(tmp_path, boundary):
    def alter(stage, out, context):
        if stage == "analysis_program":
            return {"expression": "x+0.2", "initial": {}}
        if stage == "evidence_report":
            out["sections"][0]["heading"] = "Results 1"
        return out

    g = PaperGateway(alter)

    def stop(record):
        if record["type"] == "commit" and record["name"] == boundary:
            raise PowerLoss()

    with pytest.raises(PowerLoss):
        durable(tmp_path, g, stop).run()
    out = durable(tmp_path, g).run()
    assert out["status"] == "complete", out["failure"]
    assert len(g.calls) == 6 and out["host_submission"]["accounting"]["fitting_attempts"] == 1
    assert len(out["statistical_accounting"]) == 1
