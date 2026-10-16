from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

from .contracts.schema import validate_contract
from .io import read_json, write_json
from .methods.registry import DEFAULT_ROLES, METHODS


def main():
    p = argparse.ArgumentParser(
        prog="principia-asd",
        description="Discover reproducible scientific rules from local measurements.",
    )
    sub = p.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="Open the local discovery workspace")
    for k in ["workspace", "data-root", "leaderboard-root", "vault"]:
        serve.add_argument("--" + k, type=Path, required=True)
    serve.add_argument("--env-file", type=Path)
    serve.add_argument(
        "--project-root",
        type=Path,
        help="Public code root; required for the explicit-state Laboratory worker",
    )
    serve.add_argument("--port", type=int, default=8150)
    companion = sub.add_parser(
        "companion", help="Start a private local workspace from a public-release distribution"
    )
    companion.add_argument("--bundle-root", type=Path, required=True)
    companion.add_argument(
        "--workspace", type=Path, default=Path.home() / ".local/share/principia-asd"
    )
    companion.add_argument("--port", type=int, default=8150)
    site = sub.add_parser("build-site", help="Export a read-only public catalog and explored rules")
    for key in ("data-root", "leaderboard-root", "output"):
        site.add_argument("--" + key, type=Path, required=True)
    site.add_argument(
        "--preview",
        action="store_true",
        help="Local acceptance preview; does not grant data redistribution rights",
    )
    site.add_argument("--companion-bundle", type=Path)
    site.add_argument("--base-path", default="/")
    site.add_argument("--collections", type=Path, help="Hash-bound public COLLECTIONS.json")
    sub.add_parser("methods")
    for name in ["catalog", "audit"]:
        x = sub.add_parser(name)
        x.add_argument("root", type=Path)
    validate = sub.add_parser("validate")
    validate.add_argument("contract", type=Path)
    worker = sub.add_parser("worker", help=argparse.SUPPRESS)
    worker.add_argument("path", type=Path)
    worker.add_argument("--settings", type=Path, required=True)
    worker.add_argument("--no-evaluate", action="store_true")
    run = sub.add_parser("run")
    run.add_argument("--scenario", type=Path, required=True)
    run.add_argument("--method", required=True)
    run.add_argument("--settings", type=Path, required=True)
    run.add_argument("--no-evaluate", action="store_true")
    run.add_argument(
        "--protocol",
        choices=["v1", "v2"],
        help="Explicit-state Engine only; omission preserves v1. Saved runs always resume their frozen version.",
    )
    for cmd in ["resume", "evaluate", "replay"]:
        x = sub.add_parser(cmd)
        x.add_argument("path", type=Path)
        x.add_argument("--settings", type=Path, required=True)
    for cmd in ["leaderboard", "export"]:
        x = sub.add_parser(cmd)
        x.add_argument("--settings", type=Path, required=True)
        x.add_argument("--campaign", type=Path, required=True)
    prepare = sub.add_parser(
        "prepare",
        help="Import a grouped CSV or reconstruct a draft from a registered native recipe",
    )
    prepare.add_argument("--settings", type=Path)
    source = prepare.add_mutually_exclusive_group(required=True)
    source.add_argument("--spec", type=Path)
    source.add_argument("--native-recipe", type=Path)
    prepare.add_argument("--source-root", type=Path)
    prepare.add_argument("--output-root", type=Path)
    prepare.add_argument("--compare-scenario", type=Path)
    review = sub.add_parser(
        "review", help="Attach an externally prepared scientific review after quantitative freeze"
    )
    review.add_argument("path", type=Path)
    review.add_argument("--review-file", type=Path, required=True)
    a = p.parse_args()
    if a.command == "companion":
        from .web.server import serve

        base = a.bundle_root.expanduser().resolve()
        workspace = a.workspace.expanduser().resolve()
        settings = {
            "workspace": str(workspace),
            "data_root": str(base / "datas/ASD-Scenarios-26Oct10"),
            "leaderboard_root": str(base / "leaderboards/Scenarios-rules-26Oct10"),
            "project_root": str(base / "projects/PrincipiaASD-dev-26Oct10"),
            "vault": str(workspace / "private-evaluator"),
        }
        if (base / "pyproject.toml").is_file() and (base / "data/EDITION.json").is_file():
            settings.update(
                data_root=str(base / "data"),
                leaderboard_root=str(base / "leaderboards"),
                project_root=str(base),
            )
        if not all(
            Path(settings[k]).is_dir() for k in ("data_root", "leaderboard_root", "project_root")
        ):
            p.error(
                "--bundle-root must be the extracted public-release folder (or the legacy three-folder bundle)"
            )
        if (base / "COLLECTIONS.json").is_file():
            from .web.collections import bundle_packs

            settings["bundled_packs"] = bundle_packs(base / "COLLECTIONS.json", workspace)
        serve(settings, a.port)
        return
    if a.command == "build-site":
        from .web.public_site import build_site

        result = build_site(
            a.data_root,
            a.leaderboard_root,
            a.output,
            preview=a.preview,
            companion_bundle=a.companion_bundle,
            collections_manifest=a.collections,
            base_path=a.base_path,
        )
        print(
            json.dumps(
                {k: v for k, v in result.items() if k not in {"files", "bindings"}}, indent=2
            )
        )
        return
    if a.command == "prepare":
        if a.spec and (not a.settings or a.source_root or a.output_root or a.compare_scenario):
            p.error("CSV preparation requires --settings and --spec only")
        if a.native_recipe and (a.settings or not a.source_root or not a.output_root):
            p.error(
                "Native preparation requires --source-root and --output-root, without --settings"
            )
    if a.command == "serve":
        from .web.server import serve

        settings = {
            k: str(getattr(a, k)) for k in ["workspace", "data_root", "leaderboard_root", "vault"]
        }
        if a.env_file:
            settings["env_file"] = str(a.env_file)
        if a.project_root:
            settings["project_root"] = str(a.project_root.resolve())
        serve(settings, a.port)
        return
    if a.command == "methods":
        result = [m.as_dict() for m in METHODS.values()]
    elif a.command == "audit":
        from .catalog.audit import audit_root

        result = audit_root(a.root)
        if not result["valid"]:
            print(json.dumps(result, indent=2))
            raise SystemExit(1)
    elif a.command == "catalog":
        root = a.root / "scenarios" if (a.root / "scenarios").exists() else a.root
        result = []
        for folder in sorted(root.iterdir()):
            if (folder / "scenario.json").exists():
                t = read_json(folder / "task-contracts/task-001.json")
                errors = validate_contract(t)
                result.append({"scenario_id": folder.name, "valid": not errors, "errors": errors})
        if a.command == "audit" and any(not x["valid"] for x in result):
            print(json.dumps(result, indent=2))
            raise SystemExit(1)
    elif a.command == "validate":
        errors = validate_contract(read_json(a.contract))
        result = {"valid": not errors, "errors": errors}
        if errors:
            print(json.dumps(result))
            raise SystemExit(1)
    elif a.command in {"worker", "run", "resume"}:
        from .runtime import worker

        settings = read_json(a.settings)
        from . import bound_jobs, laboratory_jobs, paper_v2_jobs

        if a.command == "run" and a.protocol and a.method != bound_jobs.METHOD_ID:
            p.error("--protocol is only available for principia_engine_explicit")
        if a.command == "run" and a.method in {laboratory_jobs.METHOD_ID, paper_v2_jobs.METHOD_ID}:
            jobs = laboratory_jobs if a.method == laboratory_jobs.METHOD_ID else paper_v2_jobs
            if not settings.get("project_root"):
                p.error("Explicit-state adapter development settings require project_root")
            folder = jobs.prepare(settings, a.scenario)
            bound_jobs.launch(folder)
            print(json.dumps({"run_id": folder.name, "state": read_json(folder / "state.json")}))
            return
        if a.command == "run" and a.method == bound_jobs.METHOD_ID:
            task = read_json(a.scenario / "task-contracts/task-001.json")
            folder = bound_jobs.prepare(
                settings, a.scenario, task["scenario_id"], protocol=a.protocol or "v1"
            )
            bound_jobs.launch(folder)
            print(json.dumps({"run_id": folder.name, "state": read_json(folder / "state.json")}))
            return
        if (
            a.command in {"worker", "resume"}
            and (a.path / "launch.json").exists()
            and (a.path / "request.json").exists()
            and read_json(a.path / "request.json").get("scope")
            in {
                "engineering_only_explicit_state_v1",
                "engineering_only_explicit_state_v2",
                laboratory_jobs.SCOPE,
                "engineering_only_data_to_paper_explicit_v1",
                "engineering_only_data_to_paper_explicit_v2",
                "engineering_only_asta_explicit_v1",
            }
        ):
            bound_jobs.launch(a.path)
            print(json.dumps({"run_id": a.path.name, "state": read_json(a.path / "state.json")}))
            return
        if (
            a.command in {"worker", "resume"}
            and (a.path / "request.json").exists()
            and str(read_json(a.path / "request.json").get("scope", "")).startswith(
                (
                    "engineering_only_explicit_state_",
                    "engineering_only_laboratory_explicit_",
                    "engineering_only_data_to_paper_explicit_",
                    "engineering_only_asta_explicit_",
                )
            )
        ):
            p.error("Unknown explicit-state protocol or missing frozen launch binding")
        if a.command == "run":
            folder = Path(settings["workspace"]) / "runs" / ("run-" + uuid.uuid4().hex[:16])
            folder.mkdir(parents=True)
            task = read_json(a.scenario / "task-contracts/task-001.json")
            write_json(
                folder / "request.json",
                {
                    "scenario_path": str(a.scenario.resolve()),
                    "scenario_id": task["scenario_id"],
                    "method_id": a.method,
                    "model_roles": DEFAULT_ROLES,
                    "created_at": __import__("datetime")
                    .datetime.now(__import__("datetime").timezone.utc)
                    .isoformat(),
                    "limits": {"api_cny": 12, "max_calls": 32},
                },
                immutable=True,
            )
        else:
            folder = a.path
        if a.command == "resume" and (folder / "submission-freeze.json").exists():
            result = {"status": "already_frozen", "run_id": folder.name}
        else:
            worker(folder, settings, evaluate=not getattr(a, "no_evaluate", False))
            result = {"run_id": folder.name, "state": read_json(folder / "state.json")}
    elif a.command in {"evaluate", "replay"}:
        from .runtime import evaluate_run

        if (a.path / "request.json").exists() and str(
            read_json(a.path / "request.json").get("scope", "")
        ).startswith(
            (
                "engineering_only_explicit_state_",
                "engineering_only_laboratory_explicit_",
                "engineering_only_data_to_paper_explicit_",
                "engineering_only_asta_explicit_",
            )
        ):
            p.error(
                "Explicit-state development runs are not admitted for private-test evaluation. "
                "Inspect or download their frozen train/dev records in the UI."
            )
        settings = read_json(a.settings)
        result = evaluate_run(a.path, Path(settings["vault"]), replay=a.command == "replay")
    elif a.command in {"leaderboard", "export"}:
        from .reports import export_campaign

        result = export_campaign(a.campaign, read_json(a.settings))
    elif a.command == "prepare":
        if a.native_recipe:
            from .catalog.native import prepare

            result = prepare(
                a.native_recipe, a.source_root, a.output_root, compare_scenario=a.compare_scenario
            )
        else:
            from .web.server import App

            app = App(read_json(a.settings))
            result = app.import_local(read_json(a.spec))
    elif a.command == "review":
        if not (a.path / "evaluation.json").exists():
            raise ValueError("Quantitative evaluation must be frozen first")
        value = read_json(a.review_file)
        if not {"rubric", "evidence", "limitations", "status"} <= set(value):
            raise ValueError("Review must include rubric, evidence, limitations and status")
        write_json(a.path / "scientific-review.json", value, immutable=True)
        result = {"status": "review_attached", "quantitative_scores_modified": False}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
