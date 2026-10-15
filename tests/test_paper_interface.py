"""Public selection must use frozen development jobs, never the legacy evaluator."""

import subprocess
import sys
from pathlib import Path

import pytest
from test_bound_jobs import PausedPool
from test_paper_jobs import SCRIPT
from test_paper_jobs import setup as setup

from principia_asd import bound_jobs, cli, paper_v2_jobs
from principia_asd.engine.search import execute_method
from principia_asd.io import read_json, write_json
from principia_asd.methods.registry import DEFAULT_ROLES
from principia_asd.web.server import App


@pytest.fixture
def app(setup, monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "offline-ui-fixture-key")
    settings, scenario = setup
    write_json(scenario / "scenario.json", {"title": "Disclosed synthetic fixture"})
    value = App(settings)
    original_pool = value.pool
    value.pool = PausedPool()
    try:
        yield value
    finally:
        original_pool.shutdown()
        value.server_lock.close()


def request(**changes):
    return {"scenario_id": "SYNTHETIC", "method_id": paper_v2_jobs.METHOD_ID, **changes}


def test_config_and_queued_cancellation_preserve_identity(app):
    config = app.config()
    method = next(m for m in config["methods"] if m["method_id"] == paper_v2_jobs.METHOD_ID)
    assert method["available"] and method["tier"] == "engineering"
    assert "project_root" not in config and "env_file" not in config
    out = app.start(request())
    folder = app.run_path(out["run_id"])
    req = read_json(folder / "request.json")
    assert req["scope"] == paper_v2_jobs.SCOPE and req["roles"] == DEFAULT_ROLES
    assert read_json(folder / "ui.json")["protocol_revision"] == "paper-v2"
    assert req["limits"]["max_calls"] == 6 and req["limits"]["max_fits"] == 2
    view = app.get_run(folder.name)
    assert view["method_id"] == paper_v2_jobs.METHOD_ID and not view["ranking_authorized"]
    with pytest.raises(ValueError, match="already"):
        app.queue_bound(folder)
    assert app.cancel(folder.name)["status"] == "cancelled"
    app.pool.jobs[0][0](*app.pool.jobs[0][1])
    app.pool.jobs[0][2].set_result(None)
    assert app.get_run(folder.name)["status"] == "cancelled"
    assert app.ledger.summary()["requests"] == 0


@pytest.mark.parametrize(
    "case", ["project", "objective", "protocol", "budget", "role", "capability"]
)
def test_preflight_errors_never_queue_or_charge(app, case):
    payload = request()
    if case == "project":
        app.settings.pop("project_root")
        assert not next(
            m for m in app.config()["methods"] if m["method_id"] == paper_v2_jobs.METHOD_ID
        )["available"]
    elif case == "objective":
        payload["objective"] = "Quietly change the task"
    elif case == "protocol":
        payload["protocol_revision"] = "v2"
    elif case == "budget":
        payload["budget_cny"] = 13
    elif case == "role":
        payload["model_roles"] = DEFAULT_ROLES | {"critic": "unavailable"}
    else:
        caps = app.capabilities()
        caps[DEFAULT_ROLES["critic"]]["state"] = "unverified"
        write_json(app.workspace / "capabilities.json", caps)
    with pytest.raises(ValueError):
        app.start(payload)
    assert app.pool.jobs == [] and app.ledger.summary()["requests"] == 0
    assert not list(app.bound_runs.iterdir())


def test_real_queued_worker_path_with_mocked_transport(app, monkeypatch):
    def launch(folder):
        result = subprocess.run(
            [sys.executable, "-I", "-B", str(SCRIPT), "--child", str(folder), "--case", "complete"],
            capture_output=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr.decode()

    monkeypatch.setattr(bound_jobs, "launch", launch)
    out = app.start(request())
    fn, args, future = app.pool.jobs[0]
    fn(*args)
    future.set_result(None)
    view = app.get_run(out["run_id"])
    assert view["status"] == "complete" and not view["resume_available"]
    assert len(view["bound_result"]["handoffs"]) == 4
    assert len(view["bound_result"]["experiments"]) == 1
    assert len(view["bound_result"]["selection"]["nominations"]) == 3
    assert view["accounting"]["fitting_attempts"] == 1 and view["accounting"]["model_calls"] == 4
    assert all(r["method_id"] == paper_v2_jobs.METHOD_ID for r in view["rules"])
    assert "evaluation" not in view and not Path(app.settings["vault"]).exists()
    assert not Path(app.settings["leaderboard_root"]).exists()


def invoke(monkeypatch, settings, root, args):
    path = root / "settings.json"
    write_json(path, settings)
    monkeypatch.setattr(sys, "argv", ["principia-asd", *args, "--settings", str(path)])
    cli.main()


def test_cli_run_and_resume_use_dedicated_worker(setup, monkeypatch, tmp_path):
    settings, scenario = setup
    launched = []
    monkeypatch.setattr(bound_jobs, "launch", launched.append)
    invoke(
        monkeypatch,
        settings,
        tmp_path,
        ["run", "--method", paper_v2_jobs.METHOD_ID, "--scenario", str(scenario)],
    )
    assert len(launched) == 1
    folder = launched[0]
    assert read_json(folder / "request.json")["scope"] == paper_v2_jobs.SCOPE
    for command in ["resume", "worker"]:
        invoke(monkeypatch, settings, tmp_path, [command, str(folder)])
    assert launched == [folder] * 3


@pytest.mark.parametrize("command", ["evaluate", "replay", "resume", "worker"])
@pytest.mark.parametrize(
    "scope", [paper_v2_jobs.SCOPE, "engineering_only_data_to_paper_explicit_unknown"]
)
def test_incomplete_bindings_cannot_fall_through_to_legacy(
    setup, monkeypatch, tmp_path, command, scope
):
    settings, _ = setup
    folder = tmp_path / "unbound"
    write_json(folder / "request.json", {"scope": scope})
    monkeypatch.setattr(bound_jobs, "launch", lambda *a: pytest.fail("Unexpected launch"))
    with pytest.raises(SystemExit) as exc:
        invoke(monkeypatch, settings, tmp_path, [command, str(folder)])
    assert exc.value.code == 2 and not (folder / "evaluation.json").exists()


def test_legacy_executor_refuses_the_explicit_method():
    result = execute_method(paper_v2_jobs.METHOD_ID, {}, [], [])
    assert result["status"] == "unsupported" and not result["rules"]
