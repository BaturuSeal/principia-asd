"""Frozen train/dev-only fixed-control cohorts; no provider or final evaluation."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import control_jobs
from .bound_pilot import CASES, record, verified
from .engine.bound_controls import CONTROLS
from .engine.bound_controls import POLICY as METHOD_POLICY
from .io import file_sha, read_json, sha, write_json
from .runtime import now

POLICY = "explicit-state-control-pilot-v1"


def alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (ProcessLookupError, ValueError, TypeError):
        return False


def prepare(settings, campaign_id, *, project_root):
    if not isinstance(campaign_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", campaign_id):
        raise ValueError("Invalid control cohort identity")
    workspace = Path(settings["workspace"]).resolve()
    for root in (
        project_root,
        settings["data_root"],
        settings["leaderboard_root"],
        settings["vault"],
    ):
        root = Path(root).resolve()
        if root.is_relative_to(workspace) or workspace.is_relative_to(root):
            raise ValueError("Control cohort must be separate from uploads and evaluator custody")
    root = workspace / "control-campaigns" / campaign_id
    root.mkdir(parents=True, exist_ok=False)
    jobs, source = [], None
    for sid in CASES:
        for method in CONTROLS:
            folder = control_jobs.prepare(
                settings,
                Path(settings["data_root"]) / "scenarios" / sid,
                method,
                project_root=project_root,
            )
            cfg, request = control_jobs.verify_binding(folder)
            if source and cfg["runtime_source"] != source:
                raise ValueError("Source changed during preparation; cohort is not launchable")
            source = cfg["runtime_source"]
            jobs.append(
                {
                    "assignment_id": sid + "--" + method,
                    "scenario_id": sid,
                    "control": method,
                    "run_id": folder.name,
                    "nomination_slots": 3,
                    "launch_sha256": file_sha(folder / "launch.json"),
                    "configuration_sha256": request["configuration_sha256"],
                    "exposure": "Previously engineering-exposed; retrospective development only",
                }
            )
    m = record(
        root / "manifest.json",
        {
            "policy": POLICY,
            "method_policy": METHOD_POLICY,
            "campaign_id": campaign_id,
            "created_at": now(),
            "workspace": str(workspace),
            "runtime_source": source,
            "driver_python": sys.executable,
            "driver_python_sha256": file_sha(Path(sys.executable)),
            "cases": list(CASES),
            "controls": list(CONTROLS),
            "jobs": jobs,
            "assigned": len(jobs),
            "fixed_nomination_slots": len(jobs) * 3,
            "workers": 4,
            "api_calls": 0,
            "scope": "engineering_only_train_dev_no_final_assessment",
            "ranking_authorized": False,
            "scientific_review": "not_assessed",
            "retry_policy": "Committed work restored; ambiguous local work retained, never refitted",
        },
    )
    write_json(root / "driver-status.json", {"phase": "prepared", "at": now()})
    return root, m


def check(root):
    root = Path(root).resolve()
    m = verified(root / "manifest.json")
    workspace = Path(m["workspace"])
    expected = {(s, c) for s in m["cases"] for c in m["controls"]}
    if (
        m["policy"] != POLICY
        or m["method_policy"] != METHOD_POLICY
        or root != workspace / "control-campaigns" / m["campaign_id"]
        or m["assigned"] != len(expected)
        or len(m["jobs"]) != len(expected)
        or {(j["scenario_id"], j["control"]) for j in m["jobs"]} != expected
        or len({j["run_id"] for j in m["jobs"]}) != m["assigned"]
        or m["fixed_nomination_slots"] != m["assigned"] * 3
        or m["workers"] != 4
        or m["api_calls"] != 0
        or m["ranking_authorized"]
        or file_sha(Path(m["driver_python"])) != m["driver_python_sha256"]
    ):
        raise ValueError("Frozen control cohort identity or denominator changed")
    for job in m["jobs"]:
        folder = workspace / "control-runs" / job["run_id"]
        cfg, request = control_jobs.verify_binding(folder, check_environment=True)
        if (
            file_sha(folder / "launch.json") != job["launch_sha256"]
            or cfg["runtime_source"] != m["runtime_source"]
            or job["configuration_sha256"] != request["configuration_sha256"]
            or job["scenario_id"] != request["scenario_id"]
            or job["control"] != request["control"]
            or job["nomination_slots"] != 3
            or job["assignment_id"] != job["scenario_id"] + "--" + job["control"]
        ):
            raise ValueError("Frozen control assignment changed")
    return m


def result_record(folder, job):
    envelope = read_json(folder / "result.json")
    result = envelope["result"]
    if (
        result["sha256"] != sha({k: v for k, v in result.items() if k != "sha256"})
        or result["configuration"]["sha256"] != job["configuration_sha256"]
        or result["policy"] != METHOD_POLICY
        or result["model_requests"] != 0
        or result["host_submission"]["accounting"]["api_calls"] != 0
        or result["ranking_authorized"]
    ):
        raise ValueError("Worker result differs from its frozen control assignment")
    manifest = read_json(folder / "manifest.json")
    if (
        manifest["binding"]["configuration"] != result["configuration"]
        or manifest["binding"]["run_id"] != job["run_id"]
        or manifest["binding"]["provider"]
        != {
            "provider": "none",
            "api_calls": 0,
            "launch_sha256": read_json(folder / "launch.json")["sha256"],
        }
    ):
        raise ValueError("Control journal configuration changed")
    previous, pending = sha(manifest), None
    files = {"manifest.json": file_sha(folder / "manifest.json")}
    for i, path in enumerate(sorted((folder / "checkpoints").glob("*.json"))):
        entry = verified(path)
        if (
            path.name != f"{i:04}.json"
            or entry["sequence"] != i
            or entry["previous_sha256"] != previous
        ):
            raise ValueError("Control checkpoint chain changed")
        operation = (entry["name"], entry["kind"])
        if entry["type"] == "intent" and pending is None:
            pending = operation
        elif entry["type"] == "commit" and pending == operation:
            pending = None
        else:
            raise ValueError("Control checkpoint transition changed")
        previous = entry["sha256"]
        files[str(path.relative_to(folder))] = file_sha(path)
    if pending or len(files) < 3 or previous != envelope["checkpoint_sha256"]:
        raise ValueError("Control result checkpoint binding changed")
    return {
        "status": result["status"],
        "reason": result.get("failure"),
        "unsupported_reason": result["configuration"]["unsupported_reason"],
        "result_file_sha256": file_sha(folder / "result.json"),
        "result_sha256": result["sha256"],
        "nomination_slots": result["selection"]["nominations"],
        "nomination_freeze_sha256": result["nomination_freeze"]["sha256"],
        "accounting": result["host_submission"]["accounting"],
        "candidate_count": len(result["host_submission"]["candidates"]),
        "failed_fit_count": len(result["host_submission"]["failures"]),
        "rejection_count": len(result["rejections"]),
        "conformance": result["conformance"],
        "journal_files_sha256": sha(files),
    }


def read_outcome(root, m, job):
    value = verified(root / "outcomes" / (job["assignment_id"] + ".json"))
    if any(value.get(k) != job[k] for k in ("assignment_id", "scenario_id", "control", "run_id")):
        raise ValueError("Outcome identity changed")
    if len(value["nomination_slots"]) != 3:
        raise ValueError("Outcome nomination denominator changed")
    if value.get("result_file_sha256"):
        folder = Path(m["workspace"]) / "control-runs" / job["run_id"]
        actual = result_record(folder, job)
        if any(value.get(k) != v for k, v in actual.items()):
            raise ValueError("Sealed control result changed")
    return value


def run_one(root, m, job):
    target = root / "outcomes" / (job["assignment_id"] + ".json")
    if target.exists():
        return read_outcome(root, m, job)
    folder = Path(m["workspace"]) / "control-runs" / job["run_id"]
    state = control_jobs.launch(folder)
    value = {k: job[k] for k in ("assignment_id", "scenario_id", "control", "run_id")}
    value.update(
        {
            "status": "execution_unresolved",
            "reason": state,
            "nomination_slots": [
                {"slot": i, "candidate_id": None, "status": "unfilled"} for i in (1, 2, 3)
            ],
            "api_calls": 0,
            "ranking_authorized": False,
            "assessment": "not_assessed",
        }
    )
    if (folder / "result.json").exists():
        value.update(result_record(folder, job))
    elif state.get("status") in {"cancelled", "recovery_required"}:
        value["status"] = state["status"]
    if len(value["nomination_slots"]) != 3:
        raise ValueError("Fixed nomination denominator changed")
    return record(target, value)


def verify_completion(root, m=None):
    root = Path(root)
    m = check(root) if m is None else m
    completion, freeze = (
        verified(root / "completion.json"),
        verified(root / "submission-freeze.json"),
    )
    outcomes = [read_outcome(root, m, j) for j in m["jobs"]]
    expected = {o["assignment_id"]: o["sha256"] for o in outcomes}
    if (
        set(p.stem for p in (root / "outcomes").glob("*.json")) != set(expected)
        or freeze["outcomes"] != expected
        or freeze["manifest_sha256"] != m["sha256"]
        or completion["submission_freeze_sha256"] != freeze["sha256"]
        or completion["assigned"] != m["assigned"]
        or completion["fixed_nomination_slots"] != sum(len(o["nomination_slots"]) for o in outcomes)
        or completion["statuses"] != dict(Counter(o["status"] for o in outcomes))
        or completion["nominated_slots"]
        != sum(bool(s["candidate_id"]) for o in outcomes for s in o["nomination_slots"])
    ):
        raise ValueError("Control cohort freeze or completion changed")
    return completion


def drive(root):
    root = Path(root)
    with (root / "driver.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        m = check(root)
        if (root / "completion.json").exists():
            return verify_completion(root, m)
        started = now()
        write_json(root / "driver-status.json", {"phase": "development_controls", "at": started})
        with ThreadPoolExecutor(max_workers=m["workers"]) as pool:
            outcomes = list(pool.map(lambda j: run_one(root, m, j), m["jobs"]))
        check(root)
        expected = {o["assignment_id"]: o["sha256"] for o in outcomes}
        if not (root / "submission-freeze.json").exists():
            record(
                root / "submission-freeze.json",
                {
                    "manifest_sha256": m["sha256"],
                    "outcomes": expected,
                    "at": now(),
                    "assigned": m["assigned"],
                    "fixed_nomination_slots": m["fixed_nomination_slots"],
                    "ranking_authorized": False,
                },
            )
        freeze = verified(root / "submission-freeze.json")
        if freeze["outcomes"] != expected or freeze["manifest_sha256"] != m["sha256"]:
            raise ValueError("Existing submission freeze differs")
        record(
            root / "completion.json",
            {
                "campaign_id": m["campaign_id"],
                "started_at": started,
                "finished_at": now(),
                "assigned": m["assigned"],
                "statuses": dict(Counter(o["status"] for o in outcomes)),
                "fixed_nomination_slots": m["fixed_nomination_slots"],
                "nominated_slots": sum(
                    bool(s["candidate_id"]) for o in outcomes for s in o["nomination_slots"]
                ),
                "submission_freeze_sha256": freeze["sha256"],
                "api_calls": 0,
                "assessment": "not_assessed",
                "ranking_authorized": False,
            },
        )
        receipt = verify_completion(root, m)
        write_json(root / "driver-status.json", {"phase": "execution_finished", "at": now()})
        return receipt


def launch(root):
    root = Path(root).resolve()
    with (root / "launcher.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        m = check(root)
        if (root / "completion.json").exists():
            verify_completion(root, m)
            return {"status": "already_finished"}
        pid = read_json(root / "driver.pid")["pid"] if (root / "driver.pid").exists() else None
        if alive(pid):
            return {"status": "already_running", "pid": pid}
        bootstrap = "import sys;sys.path.insert(0,sys.argv[1]);from principia_asd.control_pilot import drive;drive(sys.argv[2])"
        args = [m["driver_python"], "-I", "-B", "-c", bootstrap, m["runtime_source"], str(root)]
        env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}
        with (root / "driver.log").open("ab") as log:
            proc = subprocess.Popen(
                args,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                cwd=root,
                env=env,
                start_new_session=True,
            )
        write_json(root / "driver.pid", {"pid": proc.pid, "started_at": now()})
        return {"status": "started", "pid": proc.pid}


def summary(root):
    root = Path(root)
    m = verified(root / "manifest.json")
    outcomes = [
        read_outcome(root, m, j)
        for j in m["jobs"]
        if (root / "outcomes" / (j["assignment_id"] + ".json")).exists()
    ]
    phase = read_json(root / "driver-status.json")
    pid = read_json(root / "driver.pid")["pid"] if (root / "driver.pid").exists() else None
    return {
        "campaign_id": m["campaign_id"],
        "phase": phase["phase"],
        "driver_alive": alive(pid),
        "assigned": m["assigned"],
        "terminal_records": len(outcomes),
        "statuses": dict(Counter(o["status"] for o in outcomes)),
        "fixed_nomination_slots": m["fixed_nomination_slots"],
        "nominated_slots": sum(
            bool(s["candidate_id"]) for o in outcomes for s in o["nomination_slots"]
        ),
        "fitting_attempts": sum(
            o.get("accounting", {}).get("fitting_attempts", 0) for o in outcomes
        ),
        "optimizer_evaluations": sum(
            o.get("accounting", {}).get("optimizer_evaluations", 0) for o in outcomes
        ),
        "accounting_unavailable_assignments": [
            o["assignment_id"] for o in outcomes if "accounting" not in o
        ],
        "active_workers": [
            j["run_id"]
            for j in m["jobs"]
            if (Path(m["workspace"]) / "control-runs" / j["run_id"] / "process.json").exists()
            and alive(
                read_json(Path(m["workspace"]) / "control-runs" / j["run_id"] / "process.json")[
                    "pid"
                ]
            )
        ],
        "submission_freeze": (root / "submission-freeze.json").exists(),
        "api_calls": 0,
        "accounted_cny": 0,
        "ranking_authorized": False,
        "assessment": "not_assessed",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "launch", "drive", "status", "verify"])
    parser.add_argument("path", type=Path)
    parser.add_argument("--campaign-id")
    parser.add_argument("--project-root", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        if not args.campaign_id or not args.project_root:
            parser.error("Preparation requires a campaign ID and project root")
        root, m = prepare(read_json(args.path), args.campaign_id, project_root=args.project_root)
        value = {"path": str(root), "manifest_sha256": m["sha256"]}
    else:
        value = {"launch": launch, "drive": drive, "status": summary, "verify": verify_completion}[
            args.command
        ](args.path)
    print(json.dumps(value, indent=2))


if __name__ == "__main__":
    main()
