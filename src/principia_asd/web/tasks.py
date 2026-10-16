"""Local task variants with isolated identities and development-only custody."""

from __future__ import annotations

import copy
import shutil
import uuid
from pathlib import Path

from ..catalog.presentation import variable
from ..contracts.schema import validate_contract
from ..io import contained, file_sha, read_csv, read_json, sha, write_csv, write_json


def task_entries(scenario, workspace, *, packs=None):
    scenario = Path(scenario)
    entries = [(scenario, p) for p in sorted((scenario / "task-contracts").glob("*.json"))]
    if packs is None:
        pack_file = Path(workspace) / "scenario-packs.json" if workspace else None
        packs = read_json(pack_file).get("packs", []) if pack_file and pack_file.exists() else []
    for pack in packs:
        extension = Path(pack["data_root"]) / "scenarios" / scenario.name
        if extension.resolve() == scenario.resolve() or not (extension / "scenario.json").exists():
            continue
        info = read_json(extension / "scenario.json")
        if info.get("extends_scenario_sha256") != file_sha(scenario / "scenario.json"):
            raise ValueError("Scenario task extension does not match the preserved base identity")
        if info.get("extends_task_sha256") != file_sha(scenario / "task-contracts/task-001.json"):
            raise ValueError("Scenario task extension does not match the preserved base contract")
        entries.extend(
            (extension, p) for p in sorted((extension / "task-contracts").glob("*.json"))
        )
    ids = [read_json(p).get("task_id") for _, p in entries]
    # Legacy single-contract callers may omit task_id. Multiple contracts must
    # have explicit, distinct identities to avoid silently selecting a vault.
    if len(entries) > 1 and (None in ids or len(ids) != len(set(ids))):
        raise ValueError("Duplicate task identity across scenario editions")
    # Reviewed connected-equation tasks are the default preview; historical tasks
    # remain individually selectable with their original contracts and results.
    entries.sort(key=lambda pair: not bool(read_json(pair[1]).get("equation_templates")))
    for path in sorted((Path(workspace) / "imports").glob("*/scenario.json")) if workspace else []:
        info = read_json(path)
        if info.get("parent_scenario_id") == scenario.name and info.get("custom_task"):
            entries.append((path.parent, path.parent / "task-contracts/task-001.json"))
    return entries


def resolve_task(scenario, workspace, task_id=None, *, packs=None):
    entries = task_entries(scenario, workspace, packs=packs)
    matches = [(p, f) for p, f in entries if not task_id or read_json(f)["task_id"] == task_id]
    if not matches:
        raise ValueError("Select a task belonging to this scenario")
    path, contract = matches[0]
    if contract.name == "task-001.json":
        return path, read_json(contract)
    # Older workers use task-001.json: stage an exact copy, never rewrite a public package.
    task = read_json(contract)
    files = {key: contained(path, task["split"][key]) for key in ("train", "dev", "test")}
    key = sha({"contract": file_sha(contract), "files": {k: file_sha(p) for k, p in files.items()}})
    staged = Path(workspace) / "imports" / ("STAGED-" + key[:24]) / task["scenario_id"]
    if not (staged / "scenario.json").exists():
        for kind, source in files.items():
            destination = contained(staged, task["split"][kind])
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        write_json(staged / "task-contracts/task-001.json", task, immutable=True)
        info = read_json(path / "scenario.json") | {"presentation_staging": True}
        write_json(staged / "scenario.json", info, immutable=True)
    if file_sha(staged / "task-contracts/task-001.json") != file_sha(contract):
        raise ValueError("Staged task identity changed")
    for kind, source in files.items():
        if file_sha(contained(staged, task["split"][kind])) != file_sha(source):
            raise ValueError("Staged task data changed")
    return staged, task


def create_task(scenario, workspace, payload, *, packs=None):
    source, base = resolve_task(scenario, workspace, payload.get("base_task_id"), packs=packs)
    if base.get("assessment_policy") == "development_only":
        raise ValueError("Create a task from a preset task, not from another custom variant")
    allowed = set(base["inputs"]) | {base["output"]}
    inputs, output = payload.get("inputs"), payload.get("output")
    if not isinstance(inputs, list) or not inputs or not all(isinstance(k, str) for k in inputs):
        raise ValueError("Choose at least one numeric input")
    if (
        len(inputs) != len(set(inputs))
        or not set(inputs) <= allowed
        or output not in allowed
        or output in inputs
    ):
        raise ValueError("Inputs and output must be distinct available numeric variables")
    title = str(payload.get("title", "")).strip()
    if not 3 <= len(title) <= 120:
        raise ValueError("Give the task a descriptive name of 3–120 characters")
    task = copy.deepcopy(base)
    # A changed prediction direction does not inherit the original constitutive prior.
    task.pop("equation_templates", None)
    ident = "TASK-" + uuid.uuid4().hex[:16]
    task.update(
        scenario_id=ident,
        task_id=ident + ".v1",
        title=title,
        inputs=inputs,
        output=output,
        output_description=variable(base, output)["description"],
        output_units=variable(base, output)["units"],
        input_units={k: variable(base, k)["units"] for k in inputs},
        variable_descriptions={k: variable(base, k)["description"] for k in [*inputs, output]},
        assessment_policy="development_only",
        test_exposure="local-user-split",
        positive_prediction=False,
        nonnegative_prediction=False,
        metric={"primary": "mae", "aggregation": "equal_group_mean"},
        source_task=base["task_id"],
        parent_scenario_id=Path(scenario).name,
        observation_window="Custom input/output question using the original train/dev group partitions. Timing, units and scientific meaning require review for this new question.",
        custody="No test data or evaluator is inherited. Development results only.",
    )
    for key in ("source_contract_sha256", "accuracy_gate"):
        task.pop(key, None)
    task["stability"]["ranking"] = False
    task["split"] = {
        **task["split"],
        "train": "public/train.csv.gz",
        "dev": "public/dev.csv.gz",
        "test": "public/test_inputs.csv.gz",
    }
    if errors := validate_contract(task):
        raise ValueError("; ".join(errors))
    # Reads only allowed train/dev columns; final targets and public test inputs are not opened.
    fields = ["sample_id", "group", *inputs, output]
    chunks = {
        part: [
            {k: row[k] for k in fields} for row in read_csv(contained(source, base["split"][part]))
        ]
        for part in ("train", "dev")
    }
    for key in inputs:
        if all(row[key] == row[output] for rows in chunks.values() for row in rows):
            raise ValueError("An input is an exact alias of the requested output: " + key)
    dest = Path(workspace) / "imports" / ident
    for part, rows in chunks.items():
        write_csv(dest / task["split"][part], rows, fields)
    write_csv(dest / task["split"]["test"], [], fields[:-1])
    write_json(dest / "task-contracts/task-001.json", task, immutable=True)
    info = read_json(source / "scenario.json")
    write_json(
        dest / "scenario.json",
        info
        | {
            "scenario_id": ident,
            "parent_scenario_id": Path(scenario).name,
            "custom_task": True,
            "title": title,
            "publication_authorized": False,
            "rows": {**{p: len(rows) for p, rows in chunks.items()}, "test": 0},
            "source_task_sha256": sha(base),
            "source_partition_hashes": {
                p: file_sha(contained(source, base["split"][p])) for p in chunks
            },
        },
        immutable=True,
    )
    return {
        "scenario_id": Path(scenario).name,
        "task_id": task["task_id"],
        "assessment_policy": "development_only",
    }
