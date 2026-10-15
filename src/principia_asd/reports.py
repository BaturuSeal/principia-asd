"""Rebuild portable JSON/CSV/HTML solely from frozen submissions and receipts."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from .evaluate.metrics import pareto_front
from .io import file_sha, read_json, sha, write_json
from .methods.registry import METHODS
from .report_html import render_leaderboards
from .store.ledger import CostLedger


def export_campaign(campaign, settings):
    manifest = read_json(campaign / "manifest.json")
    freeze = read_json(campaign / "submission-freeze.json")
    if file_sha(campaign / "manifest.json") != freeze["manifest_sha256"]:
        raise ValueError("Campaign manifest mutation")
    runs = Path(settings["workspace"]) / "runs"
    # Aggregate only complete, frozen cohorts from this exact data edition.
    campaign_receipts = {
        manifest["campaign_id"]: {"manifest": manifest, "submission_freeze": freeze}
    }
    historical_attempts = []
    for other in sorted(campaign.parent.glob("*/manifest.json")):
        if other.parent == campaign or not (other.parent / "evaluation-freeze.json").exists():
            continue
        candidate = read_json(other)
        if candidate["data_edition_sha256"] != manifest["data_edition_sha256"]:
            continue
        retirement = other.parent / "retirement.json"
        if retirement.exists():
            note = read_json(retirement)
            for job in candidate["jobs"]:
                submission = read_json(runs / job["run_id"] / "submission.json")
                historical_attempts.append(
                    job
                    | {
                        "status": submission["status"],
                        "rules": len(submission["rules"]),
                        "included_in_current_ranking": False,
                        "reason": note["reason"],
                    }
                )
            continue
        sealed = read_json(other.parent / "submission-freeze.json")
        if file_sha(other) != sealed["manifest_sha256"]:
            raise ValueError("Earlier campaign manifest mutation")
        campaign_receipts[candidate["campaign_id"]] = {
            "manifest": candidate,
            "submission_freeze": sealed,
        }
    for cid, record in campaign_receipts.items():
        record["evaluation_freeze"] = read_json(campaign.parent / cid / "evaluation-freeze.json")
        for job in record["manifest"]["jobs"]:
            if (
                file_sha(runs / job["run_id"] / "evaluation.json")
                != record["evaluation_freeze"]["evaluations"][job["run_id"]]
            ):
                raise ValueError("Evaluation receipt mutation")
    all_campaign_receipts = dict(campaign_receipts)
    engineering_history = []
    primary = [
        (cid, r) for cid, r in campaign_receipts.items() if r["manifest"].get("track") == "primary"
    ]
    if primary:
        primary_id, primary_record = max(primary, key=lambda item: item[1]["manifest"]["created"])
        for cid, record in campaign_receipts.items():
            if cid == primary_id:
                continue
            for job in record["manifest"]["jobs"]:
                folder = runs / job["run_id"]
                sub = read_json(folder / "submission.json")
                if (
                    file_sha(folder / "submission.json")
                    != record["submission_freeze"]["submissions"][job["run_id"]]
                ):
                    raise ValueError("Historical submission mutation")
                engineering_history.append(
                    job
                    | {
                        "campaign_id": cid,
                        "status": sub["status"],
                        "reason": sub.get("reason"),
                        "rules": sub["rules"],
                        "accounting": sub.get("accounting", {}),
                        "evaluation": read_json(folder / "evaluation.json"),
                        "included_in_primary_ranking": False,
                    }
                )
        campaign_receipts = {primary_id: primary_record}
        manifest = primary_record["manifest"]
        freeze = primary_record["submission_freeze"]
    jobs = [
        job | {"campaign_id": cid}
        for cid, record in campaign_receipts.items()
        for job in record["manifest"]["jobs"]
    ]
    if len({j["run_id"] for j in jobs}) != len(jobs):
        raise ValueError("Duplicate assigned attempt identity")
    manifest = manifest | {"jobs": jobs, "scenarios": sorted({j["scenario_id"] for j in jobs})}
    freeze = freeze | {
        "submissions": {
            k: v
            for r in campaign_receipts.values()
            for k, v in r["submission_freeze"]["submissions"].items()
        }
    }
    root = Path(settings["leaderboard_root"])
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    summaries = []
    all_attempts = []
    task_jobs = {}
    contract_hashes = {}
    for job in manifest["jobs"]:
        submission_path = runs / job["run_id"] / "submission.json"
        if file_sha(submission_path) != freeze["submissions"][job["run_id"]]:
            raise ValueError("Frozen submission changed")
        contract = read_json(submission_path)["contract"]
        task_id = contract["task_id"]
        if job.get("task_id", task_id) != task_id:
            raise ValueError("Assigned task differs from the submitted task")
        key = (job["scenario_id"], task_id)
        if key in contract_hashes and contract_hashes[key] != sha(contract):
            raise ValueError("One task identity refers to different scientific contracts")
        contract_hashes[key] = sha(contract)
        task_jobs.setdefault(key, []).append(job)
    for (sid, task_id), assigned in task_jobs.items():
        source_contracts = (
            Path(settings["data_root"]) / "scenarios" / sid / "task-contracts"
            if settings.get("data_root")
            else None
        )
        matching = (
            [
                p
                for p in sorted(source_contracts.glob("*.json"))
                if read_json(p)["task_id"] == task_id
            ]
            if source_contracts
            else []
        )
        if len(matching) > 1:
            raise ValueError("Duplicate task identity in the scenario package")
        task_name = (
            matching[0].stem
            if matching
            else "task-001"
            if sum(s == sid for s, _ in task_jobs) == 1
            else "task-" + sha(task_id)[:16]
        )
        target = root / "scenarios" / sid / "tasks" / task_name
        rules = []
        attempts = []
        for job in assigned:
            p = runs / job["run_id"]
            sub = read_json(p / "submission.json")
            receipt = read_json(p / "evaluation.json")
            if file_sha(p / "submission.json") != freeze["submissions"][job["run_id"]]:
                raise ValueError("Frozen submission changed")
            attempt = {
                "run_id": job["run_id"],
                "campaign_id": job["campaign_id"],
                "method_id": job["method_id"],
                "scenario_id": sid,
                "task_id": task_id,
                "status": sub["status"],
                "reason": sub.get("reason"),
                "rule_count": len(sub["rules"]),
                "accounting": sub.get("accounting", {}),
            }
            attempts.append(attempt)
            cards = {r["rule_id"]: r for r in sub["rules"]}
            for result in receipt["receipts"]:
                card = cards[result["rule_id"]]
                row = result | {
                    "campaign_id": job["campaign_id"],
                    "card": card,
                    "expression": card["expression"],
                    "model_ids": card.get("model_ids", []),
                    "scenario_id": sid,
                    "task_id": sub["contract"]["task_id"],
                }
                rules.append(row)
                dest = target / "rules" / result["rule_id"]
                write_json(dest / "rule-card.json", card)
                write_json(dest / "evaluation-receipt.json", result)
                write_json(
                    dest / "program/expression.json",
                    {
                        "expression": card["expression"],
                        "parameters": card.get("parameters", {}),
                        "tree": card.get("tree"),
                        "representation": card["representation"],
                        "runtime": "principia-asd 1.0.0rc2",
                    },
                )
        rules.sort(
            key=lambda r: (
                not bool(r.get("accuracy_gate")),
                r["accuracy"]["primary_error"]
                if r["accuracy"]["primary_error"] is not None
                else float("inf"),
                r["simplicity"]["weighted_operator_count"],
            )
        )
        board = {
            "version": "1.0.0rc2",
            "scenario_id": sid,
            "task_id": task_id,
            "campaign_id": manifest["campaign_id"],
            "campaign_ids": sorted(campaign_receipts),
            "track": "primary" if primary else "engineering",
            "rules": rules,
            "attempts": attempts,
            "pareto_front_rule_ids": [r["rule_id"] for r in pareto_front(rules)],
            "ranking": "Within-task accuracy gate then accuracy/expanded-complexity Pareto; sensitivity diagnostic only",
            "scientific_review": "not_assessed",
            "exposure": "retrospective-open-test",
        }
        write_json(target / "leaderboard.json", board)
        text = io.StringIO()
        fields = [
            "rule_id",
            "method_id",
            "status",
            "primary_error",
            "operators",
            "parameters",
            "coverage",
            "accuracy_gate",
        ]
        w = csv.DictWriter(text, fieldnames=fields)
        w.writeheader()
        for r in rules:
            w.writerow(
                {
                    "rule_id": r["rule_id"],
                    "method_id": r["method_id"],
                    "status": r["status"],
                    "primary_error": r["accuracy"]["primary_error"],
                    "operators": r["simplicity"]["weighted_operator_count"],
                    "parameters": r["simplicity"]["free_parameters"],
                    "coverage": r["coverage"]["fraction"],
                    "accuracy_gate": r["accuracy_gate"],
                }
            )
        (target / "leaderboard.csv").write_text(text.getvalue())
        summary = {
            "scenario_id": sid,
            "task_id": task_id,
            "rule_count": len(rules),
            "attempts": len(attempts),
            "complete_attempts": sum(a["status"] == "complete" for a in attempts),
            "failed_attempts": sum(a["status"] == "failed" for a in attempts),
        }
        summaries.append(summary)
        rows.extend(rules)
        all_attempts.extend(attempts)
    task_summaries = summaries
    summaries = []
    for sid in manifest["scenarios"]:
        tasks = [row for row in task_summaries if row["scenario_id"] == sid]
        summary = {
            "scenario_id": sid,
            "tasks": tasks,
            **{
                field: sum(row[field] for row in tasks)
                for field in ("rule_count", "attempts", "complete_attempts", "failed_attempts")
            },
        }
        write_json(root / "scenarios" / sid / "summary.json", summary)
        summaries.append(summary)
    write_json(
        root / "EDITION.json",
        {
            "version": "1.0.0rc2",
            "edition_id": "rules-v2",
            "campaign_id": manifest["campaign_id"],
            "campaign_ids": sorted(campaign_receipts),
            "scenario_count": len(summaries),
            "release_status": "release_candidate",
            "scientific_review": "not_assessed",
        },
    )
    write_json(root / "exports/all-rules.json", rows)
    flat = io.StringIO()
    writer = csv.DictWriter(
        flat,
        fieldnames=[
            "scenario_id",
            "task_id",
            "rule_id",
            "method_id",
            "campaign_id",
            "status",
            "primary_error",
            "operators",
            "parameters",
            "coverage",
            "scientific_review",
        ],
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                k: row[k]
                for k in [
                    "scenario_id",
                    "task_id",
                    "rule_id",
                    "method_id",
                    "campaign_id",
                    "status",
                    "scientific_review",
                ]
            }
            | {
                "primary_error": row["accuracy"]["primary_error"],
                "operators": row["simplicity"]["weighted_operator_count"],
                "parameters": row["simplicity"]["free_parameters"],
                "coverage": row["coverage"]["fraction"],
            }
        )
    (root / "exports/all-rules.csv").write_text(flat.getvalue())
    write_json(root / "exports/all-attempts.json", all_attempts)
    write_json(root / "exports/historical-attempts.json", historical_attempts)
    write_json(root / "exports/engineering-history.json", engineering_history)
    write_json(root / "exports/scenario-summary.json", summaries)
    write_json(
        root / "exports/coverage.json",
        {
            "scenarios": len(summaries),
            "attempts": len(all_attempts),
            "rules": len(rows),
            "status_counts": {
                s: sum(a["status"] == s for a in all_attempts)
                for s in {a["status"] for a in all_attempts}
            },
            "assigned_attempt_denominator": len(manifest["jobs"]),
            "superseded_engineering_attempts": len(historical_attempts),
            "separate_engineering_attempts": len(engineering_history),
            "track": "primary" if primary else "engineering",
        },
    )
    write_json(
        root / "exports/costs.json",
        CostLedger(Path(settings["workspace"]) / "costs.sqlite").summary(),
    )
    write_json(root / "methods/method-registry.json", [m.as_dict() for m in METHODS.values()])
    for cid, record in all_campaign_receipts.items():
        # Machine-specific snapshot paths are not public release artifacts.
        portable = {k: v for k, v in record["manifest"].items() if k != "runtime_source"}
        write_json(root / "receipts/campaigns" / cid / "manifest.json", portable)
        write_json(
            root / "receipts/campaigns" / cid / "submission-freeze.json",
            record["submission_freeze"],
        )
        write_json(
            root / "receipts/campaigns" / cid / "evaluation-freeze.json",
            record["evaluation_freeze"],
        )
    write_json(
        root / "receipts/campaign-freeze.json",
        {
            "campaign_ids": sorted(campaign_receipts),
            "assigned_attempt_denominator": len(jobs),
            "all_submissions_frozen": True,
        },
    )
    write_json(
        root / "reviews/scientific-review.json",
        {
            "status": "not_assessed",
            "reason": "Strong-model literature-grounded scientific review has not been completed",
        },
    )
    (root / "README.md").write_text(
        "# Per-scenario rule leaderboards\n\nRebuilt from frozen submissions and deterministic receipts. See index.html, exports/coverage.json and the per-task JSON/CSV records. Unsupported and failed attempts remain in the denominator. The earlier shared-formula preview has been withdrawn and preserved in the private audit archive.\n"
    )
    render_leaderboards(root, Path(settings["data_root"]) if settings.get("data_root") else None)
    return {"scenarios": len(summaries), "rules": len(rows), "attempts": len(all_attempts)}
