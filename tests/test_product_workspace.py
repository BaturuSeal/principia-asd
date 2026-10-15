"""Task selection, display fidelity and custom-task evaluator isolation."""

import copy
from pathlib import Path

import pytest

from principia_asd.catalog.presentation import describe_scenario, describe_task
from principia_asd.io import file_sha, read_json, write_csv, write_json
from principia_asd.runtime import evaluate_run, worker
from principia_asd.web.rule_view import rule_view
from principia_asd.web.server import App
from principia_asd.web.tasks import create_task, resolve_task


@pytest.fixture
def example(tmp_path):
    scenario = tmp_path / "data/scenarios/P100-054"
    workspace = tmp_path / "private"
    task = {
        "task_id": "P100-054.example.v1",
        "scenario_id": "P100-054",
        "title": "Failure load",
        "inputs": ["width_um", "length_um"],
        "output": "target",
        "input_units": {"width_um": "um", "length_um": "um"},
        "output_units": "mN",
        "output_description": "Second-bridge failure load",
        "split": {
            "train": "public/train.csv.gz",
            "dev": "public/dev.csv.gz",
            "test": "public/test_inputs.csv.gz",
            "independent_unit": "Specimen",
        },
        "metric": {"primary": "mae", "aggregation": "equal_group_mean"},
        "stability": {
            "domain": "observed training range",
            "ranking": False,
            "relative_noise": 0.01,
        },
        "test_exposure": "retrospective-open-test",
    }
    write_json(scenario / "task-contracts/task-001.json", task)
    write_json(
        scenario / "scenario.json",
        {
            "scenario_id": "P100-054",
            "title": "Data set: a draft title",
            "rows": {"train": 12, "dev": 5, "test": 3},
        },
    )
    for part, indices in [("train", range(12)), ("dev", range(12, 17))]:
        write_csv(
            scenario / f"public/{part}.csv.gz",
            [
                {
                    "sample_id": f"s{i}",
                    "group": f"g{i}",
                    "width_um": i + 1,
                    "length_um": (i + 1) ** 2,
                    "target": 3 + 2 * i,
                }
                for i in indices
            ],
            ["sample_id", "group", "width_um", "length_um", "target"],
        )
    # A test canary that would fail parsing if accidentally opened while creating tasks.
    (scenario / "public/test_inputs.csv.gz").write_bytes(b"CONFIRMATION MUST NOT BE OPENED")
    settings = {
        "data_root": str(tmp_path / "data"),
        "workspace": str(workspace),
        "vault": str(tmp_path / "vault"),
        "leaderboard_root": str(tmp_path / "boards"),
    }
    return scenario, workspace, task, settings


def test_descriptions_preserve_contract_and_source_identity(example):
    scenario, _, task, _ = example
    original = copy.deepcopy(task)
    view = describe_task(task)
    assert view["display_title"] == "Predict second-bridge failure load"
    assert view["variables"][0]["description"] == "Cantilever specimen width"
    assert task == original
    s = describe_scenario(read_json(scenario / "scenario.json"), task)
    assert s["title"] == "Microfracture load and notch geometry"
    assert s["source_title"] == "Data set: a draft title"


def test_symbolic_formula_preserves_state_and_precedence():
    card = {
        "rule_id": "rule-1",
        "inputs": ["x"],
        "output": "y",
        "parameters": {"p0": 0.123456789, "p1": -9.87654321},
        "expression": "p0*(x-p1)/(x+0.333333333)",
    }
    original = copy.deepcopy(card)
    p = rule_view(
        card, {"output": "y", "title": "Response", "input_units": {"x": "s"}, "output_units": "V"}
    )
    assert "\\frac{" in p["latex"] and "\\theta_{1}" in p["latex"]
    assert "0.123456789" not in p["latex"] and "0.333333333" not in p["latex"]
    assert [x["value"] for x in p["parameters"]] == [0.123456789, -9.87654321, 0.333333333]
    assert "\\left(" in p["latex"]
    assert card == original
    assert rule_view(card | {"rule_id": "rule-2"}, {})["name"] != p["name"]


def test_bound_state_and_complete_tree_are_not_hidden():
    card = {
        "candidate_id": "bound",
        "inputs": ["x"],
        "output": "y",
        "program": {
            "expression": "p0*(x-bound0)",
            "execution_values": {"p0": 2.2, "bound0": 0.9},
            "states": {"a": {"value": 0.9, "kind": "train_statistic", "value_path": ["mean", "x"]}},
        },
    }
    p = rule_view(card, {"output": "y", "title": "Response"})
    assert len(p["parameters"]) == 2 and "Train statistic" in p["parameters"][1]["description"]
    tree = {
        "rule_id": "tree",
        "representation": "tree",
        "inputs": ["x"],
        "output": "y",
        "tree": {
            "features": ["x"],
            "feature": [0, -2, -2],
            "threshold": [0.45, -2, -2],
            "left": [1, -1, -1],
            "right": [2, -1, -1],
            "value": [0.5, 0.2, 0.8],
        },
    }
    p = rule_view(tree, {"title": "Response", "output": "y"})
    assert "\\begin{cases}" in p["expanded_latex"] and len(p["parameters"]) == 3
    assert [v["value"] for v in p["parameters"]] == [0.45, 0.2, 0.8]


def test_custom_task_complete_execution_never_inherits_test(example, monkeypatch):
    scenario, workspace, base, settings = example
    before = {str(p): file_sha(p) for p in scenario.rglob("*") if p.is_file()}
    result = create_task(
        scenario,
        workspace,
        {
            "title": "Predict specimen width",
            "inputs": ["length_um", "target"],
            "output": "width_um",
        },
    )
    path, task = resolve_task(scenario, workspace, result["task_id"])
    assert task["scenario_id"] != base["scenario_id"] and task["output"] == "width_um"
    assert task["assessment_policy"] == "development_only"
    assert {str(p): file_sha(p) for p in scenario.rglob("*") if p.is_file()} == before
    folder = workspace / "runs/custom-test"
    write_json(
        folder / "request.json",
        {
            "scenario_id": "P100-054",
            "task_id": task["task_id"],
            "scenario_path": str(path),
            "method_id": "linear_control",
            "created_at": "2026-10-14",
            "limits": {"max_fits": 10, "wall_seconds": 60},
        },
    )
    # Install an apparent vault so absence cannot accidentally enforce the policy.
    write_json(
        Path(settings["vault"]) / task["scenario_id"] / "evaluator-manifest.json",
        {"trap": "must not be read"},
    )
    monkeypatch.setattr(
        "principia_asd.runtime.evaluate_run", lambda *a, **k: pytest.fail("Worker called evaluator")
    )
    worker(folder, settings)
    assert read_json(folder / "submission.json")["status"] == "complete"
    assert not (folder / "evaluation.json").exists()
    with pytest.raises(ValueError, match="development-only"):
        evaluate_run(folder, Path(settings["vault"]))


def test_invalid_task_definition_and_target_alias(example):
    scenario, workspace, _, _ = example
    for inputs, output in [
        (["target"], "target"),
        (["group"], "target"),
        (["width_um", "width_um"], "target"),
        (["missing"], "target"),
    ]:
        with pytest.raises(ValueError):
            create_task(
                scenario, workspace, {"title": "Invalid task", "inputs": inputs, "output": output}
            )
    assert not (workspace / "imports").exists()


def test_multitask_catalog_selection_and_portfolios(example):
    scenario, workspace, task, settings = example
    result = create_task(
        scenario,
        workspace,
        {"title": "Width from length", "inputs": ["length_um"], "output": "width_um"},
    )
    app = App(settings)
    try:
        catalog = app.catalog()
        assert len(catalog) == 1 and len(catalog[0]["tasks"]) == 2
        assert catalog[0]["local_path"] == str(scenario.resolve())
        assert catalog[0]["tasks"][1]["custom"]
        with pytest.raises(ValueError, match="belonging"):
            resolve_task(scenario, workspace, "other-task")
        # Two task boards must survive, even with the same scenario identity.
        for task_id in [task["task_id"], result["task_id"]]:
            write_json(
                Path(settings["leaderboard_root"])
                / "scenarios/P100-054/tasks"
                / task_id
                / "leaderboard.json",
                {"scenario_id": "P100-054", "task_id": task_id, "rules": []},
            )
        assert {b["task_id"] for b in app.leaderboards()} == {task["task_id"], result["task_id"]}
        assert (
            next(m for m in app.config()["methods"] if m["method_id"] == "principia_engine")["name"]
            == "Adaptive Primitive Search (APS)"
        )
    finally:
        app.pool.shutdown()
        app.server_lock.close()


def test_shared_source_columns_are_not_exposed_to_selected_method(example, monkeypatch):
    from principia_asd import runtime
    from principia_asd.io import read_csv

    scenario, workspace, task, settings = example
    for part in ("train", "dev"):
        path = scenario / task["split"][part]
        rows = [r | {"another_task_output": 999} for r in read_csv(path)]
        write_csv(path, rows, list(rows[0]))
    execute = runtime.execute_method

    def checked(method, contract, train, dev, **kwargs):
        assert all(
            set(r) == {"sample_id", "group", *task["inputs"], task["output"]} for r in train + dev
        )
        return execute(method, contract, train, dev, **kwargs)

    monkeypatch.setattr(runtime, "execute_method", checked)
    folder = workspace / "runs/field-projection-test"
    write_json(
        folder / "request.json",
        {
            "scenario_id": task["scenario_id"],
            "scenario_path": str(scenario),
            "method_id": "mean_control",
            "limits": {"wall_seconds": 60},
        },
    )
    worker(folder, settings, evaluate=False)
    assert read_json(folder / "submission.json")["status"] == "complete"
