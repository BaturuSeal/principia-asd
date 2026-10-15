"""Installed, sandboxed control-worker proof using only synthetic measurements."""

import argparse
import inspect
import json
import os
import subprocess
import tempfile
from pathlib import Path

from principia_asd import control_jobs
from principia_asd.io import file_sha, read_json, write_csv, write_json
from principia_asd.runtime import now


def verify(workspace, receipt):
    assert "site-packages" in inspect.getfile(control_jobs)
    workspace.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="control-worker-fixture-", dir=workspace))
    settings = {
        "workspace": str(root / "private"),
        "data_root": str(root / "data"),
        "leaderboard_root": str(root / "boards"),
        "vault": str(root / "vault"),
    }
    scenario = root / "data/scenarios/SYNTHETIC"
    task = {
        "scenario_id": "SYNTHETIC",
        "inputs": ["x", "z"],
        "output": "y",
        "metric": {"primary": "rmse"},
        "stability": {"ranking": False},
        "split": {"train": "public/train.csv", "dev": "public/dev.csv", "test": "never-open.csv"},
    }
    write_json(scenario / "task-contracts/task-001.json", task)
    for name, values in (("train", range(20)), ("dev", range(20, 25))):
        rows = [
            {
                "sample_id": f"{name}-{i}",
                "group": name,
                "x": i / 10,
                "z": (i % 4) / 10,
                "y": 2 + 0.3 * (i / 10) + 0.2 * ((i % 4) / 10) ** 2,
            }
            for i in values
        ]
        write_csv(scenario / task["split"][name], rows, list(rows[0]))
    methods = ["fitted_constant", "affine", "quadratic", "fixed_symbolic"]
    jobs = {
        method: control_jobs.prepare(settings, scenario, method, project_root=root / "project")
        for method in methods
    }
    write_json(
        root / "assignment-freeze.json",
        {method: file_sha(folder / "launch.json") for method, folder in jobs.items()},
        immutable=True,
    )
    cases = []
    for method, folder in jobs.items():
        state = control_jobs.launch(folder)
        assert state["status"] == "complete", (folder / "worker.log").read_text()
        digest = file_sha(folder / "result.json")
        assert control_jobs.launch(folder) == state and file_sha(folder / "result.json") == digest
        result = read_json(folder / "result.json")["result"]
        cases.append(
            {
                "method": method,
                "result_sha256": digest,
                "status": state["status"],
                "fits": result["host_submission"]["accounting"]["fitting_attempts"],
                "slots": 3,
                "nominations": sum(
                    s["status"] == "nominated" for s in result["selection"]["nominations"]
                ),
                "api_calls": 0,
            }
        )
    folder = jobs["fixed_symbolic"]
    cfg = read_json(folder / "launch.json")
    canaries = [
        root / "credentials.env",
        root / "vault/test_targets.json",
        root / "data/scenarios/SIBLING/data.csv",
    ]
    for path in canaries:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic canary; never print content")
    protected = [
        folder / "inputs/train.csv",
        folder / "request.json",
        Path(cfg["runtime_source"]) / "principia_asd/control_jobs.py",
    ]
    code = """import json,socket,sys
from pathlib import Path
result={}
for i,path in enumerate(json.loads(sys.argv[1])):
 try: Path(path).read_bytes();result['private_read_'+str(i)]=False
 except PermissionError: result['private_read_'+str(i)]=True
for i,path in enumerate(json.loads(sys.argv[2])):
 try: Path(path).write_text('MUTATION');result['frozen_write_'+str(i)]=False
 except PermissionError: result['frozen_write_'+str(i)]=True
try: socket.socket().connect(('127.0.0.1',9));result['network']=False
except PermissionError: result['network']=True
print(json.dumps(result))
"""
    command = [
        cfg["environment"]["sandbox"],
        "-f",
        str(folder / "sandbox.sb"),
        cfg["environment"]["python"],
        "-I",
        "-B",
        "-c",
        code,
        json.dumps([str(p) for p in canaries]),
        json.dumps([str(p) for p in protected]),
    ]
    denied = subprocess.run(
        command, capture_output=True, text=True, timeout=15, env={"PATH": "/usr/bin:/bin"}
    )
    assert denied.returncode == 0, denied.stderr
    guards = json.loads(denied.stdout)
    assert len(guards) == 7 and all(guards.values()), guards
    control_jobs.verify_binding(folder)

    recoveries = []
    for kind, boundary in (
        ("commit", "fixed-experiment-2"),
        ("commit", "nominate"),
        ("intent", "fixed-experiment-2"),
    ):
        folder = control_jobs.prepare(
            settings, scenario, "fixed_symbolic", project_root=root / "project"
        )
        cfg = read_json(folder / "launch.json")
        wrapper = """import json,sys,os
from pathlib import Path
f=Path(sys.argv[1]);c=json.loads((f/'launch.json').read_text())
sys.path[:0]=[c['runtime_source'],*c['environment']['site_paths']]
from principia_asd.engine.bound_checkpoint import DurableBoundRun
from principia_asd.engine.control_worker import execute
original=DurableBoundRun._append
def fault(self,record):
 result=original(self,record)
 if record['type']==sys.argv[2] and record['name']==sys.argv[3]:os._exit(83)
 return result
DurableBoundRun._append=fault
execute(f)
"""
        child = subprocess.run(
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
                kind,
                boundary,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            env={"PATH": "/usr/bin:/bin"},
        )
        assert child.returncode == 83, child.stderr
        before = {p.name: file_sha(p) for p in (folder / "checkpoints").glob("*.json")}
        state = control_jobs.launch(folder)
        expected = "complete" if kind == "commit" else "recovery_required"
        assert state["status"] == expected, (folder / "worker.log").read_text()
        if kind == "commit":
            out = read_json(folder / "result.json")["result"]
            assert out["host_submission"]["accounting"]["fitting_attempts"] == 10
        else:
            assert before == {p.name: file_sha(p) for p in (folder / "checkpoints").glob("*.json")}
            assert not (folder / "result.json").exists()
        recoveries.append(
            {"kind": kind, "boundary": boundary, "state": expected, "duplicate_completed_work": 0}
        )
    assert not (root / "private/costs.sqlite").exists()
    proof = {
        "checked_at": now(),
        "status": "passed_installed_sandboxed_controls",
        "scope": "Synthetic host-authored control fixtures; not a scientific comparison or generated-Python execution",
        "source_is_installed_distribution": True,
        "module_sha256": file_sha(Path(inspect.getfile(control_jobs))),
        "cases": cases,
        "sandbox_denials": guards,
        "hard_exit_recovery": recoveries,
        "api_calls": 0,
        "ledger_created": False,
        "fixed_nomination_slots": 12,
        "numerical_threads": 1,
        "memory_limit_bytes": 4 * 1024**3,
        "ranking_authorized": False,
        "scientific_review": "not_assessed",
        "private_fixture_root": str(root),
        "secrets_inherited": False,
        "fault_injection": "Test wrapper only; copied runtime and request were not edited",
    }
    write_json(receipt, proof, immutable=True)
    print({k: v for k, v in proof.items() if k != "private_fixture_root"})


if __name__ == "__main__":
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--receipt", type=Path, required=True)
    args = p.parse_args()
    verify(args.workspace.resolve(), args.receipt)
