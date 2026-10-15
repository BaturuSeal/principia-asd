"""Shared custody and launch bindings for explicit-state development adapters.

Uses the common provider gateway, checkpoint journal and launch lifecycle. Only
staged train/dev inputs are loaded; no test evaluator or ranking is invoked.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import uuid
from pathlib import Path

from .control_jobs import environment
from .io import contained, file_sha, read_csv, read_json, sha, write_json
from .llm.siliconflow import PRICE_SOURCE, PROFILES
from .runtime import now
from .store.snapshot import runtime_snapshot

SPECS = {
    "asta": {
        "scope": "engineering_only_asta_explicit_v1",
        "method_id": "asta_autodiscovery_explicit",
        "prefix": "asta-",
        "protocol": "asta-v1",
        "label": "Asta",
        "worker_module": "principia_asd.engine.asta_worker",
        "max_calls": 25,
        "max_fits": 4,
    },
    "laboratory": {
        "scope": "engineering_only_laboratory_explicit_v1",
        "method_id": "agent_laboratory_explicit",
        "prefix": "laboratory-",
        "protocol": "laboratory-v1",
        "label": "Laboratory",
        "worker_module": "principia_asd.engine.laboratory_worker",
    },
    "paper": {
        "scope": "engineering_only_data_to_paper_explicit_v1",
        "method_id": "data_to_paper_explicit",
        "prefix": "paper-",
        "protocol": "paper-v1",
        "label": "data-to-paper",
        "worker_module": "principia_asd.engine.paper_worker",
    },
    "paper_v2": {
        "scope": "engineering_only_data_to_paper_explicit_v2",
        "method_id": "data_to_paper_explicit",
        "prefix": "paper-v2-",
        "protocol": "paper-v2",
        "label": "data-to-paper v2",
        "worker_module": "principia_asd.engine.paper_v2_worker",
    },
}
PROTOCOL_ADAPTERS = {s["protocol"]: name for name, s in SPECS.items()}


def specification(adapter):
    if not isinstance(adapter, str) or adapter not in SPECS:
        raise ValueError("Unknown explicit-state adapter; no fallback")
    return SPECS[adapter].copy()


def engine_class(adapter):
    specification(adapter)
    if adapter == "asta":
        from .engine.bound_asta import BoundAsta

        return BoundAsta
    if adapter == "paper_v2":
        from .engine.bound_data_to_paper_v2 import SchemaBoundDataToPaper

        return SchemaBoundDataToPaper
    if adapter == "laboratory":
        from .engine.bound_laboratory import BoundLaboratory

        return BoundLaboratory
    from .engine.bound_data_to_paper import BoundDataToPaper

    return BoundDataToPaper


def prepare(
    settings,
    scenario,
    *,
    adapter,
    roles=None,
    budget=12,
    limits=None,
    campaign_id=None,
    environment_probe=environment,
):
    spec = specification(adapter)
    workspace, scenario = Path(settings["workspace"]).resolve(), Path(scenario).resolve()
    roots = [Path(settings[k]).resolve() for k in ("project_root", "data_root", "leaderboard_root")]
    if any(workspace.is_relative_to(r) or r.is_relative_to(workspace) for r in roots):
        raise ValueError("Worker workspace must be separate from the three upload roots")
    if not (scenario.is_relative_to(roots[1]) or scenario.is_relative_to(workspace / "imports")):
        raise ValueError("Scenario is outside the configured edition or private imports")
    if settings.get("vault"):
        vault = Path(settings["vault"]).resolve()
        if (
            workspace.is_relative_to(vault)
            or vault.is_relative_to(workspace)
            or scenario.is_relative_to(vault)
        ):
            raise ValueError("Worker inputs/workspace must be separate from evaluator custody")
    if type(budget) not in (int, float) or not math.isfinite(budget) or not 0 < budget <= 12:
        raise ValueError("Attempt cap must be in (0,12] CNY")
    contract_path = contained(scenario, "task-contracts/task-001.json")
    if (scenario / "task-contracts/task-001.json").is_symlink():
        raise ValueError("Contract symlinks are not permitted")
    task = read_json(contract_path)
    if task.get("scenario_id") != scenario.name:
        raise ValueError("Scenario identity and contract differ")
    paths = {k: contained(scenario, task["split"][k]) for k in ("train", "dev")}
    if len(set(paths.values())) != 2 or any(
        (scenario / task["split"][k]).is_symlink() for k in paths
    ):
        raise ValueError("Distinct non-symlink train/dev inputs required")
    permitted = set(task["inputs"]) | {task["output"], "group", "sample_id"}
    rows = {k: read_csv(v) for k, v in paths.items()}
    if any(set(r) != permitted for data in rows.values() for r in data):
        raise ValueError("Inputs must contain exactly permitted measurements and identities")
    maximum = {
        "max_calls": spec.get("max_calls", 6),
        "max_fits": spec.get("max_fits", 2),
        "max_structures": 8000,
        "max_optimizer_evaluations": 4096,
        "max_seconds": 2400,
    }
    if limits and (
        set(limits) - set(maximum)
        or any(type(v) is not int or not 1 <= v <= maximum[k] for k, v in limits.items())
    ):
        raise ValueError("Limits exceed the frozen " + spec["label"] + " envelope")
    engine = engine_class(adapter)(
        task,
        rows["train"],
        rows["dev"],
        gateway=None,
        run_id="preflight",
        roles=roles,
        limits=maximum | (limits or {}),
    )
    capabilities = read_json(workspace / "capabilities.json")
    for model in set(engine.roles.values()):
        if (
            capabilities.get(model, {}).get("state") != "verified"
            or capabilities[model].get("generation") != PROFILES[model]
        ):
            raise ValueError("Exact provider profile is not verified; no substitutions")
    env = environment_probe()
    source = runtime_snapshot(workspace)
    root = workspace / "bound-runs"
    if root.exists() and root.resolve().parent != workspace:
        raise ValueError("Run root cannot leave the private workspace")
    folder = root / (spec["prefix"] + uuid.uuid4().hex[:16])
    folder.mkdir(parents=True)
    inputs = {}
    for key, path in {"contract": contract_path, **paths}.items():
        digest = file_sha(path)
        dest = (
            folder
            / "inputs"
            / (
                "contract.json"
                if key == "contract"
                else key + (".csv.gz" if path.suffix == ".gz" else ".csv")
            )
        )
        dest.parent.mkdir(exist_ok=True)
        dest.write_bytes(path.read_bytes())
        if file_sha(dest) != digest or file_sha(path) != digest:
            raise ValueError("Input changed during staging; incomplete job is not launchable")
        inputs[key] = {
            "path": str(dest.relative_to(folder)),
            "sha256": digest,
            "source_path": str(path),
        }
    write_json(folder / "inputs.json", inputs, immutable=True)
    write_json(folder / "capabilities.json", capabilities, immutable=True)
    # Credentials and test custody are deliberately absent from this frozen file.
    worker_settings = {k: settings[k] for k in ("workspace", "env_file") if settings.get(k)}
    worker_settings["workspace"] = str(workspace)
    write_json(folder / "settings.json", worker_settings, immutable=True)
    request = {
        "scope": spec["scope"],
        "run_id": folder.name,
        "scenario_id": task["scenario_id"],
        "roles": engine.roles,
        "limits": engine.limits,
        "attempt_cap_cny": budget,
        "configuration_sha256": engine.configuration["sha256"],
    }
    write_json(folder / "request.json", request, immutable=True)
    write_json(
        folder / "ui.json",
        {
            "scenario_id": task["scenario_id"],
            "method_id": spec["method_id"],
            "created_at": now(),
            "objective": "",
            "mode": "engineering",
            "development_campaign": campaign_id,
            "protocol_revision": spec["protocol"],
        },
        immutable=True,
    )
    launch = {
        "policy": spec["scope"],
        "runtime_source": str(source),
        "interpreter": sys.executable,
        "interpreter_sha256": file_sha(Path(sys.executable)),
        "environment": env,
        "runtime_binding_sha256": file_sha(source.parent / "binding.json"),
        "settings_sha256": file_sha(folder / "settings.json"),
        "request_sha256": file_sha(folder / "request.json"),
        "inputs_sha256": file_sha(folder / "inputs.json"),
        "capabilities_sha256": file_sha(folder / "capabilities.json"),
        "ui_sha256": file_sha(folder / "ui.json"),
        "configuration_sha256": engine.configuration["sha256"],
        "provider": {
            "profiles": {m: PROFILES[m] for m in sorted(set(engine.roles.values()))},
            "price_source": PRICE_SOURCE,
            "global_cap_cny": 3000,
            "attempt_cap_cny": budget,
        },
        "memory_bytes": 4 * 1024**3,
        "numerical_threads": 1,
    }
    launch["sha256"] = sha(launch)
    write_json(folder / "launch.json", launch, immutable=True)
    write_json(
        folder / "state.json",
        {"status": "queued", "created_at": now(), "ranking_authorized": False},
    )
    return folder


def verify_binding(folder, *, adapter, check_environment=False, environment_probe=environment):
    spec = specification(adapter)
    folder = Path(folder).resolve()
    config, request, settings = [
        read_json(folder / (n + ".json")) for n in ("launch", "request", "settings")
    ]
    workspace = Path(settings["workspace"]).resolve()
    source = Path(config["runtime_source"]).resolve()
    if (
        folder.parent != workspace / "bound-runs"
        or request.get("run_id") != folder.name
        or request.get("scope") != spec["scope"]
        or config.get("policy") != spec["scope"]
    ):
        raise ValueError("Invalid private adapter custody/identity")
    if config["sha256"] != sha({k: v for k, v in config.items() if k != "sha256"}):
        raise ValueError("Frozen launch configuration changed")
    for name in ("settings", "request", "inputs", "capabilities", "ui"):
        if file_sha(folder / (name + ".json")) != config[name + "_sha256"]:
            raise ValueError("Frozen " + name + " changed")
    if (
        not source.is_relative_to(workspace / "runtime-revisions")
        or file_sha(source.parent / "binding.json") != config["runtime_binding_sha256"]
    ):
        raise ValueError("Frozen runtime binding changed")
    actual = {
        str(p.relative_to(source / "principia_asd")): file_sha(p)
        for p in (source / "principia_asd").rglob("*.py")
    }
    if actual != read_json(source.parent / "binding.json")["files"]:
        raise ValueError("Frozen runtime source changed")
    inputs = read_json(folder / "inputs.json")
    if set(inputs) != {"contract", "train", "dev"}:
        raise ValueError("Only contract/train/dev inputs are permitted")
    for item in inputs.values():
        path = contained(folder, item["path"])
        if not path.is_relative_to(folder / "inputs") or file_sha(path) != item["sha256"]:
            raise ValueError("Frozen staged input changed")
    if check_environment and (
        environment_probe() != config["environment"]
        or file_sha(Path(config["interpreter"])) != config["interpreter_sha256"]
    ):
        raise ValueError("Frozen interpreter/dependency environment changed")
    return config, request, settings


def verify_finished(folder, config):
    """A terminal read checks the full journal chain and its launch binding."""
    folder = Path(folder)
    manifest = read_json(folder / "manifest.json")
    if (
        manifest["binding"]["provider"]["launch_sha256"] != config["sha256"]
        or manifest["binding"]["configuration"]["sha256"] != config["configuration_sha256"]
    ):
        raise ValueError("Completed journal launch/configuration mismatch")
    previous, pending = sha(manifest), None
    for i, path in enumerate(sorted((folder / "checkpoints").glob("*.json"))):
        record = read_json(path)
        if (
            path.name != f"{i:04}.json"
            or record["sequence"] != i
            or record["previous_sha256"] != previous
            or record["sha256"] != sha({k: v for k, v in record.items() if k != "sha256"})
        ):
            raise ValueError("Completed checkpoint chain changed")
        pair = (record["name"], record["kind"])
        if record["type"] == "intent" and pending is None:
            pending = pair
        elif record["type"] == "commit" and pending == pair:
            pending = None
        else:
            raise ValueError("Completed checkpoint transition changed")
        previous = record["sha256"]
    saved = read_json(folder / "result.json")
    result = saved["result"]
    if (
        pending
        or saved["checkpoint_sha256"] != previous
        or result["sha256"] != sha({k: v for k, v in result.items() if k != "sha256"})
        or result["configuration"] != manifest["binding"]["configuration"]
    ):
        raise ValueError("Completed result or checkpoint changed")
    return result


def main(adapter):
    specification(adapter)
    from . import bound_jobs
    from .store.ledger import CostLedger

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "run", "resume", "status"])
    parser.add_argument("path", type=Path)
    parser.add_argument("--scenario", type=Path)
    parser.add_argument("--budget", type=float, default=12)
    args = parser.parse_args()
    if args.command == "prepare":
        if not args.scenario:
            parser.error("prepare requires --scenario")
        result = {
            "folder": str(
                prepare(read_json(args.path), args.scenario, adapter=adapter, budget=args.budget)
            )
        }
    else:
        _, _, settings = verify_binding(args.path, adapter=adapter, check_environment=True)
        ledger = CostLedger(Path(settings["workspace"]) / "costs.sqlite")
        if args.command in {"run", "resume"}:
            if bound_jobs.alive(args.path):
                raise ValueError("Worker is still alive; no duplicate dispatch")
            if not (args.path / "result.json").exists():
                allowed, reason = bound_jobs.recovery(args.path, ledger)
                if not allowed:
                    raise ValueError(reason)
                bound_jobs.launch(args.path)
        result = bound_jobs.view(args.path, ledger)
    print(json.dumps(result, indent=2))
