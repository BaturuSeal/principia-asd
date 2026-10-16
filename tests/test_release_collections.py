"""Portable collection completeness and custody boundaries, without provider calls."""

import copy
import shutil
from pathlib import Path

import pytest
from test_cloud_preparation import public_fixture
from test_product_workspace import example as example

from principia_asd.io import file_sha, read_json, write_json
from principia_asd.web.collections import bundle_packs
from principia_asd.web.public_site import build_site
from principia_asd.web.server import App
from principia_asd.web.tasks import resolve_task


def extension(example, root):
    data, boards = public_fixture(example)
    scenario, _, task, settings = example
    extra = root / "collections/extra/data"
    result = root / "collections/extra/leaderboards"
    dest = extra / "scenarios" / scenario.name
    shutil.copytree(scenario, dest)
    info = read_json(dest / "scenario.json") | {
        "extends_scenario_sha256": file_sha(scenario / "scenario.json"),
        "extends_task_sha256": file_sha(scenario / "task-contracts/task-001.json"),
    }
    write_json(dest / "scenario.json", info)
    task = copy.deepcopy(task) | {
        "task_id": "P100-054.connected.v2",
        "equation_templates": ["fixture"],
    }
    write_json(dest / "task-contracts/task-001.json", task)
    write_json(extra / "EDITION.json", {"scenarios": [scenario.name]})
    write_json(result / "EDITION.json", {"version": "fixture"})
    board = read_json(boards / "scenarios/P100-054/tasks/task-001/leaderboard.json")
    board["task_id"] = task["task_id"]
    board["rules"][0]["rule_id"] = "extension-rule"
    board["rules"][0]["card"]["rule_id"] = "extension-rule"
    write_json(result / "scenarios/P100-054/tasks/task-001/leaderboard.json", board)
    manifest = root / "COLLECTIONS.json"
    write_json(
        manifest,
        {
            "collections": [
                {
                    "id": "extra",
                    "data_root": "collections/extra/data",
                    "leaderboard_root": "collections/extra/leaderboards",
                    "data_root_sha256": file_sha(extra / "EDITION.json"),
                    "leaderboard_root_sha256": file_sha(result / "EDITION.json"),
                }
            ]
        },
    )
    return data, boards, dest, manifest, settings


def test_static_site_keeps_both_frozen_tasks_and_every_rule(example, tmp_path):
    data, boards, dest, manifest, _ = extension(example, tmp_path)
    before = {str(f): file_sha(f) for f in tmp_path.rglob("*") if f.is_file()}
    site = tmp_path / "site"
    receipt = build_site(data, boards, site, preview=True, collections_manifest=manifest)
    assert (receipt["scenario_count"], receipt["task_count"], receipt["rule_count"]) == (1, 2, 2)
    tasks = read_json(site / "data/scenarios.json")[0]["tasks"]
    assert tasks[0]["task_id"] == "P100-054.connected.v2"
    assert tasks[0]["package_path"] == "collections/extra/data/scenarios/P100-054"
    assert len(read_json(site / "data/leaderboards.json")) == 2
    assert all(file_sha(Path(f)) == digest for f, digest in before.items())
    write_json(
        dest / "scenario.json",
        read_json(dest / "scenario.json") | {"extends_scenario_sha256": "wrong"},
    )
    with pytest.raises(ValueError, match="collision"):
        build_site(data, boards, tmp_path / "bad-site", preview=True, collections_manifest=manifest)


def test_companion_registers_collections_without_operator_vault_or_shared_writes(example, tmp_path):
    _, _, dest, manifest, settings = extension(example, tmp_path)
    packs = bundle_packs(manifest, tmp_path / "private")
    assert packs[0]["vault"] == str(tmp_path / "private/private-evaluator/collections/extra")
    app = App(settings | {"bundled_packs": packs})
    try:
        catalog = app.catalog()
        assert [t["task_id"] for t in catalog[0]["tasks"]] == [
            "P100-054.connected.v2",
            "P100-054.example.v1",
        ]
        selected, task = resolve_task(
            example[0], app.workspace, "P100-054.connected.v2", packs=app.local_packs()
        )
        assert selected == dest and task["task_id"] == "P100-054.connected.v2"
        assert not app.config()["api_configured"] and app.ledger.summary()["requests"] == 0
        assert not (app.workspace / "private-evaluator").exists()
    finally:
        app.pool.shutdown()
        app.server_lock.close()


@pytest.mark.parametrize("change", ["escape", "absolute", "changed_hash", "duplicate_id"])
def test_collection_manifest_rejects_unsafe_or_ambiguous_bindings(example, tmp_path, change):
    _, _, _, manifest, _ = extension(example, tmp_path)
    value = read_json(manifest)
    row = value["collections"][0]
    if change == "escape":
        row["data_root"] = "../outside"
    elif change == "absolute":
        row["data_root"] = str(tmp_path / "collections/extra/data")
    elif change == "changed_hash":
        row["data_root_sha256"] = "incorrect"
    else:
        value["collections"].append(dict(row))
    write_json(manifest, value)
    with pytest.raises(ValueError):
        bundle_packs(manifest)
