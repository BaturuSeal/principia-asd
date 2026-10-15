"""CLI version routing must not change a frozen method or call the legacy evaluator."""

import sys

import pytest
from test_bound_jobs import setup as setup

from principia_asd import bound_jobs, cli
from principia_asd.io import read_json, write_json


def invoke(monkeypatch, setup, args):
    settings, scenario = setup
    path = scenario.parent.parent.parent / "settings.json"
    write_json(path, settings)
    monkeypatch.setattr(sys, "argv", ["principia-asd", *args, "--settings", str(path)])
    cli.main()


@pytest.mark.parametrize("protocol", [None, "v1", "v2"])
def test_cli_new_run_freezes_selected_protocol(monkeypatch, setup, protocol):
    folders = []

    def capture(folder):
        folders.append(folder)
        assert read_json(folder / "request.json")["scope"] == (
            "engineering_only_explicit_state_" + (protocol or "v1")
        )

    monkeypatch.setattr(bound_jobs, "launch", capture)
    args = ["run", "--scenario", str(setup[1]), "--method", bound_jobs.METHOD_ID]
    if protocol:
        args.extend(["--protocol", protocol])
    invoke(monkeypatch, setup, args)
    assert len(folders) == 1
    assert read_json(folders[0] / "ui.json")["protocol_revision"] == (protocol or "v1")


@pytest.mark.parametrize("command", ["resume", "worker"])
@pytest.mark.parametrize("protocol", ["v1", "v2"])
def test_cli_resume_routes_only_saved_bound_job(monkeypatch, setup, command, protocol):
    folder = bound_jobs.prepare(setup[0], setup[1], "SYNTHETIC", protocol=protocol)
    original = (folder / "request.json").read_bytes()
    launched = []
    monkeypatch.setattr(bound_jobs, "launch", launched.append)
    invoke(monkeypatch, setup, [command, str(folder)])
    assert launched == [folder]
    assert (folder / "request.json").read_bytes() == original


@pytest.mark.parametrize("command", ["evaluate", "replay"])
@pytest.mark.parametrize("protocol", ["v1", "v2", "unrecognized"])
def test_cli_all_development_scopes_refuse_legacy_evaluation(monkeypatch, setup, command, protocol):
    folder = setup[1].parent.parent.parent / "isolated-run"
    write_json(folder / "request.json", {"scope": "engineering_only_explicit_state_" + protocol})
    with pytest.raises(SystemExit) as err:
        invoke(monkeypatch, setup, [command, str(folder)])
    assert err.value.code == 2
    assert not (folder / "evaluation.json").exists()


@pytest.mark.parametrize("command", ["resume", "worker"])
@pytest.mark.parametrize("scope,launch", [("v2", False), ("v3", True)])
def test_cli_no_fallback_for_invalid_bound_launch(monkeypatch, setup, command, scope, launch):
    folder = setup[1].parent.parent.parent / "isolated-run"
    write_json(folder / "request.json", {"scope": "engineering_only_explicit_state_" + scope})
    if launch:
        write_json(folder / "launch.json", {})
    monkeypatch.setattr(bound_jobs, "launch", lambda *a: pytest.fail("dispatched"))
    with pytest.raises(SystemExit) as err:
        invoke(monkeypatch, setup, [command, str(folder)])
    assert err.value.code == 2


def test_cli_unrelated_method_rejects_protocol(monkeypatch, setup):
    with pytest.raises(SystemExit) as err:
        invoke(
            monkeypatch,
            setup,
            ["run", "--scenario", str(setup[1]), "--method", "mean_control", "--protocol", "v2"],
        )
    assert err.value.code == 2
