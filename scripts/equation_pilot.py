"""A small local engineering cohort; all submissions freeze before any test assessment.

Run this script with the manifest's copied runtime. Completed or ambiguously billed
requests are never assigned a second attempt. It writes only its separate result pack.
"""

from __future__ import annotations

import argparse
import fcntl
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import principia_asd
from principia_asd.io import file_sha, read_json, write_json
from principia_asd.reports import export_campaign
from principia_asd.runtime import evaluate_run, now
from principia_asd.store.ledger import CostLedger


def run(campaign):
    manifest = read_json(campaign / "manifest.json")
    source = Path(manifest["runtime_source"]) / "principia_asd"
    if Path(principia_asd.__file__).resolve().parent != source.resolve():
        raise ValueError("Use the manifest's frozen runtime_source")
    if {str(p.relative_to(source)): file_sha(p) for p in source.rglob("*.py")} != manifest[
        "source_hashes"
    ]:
        raise ValueError("Frozen runtime mutated")
    if file_sha(Path(__file__)) != manifest["driver_sha256"]:
        raise ValueError("Frozen driver mutated")
    with (campaign / "driver.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        (campaign / "driver.pid").write_text(str(os.getpid()))
        settings = read_json(campaign / "settings.json")
        workspace = Path(settings["workspace"])
        env = os.environ.copy()
        env["PYTHONPATH"] = manifest["runtime_source"]
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        for key in [
            "OPENBLAS_NUM_THREADS",
            "OMP_NUM_THREADS",
            "MKL_NUM_THREADS",
            "VECLIB_MAXIMUM_THREADS",
        ]:
            env[key] = "1"

        def discover(job):
            folder = workspace / "runs" / job["run_id"]
            if (folder / "submission-freeze.json").exists():
                return
            if (folder / "manifest.json").exists():
                # Runtime recovery is conservative, even for a purely numerical interrupted job.
                raise ValueError(
                    "Interrupted started attempt requires explicit receipt diagnosis: "
                    + job["run_id"]
                )
            with (folder / "worker.log").open("ab") as log:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "principia_asd.cli",
                        "worker",
                        str(folder),
                        "--settings",
                        str(campaign / "settings.json"),
                        "--no-evaluate",
                    ],
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=2450,
                    check=False,
                )
            if not (folder / "submission-freeze.json").exists():
                raise ValueError(
                    f"Attempt has no frozen outcome ({result.returncode}): " + job["run_id"]
                )
            sub = read_json(folder / "submission.json")
            print(
                job["scenario_id"], job["method_id"], sub["status"], len(sub["rules"]), flush=True
            )

        write_json(campaign / "driver-status.json", {"phase": "discovery", "at": now()})
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(discover, manifest["jobs"]))
        submissions = {
            j["run_id"]: file_sha(workspace / "runs" / j["run_id"] / "submission.json")
            for j in manifest["jobs"]
        }
        freeze = campaign / "submission-freeze.json"
        if not freeze.exists():
            write_json(
                freeze,
                {
                    "at": now(),
                    "manifest_sha256": file_sha(campaign / "manifest.json"),
                    "submissions": submissions,
                },
                immutable=True,
            )
        if read_json(freeze)["submissions"] != submissions:
            raise ValueError("Frozen submission changed")
        write_json(campaign / "driver-status.json", {"phase": "zero-API assessment", "at": now()})
        for job in manifest["jobs"]:
            evaluate_run(workspace / "runs" / job["run_id"], Path(settings["vault"]))
        if not (campaign / "evaluation-freeze.json").exists():
            write_json(
                campaign / "evaluation-freeze.json",
                {
                    "at": now(),
                    "submission_freeze_sha256": file_sha(freeze),
                    "evaluations": {
                        j["run_id"]: file_sha(workspace / "runs" / j["run_id"] / "evaluation.json")
                        for j in manifest["jobs"]
                    },
                },
                immutable=True,
            )
        export_campaign(campaign, settings)
        ledger = CostLedger(workspace / "costs.sqlite")
        write_json(
            campaign / "driver-status.json",
            {
                "phase": "complete",
                "at": now(),
                "attempts": len(manifest["jobs"]),
                "costs": ledger.summary(),
            },
        )
        print("Frozen, assessed and exported", len(manifest["jobs"]), "attempts", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("campaign", type=Path)
    args = parser.parse_args()
    run(args.campaign.resolve())
