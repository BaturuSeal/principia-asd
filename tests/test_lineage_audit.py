import runpy
from pathlib import Path

import pytest

from principia_asd.engine.lineage_audit import audit_expression
from principia_asd.io import file_sha, write_csv, write_json


@pytest.fixture
def archived_campaign(tmp_path):
    audit = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "scripts/audit_literal_lineage.py")
    )["audit"]
    runtime = tmp_path / "runtime/src/principia_asd/engine/search.py"
    runtime.parent.mkdir(parents=True)
    runtime.write_text("# isolated fixture source")
    audit.__globals__["REVIEWED_GRAMMAR_SHA256"] = file_sha(runtime)
    campaign = tmp_path / "campaigns/fixture"
    scenario = tmp_path / "data"
    train = scenario / "train.csv"
    write_csv(train, [{"x": 1.0}, {"x": 3.0}], ["x"])
    jobs = []
    frozen = {}
    for index, status in enumerate(["complete", "failed"]):
        run_id = f"run-{index}"
        jobs.append({"run_id": run_id, "scenario_id": "fixture", "method_id": "anonymous"})
        folder = tmp_path / "runs" / run_id
        write_json(folder / "request.json", {"scenario_path": str(scenario)})
        write_json(folder / "manifest.json", {"input_hashes": {"train": file_sha(train)}})
        write_json(
            folder / "submission.json",
            {
                "contract": {"split": {"train": "train.csv"}},
                "status": status,
                "rules": [rule("p0*tanh((x-2.0)/1.0)")] if status == "complete" else [],
                "trace": [],
            },
        )
        write_json(
            folder / "submission-freeze.json",
            {
                "submission_sha256": file_sha(folder / "submission.json"),
                "manifest_sha256": file_sha(folder / "manifest.json"),
            },
        )
        frozen[run_id] = file_sha(folder / "submission.json")
    write_json(
        campaign / "manifest.json",
        {"jobs": jobs, "source_hashes": {"engine/search.py": file_sha(runtime)}},
    )
    write_json(campaign / "launch.json", {"runtime_source": str(runtime.parents[2])})
    write_json(
        campaign / "submission-freeze.json",
        {"manifest_sha256": file_sha(campaign / "manifest.json"), "submissions": frozen},
    )
    return audit, tmp_path


def test_campaign_audit_keeps_failures_and_changes_no_inputs(archived_campaign):
    audit, root = archived_campaign
    before = {str(p): file_sha(p) for p in root.rglob("*") if p.is_file()}
    result = audit(root, "fixture")
    assert result["summary"]["attempts"] == 2
    assert result["summary"]["attempt_status_counts"] == {"complete": 1, "failed": 1}
    assert result["summary"]["known_grammar_normalization_rules"] == 1
    assert result["api_calls"] == result["fitting_attempts"] == 0
    assert before == {str(p): file_sha(p) for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize(
    "relative",
    [
        "data/train.csv",
        "runtime/src/principia_asd/engine/search.py",
        "runs/run-0/submission.json",
        "runs/run-0/manifest.json",
        "campaigns/fixture/manifest.json",
    ],
)
def test_campaign_audit_rejects_changed_bindings(archived_campaign, relative):
    audit, root = archived_campaign
    path = root / relative
    path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError, match="mutation"):
        audit(root, "fixture")


def rule(expression, **kw):
    return {
        "rule_id": "fixture",
        "representation": "expression",
        "inputs": ["x"],
        "parameters": {"p0": 1.0},
        "expression": expression,
        "origin": "grammar-round-0",
        "simplicity": {"free_parameters": 1},
        **kw,
    }


def test_signed_whole_fit_match_not_decimal_guess():
    trace = [
        {
            "diagnostics": {
                "best": [{"expression": "a+b*x", "parameters": {"a": 0.456, "b": -0.114}}]
            }
        },
        {"kernel_library": [{"expression": ".456-.114*x", "round": 0, "model": "critic"}]},
    ]
    found = audit_expression(rule("p0*(.456-.114*x)"), trace, [{"x": 1.0}, {"x": 3.0}], "source")
    assert len(found["prior_fit_matches"]) == 1
    assert found["prior_fit_matches"][0]["later_saved_kernel_matches"][0]["kernel_index"] == 0
    assert not found["normalization_witnesses"]
    rounded = audit_expression(rule("p0*(.456-.11*x)"), trace, [{"x": 1.0}, {"x": 3.0}], "source")
    assert not rounded["prior_fit_matches"]
    assert rounded["full_learned_state_status"] == "not_assessed"


def test_train_normalization_counted_once_when_repeated():
    found = audit_expression(
        rule("p0*(tanh((x-2.0)/1.0)+log1p(abs((x-2.0)/1.0)))"),
        [],
        [{"x": 1.0}, {"x": 3.0}],
        "source",
    )
    assert len(found["normalization_witnesses"]) == 1
    assert found["normalization_witnesses"][0]["statistics"] == 2
    assert found["normalization_witnesses"][0]["source"]["sha256"] == "source"


def test_equal_literals_without_known_computation_not_proven_origin():
    found = audit_expression(
        rule("p0*tanh((x-2.0)/1.0)", origin="single_generation"),
        [],
        [{"x": 1.0}, {"x": 3.0}],
        "source",
    )
    assert found["scan_status"] == "no_exact_match_not_a_clearance"


@pytest.mark.parametrize("method", ["principia_engine", "competitor", "anonymous"])
def test_method_identity_does_not_affect_deterministic_audit(method):
    found = audit_expression(
        rule("p0*tanh((x-2.0)/1.0)", method_id=method), [], [{"x": 1.0}, {"x": 3.0}], "source"
    )
    assert len(found["normalization_witnesses"]) == 1


def test_tree_and_no_witness_are_not_cleared():
    found = audit_expression(rule("tree", representation="tree"), [], [], "source")
    assert found["scan_status"] == "nonexpression_not_assessed"
    assert found["full_learned_state_status"] == "not_assessed"
