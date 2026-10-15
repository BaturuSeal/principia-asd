"""Host-only SiliconFlow gateway: exact models, bounded payloads and durable receipts."""

from __future__ import annotations

import json
import os
import ssl
import time
import urllib.request
from pathlib import Path

import certifi

from ..io import read_json, sha, write_json
from ..store.ledger import DuplicateRequest

PROFILES = {
    "deepseek-ai/DeepSeek-V4-Flash": {
        "input_rate": 3,
        "output_rate": 9,
        "options": {"enable_thinking": False},
        "reasoning_bound": 0,
    },
    "zai-org/GLM-5.3": {
        "input_rate": 8,
        "output_rate": 28,
        "options": {"enable_thinking": True, "thinking_budget": 1024, "reasoning_effort": "high"},
        "reasoning_bound": 1024,
    },
    "Qwen/Qwen3.8-27B": {
        "input_rate": 3,
        "output_rate": 12,
        "options": {"enable_thinking": False},
        "reasoning_bound": 0,
    },
    "Pro/moonshotai/Kimi-K2.6": {
        "input_rate": 6.5,
        "output_rate": 27,
        "options": {"enable_thinking": False},
        "reasoning_bound": 0,
    },
}
PRICE_SOURCE = {
    "url": "https://www.siliconflow.cn/pricing",
    "date": "2026-10-11",
    "currency": "CNY",
    "unit": "per million tokens",
    "policy": "highest daily input/output rates; cache discounts not assumed",
}


def read_env_file(path):
    values = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip().removeprefix("export ")
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip().strip("\"'")
    return values


class SiliconFlowClient:
    def __init__(
        self,
        *,
        env_file=None,
        ledger,
        artifact_dir,
        attempt_cap_cny=12,
        require_capabilities=True,
        capabilities=None,
        timeout=240,
        profiles=None,
    ):
        values = read_env_file(env_file) if env_file and Path(env_file).is_file() else {}
        self.api_key = values.get("SILICONFLOW_API_KEY") or os.environ.get("SILICONFLOW_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Set SILICONFLOW_API_KEY on the server or configure the credential file"
            )
        self.ledger = ledger
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.attempt_cap = float(attempt_cap_cny)
        self.timeout = timeout
        self.attempt_id = str(self.artifact_dir.resolve())
        self.require_capabilities = require_capabilities
        self.capabilities = capabilities or {}
        self.profiles = json.loads(json.dumps(PROFILES if profiles is None else profiles))
        self.custom_profiles = profiles is not None

    def recover_completed(self, **request):
        """Read a settled, integrity-checked response; this path cannot dispatch."""
        return self.complete(**request, _recovery_only=True)

    def complete(
        self,
        *,
        model,
        system,
        prompt,
        max_tokens=1800,
        temperature=0.25,
        request_id,
        _recovery_only=False,
    ):
        if model not in self.profiles:
            raise ValueError("Unconfigured model; no substitution: " + model)
        if (
            self.require_capabilities
            and self.capabilities.get(model, {}).get("state") != "verified"
        ):
            raise ValueError("Model capability profile has not passed: " + model)
        if len((system + prompt).encode()) > 48000 or not 1 <= max_tokens <= 4096:
            raise ValueError("Payload exceeds frozen request limits")
        profile = self.profiles[model]
        if (
            self.require_capabilities
            and self.custom_profiles
            and self.capabilities.get(model, {}).get("profile_sha256") != sha(profile)
        ):
            raise ValueError("Model profile changed; run its capability check again: " + model)
        price_source = profile.get("price_source", PRICE_SOURCE)
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
            "response_format": {"type": "json_object"},
            **profile["options"],
        }
        bound = max(
            2.0,
            (
                (len(json.dumps(body).encode()) + 256) * profile["input_rate"]
                + (max_tokens + profile["reasoning_bound"]) * profile["output_rate"]
            )
            / 1e6,
        )
        request_hash = sha(body)
        cache = self.artifact_dir / (sha(request_id) + ".json")
        prior = self.ledger.get(request_id)
        if prior:
            if prior["state"] == "completed" and cache.exists():
                if self.custom_profiles and prior["payload"].get("profile_sha256") != sha(profile):
                    raise DuplicateRequest("Cached request belongs to a different model profile")
                saved = read_json(cache)
                if saved["payload_sha256"] != request_hash:
                    raise DuplicateRequest("Cached request belongs to different frozen payload")
                if (
                    prior["payload"].get("payload_sha256") != request_hash
                    or prior["payload"].get("response_sha256") != sha(saved["response"])
                    or saved["response"].get("request_id") != request_id
                    or saved["response"].get("model") != model
                ):
                    raise DuplicateRequest(
                        "Cached response failed ledger identity or integrity checks"
                    )
                if (
                    prior["payload"].get("capability_violation")
                    or saved["response"].get("finish_reason") == "length"
                ):
                    raise ValueError(
                        "Cached provider response failed its capability or completeness check; create a new explicitly configured attempt"
                    )
                return saved["response"]
            raise DuplicateRequest(
                "Previously dispatched request has no reusable completed response; never replay automatically"
            )
        if _recovery_only:
            raise DuplicateRequest(
                "No settled response exists; recovery never dispatches a new request"
            )
        self.ledger.reserve(
            request_id,
            bound,
            {
                "model": model,
                "payload_sha256": request_hash,
                "price_source": price_source,
                "generation": body | {"messages": "private"},
                "max_tokens": max_tokens,
                "profile_sha256": sha(profile),
            },
            attempt_id=self.attempt_id,
            attempt_cap_cny=self.attempt_cap,
        )
        request = urllib.request.Request(
            "https://api.siliconflow.cn/v1/chat/completions",
            data=json.dumps(body).encode(),
            method="POST",
            headers={
                "Authorization": "Bearer " + self.api_key,
                "Content-Type": "application/json",
                "X-Trace-Id": request_id,
            },
        )
        start = time.monotonic()
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout,
                context=ssl.create_default_context(cafile=certifi.where()),
            ) as r:
                raw = r.read(1_000_001)
            if len(raw) > 1_000_000:
                raise ValueError("Provider response exceeds receipt limit")
            data = json.loads(raw)
            usage = data.get("usage", {})
            choice = data["choices"][0]
            message = choice["message"]
            actual_model = data.get("model")
            if actual_model != model:
                raise ValueError("Provider returned a different model identifier")
            reasoning = int(usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0))
            violation = (
                reasoning > profile["reasoning_bound"]
                or int(usage.get("completion_tokens", 0)) > max_tokens + profile["reasoning_bound"]
            )
            result = {
                "request_id": request_id,
                "model": model,
                "text": message.get("content", ""),
                "usage": usage,
                "elapsed_seconds": time.monotonic() - start,
                "finish_reason": choice.get("finish_reason"),
                "price_source": price_source,
            }
            # Store the completed response before settling the ledger. A crash never causes a paid replay.
            write_json(cache, {"payload_sha256": request_hash, "response": result}, immutable=True)
            cost = None
            if "prompt_tokens" in usage and "completion_tokens" in usage:
                cost = (
                    usage["prompt_tokens"] * profile["input_rate"]
                    + usage["completion_tokens"] * profile["output_rate"]
                ) / 1e6
            self.ledger.record(
                {
                    "request_id": request_id,
                    "state": "completed",
                    "model": model,
                    "usage": usage,
                    "actual_cny": cost,
                    "capability_violation": violation,
                    "response_sha256": sha(result),
                }
            )
            if violation:
                raise ValueError("Reasoning or completion bound violated; profile must be reprobed")
            if choice.get("finish_reason") == "length":
                raise ValueError("Provider output truncated; no automatic repair request")
            return result
        except Exception as exc:
            if self.ledger.get(request_id)["state"] == "reserved":
                self.ledger.record(
                    {
                        "request_id": request_id,
                        "state": "unknown",
                        "model": model,
                        "error": type(exc).__name__,
                    }
                )
            raise
