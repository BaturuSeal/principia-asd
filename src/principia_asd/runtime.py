"""Durable discovery jobs, submission freeze, and an evaluator-only confirmation stage."""

from __future__ import annotations

import json
import traceback
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from .contracts.schema import validate_contract
from .engine.search import Cancelled, execute_method
from .io import contained, file_sha, read_csv, read_json, sha, write_json
from .llm.siliconflow import SiliconFlowClient
from .methods.registry import DEFAULT_ROLES, get_method
from .store.ledger import CostLedger
from .store.worker_limits import WorkerCancelled


def now():
    return datetime.now(UTC).isoformat()


def log_event(folder, stage, detail):
    with (folder / "events.jsonl").open("a") as f:
        f.write(json.dumps({"at": now(), "stage": stage, "detail": detail}, allow_nan=False) + "\n")
    write_json(folder / "progress.json", {"stage": stage, "updated_at": now(), "detail": detail})


def validate_data(rows, task, targets=True):
    if not rows:
        raise ValueError("Empty measurement partition")
    ids = [r.get("sample_id") for r in rows]
    if None in ids or len(set(ids)) != len(ids):
        raise ValueError("Missing or duplicated sample identity")
    for row in rows:
        if not row.get("group"):
            raise ValueError("Every measurement needs a group identity")
        for k in task["inputs"] + ([task["output"]] if targets else []):
            if not isinstance(row.get(k), (float, int)) or not np.isfinite(row[k]):
                raise ValueError("Missing or invalid numeric measurement: " + k)
        if not targets and task["output"] in row:
            raise ValueError("Protected target present in public test inputs")


def train_contract(task, train):
    t = json.loads(json.dumps(task))
    t["stability"]["input_ranges"] = {
        k: [float(min(r[k] for r in train)), float(max(r[k] for r in train))]
        for k in task["inputs"]
    }
    t["stability"]["output_scale"] = max(float(np.std([r[task["output"]] for r in train])), 1e-12)
    return t


def discover_run(folder: Path, settings: dict):
    folder = Path(folder)
    config = read_json(folder / "request.json")
    scenario = Path(config["scenario_path"])
    method = get_method(config["method_id"])
    contract_path = scenario / "task-contracts/task-001.json"
    task = read_json(contract_path)
    errors = validate_contract(task)
    if errors:
        raise ValueError("; ".join(errors))
    train_path = contained(scenario, task["split"]["train"])
    dev_path = contained(scenario, task["split"]["dev"])
    train = read_csv(train_path)
    dev = read_csv(dev_path)
    # A source table may serve several tasks. Each method sees only its declared fields.
    permitted = {"sample_id", "group", *task["inputs"], task["output"]}
    train = [{k: v for k, v in row.items() if k in permitted} for row in train]
    dev = [{k: v for k, v in row.items() if k in permitted} for row in dev]
    validate_data(train, task)
    validate_data(dev, task)
    if {r["sample_id"] for r in train} & {r["sample_id"] for r in dev} or {
        r["group"] for r in train
    } & {r["group"] for r in dev}:
        raise ValueError("Train/development identity or group leakage")
    frozen_task = train_contract(task, train)
    frozen_task["research_objective"] = config.get("objective", "")
    hashes = {
        "contract": file_sha(contract_path),
        "train": file_sha(train_path),
        "dev": file_sha(dev_path),
    }
    manifest = {
        "version": "1.0.0rc2",
        "run_id": folder.name,
        "scenario_id": task["scenario_id"],
        "task_id": task["task_id"],
        "method": method.as_dict(),
        "model_roles": config.get("model_roles", DEFAULT_ROLES),
        "objective": config.get("objective", ""),
        "input_hashes": hashes,
        "limits": config.get("limits", {}),
        "created_at": now(),
        "test_exposure": task["test_exposure"],
    }
    if "provider_profiles" in config:
        manifest["provider_profiles_sha256"] = sha(config["provider_profiles"])
        manifest["provider_capabilities_sha256"] = sha(config.get("provider_capabilities", {}))
    source = Path(__file__).parent
    manifest["runtime_sha256"] = sha(
        {str(p.relative_to(source)): file_sha(p) for p in sorted(source.rglob("*.py"))}
    )
    # Hash identity excludes timestamps so an interrupted pre-freeze job can resume.
    if (folder / "manifest.json").exists():
        old = read_json(folder / "manifest.json")
        for key in [
            "input_hashes",
            "method",
            "model_roles",
            "objective",
            "limits",
            "runtime_sha256",
            "provider_profiles_sha256",
            "provider_capabilities_sha256",
        ]:
            if old.get(key) != manifest.get(key):
                raise ValueError(
                    "Frozen context, configuration or runtime changed; use the original source snapshot or create a new run"
                )
    else:
        write_json(folder / "manifest.json", manifest, immutable=True)
    if (folder / "submission-freeze.json").exists():
        return read_json(folder / "submission.json")
    write_json(
        folder / "state.json",
        {
            "status": "running",
            "started_at": now(),
            "scenario_id": task["scenario_id"],
            "method_id": method.method_id,
        },
    )

    def event(stage, detail):
        log_event(folder, stage, detail)

    event(
        "data_validated",
        {
            "train_rows": len(train),
            "dev_rows": len(dev),
            "input_count": len(task["inputs"]),
            "test_access": False,
        },
    )
    ledger = CostLedger(Path(settings["workspace"]) / "costs.sqlite")
    gateway = None
    if method.needs_llm:
        caps_path = Path(settings["workspace"]) / "capabilities.json"
        gateway = SiliconFlowClient(
            env_file=settings.get("env_file"),
            ledger=ledger,
            artifact_dir=folder / "provider",
            capabilities=config.get(
                "provider_capabilities", read_json(caps_path) if caps_path.exists() else {}
            ),
            profiles=config.get("provider_profiles"),
            attempt_cap_cny=config.get("limits", {}).get("api_cny", 12),
        )
    try:
        # Only development data is supplied to the method; final targets have not been opened.
        result = execute_method(
            method.method_id,
            frozen_task,
            train,
            dev,
            gateway=gateway,
            roles=config.get("model_roles"),
            event=event,
            stopped=lambda: (folder / "cancel.requested").exists(),
            run_id=folder.name,
            limits=config.get("limits"),
        )
    except Cancelled as e:
        result = {"status": "cancelled", "reason": str(e), "rules": [], "trace": []}
    except Exception as e:
        result = {
            "status": "failed",
            "reason": f"{type(e).__name__}: {e}",
            "rules": [],
            "trace": [],
        }
        (folder / "error.txt").write_text(traceback.format_exc())
    result["contract"] = frozen_task
    result["baseline_mean"] = float(np.mean([r[task["output"]] for r in train]))
    result["run_id"] = folder.name
    result["scenario_id"] = task["scenario_id"]
    result["method_id"] = method.method_id
    for r in result["rules"]:
        r["rule_sha256"] = sha(r)
    write_json(folder / "submission.json", result, immutable=True)
    write_json(
        folder / "submission-freeze.json",
        {
            "at": now(),
            "submission_sha256": file_sha(folder / "submission.json"),
            "manifest_sha256": file_sha(folder / "manifest.json"),
            "portfolio_size": len(result["rules"]),
            "selection": "train/dev only",
            "status": result["status"],
        },
        immutable=True,
    )
    event("submission_frozen", {"rules": len(result["rules"]), "status": result["status"]})
    write_json(
        folder / "state.json",
        {
            "status": result["status"],
            "phase": "frozen",
            "finished_at": now(),
            "reason": result.get("reason"),
        },
    )
    return result


def evaluate_run(folder: Path, vault: Path, *, replay=False):
    from .evaluate.metrics import evaluate_rule, loss, pareto_front

    freeze = read_json(folder / "submission-freeze.json")
    if (
        file_sha(folder / "submission.json") != freeze["submission_sha256"]
        or file_sha(folder / "manifest.json") != freeze["manifest_sha256"]
    ):
        raise ValueError("Frozen artifact mutation detected")
    cached = (
        read_json(folder / "evaluation.json") if (folder / "evaluation.json").exists() else None
    )
    if cached is not None and not replay:
        return cached
    sub = read_json(folder / "submission.json")
    task = sub["contract"]
    if task.get("assessment_policy") == "development_only":
        raise ValueError(
            "Custom task is development-only; private-test assessment is not authorized"
        )
    config = read_json(folder / "request.json")
    scenario = Path(config["scenario_path"])
    custody = vault / task["scenario_id"]
    task_custody = contained(custody, task["task_id"])
    if (task_custody / "evaluator-manifest.json").exists():
        custody = task_custody
    ex = read_json(custody / "evaluator-manifest.json")
    if ex.get("task_id", task["task_id"]) != task["task_id"]:
        raise ValueError("Evaluator is for a different task")
    tfile = custody / "test_targets.csv.gz"
    xfile = contained(scenario, task["split"]["test"])
    if file_sha(tfile) != ex["target_sha256"] or file_sha(xfile) != ex["input_sha256"]:
        raise ValueError("Evaluator data hashes changed")
    if file_sha(scenario / "task-contracts/task-001.json") != ex["contract_sha256"]:
        raise ValueError("Evaluator contract changed")
    rows = read_csv(xfile)
    targets = read_csv(tfile)
    validate_data(rows, task, targets=False)
    by_id = {r["sample_id"]: r for r in targets}
    if len(by_id) != len(targets) or set(by_id) != {r["sample_id"] for r in rows}:
        raise ValueError("Preparation defect: exact target identity coverage mismatch")
    y = []
    for r in rows:
        t = by_id[r["sample_id"]]
        if r["group"] != t["group"]:
            raise ValueError("Preparation defect: group mismatch")
        y.append(float(t["target"]))
    groups = [r["group"] for r in rows]
    baseline = loss(np.full(len(y), sub["baseline_mean"]), y, task["metric"]["primary"], groups)
    receipts = []
    for card in sub["rules"]:
        value = evaluate_rule(card, rows, y, task)
        value.pop("predictions", None)
        value.update(
            rule_id=card["rule_id"],
            run_id=folder.name,
            method_id=sub["method_id"],
            status="complete" if value["status"] == "valid" else "invalid",
            accuracy_gate=value["accuracy"]["primary_error"] is not None
            and value["accuracy"]["primary_error"]
            <= baseline * task.get("accuracy_gate", {}).get("ratio", 1),
            baseline_loss=baseline,
            evaluator_version="deterministic-equations-v1" if card.get("representation") == "equation-system-v1" else "deterministic-v2",
            test_exposure=task["test_exposure"],
            rule_sha256=card["rule_sha256"],
            scientific_review="not_assessed",
        )
        receipts.append(value)
    report = {
        "version": "1.0.0rc2",
        "run_id": folder.name,
        "scenario_id": task["scenario_id"],
        "task_id": task["task_id"],
        "status": sub["status"],
        "reason": sub.get("reason"),
        "evaluated_at": now(),
        "receipts": receipts,
        "pareto_rule_ids": [r["rule_id"] for r in pareto_front(receipts)],
        "submission_sha256": freeze["submission_sha256"],
        "test_target_sha256": ex["target_sha256"],
        "final_assessment_model_calls": 0,
    }
    if cached is not None:
        expected = {k: v for k, v in cached.items() if k != "evaluated_at"}
        actual = {k: v for k, v in report.items() if k != "evaluated_at"}
        if expected != actual:
            raise ValueError(
                "Replay differs from frozen receipt; use the exact original runtime and inspect its retained hashes"
            )
        return cached | {"replay_verified": True}
    write_json(folder / "evaluation.json", report, immutable=True)
    log_event(folder, "evaluation_complete", {"rules": len(receipts), "final_model_calls": 0})
    return report


def worker(folder, settings, evaluate=True):
    try:
        from .store.worker_limits import process_limits, worker_slot

        request = read_json(folder / "request.json")
        with worker_slot(settings["workspace"], lambda: (folder / "cancel.requested").exists()):
            with process_limits(folder, request.get("limits", {}).get("wall_seconds", 2400)):
                discover_run(folder, settings)
                if (
                    evaluate
                    and read_json(folder / "submission.json")["contract"].get("assessment_policy")
                    == "development_only"
                ):
                    log_event(
                        folder,
                        "assessment_pending",
                        {
                            "message": "Custom task: train/dev results only. A separately reviewed test contract is required for test ranking."
                        },
                    )
                elif evaluate:
                    scenario_id = read_json(folder / "submission.json")["scenario_id"]
                    task_id = read_json(folder / "submission.json")["contract"]["task_id"]
                    custody = Path(settings["vault"]) / scenario_id
                    if not any(
                        (p / "evaluator-manifest.json").exists()
                        for p in (custody, contained(custody, task_id))
                    ):
                        log_event(
                            folder,
                            "assessment_pending",
                            {
                                "message": "Rules are frozen. Protected evaluator targets are not installed on this machine; no test score is available."
                            },
                        )
                    else:
                        evaluate_run(folder, Path(settings["vault"]))
    except WorkerCancelled as exc:
        log_event(folder, "cancelled", {"message": str(exc)})
        write_json(
            folder / "state.json", {"status": "cancelled", "reason": str(exc), "finished_at": now()}
        )
    except Exception as exc:
        log_event(folder, "error", {"message": str(exc)[:600]})
        write_json(
            folder / "state.json", {"status": "failed", "reason": str(exc), "finished_at": now()}
        )
        (folder / "error.txt").write_text(traceback.format_exc())
        raise
