"""Reproject the frozen v1 engineering checkpoints without fitting or API calls.

This is development-interface verification, never a replay of scientific trials.
"""

import argparse
import ast
import inspect
import json
import textwrap
from pathlib import Path

from principia_asd.bound_pilot import check, record, verify_completion
from principia_asd.engine.bound_checkpoint import _restore
from principia_asd.engine.bound_engine import BoundEngine
from principia_asd.engine.bound_engine_v2 import SchemaBoundEngine
from principia_asd.io import contained, read_csv, read_json, sha
from principia_asd.runtime import now
from principia_asd.store.ledger import CostLedger


class NoDispatch:
    def complete(self, **kwargs):
        raise AssertionError("Projection must not call a model")


def verify(root, output):
    m = check(root)
    completion = verify_completion(root, m)
    ledger = CostLedger(Path(m["workspace"]) / "costs.sqlite")

    def ledger_hash():
        with ledger.connect() as db:
            return sha(db.execute("SELECT * FROM requests ORDER BY request_id").fetchall())

    before = ledger_hash()
    tree = ast.parse(textwrap.dedent(inspect.getsource(BoundEngine.run)))
    instructions = {
        node.args[0].value: node.args[1].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_ask"
    }
    rows = []
    for job in m["jobs"]:
        if not job["run_id"]:
            continue
        run = Path(m["workspace"]) / "bound-runs" / job["run_id"]
        req, manifest, result = [
            read_json(run / name) for name in ("request.json", "manifest.json", "result.json")
        ]
        scenario = Path(req["scenario_path"])
        task = read_json(scenario / "task-contracts/task-001.json")
        train, dev = [
            read_csv(contained(scenario, task["split"][name])) for name in ("train", "dev")
        ]
        for path in sorted((run / "checkpoints").glob("*.json")):
            checkpoint = read_json(path)
            if checkpoint["type"] != "intent" or checkpoint["kind"] != "provider":
                continue
            role = {"plan": "planner", "code": "coder", "critic": "critic", "report": "reporter"}[
                checkpoint["name"].split("-")[0]
            ]
            frozen = None
            if role == "reporter":
                r = result["result"]
                selected = {
                    s["candidate_id"] for s in r["selection"]["nominations"] if s["candidate_id"]
                }
                frozen = {
                    "nomination_freeze": r["nomination_freeze"],
                    "selection": r["selection"],
                    "candidates": [
                        c
                        for c in r["host_submission"]["candidates"]
                        if c["candidate_id"] in selected
                    ],
                }
            sizes = []
            for cls in (BoundEngine, SchemaBoundEngine):
                e = cls(
                    task,
                    train,
                    dev,
                    gateway=NoDispatch(),
                    run_id=req["run_id"],
                    roles=req["roles"],
                    limits=req["limits"],
                )
                if cls is BoundEngine:
                    assert e.configuration == manifest["binding"]["configuration"]
                _restore(e, checkpoint["state"], manifest["created_at"])
                initial_counts = (e.host.fits, e.host.optimizer_evaluations, e.requests)
                context = e._context(role, instructions[role], frozen=frozen)
                sizes.append(
                    len(
                        (
                            e._system(role) + json.dumps(context, allow_nan=False, sort_keys=True)
                        ).encode()
                    )
                )
                assert initial_counts == (e.host.fits, e.host.optimizer_evaluations, e.requests)
            rows.append(
                {
                    "scenario_id": job["scenario_id"],
                    "step": checkpoint["name"],
                    "checkpoint_sha256": checkpoint["sha256"],
                    "v1_bytes": sizes[0],
                    "v2_bytes": sizes[1],
                }
            )
    assert before == ledger_hash()
    assert rows and all(r["v2_bytes"] <= 48000 for r in rows)
    receipt = {
        "checked_at": now(),
        "status": "passed",
        "scope": "Development-only context projection; no new model response or scientific evaluation",
        "source_completion_sha256": completion["sha256"],
        "contexts": rows,
        "context_count": len(rows),
        "v1_max_bytes": max(r["v1_bytes"] for r in rows),
        "v2_max_bytes": max(r["v2_bytes"] for r in rows),
        "api_calls": 0,
        "fits": 0,
        "ledger_unchanged": True,
        "ranking_authorized": False,
    }
    return record(output, receipt)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = verify(args.cohort, args.output)
    print(
        {
            k: receipt[k]
            for k in (
                "status",
                "context_count",
                "v1_max_bytes",
                "v2_max_bytes",
                "api_calls",
                "fits",
            )
        }
    )
