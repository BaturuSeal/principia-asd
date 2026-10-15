"""Private, frozen, no-provider control jobs; separate from primary comparisons."""

from __future__ import annotations

import argparse
import fcntl
import importlib.metadata
import json
import os
import subprocess
import uuid
from pathlib import Path

from .io import contained, file_sha, read_csv, read_json, sha, write_json
from .runtime import now
from .sandbox.controls import POLICY as SANDBOX_POLICY
from .sandbox.controls import profile, runtime
from .store.snapshot import runtime_snapshot

SCOPE = "engineering_only_explicit_state_controls_v1"
DEPENDENCIES = ("numpy", "scipy", "scikit-learn", "threadpoolctl")


def environment():
    result = runtime()
    result["dependencies"] = {name: importlib.metadata.version(name) for name in DEPENDENCIES}
    return result


def prepare(settings, scenario, control, *, project_root, limits=None):
    from .engine.bound_controls import BoundControl

    workspace, scenario = Path(settings["workspace"]).resolve(), Path(scenario).resolve()
    roots = [
        Path(project_root).resolve(),
        Path(settings["data_root"]).resolve(),
        Path(settings["leaderboard_root"]).resolve(),
    ]
    if any(workspace.is_relative_to(root) or root.is_relative_to(workspace) for root in roots):
        raise ValueError("Control workspace must be separate from all three upload roots")
    if not (scenario.is_relative_to(roots[1]) or scenario.is_relative_to(workspace / "imports")):
        raise ValueError("Scenario is outside the permitted edition or private imports")
    if settings.get("vault"):
        vault = Path(settings["vault"]).resolve()
        if (
            workspace.is_relative_to(vault)
            or vault.is_relative_to(workspace)
            or scenario.is_relative_to(vault)
        ):
            raise ValueError("Control inputs/workspace must be separate from evaluator custody")
    contract_path = contained(scenario, "task-contracts/task-001.json")
    if (scenario / "task-contracts/task-001.json").is_symlink():
        raise ValueError("Contract symlinks are not permitted")
    contract = read_json(contract_path)
    if contract.get("scenario_id") != scenario.name:
        raise ValueError("Scenario identity and task contract differ")
    paths = {key: contained(scenario, contract["split"][key]) for key in ("train", "dev")}
    if any((scenario / contract["split"][key]).is_symlink() for key in paths):
        raise ValueError("Input symlinks are not permitted")
    if len(set(paths.values())) != 2:
        raise ValueError("Train and dev paths must differ")
    source_hashes = {
        "contract": file_sha(contract_path),
        **{k: file_sha(v) for k, v in paths.items()},
    }
    rows = {k: read_csv(v) for k, v in paths.items()}
    permitted = set(contract["inputs"]) | {contract["output"], "sample_id", "group"}
    if any(set(row) != permitted for data in rows.values() for row in data):
        raise ValueError("Control data must contain exactly permitted measurements and identities")
    # Validate numeric context, split integrity and limits before making a job.
    engine = BoundControl(
        contract, rows["train"], rows["dev"], control=control, run_id="preflight", limits=limits
    )
    env = environment()
    source = runtime_snapshot(workspace)
    root = workspace / "control-runs"
    if root.exists() and root.resolve().parent != workspace:
        raise ValueError("Control run root cannot leave private workspace")
    folder = root / ("control-" + uuid.uuid4().hex[:16])
    folder.mkdir(parents=True)
    source_paths = {"contract": contract_path, **paths}
    inputs = {}
    for key, path in source_paths.items():
        name = (
            "contract.json"
            if key == "contract"
            else key + (".csv.gz" if path.suffix == ".gz" else ".csv")
        )
        destination = folder / "inputs" / name
        destination.parent.mkdir(exist_ok=True)
        raw = path.read_bytes()
        destination.write_bytes(raw)
        if file_sha(destination) != source_hashes[key] or file_sha(path) != source_hashes[key]:
            raise ValueError("Source changed while staging; incomplete job is not launchable")
        inputs[key] = {
            "path": str(destination.relative_to(folder)),
            "source_path": str(path),
            "sha256": source_hashes[key],
        }
    write_json(folder / "inputs.json", inputs, immutable=True)
    request = {
        "scope": SCOPE,
        "run_id": folder.name,
        "scenario_id": contract["scenario_id"],
        "control": control,
        "limits": engine.limits,
        "configuration_sha256": engine.configuration["sha256"],
        "workspace": str(workspace),
    }
    write_json(folder / "request.json", request, immutable=True)
    sandbox = profile(folder, source, workspace, env)
    (folder / "sandbox.sb").write_text(sandbox)
    launch = {
        "policy": SCOPE,
        "created_at": now(),
        "runtime_source": str(source),
        "environment": env,
        "runtime_binding_sha256": file_sha(source.parent / "binding.json"),
        "request_sha256": file_sha(folder / "request.json"),
        "inputs_sha256": file_sha(folder / "inputs.json"),
        "sandbox_policy": SANDBOX_POLICY,
        "sandbox_sha256": file_sha(folder / "sandbox.sb"),
        "source_configuration_sha256": engine.configuration["sha256"],
        "api_calls": 0,
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


def verify_binding(folder, *, check_environment=False):
    folder = Path(folder).resolve()
    config, request = read_json(folder / "launch.json"), read_json(folder / "request.json")
    source, workspace = Path(config["runtime_source"]), Path(request["workspace"])
    if (
        folder.parent != workspace / "control-runs"
        or request["run_id"] != folder.name
        or request["scope"] != SCOPE
    ):
        raise ValueError("Invalid private control identity/custody")
    if (
        config.get("policy") != SCOPE
        or config["sha256"] != sha({k: v for k, v in config.items() if k != "sha256"})
        or file_sha(folder / "request.json") != config["request_sha256"]
        or file_sha(folder / "inputs.json") != config["inputs_sha256"]
        or file_sha(folder / "sandbox.sb") != config["sandbox_sha256"]
        or file_sha(source.parent / "binding.json") != config["runtime_binding_sha256"]
    ):
        raise ValueError("Frozen control launch binding changed")
    if not source.resolve().is_relative_to(workspace / "runtime-revisions"):
        raise ValueError("Runtime source is outside frozen private revisions")
    files = read_json(source.parent / "binding.json")["files"]
    actual = {
        str(p.relative_to(source / "principia_asd")): file_sha(p)
        for p in (source / "principia_asd").rglob("*.py")
    }
    if actual != files:
        raise ValueError("Frozen control runtime changed")
    inputs = read_json(folder / "inputs.json")
    if set(inputs) != {"contract", "train", "dev"}:
        raise ValueError("Only contract/train/dev inputs are permitted")
    for item in inputs.values():
        path = contained(folder, item["path"])
        if not path.is_relative_to(folder / "inputs") or file_sha(path) != item["sha256"]:
            raise ValueError("Frozen staged input changed")
    if (
        profile(folder, source, workspace, config["environment"])
        != (folder / "sandbox.sb").read_text()
    ):
        raise ValueError("Sandbox no longer matches the frozen custody policy")
    if check_environment and config["environment"] != environment():
        raise ValueError("Frozen interpreter or dependency configuration changed")
    return config, request


def launch(folder):
    """Synchronous launcher; initial run and resume both use the copied runtime."""
    folder = Path(folder).resolve()
    config, request = verify_binding(folder, check_environment=True)
    with (folder / "launch.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Another launcher owns this control run") from exc
        if (folder / "result.json").exists():
            saved = read_json(folder / "result.json")
            result = saved["result"]
            state = read_json(folder / "state.json")
            last = read_json(sorted((folder / "checkpoints").glob("*.json"))[-1])
            if (
                result["sha256"] != sha({k: v for k, v in result.items() if k != "sha256"})
                or state.get("result_sha256") != result["sha256"]
                or saved["checkpoint_sha256"] != last["sha256"]
                or last["sha256"] != sha({k: v for k, v in last.items() if k != "sha256"})
            ):
                raise ValueError("Completed control result or checkpoint changed")
            return state
        if (folder / "process.json").exists():
            try:
                os.kill(int(read_json(folder / "process.json")["pid"]), 0)
            except ProcessLookupError:
                pass
            else:
                raise ValueError("The previous worker is still alive; no duplicate launched")
        if (folder / "cancel.requested").exists():
            state = {
                "status": "cancelled",
                "reason": "Cancelled before launch; no numerical work replayed",
                "api_calls": 0,
            }
            write_json(folder / "state.json", state)
            return state
        source = Path(config["runtime_source"])
        slots = Path(request["workspace"]) / "worker-slots"
        slots.mkdir(parents=True, exist_ok=True)
        env = {
            "PATH": "/usr/bin:/bin",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "LANG": "C.UTF-8",
        }
        for name in (
            "OPENBLAS_NUM_THREADS",
            "OMP_NUM_THREADS",
            "MKL_NUM_THREADS",
            "VECLIB_MAXIMUM_THREADS",
            "NUMEXPR_NUM_THREADS",
            "BLIS_NUM_THREADS",
        ):
            env[name] = "1"
        args = [
            config["environment"]["sandbox"],
            "-f",
            str(folder / "sandbox.sb"),
            config["environment"]["python"],
            "-I",
            "-B",
            str(source / "principia_asd/engine/control_worker.py"),
            str(folder),
        ]
        write_json(
            folder / "state.json", {"status": "running", "started_at": now(), "api_calls": 0}
        )
        with (folder / "worker.log").open("ab") as log:
            proc = subprocess.Popen(
                args,
                cwd=folder,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
            write_json(folder / "process.json", {"pid": proc.pid, "started_at": now()})
            try:
                code = proc.wait(timeout=request["limits"]["max_seconds"] + 30)
            except subprocess.TimeoutExpired:
                proc.kill()
                code = proc.wait(timeout=10)
        if not (folder / "result.json").exists():
            state = read_json(folder / "state.json")
            if state.get("status") not in {"recovery_required", "cancelled"}:
                state = {
                    "status": "interrupted",
                    "reason": "Worker stopped; uncommitted local work must not be replayed",
                    "exit_code": code,
                    "api_calls": 0,
                }
                write_json(folder / "state.json", state)
        return read_json(folder / "state.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_cmd = sub.add_parser("prepare")
    for field in ("settings", "scenario", "project-root"):
        prepare_cmd.add_argument("--" + field, type=Path, required=True)
    prepare_cmd.add_argument(
        "--control",
        required=True,
        choices=["fitted_constant", "affine", "quadratic", "fixed_symbolic"],
    )
    for command in ("run", "resume"):
        sub.add_parser(command).add_argument("folder", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        folder = prepare(
            read_json(args.settings), args.scenario, args.control, project_root=args.project_root
        )
        print(
            json.dumps({"folder": str(folder), "status": "prepared", "ranking_authorized": False})
        )
    else:
        print(json.dumps(launch(args.folder)))


if __name__ == "__main__":
    main()
