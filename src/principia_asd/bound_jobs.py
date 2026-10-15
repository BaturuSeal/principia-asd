"""Interactive development jobs for the explicit-state engine, separate from v5."""

from __future__ import annotations

import fcntl
import os
import subprocess
import sys
import uuid
from pathlib import Path

from .io import file_sha, read_json, sha, write_json
from .methods.registry import DEFAULT_ROLES
from .runtime import now
from .store.snapshot import runtime_snapshot

METHOD_ID = "principia_engine_explicit"
PROTOCOLS = (
    {
        "id": "v2",
        "label": "v2 · explicit role contracts (recommended)",
        "description": "Exact role schemas and compact evidence context. All six supported engineering-pilot cases completed; two wider-input cases remain unsupported. This is development evidence, not a scientific ranking.",
    },
    {
        "id": "v1",
        "label": "v1 · original development protocol",
        "description": "Original prompts and full evidence context, retained for reproduction. Its pilot recorded one complete, four incomplete, one failed and two unsupported assignments.",
    },
)


def prepare(
    settings, scenario, sid, roles=None, budget=12, objective="", *, campaign_id=None, protocol="v1"
):
    if not isinstance(protocol, str) or protocol not in {"v1", "v2"}:
        raise ValueError("Unknown explicit-state protocol revision")
    workspace, scenario = Path(settings["workspace"]), Path(scenario)
    task = read_json(scenario / "task-contracts/task-001.json")
    if not 1 <= len(task["inputs"]) <= 8:
        raise ValueError(
            "Explicit-state development supports 1–8 numeric inputs; no columns are silently omitted"
        )
    if not 0 < budget <= 12:
        raise ValueError("Explicit-state development budget must be between 0 and 12 CNY")
    # Validate custody before creating a job or taking a runtime snapshot.
    workspace = workspace.resolve()
    scenario = scenario.resolve()
    if not (
        scenario.is_relative_to(Path(settings["data_root"]).resolve())
        or scenario.is_relative_to(workspace / "imports")
    ):
        raise ValueError("Scenario is outside the configured data edition or local imports")
    for key in ("data_root", "leaderboard_root", "project_root"):
        if settings.get(key) and workspace.is_relative_to(Path(settings[key]).resolve()):
            raise ValueError("Mutable worker workspace must stay outside upload roots")
    folder = workspace / "bound-runs" / ("bound-" + uuid.uuid4().hex[:16])
    folder.mkdir(parents=True)
    write_json(
        folder / "request.json",
        {
            "scope": "engineering_only_explicit_state_" + protocol,
            "run_id": folder.name,
            "scenario_path": str(scenario.resolve()),
            "roles": roles or DEFAULT_ROLES,
            "limits": {
                "max_calls": 7,
                "max_fits": 16,
                "max_structures": 8000,
                "max_optimizer_evaluations": 4096,
                "max_seconds": 2400,
            },
            "attempt_cap_cny": budget,
        },
        immutable=True,
    )
    write_json(
        folder / "ui.json",
        {
            "scenario_id": sid,
            "method_id": METHOD_ID,
            "created_at": now(),
            "objective": str(objective)[:2000],
            "mode": "engineering",
            "development_campaign": campaign_id,
            "protocol_revision": protocol,
            "objective_scope": "Personal note; scientific task and protocol remain fixed",
        },
        immutable=True,
    )
    write_json(folder / "settings.json", settings, immutable=True)
    source = runtime_snapshot(workspace)
    launch = {
        "runtime_source": str(source),
        "interpreter": sys.executable,
        "runtime_binding_sha256": file_sha(source.parent / "binding.json"),
        "settings_sha256": file_sha(folder / "settings.json"),
        "request_sha256": file_sha(folder / "request.json"),
    }
    launch["sha256"] = sha(launch)
    write_json(folder / "launch.json", launch, immutable=True)
    write_json(folder / "state.json", {"status": "queued", "created_at": now()})
    return folder


def alive(folder):
    path = folder / "process.json"
    if not path.exists():
        return False
    try:
        os.kill(int(read_json(path)["pid"]), 0)
        return True
    except (ProcessLookupError, ValueError, KeyError):
        return False


def recovery(folder, ledger):
    """A UI eligibility hint; the worker revalidates the entire frozen chain."""
    if (folder / "result.json").exists() or (folder / "cancel.requested").exists():
        return False, "This run is terminal or was cancelled; it will not be restarted."
    files = sorted((folder / "checkpoints").glob("*.json"))
    if not files:
        return True, "No scientific operation has been checkpointed."
    last = read_json(files[-1])
    if last["type"] == "commit":
        return True, "Continue from the last committed operation with the frozen runtime."
    if last["kind"] != "provider":
        return (
            False,
            "A local operation was interrupted. Its unrecorded numerical work is unknown; automatic refitting is blocked.",
        )
    scope = read_json(folder / "request.json")["scope"]
    protocol = scope.removeprefix("engineering_only_explicit_state_")
    if scope == "engineering_only_laboratory_explicit_v1":
        from .engine.bound_laboratory import ROLES, STAGES

        if last["name"] not in STAGES:
            return False, "Unknown Laboratory handoff; do not dispatch."
        role = ROLES[STAGES.index(last["name"])]
        tag = "laboratory-bound-v1"
    elif scope in {
        "engineering_only_data_to_paper_explicit_v1",
        "engineering_only_data_to_paper_explicit_v2",
    }:
        from .engine.bound_data_to_paper import ROLES

        if last["name"] not in ROLES:
            return False, "Unknown data-to-paper handoff; do not dispatch."
        role = ROLES[last["name"]]
        tag = "paper-bound-" + scope.rsplit("_", 1)[1]
    elif scope == "engineering_only_asta_explicit_v1":
        from .asta_jobs import HANDOFF_ROLES

        role = HANDOFF_ROLES.get(last["name"])
        if role is None:
            return False, "Unknown Asta handoff; do not dispatch."
        tag = "asta-bound-v1"
    elif protocol in {"v1", "v2"}:
        role = {"plan": "planner", "code": "coder", "critic": "critic", "report": "reporter"}.get(
            last["name"].split("-")[0]
        )
        if role is None:
            return False, "Unknown engine handoff; do not dispatch."
        tag = "bound-" + protocol
    else:
        return False, "Unknown frozen protocol; do not dispatch."
    rid = f"{folder.name}--{tag}--{role}--{last['state']['engine']['requests'] + 1}"
    prior = ledger.get(rid)
    if (
        prior
        and prior["state"] == "completed"
        and (folder / "provider" / (sha(rid) + ".json")).exists()
    ):
        return (
            True,
            "A settled response is available. Recovery verifies its hash and does not resend that request.",
        )
    return (
        False,
        "The interrupted provider call has no verified settled response. Its reservation is retained and automatic replay is blocked.",
    )


def view(folder, ledger, details=True, *, scheduled=False):
    meta = read_json(folder / "ui.json")
    state = (
        read_json(folder / "state.json")
        if (folder / "state.json").exists()
        else {"status": "queued"}
    )
    value = {
        "run_id": folder.name,
        **meta,
        **state,
        "ranking_authorized": False,
        "assessment_status": "not_assessed",
        "resume_available": False,
    }
    running = alive(folder)
    managed = bool(meta.get("development_campaign"))
    scheduled = scheduled or (managed and value["status"] == "queued")
    if not running and not scheduled and value["status"] in {"running", "cancelling", "queued"}:
        value.update(
            status="interrupted", reason="The worker stopped before writing its terminal record."
        )
    if not running and value["status"] in {"interrupted", "recovery_required"}:
        value["resume_available"], value["recovery_reason"] = recovery(folder, ledger)
    if managed:
        value.update(
            resume_available=False,
            recovery_reason="This run belongs to a frozen development cohort; recovery is managed by its driver.",
        )
    if (folder / "progress.json").exists():
        value["progress"] = read_json(folder / "progress.json")
    if details:
        checkpoints = sorted((folder / "checkpoints").glob("*.json"))
        if checkpoints:
            saved = read_json(checkpoints[-1])["state"]["host"]
            value["accounting"] = {k: saved[k] for k in ["fits", "optimizer_evaluations"]}
            value["accounting"]["fitting_attempts"] = value["accounting"].pop("fits")
        value["events"] = []
        if (folder / "events.jsonl").exists():
            for line in (folder / "events.jsonl").read_text().splitlines()[-200:]:
                try:
                    value["events"].append(__import__("json").loads(line))
                except ValueError:
                    pass  # A writer's final partial line is not a scientific receipt.
        if (folder / "result.json").exists():
            result = read_json(folder / "result.json")["result"]
            if result["sha256"] != sha({k: v for k, v in result.items() if k != "sha256"}):
                raise ValueError("Frozen explicit-state result changed")
            value["status"] = (
                "cancelled"
                if (result.get("failure") or {}).get("type") == "InterruptedError"
                else result["status"]
            )
            value["reason"] = (result.get("failure") or {}).get("reason")
            value["bound_result"] = result
            candidates = {c["candidate_id"]: c for c in result["host_submission"]["candidates"]}
            value["rules"] = [
                candidates[n["candidate_id"]]
                | {
                    "rule_id": n["candidate_id"],
                    "method_id": meta["method_id"],
                    "parameters": candidates[n["candidate_id"]]["program"]["specification"][
                        "parameters"
                    ],
                    "model_ids": list(result["configuration"]["roles"].values()),
                }
                for n in result["selection"]["nominations"]
                if n["candidate_id"]
            ]
            value["accounting"] = result["host_submission"]["accounting"] | {
                "model_calls": result["model_requests"]
            }
            value["resume_available"] = False
    return value


def launch(folder):
    """Use the original copied runtime on first launch and recovery alike."""
    folder = Path(folder)
    with (folder / "launch.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Another launcher already owns this development run") from exc
        from . import adapter_jobs

        scope = read_json(folder / "request.json").get("scope")
        adapter = next(
            (name for name, spec in adapter_jobs.SPECS.items() if spec["scope"] == scope), None
        )
        if adapter is None and scope not in {
            "engineering_only_explicit_state_v1",
            "engineering_only_explicit_state_v2",
        }:
            raise ValueError("Unknown frozen protocol; no worker fallback")
        if adapter:
            from .adapter_jobs import verify_binding, verify_finished

            config, _, _ = verify_binding(folder, adapter=adapter, check_environment=True)
            if (folder / "result.json").exists():
                verify_finished(folder, config)
                return
            if alive(folder):
                raise ValueError("Previous worker is still alive; no duplicate launched")
        if (folder / "cancel.requested").exists() or (folder / "result.json").exists():
            return
        config = read_json(folder / "launch.json")
        source = Path(config["runtime_source"])
        if (
            config["sha256"] != sha({k: v for k, v in config.items() if k != "sha256"})
            or file_sha(source.parent / "binding.json") != config["runtime_binding_sha256"]
            or file_sha(folder / "settings.json") != config["settings_sha256"]
            or file_sha(folder / "request.json") != config["request_sha256"]
        ):
            raise ValueError("Frozen launch configuration changed")
        for path, digest in read_json(source.parent / "binding.json")["files"].items():
            if file_sha(source / "principia_asd" / path) != digest:
                raise ValueError("Copied worker runtime changed")
        env = {
            k: v
            for k, v in os.environ.items()
            if not any(w in k.upper() for w in ["API_KEY", "TOKEN", "SECRET"])
        }
        env.update(PYTHONPATH=str(source), PYTHONDONTWRITEBYTECODE="1")
        for key in [
            "OPENBLAS_NUM_THREADS",
            "MKL_NUM_THREADS",
            "OMP_NUM_THREADS",
            "VECLIB_MAXIMUM_THREADS",
        ]:
            env[key] = "1"
        args = [
            config["interpreter"],
            "-B",
            "-m",
            "principia_asd.engine.bound_worker",
            "--folder",
            str(folder),
            "--settings",
            str(folder / "settings.json"),
        ]
        if adapter:
            # Ignore injected PYTHONPATH/startup hooks; use only the copied source
            # and the originally prepared interpreter's installed dependencies.
            env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}
            for key in (
                "OPENBLAS_NUM_THREADS",
                "OMP_NUM_THREADS",
                "MKL_NUM_THREADS",
                "VECLIB_MAXIMUM_THREADS",
                "NUMEXPR_NUM_THREADS",
                "BLIS_NUM_THREADS",
            ):
                env[key] = "1"
            args = [
                config["interpreter"],
                "-I",
                "-B",
                "-c",
                "import sys;sys.path.insert(0,sys.argv[1]);from "
                + adapter_jobs.specification(adapter)["worker_module"]
                + " import execute_worker;execute_worker(sys.argv[2])",
                str(source),
                str(folder),
            ]
        with (folder / "worker.log").open("ab") as log:
            write_json(folder / "state.json", {"status": "running"})
            proc = subprocess.Popen(args, stdout=log, stderr=log, env=env, start_new_session=True)
            write_json(folder / "process.json", {"pid": proc.pid, "started_at": now()})
            try:
                code = proc.wait(timeout=2600)
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    code = proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    code = proc.wait()
            if code and not (folder / "result.json").exists():
                state = read_json(folder / "state.json")
                if (folder / "cancel.requested").exists():
                    write_json(
                        folder / "state.json",
                        {
                            "status": "cancelled",
                            "reason": "Worker stopped after cancellation; all paid-call reservations and checkpoints are retained.",
                            "finished_at": now(),
                        },
                    )
                elif state.get("status") != "recovery_required":
                    write_json(
                        folder / "state.json",
                        {
                            "status": "interrupted",
                            "reason": "Worker stopped; inspect the recovery status and retained log.",
                            "finished_at": now(),
                        },
                    )
