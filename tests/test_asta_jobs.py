import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from principia_asd import adapter_jobs, asta_jobs, bound_jobs
from principia_asd.io import file_sha, read_json, sha, write_json
from principia_asd.store.ledger import CostLedger

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/verify_asta_worker.py"
spec = importlib.util.spec_from_file_location("asta_worker_fixture", SCRIPT)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


@pytest.fixture
def setup(tmp_path):
    return helper.helper().fixture(tmp_path)


def child(folder, *args):
    cfg = read_json(folder / "launch.json")
    return subprocess.run(
        [cfg["interpreter"], "-I", "-B", str(SCRIPT), "--child", str(folder), *args],
        capture_output=True,
        timeout=90,
    )


def test_asta_freezes_exact_protocol_and_only_permitted_development_inputs(setup):
    settings, scenario = setup
    folder = asta_jobs.prepare(settings, scenario)
    cfg, req, private_settings = asta_jobs.verify_binding(folder, check_environment=True)
    assert req["scope"] == asta_jobs.SCOPE and folder.name.startswith("asta-")
    assert read_json(folder / "ui.json")["method_id"] == asta_jobs.METHOD_ID
    assert set(read_json(folder / "inputs.json")) == {"contract", "train", "dev"}
    assert set(private_settings) == {"workspace"}
    assert req["limits"]["max_calls"] == 25 and req["limits"]["max_fits"] == 4
    assert req["limits"]["max_seconds"] == 2400
    assert cfg["memory_bytes"] == 4 * 1024**3 and cfg["numerical_threads"] == 1
    assert len(cfg["provider"]["profiles"]) == 4
    assert not (folder / "inputs/MUST_NOT_READ.csv").exists()
    (scenario / "train.csv").write_text("changed original")
    write_json(Path(settings["workspace"]) / "capabilities.json", {})
    assert asta_jobs.verify_binding(folder)[0] == cfg
    assert not (Path(settings["workspace"]) / "costs.sqlite").exists()
    with pytest.raises(ValueError, match="identity"):
        adapter_jobs.verify_binding(folder, adapter="paper_v2")


@pytest.mark.parametrize(
    "which", ["capabilities", "budget", "calls", "fits", "roles", "vault", "extra_column"]
)
def test_asta_preflight_refuses_unsafe_jobs_without_dispatch(setup, which):
    settings, scenario = setup
    kwargs = {}
    if which == "capabilities":
        write_json(Path(settings["workspace"]) / "capabilities.json", {})
    elif which == "budget":
        kwargs["budget"] = float("nan")
    elif which in {"calls", "fits"}:
        kwargs["limits"] = {"max_" + which: 26 if which == "calls" else 5}
    elif which == "roles":
        kwargs["roles"] = {"coder": "silent-fallback"}
    elif which == "vault":
        settings["vault"] = settings["workspace"]
    else:
        f = scenario / "train.csv"
        f.write_text(f.read_text().replace("sample_id,", "target_alias,sample_id,", 1))
    with pytest.raises((ValueError, KeyError)):
        asta_jobs.prepare(settings, scenario, **kwargs)
    assert not list(Path(settings["workspace"]).glob("bound-runs/*"))


@pytest.mark.parametrize(
    "target",
    ["request", "settings", "inputs", "capabilities", "ui", "staged", "runtime", "extra_runtime"],
)
def test_asta_mutations_fail_before_process_dispatch(setup, monkeypatch, target):
    folder = asta_jobs.prepare(*setup)
    cfg = read_json(folder / "launch.json")
    if target == "staged":
        path = folder / read_json(folder / "inputs.json")["train"]["path"]
    elif target in {"runtime", "extra_runtime"}:
        path = (
            Path(cfg["runtime_source"])
            / "principia_asd"
            / ("injected.py" if target == "extra_runtime" else "engine/bound_asta.py")
        )
    else:
        path = folder / (target + ".json")
    path.write_text((path.read_text() if path.exists() else "") + " ")
    monkeypatch.setattr(
        bound_jobs.subprocess, "Popen", lambda *a, **kw: pytest.fail("unsafe dispatch")
    )
    with pytest.raises(ValueError, match="changed"):
        bound_jobs.launch(folder)


def test_asta_launch_uses_own_entrypoint_no_credentials_and_no_duplicate(setup, monkeypatch):
    folder = asta_jobs.prepare(*setup)
    cfg = read_json(folder / "launch.json")
    captured = {}
    monkeypatch.setenv("SILICONFLOW_API_KEY", "synthetic-canary")
    monkeypatch.setenv("PYTHONPATH", "hostile")

    class Child:
        pid = 99999999

        def __init__(self, args, **kw):
            captured.update(args=args, **kw)

        def wait(self, **kw):
            return 0

    monkeypatch.setattr(bound_jobs.subprocess, "Popen", Child)
    bound_jobs.launch(folder)
    assert captured["args"][:3] == [cfg["interpreter"], "-I", "-B"]
    assert "engine.asta_worker" in captured["args"][4]
    assert captured["args"][-2:] == [cfg["runtime_source"], str(folder)]
    assert "SILICONFLOW_API_KEY" not in captured["env"] and "PYTHONPATH" not in captured["env"]
    write_json(folder / "process.json", {"pid": os.getpid()})
    with pytest.raises(ValueError, match="still alive"):
        bound_jobs.launch(folder)


@pytest.mark.parametrize(
    "count,name,role",
    [(i, name, role) for i, (name, role) in enumerate(asta_jobs.HANDOFF_ROLES.items())],
)
def test_all_25_asta_handoffs_recover_only_exact_settled_cache(setup, count, name, role):
    folder = asta_jobs.prepare(*setup)
    write_json(
        folder / "checkpoints/0000.json",
        {
            "type": "intent",
            "kind": "provider",
            "name": name,
            "state": {"engine": {"requests": count}},
        },
    )
    ledger = CostLedger(Path(setup[0]["workspace"]) / "costs.sqlite")
    rid = f"{folder.name}--asta-bound-v1--{role}--{count + 1}"
    ledger.reserve(rid, 2)
    ledger.record({"request_id": rid, "state": "unknown"})
    write_json(folder / "provider" / (sha(rid) + ".json"), {"eligibility": "worker verifies cache"})
    assert not bound_jobs.recovery(folder, ledger)[0]
    assert ledger.summary()["unknown_usage_reserved"] == 2
    completed = CostLedger(Path(setup[0]["workspace"]) / "completed-fixture.sqlite")
    completed.reserve(rid, 2)
    completed.record({"request_id": rid, "state": "completed", "actual_cny": 0.02})
    assert bound_jobs.recovery(folder, completed)[0]


@pytest.mark.parametrize(
    "name",
    ["hypothesis-5:nomination", "hypothesis-1:prior:3", "invented", "hypothesis-1:experiment"],
)
def test_unknown_asta_handoffs_never_offer_recovery(setup, name):
    folder = asta_jobs.prepare(*setup)
    write_json(
        folder / "checkpoints/0000.json",
        {
            "type": "intent",
            "kind": "provider",
            "name": name,
            "state": {"engine": {"requests": 0}},
        },
    )
    assert not bound_jobs.recovery(
        folder, CostLedger(Path(setup[0]["workspace"]) / "costs.sqlite")
    )[0]


@pytest.mark.parametrize("crash", [1, 3, 4, 6, 25])
def test_real_asta_process_recovers_without_repeating_calls_fits_or_tree_updates(setup, crash):
    folder = asta_jobs.prepare(*setup)
    for point, expected in ((crash, 91), (-1, 0), (-1, 0)):
        p = child(folder, "--crash-at", str(point))
        assert p.returncode == expected, p.stderr.decode()[-2000:]
    result = asta_jobs.verify_finished(folder, read_json(folder / "launch.json"))
    assert result["status"] == "complete"
    assert result["host_submission"]["accounting"]["fitting_attempts"] == 4
    assert result["search_tree"][0]["visits"] == 4
    assert len(result["selection"]["nominations"]) == 3
    calls = [json.loads(s) for s in (folder / "mock-dispatches.jsonl").read_text().splitlines()]
    assert len(calls) == len({c["request_id"] for c in calls}) == 25
    digest = file_sha(folder / "result.json")
    bound_jobs.launch(folder)
    assert file_sha(folder / "result.json") == digest


def test_uncommitted_asta_experiment_never_refits_or_dispatches_on_recovery(setup):
    folder = asta_jobs.prepare(*setup)
    p = child(folder, "--crash-local", "hypothesis-2:experiment")
    assert p.returncode == 92, p.stderr.decode()[-2000:]
    before = (folder / "mock-dispatches.jsonl").read_bytes()
    p = child(folder)
    assert p.returncode != 0 and b"RecoveryRequired" in p.stderr
    assert read_json(folder / "state.json")["status"] == "recovery_required"
    assert (folder / "mock-dispatches.jsonl").read_bytes() == before


@pytest.mark.parametrize("case", ["abstention", "changed_claim", "wrong_report"])
def test_asta_worker_preserves_incomplete_algorithm_outcomes(setup, case):
    folder = asta_jobs.prepare(*setup)
    p = child(folder, "--case", case)
    assert p.returncode == 0, p.stderr.decode()[-2000:]
    result = asta_jobs.verify_finished(folder, read_json(folder / "launch.json"))
    assert result["status"] == "incomplete_method_execution"
    assert len(result["selection"]["nominations"]) == 3
    assert not read_json(folder / "state.json")["ranking_authorized"]


@pytest.mark.parametrize("case", ["forbidden_file", "forbidden_network", "forbidden_write"])
def test_worker_rejects_file_and_network_operations_before_expression_execution(setup, case):
    settings, scenario = setup
    canary = scenario / "MUST_NOT_READ.csv"
    canary.write_text("protected-confirmation-canary")
    folder = asta_jobs.prepare(settings, scenario)
    before = file_sha(canary)
    p = child(folder, "--case", case)
    assert p.returncode == 0, p.stderr.decode()[-2000:]
    result = asta_jobs.verify_finished(folder, read_json(folder / "launch.json"))
    first = result["search_tree"][1]
    assert not first["valid_claim"] and not first["experiment"]["binding_valid"]
    assert first["experiment"]["fitting_attempts"] == 0
    assert result["host_submission"]["accounting"]["fitting_attempts"] == 3
    assert "protected-confirmation-canary" not in (folder / "result.json").read_text()
    assert file_sha(canary) == before and not (folder / "MUST_NOT_WRITE").exists()


@pytest.mark.parametrize("command", ["evaluate", "replay", "resume"])
def test_ordinary_cli_never_sends_asta_development_work_to_private_evaluator(
    setup, monkeypatch, command
):
    from principia_asd import cli

    folder = asta_jobs.prepare(*setup)
    if command == "resume":
        (folder / "launch.json").unlink()
    monkeypatch.setattr(
        sys,
        "argv",
        ["principia-asd", command, str(folder), "--settings", str(folder / "settings.json")],
    )
    with pytest.raises(SystemExit):
        cli.main()
