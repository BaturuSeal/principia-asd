"""Frozen development-only cohorts for the explicit-state Engine.

Uses the existing ledger and dedicated workers. No evaluator or leaderboard
export is imported. Unsupported and unresolved assignments keep three slots.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import bound_jobs
from .adapter_jobs import PROTOCOL_ADAPTERS
from .io import contained, file_sha, read_json, sha, write_json
from .llm.siliconflow import PRICE_SOURCE, PROFILES, SiliconFlowClient
from .methods.registry import DEFAULT_ROLES
from .runtime import now
from .store.ledger import CostLedger
from .store.snapshot import runtime_snapshot

CASES = tuple(f"P100-{i:03d}" for i in (2, 17, 43, 51, 54, 68, 87, 90))
POLICY = "explicit-state-engineering-pilot-v1"


def record(path, value):
    value = dict(value)
    value["sha256"] = sha(value)
    write_json(path, value, immutable=True)
    return value


def verified(path):
    value = read_json(path)
    if value.get("sha256") != sha({k: v for k, v in value.items() if k != "sha256"}):
        raise ValueError("Immutable pilot record changed: " + path.name)
    return value


def prepare(settings, campaign_id, price_check, *, protocol="v1"):
    if protocol not in {"v1", "v2", "laboratory-v1", "paper-v1", "paper-v2"}:
        raise ValueError("Unknown explicit-state pilot protocol")
    if not campaign_id or not all(c.isalnum() or c in "-_" for c in campaign_id):
        raise ValueError("Invalid development cohort identity")
    workspace = Path(settings["workspace"]).resolve()
    root = workspace / "development-campaigns" / campaign_id
    # A partly prepared directory must be inspected, never silently overwritten.
    root.mkdir(parents=True, exist_ok=False)
    caps_path = workspace / "capabilities.json"
    caps = read_json(caps_path)
    if any(
        caps.get(model, {}).get("state") != "verified" or caps[model].get("generation") != profile
        for model, profile in PROFILES.items()
    ):
        raise ValueError("Existing exact provider profiles are not verified")
    if price_check.get("rates") != {
        m: {k: p[k] for k in ("input_rate", "output_rate")} for m, p in PROFILES.items()
    }:
        raise ValueError("Dated price verification does not match provider rates")
    source = runtime_snapshot(workspace)
    private_settings = {
        "workspace": str(workspace),
        "data_root": str(root / "data"),
        "leaderboard_root": settings["leaderboard_root"],
        "env_file": settings.get("env_file"),
    }
    write_json(root / "settings.json", private_settings, immutable=True)
    write_json(root / "capabilities.json", caps, immutable=True)
    jobs, frozen_files = [], {}
    for sid in CASES:
        original = Path(settings["data_root"]) / "scenarios" / sid
        task = read_json(original / "task-contracts/task-001.json")
        if task["scenario_id"] != sid:
            raise ValueError("Scenario identity mismatch")
        staged = root / "data/scenarios" / sid
        paths = ["task-contracts/task-001.json", task["split"]["train"], task["split"]["dev"]]
        for relative in paths:
            src, dest = contained(original, relative), contained(staged, relative)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            if file_sha(src) != file_sha(dest):
                raise ValueError("Input copy changed")
            frozen_files[str(dest.relative_to(root))] = file_sha(dest)
        supported = 1 <= len(task["inputs"]) <= 8
        job = {
            "scenario_id": sid,
            "task_id": task["task_id"],
            "input_count": len(task["inputs"]),
            "supported": supported,
            "run_id": None,
            "nomination_slots": 3,
            "exposure": "previously engineering-exposed; retrospective development only",
        }
        if supported:
            if protocol == "laboratory-v1":
                from .laboratory_jobs import prepare as prepare_laboratory

                run = prepare_laboratory(settings, original, campaign_id=campaign_id)
            elif protocol == "paper-v2":
                from .paper_v2_jobs import prepare as prepare_paper_v2

                run = prepare_paper_v2(settings, original, campaign_id=campaign_id)
            elif protocol == "paper-v1":
                from .paper_jobs import prepare as prepare_paper

                run = prepare_paper(settings, original, campaign_id=campaign_id)
            else:
                run = bound_jobs.prepare(
                    private_settings, staged, sid, campaign_id=campaign_id, protocol=protocol
                )
            job.update(
                run_id=run.name,
                launch_sha256=file_sha(run / "launch.json"),
                request_sha256=file_sha(run / "request.json"),
                ui_sha256=file_sha(run / "ui.json"),
            )
        jobs.append(job)
    manifest = record(
        root / "manifest.json",
        {
            "policy": {
                "v1": POLICY,
                "v2": "explicit-state-engineering-pilot-v2",
                "laboratory-v1": "explicit-state-laboratory-pilot-v1",
                "paper-v1": "explicit-state-data-to-paper-pilot-v1",
                "paper-v2": "explicit-state-data-to-paper-pilot-v2",
            }[protocol],
            "protocol_revision": protocol,
            "campaign_id": campaign_id,
            "created_at": now(),
            "scope": "engineering_only_train_dev_no_final_assessment",
            "workspace": str(workspace),
            "jobs": jobs,
            "assigned": len(CASES),
            "fixed_nomination_slots": 3 * len(CASES),
            "runtime_source": str(source),
            "runtime_binding_sha256": file_sha(source.parent / "binding.json"),
            "settings_sha256": file_sha(root / "settings.json"),
            "capabilities_sha256": file_sha(root / "capabilities.json"),
            "global_capabilities_sha256": file_sha(caps_path),
            "inputs": frozen_files,
            "roles": DEFAULT_ROLES,
            "profiles": PROFILES,
            "price_source": PRICE_SOURCE,
            "price_rechecked": price_check,
            "workers": 4,
            "attempt_cap_cny": 12,
            "probe_cap_cny": 8,
            "maximum_additional_cny": 12 * sum(j["supported"] for j in jobs) + 8,
            "global_cap_cny": 3000,
            "selection": "six Laboratory handoffs, two experiments, three fixed slots"
            if protocol == "laboratory-v1"
            else "guarded statistical analysis, conditional repairs, traced report and three fixed slots"
            if protocol in {"paper-v1", "paper-v2"}
            else "unchanged two-round development protocol and three fixed slots",
            "retry_policy": "No automatic replay of ambiguous calls or sealed attempts",
            "ranking_authorized": False,
            "scientific_review": "not_assessed",
        },
    )
    write_json(root / "driver-status.json", {"phase": "prepared", "at": now()})
    return root, manifest


def check(root):
    root = Path(root)
    m = verified(root / "manifest.json")
    workspace, source = Path(m["workspace"]), Path(m["runtime_source"])
    for path, digest in [
        (root / "settings.json", m["settings_sha256"]),
        (root / "capabilities.json", m["capabilities_sha256"]),
        (workspace / "capabilities.json", m["global_capabilities_sha256"]),
        (source.parent / "binding.json", m["runtime_binding_sha256"]),
        *[(contained(root, p), h) for p, h in m["inputs"].items()],
    ]:
        if file_sha(path) != digest:
            raise ValueError("Frozen pilot context changed: " + path.name)
    for p, h in read_json(source.parent / "binding.json")["files"].items():
        if file_sha(source / "principia_asd" / p) != h:
            raise ValueError("Copied pilot runtime changed")
    for job in m["jobs"]:
        if job["run_id"]:
            run = workspace / "bound-runs" / job["run_id"]
            if m["protocol_revision"] in {"laboratory-v1", "paper-v1", "paper-v2"}:
                from .adapter_jobs import verify_binding

                verify_binding(
                    run, adapter=PROTOCOL_ADAPTERS[m["protocol_revision"]], check_environment=True
                )
            for name in ("request", "launch", "ui"):
                if file_sha(run / (name + ".json")) != job[name + "_sha256"]:
                    raise ValueError("Frozen pilot job changed")
            if read_json(run / "launch.json")["runtime_source"] != str(source):
                raise ValueError("Run uses another runtime")
    return m


def probe(root, m):
    settings = read_json(root / "settings.json")
    ledger = CostLedger(Path(m["workspace"]) / "costs.sqlite")
    gateway = SiliconFlowClient(
        env_file=settings.get("env_file"),
        ledger=ledger,
        artifact_dir=root / "probes/provider",
        attempt_cap_cny=m["probe_cap_cny"],
        capabilities=read_json(root / "capabilities.json"),
    )

    def one(model):
        path = root / "probes" / (sha(model) + ".json")
        if path.exists():
            return verified(path)
        rid = m["campaign_id"] + "--probe--" + model
        try:
            # A prior entry can only be recovered: this branch cannot dispatch.
            method = gateway.recover_completed if ledger.get(rid) else gateway.complete
            response = method(
                model=model,
                system="Return JSON only.",
                prompt='Return {"ok":true,"scope":"explicit-state development capability probe"}.',
                max_tokens=1800,
                temperature=0.25,
                request_id=rid,
            )
            body = json.loads(response["text"])
            if body.get("ok") is not True:
                raise ValueError("Exact JSON capability not confirmed")
            value = {
                "state": "verified",
                "model": model,
                "request_id": rid,
                "response_sha256": sha(response),
                "generation": PROFILES[model],
            }
        except Exception as exc:
            value = {
                "state": "unavailable",
                "model": model,
                "request_id": rid,
                "reason": type(exc).__name__ + ": " + str(exc)[:300],
            }
        return record(path, value)

    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(one, m["profiles"]))
    return all(r["state"] == "verified" for r in rows)


def run_one(root, m, job):
    target = root / "outcomes" / (job["scenario_id"] + ".json")
    if target.exists():
        value = verified(target)
        if value.get("result_file_sha256"):
            run = Path(m["workspace"]) / "bound-runs" / job["run_id"]
            if file_sha(run / "result.json") != value["result_file_sha256"]:
                raise ValueError("Sealed worker result changed")
            if m["protocol_revision"] in {"laboratory-v1", "paper-v1", "paper-v2"}:
                from .adapter_jobs import verify_binding, verify_finished

                config, _, _ = verify_binding(
                    run, adapter=PROTOCOL_ADAPTERS[m["protocol_revision"]]
                )
                verify_finished(run, config)
        return value
    value = {
        "scenario_id": job["scenario_id"],
        "run_id": job["run_id"],
        "status": "unsupported",
        "reason": "Development protocol supports one to eight inputs",
        "nomination_slots": [
            {"slot": i + 1, "candidate_id": None, "status": "unfilled"} for i in range(3)
        ],
        "ranking_authorized": False,
        "assessment": "not_assessed",
    }
    if job["run_id"]:
        run = Path(m["workspace"]) / "bound-runs" / job["run_id"]
        if (run / "cancel.requested").exists() and not (run / "result.json").exists():
            value.update(status="cancelled", reason="Cancelled before a result was frozen")
            return record(target, value)
        if not (run / "result.json").exists():
            if bound_jobs.alive(run):
                raise RuntimeError("An assigned worker is still alive; no duplicate dispatch")
            ledger = CostLedger(Path(m["workspace"]) / "costs.sqlite")
            allowed, reason = bound_jobs.recovery(run, ledger)
            if allowed:
                bound_jobs.launch(run)
            else:
                value.update(status="recovery_required", reason=reason)
        if (run / "result.json").exists():
            result = read_json(run / "result.json")["result"]
            if result["sha256"] != sha({k: v for k, v in result.items() if k != "sha256"}):
                raise ValueError("Frozen worker result changed")
            value.update(
                status=result["status"],
                reason=result.get("failure"),
                result_file_sha256=file_sha(run / "result.json"),
                result_sha256=result["sha256"],
                nomination_slots=result["selection"]["nominations"],
                nomination_freeze_sha256=result["nomination_freeze"]["sha256"],
                conformance=result["conformance"],
                model_requests=result["model_requests"],
                accounting=result["host_submission"]["accounting"],
                candidate_count=len(result["host_submission"]["candidates"]),
            )
            if m["protocol_revision"] in {"paper-v1", "paper-v2"}:
                value["statistical_accounting"] = result["statistical_accounting"]
                value["computed_facts_sha256"] = (result.get("computed_facts") or {}).get("sha256")
        elif value["status"] != "recovery_required":
            state = read_json(run / "state.json") if (run / "state.json").exists() else {}
            value.update(status="execution_unresolved", reason=state)
    if len(value["nomination_slots"]) != job["nomination_slots"]:
        raise ValueError("Fixed nomination denominator changed")
    return record(target, value)


def verify_completion(root, m):
    receipt = verified(root / "completion.json")
    frozen = verified(root / "submission-freeze.json")
    if (
        receipt["submission_freeze_sha256"] != frozen["sha256"]
        or frozen["manifest_sha256"] != m["sha256"]
    ):
        raise ValueError("Completion freeze binding changed")
    outcomes = []
    for job in m["jobs"]:
        path = root / "outcomes" / (job["scenario_id"] + ".json")
        value = verified(path)
        if value["sha256"] != frozen["outcomes"].get(job["scenario_id"]):
            raise ValueError("Completed outcome changed")
        outcomes.append(run_one(root, m, job))
    if sum(len(o["nomination_slots"]) for o in outcomes) != m["fixed_nomination_slots"]:
        raise ValueError("Completed nomination denominator changed")
    return receipt


def drive(root):
    root = Path(root)
    with (root / "driver.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        m = check(root)
        if (root / "completion.json").exists():
            return verify_completion(root, m)
        write_json(root / "driver-status.json", {"phase": "capability_probes", "at": now()})
        if not probe(root, m):
            write_json(root / "driver-status.json", {"phase": "blocked_capability", "at": now()})
            return {"phase": "blocked_capability"}
        check(root)
        write_json(root / "driver-status.json", {"phase": "development_runs", "at": now()})
        with ThreadPoolExecutor(max_workers=m["workers"]) as pool:
            outcomes = list(pool.map(lambda job: run_one(root, m, job), m["jobs"]))
        check(root)
        freeze = {
            "manifest_sha256": m["sha256"],
            "at": now(),
            "assigned": m["assigned"],
            "fixed_nomination_slots": m["fixed_nomination_slots"],
            "outcomes": {r["scenario_id"]: r["sha256"] for r in outcomes},
            "scope": m["scope"],
            "ranking_authorized": False,
        }
        if not (root / "submission-freeze.json").exists():
            record(root / "submission-freeze.json", freeze)
        frozen = verified(root / "submission-freeze.json")
        if frozen["outcomes"] != freeze["outcomes"] or frozen["manifest_sha256"] != m["sha256"]:
            raise ValueError("Submission freeze no longer matches outcomes")
        completion = record(
            root / "completion.json",
            {
                "campaign_id": m["campaign_id"],
                "at": now(),
                "assigned": len(outcomes),
                "statuses": dict(Counter(r["status"] for r in outcomes)),
                "fixed_nomination_slots": m["fixed_nomination_slots"],
                "nominated_slots": sum(
                    bool(s["candidate_id"]) for r in outcomes for s in r["nomination_slots"]
                ),
                "submission_freeze_sha256": frozen["sha256"],
                "assessment": "not_assessed",
                "ranking_authorized": False,
                "scope": "Execution receipts only; no test evaluation or scientific-success claim",
            },
        )
        write_json(root / "driver-status.json", {"phase": "execution_finished", "at": now()})
        return completion


def launch(root):
    root = Path(root)
    with (root / "launcher.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        m = check(root)
        if (root / "completion.json").exists():
            verify_completion(root, m)
            return {"status": "already_finished"}
        if (root / "driver.pid").exists():
            pid = read_json(root / "driver.pid")["pid"]
            try:
                os.kill(pid, 0)
                return {"status": "already_running", "pid": pid}
            except ProcessLookupError:
                pass
        env = {
            k: v
            for k, v in os.environ.items()
            if not any(s in k.upper() for s in ("API_KEY", "TOKEN", "SECRET"))
        }
        env.update(PYTHONPATH=m["runtime_source"], PYTHONDONTWRITEBYTECODE="1")
        for k in (
            "OPENBLAS_NUM_THREADS",
            "OMP_NUM_THREADS",
            "MKL_NUM_THREADS",
            "VECLIB_MAXIMUM_THREADS",
        ):
            env[k] = "1"
        interpreters = {
            read_json(Path(m["workspace"]) / "bound-runs" / j["run_id"] / "launch.json")[
                "interpreter"
            ]
            for j in m["jobs"]
            if j["run_id"]
        }
        if len(interpreters) != 1:
            raise ValueError("Pilot requires one frozen interpreter")
        args = [interpreters.pop(), "-B", "-m", "principia_asd.bound_pilot", "drive", str(root)]
        with (root / "driver.log").open("ab") as log:
            proc = subprocess.Popen(args, stdout=log, stderr=log, env=env, start_new_session=True)
        write_json(root / "driver.pid", {"pid": proc.pid, "started_at": now()})
        return {"status": "started", "pid": proc.pid}


def summary(root):
    root = Path(root)
    m = verified(root / "manifest.json")
    outcomes = [verified(p) for p in sorted((root / "outcomes").glob("*.json"))]
    phase = read_json(root / "driver-status.json")
    pid = read_json(root / "driver.pid")["pid"] if (root / "driver.pid").exists() else None
    try:
        os.kill(pid, 0)
        alive = True
    except (TypeError, ProcessLookupError):
        alive = False
    ledger = CostLedger(Path(m["workspace"]) / "costs.sqlite")
    run_ids = {j["run_id"] for j in m["jobs"] if j["run_id"]}
    with ledger.connect() as db:
        rows = [
            (state, cost)
            for rid, state, cost in db.execute(
                "SELECT request_id,state,COALESCE(actual_cny,reserved_cny) FROM requests"
            )
            if rid.startswith(m["campaign_id"] + "--probe--")
            or rid.split("--bound-v1--")[0] in run_ids
            or rid.split("--bound-v2--")[0] in run_ids
            or rid.split("--laboratory-bound-v1--")[0] in run_ids
            or rid.split("--paper-bound-v1--")[0] in run_ids
            or rid.split("--paper-bound-v2--")[0] in run_ids
        ]
    return {
        "campaign_id": m["campaign_id"],
        "phase": phase["phase"],
        "driver_alive": alive,
        "phase_started_at": phase["at"],
        "assigned": m["assigned"],
        "terminal_records": len(outcomes),
        "statuses": dict(Counter(o["status"] for o in outcomes)),
        "fixed_nomination_slots": m["fixed_nomination_slots"],
        "nominated_slots": sum(
            bool(s["candidate_id"]) for r in outcomes for s in r["nomination_slots"]
        ),
        "submission_freeze": (root / "submission-freeze.json").exists(),
        "assessment": "not_assessed",
        "ranking_authorized": False,
        "costs": {
            "accounted_cny": sum(cost for _, cost in rows),
            "requests": len(rows),
            "states": dict(Counter(state for state, _ in rows)),
            "pending_cny": sum(cost for state, cost in rows if state == "reserved"),
            "unknown_cny": sum(cost for state, cost in rows if state == "unknown"),
            "maximum_additional_cny": m["maximum_additional_cny"],
        },
        "active_workers": [
            j["run_id"]
            for j in m["jobs"]
            if j["run_id"] and bound_jobs.alive(Path(m["workspace"]) / "bound-runs" / j["run_id"])
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "launch", "drive", "status"])
    parser.add_argument("path", type=Path)
    parser.add_argument("--campaign-id")
    parser.add_argument("--price-check", type=Path)
    parser.add_argument(
        "--protocol", choices=["v1", "v2", "laboratory-v1", "paper-v1", "paper-v2"], default="v1"
    )
    args = parser.parse_args()
    if args.command == "prepare":
        if not args.campaign_id or not args.price_check:
            parser.error("Preparation requires a campaign ID and dated price verification")
        root, m = prepare(
            read_json(args.path),
            args.campaign_id,
            read_json(args.price_check),
            protocol=args.protocol,
        )
        result = {"path": str(root), "manifest_sha256": m["sha256"]}
    else:
        result = {"launch": launch, "drive": drive, "status": summary}[args.command](args.path)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
