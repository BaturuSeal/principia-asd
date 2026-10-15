"""Loopback-only application. Browser requests never receive credentials or vault paths."""

from __future__ import annotations

import fcntl
import json
import os
import secrets
import subprocess
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .. import __version__, bound_jobs, laboratory_jobs, paper_v2_jobs
from ..catalog.presentation import describe_scenario, describe_task
from ..catalog.reviews import known_advisories, task_advisories
from ..io import file_sha, read_csv, read_json, sha, write_csv, write_json
from ..methods.registry import DEFAULT_ROLES, METHODS, MODELS
from ..runtime import now
from ..store.ledger import CostLedger
from . import credentials, model_settings
from .rule_view import rule_view
from .tasks import create_task, resolve_task, task_entries


class App:
    def __init__(self, settings):
        self.settings = dict(settings)
        self.workspace = Path(settings["workspace"]).expanduser().resolve()
        self.settings["workspace"] = str(self.workspace)
        for key in ("data_root", "leaderboard_root", "project_root"):
            if settings.get(key):
                root = Path(settings[key]).expanduser().resolve()
                if self.workspace.is_relative_to(root) or root.is_relative_to(self.workspace):
                    raise ValueError(
                        "Keep the private workspace separate from code, data and shared results"
                    )
        self.workspace.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.workspace.chmod(0o700)
        self.runs = self.workspace / "runs"
        self.runs.mkdir(exist_ok=True)
        self.bound_runs = self.workspace / "bound-runs"
        self.bound_runs.mkdir(exist_ok=True)
        self.bound_pending = set()
        self.normal_pending = set()
        self.token = secrets.token_urlsafe(32)
        self.pool = ThreadPoolExecutor(max_workers=4)
        self.processes = {}
        self.lock = threading.RLock()
        self.server_lock = (self.workspace / "server.lock").open("a+")
        try:
            fcntl.flock(self.server_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError("An application already owns this workspace") from None
        self.ledger = CostLedger(self.workspace / "costs.sqlite")
        credentials.load_settings(self)
        write_json(self.workspace / "settings.json", self.settings)

    def scenario_paths(self):
        paths = {
            p.name: p
            for p in (Path(self.settings["data_root"]) / "scenarios").iterdir()
            if (p / "scenario.json").is_file()
        }
        for p in (self.workspace / "imports").glob("*"):
            if (p / "scenario.json").exists():
                info = read_json(p / "scenario.json")
                if not info.get("custom_task") and not info.get("presentation_staging"):
                    paths[p.name] = p
        return paths

    def catalog(self):
        result = []
        for sid, p in sorted(self.scenario_paths().items()):
            info = read_json(p / "scenario.json")
            tasks = [describe_task(read_json(f)) for _, f in task_entries(p, self.workspace)]
            if not tasks:
                continue
            task = tasks[0]
            result.append(
                {
                    "scenario_id": sid,
                    **describe_scenario(info, task),
                    "local_path": str(p.resolve()),
                    "tasks": tasks,
                    "domain": info.get("domain", "Local"),
                    "rows": info.get("rows", {}),
                    "size": info.get("size", {}),
                    "task": task,
                    "limitations": info.get("limitations", []),
                    "source": info.get("source", {}),
                    "publication_authorized": info.get("publication_authorized", False),
                    "review_advisories": task_advisories(task),
                }
            )
        return result

    def add_task(self, payload):
        sid = payload.get("scenario_id")
        paths = self.scenario_paths()
        if sid not in paths:
            raise ValueError("Select a registered or imported scenario")
        with self.lock:
            return create_task(paths[sid], self.workspace, payload)

    def presentations(self, cards, task):
        values = {}
        for card in cards:
            identity = card.get("rule_id", card.get("candidate_id"))
            try:
                values[identity] = rule_view(card, task)
            except (ValueError, KeyError, TypeError, SyntaxError, RecursionError):
                values[identity] = {
                    "name": "Executable rule · " + str(identity)[-12:],
                    "unavailable": "This program has no supported analytic rendering. Download its complete executable record.",
                }
        return values

    def capabilities(self):
        p = self.workspace / "capabilities.json"
        return read_json(p) if p.exists() else {}

    def config(self):
        methods = [m.as_dict() for m in METHODS.values()]
        if not self.settings.get("project_root"):
            for method in methods:
                if method["method_id"] in {laboratory_jobs.METHOD_ID, paper_v2_jobs.METHOD_ID}:
                    method.update(
                        available=False,
                        reason="Configure --project-root before using the explicit-state adapter worker",
                    )
        return {
            "version": __version__,
            "deployment": "local",
            "csrf": self.token,
            "methods": methods,
            "explicit_state_protocols": list(bound_jobs.PROTOCOLS),
            "models": list(model_settings.profiles(self)),
            "model_profiles": model_settings.profiles(self),
            "probe_reservations": {
                m: model_settings.probe_bound(p) for m, p in model_settings.profiles(self).items()
            },
            "model_aliases": dict(zip(["deepseek", "glm", "qwen", "kimi"], MODELS, strict=True)),
            "model_roles": {
                k: v if v in model_settings.profiles(self) else "" for k, v in DEFAULT_ROLES.items()
            },
            "capabilities": self.capabilities(),
            "costs": self.ledger.summary(),
            "workers": 4,
            "api_configured": credentials.status(self)["configured"],
            "credential_status": credentials.status(self),
            "provider_probe": credentials.probe_status(self),
            "release_status": "Release candidate — final acceptance open",
            "data_preparation_advisories": known_advisories(),
        }

    def run_path(self, id):
        if not id or not all(x.isalnum() or x in "-_" for x in id):
            raise ValueError("Invalid run identity")
        paths = [root / id for root in [self.runs, self.bound_runs] if (root / id).is_dir()]
        if len(paths) != 1:
            raise FileNotFoundError("Run does not exist or identity is ambiguous")
        return paths[0]

    def get_run(self, id, details=True):
        p = self.run_path(id)
        if p.parent == self.bound_runs:
            value = bound_jobs.view(p, self.ledger, details, scheduled=id in self.bound_pending)
            req = read_json(p / "request.json")
            task_file = (
                (Path(req["scenario_path"]) / "task-contracts/task-001.json")
                if req.get("scenario_path")
                else p / "inputs/contract.json"
            )
            if task_file.exists():
                task = read_json(task_file)
                value["task_id"] = task.get("task_id", value["scenario_id"] + ".development")
                value["scenario_id"] = task.get("parent_scenario_id", value["scenario_id"])
                if details:
                    value["rule_presentations"] = self.presentations(value.get("rules", []), task)
            return value
        req = read_json(p / "request.json")
        state = read_json(p / "state.json") if (p / "state.json").exists() else {"status": "queued"}
        value = {
            "run_id": id,
            "scenario_id": req["scenario_id"],
            "method_id": req["method_id"],
            "created_at": req["created_at"],
            "task_id": req.get("task_id"),
            "objective": req.get("objective", ""),
            "mode": req.get("mode", "interactive"),
            **state,
        }
        value["scenario_id"] = req["scenario_id"]
        if (p / "progress.json").exists():
            value["progress"] = read_json(p / "progress.json")
        if details:
            value["events"] = (
                [json.loads(x) for x in (p / "events.jsonl").read_text().splitlines()[-200:]]
                if (p / "events.jsonl").exists()
                else []
            )
            if (p / "submission.json").exists():
                sub = read_json(p / "submission.json")
                value["rules"] = sub["rules"]
                value["task_id"] = sub["contract"]["task_id"]
                value["assessment_policy"] = sub["contract"].get("assessment_policy")
                value["rule_presentations"] = self.presentations(sub["rules"], sub["contract"])
                value["accounting"] = sub.get("accounting", {})
                value["reason"] = sub.get("reason") or value.get("reason")
                value["review_advisories"] = task_advisories(sub.get("contract", {}))
                if "method_evidence" in sub:
                    value["method_evidence"] = sub["method_evidence"]
            if (p / "evaluation.json").exists():
                value["evaluation"] = read_json(p / "evaluation.json")
        return value

    def list_runs(self):
        return [
            self.get_run(p.name, False)
            for p in sorted(
                [*self.runs.iterdir(), *self.bound_runs.iterdir()],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if (p / "request.json").exists() and (p.parent == self.runs or (p / "ui.json").exists())
        ]

    def start(self, req):
        with self.lock:
            return self._start(req)

    def _start(self, req):
        sid = req.get("scenario_id")
        paths = self.scenario_paths()
        if sid not in paths:
            raise ValueError("Select a registered or imported scenario")
        mid = req.get("method_id", "principia_engine")
        method = METHODS.get(mid)
        if not method or not method.available:
            raise ValueError("Method integration has not passed conformance checks")
        if "protocol_revision" in req and mid != bound_jobs.METHOD_ID:
            raise ValueError(
                "Protocol selection is only available for explicit-state Adaptive Primitive Search"
            )
        roles = req.get("model_roles", DEFAULT_ROLES)
        profiles = model_settings.profiles(self)
        if (
            not isinstance(roles, dict)
            or set(roles) != set(DEFAULT_ROLES)
            or any(not isinstance(v, str) for v in roles.values())
        ):
            raise ValueError("Unknown model role configuration")
        if method.needs_llm:
            if not credentials.status(self)["configured"]:
                raise ValueError(
                    "Add your SiliconFlow API key in API settings before using this method"
                )
            if self.probe_pending:
                raise ValueError("Wait for the model capability check to finish")
            used = {roles["coder"]}
            if mid in {
                "principia_engine",
                "principia_engine_explicit",
                "agent_laboratory",
                "agent_laboratory_explicit",
                "data_to_paper",
                "data_to_paper_explicit",
                "asta_autodiscovery",
                "agentrxiv",
            }:
                used = set(roles.values())
            if mid.startswith("direct_"):
                used = {MODELS[["deepseek", "glm", "qwen", "kimi"].index(mid.split("_", 1)[1])]}
            if any(
                m not in profiles or self.capabilities().get(m, {}).get("state") != "verified"
                for m in used
            ):
                raise ValueError(
                    "One or more selected model profiles have not passed capability checks"
                )
        if method.needs_llm:
            for m in used:
                binding = self.capabilities().get(m, {}).get("profile_sha256")
                if binding is not None and binding != sha(profiles[m]):
                    raise ValueError("Model profile changed; check access again before running")
        if mid in {bound_jobs.METHOD_ID, laboratory_jobs.METHOD_ID, paper_v2_jobs.METHOD_ID}:
            from ..llm.siliconflow import PROFILES

            if any(profiles.get(m) != PROFILES.get(m) for m in roles.values()):
                raise ValueError(
                    "This development protocol requires its frozen model profiles. Use the standard method for custom profiles."
                )
        budget = float(req.get("budget_cny", 12))
        if not 0 < budget <= 30:
            raise ValueError("Attempt API budget must be between 0 and 30 CNY")
        scenario, selected_task = resolve_task(paths[sid], self.workspace, req.get("task_id"))
        if mid in {laboratory_jobs.METHOD_ID, paper_v2_jobs.METHOD_ID}:
            jobs = laboratory_jobs if mid == laboratory_jobs.METHOD_ID else paper_v2_jobs
            if not self.settings.get("project_root"):
                raise ValueError(
                    "Configure --project-root before using the explicit-state adapter worker"
                )
            if req.get("objective", ""):
                raise ValueError(
                    "Explicit-state adapter development uses the frozen task objective; custom objectives are unsupported"
                )
            folder = jobs.prepare(self.settings, scenario, roles=roles, budget=budget)
            self.queue_bound(folder)
            return {"run_id": folder.name, "status": "queued"}
        if mid == bound_jobs.METHOD_ID:
            folder = bound_jobs.prepare(
                self.settings,
                scenario,
                sid,
                roles,
                budget,
                req.get("objective", ""),
                protocol=req.get("protocol_revision", "v1"),
            )
            self.queue_bound(folder)
            return {"run_id": folder.name, "status": "queued"}
        id = "run-" + uuid.uuid4().hex[:16]
        folder = self.runs / id
        folder.mkdir()
        frozen = {
            "scenario_id": sid,
            "scenario_path": str(scenario),
            "task_id": selected_task["task_id"],
            "method_id": mid,
            "model_roles": roles,
            "objective": str(req.get("objective", ""))[:2000],
            "created_at": now(),
            "limits": {"api_cny": budget, "max_calls": 32, "max_fits": 1000, "wall_seconds": 2400},
            "mode": "interactive",
            "provider_profiles": profiles,
            "provider_capabilities": {
                m: c | {"profile_sha256": sha(profiles[m])}
                for m, c in self.capabilities().items()
                if m in profiles
            },
        }
        write_json(folder / "request.json", frozen, immutable=True)
        # Bind this job to its own local settings. Import evaluation never writes to
        # or relies on the shared benchmark evaluator directory.
        run_settings = dict(self.settings)
        if sid.startswith("LOCAL-"):
            run_settings["vault"] = str(self.workspace / "private-evaluator")
        write_json(folder / "local-settings.json", run_settings, immutable=True)
        write_json(folder / "state.json", {"status": "queued", "created_at": now()})
        self.normal_pending.add(id)
        future = self.pool.submit(self.execute, id)

        def completion(result):
            with self.lock:
                self.normal_pending.discard(id)
            failure = result.exception()
            if failure is not None:
                write_json(
                    folder / "state.json",
                    {
                        "status": "failed",
                        "reason": "Worker could not start: " + str(failure),
                        "finished_at": now(),
                    },
                )

        future.add_done_callback(completion)
        return {"run_id": id, "status": "queued"}

    def queue_bound(self, folder):
        if read_json(folder / "ui.json").get("development_campaign"):
            raise ValueError("This run is managed by its frozen development cohort driver")
        with self.lock:
            if folder.name in self.bound_pending or bound_jobs.alive(folder):
                raise ValueError("This development run already has a queued or active worker")
            self.bound_pending.add(folder.name)
        write_json(folder / "state.json", {"status": "queued"})
        future = self.pool.submit(bound_jobs.launch, folder)

        def completion(result):
            try:
                failure = result.exception()
                if failure is not None:
                    write_json(
                        folder / "state.json",
                        {
                            "status": "failed",
                            "reason": "Worker launch refused: " + str(failure),
                            "finished_at": now(),
                        },
                    )
            finally:
                with self.lock:
                    self.bound_pending.discard(folder.name)

        future.add_done_callback(completion)

    def resume_bound(self, id):
        folder = self.run_path(id)
        if folder.parent != self.bound_runs:
            raise ValueError(
                "Checkpoint recovery is only available for explicit-state development runs"
            )
        state = self.get_run(id, False)
        if not state.get("resume_available"):
            raise ValueError(state.get("recovery_reason", "This run cannot be resumed"))
        self.queue_bound(folder)
        return {"run_id": id, "status": "queued"}

    def execute(self, id):
        p = self.run_path(id)
        if (p / "cancel.requested").exists():
            write_json(p / "state.json", {"status": "cancelled"})
            return
        args = [
            sys.executable,
            "-m",
            "principia_asd.cli",
            "worker",
            str(p),
            "--settings",
            str(
                p / "local-settings.json"
                if (p / "local-settings.json").exists()
                else self.workspace / "settings.json"
            ),
        ]
        env = os.environ.copy()
        from ..store.snapshot import runtime_snapshot

        env["PYTHONPATH"] = str(runtime_snapshot(self.workspace))
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        for k in list(env):
            if any(word in k.upper() for word in ["API_KEY", "TOKEN", "SECRET"]):
                env.pop(k, None)
        for k in [
            "OPENBLAS_NUM_THREADS",
            "OMP_NUM_THREADS",
            "MKL_NUM_THREADS",
            "NUMEXPR_NUM_THREADS",
        ]:
            env[k] = "1"
        with (p / "worker.log").open("ab") as log:
            proc = subprocess.Popen(args, stdout=log, stderr=log, env=env, start_new_session=True)
            with self.lock:
                self.processes[id] = proc
            write_json(p / "process.json", {"pid": proc.pid, "started_at": now()})
            try:
                code = proc.wait(timeout=2600)
            except subprocess.TimeoutExpired:
                proc.terminate()
                code = proc.wait(timeout=15)
            with self.lock:
                self.processes.pop(id, None)
            if code and not (p / "submission-freeze.json").exists():
                write_json(
                    p / "state.json",
                    {
                        "status": "failed",
                        "reason": "Worker stopped before submission freeze; inspect the retained execution log",
                        "finished_at": now(),
                    },
                )

    def cancel(self, id):
        p = self.run_path(id)
        state = self.get_run(id, False)
        if state.get("mode") == "campaign":
            raise ValueError(
                "Campaign attempts are managed together by their driver; individual cancellation is unavailable"
            )
        if state["status"] in {
            "complete",
            "failed",
            "cancelled",
            "unsupported",
            "incomplete_method_execution",
        }:
            return state
        (p / "cancel.requested").touch()
        if p.parent == self.runs and id not in self.normal_pending:
            alive = False
            if (p / "process.json").exists():
                try:
                    os.kill(int(read_json(p / "process.json")["pid"]), 0)
                    alive = True
                except (ValueError, KeyError, ProcessLookupError):
                    pass
            if not alive:
                write_json(
                    p / "state.json",
                    {
                        "status": "cancelled",
                        "reason": "Cancelled after local interruption; existing paid receipts are retained.",
                    },
                )
                return {"run_id": id, "status": "cancelled"}
        if p.parent == self.bound_runs and not bound_jobs.alive(p):
            write_json(
                p / "state.json",
                {
                    "status": "cancelled",
                    "reason": "Cancelled before another worker started; paid receipts are retained.",
                },
            )
            return {"run_id": id, "status": "cancelled"}
        write_json(
            p / "state.json",
            {
                "status": "cancelling",
                "reason": "Stopping at the next safe boundary; an in-flight paid request will not be replayed",
            },
        )
        return {"run_id": id, "status": "cancelling"}

    def leaderboards(self):
        root = Path(self.settings["leaderboard_root"])
        tasks = {(s["scenario_id"], t["task_id"]): t for s in self.catalog() for t in s["tasks"]}
        rows = []
        for p in sorted((root / "scenarios").glob("*/tasks/*/leaderboard.json")):
            value = read_json(p)
            task = tasks.get((value["scenario_id"], value["task_id"]), {})
            value["rule_presentations"] = self.presentations(
                [r.get("card", r) for r in value["rules"]], task
            )
            rows.append(value)
        # Local custom tasks retain their own development portfolios; no fabricated test ranking.
        by_task = {}
        for p in sorted(self.runs.glob("*/submission.json")):
            sub = read_json(p)
            task = sub.get("contract", {})
            if task.get("assessment_policy") != "development_only":
                continue
            key = (task["parent_scenario_id"], task["task_id"])
            board = by_task.setdefault(
                key,
                {
                    "scenario_id": key[0],
                    "task_id": key[1],
                    "rules": [],
                    "attempts": [],
                    "pareto_front_rule_ids": [],
                    "track": "local-development",
                    "rule_presentations": {},
                },
            )
            board["attempts"].append(
                {
                    "method_id": sub["method_id"],
                    "status": sub["status"],
                    "reason": sub.get("reason"),
                }
            )
            board["rules"].extend(
                {
                    "rule_id": c["rule_id"],
                    "method_id": c["method_id"],
                    "card": c,
                    "simplicity": c.get("simplicity"),
                    "status": "development_only",
                }
                for c in sub["rules"]
            )
            board["rule_presentations"].update(self.presentations(sub["rules"], task))
        rows.extend(by_task.values())
        return rows

    def inspect_local(self, path):
        p = Path(path).expanduser().resolve()
        if not p.is_dir():
            raise ValueError("Enter a local folder containing CSV measurements")
        if any(x in {"private-evaluator", ".secrets", ".codex"} for x in p.parts):
            raise ValueError("This folder is protected")
        files = []
        for f in sorted(p.iterdir()):
            if (
                f.is_file()
                and f.name.endswith((".csv", ".csv.gz"))
                and "test_target" not in f.name.lower()
                and not f.is_symlink()
            ):
                rows = read_csv(f, max_bytes=10_000_000)
                if rows:
                    files.append(
                        {
                            "name": f.name,
                            "rows": len(rows),
                            "columns": list(rows[0]),
                            "numeric_columns": [
                                k for k, v in rows[0].items() if isinstance(v, (int, float))
                            ],
                        }
                    )
        if not files:
            raise ValueError("No supported CSV files found (limit: 10 MB expanded per file)")
        return {"folder": str(p), "files": files}

    def import_local(self, req):
        scan = self.inspect_local(req["folder"])
        filename = req["file"]
        if filename not in {f["name"] for f in scan["files"]}:
            raise ValueError("File is not in the inspected folder")
        rows = read_csv(Path(scan["folder"]) / filename)
        output = req["output"]
        group = req["group"]
        inputs = req["inputs"]
        if (
            not inputs
            or output in inputs
            or group in inputs
            or (set(inputs) | {output, group}) - set(rows[0])
        ):
            raise ValueError("Choose distinct allowed inputs, target and group columns")
        groups = sorted({str(r[group]) for r in rows}, key=lambda g: sha(["local-import", g]))
        if len(groups) < 6:
            raise ValueError("At least six independent groups are required to form train/dev/test")
        n = max(1, len(groups) // 5)
        assignment = {
            g: "test" if i < n else "dev" if i < 2 * n else "train" for i, g in enumerate(groups)
        }
        sid = "LOCAL-" + uuid.uuid4().hex[:8]
        path = self.workspace / "imports" / sid
        chunks = {"train": [], "dev": [], "test": []}
        for i, row in enumerate(rows):
            clean = {
                "sample_id": f"row-{i}",
                "group": str(row[group]),
                **{k: row[k] for k in inputs},
                "target": row[output],
            }
            chunks[assignment[str(row[group])]].append(clean)
        from ..contracts.schema import validate_contract
        from ..runtime import validate_data

        task = {
            "schema_version": "principia-asd.task-contract/2.0",
            "scenario_id": sid,
            "task_id": sid + ".v1",
            "title": str(req.get("title") or filename),
            "inputs": inputs,
            "input_units": {k: "user review required" for k in inputs},
            "output": "target",
            "output_units": "user review required",
            "split": {
                "train": "public/train.csv.gz",
                "dev": "public/dev.csv.gz",
                "test": "public/test_inputs.csv.gz",
                "policy": "whole user-declared groups; deterministic 60:20:20",
            },
            "metric": {"primary": "mae", "aggregation": "equal_group_mean"},
            "stability": {
                "domain": "training range",
                "relative_noise": 0.01,
                "ranking": False,
                "scope": "diagnostic only",
            },
            "coverage": {"required_fraction": 1},
            "test_exposure": "local-user-split",
            "observation_window": "user-declared columns; scientific availability has not been independently reviewed",
            "accuracy_gate": {"ratio": 1},
        }
        errors = validate_contract(task)
        if errors:
            raise ValueError("; ".join(errors))
        for v in chunks.values():
            validate_data(v, task)
        fields = ["sample_id", "group", *inputs, "target"]
        write_csv(path / "public/train.csv.gz", chunks["train"], fields)
        write_csv(path / "public/dev.csv.gz", chunks["dev"], fields)
        target = [{k: r[k] for k in ["sample_id", "group", "target"]} for r in chunks["test"]]
        test = [{k: r[k] for k in fields if k != "target"} for r in chunks["test"]]
        write_csv(path / "public/test_inputs.csv.gz", test, fields[:-1])
        vp = self.workspace / "private-evaluator" / sid
        write_csv(vp / "test_targets.csv.gz", target, ["sample_id", "group", "target"])
        write_json(path / "task-contracts/task-001.json", task)
        info = {
            "scenario_id": sid,
            "title": task["title"],
            "domain": "Local import",
            "description": "User-provided measurements",
            "rows": {k: len(v) for k, v in chunks.items()},
            "source": {
                "source_sha256": file_sha(Path(scan["folder"]) / filename),
                "license": "user supplied; not cleared for redistribution",
            },
            "publication_authorized": False,
            "limitations": [
                "User must verify independent groups, timing and units.",
                "Exploratory local result; not admitted to public benchmark.",
            ],
        }
        write_json(path / "scenario.json", info)
        write_json(
            vp / "evaluator-manifest.json",
            {
                "task_id": task["task_id"],
                "target_sha256": file_sha(vp / "test_targets.csv.gz"),
                "input_sha256": file_sha(path / "public/test_inputs.csv.gz"),
                "contract_sha256": file_sha(path / "task-contracts/task-001.json"),
            },
        )
        return {"scenario_id": sid, "rows": info["rows"]}


def serve(settings, port=8150):
    app = App(settings)
    assets = Path(__file__).parent

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, obj, status=200):
            raw = json.dumps(obj, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(raw)

        def guard(self):
            host = self.headers.get("Host", "").split(":")[0]
            if host not in {"127.0.0.1", "localhost"}:
                raise ValueError("Loopback host required")
            origin = self.headers.get("Origin")
            if origin and origin not in {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}:
                raise ValueError("Cross-origin request denied")

        def do_GET(self):
            try:
                self.guard()
                path = urlparse(self.path).path
                if path == "/api/health":
                    return self.send({"ok": True, "version": __version__})
                if path == "/api/config":
                    return self.send(app.config())
                if path == "/api/provider":
                    return self.send(
                        {
                            "credential_status": credentials.status(app),
                            "probe": credentials.probe_status(app),
                            "capabilities": app.capabilities(),
                        }
                    )
                if path == "/api/scenarios":
                    return self.send(app.catalog())
                if path == "/api/runs":
                    return self.send(app.list_runs())
                if path == "/api/leaderboards":
                    return self.send(app.leaderboards())
                if path.startswith("/api/runs/"):
                    id = path.split("/")[3]
                    if path.endswith("/download"):
                        return self.send(app.get_run(id))
                    return self.send(app.get_run(id))
                name = {
                    "/": "index.html",
                    "/app.js": "app.js",
                    "/style.css": "style.css",
                    "/vendor/katex.min.js": "vendor/katex.min.js",
                }.get(path)
                if not name:
                    return self.send({"error": "Not found"}, 404)
                raw = (assets / name).read_bytes()
                self.send_response(200)
                self.send_header(
                    "Content-Type",
                    {
                        "index.html": "text/html",
                        "app.js": "text/javascript",
                        "style.css": "text/css",
                        "vendor/katex.min.js": "text/javascript",
                    }[name],
                )
                self.send_header("Content-Length", str(len(raw)))
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'",
                )
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(raw)
            except (ValueError, KeyError, FileNotFoundError) as e:
                self.send({"error": str(e)}, 400)
            except Exception as e:
                self.send({"error": "Application error: " + type(e).__name__}, 500)

        def do_POST(self):
            try:
                self.guard()
                if self.headers.get("X-Principia-CSRF") != app.token:
                    return self.send(
                        {"error": "Session token missing; reload the application"}, 403
                    )
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 64000:
                    raise ValueError("Request too large")
                req = json.loads(self.rfile.read(size))
                path = urlparse(self.path).path
                if path == "/api/provider/models":
                    return self.send(model_settings.save(app, req))
                if path == "/api/provider/catalog":
                    return self.send(model_settings.catalog(app))
                if path == "/api/provider/key":
                    return self.send(credentials.save(app, req))
                if path == "/api/provider/probe":
                    return self.send(credentials.start_probe(app, req), 202)
                if path == "/api/runs":
                    return self.send(app.start(req), 202)
                if path.startswith("/api/runs/") and path.endswith("/resume"):
                    return self.send(app.resume_bound(path.split("/")[3]), 202)
                if path.startswith("/api/runs/") and path.endswith("/cancel"):
                    return self.send(app.cancel(path.split("/")[3]))
                if path == "/api/tasks":
                    return self.send(app.add_task(req), 201)
                if path == "/api/local/inspect":
                    return self.send(app.inspect_local(req["folder"]))
                if path == "/api/local/import":
                    return self.send(app.import_local(req))
                self.send({"error": "Not found"}, 404)
            except (ValueError, KeyError, FileNotFoundError) as e:
                self.send({"error": str(e)}, 400)
            except Exception as e:
                self.send({"error": "Application error: " + type(e).__name__}, 500)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Principia-ASD: http://127.0.0.1:{port}", flush=True)
    server.serve_forever()
