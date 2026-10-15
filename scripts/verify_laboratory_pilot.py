"""Verify frozen Laboratory/Paper evidence without calls, fits or test access."""

import argparse
import inspect
import json
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from principia_asd import bound_jobs, bound_pilot
from principia_asd.engine.bound_checkpoint import _restore
from principia_asd.engine.bound_laboratory import ROLES, STAGES, BoundLaboratory
from principia_asd.evaluate.bound import verify_frozen_candidate
from principia_asd.io import contained, read_csv, read_json, sha, write_csv, write_json
from principia_asd.laboratory_jobs import verify_binding, verify_finished
from principia_asd.runtime import now


def ledger_rows(workspace):
    with sqlite3.connect((Path(workspace) / "costs.sqlite").as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        return [dict(r) for r in db.execute("SELECT * FROM requests ORDER BY request_id")]


def verify(root, receipt, *, adapter="laboratory"):
    if adapter in {"paper", "paper-v2"}:
        from principia_asd.engine.bound_data_to_paper import ROLES as roles
        from principia_asd.engine.bound_data_to_paper import BoundDataToPaper as engine_class
        from principia_asd.paper_jobs import verify_binding as verify_job

        if adapter == "paper-v2":
            from principia_asd.engine.bound_data_to_paper_v2 import (
                SchemaBoundDataToPaper as engine_class,
            )
            from principia_asd.paper_v2_jobs import verify_binding as verify_job
    elif adapter == "laboratory":
        roles = dict(zip(STAGES, ROLES, strict=True))
        engine_class, verify_job = BoundLaboratory, verify_binding
    else:
        raise ValueError("Unknown adapter")
    root = Path(root).resolve()
    m = bound_pilot.check(root)
    assert (
        Path(inspect.getfile(bound_pilot)).resolve()
        == Path(m["runtime_source"]) / "principia_asd/bound_pilot.py"
    ), "Use the frozen copied runtime"
    assert m["protocol_revision"] == ("paper-v2" if adapter == "paper-v2" else adapter + "-v1")
    summary = bound_pilot.summary(root)
    assert not summary["driver_alive"] and not summary["active_workers"]
    before = ledger_rows(m["workspace"])
    ledger = {r["request_id"]: r | {"payload": json.loads(r["payload"])} for r in before}
    completion = bound_pilot.verify_completion(root, m)
    rows, requests = [], []
    for job in m["jobs"]:
        outcome = bound_pilot.verified(root / "outcomes" / (job["scenario_id"] + ".json"))
        row = dict(
            scenario_id=job["scenario_id"],
            status=outcome["status"],
            slots=3,
            nominations=sum(bool(s["candidate_id"]) for s in outcome["nomination_slots"]),
            candidate_count=0,
            fitting_attempts=0,
            optimizer_evaluations=0,
            failed_fits=0,
            invalid_handoffs=[],
            failure=outcome.get("reason"),
            payloads_verified=0,
            ranking_authorized=False,
        )
        if job["run_id"]:
            folder = Path(m["workspace"]) / "bound-runs" / job["run_id"]
            config, request, _ = verify_job(folder)
            verify_finished(folder, config)
            result = read_json(folder / "result.json")["result"]
            frozen = result["host_submission"]
            for c in frozen["candidates"]:
                verify_frozen_candidate(frozen, frozen["sha256"], c["candidate_id"])
            inputs = read_json(folder / "inputs.json")
            engine = engine_class(
                read_json(contained(folder, inputs["contract"]["path"])),
                read_csv(contained(folder, inputs["train"]["path"])),
                read_csv(contained(folder, inputs["dev"]["path"])),
                gateway=None,
                run_id=folder.name,
                roles=request["roles"],
                limits=request["limits"],
            )
            assert engine.configuration["sha256"] == config["configuration_sha256"]
            records = [read_json(p) for p in sorted((folder / "checkpoints").glob("*.json"))]
            for record in records:
                if record["type"] != "intent" or record["kind"] != "provider":
                    continue
                _restore(engine, record["state"], read_json(folder / "manifest.json")["created_at"])
                name = record["name"]
                role = roles[name]
                nominated = None
                if name in {"evidence_report", "statistical_review", "report_repair"}:
                    nominated = next(
                        r["output"]
                        for r in records
                        if r["type"] == "commit" and r["name"] == "nominate"
                    )
                    nominated = nominated | {
                        "candidates": [
                            engine.host.candidates[s["candidate_id"]]
                            for s in nominated["selection"]["nominations"]
                            if s["candidate_id"]
                        ]
                    }
                context = engine._context(role, name, frozen=nominated)
                model = engine.roles[role]
                body = dict(
                    model=model,
                    messages=[
                        {"role": "system", "content": engine._system(role)},
                        {
                            "role": "user",
                            "content": json.dumps(context, allow_nan=False, sort_keys=True),
                        },
                    ],
                    max_tokens=1800,
                    temperature=0.25,
                    stream=False,
                    response_format={"type": "json_object"},
                    **m["profiles"][model]["options"],
                )
                rid = f"{folder.name}--{engine.request_tag}--{role}--{engine.requests + 1}"
                entry = ledger[rid]
                saved = read_json(folder / "provider" / (sha(rid) + ".json"))
                assert entry["state"] == "completed"
                assert sha(body) == entry["payload"]["payload_sha256"] == saved["payload_sha256"]
                response = saved["response"]
                assert sha(response) == entry["payload"]["response_sha256"]
                assert response["model"] == model and response["request_id"] == rid
                requests.append(
                    {
                        "request_id": rid,
                        "model": model,
                        "payload_sha256": sha(body),
                        "response_sha256": sha(response),
                        "finish_reason": response["finish_reason"],
                        "actual_cny": entry["actual_cny"],
                    }
                )
                row["payloads_verified"] += 1
            row.update(
                candidate_count=len(frozen["candidates"]),
                fitting_attempts=frozen["accounting"]["fitting_attempts"],
                optimizer_evaluations=frozen["accounting"]["optimizer_evaluations"],
                failed_fits=len(frozen["failures"]),
                invalid_handoffs=[h["name"] for h in result["handoffs"] if not h["schema_valid"]]
                if adapter == "laboratory"
                else [
                    {"stage": r["stage"], "errors": r["errors"]}
                    for r in result["trace"]
                    if r["stage"]
                    in {"paper_plan_guard", "paper_review_guard", "paper_report_guard"}
                    and not r["valid"]
                ],
                failure=result["failure"],
            )
            assert row["payloads_verified"] == result["model_requests"]
            bound_jobs.launch(
                folder
            )  # Verified terminal return only, guarded against process dispatch below.
        rows.append(row)
    for model in m["profiles"]:
        probe = bound_pilot.verified(root / "probes" / (sha(model) + ".json"))
        saved = read_json(root / "probes/provider" / (sha(probe["request_id"]) + ".json"))
        entry = ledger[probe["request_id"]]
        assert probe["state"] == "verified" and entry["state"] == "completed"
        assert (
            probe["response_sha256"]
            == entry["payload"]["response_sha256"]
            == sha(saved["response"])
        )
    assert len(set(r["request_id"] for r in requests)) == len(requests)
    assert bound_pilot.launch(root) == {"status": "already_finished"}
    assert before == ledger_rows(m["workspace"]), "Verification changed request ledger"
    started = read_json(root / "driver.pid")["started_at"]
    seconds = (
        datetime.fromisoformat(completion["at"]) - datetime.fromisoformat(started)
    ).total_seconds()
    value = dict(
        status="passed_development_execution_verification",
        checked_at=now(),
        campaign_id=m["campaign_id"],
        manifest_sha256=m["sha256"],
        submission_freeze_sha256=completion["submission_freeze_sha256"],
        completion_sha256=completion["sha256"],
        source_binding_sha256=m["runtime_binding_sha256"],
        assigned=len(rows),
        statuses=dict(Counter(r["status"] for r in rows)),
        fixed_slots=sum(r["slots"] for r in rows),
        nominated_slots=sum(r["nominations"] for r in rows),
        attempts=rows,
        request_receipts=requests,
        probe_receipts_verified=len(m["profiles"]),
        provider_requests=summary["costs"]["requests"],
        accounted_cny=summary["costs"]["accounted_cny"],
        elapsed_seconds=seconds,
        new_api_calls=0,
        new_fits=0,
        ledger_unchanged=True,
        source_is_frozen_runtime=True,
        private_test_assessment="not_performed",
        ranking_authorized=False,
        scientific_review="not_assessed",
    )
    assert value["fixed_slots"] == m["fixed_nomination_slots"]
    write_json(receipt, value, immutable=True)
    write_csv(receipt.with_suffix(".csv"), rows, list(rows[0]))
    return {
        k: value[k]
        for k in [
            "status",
            "assigned",
            "statuses",
            "fixed_slots",
            "nominated_slots",
            "provider_requests",
            "accounted_cny",
            "elapsed_seconds",
            "ledger_unchanged",
        ]
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", type=Path)
    p.add_argument("--receipt", type=Path, required=True)
    p.add_argument("--adapter", choices=["laboratory", "paper", "paper-v2"], default="laboratory")
    a = p.parse_args()
    with (
        patch("urllib.request.urlopen", side_effect=AssertionError("No verification network")),
        patch("subprocess.Popen", side_effect=AssertionError("No verification dispatch")),
        patch(
            "principia_asd.engine.bound_search.BoundSearch.fit",
            side_effect=AssertionError("No verification fit"),
        ),
    ):
        print(json.dumps(verify(a.root, a.receipt, adapter=a.adapter), indent=2))
