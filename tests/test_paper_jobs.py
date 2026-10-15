import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from principia_asd import adapter_jobs, bound_jobs, bound_pilot, paper_jobs
from principia_asd.io import file_sha, read_json, sha, write_json
from principia_asd.store.ledger import CostLedger

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/verify_paper_worker.py"
spec = importlib.util.spec_from_file_location("paper_fixture", SCRIPT)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


@pytest.fixture
def setup(tmp_path):
    return helper.helper().fixture(tmp_path)


def child(folder, *args):
    cfg = read_json(folder / "launch.json")
    return subprocess.run(
        [cfg["interpreter"], "-I", "-B", str(SCRIPT), "--child", str(folder), *args],
        capture_output=True,
        timeout=60,
    )


def test_exact_paper_identity_and_development_custody(setup):
    folder = paper_jobs.prepare(*setup)
    cfg, req, settings = paper_jobs.verify_binding(folder, check_environment=True)
    assert req["scope"] == paper_jobs.SCOPE and folder.name.startswith("paper-")
    assert read_json(folder / "ui.json")["method_id"] == paper_jobs.METHOD_ID
    assert set(read_json(folder / "inputs.json")) == {"contract", "train", "dev"}
    assert set(settings) == {"workspace"}
    assert req["limits"]["max_calls"] == 6 and req["limits"]["max_fits"] == 2
    assert cfg["memory_bytes"] == 4 * 1024**3 and cfg["numerical_threads"] == 1
    with pytest.raises(ValueError, match="identity"):
        adapter_jobs.verify_binding(folder, adapter="laboratory")
    with pytest.raises(ValueError, match="Unknown"):
        adapter_jobs.prepare(*setup, adapter="unknown")


@pytest.mark.parametrize(
    "which", ["capability", "budget", "limits", "roles", "vault", "extra_column"]
)
def test_preflight_errors_never_create_a_run(setup, which):
    settings, scenario = setup
    kw = {}
    if which == "capability":
        write_json(Path(settings["workspace"]) / "capabilities.json", {})
    elif which == "budget":
        kw["budget"] = float("nan")
    elif which == "limits":
        kw["limits"] = {"max_calls": 7}
    elif which == "roles":
        kw["roles"] = {"coder": "fallback"}
    elif which == "vault":
        settings["vault"] = settings["workspace"]
    else:
        f = scenario / "train.csv"
        f.write_text(f.read_text().replace("sample_id,", "target_alias,sample_id,", 1))
    with pytest.raises((ValueError, KeyError)):
        paper_jobs.prepare(settings, scenario, **kw)
    assert not list(Path(settings["workspace"]).glob("bound-runs/*"))


@pytest.mark.parametrize(
    "target", ["request", "settings", "inputs", "capabilities", "ui", "staged", "runtime"]
)
def test_mutations_fail_before_process_dispatch(setup, monkeypatch, target):
    folder = paper_jobs.prepare(*setup)
    cfg = read_json(folder / "launch.json")
    path = folder / (target + ".json")
    if target == "staged":
        path = folder / read_json(folder / "inputs.json")["train"]["path"]
    elif target == "runtime":
        path = Path(cfg["runtime_source"]) / "principia_asd/engine/bound_data_to_paper.py"
    path.write_text(path.read_text() + " ")
    monkeypatch.setattr(
        bound_jobs.subprocess, "Popen", lambda *a, **kw: pytest.fail("unsafe dispatch")
    )
    with pytest.raises(ValueError, match="changed"):
        bound_jobs.launch(folder)


def test_launch_uses_paper_entrypoint_and_no_credentials_or_duplicate_process(setup, monkeypatch):
    folder = paper_jobs.prepare(*setup)
    cfg = read_json(folder / "launch.json")
    captured = {}
    monkeypatch.setenv("API_KEY", "synthetic-canary")
    monkeypatch.setenv("PYTHONPATH", "hostile")

    class Child:
        pid = 99999999

        def __init__(self, args, **kw):
            captured.update(args=args, **kw)

        def wait(self, **kw):
            return 0

    monkeypatch.setattr(bound_jobs.subprocess, "Popen", Child)
    bound_jobs.launch(folder)
    assert captured["args"][:3] == [cfg["interpreter"], "-I", "-B"]
    assert "engine.paper_worker" in captured["args"][4]
    assert "API_KEY" not in captured["env"] and "PYTHONPATH" not in captured["env"]
    write_json(folder / "process.json", {"pid": os.getpid()})
    with pytest.raises(ValueError, match="still alive"):
        bound_jobs.launch(folder)


@pytest.mark.parametrize(
    "name,role,count",
    [
        ("analysis_plan", "planner", 0),
        ("analysis_program", "coder", 1),
        ("analysis_repair", "coder", 2),
        ("statistical_review", "critic", 3),
        ("evidence_report", "reporter", 4),
        ("report_repair", "reporter", 5),
    ],
)
def test_each_paper_recovery_id_matches_exact_settled_cache(setup, name, role, count):
    folder = paper_jobs.prepare(*setup)
    write_json(
        folder / "checkpoints/0000.json",
        {
            "type": "intent",
            "kind": "provider",
            "name": name,
            "state": {"engine": {"requests": count}},
        },
    )
    ledger = CostLedger(Path(setup[0]["workspace"]) / "costs.sqlite")
    rid = f"{folder.name}--paper-bound-v1--{role}--{count + 1}"
    ledger.reserve(rid, 2)
    ledger.record({"request_id": rid, "state": "unknown"})
    write_json(
        folder / "provider" / (sha(rid) + ".json"),
        {"placeholder": "eligibility only; worker verifies content"},
    )
    assert not bound_jobs.recovery(folder, ledger)[0]
    completed_ledger = CostLedger(Path(setup[0]["workspace"]) / "completed-fixture.sqlite")
    completed_ledger.reserve(rid, 2)
    completed_ledger.record({"request_id": rid, "state": "completed", "actual_cny": 0.02})
    assert bound_jobs.recovery(folder, completed_ledger)[0]


@pytest.mark.parametrize("crash", [2, 4, 6])
def test_real_worker_hard_exit_at_repairs_and_frozen_review_resumes_exactly(setup, crash):
    folder = paper_jobs.prepare(*setup)
    for point, expected in ((crash, 91), (-1, 0), (-1, 0)):
        p = child(folder, "--case", "both_repairs", "--crash-at", str(point))
        assert p.returncode == expected, p.stderr.decode()[-2000:]
    cfg = read_json(folder / "launch.json")
    result = paper_jobs.verify_finished(folder, cfg)
    assert (
        result["status"] == "complete"
        and result["host_submission"]["accounting"]["fitting_attempts"] == 1
    )
    assert len(result["statistical_accounting"]) == 1 and result["verified_report"]["valid"]
    calls = [json.loads(s) for s in (folder / "mock-dispatches.jsonl").read_text().splitlines()]
    assert len(calls) == len({s["request_id"] for s in calls}) == 6
    digest = file_sha(folder / "result.json")
    bound_jobs.launch(folder)
    assert file_sha(folder / "result.json") == digest
    view = bound_jobs.view(folder, CostLedger(Path(setup[0]["workspace"]) / "costs.sqlite"))
    assert view["rules"][0]["method_id"] == paper_jobs.METHOD_ID


def test_unknown_post_freeze_local_work_is_blocked_without_paid_replay(setup):
    folder = paper_jobs.prepare(*setup)
    p = child(folder, "--crash-local", "computed_statistics")
    assert p.returncode == 92, p.stderr.decode()[-2000:]
    before = (folder / "mock-dispatches.jsonl").read_bytes()
    p = child(folder)
    assert p.returncode != 0 and b"RecoveryRequired" in p.stderr
    assert read_json(folder / "state.json")["status"] == "recovery_required"
    assert (folder / "mock-dispatches.jsonl").read_bytes() == before


@pytest.mark.parametrize("command", ["evaluate", "replay", "resume"])
def test_ordinary_cli_cannot_route_missing_bindings_to_legacy(setup, monkeypatch, command):
    from principia_asd import cli

    folder = paper_jobs.prepare(*setup)
    if command == "resume":
        (folder / "launch.json").unlink()
    monkeypatch.setattr(
        sys,
        "argv",
        ["principia-asd", command, str(folder), "--settings", str(folder / "settings.json")],
    )
    with pytest.raises(SystemExit):
        cli.main()


def test_paper_pilot_keeps_unsupported_slots_and_matches_shared_cost_records(setup, monkeypatch):
    import shutil

    from principia_asd.llm.siliconflow import PROFILES

    settings, scenario = setup
    for sid, count in (("CASE-A", 1), ("CASE-B", 10)):
        dest = scenario.parent / sid
        shutil.copytree(scenario, dest)
        path = dest / "task-contracts/task-001.json"
        task = read_json(path) | {"scenario_id": sid, "task_id": sid + ".task"}
        if count == 10:
            task["inputs"] = [f"x{i}" for i in range(count)]
        write_json(path, task)
    monkeypatch.setattr(bound_pilot, "CASES", ("CASE-A", "CASE-B"))
    price = {
        "at": "fixture",
        "rates": {m: {k: p[k] for k in ("input_rate", "output_rate")} for m, p in PROFILES.items()},
    }
    root, manifest = bound_pilot.prepare(settings, "paper-fixture", price, protocol="paper-v1")
    assert manifest["policy"] == "explicit-state-data-to-paper-pilot-v1"
    monkeypatch.setattr(bound_pilot, "probe", lambda *a: True)

    def launch(folder):
        p = child(folder)
        assert p.returncode == 0, p.stderr.decode()[-2000:]

    monkeypatch.setattr(bound_jobs, "launch", launch)
    receipt = bound_pilot.drive(root)
    assert receipt["statuses"] == {"complete": 1, "unsupported": 1}
    assert receipt["fixed_nomination_slots"] == 6 and receipt["nominated_slots"] == 1
    summary = bound_pilot.summary(root)
    assert summary["costs"]["requests"] == 4 and summary["costs"]["pending_cny"] == 0
    row = read_json(root / "outcomes/CASE-A.json")
    assert (
        row["computed_facts_sha256"] and row["statistical_accounting"][0]["prediction_rows"] == 10
    )
    monkeypatch.setattr(bound_jobs, "launch", lambda *a: pytest.fail("sealed replay"))
    assert bound_pilot.drive(root) == receipt
