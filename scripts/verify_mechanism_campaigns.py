"""Verify and replay every frozen local mechanism outcome with its original runtime."""

import argparse
import os
import subprocess
from pathlib import Path

from principia_asd.io import file_sha, read_json, write_json
from principia_asd.store.ledger import CostLedger


def verify(workspace, campaigns, python, output):
    ledger = CostLedger(workspace / "costs.sqlite")
    before = ledger.summary()
    rows = []
    for name in campaigns:
        root = workspace / "local-campaigns" / name
        manifest = read_json(root / "manifest.json")
        submissions = read_json(root / "submission-freeze.json")
        evaluations = read_json(root / "evaluation-freeze.json")
        settings = read_json(root / "settings.json")
        assert read_json(root / "driver-status.json")["phase"] == "complete"
        assert file_sha(root / "manifest.json") == submissions["manifest_sha256"]
        assert file_sha(root / "driver.py") == manifest["driver_sha256"]
        assert file_sha(root / "submission-freeze.json") == evaluations["submission_freeze_sha256"]
        source = Path(manifest["runtime_source"]) / "principia_asd"
        assert {str(f.relative_to(source)): file_sha(f) for f in source.rglob("*.py")} == manifest[
            "source_hashes"
        ]
        data = Path(settings["data_root"])
        assert {
            str(f.relative_to(data)): file_sha(f) for f in data.rglob("*") if f.is_file()
        } == manifest["data_hashes"]
        for job in manifest["jobs"]:
            run = workspace / "runs" / job["run_id"]
            assert file_sha(run / "submission.json") == submissions["submissions"][job["run_id"]]
            assert file_sha(run / "evaluation.json") == evaluations["evaluations"][job["run_id"]]
            assert submissions["at"] <= read_json(run / "evaluation.json")["evaluated_at"]
        child = """
import sys, socket, urllib.request
from pathlib import Path
from principia_asd.io import read_json
from principia_asd.runtime import evaluate_run
def denied(*a, **k):
    raise AssertionError("Final assessment must not use network")
socket.socket.connect = denied
urllib.request.urlopen = denied
c=Path(sys.argv[1]); m=read_json(c/'manifest.json'); s=read_json(c/'settings.json')
for j in m['jobs']:
    result=evaluate_run(Path(s['workspace'])/'runs'/j['run_id'],Path(s['vault']),replay=True)
    assert result['replay_verified'] and result['final_assessment_model_calls']==0
print(len(m['jobs']))
"""
        env = os.environ.copy()
        env.update(
            PYTHONPATH=manifest["runtime_source"],
            PYTHONDONTWRITEBYTECODE="1",
            OMP_NUM_THREADS="1",
            OPENBLAS_NUM_THREADS="1",
            MKL_NUM_THREADS="1",
            VECLIB_MAXIMUM_THREADS="1",
        )
        result = subprocess.run(
            [str(python), "-B", "-c", child, str(root)],
            env=env,
            text=True,
            capture_output=True,
            timeout=180,
            check=True,
        )
        count = int(result.stdout.strip())
        assert count == len(manifest["jobs"])
        rows.append(
            {
                "campaign": name,
                "terminal_attempts": count,
                "exact_offline_replays": count,
                "frozen_runtime_and_inputs": True,
                "manifest_sha256": file_sha(root / "manifest.json"),
                "submission_freeze_sha256": file_sha(root / "submission-freeze.json"),
                "evaluation_freeze_sha256": file_sha(root / "evaluation-freeze.json"),
            }
        )
    after = ledger.summary()
    assert before == after
    receipt = {
        "campaigns": rows,
        "total_attempts": sum(r["terminal_attempts"] for r in rows),
        "all_exact_replays": True,
        "no_provider_requests": True,
        "ledger_unchanged": True,
        "costs": after,
    }
    write_json(output, receipt)
    print({"attempts": receipt["total_attempts"], "exact_replay": True, "ledger_unchanged": True})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for key in ["workspace", "python", "output"]:
        parser.add_argument("--" + key, type=Path, required=True)
    parser.add_argument("--campaigns", nargs="+", required=True)
    args = parser.parse_args()
    verify(args.workspace.resolve(), args.campaigns, args.python.absolute(), args.output)
