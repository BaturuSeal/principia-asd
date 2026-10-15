"""Public/private execution boundaries. Provider transport is always mocked."""

import json
import stat
from pathlib import Path

import pytest
from test_bound_jobs import PausedPool
from test_product_workspace import example as example

from principia_asd.io import file_sha, read_json, write_csv, write_json
from principia_asd.methods.registry import DEFAULT_ROLES
from principia_asd.web import credentials
from principia_asd.web.public_site import build_site, safe_public
from principia_asd.web.server import App


@pytest.fixture
def app(example, monkeypatch):
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)
    value = App(example[3])
    pool = value.pool
    value.pool = PausedPool()
    try:
        yield value
    finally:
        pool.shutdown()
        value.server_lock.close()


def test_missing_key_blocks_llm_but_numerical_control_still_queues(app):
    assert not app.config()["api_configured"]
    with pytest.raises(ValueError, match="API key"):
        app.start({"scenario_id": "P100-054", "method_id": "principia_engine"})
    assert not list(app.runs.iterdir()) and app.ledger.summary()["requests"] == 0
    result = app.start({"scenario_id": "P100-054", "method_id": "mean_control"})
    assert result["status"] == "queued"


def test_credentials_are_private_not_echoed_and_survive_restart(app, example):
    key = "offline-test-key-do-not-echo-123"
    write_json(app.workspace / "capabilities.json", {"stale": {"state": "verified"}})
    credentials.save(app, {"api_key": key})
    path = app.workspace / ".credentials/siliconflow.env"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(app.workspace.stat().st_mode) == 0o700
    assert key not in json.dumps(app.config())
    assert key not in (app.workspace / "settings.json").read_text()
    assert app.capabilities() == {} and app.ledger.summary()["requests"] == 0
    app.server_lock.close()
    reopened = App(example[3])
    try:
        assert reopened.config()["api_configured"]
        credentials.save(reopened, {"action": "remove"})
        assert not reopened.config()["api_configured"] and not path.exists()
    finally:
        reopened.pool.shutdown()
        reopened.server_lock.close()


@pytest.mark.parametrize(
    "key", ["short", "abc\nSILICONFLOW_API_KEY=malicious", 'abc"quoted-12345', None, ["bad"]]
)
def test_reject_unsafe_credential_values_without_persisting(app, key):
    with pytest.raises(ValueError):
        credentials.save(app, {"api_key": key})
    assert not (app.workspace / ".credentials").exists()


def test_external_credentials_are_not_deleted_or_silently_reenabled(app, tmp_path):
    source = tmp_path / "external.env"
    source.write_text("SILICONFLOW_API_KEY=offline-external-test-key\n")
    app.settings["env_file"] = str(source)
    before = file_sha(source)
    assert credentials.status(app)["configured"]
    credentials.save(app, {"action": "remove"})
    assert file_sha(source) == before
    assert not app.config()["api_configured"]


def test_key_change_and_probe_blocked_while_job_is_queued(app):
    app.start({"scenario_id": "P100-054", "method_id": "mean_control"})
    with pytest.raises(ValueError, match="active|outstanding"):
        credentials.save(app, {"api_key": "offline-test-key-12345"})
    with pytest.raises(ValueError, match="active|outstanding"):
        credentials.start_probe(
            app, {"models": [next(iter(DEFAULT_ROLES.values()))], "confirm_cost": True}
        )


def test_explicit_probe_receipts_and_unknown_usage_are_retained(app, monkeypatch):
    key = "offline-test-key-for-probe"
    credentials.save(app, {"api_key": key})
    selected = list(DEFAULT_ROLES.values())[:2]
    seen = []

    def complete(self, **request):
        seen.append(request["request_id"])
        self.ledger.reserve(request["request_id"], 2)
        if request["model"] == selected[1]:
            self.ledger.record({"request_id": request["request_id"], "state": "unknown"})
            raise RuntimeError("Server echoed secret: " + key)
        self.ledger.record(
            {"request_id": request["request_id"], "state": "completed", "actual_cny": 0.01}
        )
        return {"text": '{"ok":true}', "usage": {"prompt_tokens": 3, "completion_tokens": 5}}

    monkeypatch.setattr(credentials.SiliconFlowClient, "complete", complete)
    with pytest.raises(ValueError, match="Confirm"):
        credentials.start_probe(app, {"models": selected})
    value = credentials.start_probe(app, {"models": selected, "confirm_cost": True})
    assert value["reservation_cny"] == 4 and len(app.pool.jobs) == 1
    with pytest.raises(ValueError, match="active"):
        credentials.save(app, {"action": "remove"})
    job, args, future = app.pool.jobs[0]
    job(*args)
    future.set_result(None)
    assert len(seen) == len(set(seen)) == 2
    assert app.capabilities()[selected[0]]["state"] == "verified"
    assert app.capabilities()[selected[1]]["state"] == "unavailable"
    assert key not in json.dumps(credentials.probe_status(app))
    assert app.ledger.summary()["accounted_cny"] == 2.01
    assert app.ledger.summary()["states"]["unknown"] == 1
    assert not app.probe_pending


def test_interrupted_probe_never_resumes_automatically(app):
    write_json(app.workspace / "provider-probe.json", {"state": "running", "probe_id": "old"})
    assert credentials.probe_status(app)["state"] == "interrupted"
    assert not app.pool.jobs and app.ledger.summary()["requests"] == 0


def test_two_user_workspaces_isolate_imports_keys_runs_and_targets(app, example, tmp_path):
    shared_data = {
        str(p): file_sha(p) for p in Path(app.settings["data_root"]).rglob("*") if p.is_file()
    }
    source = tmp_path / "measurements"
    write_csv(
        source / "values.csv",
        [{"sample": f"s{i}", "group": f"g{i}", "x": i + 1, "y": 2 * i + 3} for i in range(12)],
        ["sample", "group", "x", "y"],
    )
    before = file_sha(source / "values.csv")
    second = App(example[3] | {"workspace": str(tmp_path / "other-private")})
    try:
        credentials.save(app, {"api_key": "offline-first-user-key"})
        credentials.save(second, {"api_key": "offline-second-user-key"})
        result = app.import_local(
            {
                "folder": str(source),
                "file": "values.csv",
                "inputs": ["x"],
                "output": "y",
                "group": "group",
            }
        )
        sid = result["scenario_id"]
        assert (app.workspace / "private-evaluator" / sid / "test_targets.csv.gz").is_file()
        assert not (Path(app.settings["vault"]) / sid).exists()
        assert sid not in second.scenario_paths()
        with pytest.raises(ValueError, match="registered"):
            second.start({"scenario_id": sid, "method_id": "mean_control"})
        run = app.start({"scenario_id": sid, "method_id": "mean_control"})
        with pytest.raises(FileNotFoundError):
            second.get_run(run["run_id"])
        settings = read_json(app.run_path(run["run_id"]) / "local-settings.json")
        assert settings["vault"] == str(app.workspace / "private-evaluator")
        assert settings["workspace"] != second.settings["workspace"]
        assert file_sha(source / "values.csv") == before
        assert {
            str(p): file_sha(p) for p in Path(app.settings["data_root"]).rglob("*") if p.is_file()
        } == shared_data
        assert second.list_runs() == []
    finally:
        second.pool.shutdown()
        second.server_lock.close()


def public_fixture(example):
    scenario, _, task, settings = example
    data, boards = Path(settings["data_root"]), Path(settings["leaderboard_root"])
    write_json(
        data / "EDITION.json",
        {"active_scenarios": [{"scenario_id": "P100-054"}], "publication_authorized": False},
    )
    write_json(boards / "EDITION.json", {"version": "1.0.0rc2"})
    card = {
        "rule_id": "rule-fixture-1",
        "expression": "p0*width_um",
        "parameters": {"p0": 1.123456789},
        "inputs": task["inputs"],
        "output": "target",
        "method_id": "linear_control",
    }
    write_json(
        boards / "scenarios/P100-054/tasks/task-001/leaderboard.json",
        {
            "scenario_id": "P100-054",
            "task_id": task["task_id"],
            "rules": [
                {
                    "rule_id": card["rule_id"],
                    "card": card,
                    "method_id": "linear_control",
                    "status": "valid",
                    "accuracy": {"primary_error": 0.123456789},
                }
            ],
            "attempts": [
                {
                    "method_id": "direct",
                    "status": "failed",
                    "reason": "Artifact at /Users/private/data.py was unavailable",
                }
            ],
        },
    )
    return data, boards


def test_public_build_reads_only_editions_and_preserves_all_outcomes(example, tmp_path):
    data, boards = public_fixture(example)
    # Unregistered/private directories do not enter the catalog or public payload.
    write_json(data / "scenarios/LOCAL-private/scenario.json", {"secret": "PRIVATE_CANARY"})
    receipt = build_site(data, boards, tmp_path / "site", preview=True)
    assert receipt["scenario_count"] == receipt["rule_count"] == receipt["attempt_count"] == 1
    assert not receipt["private_workspace_accessed"] and receipt["provider_calls"] == 0
    all_json = "".join(p.read_text() for p in (tmp_path / "site/data").rglob("*.json"))
    assert "PRIVATE_CANARY" not in all_json and "/Users/" not in all_json
    assert "test_targets" not in all_json
    index = read_json(tmp_path / "site/data/leaderboards.json")[0]
    board = read_json(tmp_path / "site" / index["data_url"].lstrip("/"))
    assert board["attempts"][0]["status"] == "failed"
    assert board["rules"][0]["accuracy"]["primary_error"] == 0.123456789
    assert board["rule_presentations"]["rule-fixture-1"]["parameters"][0]["value"] == 1.123456789
    assert 'data-deployment="public"' in (tmp_path / "site/index.html").read_text()
    assert not (tmp_path / "site/api").exists()
    with pytest.raises(ValueError, match="immutable"):
        build_site(data, boards, tmp_path / "site", preview=True)


def test_publication_gate_and_private_field_redaction(example, tmp_path):
    data, boards = public_fixture(example)
    with pytest.raises(ValueError, match="redistribution"):
        build_site(data, boards, tmp_path / "not-cleared")
    assert not (tmp_path / "not-cleared").exists()
    assert safe_public({"env_file": "/secret", "nested": {"csrf": "x", "loss": 1.25}}) == {
        "nested": {"loss": 1.25}
    }
    with pytest.raises(ValueError, match="credential"):
        safe_public("sk-" + "A" * 32)


def test_mutable_workspace_cannot_overlap_shared_roots(example):
    _, _, _, settings = example
    for root in ["data_root", "leaderboard_root"]:
        with pytest.raises(ValueError, match="separate"):
            App(settings | {"workspace": str(Path(settings[root]) / "state")})


def test_cancel_orphaned_local_job_allows_key_setup_without_replay(app):
    folder = app.runs / "interrupted-fixture"
    write_json(
        folder / "request.json",
        {"scenario_id": "P100-054", "method_id": "direct", "created_at": "2026-10-15"},
    )
    write_json(folder / "state.json", {"status": "queued"})
    assert app.cancel(folder.name)["status"] == "cancelled"
    credentials.save(app, {"api_key": "offline-new-local-key"})
    assert app.config()["api_configured"] and not app.pool.jobs
    assert app.ledger.summary()["requests"] == 0


def test_public_download_requires_verified_companion_archive(tmp_path):
    import zipfile

    from test_acceptance_bundle import bundle

    from principia_asd.web.public_site import verify_companion

    source = tmp_path / "code"
    source.mkdir()
    (source / "README.md").write_text("Fixture")
    path = tmp_path / "bundle.zip"
    bundle.build({"projects/code": source}, path)
    assert verify_companion(path, preview=True) == path
    with pytest.raises(ValueError, match="publication"):
        verify_companion(path, preview=False)
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr("extra.txt", "UNMANIFESTED")
    with pytest.raises(ValueError, match="Unmanifested"):
        verify_companion(path, preview=True)
