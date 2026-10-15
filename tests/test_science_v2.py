import json
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

from principia_asd.engine.expression import execute, parse
from principia_asd.engine.search import execute_method
from principia_asd.evaluate.metrics import evaluate_rule, loss, pareto_front
from principia_asd.io import file_sha, read_json, write_csv, write_json
from principia_asd.runtime import discover_run, evaluate_run, worker
from principia_asd.store.ledger import BudgetExceeded, CostLedger, DuplicateRequest


def test_cancelled_worker_does_not_read_data_or_call_provider(tmp_path):
    folder = tmp_path / "cancelled"
    folder.mkdir()
    write_json(folder / "request.json", {"scenario_path": "/does-not-exist"})
    (folder / "cancel.requested").touch()
    worker(folder, {"workspace": str(tmp_path)})
    assert read_json(folder / "state.json")["status"] == "cancelled"
    assert not (folder / "submission.json").exists()


def test_campaign_cannot_be_cancelled_through_interactive_ui(tmp_path):
    from principia_asd.web.server import App

    class CampaignView:
        def run_path(self, _):
            return tmp_path

        def get_run(self, *_):
            return {"mode": "campaign", "status": "running"}

    with pytest.raises(ValueError, match="managed together"):
        App.cancel(CampaignView(), "campaign-fixture")
    assert not (tmp_path / "cancel.requested").exists()


@pytest.mark.parametrize(
    "method",
    [
        "principia_engine",
        "principia_engine_explicit",
        "agent_laboratory",
        "data_to_paper",
        "asta_autodiscovery",
        "agentrxiv",
    ],
)
@pytest.mark.parametrize("unverified_role", ["planner", "critic", "reporter"])
def test_ui_requires_every_used_model_capability(tmp_path, method, unverified_role, monkeypatch):
    from principia_asd.methods.registry import DEFAULT_ROLES
    from principia_asd.web.server import App

    monkeypatch.setattr("principia_asd.web.credentials.status", lambda _: {"configured": True})

    class UnprobedRole:
        workspace = tmp_path
        lock = threading.RLock()
        probe_pending = False
        _start = App._start

        def scenario_paths(self):
            return {"TEST": tmp_path}

        def capabilities(self):
            return {
                model: {"state": "verified"}
                for role, model in DEFAULT_ROLES.items()
                if role != unverified_role
            }

    with pytest.raises(ValueError, match="capability checks"):
        App.start(UnprobedRole(), {"scenario_id": "TEST", "method_id": method})
    assert not list(tmp_path.iterdir())


@pytest.fixture
def task():
    return {
        "task_id": "TEST.v2",
        "scenario_id": "TEST",
        "inputs": ["x", "z"],
        "output": "target",
        "output_units": "units",
        "input_units": {"x": "units", "z": "units"},
        "title": "Fixture",
        "split": {
            "train": "public/train.csv.gz",
            "dev": "public/dev.csv.gz",
            "test": "public/test_inputs.csv.gz",
        },
        "metric": {"primary": "mae"},
        "stability": {
            "domain": "training range",
            "ranking": False,
            "input_ranges": {"x": [-3, 3], "z": [-2, 2]},
            "output_scale": 1,
        },
        "test_exposure": "local-user-split",
        "accuracy_gate": {"ratio": 1},
    }


def rows(start, n):
    return [
        {
            "sample_id": str(i),
            "group": str(i // 10),
            "x": (i % 17) / 4,
            "z": (i % 13) / 6,
            "target": 2 + 3 * (i % 17) / 4 - 2 * (i % 13) / 6,
        }
        for i in range(start, start + n)
    ]


@pytest.mark.parametrize(
    "expr",
    [
        "open('/tmp/canary').read()",
        "__import__('os').getenv('SILICONFLOW_API_KEY')",
        "x.__class__",
        "[x for x in z]",
        "(lambda: x)()",
        "x**999999",
        "target+x",
        "sample_id+x",
        "x[0]",
        "sin(x, z)",
    ],
)
def test_no_ambient_capabilities(expr):
    with pytest.raises((ValueError, SyntaxError)):
        parse(expr, ["x", "z"])


def test_piecewise():
    assert execute("where(x > 0, x, -x)", {"x": np.array([-2, 3])}).tolist() == [2, 3]


def test_large_integer_literals_use_bounded_float_arithmetic():
    value = execute(
        "999999999999999999999999999999999999999999 ** (+1000000)", {"x": np.array([1.0])}
    )
    assert np.isinf(value[0])


def test_group_metric():
    assert loss([0, 0, 0], [1, 1, 9], "mae", ["a", "a", "b"]) == 5
    assert loss([0, 0], [3, 4], "rmse") == pytest.approx(np.sqrt(12.5))
    assert loss([2], [4], "log_mae") == pytest.approx(np.log(2))
    with pytest.raises(ValueError):
        loss([0], [4], "log_mae")


def test_full_coverage_required(task):
    r = evaluate_rule(
        {"expression": "1/x"},
        [{"x": 0, "z": 1, "group": "a"}, {"x": 2, "z": 1, "group": "a"}],
        [1, 1],
        task,
    )
    assert r["accuracy"]["primary_error"] is None
    assert r["coverage"]["fraction"] == 0.5


def test_diagnostic_stability_not_ranking():
    def row(id, err, ops, s):
        return {
            "rule_id": id,
            "status": "complete",
            "accuracy": {"primary_error": err},
            "simplicity": {"weighted_operator_count": ops, "free_parameters": 2},
            "stability": {"mean_relative_sensitivity": s, "ranking": False},
            "coverage": {"fraction": 1},
            "accuracy_gate": True,
        }

    a = row("a", 1, 2, 100)
    b = row("b", 2, 3, 0)
    assert [r["rule_id"] for r in pareto_front([a, b])] == ["a"]
    b["coverage"]["fraction"] = 0.99
    assert not pareto_front([b])


@pytest.mark.parametrize(
    "method",
    ["mean_control", "linear_control", "polynomial_control", "tree_control", "symbolic_control"],
)
def test_real_controls(task, method):
    r = execute_method(method, task, rows(0, 100), rows(100, 30))
    assert r["status"] == "complete" and r["rules"]
    if method == "linear_control":
        assert r["rules"][0]["dev_error"] < 1e-9
    if method == "symbolic_control":
        assert r["accounting"]["fitting_attempts"] > 20
    if method == "tree_control":
        assert r["rules"][0]["representation"] == "tree"


def test_unimplemented_methods_cannot_rank(task):
    r = execute_method("ai_scientist_v2", task, rows(0, 100), rows(100, 30))
    assert r["status"] == "unsupported" and not r["rules"]


class FakeGateway:
    def __init__(self):
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "text": json.dumps(
                {"expression": "p0+p1*x+p2*z", "parameters": {"p0": 0, "p1": 1, "p2": 1}}
            ),
            "request_id": kwargs["request_id"],
        }


@pytest.mark.parametrize("method,n", [("direct", 1), ("best_of_n", 3), ("feedback_refinement", 3)])
def test_actual_distinct_llm_lifecycles(task, method, n):
    g = FakeGateway()
    r = execute_method(method, task, rows(0, 100), rows(100, 30), gateway=g)
    assert len(g.calls) == n and r["status"] == "complete"
    if method == "feedback_refinement":
        assert json.loads(g.calls[1]["prompt"])["development_feedback"]["candidates"] > 0
    if method == "best_of_n":
        assert all(json.loads(c["prompt"])["development_feedback"] is None for c in g.calls)


def test_best_of_n_retains_good_proposals_when_one_is_malformed(task):
    class Mixed(FakeGateway):
        def complete(self, **kwargs):
            value = super().complete(**kwargs)
            if len(self.calls) == 2:
                value["text"] = '{"parameters": []}'
            return value

    gateway = Mixed()
    result = execute_method("best_of_n", task, rows(0, 100), rows(100, 30), gateway=gateway)
    assert result["status"] == "complete" and len(gateway.calls) == 3
    assert any("missing expression" in f["reason"] for f in result["failed_candidates"])


def test_tool_inspection_returns_data_to_the_next_request(task):
    class Tools(FakeGateway):
        def complete(self, **kwargs):
            response = super().complete(**kwargs)
            if len(self.calls) == 1:
                response["text"] = '{"action":"inspect"}'
            elif len(self.calls) == 2:
                content = json.loads(kwargs["prompt"])["development_feedback"]["last_tool_result"]
                assert content["action"] == "inspect" and len(content["rows"]) == 24
                value = json.loads(response["text"])
                value["action"] = "fit"
                response["text"] = json.dumps(value)
            else:
                response["text"] = '{"action":"finish"}'
            return response

    gateway = Tools()
    result = execute_method("tool_agent", task, rows(0, 100), rows(100, 30), gateway=gateway)
    assert result["status"] == "complete" and len(gateway.calls) == 3


def test_concurrent_ledger(tmp_path):
    ledger = CostLedger(tmp_path / "ledger.db", cap_cny=3)

    def attempt(i):
        try:
            ledger.reserve(str(i), 1)
            return True
        except BudgetExceeded:
            return False

    with ThreadPoolExecutor(max_workers=8) as e:
        r = list(e.map(attempt, range(16)))
    assert sum(r) == 3 and ledger.summary()["accounted_cny"] == 3
    with pytest.raises(DuplicateRequest):
        ledger.reserve(next(str(i) for i, success in enumerate(r) if success), 1)
    with pytest.raises(ValueError):
        ledger.reserve("negative", -2)


def test_attempt_budget_survives_new_gateway_process(tmp_path):
    path = tmp_path / "ledger.db"
    first = CostLedger(path)
    first.reserve("first", 2, attempt_id="run", attempt_cap_cny=3)
    first.record({"request_id": "first", "state": "unknown"})
    second = CostLedger(path)
    with pytest.raises(BudgetExceeded):
        second.reserve("second", 2, attempt_id="run", attempt_cap_cny=3)
    second.reserve("other-run", 2, attempt_id="different", attempt_cap_cny=3)


def test_runtime_snapshot_is_reusable_and_detects_mutation(tmp_path):
    from principia_asd.store.snapshot import runtime_snapshot

    first = runtime_snapshot(tmp_path)
    assert runtime_snapshot(tmp_path) == first
    (first / "principia_asd/engine/search.py").write_text("mutation")
    with pytest.raises(ValueError, match="mutation"):
        runtime_snapshot(tmp_path)


def test_immutable_json_does_not_overwrite(tmp_path):
    path = tmp_path / "record.json"
    write_json(path, {"x": 1}, immutable=True)
    with pytest.raises(FileExistsError):
        write_json(path, {"x": 2}, immutable=True)
    assert read_json(path) == {"x": 1}


def test_record_store_rejects_path_escape(tmp_path):
    from principia_asd.store import JsonStore

    with pytest.raises(ValueError, match="allowed directory"):
        JsonStore(tmp_path / "records").write("../canary.json", {"x": 1})
    assert not (tmp_path / "canary.json").exists()


def test_freeze_then_identity_join_and_mutation(task, tmp_path):
    scenario = tmp_path / "scenario"
    vault = tmp_path / "vault"
    folder = tmp_path / "workspace/runs/run-test"
    folder.mkdir(parents=True)
    train = rows(0, 100)
    dev = rows(100, 30)
    test = rows(200, 20)
    for name, data in [("train", train), ("dev", dev)]:
        write_csv(
            scenario / f"public/{name}.csv.gz", data, ["sample_id", "group", "x", "z", "target"]
        )
    write_csv(
        scenario / "public/test_inputs.csv.gz",
        [{k: v for k, v in r.items() if k != "target"} for r in test],
        ["sample_id", "group", "x", "z"],
    )
    write_json(scenario / "task-contracts/task-001.json", task)
    write_json(
        folder / "request.json",
        {
            "scenario_id": "TEST",
            "scenario_path": str(scenario),
            "method_id": "linear_control",
            "limits": {},
        },
    )
    settings = {"workspace": str(tmp_path / "workspace")}
    # Discovery succeeds with no evaluator files existing.
    sub = discover_run(folder, settings)
    assert sub["status"] == "complete" and not vault.exists()
    write_csv(
        vault / "TEST/test_targets.csv.gz",
        [{k: r[k] for k in ["sample_id", "group", "target"]} for r in reversed(test)],
        ["sample_id", "group", "target"],
    )
    write_json(
        vault / "TEST/evaluator-manifest.json",
        {
            "target_sha256": file_sha(vault / "TEST/test_targets.csv.gz"),
            "input_sha256": file_sha(scenario / "public/test_inputs.csv.gz"),
            "contract_sha256": file_sha(scenario / "task-contracts/task-001.json"),
        },
    )
    ev = evaluate_run(folder, vault)
    assert ev["receipts"][0]["accuracy"]["primary_error"] < 1e-9
    assert evaluate_run(folder, vault, replay=True)["replay_verified"]
    data = read_json(folder / "submission.json")
    data["rules"][0]["expression"] = "0"
    write_json(folder / "submission.json", data)
    with pytest.raises(ValueError, match="mutation"):
        evaluate_run(folder, vault)
