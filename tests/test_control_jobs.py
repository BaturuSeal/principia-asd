"""Control custody and real macOS confinement; no providers or scientific trials."""

import fcntl
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from test_bound_controls import fixture

from principia_asd import control_jobs
from principia_asd.io import file_sha, read_json, write_csv, write_json


@pytest.fixture
def setup(tmp_path):
    settings = {
        "workspace": str(tmp_path / "private"),
        "data_root": str(tmp_path / "data"),
        "leaderboard_root": str(tmp_path / "boards"),
        "vault": str(tmp_path / "vault"),
        "env_file": str(tmp_path / "credentials-canary.env"),
    }
    scenario = tmp_path / "data/scenarios/SYNTHETIC"
    task, train, dev = fixture()
    task.update(
        scenario_id="SYNTHETIC",
        split={
            "train": "public/train.csv.gz",
            "dev": "public/dev.csv.gz",
            "test": "public/test_inputs.csv.gz",
        },
    )
    write_json(scenario / "task-contracts/task-001.json", task)
    for split, rows in (("train", train), ("dev", dev)):
        write_csv(scenario / task["split"][split], rows, list(rows[0]))
    project = tmp_path / "project"
    return settings, scenario, project


def prepare(setup, **kw):
    settings, scenario, project = setup
    return control_jobs.prepare(
        settings, scenario, kw.pop("control", "fixed_symbolic"), project_root=project, **kw
    )


@pytest.fixture(autouse=True)
def supported_runtime(monkeypatch, request):
    if sys.platform != "darwin" or not shutil.which("sandbox-exec"):
        if "actual" in request.node.name:
            pytest.skip("macOS sandbox required; no fallback")
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


def test_preparation_stages_only_allowed_context_without_private_settings(setup):
    folder = prepare(setup)
    inputs = read_json(folder / "inputs.json")
    assert set(inputs) == {"contract", "train", "dev"}
    assert {p.name for p in (folder / "inputs").iterdir()} == {
        "contract.json",
        "train.csv.gz",
        "dev.csv.gz",
    }
    for item in inputs.values():
        assert file_sha(folder / item["path"]) == item["sha256"]
    assert not (folder / "settings.json").exists()
    assert not (Path(setup[0]["workspace"]) / "costs.sqlite").exists()
    assert not Path(setup[0]["vault"]).exists()
    public_metadata = (folder / "launch.json").read_text() + (folder / "request.json").read_text()
    assert "env_file" not in public_metadata and "credentials-canary" not in public_metadata
    assert control_jobs.verify_binding(folder)[1]["scope"] == control_jobs.SCOPE


def test_changed_original_files_do_not_change_staged_context(setup):
    folder = prepare(setup)
    source = setup[1] / "public/train.csv.gz"
    before = (folder / "inputs/train.csv.gz").read_bytes()
    source.write_bytes(b"changed original, never reopened by a worker")
    control_jobs.verify_binding(folder)
    assert (folder / "inputs/train.csv.gz").read_bytes() == before


@pytest.mark.parametrize(
    "item",
    [
        "request.json",
        "launch.json",
        "inputs.json",
        "inputs/train.csv.gz",
        "sandbox.sb",
        "runtime",
        "extra_runtime",
    ],
)
def test_binding_mutation_refused_before_launch(setup, monkeypatch, item):
    folder = prepare(setup)
    cfg = read_json(folder / "launch.json")
    path = folder / item
    if item == "runtime":
        path = Path(cfg["runtime_source"]) / "principia_asd/engine/control_worker.py"
    if item == "extra_runtime":
        path = Path(cfg["runtime_source"]) / "principia_asd/injected.py"
        path.write_text("# never execute")
    elif item == "launch.json":
        cfg["memory_bytes"] += 1
        write_json(path, cfg)
    else:
        path.write_bytes(path.read_bytes() + b" ")
    monkeypatch.setattr(
        control_jobs.subprocess, "Popen", lambda *a, **k: pytest.fail("launched altered work")
    )
    with pytest.raises(ValueError, match="changed"):
        control_jobs.launch(folder)


@pytest.mark.parametrize("root", ["project", "data_root", "leaderboard_root"])
def test_upload_roots_rejected_before_writing(setup, root):
    settings, scenario, project = setup
    settings["workspace"] = str(
        (project if root == "project" else Path(settings[root])) / "mutable"
    )
    with pytest.raises(ValueError, match="three upload roots"):
        prepare(setup)
    assert not Path(settings["workspace"]).exists()


@pytest.mark.parametrize(
    "issue",
    [
        "input_alias",
        "extra_column",
        "same_partition",
        "foreign_group",
        "outside",
        "identity",
        "bad_limits",
        "unknown_control",
    ],
)
def test_bad_inputs_and_requests_cannot_create_jobs(setup, issue):
    settings, scenario, _ = setup
    task_path = scenario / "task-contracts/task-001.json"
    task = read_json(task_path)
    kw = {}
    if issue == "input_alias":
        task["inputs"].append("y")
    if issue == "same_partition":
        task["split"]["dev"] = task["split"]["train"]
    if issue == "identity":
        task["scenario_id"] = "other"
    if issue == "outside":
        task["split"]["train"] = "../../vault/targets.csv"
    if issue == "bad_limits":
        kw["limits"] = {"max_fits": 17}
    if issue == "unknown_control":
        kw["control"] = "invented"
    if issue in {"extra_column", "foreign_group"}:
        _, train, dev = fixture()
        if issue == "extra_column":
            for row in train:
                row["target_alias"] = row["y"]
            write_csv(scenario / task["split"]["train"], train, list(train[0]))
        else:
            dev[0]["group"] = "train"
            write_csv(scenario / task["split"]["dev"], dev, list(dev[0]))
    write_json(task_path, task)
    with pytest.raises(ValueError):
        prepare(setup, **kw)
    assert not (Path(settings["workspace"]) / "control-runs").exists()


def test_missing_sandbox_has_no_unisolated_fallback(setup, monkeypatch):
    monkeypatch.setattr(
        control_jobs,
        "environment",
        lambda: (_ for _ in ()).throw(ValueError("macOS sandbox required")),
    )
    with pytest.raises(ValueError, match="sandbox"):
        prepare(setup)
    assert not (Path(setup[0]["workspace"]) / "control-runs").exists()


def test_duplicate_launcher_and_orphan_worker_are_not_dispatched(setup, monkeypatch):
    folder = prepare(setup)
    monkeypatch.setattr(control_jobs.subprocess, "Popen", lambda *a, **k: pytest.fail("duplicate"))
    with (folder / "launch.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match="Another launcher"):
            control_jobs.launch(folder)
    write_json(folder / "process.json", {"pid": os.getpid()})
    with pytest.raises(ValueError, match="still alive"):
        control_jobs.launch(folder)


def test_cancel_before_launch_retains_zero_work(setup, monkeypatch):
    folder = prepare(setup)
    (folder / "cancel.requested").touch()
    monkeypatch.setattr(
        control_jobs.subprocess, "Popen", lambda *a, **k: pytest.fail("cancelled dispatch")
    )
    assert control_jobs.launch(folder)["status"] == "cancelled"
    assert not (folder / "checkpoints").exists()


def test_launcher_uses_allowlisted_environment_and_saved_runtime(setup, monkeypatch):
    folder = prepare(setup)
    captured = {}
    monkeypatch.setenv("ODDLY_NAMED_PASSWORD", "never inherit arbitrary variables")

    class Child:
        pid = 99999999

        def __init__(self, args, **kwargs):
            captured.update(args=args, **kwargs)

        def wait(self, **kwargs):
            return 0

    monkeypatch.setattr(control_jobs.subprocess, "Popen", Child)
    control_jobs.launch(folder)
    assert "ODDLY_NAMED_PASSWORD" not in captured["env"]
    assert "PYTHONPATH" not in captured["env"]
    cfg = read_json(folder / "launch.json")
    assert captured["args"][0] == cfg["environment"]["sandbox"]
    assert (
        str(Path(cfg["runtime_source"]) / "principia_asd/engine/control_worker.py")
        in captured["args"]
    )
    assert "-I" in captured["args"]
    assert captured["cwd"] == folder


def test_actual_sandboxed_worker_completes_and_terminal_resume_does_no_work(setup):
    folder = prepare(setup)
    state = control_jobs.launch(folder)
    assert state["status"] == "complete", (folder / "worker.log").read_text()
    result = read_json(folder / "result.json")["result"]
    assert result["host_submission"]["accounting"]["fitting_attempts"] == 10
    assert result["model_requests"] == 0
    assert len(result["selection"]["nominations"]) == 3
    before = {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob("*.json")}
    assert control_jobs.launch(folder) == state
    assert before == {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob("*.json")}


def test_actual_sandbox_denies_private_reads_network_and_frozen_writes(setup):
    folder = prepare(setup)
    settings, scenario, _ = setup
    cfg = read_json(folder / "launch.json")
    forbidden = [
        Path(settings["env_file"]),
        Path(settings["vault"]) / "test_targets.json",
        scenario.parent / "SIBLING/measurements.csv",
    ]
    for path in forbidden:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("canary content never returned")
    code = """import json,socket,sys
from pathlib import Path
result={}
for i,path in enumerate(json.loads(sys.argv[1])):
 try: Path(path).read_bytes();result['read'+str(i)]=False
 except PermissionError: result['read'+str(i)]=True
for i,path in enumerate(json.loads(sys.argv[2])):
 try: Path(path).write_text('MUTATION');result['write'+str(i)]=False
 except PermissionError: result['write'+str(i)]=True
try:
 socket.socket().connect(('127.0.0.1',9));result['network']=False
except PermissionError: result['network']=True
print(json.dumps(result))
"""
    import json

    protected = [
        folder / "inputs/train.csv.gz",
        folder / "launch.json",
        Path(cfg["runtime_source"]) / "principia_asd/engine/control_worker.py",
    ]
    result = subprocess.run(
        [
            cfg["environment"]["sandbox"],
            "-f",
            str(folder / "sandbox.sb"),
            cfg["environment"]["python"],
            "-I",
            "-B",
            "-c",
            code,
            json.dumps([str(p) for p in forbidden]),
            json.dumps([str(p) for p in protected]),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert len(json.loads(result.stdout)) == 7 and all(json.loads(result.stdout).values()), (
        result.stdout
    )
    control_jobs.verify_binding(folder)


@pytest.mark.parametrize("boundary", ["fixed-experiment-2", "nominate"])
def test_actual_worker_hard_exit_recovers_only_committed_work(setup, boundary):
    folder = prepare(setup)
    cfg = read_json(folder / "launch.json")
    Path(setup[0]["workspace"], "worker-slots").mkdir(exist_ok=True)
    # Fault injection exists in this test wrapper only, never in a worker request.
    wrapper = """import json,sys,os
from pathlib import Path
f=Path(sys.argv[1]);c=json.loads((f/'launch.json').read_text())
sys.path[:0]=[c['runtime_source'],*c['environment']['site_paths']]
from principia_asd.engine.bound_checkpoint import DurableBoundRun
from principia_asd.engine.control_worker import execute
original=DurableBoundRun._append
def fault(self,record):
 result=original(self,record)
 if record['type']=='commit' and record['name']==sys.argv[2]:os._exit(83)
 return result
DurableBoundRun._append=fault
execute(f)
"""
    run = subprocess.run(
        [
            cfg["environment"]["sandbox"],
            "-f",
            str(folder / "sandbox.sb"),
            cfg["environment"]["python"],
            "-I",
            "-B",
            "-c",
            wrapper,
            str(folder),
            boundary,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert run.returncode == 83, run.stderr
    assert control_jobs.launch(folder)["status"] == "complete", (folder / "worker.log").read_text()
    result = read_json(folder / "result.json")["result"]
    assert result["host_submission"]["accounting"]["fitting_attempts"] == 10
    assert len(result["experiments"]) == 10


def test_actual_four_shared_slots_block_work_until_cancellation(setup):
    import time
    from concurrent.futures import ThreadPoolExecutor

    folder = prepare(setup)
    slots = Path(setup[0]["workspace"]) / "worker-slots"
    slots.mkdir(exist_ok=True)
    locks = []
    try:
        for i in range(4):
            lock = (slots / f"{i}.lock").open("a+")
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locks.append(lock)
        with ThreadPoolExecutor(max_workers=1) as pool:
            running = pool.submit(control_jobs.launch, folder)
            deadline = time.monotonic() + 10
            while not (folder / "process.json").exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert (folder / "process.json").exists()
            time.sleep(0.5)
            assert not (folder / "checkpoints").exists()
            (folder / "cancel.requested").touch()
            assert running.result(timeout=10)["status"] == "cancelled"
        assert not (folder / "checkpoints").exists()
    finally:
        for lock in locks:
            lock.close()


def test_actual_wall_watchdog_covers_slot_waiting(setup):
    folder = prepare(setup, limits={"max_seconds": 1})
    slots = Path(setup[0]["workspace"]) / "worker-slots"
    slots.mkdir(exist_ok=True)
    locks = []
    try:
        for i in range(4):
            lock = (slots / f"{i}.lock").open("a+")
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locks.append(lock)
        state = control_jobs.launch(folder)
        assert state["status"] == "interrupted"
        assert state["exit_code"] == 137
        assert "wall-time limit" in (folder / "resource-limit.txt").read_text()
        assert not (folder / "checkpoints").exists()
    finally:
        for lock in locks:
            lock.close()
