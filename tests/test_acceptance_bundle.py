"""Acceptance snapshot integrity and custody checks; no API or private data."""

import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "bundle", Path(__file__).resolve().parents[1] / "scripts/build_acceptance_bundle.py"
)
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)


@pytest.fixture
def roots(tmp_path):
    result = {}
    for name in ("projects/p", "datas/d", "leaderboards/l"):
        path = tmp_path / name
        path.mkdir(parents=True)
        (path / "README.md").write_text(name)
        result[name] = path
    return result


def test_archive_reproducible_and_verifier_detects_mutation(roots, tmp_path):
    first = bundle.build(roots, tmp_path / "first.zip")
    second = bundle.build(roots, tmp_path / "second.zip")
    assert first["sha256"] == second["sha256"]
    with zipfile.ZipFile(first["archive"]) as archive:
        archive.extractall(tmp_path / "unpacked")
    delivery = tmp_path / "unpacked" / bundle.DELIVERY
    command = [sys.executable, "-I", str(delivery / "VERIFY.py")]
    assert subprocess.run(command, capture_output=True).returncode == 0
    (delivery / "datas/d/README.md").write_text("changed")
    result = subprocess.run(command, capture_output=True)
    assert result.returncode == 1
    assert "changed" in json.loads(result.stdout)["errors"][0]


@pytest.mark.parametrize("name", ["test_targets.csv.gz", "llm-api.env", "costs.sqlite"])
def test_private_payload_rejected(roots, tmp_path, name):
    (roots["datas/d"] / name).write_text("private")
    with pytest.raises(ValueError, match="Private or mutable"):
        bundle.build(roots, tmp_path / "bad.zip")
    assert not (tmp_path / "bad.zip").exists()


def test_credential_and_symlink_rejected(roots, tmp_path):
    path = roots["projects/p"] / "README.md"
    path.write_text("sk-" + "A" * 32)
    with pytest.raises(ValueError, match="credential"):
        bundle.collect(roots)
    path.unlink()
    path.symlink_to(roots["datas/d"] / "README.md")
    with pytest.raises(ValueError, match="Symlink"):
        bundle.collect(roots)


def test_cache_omissions_are_recorded_and_outputs_cannot_overwrite(roots, tmp_path):
    path = roots["projects/p"]
    (path / ".DS_Store").write_bytes(b"cache")
    result = bundle.build(roots, tmp_path / "candidate.zip")
    assert result["excluded_files"] == 1
    assert (path / ".DS_Store").read_bytes() == b"cache"
    with pytest.raises(FileExistsError):
        bundle.build(roots, tmp_path / "candidate.zip")
    with pytest.raises(ValueError, match="outside"):
        bundle.build(roots, path / "recursive.zip")
