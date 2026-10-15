"""Fixed control cohorts keep assignments, failures and private custody intact."""

import fcntl
import os
import shutil
import sys
from pathlib import Path

import pytest
from test_bound_controls import fixture

from principia_asd import control_jobs
from principia_asd import control_pilot as pilot
from principia_asd.engine.bound_checkpoint import DurableBoundRun
from principia_asd.engine.bound_controls import BoundControl
from principia_asd.io import file_sha, read_csv, read_json, write_csv, write_json


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(pilot, "CASES", ("CASE-A", "CASE-WIDE"))
    settings = {
        "workspace": str(tmp_path / "private"),
        "data_root": str(tmp_path / "data"),
        "leaderboard_root": str(tmp_path / "boards"),
        "vault": str(tmp_path / "vault"),
        "env_file": str(tmp_path / "credentials.env"),
    }
    for sid, n in (("CASE-A", 2), ("CASE-WIDE", 9)):
        scenario = tmp_path / "data/scenarios" / sid
        task, train, dev = fixture(n)
        task.update(
            scenario_id=sid,
            task_id="task-001",
            split={
                "train": "public/train.csv",
                "dev": "public/dev.csv",
                "test": "do-not-read.csv",
            },
        )
        write_json(scenario / "task-contracts/task-001.json", task)
        for name, rows in (("train", train), ("dev", dev)):
            write_csv(scenario / task["split"][name], rows, list(rows[0]))
    return settings, tmp_path / "project"


@pytest.fixture(autouse=True)
def supported_runtime(monkeypatch, request):
    if sys.platform != "darwin" or not shutil.which("sandbox-exec"):
        if "actual" in request.node.name:
            pytest.skip("macOS sandbox required")
        monkeypatch.setattr(
            control_jobs,
            "environment",
            lambda: {
                "python": sys.executable,
                "base_prefix": sys.base_prefix,
                "site_paths": [],
                "sandbox": "unavailable-fixture",
            },
        )


def prepared(setup):
    return pilot.prepare(setup[0], "fixture-controls", project_root=setup[1])


def mock_numerics(monkeypatch, launched):
    def run(folder):
        launched.append(folder.name)
        _, request = control_jobs.verify_binding(folder)
        inputs = read_json(folder / "inputs.json")
        engine = BoundControl(
            read_json(folder / inputs["contract"]["path"]),
            read_csv(folder / inputs["train"]["path"]),
            read_csv(folder / inputs["dev"]["path"]),
            control=request["control"],
            run_id=folder.name,
            limits=request["limits"],
        )
        result = DurableBoundRun(
            engine,
            folder,
            provider_binding={
                "provider": "none",
                "api_calls": 0,
                "launch_sha256": read_json(folder / "launch.json")["sha256"],
            },
        ).run()
        return {"status": result["status"]}

    monkeypatch.setattr(control_jobs, "launch", run)


def test_all_combinations_frozen_without_test_provider_or_upload_writes(setup):
    root, m = prepared(setup)
    assert m["assigned"] == 8 and m["fixed_nomination_slots"] == 24
    assert len({j["assignment_id"] for j in m["jobs"]}) == 8
    assert m["workers"] == 4 and m["api_calls"] == 0
    assert pilot.check(root) == m
    assert not (root / "settings.json").exists()
    for key in ("vault", "leaderboard_root", "env_file"):
        assert not Path(setup[0][key]).exists()
    assert not (Path(m["workspace"]) / "costs.sqlite").exists()
    with pytest.raises(FileExistsError):
        prepared(setup)
    assert pilot.summary(root)["terminal_records"] == 0


@pytest.mark.parametrize("name", ["../escape", "", ".", "x/y"])
def test_invalid_id_never_prepares_jobs(setup, name):
    with pytest.raises(ValueError, match="identity"):
        pilot.prepare(setup[0], name, project_root=setup[1])
    assert not (Path(setup[0]["workspace"]) / "control-runs").exists()


def test_upload_custody_checked_before_any_creation(setup):
    settings = setup[0] | {"workspace": str(setup[1] / "mutable")}
    with pytest.raises(ValueError, match="separate"):
        pilot.prepare(settings, "fixture", project_root=setup[1])
    assert not setup[1].exists()


@pytest.mark.parametrize("mutation", ["manifest", "launch", "input", "runtime"])
def test_mutation_blocks_before_worker_dispatch(setup, monkeypatch, mutation):
    root, m = prepared(setup)
    run = Path(m["workspace"]) / "control-runs" / m["jobs"][0]["run_id"]
    path = {
        "manifest": root / "manifest.json",
        "launch": run / "launch.json",
        "input": run / "inputs/train.csv",
        "runtime": Path(m["runtime_source"]) / "principia_asd/control_pilot.py",
    }[mutation]
    if mutation == "manifest":
        obj = read_json(path)
        obj["assigned"] -= 1
        write_json(path, obj)
    else:
        path.write_bytes(path.read_bytes() + b" ")
    monkeypatch.setattr(control_jobs, "launch", lambda *a: pytest.fail("dispatched changed work"))
    with pytest.raises(ValueError, match="changed"):
        pilot.drive(root)


def test_all_outcomes_frozen_resume_never_repeats_numerics(setup, monkeypatch):
    root, m = prepared(setup)
    launched = []
    mock_numerics(monkeypatch, launched)
    result = pilot.drive(root)
    assert result["statuses"] == {"complete": 4, "unsupported": 4}
    assert result["nominated_slots"] == 6 and result["fixed_nomination_slots"] == 24
    assert len(launched) == 8
    assert pilot.drive(root) == result and pilot.verify_completion(root) == result
    assert pilot.launch(root)["status"] == "already_finished" and len(launched) == 8
    s = pilot.summary(root)
    assert s["fitting_attempts"] == 13 and s["terminal_records"] == 8
    assert not s["driver_alive"] and not s["ranking_authorized"]
    run = Path(m["workspace"]) / "control-runs" / m["jobs"][0]["run_id"]
    path = run / "result.json"
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError, match="changed"):
        pilot.verify_completion(root)


@pytest.mark.parametrize("status", ["cancelled", "recovery_required", "interrupted"])
def test_unresolved_retained_with_all_slots_and_no_retry(setup, monkeypatch, status):
    root, m = prepared(setup)
    launched = []

    def run(folder):
        launched.append(folder.name)
        return {"status": status, "reason": "fixture interruption"}

    monkeypatch.setattr(control_jobs, "launch", run)
    receipt = pilot.drive(root)
    expected = "execution_unresolved" if status == "interrupted" else status
    assert receipt["statuses"] == {expected: 8} and receipt["nominated_slots"] == 0
    assert receipt["fixed_nomination_slots"] == 24
    assert pilot.drive(root) == receipt and len(launched) == 8


def test_partial_cohort_resume_reuses_sealed_attempts(setup, monkeypatch):
    root, m = prepared(setup)
    launched = []
    mock_numerics(monkeypatch, launched)
    pilot.run_one(root, m, m["jobs"][0])
    sealed = file_sha(root / "outcomes" / (m["jobs"][0]["assignment_id"] + ".json"))
    pilot.drive(root)
    assert len(launched) == len(set(launched)) == 8
    assert file_sha(root / "outcomes" / (m["jobs"][0]["assignment_id"] + ".json")) == sealed


def test_driver_lock_and_live_pid_prevent_duplicates(setup, monkeypatch):
    root, _ = prepared(setup)
    with (root / "driver.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            pilot.drive(root)
    write_json(root / "driver.pid", {"pid": os.getpid()})
    monkeypatch.setattr(pilot.subprocess, "Popen", lambda *a, **k: pytest.fail("duplicate"))
    assert pilot.launch(root)["status"] == "already_running"


def test_launcher_uses_copied_driver_and_allowlisted_environment(setup, monkeypatch):
    root, m = prepared(setup)
    captured = []

    class Process:
        pid = 765432

        def __init__(self, args, **kw):
            captured.append((args, kw))

    monkeypatch.setenv("CANARY_API_KEY", "synthetic-never-forward")
    monkeypatch.setattr(pilot.subprocess, "Popen", Process)
    assert pilot.launch(root)["status"] == "started"
    args, kw = captured[0]
    assert args[0] == m["driver_python"] and "-I" in args
    assert args[-2:] == [m["runtime_source"], str(root)]
    assert "CANARY_API_KEY" not in kw["env"] and "PYTHONPATH" not in kw["env"]


def test_actual_sandboxed_cohort_and_terminal_read_only_resume(setup):
    root, m = prepared(setup)
    receipt = pilot.drive(root)
    assert receipt["statuses"] == {"complete": 4, "unsupported": 4}
    assert receipt["nominated_slots"] == 6 and receipt["fixed_nomination_slots"] == 24
    before = {
        j["run_id"]: file_sha(Path(m["workspace"]) / "control-runs" / j["run_id"] / "result.json")
        for j in m["jobs"]
    }
    assert pilot.drive(root) == receipt
    assert before == {
        j["run_id"]: file_sha(Path(m["workspace"]) / "control-runs" / j["run_id"] / "result.json")
        for j in m["jobs"]
    }
    assert not (Path(m["workspace"]) / "costs.sqlite").exists()


@pytest.mark.parametrize("target", ["checkpoint", "completion", "extra_outcome"])
def test_completed_cohort_mutation_is_rejected_without_dispatch(setup, monkeypatch, target):
    root, m = prepared(setup)
    mock_numerics(monkeypatch, [])
    pilot.drive(root)
    monkeypatch.setattr(control_jobs, "launch", lambda *a: pytest.fail("repeated work"))
    if target == "checkpoint":
        run = Path(m["workspace"]) / "control-runs" / m["jobs"][0]["run_id"]
        path = sorted((run / "checkpoints").glob("*.json"))[0]
        value = read_json(path)
        value["name"] = "changed"
        write_json(path, value)
    elif target == "completion":
        path = root / "completion.json"
        value = read_json(path)
        value["assigned"] -= 1
        write_json(path, value)
    else:
        write_json(root / "outcomes/extra.json", {})
    with pytest.raises(ValueError, match="changed"):
        pilot.verify_completion(root)
