"""Frozen engineering cohorts retain failures without private-test assessment."""

import copy
from pathlib import Path

import pytest
from test_bound_engine import FixtureGateway, fixture

from principia_asd import bound_jobs
from principia_asd import bound_pilot as pilot
from principia_asd.engine.bound_engine import BoundEngine
from principia_asd.io import file_sha, read_json, write_json
from principia_asd.llm.siliconflow import PROFILES
from principia_asd.store.ledger import CostLedger
from principia_asd.web.server import App


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(pilot, "CASES", ("CASE-A", "CASE-B", "CASE-C"))
    settings = {
        "workspace": str(tmp_path / "private"),
        "data_root": str(tmp_path / "data"),
        "leaderboard_root": str(tmp_path / "boards"),
        "vault": str(tmp_path / "vault"),
    }
    caps = {m: {"state": "verified", "generation": p} for m, p in PROFILES.items()}
    write_json(Path(settings["workspace"]) / "capabilities.json", caps)
    originals = {}
    for sid in pilot.CASES:
        root = Path(settings["data_root"]) / "scenarios" / sid
        task = fixture()[0] | {
            "scenario_id": sid,
            "task_id": "task-001",
            "split": {"train": "public/train.csv", "dev": "public/dev.csv"},
        }
        if sid == "CASE-C":
            task["inputs"] = ["x" + str(i) for i in range(10)]
        write_json(root / "task-contracts/task-001.json", task)
        (root / "public").mkdir()
        for name in ("train", "dev", "test_inputs", "test_targets"):
            (root / "public" / (name + ".csv")).write_text("canary-" + name)
        originals.update({p: file_sha(p) for p in root.rglob("*") if p.is_file()})
    price = {
        "at": "fixture",
        "rates": {m: {k: p[k] for k in ("input_rate", "output_rate")} for m, p in PROFILES.items()},
    }
    return settings, price, originals


def prepared(setup):
    settings, price, _ = setup
    return pilot.prepare(settings, "fixture-pilot", price)


def test_only_train_dev_staged_and_fixed_unsupported_denominator(setup):
    root, m = prepared(setup)
    assert m["assigned"] == 3 and m["fixed_nomination_slots"] == 9
    assert [j["supported"] for j in m["jobs"]] == [True, True, False]
    assert m["maximum_additional_cny"] == 32 and m["workers"] == 4
    assert all(p.name not in {"test_inputs.csv", "test_targets.csv"} for p in root.rglob("*"))
    assert "vault" not in read_json(root / "settings.json")
    assert not Path(setup[0]["vault"]).exists()
    assert all(file_sha(p) == h for p, h in setup[2].items())
    assert pilot.check(root) == m
    with pytest.raises(FileExistsError):
        prepared(setup)
    out = pilot.run_one(root, m, m["jobs"][-1])
    assert out["status"] == "unsupported" and len(out["nomination_slots"]) == 3
    assert not out["ranking_authorized"] and out["assessment"] == "not_assessed"


@pytest.mark.parametrize("mutation", ["data", "runtime", "request", "global_caps", "settings"])
def test_frozen_context_mutation_blocks_dispatch(setup, mutation, monkeypatch):
    root, m = prepared(setup)
    path = {
        "data": root / next(iter(m["inputs"])),
        "runtime": Path(m["runtime_source"]) / "principia_asd/bound_pilot.py",
        "request": Path(m["workspace"]) / "bound-runs" / m["jobs"][0]["run_id"] / "request.json",
        "global_caps": Path(m["workspace"]) / "capabilities.json",
        "settings": root / "settings.json",
    }[mutation]
    path.write_text(path.read_text() + " ")
    monkeypatch.setattr(pilot, "probe", lambda *a: pytest.fail("dispatched"))
    with pytest.raises(ValueError, match="changed"):
        pilot.drive(root)


class ProbeGateway:
    calls = []
    recovered = []

    def __init__(self, **kwargs):
        self.ledger = kwargs["ledger"]
        self.attempt = str(kwargs["artifact_dir"])
        assert kwargs["attempt_cap_cny"] == 8

    def complete(self, **kw):
        self.calls.append(copy.deepcopy(kw))
        rid = kw["request_id"]
        self.ledger.reserve(rid, 2, attempt_id=self.attempt, attempt_cap_cny=8)
        self.ledger.record({"request_id": rid, "state": "completed", "actual_cny": 0.01})
        return {"text": '{"ok":true}'}

    def recover_completed(self, **kw):
        self.recovered.append(kw["request_id"])
        if self.ledger.get(kw["request_id"])["state"] != "completed":
            raise ValueError("Unknown billed request cannot be replayed")
        return {"text": '{"ok":true}'}


def fake_probe(monkeypatch):
    ProbeGateway.calls, ProbeGateway.recovered = [], []
    monkeypatch.setattr(pilot, "SiliconFlowClient", ProbeGateway)


def test_exact_profiles_probed_once_and_saved_receipts_reused(setup, monkeypatch):
    root, m = prepared(setup)
    fake_probe(monkeypatch)
    assert pilot.probe(root, m) and pilot.probe(root, m)
    assert len(ProbeGateway.calls) == 4
    assert {c["model"] for c in ProbeGateway.calls} == set(PROFILES)
    assert all(c["max_tokens"] == 1800 and c["temperature"] == 0.25 for c in ProbeGateway.calls)


@pytest.mark.parametrize("state", ["reserved", "unknown", "completed"])
def test_existing_probe_is_recovered_only_never_sent_again(setup, monkeypatch, state):
    root, m = prepared(setup)
    fake_probe(monkeypatch)
    model = next(iter(PROFILES))
    rid = m["campaign_id"] + "--probe--" + model
    ledger = CostLedger(Path(m["workspace"]) / "costs.sqlite")
    ledger.reserve(rid, 2)
    if state != "reserved":
        receipt = {"request_id": rid, "state": state}
        if state == "completed":
            receipt["actual_cny"] = 0.01
        ledger.record(receipt)
    assert pilot.probe(root, m) == (state == "completed")
    assert len(ProbeGateway.calls) == 3 and ProbeGateway.recovered == [rid]
    assert pilot.probe(root, m) == (state == "completed")
    assert len(ProbeGateway.calls) == 3
    if state != "completed":
        assert ledger.summary()["unknown_usage_reserved"] == 2


def test_failed_capability_never_starts_workers(setup, monkeypatch):
    root, _ = prepared(setup)
    monkeypatch.setattr(pilot, "probe", lambda *a: False)
    monkeypatch.setattr(bound_jobs, "launch", lambda *a: pytest.fail("worker dispatched"))
    assert pilot.drive(root)["phase"] == "blocked_capability"
    assert not (root / "submission-freeze.json").exists()


def test_complete_failed_unsupported_preserved_and_resume_does_not_replay(setup, monkeypatch):
    root, m = prepared(setup)
    fake_probe(monkeypatch)
    launched = []

    def worker(folder):
        launched.append(folder.name)
        failure = 1 if folder.name == m["jobs"][1]["run_id"] else None
        result = BoundEngine(
            *fixture(), gateway=FixtureGateway(fail_at=failure), run_id=folder.name
        ).run()
        write_json(folder / "result.json", {"result": result})
        write_json(folder / "state.json", {"status": result["status"]})

    monkeypatch.setattr(bound_jobs, "launch", worker)
    result = pilot.drive(root)
    assert result["statuses"] == {"complete": 1, "failed": 1, "unsupported": 1}
    assert result["fixed_nomination_slots"] == 9
    assert len(launched) == 2 and len(ProbeGateway.calls) == 4
    assert pilot.drive(root) == result
    assert pilot.launch(root)["status"] == "already_finished"
    assert len(launched) == 2 and len(ProbeGateway.calls) == 4
    summary = pilot.summary(root)
    assert summary["terminal_records"] == 3 and summary["submission_freeze"]
    assert summary["costs"]["accounted_cny"] == pytest.approx(0.04)
    assert summary["costs"]["states"] == {"completed": 4}
    assert not summary["driver_alive"] and not summary["active_workers"]
    assert not Path(setup[0]["leaderboard_root"]).exists()
    path = Path(m["workspace"]) / "bound-runs" / launched[0] / "result.json"
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError, match="Sealed worker result changed"):
        pilot.drive(root)


def test_interrupted_numerics_retained_without_refitting(setup, monkeypatch):
    root, m = prepared(setup)
    job = m["jobs"][0]
    run = Path(m["workspace"]) / "bound-runs" / job["run_id"]
    write_json(
        run / "checkpoints/0000.json", {"type": "intent", "kind": "local", "name": "initialize"}
    )
    monkeypatch.setattr(bound_jobs, "launch", lambda *a: pytest.fail("refitted"))
    out = pilot.run_one(root, m, job)
    assert out["status"] == "recovery_required" and len(out["nomination_slots"]) == 3
    assert pilot.run_one(root, m, job) == out


def test_managed_pilot_cannot_be_launched_through_ui(setup):
    root, m = prepared(setup)
    app = App(setup[0])
    try:
        run = Path(m["workspace"]) / "bound-runs" / m["jobs"][0]["run_id"]
        assert app.get_run(run.name)["status"] == "queued"
        assert not app.get_run(run.name)["resume_available"]
        with pytest.raises(ValueError, match="managed"):
            app.queue_bound(run)
        with pytest.raises(ValueError, match="managed"):
            app.resume_bound(run.name)
        app.cancel(run.name)
        out = pilot.run_one(root, m, m["jobs"][0])
        assert out["status"] == "cancelled" and len(out["nomination_slots"]) == 3
    finally:
        app.pool.shutdown()
        app.server_lock.close()


def test_pilot_launcher_uses_bound_runtime_and_does_not_duplicate(setup, monkeypatch):
    root, m = prepared(setup)
    captured = []

    class Child:
        pid = 987654321

        def __init__(self, args, **kw):
            captured.append((args, kw))

    monkeypatch.setenv("SILICONFLOW_API_KEY", "never-expose-canary")
    monkeypatch.setattr(pilot.subprocess, "Popen", Child)
    assert pilot.launch(root)["status"] == "started"
    args, kw = captured[0]
    assert kw["env"]["PYTHONPATH"] == m["runtime_source"]
    assert "SILICONFLOW_API_KEY" not in kw["env"]
    assert kw["env"]["OMP_NUM_THREADS"] == "1"
    assert args[-3:] == ["principia_asd.bound_pilot", "drive", str(root)]
    monkeypatch.setattr(pilot.os, "kill", lambda *args: None)
    assert pilot.launch(root)["status"] == "already_running"
    assert len(captured) == 1
