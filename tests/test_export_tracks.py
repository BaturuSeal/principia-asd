from principia_asd.io import file_sha, read_json, write_json
from principia_asd.reports import export_campaign


def test_primary_denominator_and_engineering_history_remain_separate(tmp_path):
    workspace = tmp_path / "work"
    boards = tmp_path / "boards"
    settings = {"workspace": str(workspace), "leaderboard_root": str(boards)}
    for cid, track in [("pilot", "engineering"), ("full", "primary")]:
        run = workspace / "runs" / cid
        campaign = workspace / "campaigns" / cid
        manifest = {
            "version": "1.0.0rc2",
            "campaign_id": cid,
            "track": track,
            "created": "2026-10-11",
            "data_edition_sha256": "same-immutable-edition",
            "scenarios": ["TEST"],
            "jobs": [{"run_id": cid, "method_id": "direct", "scenario_id": "TEST"}],
        }
        write_json(
            run / "submission.json",
            {
                "status": "failed",
                "reason": "Engineering fixture",
                "rules": [],
                "contract": {"task_id": "TEST"},
            },
        )
        write_json(run / "evaluation.json", {"receipts": []})
        write_json(campaign / "manifest.json", manifest)
        write_json(
            campaign / "submission-freeze.json",
            {
                "manifest_sha256": file_sha(campaign / "manifest.json"),
                "submissions": {cid: file_sha(run / "submission.json")},
            },
        )
        write_json(
            campaign / "evaluation-freeze.json",
            {"evaluations": {cid: file_sha(run / "evaluation.json")}},
        )
    export_campaign(workspace / "campaigns/pilot", settings)
    coverage = read_json(boards / "exports/coverage.json")
    assert coverage["assigned_attempt_denominator"] == 1
    assert coverage["status_counts"] == {"failed": 1}
    assert coverage["separate_engineering_attempts"] == 1
    assert read_json(boards / "exports/engineering-history.json")[0]["run_id"] == "pilot"


def test_distinct_tasks_keep_separate_exports_and_failed_denominators(tmp_path):
    workspace, boards, data = (tmp_path / name for name in ["work", "boards", "data"])
    campaign = workspace / "campaigns/multitask"
    jobs, submissions, evaluations = [], {}, {}
    write_json(data / "scenarios/TEST/scenario.json", {"title": "Two scientific questions"})
    for index in [1, 2]:
        task = {"task_id": f"TEST.question-{index}", "inputs": ["x"], "output": f"y{index}"}
        write_json(data / f"scenarios/TEST/task-contracts/task-{index:03}.json", task)
        run = workspace / "runs" / f"run-{index}"
        write_json(run / "submission.json", {"status": "failed", "rules": [], "contract": task})
        write_json(run / "evaluation.json", {"receipts": []})
        jobs.append(
            {
                "run_id": run.name,
                "scenario_id": "TEST",
                "method_id": "direct",
                "task_id": task["task_id"],
            }
        )
        submissions[run.name] = file_sha(run / "submission.json")
        evaluations[run.name] = file_sha(run / "evaluation.json")
    write_json(
        campaign / "manifest.json",
        {
            "version": "1.0.0rc2",
            "campaign_id": "multitask",
            "track": "primary",
            "created": "2026-10-14",
            "data_edition_sha256": "frozen",
            "scenarios": ["TEST"],
            "jobs": jobs,
        },
    )
    write_json(
        campaign / "submission-freeze.json",
        {"manifest_sha256": file_sha(campaign / "manifest.json"), "submissions": submissions},
    )
    write_json(campaign / "evaluation-freeze.json", {"evaluations": evaluations})
    result = export_campaign(
        campaign,
        {"workspace": str(workspace), "leaderboard_root": str(boards), "data_root": str(data)},
    )
    assert result == {"scenarios": 1, "rules": 0, "attempts": 2}
    for index in [1, 2]:
        board = read_json(boards / f"scenarios/TEST/tasks/task-{index:03}/leaderboard.json")
        assert board["task_id"] == f"TEST.question-{index}"
        assert len(board["attempts"]) == 1
        assert board["attempts"][0]["status"] == "failed"
        assert board["attempts"][0]["task_id"] == board["task_id"]
    summary = read_json(boards / "scenarios/TEST/summary.json")
    assert summary["attempts"] == summary["failed_attempts"] == 2
    assert len(summary["tasks"]) == 2
    hub = (boards / "scenarios/TEST/index.html").read_text()
    assert "tasks/task-001/index.html" in hub and "tasks/task-002/index.html" in hub
