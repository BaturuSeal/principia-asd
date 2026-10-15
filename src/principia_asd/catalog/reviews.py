"""Versioned, display-only advisories; no access from the numerical evaluator."""

from importlib.resources import files

from ..io import read_json, sha


def known_advisories():
    return read_json(files("principia_asd.catalog").joinpath("review_advisories.json"))["advisories"]


def task_advisories(task):
    return [a for a in known_advisories()
            if a["task_id"] == task.get("task_id") and a["contract_sha256"] == sha(task)]
