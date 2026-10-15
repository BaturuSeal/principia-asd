"""Start or resume one durable campaign using a private source snapshot."""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from principia_asd.io import file_sha, read_json, write_json
from principia_asd.store.snapshot import runtime_snapshot


def launch(settings_path, campaign_id, methods, cases, track="engineering"):
    if not campaign_id or not all(c.isalnum() or c in "-_" for c in campaign_id):
        raise ValueError("Invalid campaign identity")
    settings = read_json(settings_path)
    workspace = Path(settings["workspace"])
    camp = workspace / "campaigns" / campaign_id
    camp.mkdir(parents=True, exist_ok=True)
    if (camp / "completion.json").exists():
        return {"status": "already_complete", "campaign_id": campaign_id}
    if (camp / "driver.pid").exists():
        pid = read_json(camp / "driver.pid")["pid"]
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            pass
        else:
            return {"status": "already_running", "pid": pid}
    binding = camp / "launch.json"
    if binding.exists():
        prior = read_json(binding)
        script = Path(prior["script"])
        source = Path(prior["runtime_source"])
        if file_sha(script) != prior["driver_sha256"]:
            raise ValueError("Frozen driver mutation")
        methods = prior["methods"]
        cases = prior["cases"]
        track = prior.get("track", "engineering")
    else:
        source = runtime_snapshot(workspace)
        script = source.parent / "scripts/campaign_v2.py"
        script.parent.mkdir(exist_ok=True)
        original = Path(__file__).with_name("campaign_v2.py")
        if script.exists() and file_sha(script) != file_sha(original):
            raise ValueError("Same source snapshot has another driver revision")
        if not script.exists():
            shutil.copyfile(original, script)
        write_json(
            binding,
            {
                "runtime_source": str(source),
                "script": str(script),
                "driver_sha256": file_sha(script),
                "methods": methods,
                "cases": cases,
                "track": track,
            },
            immutable=True,
        )
    frozen_settings = camp / "settings.json"
    if not frozen_settings.exists():
        write_json(frozen_settings, settings, immutable=True)
    elif read_json(frozen_settings) != settings:
        raise ValueError("Campaign settings changed")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(source)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    for k in ["OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"]:
        env[k] = "1"
    args = [
        sys.executable,
        str(script),
        "--settings",
        str(frozen_settings),
        "--campaign-id",
        campaign_id,
        "--methods",
        *methods,
    ]
    if cases:
        args += ["--cases", *cases]
    args += ["--track", track]
    with (camp / "driver.log").open("ab") as log:
        proc = subprocess.Popen(args, stdout=log, stderr=log, env=env, start_new_session=True)
    write_json(camp / "driver.pid", {"pid": proc.pid})
    return {"status": "started", "campaign_id": campaign_id, "pid": proc.pid}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", type=Path, required=True)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--methods", nargs="+", required=True)
    parser.add_argument("--cases", nargs="*")
    parser.add_argument("--track", choices=["engineering", "primary"], default="engineering")
    args = parser.parse_args()
    print(launch(args.settings, args.campaign_id, args.methods, args.cases, args.track))
