"""Offline verification must retain ambiguous paid requests without dispatching again."""

import importlib.util
from pathlib import Path

import pytest

from principia_asd.io import sha, write_json
from principia_asd.llm.siliconflow import PROFILES

spec = importlib.util.spec_from_file_location(
    "pilot_verifier", Path(__file__).parents[1] / "scripts/verify_adapter_pilot.py"
)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def request():
    model = "deepseek-ai/DeepSeek-V4-Flash"
    args = dict(model=model, system="unit", prompt="fixture", max_tokens=16, request_id="test--coder--1")
    body = {
        "model": model,
        "messages": [{"role": "system", "content": "unit"}, {"role": "user", "content": "fixture"}],
        "max_tokens": 16,
        "temperature": 0.25,
        "stream": False,
        "response_format": {"type": "json_object"},
        **PROFILES[model]["options"],
    }
    return args, sha(body)


def test_unknown_billed_request_is_checked_at_its_boundary_without_retry(tmp_path, monkeypatch):
    args, digest = request()
    records = {args["request_id"]: {
        "state": "unknown", "reserved_cny": 2,
        "payload": {"payload_sha256": digest, "error": "HTTPError"},
    }}

    def no_network(*args, **kwargs):
        raise AssertionError("Offline verifier attempted a network request")

    monkeypatch.setattr(verifier.urllib.request, "urlopen", no_network)
    gateway = verifier.RecordedGateway(tmp_path, records)
    with pytest.raises(verifier.RecordedTransportFailure, match="HTTPError"):
        gateway.complete(**args)
    assert not gateway.calls and gateway.failures[0]["reserved_cny"] == 2
    assert not list(tmp_path.iterdir())
    with pytest.raises(ValueError, match="Duplicate request"):
        gateway.complete(**args)


def test_different_payload_cannot_be_explained_away_as_a_transport_failure(tmp_path):
    args, _ = request()
    records = {args["request_id"]: {
        "state": "unknown", "reserved_cny": 2,
        "payload": {"payload_sha256": "different", "error": "HTTPError"},
    }}
    gateway = verifier.RecordedGateway(tmp_path, records)
    with pytest.raises(ValueError, match="context differs"):
        gateway.complete(**args)
    assert not gateway.failures


@pytest.mark.parametrize("mutate", [False, True])
def test_completed_response_must_match_both_payload_and_ledger_hash(tmp_path, mutate):
    args, digest = request()
    response = {"text": "{}", "request_id": args["request_id"]}
    records = {args["request_id"]: {
        "state": "completed", "reserved_cny": 2,
        "payload": {"payload_sha256": digest, "response_sha256": sha(response)},
    }}
    write_json(tmp_path / "provider" / (sha(args["request_id"]) + ".json"), {
        "payload_sha256": digest,
        "response": response | ({"text": "changed"} if mutate else {}),
    })
    gateway = verifier.RecordedGateway(tmp_path, records)
    if mutate:
        with pytest.raises(AssertionError):
            gateway.complete(**args)
    else:
        assert gateway.complete(**args) == response
        assert len(gateway.calls) == 1 and not gateway.failures
