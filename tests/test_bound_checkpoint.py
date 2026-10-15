import copy
import fcntl
import json

import pytest
from test_bound_engine import FixtureGateway, fixture

from principia_asd.engine.bound_checkpoint import DurableBoundRun, RecoveryRequired
from principia_asd.engine.bound_engine import BoundEngine
from principia_asd.io import read_json, sha, write_json


class PowerLoss(BaseException):
    pass


class SettledGateway(FixtureGateway):
    def __init__(self, crash_after=None):
        super().__init__()
        self.receipts, self.recovered = {}, []
        self.crash_after = crash_after

    def complete(self, **request):
        assert request["request_id"] not in self.receipts, "paid call replayed"
        response = super().complete(**request)
        self.receipts[request["request_id"]] = (sha(request), response)
        if len(self.calls) == self.crash_after:
            self.crash_after = None
            raise PowerLoss()
        return response

    def recover_completed(self, **request):
        digest, response = self.receipts[request["request_id"]]
        assert digest == sha(request), "resumed payload changed"
        self.recovered.append(request["request_id"])
        return copy.deepcopy(response)


def runner(path, gateway, hook=lambda _: None, task=None, **kw):
    t, train, dev = fixture()
    e = BoundEngine(task or t, train, dev, gateway=gateway, run_id="durability-fixture", **kw)
    return DurableBoundRun(
        e, path, provider_binding={"fixture": "scripted-zero-api"}, after_record=hook
    )


@pytest.mark.parametrize("boundary", range(15))
def test_every_committed_boundary_resumes_without_repeating_work(tmp_path, boundary):
    g = SettledGateway()

    def stop(r):
        if r["type"] == "commit" and r["sequence"] // 2 == boundary:
            raise PowerLoss()

    first = runner(tmp_path, g, stop)
    with pytest.raises(PowerLoss):
        first.run()
    committed = read_json(sorted((tmp_path / "checkpoints").glob("*.json"))[-1])
    second = runner(tmp_path, g)
    result = second.run()
    assert result["status"] == "complete", result["failure"]
    assert len(g.calls) == len({c["request_id"] for c in g.calls}) == 7
    assert result["host_submission"]["accounting"]["fitting_attempts"] == 6
    assert result["model_requests"] == 7
    assert committed["state"]["host"]["fits"] <= second.engine.host.fits
    assert runner(tmp_path, g).run() == result
    assert len(g.calls) == 7


@pytest.mark.parametrize("call", range(1, 8))
def test_crash_after_settlement_reads_cache_and_preserves_frozen_report_payload(tmp_path, call):
    g = SettledGateway(crash_after=call)
    with pytest.raises(PowerLoss):
        runner(tmp_path, g).run()
    result = runner(tmp_path, g).run()
    assert result["status"] == "complete", result["failure"]
    assert len(g.calls) == result["model_requests"] == 7
    assert len(g.recovered) == 1
    assert result["host_submission"]["accounting"]["fitting_attempts"] == 6
    assert result["host_submission"]["accounting"]["optimizer_evaluations"] == 46


def test_unsettled_call_is_never_replayed_and_reservation_boundary_remains(tmp_path):
    g = SettledGateway()

    def stop(r):
        if r["type"] == "intent" and r["name"] == "plan-0":
            raise PowerLoss()

    with pytest.raises(PowerLoss):
        runner(tmp_path, g, stop).run()
    before = {p.name: p.read_bytes() for p in (tmp_path / "checkpoints").glob("*.json")}
    for _ in range(2):
        with pytest.raises(RecoveryRequired, match="no verified settled response"):
            runner(tmp_path, g).run()
    assert not g.calls
    assert before == {p.name: p.read_bytes() for p in (tmp_path / "checkpoints").glob("*.json")}
    assert not (tmp_path / "result.json").exists()


def test_interrupted_fit_group_blocks_instead_of_resetting_numerical_budget(tmp_path):
    g = SettledGateway()

    def stop(r):
        if r["type"] == "intent" and r["name"] == "experiments-0":
            raise PowerLoss()

    with pytest.raises(PowerLoss):
        runner(tmp_path, g, stop).run()
    with pytest.raises(RecoveryRequired, match="numerical work.*unknown"):
        runner(tmp_path, g).run()
    assert len(g.calls) == 2


def test_context_and_configuration_change_refused(tmp_path):
    g = SettledGateway()
    runner(tmp_path, g).run()
    changed = fixture()[0] | {"title": "changed contract"}
    with pytest.raises(ValueError, match="configuration changed"):
        runner(tmp_path, g, task=changed).run()
    with pytest.raises(ValueError, match="configuration changed"):
        runner(tmp_path, g, limits={"max_calls": 8}).run()
    r = runner(tmp_path, g)
    r.binding["provider"]["fixture"] = "other"
    with pytest.raises(ValueError, match="configuration changed"):
        r.run()
    r = runner(tmp_path, g)
    r.binding["runtime"]["sources_sha256"] = "different"
    with pytest.raises(ValueError, match="configuration changed"):
        r.run()
    assert len(g.calls) == 7


@pytest.mark.parametrize("target", ["checkpoint", "result", "gap"])
def test_mutation_or_missing_record_refused(tmp_path, target):
    g = SettledGateway()
    runner(tmp_path, g).run()
    if target == "gap":
        (tmp_path / "checkpoints/0002.json").unlink()
    elif target == "checkpoint":
        p = tmp_path / "checkpoints/0001.json"
        d = read_json(p)
        d["state"]["host"]["fits"] = 0
        write_json(p, d)
    else:
        p = tmp_path / "result.json"
        d = read_json(p)
        d["result"]["status"] = "invented"
        write_json(p, d)
    with pytest.raises(ValueError, match="integrity|changed"):
        runner(tmp_path, g).run()
    assert len(g.calls) == 7


def test_duplicate_worker_lock_denied(tmp_path):
    with (tmp_path / "worker.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RecoveryRequired, match="Another worker"):
            runner(tmp_path, SettledGateway()).run()
    assert not (tmp_path / "manifest.json").exists()


def test_downtime_does_not_reset_wall_time(tmp_path, monkeypatch):
    import principia_asd.engine.bound_checkpoint as cp

    g = SettledGateway()

    def stop(r):
        if r["type"] == "commit" and r["name"] == "initialize":
            raise PowerLoss()

    with pytest.raises(PowerLoss):
        runner(tmp_path, g, stop).run()
    future = cp.time.time() + 3000
    monkeypatch.setattr(cp.time, "time", lambda: future)
    result = runner(tmp_path, g).run()
    assert result["status"] == "failed" and result["failure"]["type"] == "TimeoutError"
    assert not g.calls
    assert result["host_submission"]["accounting"]["wall_seconds"] >= 3000


def test_failed_provider_outcome_is_durable_and_no_retry(tmp_path):
    g = FixtureGateway(fail_at=2)
    result = runner(tmp_path, g).run()
    assert result["status"] == "failed"
    assert result["failure"]["type"] == "RuntimeError"
    assert runner(tmp_path, g).run() == result
    assert len(g.calls) == 2


def test_provider_cache_recovery_is_read_only_and_integrity_checked(tmp_path, monkeypatch):
    import principia_asd.llm.siliconflow as sf
    from principia_asd.store.ledger import CostLedger, DuplicateRequest

    monkeypatch.setenv("SILICONFLOW_API_KEY", "synthetic-test-secret")
    client = sf.SiliconFlowClient(
        ledger=CostLedger(tmp_path / "ledger.sqlite"),
        artifact_dir=tmp_path / "calls",
        require_capabilities=False,
    )
    request = dict(
        model="deepseek-ai/DeepSeek-V4-Flash",
        system="fixture",
        prompt="fixture",
        request_id="fixture-call",
    )

    def no_network(*a, **kw):
        pytest.fail("Recovery performed a network request")

    monkeypatch.setattr(sf.urllib.request, "urlopen", no_network)
    with pytest.raises(DuplicateRequest, match="No settled response"):
        client.recover_completed(**request)
    assert client.ledger.summary()["requests"] == 0

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def read(self, *a):
            return json.dumps(
                {
                    "model": request["model"],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 20},
                    "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
                }
            ).encode()

    monkeypatch.setattr(sf.urllib.request, "urlopen", lambda *a, **kw: Response())
    expected = client.complete(**request)
    monkeypatch.setattr(sf.urllib.request, "urlopen", no_network)
    before = client.ledger.summary()
    assert client.recover_completed(**request) == expected
    assert client.ledger.summary() == before
    with pytest.raises(DuplicateRequest, match="different frozen payload"):
        client.recover_completed(**(request | {"prompt": "changed"}))
    cache = tmp_path / "calls" / f"{sha(request['request_id'])}.json"
    value = read_json(cache)
    value["response"]["text"] = "tampered"
    write_json(cache, value)
    with pytest.raises(DuplicateRequest, match="integrity"):
        client.recover_completed(**request)
    client.ledger.reserve("unknown", 2)
    client.ledger.record({"request_id": "unknown", "state": "unknown"})
    with pytest.raises(DuplicateRequest, match="never replay"):
        client.recover_completed(**(request | {"request_id": "unknown"}))
    assert client.ledger.summary()["unknown_usage_reserved"] == 2


@pytest.mark.parametrize(
    "change", ["scope", "identity", "cap", "fits", "wall", "scenario", "extra"]
)
def test_worker_request_refuses_scope_resource_and_path_changes(tmp_path, change):
    from principia_asd.engine.bound_worker import validate_worker_request
    from principia_asd.methods.registry import DEFAULT_ROLES

    workspace = tmp_path / "private"
    data = tmp_path / "data"
    folder = workspace / "bound-runs/run-1"
    request = {
        "scope": "engineering_only_explicit_state_v1",
        "run_id": "run-1",
        "scenario_path": str(data / "scenario"),
        "roles": DEFAULT_ROLES,
        "limits": {},
        "attempt_cap_cny": 12,
    }
    write_json(folder / "request.json", request)
    settings = {
        "workspace": str(workspace),
        "data_root": str(data),
        "leaderboard_root": str(tmp_path / "leaderboard"),
    }
    assert validate_worker_request(folder, settings)[3] == request
    if change == "scope":
        request["scope"] = "primary"
    elif change == "identity":
        request["run_id"] = "other"
    elif change == "cap":
        request["attempt_cap_cny"] = 3001
    elif change == "fits":
        request["limits"] = {"max_fits": 17}
    elif change == "wall":
        request["limits"] = {"max_seconds": 2401}
    elif change == "scenario":
        request["scenario_path"] = str(tmp_path / "private-evaluator")
    else:
        request["vault"] = "not permitted"
    write_json(folder / "request.json", request)
    with pytest.raises(ValueError):
        validate_worker_request(folder, settings)
