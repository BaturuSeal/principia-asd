"""Read-only campaign integrity/replay audit; run against its frozen runtime_source."""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import principia_asd
from principia_asd.io import contained, file_sha, read_json, sha, write_json
from principia_asd.runtime import evaluate_run, now


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(campaign, settings, replay):
    manifest = read_json(campaign / "manifest.json")
    freeze = read_json(campaign / "submission-freeze.json")
    evaluation_freeze = read_json(campaign / "evaluation-freeze.json")
    completion = read_json(campaign / "completion.json")
    launch = read_json(campaign / "launch.json")
    source = Path(manifest["runtime_source"]) / "principia_asd"
    require(
        Path(principia_asd.__file__).resolve().parent == source.resolve(),
        "Use the frozen runtime_source on PYTHONPATH",
    )
    hashes = {str(p.relative_to(source)): file_sha(p) for p in source.rglob("*.py")}
    require(hashes == manifest["source_hashes"], "Runtime source mutation")
    require(
        file_sha(Path(launch["script"])) == manifest["driver_sha256"] == launch["driver_sha256"],
        "Driver mutation",
    )
    require(file_sha(campaign / "manifest.json") == freeze["manifest_sha256"], "Manifest mutation")
    freeze_hash = file_sha(campaign / "submission-freeze.json")
    require(
        evaluation_freeze["submission_freeze_sha256"]
        == completion["submission_freeze_sha256"]
        == freeze_hash,
        "Freeze chain mismatch",
    )
    workspace = Path(settings["workspace"])
    data = Path(settings["data_root"])
    vault = Path(settings["vault"])
    require(
        file_sha(data / "EDITION.json") == manifest["data_edition_sha256"], "Data edition mutation"
    )
    require(
        file_sha(workspace / "capabilities.json") == manifest["capabilities_sha256"],
        "Capability profile mutation",
    )
    require(
        read_json(workspace / "price-snapshot.json") == manifest["price_snapshot"],
        "Price snapshot mutation",
    )
    jobs = manifest["jobs"]
    expected = {(s, m) for s in manifest["scenarios"] for m in manifest["methods"]}
    require(len(jobs) == len(expected) == completion["attempts"], "Attempt denominator mismatch")
    require(
        {(j["scenario_id"], j["method_id"]) for j in jobs} == expected,
        "Incomplete method/scenario matrix",
    )
    ids = {j["run_id"] for j in jobs}
    require(
        len(ids) == len(jobs)
        and set(freeze["submissions"]) == ids
        and set(evaluation_freeze["evaluations"]) == ids,
        "Missing or duplicate frozen attempts",
    )
    attempts = Counter()
    rules = Counter()
    methods = defaultdict(
        lambda: {
            "attempts": 0,
            "completed": 0,
            "failed": 0,
            "rules": 0,
            "invalid_rules": 0,
            "scenarios_with_accuracy_gate_rule": 0,
        }
    )
    replayed = 0
    source_digest = sha(hashes)
    ledger_before = file_sha(workspace / "costs.sqlite")
    exported_rows = read_json(Path(settings["leaderboard_root"]) / "exports/all-rules.json")
    exported_by_id = {r["rule_id"]: r for r in exported_rows}
    require(len(exported_by_id) == len(exported_rows), "Duplicate exported rule identity")
    all_rule_ids = set()
    for job in jobs:
        run = contained(workspace / "runs", job["run_id"])
        sub = read_json(run / "submission.json")
        seal = read_json(run / "submission-freeze.json")
        binding = read_json(run / "manifest.json")
        request = read_json(run / "request.json")
        assessment = read_json(run / "evaluation.json")
        require(
            file_sha(run / "submission.json")
            == seal["submission_sha256"]
            == freeze["submissions"][job["run_id"]],
            "Submission mutation: " + job["run_id"],
        )
        require(file_sha(run / "manifest.json") == seal["manifest_sha256"], "Run manifest mutation")
        require(
            file_sha(run / "evaluation.json") == evaluation_freeze["evaluations"][job["run_id"]],
            "Evaluation mutation",
        )
        require(binding["runtime_sha256"] == source_digest, "Run runtime mismatch")
        require(
            binding["model_roles"] == request["model_roles"] == manifest["roles"],
            "Model roles changed",
        )
        require(binding["limits"] == request["limits"], "Run resource limits changed")
        require(
            binding["method"]["method_id"]
            == request["method_id"]
            == sub["method_id"]
            == job["method_id"],
            "Method identity mismatch",
        )
        require(
            sub["scenario_id"] == job["scenario_id"] == binding["scenario_id"],
            "Scenario identity mismatch",
        )
        scenario = contained(data, "scenarios/" + job["scenario_id"])
        require(Path(request["scenario_path"]).resolve() == scenario, "Scenario path changed")
        contract = read_json(scenario / "task-contracts/task-001.json")
        for name, path in {
            "contract": scenario / "task-contracts/task-001.json",
            "train": contained(scenario, contract["split"]["train"]),
            "dev": contained(scenario, contract["split"]["dev"]),
        }.items():
            require(file_sha(path) == binding["input_hashes"][name], "Development input mutation")
        require(
            seal["at"] <= freeze["at"] <= assessment["evaluated_at"] <= evaluation_freeze["at"],
            "Evaluation occurred before the global freeze",
        )
        require(
            assessment["final_assessment_model_calls"] == 0, "Final assessment reports model calls"
        )
        require(
            assessment["submission_sha256"] == seal["submission_sha256"],
            "Assessment submission mismatch",
        )
        card_ids = {r["rule_id"] for r in sub["rules"]}
        require(
            len(card_ids) == len(sub["rules"])
            and card_ids == {r["rule_id"] for r in assessment["receipts"]},
            "Rule/receipt coverage mismatch",
        )
        require(not all_rule_ids.intersection(card_ids), "Duplicate rule identity across runs")
        all_rule_ids.update(card_ids)
        cards = {c["rule_id"]: c for c in sub["rules"]}
        for card in sub["rules"]:
            require(
                sha({k: v for k, v in card.items() if k != "rule_sha256"}) == card["rule_sha256"],
                "Rule content hash mismatch",
            )
        for receipt in assessment["receipts"]:
            exported = exported_by_id[receipt["rule_id"]]
            require(
                all(exported.get(k) == v for k, v in receipt.items()),
                "Export differs from immutable assessment",
            )
            require(
                exported["card"] == cards[receipt["rule_id"]], "Export differs from immutable rule"
            )
            rules[receipt["status"]] += 1
            rules["accuracy_gate_passed"] += int(
                receipt["accuracy_gate"] and receipt["status"] == "complete"
            )
        if replay:
            require(
                evaluate_run(run, vault, replay=True).get("replay_verified"),
                "Replay did not verify",
            )
            replayed += 1
        attempts[sub["status"]] += 1
        m = methods[job["method_id"]]
        m["attempts"] += 1
        m["completed"] += int(sub["status"] == "complete")
        m["failed"] += int(sub["status"] == "failed")
        m["rules"] += len(sub["rules"])
        m["invalid_rules"] += sum(r["status"] != "complete" for r in assessment["receipts"])
        m["scenarios_with_accuracy_gate_rule"] += int(
            any(r["status"] == "complete" and r["accuracy_gate"] for r in assessment["receipts"])
        )
    require(all_rule_ids == set(exported_by_id), "Extra or missing canonical rule exports")
    require(len(all_rule_ids) == completion["rules"], "Rule denominator mismatch")
    require(
        file_sha(workspace / "costs.sqlite") == ledger_before,
        "Ledger changed during read-only audit; inspect concurrent activity",
    )
    return {
        "checked_at": now(),
        "campaign_id": manifest["campaign_id"],
        "status": "passed",
        "assigned_attempts": len(jobs),
        "attempt_statuses": dict(attempts),
        "rules": len(all_rule_ids),
        "rule_evidence_profile": dict(rules),
        "methods": dict(methods),
        "replayed_attempts": replayed,
        "runtime_sha256": source_digest,
        "submission_freeze_sha256": freeze_hash,
        "evaluation_freeze_sha256": file_sha(campaign / "evaluation-freeze.json"),
        "zero_api_assessment_and_replay": True,
        "ledger_unchanged": True,
        "engineering_exposed_scenarios": manifest["engineering_exposed_scenarios"],
        "scientific_review": "not_assessed",
        "release_ready": False,
        "scope": "Frozen source/config/data integrity, complete fixed denominator, global freeze timing, exact deterministic receipt replay and canonical export parity; not source-rights or scientific-validity approval",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", type=Path, required=True)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    result = verify(args.campaign, read_json(args.settings), args.replay)
    write_json(args.output, result)
    print(json.dumps(result, indent=2))
