"""User-facing development jobs; no network or real provider credentials."""

from concurrent.futures import Future
from pathlib import Path

import pytest
from test_bound_engine import FixtureGateway, fixture

from principia_asd import bound_jobs
from principia_asd.engine.bound_engine import BoundEngine
from principia_asd.engine.bound_worker import validate_worker_request
from principia_asd.engine.search import execute_method
from principia_asd.io import file_sha, read_json, sha, write_json
from principia_asd.methods.registry import DEFAULT_ROLES
from principia_asd.store.ledger import CostLedger
from principia_asd.web.server import App


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "offline-ui-fixture-key")
    settings = {
        "workspace": str(tmp_path / "private"),
        "data_root": str(tmp_path / "data"),
        "leaderboard_root": str(tmp_path / "boards"),
        "vault": str(tmp_path / "vault"),
    }
    task, _, _ = fixture()
    task["scenario_id"] = "SYNTHETIC"
    scenario = tmp_path / "data/scenarios/SYNTHETIC"
    write_json(scenario / "scenario.json", {"title": "Disclosed synthetic fixture"})
    write_json(scenario / "task-contracts/task-001.json", task)
    return settings, scenario


def prepared(setup):
    settings, scenario = setup
    folder = bound_jobs.prepare(settings, scenario, "SYNTHETIC")
    ledger = CostLedger(Path(settings["workspace"]) / "costs.sqlite")
    return folder, ledger


def test_new_job_has_separate_identity_frozen_runtime_and_no_test_read(setup):
    folder, ledger = prepared(setup)
    req = read_json(folder / "request.json")
    assert folder.parent.name == "bound-runs"
    assert req["limits"]["max_calls"] == 7
    assert req["roles"] == DEFAULT_ROLES
    assert read_json(folder / "ui.json")["mode"] == "engineering"
    cfg = read_json(folder / "launch.json")
    assert file_sha(folder / "request.json") == cfg["request_sha256"]
    assert Path(cfg["runtime_source"]).is_relative_to(Path(setup[0]["workspace"]))
    assert ledger.summary()["requests"] == 0
    assert not Path(setup[0]["vault"]).exists()
    view = bound_jobs.view(folder, ledger, scheduled=True)
    assert view["status"] == "queued"
    assert not view["ranking_authorized"] and view["assessment_status"] == "not_assessed"
    assert "settings" not in view and "env_file" not in view
    assert bound_jobs.view(folder, ledger)["resume_available"]


@pytest.mark.parametrize("budget", [0, -1, 13, float("nan"), float("inf")])
def test_invalid_cap_creates_no_job(setup, budget):
    settings, scenario = setup
    with pytest.raises(ValueError, match="budget"):
        bound_jobs.prepare(settings, scenario, "SYNTHETIC", budget=budget)
    assert not (Path(settings["workspace"]) / "bound-runs").exists()


def test_no_hidden_column_subsetting_and_upload_root_custody(setup):
    settings, scenario = setup
    path = scenario / "task-contracts/task-001.json"
    task = read_json(path)
    task["inputs"] = list("abcdefghi")
    write_json(path, task)
    with pytest.raises(ValueError, match="1–8"):
        bound_jobs.prepare(settings, scenario, "SYNTHETIC")
    task["inputs"] = ["x"]
    write_json(path, task)
    unsafe = settings | {"workspace": str(Path(settings["data_root"]) / "mutable")}
    with pytest.raises(ValueError, match="outside upload"):
        bound_jobs.prepare(unsafe, scenario, "SYNTHETIC")
    outside = settings | {"data_root": str(Path(settings["data_root"]) / "other")}
    with pytest.raises(ValueError, match="outside the configured"):
        bound_jobs.prepare(outside, scenario, "SYNTHETIC")


def test_imports_are_allowed_but_symlink_to_vault_is_not(setup):
    folder, _ = prepared(setup)
    settings, _ = setup
    root = Path(settings["workspace"]) / "imports"
    root.mkdir()
    request = read_json(folder / "request.json")
    request["scenario_path"] = str(root / "local-data")
    write_json(folder / "request.json", request)
    assert validate_worker_request(folder, settings)[2] == root / "local-data"
    vault = Path(settings["vault"])
    vault.mkdir()
    (root / "local-data").symlink_to(vault, target_is_directory=True)
    with pytest.raises(ValueError, match="outside"):
        validate_worker_request(folder, settings)


@pytest.mark.parametrize("failure", [None, 1, 7])
def test_complete_or_failed_records_keep_three_slots_state_and_failures(setup, failure):
    folder, ledger = prepared(setup)
    result = BoundEngine(
        *fixture(), gateway=FixtureGateway(fail_at=failure), run_id=folder.name
    ).run()
    write_json(folder / "result.json", {"result": result})
    write_json(folder / "state.json", {"status": result["status"]})
    v = bound_jobs.view(folder, ledger)
    assert v["status"] == ("complete" if failure is None else "failed")
    assert len(v["bound_result"]["selection"]["nominations"]) == 3
    assert not v["resume_available"] and "evaluation" not in v
    for rule in v["rules"]:
        assert rule["parameters"] == rule["program"]["specification"]["parameters"]
        s = rule["simplicity"]
        assert s["learned_scalar_count"] == (
            s["final_stage_parameters"]
            + s["inherited_fitted_scalars"]
            + s["train_statistic_scalars"]
        )
    result["model_requests"] += 1
    write_json(folder / "result.json", {"result": result})
    with pytest.raises(ValueError, match="changed"):
        bound_jobs.view(folder, ledger)


def test_local_interruption_and_unknown_call_are_not_offered_for_replay(setup):
    folder, ledger = prepared(setup)
    p = folder / "checkpoints/0000.json"
    event = {"type": "intent", "kind": "local", "name": "initialize"}
    write_json(p, event)
    ok, reason = bound_jobs.recovery(folder, ledger)
    assert not ok and "numerical work is unknown" in reason
    event.update(kind="provider", name="plan-0", state={"engine": {"requests": 0}})
    write_json(p, event)
    rid = folder.name + "--bound-v1--planner--1"
    ledger.reserve(rid, 2)
    ledger.record({"request_id": rid, "state": "unknown"})
    write_json(folder / "provider" / (sha(rid) + ".json"), {"not": "verified"})
    assert not bound_jobs.recovery(folder, ledger)[0]
    assert ledger.summary()["unknown_usage_reserved"] == 2


def test_settled_recovery_is_only_a_hint_and_cancel_is_terminal(setup):
    folder, ledger = prepared(setup)
    rid = folder.name + "--bound-v1--critic--3"
    ledger.reserve(rid, 2)
    ledger.record({"request_id": rid, "state": "completed", "actual_cny": 0.01})
    write_json(folder / "provider" / (sha(rid) + ".json"), {"fixture": "hash checked by worker"})
    write_json(
        folder / "checkpoints/0000.json",
        {
            "type": "intent",
            "kind": "provider",
            "name": "critic-0",
            "state": {"engine": {"requests": 2}},
        },
    )
    assert bound_jobs.recovery(folder, ledger)[0]
    (folder / "cancel.requested").touch()
    assert not bound_jobs.recovery(folder, ledger)[0]


def test_launcher_uses_frozen_source_strips_secrets_and_preserves_fast_terminal(setup, monkeypatch):
    folder, _ = prepared(setup)
    captured = {}
    monkeypatch.setenv("SILICONFLOW_API_KEY", "canary-never-child-env")

    class Child:
        pid = 123456789

        def __init__(self, args, **kw):
            captured.update(args=args, **kw)
            assert read_json(folder / "state.json")["status"] == "running"
            write_json(folder / "state.json", {"status": "complete"})

        def wait(self, **kw):
            return 0

    monkeypatch.setattr(bound_jobs.subprocess, "Popen", Child)
    bound_jobs.launch(folder)
    launch = read_json(folder / "launch.json")
    assert captured["env"]["PYTHONPATH"] == launch["runtime_source"]
    assert captured["args"][0] == launch["interpreter"]
    assert "SILICONFLOW_API_KEY" not in captured["env"]
    assert read_json(folder / "state.json")["status"] == "complete"


@pytest.mark.parametrize("mutation", ["request", "settings", "runtime"])
def test_changed_frozen_launch_refused_before_subprocess(setup, monkeypatch, mutation):
    folder, _ = prepared(setup)
    cfg = read_json(folder / "launch.json")
    path = folder / (mutation + ".json")
    if mutation == "runtime":
        path = Path(cfg["runtime_source"]) / "principia_asd/bound_jobs.py"
    path.write_text(path.read_text() + " ")
    monkeypatch.setattr(bound_jobs.subprocess, "Popen", lambda *a, **k: pytest.fail("dispatched"))
    with pytest.raises(ValueError, match="changed"):
        bound_jobs.launch(folder)


class PausedPool:
    def __init__(self):
        self.jobs = []

    def submit(self, fn, *args):
        future = Future()
        self.jobs.append((fn, args, future))
        return future


@pytest.mark.parametrize("protocol", [None, "v1", "v2"])
def test_ui_start_duplicate_resume_and_queued_cancel(setup, protocol):
    settings, _ = setup
    app = App(settings)
    original_pool = app.pool
    app.pool = PausedPool()
    app.capabilities = lambda: {m: {"state": "verified"} for m in DEFAULT_ROLES.values()}
    try:
        request = {"scenario_id": "SYNTHETIC", "method_id": bound_jobs.METHOD_ID}
        if protocol is not None:
            request["protocol_revision"] = protocol
        out = app.start(request)
        rid = out["run_id"]
        assert app.get_run(rid)["protocol_revision"] == (protocol or "v1")
        saved = read_json(app.run_path(rid) / "request.json")
        assert saved["scope"] == "engineering_only_explicit_state_" + (protocol or "v1")
        assert app.get_run(rid)["status"] == "queued"
        assert len(app.pool.jobs) == 1
        with pytest.raises(ValueError, match="cannot be resumed"):
            app.resume_bound(rid)
        with pytest.raises(ValueError, match="already"):
            app.queue_bound(app.run_path(rid))
        assert app.cancel(rid)["status"] == "cancelled"
        app.pool.jobs[0][0](*app.pool.jobs[0][1])  # cancelled launch is a no-op
        app.pool.jobs[0][2].set_result(None)
        assert app.list_runs()[0]["status"] == "cancelled"
        assert not app.get_run(rid)["resume_available"]
        assert app.ledger.summary()["requests"] == 0
        assert not Path(settings["leaderboard_root"]).exists()
    finally:
        original_pool.shutdown()
        app.server_lock.close()


@pytest.mark.parametrize("protocol", ["v3", "", None, [], {}])
def test_ui_rejects_unknown_protocol_without_job_or_dispatch(setup, protocol):
    app = App(setup[0])
    app.capabilities = lambda: {m: {"state": "verified"} for m in DEFAULT_ROLES.values()}
    try:
        assert [p["id"] for p in app.config()["explicit_state_protocols"]] == ["v2", "v1"]
        with pytest.raises(ValueError, match="Unknown explicit-state protocol"):
            app.start(
                {
                    "scenario_id": "SYNTHETIC",
                    "method_id": bound_jobs.METHOD_ID,
                    "protocol_revision": protocol,
                }
            )
        assert list(app.bound_runs.iterdir()) == []
        assert app.ledger.summary()["requests"] == 0
    finally:
        app.pool.shutdown()
        app.server_lock.close()


def test_non_engine_cannot_silently_ignore_protocol_selection(setup):
    app = App(setup[0])
    try:
        with pytest.raises(ValueError, match="only available"):
            app.start(
                {"scenario_id": "SYNTHETIC", "method_id": "mean_control", "protocol_revision": "v2"}
            )
        assert list(app.runs.iterdir()) == []
    finally:
        app.pool.shutdown()
        app.server_lock.close()


def test_legacy_search_cannot_misroute_explicit_state_to_old_engine():
    task, train, dev = fixture()
    out = execute_method(bound_jobs.METHOD_ID, task, train, dev)
    assert out["status"] == "unsupported" and not out["rules"]
    assert "dedicated" in out["reason"]


def test_worker_cancelled_before_journal_keeps_terminal_state(setup, monkeypatch):
    folder, ledger = prepared(setup)

    class Child:
        pid = 123456789

        def __init__(self, *a, **kw):
            (folder / "cancel.requested").touch()

        def wait(self, **kw):
            return 1

    monkeypatch.setattr(bound_jobs.subprocess, "Popen", Child)
    bound_jobs.launch(folder)
    assert bound_jobs.view(folder, ledger, False)["status"] == "cancelled"
    assert not bound_jobs.recovery(folder, ledger)[0]
    assert not (folder / "result.json").exists()
