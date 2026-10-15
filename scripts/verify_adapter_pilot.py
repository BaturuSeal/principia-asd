"""Replay an adapter pilot with recorded responses only, using its frozen runtime."""

import argparse
import json
import sqlite3
import urllib.request
from collections import Counter
from pathlib import Path

import principia_asd
from principia_asd.engine.search import execute_method
from principia_asd.io import file_sha, read_csv, read_json, sha, write_json
from principia_asd.llm.siliconflow import PROFILES
from principia_asd.runtime import evaluate_run, now


class RecordedTransportFailure(RuntimeError):
    """A verified recorded boundary, never a fresh provider dispatch."""


class RecordedGateway:
    def __init__(self, folder, ledger_records):
        self.folder = folder
        self.calls = []
        self.requests = []
        self.failures = []
        self.ledger_records = ledger_records

    def complete(self, *, model, system, prompt, max_tokens, request_id):
        if request_id in self.requests:
            raise ValueError("Duplicate request during deterministic replay")
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.25,
            "stream": False,
            "response_format": {"type": "json_object"},
            **PROFILES[model]["options"],
        }
        record = self.ledger_records[request_id]
        if record["payload"]["payload_sha256"] != sha(body):
            raise ValueError("Replayed context differs from paid request: " + request_id)
        self.requests.append(request_id)
        cache = self.folder / "provider" / (sha(request_id) + ".json")
        if record["state"] != "completed":
            assert record["state"] == "unknown" and not cache.exists()
            assert record["payload"].get("error")
            self.failures.append({
                "request_id": request_id,
                "state": record["state"],
                "error_type": record["payload"]["error"],
                "payload_sha256": sha(body),
                "reserved_cny": record["reserved_cny"],
                "verification_scope": "Recorded unknown-usage boundary only; no provider redispatch or billing-resolution claim",
            })
            raise RecordedTransportFailure(record["payload"]["error"])
        saved = read_json(cache)
        assert saved["payload_sha256"] == sha(body)
        assert record["payload"]["response_sha256"] == sha(saved["response"])
        self.calls.append(request_id)
        return saved["response"]


def verify(campaign, settings):
    manifest = read_json(campaign / "manifest.json")
    launch = read_json(campaign / "launch.json")
    source = Path(manifest["runtime_source"]) / "principia_asd"
    assert Path(principia_asd.__file__).resolve().parent == source.resolve(), (
        "Use frozen PYTHONPATH"
    )
    assert {str(p.relative_to(source)): file_sha(p) for p in source.rglob("*.py")} == manifest[
        "source_hashes"
    ]
    assert file_sha(Path(launch["script"])) == launch["driver_sha256"] == manifest["driver_sha256"]
    freeze = read_json(campaign / "submission-freeze.json")
    ef = read_json(campaign / "evaluation-freeze.json")
    assert freeze["manifest_sha256"] == file_sha(campaign / "manifest.json")
    assert ef["submission_freeze_sha256"] == file_sha(campaign / "submission-freeze.json")
    ids = {j["run_id"] for j in manifest["jobs"]}
    assert len(ids) == len(manifest["jobs"]) and ids == set(freeze["submissions"]) == set(
        ef["evaluations"]
    )
    workspace = Path(settings["workspace"])
    ledger_before = file_sha(workspace / "costs.sqlite")
    with sqlite3.connect((workspace / "costs.sqlite").resolve().as_uri() + "?mode=ro", uri=True) as db:
        ledger_records = {
            rid: {"state": state, "reserved_cny": reserved, "payload": json.loads(payload)}
            for rid, state, reserved, payload in db.execute(
                "SELECT request_id,state,reserved_cny,payload FROM requests"
            )
        }
    attempts, rules = Counter(), Counter()
    request_count = 0
    failure_boundaries = []
    jobs = []

    def deny_network(*args, **kwargs):
        raise AssertionError("Network request attempted during offline replay")

    urllib.request.urlopen = deny_network
    for job in manifest["jobs"]:
        run = workspace / "runs" / job["run_id"]
        sub = read_json(run / "submission.json")
        req = read_json(run / "request.json")
        binding = read_json(run / "manifest.json")
        seal = read_json(run / "submission-freeze.json")
        assessment = read_json(run / "evaluation.json")
        assert (
            file_sha(run / "submission.json")
            == freeze["submissions"][job["run_id"]]
            == seal["submission_sha256"]
        )
        assert file_sha(run / "manifest.json") == seal["manifest_sha256"]
        assert file_sha(run / "evaluation.json") == ef["evaluations"][job["run_id"]]
        assert seal["at"] <= freeze["at"] <= assessment["evaluated_at"] <= ef["at"]
        assert req["model_roles"] == manifest["roles"] == binding["model_roles"]
        assert binding["runtime_sha256"] == sha(manifest["source_hashes"])
        scenario = Path(req["scenario_path"])
        task = sub["contract"]
        for name, path in {
            "contract": scenario / "task-contracts/task-001.json",
            "train": scenario / task["split"]["train"],
            "dev": scenario / task["split"]["dev"],
        }.items():
            assert file_sha(path) == binding["input_hashes"][name]
        replay = RecordedGateway(run, ledger_records)
        try:
            regenerated = execute_method(
                job["method_id"],
                task,
                read_csv(scenario / task["split"]["train"]),
                read_csv(scenario / task["split"]["dev"]),
                gateway=replay,
                roles=req["model_roles"],
                run_id=job["run_id"],
                limits=req["limits"],
            )
        except RecordedTransportFailure as exc:
            assert sub["status"] == "failed" and sub["reason"].startswith(str(exc) + ":")
            assert (run / "error.txt").read_text().strip().splitlines()[-1].endswith(sub["reason"])
            regenerated = {"status": "failed", "reason": sub["reason"], "rules": [], "trace": []}
            failure_boundaries.extend(replay.failures)
        for card in regenerated["rules"]:
            card["rule_sha256"] = sha(card)
        for key, value in regenerated.items():
            if key == "accounting":
                assert {k: v for k, v in value.items() if k != "wall_seconds"} == {
                    k: v for k, v in sub[key].items() if k != "wall_seconds"
                }
            else:
                assert value == sub[key], f"Replay differs in {key}: {job['run_id']}"
        assert evaluate_run(run, Path(settings["vault"]), replay=True)["replay_verified"]
        request_count += len(replay.calls)
        attempts[sub["status"]] += 1
        for receipt in assessment["receipts"]:
            rules[receipt["status"]] += 1
        jobs.append(
            job
            | {
                "status": sub["status"],
                "rules": len(sub["rules"]),
                "conformance": sub.get("method_evidence", {}).get("conformance"),
                "recorded_requests_replayed": len(replay.calls),
                "recorded_failure_boundaries": replay.failures,
            }
        )
    assert file_sha(workspace / "costs.sqlite") == ledger_before
    completion = read_json(campaign / "completion.json")
    local_summary = "canonical_export" in completion
    if local_summary:
        assert completion["attempts"] == len(ids)
        assert completion["status_counts"] == dict(attempts)
        assert completion["rules"] == sum(rules.values())
    return {
        "checked_at": now(),
        "status": "passed",
        "campaign_id": manifest["campaign_id"],
        "track": manifest["track"],
        "assigned_attempts": len(ids),
        "attempt_statuses": dict(attempts),
        "rule_statuses": dict(rules),
        "jobs": jobs,
        "recorded_requests_replayed": request_count,
        "ambiguous_requests_not_replayed": failure_boundaries,
        "new_api_calls": 0,
        "ledger_unchanged": True,
        "runtime_sha256": sha(manifest["source_hashes"]),
        "submission_freeze_sha256": file_sha(campaign / "submission-freeze.json"),
        "evaluation_freeze_sha256": file_sha(campaign / "evaluation-freeze.json"),
        "replay_scope": "Exact paid-payload hashes, cached responses, handoffs, programs, numeric results, conformance and final assessments. Unknown-usage failures verify cached prefixes and their recorded error boundary only; they are never redispatched. Excludes wall-clock timing and external billing resolution.",
        "scientific_review": "not_assessed",
        "included_in_primary_ranking": False,
        "driver_summary_note": (
            "Campaign-local completion counts verified separately from canonical primary export counts"
            if local_summary
            else "The frozen driver's completion counts summarize the canonical primary export; this receipt uses the pilot manifest's own fixed denominator"
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", type=Path, required=True)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = verify(args.campaign, read_json(args.settings))
    write_json(args.output, receipt)
    print(json.dumps(receipt, indent=2))
