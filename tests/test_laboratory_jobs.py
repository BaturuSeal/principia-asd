import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

from principia_asd import bound_jobs, laboratory_jobs
from principia_asd import bound_pilot as pilot
from principia_asd.io import file_sha, read_json, sha, write_json
from principia_asd.store.ledger import CostLedger

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/verify_laboratory_worker.py"
spec = importlib.util.spec_from_file_location("laboratory_fixture", SCRIPT)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


@pytest.fixture
def setup(tmp_path):
    return helper.fixture(tmp_path)


def test_preparation_freezes_only_development_files_and_exact_profiles(setup):
    settings, scenario = setup
    folder = laboratory_jobs.prepare(settings, scenario)
    config, req, private_settings = laboratory_jobs.verify_binding(folder, check_environment=True)
    assert req["scope"] == laboratory_jobs.SCOPE
    assert req["limits"]["max_fits"] == 2 and req["limits"]["max_calls"] == 6
    assert set(private_settings) == {"workspace"}
    assert set(read_json(folder / "inputs.json")) == {"contract", "train", "dev"}
    assert not (folder / "inputs/MUST_NOT_READ.csv").exists()
    assert config["numerical_threads"] == 1 and config["memory_bytes"] == 4 * 1024**3
    assert len(config["provider"]["profiles"]) == 4
    # A frozen job no longer reads the mutable source or global capability file.
    (scenario / "train.csv").write_text("changed original")
    write_json(Path(settings["workspace"]) / "capabilities.json", {})
    assert laboratory_jobs.verify_binding(folder)[0] == config
    assert not (Path(settings["workspace"]) / "costs.sqlite").exists()


@pytest.mark.parametrize(
    "bad",
    [
        "project",
        "data",
        "vault",
        "outside",
        "extra_column",
        "test_alias",
        "capabilities",
        "roles",
        "budget",
        "limit",
    ],
)
def test_preflight_rejects_unsafe_or_incompatible_jobs_without_dispatch(setup, bad):
    settings, scenario = setup
    kwargs = {}
    if bad in {"project", "data"}:
        settings["workspace"] = str(Path(settings[bad + "_root"]) / "mutable")
    elif bad == "vault":
        settings["vault"] = settings["workspace"]
    elif bad == "outside":
        settings["data_root"] = str(scenario / "different")
    elif bad == "extra_column":
        path = scenario / "train.csv"
        path.write_text(path.read_text().replace("sample_id,", "test_alias,sample_id,", 1))
    elif bad == "test_alias":
        path = scenario / "task-contracts/task-001.json"
        task = read_json(path)
        task["inputs"].append("y")
        write_json(path, task)
    elif bad == "capabilities":
        write_json(Path(settings["workspace"]) / "capabilities.json", {})
    elif bad == "roles":
        kwargs["roles"] = {"coder": "silent-fallback"}
    elif bad == "budget":
        kwargs["budget"] = float("nan")
    else:
        kwargs["limits"] = {"max_fits": 3}
    with pytest.raises((ValueError, KeyError)):
        laboratory_jobs.prepare(settings, scenario, **kwargs)
    assert not list(Path(settings["workspace"]).glob("bound-runs/*"))


@pytest.mark.parametrize(
    "target",
    ["request", "settings", "inputs", "capabilities", "ui", "staged", "runtime", "extra_runtime"],
)
def test_mutation_refused_before_subprocess(setup, monkeypatch, target):
    folder = laboratory_jobs.prepare(*setup)
    cfg = read_json(folder / "launch.json")
    if target == "staged":
        path = folder / read_json(folder / "inputs.json")["train"]["path"]
    elif target in {"runtime", "extra_runtime"}:
        path = (
            Path(cfg["runtime_source"])
            / "principia_asd"
            / ("injected.py" if target == "extra_runtime" else "laboratory_jobs.py")
        )
    else:
        path = folder / (target + ".json")
    path.write_text((path.read_text() if path.exists() else "") + " ")
    monkeypatch.setattr(
        bound_jobs.subprocess, "Popen", lambda *a, **kw: pytest.fail("unsafe dispatch")
    )
    with pytest.raises(ValueError, match="changed"):
        bound_jobs.launch(folder)


def test_launcher_uses_exact_interpreter_source_and_allowlisted_environment(setup, monkeypatch):
    folder = laboratory_jobs.prepare(*setup)
    cfg = read_json(folder / "launch.json")
    captured = {}
    monkeypatch.setenv("SILICONFLOW_API_KEY", "synthetic-canary")
    monkeypatch.setenv("PYTHONPATH", "untrusted-path")

    class Child:
        pid = 99999999

        def __init__(self, args, **kw):
            captured.update(args=args, **kw)

        def wait(self, **kw):
            return 0

    monkeypatch.setattr(bound_jobs.subprocess, "Popen", Child)
    bound_jobs.launch(folder)
    assert captured["args"][:3] == [cfg["interpreter"], "-I", "-B"]
    assert captured["args"][-2:] == [cfg["runtime_source"], str(folder)]
    assert "SILICONFLOW_API_KEY" not in captured["env"] and "PYTHONPATH" not in captured["env"]
    assert captured["env"]["BLIS_NUM_THREADS"] == "1"


def test_live_pid_prevents_duplicate_and_unknown_call_remains_reserved(setup, monkeypatch):
    folder = laboratory_jobs.prepare(*setup)
    write_json(folder / "process.json", {"pid": os.getpid()})
    monkeypatch.setattr(
        bound_jobs.subprocess, "Popen", lambda *a, **kw: pytest.fail("duplicate dispatch")
    )
    with pytest.raises(ValueError, match="still alive"):
        bound_jobs.launch(folder)
    ledger = CostLedger(Path(setup[0]["workspace"]) / "costs.sqlite")
    write_json(
        folder / "checkpoints/0000.json",
        {
            "type": "intent",
            "kind": "provider",
            "name": "initial_engineering",
            "state": {"engine": {"requests": 2}},
        },
    )
    rid = folder.name + "--laboratory-bound-v1--coder--3"
    ledger.reserve(rid, 2)
    ledger.record({"request_id": rid, "state": "unknown"})
    write_json(folder / "provider" / (sha(rid) + ".json"), {"not": "a settled response"})
    assert not bound_jobs.recovery(folder, ledger)[0]
    assert ledger.summary()["unknown_usage_reserved"] == 2


@pytest.mark.parametrize("crash", [3, 6])
def test_actual_worker_hard_exit_recovers_without_duplicate_calls_or_refits(tmp_path, crash):
    settings, scenario = helper.fixture(tmp_path)
    folder = laboratory_jobs.prepare(settings, scenario)
    cfg = read_json(folder / "launch.json")
    command = [cfg["interpreter"], "-I", "-B", str(SCRIPT), "--child", str(folder), "--crash-at"]
    for point, expected in ((crash, 91), (-1, 0), (-1, 0)):
        proc = subprocess.run(command + [str(point)], capture_output=True, timeout=60)
        assert proc.returncode == expected, proc.stderr.decode()[-2000:]
    result = laboratory_jobs.verify_finished(folder, cfg)
    assert result["status"] == "complete"
    assert result["host_submission"]["accounting"]["fitting_attempts"] == 2
    calls = [json.loads(s) for s in (folder / "mock-dispatches.jsonl").read_text().splitlines()]
    assert len(calls) == len({s["request_id"] for s in calls}) == 6
    ledger = CostLedger(Path(settings["workspace"]) / "costs.sqlite")
    view = bound_jobs.view(folder, ledger)
    assert all(r["method_id"] == laboratory_jobs.METHOD_ID for r in view["rules"])
    digest = file_sha(folder / "result.json")
    bound_jobs.launch(folder)
    assert file_sha(folder / "result.json") == digest
    # Terminal reads verify earlier checkpoints, not just the result's own hash.
    p = folder / "checkpoints/0001.json"
    value = read_json(p)
    value["state"]["host"]["fits"] = 100
    write_json(p, value)
    with pytest.raises(ValueError, match="checkpoint chain"):
        bound_jobs.launch(folder)


def test_changed_environment_cannot_start(setup, monkeypatch):
    folder = laboratory_jobs.prepare(*setup)
    env = laboratory_jobs.environment()
    monkeypatch.setattr(laboratory_jobs, "environment", lambda: env | {"changed": True})
    with pytest.raises(ValueError, match="environment changed"):
        laboratory_jobs.verify_binding(folder, check_environment=True)


def test_laboratory_cohort_keeps_unsupported_slots_and_uses_shared_ledger(tmp_path, monkeypatch):
    import shutil

    from principia_asd.llm.siliconflow import PROFILES

    settings, scenario = helper.fixture(tmp_path)
    for sid, count in (("CASE-A", 1), ("CASE-B", 10)):
        dest = scenario.parent / sid
        shutil.copytree(scenario, dest)
        path = dest / "task-contracts/task-001.json"
        task = read_json(path) | {"scenario_id": sid, "task_id": sid + ".task"}
        if count == 10:
            task["inputs"] = [f"x{i}" for i in range(count)]
        write_json(path, task)
    monkeypatch.setattr(pilot, "CASES", ("CASE-A", "CASE-B"))
    price = {
        "at": "fixture",
        "rates": {m: {k: p[k] for k in ("input_rate", "output_rate")} for m, p in PROFILES.items()},
    }
    root, manifest = pilot.prepare(
        settings, "laboratory-cohort-fixture", price, protocol="laboratory-v1"
    )
    assert manifest["policy"] == "explicit-state-laboratory-pilot-v1"
    assert manifest["assigned"] == 2 and manifest["fixed_nomination_slots"] == 6
    monkeypatch.setattr(pilot, "probe", lambda *a: True)

    def launch_fixture(folder):
        cfg = read_json(folder / "launch.json")
        proc = subprocess.run(
            [cfg["interpreter"], "-I", "-B", str(SCRIPT), "--child", str(folder)],
            capture_output=True,
            timeout=60,
        )
        assert proc.returncode == 0, proc.stderr.decode()[-1800:]

    monkeypatch.setattr(bound_jobs, "launch", launch_fixture)
    receipt = pilot.drive(root)
    assert receipt["statuses"] == {"complete": 1, "unsupported": 1}
    assert receipt["fixed_nomination_slots"] == 6
    assert not receipt["ranking_authorized"] and receipt["assessment"] == "not_assessed"
    summary = pilot.summary(root)
    assert summary["costs"]["requests"] == 6
    assert summary["costs"]["pending_cny"] == summary["costs"]["unknown_cny"] == 0
    monkeypatch.setattr(bound_jobs, "launch", lambda *a: pytest.fail("sealed attempt replayed"))
    assert pilot.drive(root) == receipt
    run = Path(settings["workspace"]) / "bound-runs" / manifest["jobs"][0]["run_id"]
    path = run / "inputs" / "train.csv"
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError, match="staged input changed"):
        pilot.drive(root)
