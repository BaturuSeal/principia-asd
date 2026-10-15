"""Read-only control-cohort proof and compact release export; no assessment."""

import argparse
import inspect
import json
import sqlite3
from collections import Counter
from pathlib import Path

from principia_asd import control_pilot
from principia_asd.evaluate.bound import verify_frozen_candidate
from principia_asd.io import file_sha, read_json, sha, write_csv, write_json
from principia_asd.runtime import now


def ledger_snapshot(workspace):
    path = Path(workspace) / "costs.sqlite"
    if not path.exists():
        return {"exists": False}
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        rows = [dict(r) for r in db.execute("SELECT * FROM requests ORDER BY request_id")]
    return {"exists": True, "requests": len(rows), "requests_sha256": sha(rows)}


def verify(root, receipt):
    assert "site-packages" in inspect.getfile(control_pilot), "Use the separately installed wheel"
    root = Path(root).resolve()
    m = control_pilot.check(root)
    before = read_json(root / "ledger-before.json")
    completion = control_pilot.verify_completion(root, m)
    assert not control_pilot.summary(root)["active_workers"]
    rows, profiles = [], {}
    for job in m["jobs"]:
        outcome = control_pilot.read_outcome(root, m, job)
        run = Path(m["workspace"]) / "control-runs" / job["run_id"]
        checked = 0
        if (run / "result.json").exists():
            r = read_json(run / "result.json")["result"]
            frozen = r["host_submission"]
            for candidate in frozen["candidates"]:
                verify_frozen_candidate(frozen, frozen["sha256"], candidate["candidate_id"])
                checked += 1
        rows.append(
            {
                "scenario_id": job["scenario_id"],
                "control": job["control"],
                "status": outcome["status"],
                "slots": 3,
                "nominations": sum(bool(s["candidate_id"]) for s in outcome["nomination_slots"]),
                "candidates_verified": checked,
                "fitting_attempts": outcome.get("accounting", {}).get("fitting_attempts"),
                "optimizer_evaluations": outcome.get("accounting", {}).get("optimizer_evaluations"),
                "failed_fits": outcome.get("failed_fit_count"),
                "rejections": outcome.get("rejection_count"),
                "unsupported_reason": outcome.get("unsupported_reason"),
                "reason": outcome.get("reason"),
                "api_calls": 0,
                "ranking_authorized": False,
            }
        )
    for method in m["controls"]:
        values = [r for r in rows if r["control"] == method]
        profiles[method] = {
            "assigned": len(values),
            "statuses": dict(Counter(r["status"] for r in values)),
            "nominations": sum(r["nominations"] for r in values),
            "slots": len(values) * 3,
            "fitting_attempts": sum(r["fitting_attempts"] or 0 for r in values),
            "optimizer_evaluations": sum(r["optimizer_evaluations"] or 0 for r in values),
        }
    # Terminal verification must not dispatch any process or change the recorded result.
    assert control_pilot.launch(root) == {"status": "already_finished"}
    assert control_pilot.verify_completion(root, m) == completion
    assert ledger_snapshot(m["workspace"]) == before, "Global request ledger changed"
    value = {
        "checked_at": now(),
        "status": "passed_development_execution_verification",
        "campaign_id": m["campaign_id"],
        "manifest_sha256": m["sha256"],
        "submission_freeze_sha256": completion["submission_freeze_sha256"],
        "completion_sha256": completion["sha256"],
        "source_binding_sha256": file_sha(Path(m["runtime_source"]).parent / "binding.json"),
        "driver_source_sha256": file_sha(
            Path(m["runtime_source"]) / "principia_asd/control_pilot.py"
        ),
        "source_is_installed_distribution": True,
        "profiles": profiles,
        "attempts": rows,
        "assigned": m["assigned"],
        "statuses": completion["statuses"],
        "fixed_slots": m["fixed_nomination_slots"],
        "nominated_slots": completion["nominated_slots"],
        "started_at": completion["started_at"],
        "finished_at": completion["finished_at"],
        "api_calls": 0,
        "accounted_cny": 0,
        "ledger_unchanged": True,
        "context_runtime_journal_and_candidate_bindings": "verified",
        "private_test_assessment": "not_performed",
        "ranking_authorized": False,
        "scientific_review": "not_assessed",
        "scope": "Eight previously engineering-exposed scenarios; fixed-control development execution only",
    }
    write_json(receipt, value, immutable=True)
    write_csv(receipt.with_suffix(".csv"), rows, list(rows[0]))
    return {
        k: value[k]
        for k in (
            "status",
            "assigned",
            "statuses",
            "fixed_slots",
            "nominated_slots",
            "profiles",
            "api_calls",
            "ledger_unchanged",
        )
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", type=Path)
    p.add_argument("--receipt", type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(verify(a.root, a.receipt), indent=2))
