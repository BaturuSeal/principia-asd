from html.parser import HTMLParser
from urllib.parse import unquote

import pytest

from principia_asd.catalog import reviews
from principia_asd.io import file_sha, read_json, sha, write_json
from principia_asd.report_html import render_leaderboards


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.targets = []

    def handle_starttag(self, tag, attrs):
        if tag in {"a", "link"}:
            self.targets.extend(v for k, v in attrs if k == "href")


def fixture_board(tmp_path):
    root = tmp_path / "boards"
    card = {
        "rule_id": "rule-1",
        "rule_sha256": "frozen",
        "expression": "p0*x",
        "parameters": {"p0": 2},
        "method_id": "direct",
        "representation": "expression",
        "simplicity": {
            "expanded_expression": "2*x",
            "weighted_operator_count": 1,
            "free_parameters": 1,
        },
        "inputs": ["x"],
        "output": "y",
        "model_ids": [],
    }
    row = {
        "rule_id": "rule-1",
        "rule_sha256": "frozen",
        "method_id": "direct",
        "run_id": "run-1",
        "status": "complete",
        "accuracy_gate": True,
        "accuracy": {"primary": "mae", "primary_error": 0.5},
        "simplicity": card["simplicity"],
        "coverage": {"predicted": 10, "eligible": 10},
        "card": card,
    }
    board = {
        "scenario_id": "TEST",
        "task_id": "TEST.task",
        "campaign_id": "cohort",
        "rules": [row],
        "attempts": [
            {"run_id": "run-1", "method_id": "direct", "status": "complete", "rule_count": 1},
            {
                "run_id": "run-2",
                "method_id": "direct",
                "status": "failed",
                "rule_count": 0,
                "reason": "<script>unsafe</script>",
            },
        ],
        "ranking": "Accuracy gate then Pareto",
        "scientific_review": "not_assessed",
        "pareto_front_rule_ids": ["rule-1"],
    }
    task = root / "scenarios/TEST/tasks/task-001"
    write_json(task / "leaderboard.json", board)
    (task / "leaderboard.csv").write_text("rule_id\nrule-1\n")
    write_json(task / "rules/rule-1/rule-card.json", card)
    write_json(task / "rules/rule-1/evaluation-receipt.json", row)
    write_json(
        task / "rules/rule-1/program/expression.json",
        {"expression": "p0*x", "parameters": {"p0": 2}},
    )
    write_json(root / "EDITION.json", {"version": "1.0.0rc2", "campaign_id": "cohort"})
    write_json(
        root / "exports/coverage.json",
        {
            "scenarios": 1,
            "rules": 1,
            "assigned_attempt_denominator": 2,
            "status_counts": {"failed": 1},
        },
    )
    write_json(root / "exports/all-attempts.json", board["attempts"])
    (root / "exports/all-rules.csv").write_text("rule_id\nrule-1\n")
    write_json(root / "reviews/scientific-review.json", {"status": "not_assessed"})
    return root


def test_offline_rule_navigation_preserves_records_and_failed_denominator(tmp_path):
    root = fixture_board(tmp_path)
    before = {p: file_sha(p) for p in root.rglob("*") if p.is_file()}
    result = render_leaderboards(root)
    assert result == {
        "scenarios": 1,
        "rule_pages": 1,
        "attempts": 2,
        "numerical_records_modified": False,
    }
    assert {p: file_sha(p) for p in before} == before
    for path in root.rglob("*.html"):
        parser = Links()
        parser.feed(path.read_text())
        for target in parser.targets:
            resolved = (path.parent / unquote(target)).resolve()
            assert resolved.is_relative_to(root)
            assert resolved.is_file(), (path, target)
    detail = root / "scenarios/TEST/tasks/task-001/rules/rule-1/index.html"
    assert "2*x" in detail.read_text()
    assert "Pareto front" in detail.read_text()
    assert (
        "Upstream scenario preprocessing, calibration and scientific property routines are not included"
        in detail.read_text()
    )
    scenario = (root / "scenarios/TEST/tasks/task-001/index.html").read_text()
    assert "&lt;script&gt;unsafe&lt;/script&gt;" in scenario
    assert "<script>unsafe</script>" not in scenario
    assert "run-2" in scenario
    assert (
        "Upstream scenario preprocessing, calibration and scientific property routines are not included"
        in scenario
    )


def test_renderer_rejects_missing_artifacts_and_unsafe_identities(tmp_path):
    root = fixture_board(tmp_path)
    task = root / "scenarios/TEST/tasks/task-001"
    program = task / "rules/rule-1/program/expression.json"
    program.unlink()
    with pytest.raises(ValueError, match="Missing exported rule artifact"):
        render_leaderboards(root)
    board = read_json(task / "leaderboard.json")
    board["rules"][0]["rule_id"] = "../../escape"
    write_json(task / "leaderboard.json", board)
    with pytest.raises(ValueError, match="Unsafe artifact identity"):
        render_leaderboards(root)


def test_renderer_refuses_modified_metric(tmp_path):
    root = fixture_board(tmp_path)
    path = root / "scenarios/TEST/tasks/task-001/leaderboard.json"
    board = read_json(path)
    board["rules"][0]["accuracy"]["primary_error"] = 0
    write_json(path, board)
    with pytest.raises(ValueError, match="metrics differ"):
        render_leaderboards(root)


def test_advisories_require_exact_contract_and_do_not_escape_bindings(monkeypatch):
    task = {"task_id": "TEST.task", "revision": "v2", "metric": "mae"}
    advisory = {"task_id": task["task_id"], "contract_sha256": sha(task)}
    monkeypatch.setattr(reviews, "known_advisories", lambda: [advisory])
    assert reviews.task_advisories(task) == [advisory]
    assert reviews.task_advisories({**task, "revision": "v3"}) == []
    assert reviews.task_advisories({**task, "metric": "rmse"}) == []
    assert reviews.task_advisories({**task, "task_id": "OTHER.task"}) == []


def test_review_warnings_preserve_all_numeric_artifacts(tmp_path, monkeypatch):
    root = fixture_board(tmp_path)
    data = tmp_path / "data"
    task = {"task_id": "TEST.task", "revision": "v2"}
    write_json(data / "scenarios/TEST/scenario.json", {"title": "Example"})
    write_json(data / "scenarios/TEST/task-contracts/task-001.json", task)
    advisory = {
        "task_id": task["task_id"],
        "contract_sha256": sha(task),
        "scenario_id": "TEST",
        "title": "Development split requires correction",
        "detail": "Batch <A> crosses train/dev.",
        "consequence": "Historical metrics and denominators are retained.",
    }
    monkeypatch.setattr(reviews, "known_advisories", lambda: [advisory])
    before = {p: file_sha(p) for p in root.rglob("*") if p.suffix in {".json", ".csv"}}
    result = render_leaderboards(root, data)
    assert result["attempts"] == 2
    assert {p: file_sha(p) for p in before} == before
    for path in [
        root / "index.html",
        root / "scenarios/TEST/index.html",
        root / "scenarios/TEST/tasks/task-001/rules/rule-1/index.html",
    ]:
        assert advisory["title"] in path.read_text()
        assert "Batch &lt;A&gt;" in path.read_text()
        assert "Batch <A>" not in path.read_text()
    write_json(data / "scenarios/TEST/task-contracts/task-001.json", {**task, "revision": "v3"})
    render_leaderboards(root, data)
    assert advisory["title"] not in (root / "scenarios/TEST/index.html").read_text()
    assert {p: file_sha(p) for p in before} == before


def test_multiple_tasks_have_distinct_pages_and_one_scenario_hub(tmp_path):
    import shutil

    root = fixture_board(tmp_path)
    first = root / "scenarios/TEST/tasks/task-001"
    second = root / "scenarios/TEST/tasks/task-002"
    shutil.copytree(first, second)
    board = read_json(second / "leaderboard.json")
    board["task_id"] = "TEST.second-task"
    write_json(second / "leaderboard.json", board)
    coverage = read_json(root / "exports/coverage.json")
    coverage.update(rules=2, assigned_attempt_denominator=4)
    write_json(root / "exports/coverage.json", coverage)
    result = render_leaderboards(root)
    assert result["scenarios"] == 1 and result["rule_pages"] == 2
    hub = (root / "scenarios/TEST/index.html").read_text()
    assert "task-001/index.html" in hub and "task-002/index.html" in hub
    assert "TEST.task" in (first / "index.html").read_text()
    assert "TEST.second-task" in (second / "index.html").read_text()
