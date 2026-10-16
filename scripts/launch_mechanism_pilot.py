"""Freeze and start one separate local cohort. Existing identities are never reused."""

import argparse
import os
import shutil
import subprocess
from pathlib import Path

from principia_asd.io import file_sha, read_json, sha, write_json
from principia_asd.llm.siliconflow import PROFILES
from principia_asd.methods.registry import DEFAULT_ROLES
from principia_asd.runtime import now
from principia_asd.store.ledger import CostLedger


def launch(
    project,
    workspace,
    data,
    vault,
    leaderboard,
    python,
    campaign_id="mechanism-systems-local-v2",
    agent_only=False,
    controls_only=False,
):
    # Resolving a virtualenv executable symlink bypasses the environment.
    subprocess.run([str(python), "-c", "import numpy, scipy, sklearn"], check=True)
    if not campaign_id.replace("-", "").isalnum():
        raise ValueError("Invalid campaign identity")
    campaign = workspace / "local-campaigns" / campaign_id
    if campaign.exists():
        raise FileExistsError(
            "Campaign identity already exists; inspect it instead of replaying requests"
        )
    settings = read_json(workspace / "settings.json") | {
        "data_root": str(data),
        "vault": str(vault),
        "leaderboard_root": str(leaderboard),
    }
    capabilities = read_json(workspace / "capabilities.json")
    for model, profile in PROFILES.items():
        if (
            capabilities[model].get("state") != "verified"
            or capabilities[model].get("generation") != profile
        ):
            raise ValueError("Exact model profile lacks capability evidence: " + model)
    costs = CostLedger(workspace / "costs.sqlite").summary()
    campaign.mkdir(parents=True)
    runtime = campaign / "runtime"
    shutil.copytree(
        project / "src/principia_asd",
        runtime / "principia_asd",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    driver = campaign / "driver.py"
    shutil.copyfile(project / "scripts/equation_pilot.py", driver)
    write_json(campaign / "settings.json", settings, immutable=True)
    methods = [
        "mean_control",
        "linear_control",
        "polynomial_control",
        "tree_control",
        "persistence_control",
        "equation_search",
        "equation_agent",
    ]
    if agent_only:
        methods = ["equation_agent"]
    if controls_only:
        methods = ["linear_control", "polynomial_control"]
    jobs = []
    for scenario in sorted((data / "scenarios").iterdir()):
        task = read_json(scenario / "task-contracts/task-001.json")
        for method in methods:
            rid = campaign_id + "-" + scenario.name.lower() + "-" + method.replace("_", "-")
            folder = workspace / "runs" / rid
            if folder.exists():
                raise ValueError("Assigned run already exists: " + rid)
            folder.mkdir()
            request = {
                "created_at": now(),
                "scenario_id": scenario.name,
                "scenario_path": str(scenario),
                "task_id": task["task_id"],
                "method_id": method,
                "mode": "engineering_pilot",
                "model_roles": DEFAULT_ROLES,
                "limits": {
                    "api_cny": 12,
                    "max_calls": 5,
                    "max_fits": 16,
                    "wall_seconds": 2400,
                    "equation_role_tokens": 3000,
                    "equation_proposal_tokens": 4096,
                },
                "provider_profiles": PROFILES,
                "provider_capabilities": {
                    m: c | {"profile_sha256": sha(PROFILES[m])}
                    for m, c in capabilities.items()
                    if m in PROFILES
                },
            }
            write_json(folder / "request.json", request, immutable=True)
            jobs.append(
                {
                    "run_id": rid,
                    "scenario_id": scenario.name,
                    "task_id": task["task_id"],
                    "method_id": method,
                }
            )
    manifest = {
        "campaign_id": campaign.name,
        "artifact_version": "1.0.0rc6",
        "track": "engineering-mechanism-comparison",
        "created": now(),
        "runtime_source": str(runtime),
        "driver_sha256": file_sha(driver),
        "source_hashes": {
            str(p.relative_to(runtime / "principia_asd")): file_sha(p)
            for p in sorted((runtime / "principia_asd").rglob("*.py"))
        },
        "data_hashes": {
            str(p.relative_to(data)): file_sha(p) for p in sorted(data.rglob("*")) if p.is_file()
        },
        "data_edition_sha256": file_sha(data / "EDITION.json"),
        "model_profiles": PROFILES,
        "model_roles": DEFAULT_ROLES,
        "capability_profile_sha256": sha(capabilities),
        "jobs": jobs,
        "scenarios": sorted({j["scenario_id"] for j in jobs}),
        "costs_before": costs,
        "global_cap_cny": 3000,
        "pilot_cap_cny": 0 if controls_only else 96,
        "engineering_revision": (
            "Zero-API numerical correction: center training design columns before scaling, preserve raw-coordinate coefficients. Constant-coordinate rank loss reproduced on synthetic data. All prior attempts retained; applies uniformly to all eight tasks, no equation or task changes."
            if controls_only
            else "Compact 200-word role handoffs with 3000 output tokens; equation proposals bounded to 4096 tokens. Four exact models unchanged. Frozen before inspecting any final test scores; prior failures retained, no uncertain request replay."
        ),
        "selection": "Within each method: training fit and development-only nomination, up to three equation systems. No post-test redesign in this cohort.",
        "claim_scope": "Local retrospective constitutive-model engineering. Known priors, negative transfers, unsupported references and failed attempts retained. Independent mechanism, novelty and external validation not assessed.",
    }
    write_json(campaign / "manifest.json", manifest, immutable=True)
    env = os.environ.copy()
    env.update(
        PYTHONPATH=str(runtime),
        PYTHONDONTWRITEBYTECODE="1",
        OMP_NUM_THREADS="1",
        OPENBLAS_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
        VECLIB_MAXIMUM_THREADS="1",
    )
    with (campaign / "driver.log").open("ab") as log:
        proc = subprocess.Popen(
            [str(python), str(driver), str(campaign)],
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    write_json(
        campaign / "launch.json",
        {
            "pid": proc.pid,
            "at": now(),
            "runtime_source": str(runtime),
            "driver": str(driver),
            "python": str(python),
        },
        immutable=True,
    )
    print(
        {
            "campaign": str(campaign),
            "pid": proc.pid,
            "assigned": len(jobs),
            "maximum_new_api_cny": 0 if controls_only else 96,
            "models": list(PROFILES),
        },
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for key in ["project", "workspace", "data", "vault", "leaderboard"]:
        parser.add_argument("--" + key, type=lambda x: Path(x).resolve(), required=True)
    parser.add_argument("--python", type=lambda x: Path(x).absolute(), required=True)
    parser.add_argument("--campaign-id", default="mechanism-systems-local-v2")
    parser.add_argument("--agent-only", action="store_true")
    parser.add_argument("--controls-only", action="store_true")
    a = parser.parse_args()
    launch(
        a.project,
        a.workspace,
        a.data,
        a.vault,
        a.leaderboard,
        a.python,
        a.campaign_id,
        a.agent_only,
        a.controls_only,
    )
