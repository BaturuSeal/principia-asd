"""Train/dev payload preflight for the eight disclosed engineering scenarios.

Uses scripted hypotheses and synthetic observer replies, not provider calls.
Results establish transport size and expression compatibility only.
"""

import argparse
import importlib.util
import inspect
from pathlib import Path


def verify(data_root, workspace, receipt):
    from principia_asd.bound_pilot import CASES
    from principia_asd.engine.bound_asta import BoundAsta
    from principia_asd.io import contained, file_sha, read_csv, read_json, sha, write_json
    from principia_asd.runtime import now

    assert "site-packages" in inspect.getfile(BoundAsta)
    script = Path(__file__).with_name("verify_bound_asta.py")
    spec = importlib.util.spec_from_file_location("asta_context_fixture", script)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    workspace.mkdir(parents=True, exist_ok=False)
    rows = []
    for sid in CASES:
        scenario = data_root / "scenarios" / sid
        contract_path = scenario / "task-contracts/task-001.json"
        task = read_json(contract_path)
        inputs = {key: contained(scenario, task["split"][key]) for key in ("train", "dev")}
        source_hashes = {
            "contract": file_sha(contract_path),
            **{k: file_sha(p) for k, p in inputs.items()},
        }
        permitted = set(task["inputs"]) | {task["output"], "group", "sample_id"}
        data = {
            key: [{k: r[k] for k in permitted} for r in read_csv(path)]
            for key, path in inputs.items()
        }
        base = {"scenario_id": sid, "source_hashes": source_hashes, "fixed_slots": 3}
        if not 1 <= len(task["inputs"]) <= 8:
            rows.append(
                base
                | {
                    "status": "unsupported",
                    "reason": "Requires one to eight numeric inputs",
                    "model_calls": 0,
                    "fitting_attempts": 0,
                }
            )
            continue
        gateway = helper.ScriptedAsta("complete")
        engine = BoundAsta(
            task, data["train"], data["dev"], gateway=gateway, run_id="context-preflight-" + sid
        )
        result = engine.run()
        write_json(workspace / (sid + ".json"), result, immutable=True)
        payloads = [
            {
                "request_id": r["request_id"],
                "model": r["model"],
                "system_and_prompt_bytes": len((r["system"] + r["prompt"]).encode()),
                "max_tokens": r["max_tokens"],
                "request_sha256": sha(r),
            }
            for r in gateway.calls
        ]
        write_json(workspace / (sid + "-payloads.json"), payloads, immutable=True)
        passed = all(
            r["system_and_prompt_bytes"] <= 48000 and 1 <= r["max_tokens"] <= 4096 for r in payloads
        )
        rows.append(
            base
            | {
                "status": result["status"],
                "scripted_requests": len(payloads),
                "request_limits_passed": passed,
                "largest_payload_bytes": max(
                    (r["system_and_prompt_bytes"] for r in payloads), default=0
                ),
                "configuration_sha256": engine.configuration["sha256"],
                "result_sha256": result["sha256"],
                "fitting_attempts": result["host_submission"]["accounting"]["fitting_attempts"],
                "optimizer_evaluations": result["host_submission"]["accounting"][
                    "optimizer_evaluations"
                ],
            }
        )
        assert source_hashes == {
            "contract": file_sha(contract_path),
            **{k: file_sha(p) for k, p in inputs.items()},
        }
    value = {
        "checked_at": now(),
        "status": "passed" if all(r.get("request_limits_passed", True) for r in rows) else "failed",
        "scope": "Scripted train/dev engineering preflight, not live model conformance or independent scientific evidence. No test inputs or targets accessed. Unsupported and incomplete outcomes retained.",
        "source_is_installed_distribution": True,
        "assigned_scenarios": len(CASES),
        "fixed_slots": 3 * len(CASES),
        "cases": rows,
        "provider_payload_limit_bytes": 48000,
        "real_api_calls": 0,
        "ranking_authorized": False,
        "scientific_review": "not_assessed",
        "engine_module_sha256": file_sha(Path(inspect.getfile(BoundAsta))),
    }
    write_json(receipt, value, immutable=True)
    print(
        value["status"],
        [(r["scenario_id"], r["status"], r.get("largest_payload_bytes")) for r in rows],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    verify(args.data_root, args.workspace, args.receipt)
