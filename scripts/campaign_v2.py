"""Single-driver campaign with immutable contexts and a global evaluation barrier."""

from __future__ import annotations

import argparse
import fcntl
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from principia_asd.io import file_sha, read_json, write_json
from principia_asd.methods.registry import DEFAULT_ROLES
from principia_asd.reports import export_campaign
from principia_asd.runtime import evaluate_run, now


def run(settings_path, campaign_id, methods, cases, track="engineering"):
    settings = read_json(settings_path)
    work = Path(settings["workspace"])
    camp = work / "campaigns" / campaign_id
    camp.mkdir(parents=True, exist_ok=True)
    lock = (camp / "driver.lock").open("a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise RuntimeError("Campaign driver already running") from None
    write_json(camp / "driver.pid", {"pid": os.getpid(), "started": now()})
    source = Path(__file__).resolve().parent.parent / "src/principia_asd"
    source_hashes = {str(p.relative_to(source)): file_sha(p) for p in source.rglob("*.py")}
    root = Path(settings["data_root"])
    if (camp / "manifest.json").exists():
        manifest = read_json(camp / "manifest.json")
        if manifest["source_hashes"] != source_hashes or manifest["driver_sha256"] != file_sha(
            Path(__file__)
        ):
            raise ValueError("Campaign source changed; resume using its original runtime_source")
        if manifest["data_edition_sha256"] != file_sha(root / "EDITION.json"):
            raise ValueError("Campaign data edition changed")
    else:
        root = Path(settings["data_root"])
        cases = cases or [
            x["scenario_id"] for x in read_json(root / "EDITION.json")["active_scenarios"]
        ]
        jobs = [
            {"run_id": campaign_id + "--" + sid + "--" + m, "scenario_id": sid, "method_id": m}
            for sid in cases
            for m in methods
        ]
        source = Path(__file__).resolve().parent.parent / "src/principia_asd"
        manifest = {
            "version": "1.0.0rc2",
            "campaign_id": campaign_id,
            "scenarios": cases,
            "methods": methods,
            "jobs": jobs,
            "created": now(),
            "runtime_source": str(source.parent),
            "driver_sha256": file_sha(Path(__file__)),
            "source_hashes": {
                str(p.relative_to(source)): file_sha(p) for p in source.rglob("*.py")
            },
            "roles": DEFAULT_ROLES,
            "max_workers": 4,
            "api_cap_cny": 3000,
            "capabilities_sha256": file_sha(work / "capabilities.json"),
            "price_snapshot": read_json(work / "price-snapshot.json"),
            "track": track,
            "engineering_exposed_scenarios": [
                "P100-002",
                "P100-017",
                "P100-043",
                "P100-051",
                "P100-054",
                "P100-068",
                "P100-087",
                "P100-090",
            ],
            "data_edition_sha256": file_sha(root / "EDITION.json"),
        }
        write_json(camp / "manifest.json", manifest, immutable=True)

    def phase(name, **kw):
        write_json(camp / "driver-status.json", {"phase": name, "at": now(), **kw})
        print(name, kw, flush=True)

    phase("discovery", assigned=len(manifest["jobs"]))

    def one(job):
        folder = work / "runs" / job["run_id"]
        folder.mkdir(parents=True, exist_ok=True)
        if (folder / "submission-freeze.json").exists():
            return job
        if (folder / "process.json").exists():
            previous = read_json(folder / "process.json")
            try:
                os.kill(previous["pid"], 0)
            except ProcessLookupError:
                pass
            else:
                raise RuntimeError("An earlier worker may still be active; inspect before resuming")
        request = {
            "scenario_path": str(Path(settings["data_root"]) / "scenarios" / job["scenario_id"]),
            "scenario_id": job["scenario_id"],
            "method_id": job["method_id"],
            "model_roles": manifest["roles"],
            "created_at": now(),
            "mode": "campaign",
            "limits": {"api_cny": 12, "max_calls": 32, "max_fits": 1000, "wall_seconds": 2400},
        }
        if not (folder / "request.json").exists():
            write_json(folder / "request.json", request, immutable=True)
        env = os.environ.copy()
        for k in [
            "OPENBLAS_NUM_THREADS",
            "OMP_NUM_THREADS",
            "MKL_NUM_THREADS",
            "NUMEXPR_NUM_THREADS",
        ]:
            env[k] = "1"
        with (folder / "worker.log").open("ab") as f:
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "principia_asd.cli",
                    "worker",
                    str(folder),
                    "--settings",
                    str(settings_path),
                    "--no-evaluate",
                ],
                stdout=f,
                stderr=f,
                env=env,
            )
            write_json(folder / "process.json", {"pid": proc.pid, "started_at": now()})
            try:
                code = proc.wait(timeout=2600)
            except subprocess.TimeoutExpired:
                proc.terminate()
                code = proc.wait(timeout=15)
        if not (folder / "submission-freeze.json").exists():
            raise RuntimeError(
                f"{job['run_id']} stopped before freeze (exit {code}); inspect retained log; no automatic paid replay"
            )
        return job

    done = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(one, j) for j in manifest["jobs"]]):
            job = future.result()
            done += 1
            phase("discovery", terminal=done, total=len(manifest["jobs"]), last=job["run_id"])
    freeze = camp / "submission-freeze.json"
    if not freeze.exists():
        write_json(
            freeze,
            {
                "campaign_id": campaign_id,
                "at": now(),
                "manifest_sha256": file_sha(camp / "manifest.json"),
                "submissions": {
                    j["run_id"]: file_sha(work / "runs" / j["run_id"] / "submission.json")
                    for j in manifest["jobs"]
                },
            },
            immutable=True,
        )
    phase("evaluation", frozen=len(manifest["jobs"]))
    for j in manifest["jobs"]:
        evaluate_run(work / "runs" / j["run_id"], Path(settings["vault"]))
    ef = camp / "evaluation-freeze.json"
    if not ef.exists():
        write_json(
            ef,
            {
                "campaign_id": campaign_id,
                "at": now(),
                "submission_freeze_sha256": file_sha(freeze),
                "evaluations": {
                    j["run_id"]: file_sha(work / "runs" / j["run_id"] / "evaluation.json")
                    for j in manifest["jobs"]
                },
            },
            immutable=True,
        )
    phase("export")
    exported = export_campaign(camp, settings)
    submissions = [
        read_json(work / "runs" / j["run_id"] / "submission.json") for j in manifest["jobs"]
    ]
    result = {
        "attempts": len(manifest["jobs"]),
        "rules": sum(len(s["rules"]) for s in submissions),
        "scenarios": len(manifest["scenarios"]),
        "status_counts": {
            status: sum(s["status"] == status for s in submissions)
            for status in sorted({s["status"] for s in submissions})
        },
        "canonical_export": exported,
    }
    if not (camp / "completion.json").exists():
        write_json(
            camp / "completion.json",
            result | {"at": now(), "submission_freeze_sha256": file_sha(freeze)},
            immutable=True,
        )
    phase("complete", **result)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--settings", type=Path, required=True)
    p.add_argument("--campaign-id", required=True)
    p.add_argument("--methods", nargs="+", required=True)
    p.add_argument("--cases", nargs="*")
    p.add_argument("--track", choices=["engineering", "primary"], default="engineering")
    a = p.parse_args()
    run(a.settings, a.campaign_id, a.methods, a.cases, a.track)
