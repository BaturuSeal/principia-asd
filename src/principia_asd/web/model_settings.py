"""Workspace-scoped exact-model profiles. No cloud state and no paid discovery."""

from __future__ import annotations

import json
import math
import re
import ssl
import urllib.request
from datetime import date

import certifi

from ..io import read_json, sha, write_json
from ..llm.siliconflow import PRICE_SOURCE, PROFILES, SiliconFlowClient


def profiles(app):
    path = app.workspace / "model-profiles.json"
    return read_json(path) if path.exists() else json.loads(json.dumps(PROFILES))


def validate(model, value):
    if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{1,199}", model):
        raise ValueError("Enter the exact SiliconFlow model identifier")
    if not isinstance(value, dict):
        raise ValueError("Model profile must be an object")
    rates = {}
    for name in ("input_rate", "output_rate"):
        v = value.get(name)
        if (
            isinstance(v, bool)
            or not isinstance(v, (int, float))
            or not math.isfinite(v)
            or not 0 <= v <= 1000
        ):
            raise ValueError(
                "Token rates must be finite CNY per million tokens, between 0 and 1000"
            )
        rates[name] = v
    label = value.get("label", model)
    if not isinstance(label, str) or not 1 <= len(label.strip()) <= 200:
        raise ValueError("Provide a short model display name")
    options = value.get("options", {})
    if not isinstance(options, dict) or set(options) - {
        "enable_thinking",
        "thinking_budget",
        "reasoning_effort",
    }:
        raise ValueError("Unsupported generation option; endpoint and headers cannot be overridden")
    if "enable_thinking" in options and not isinstance(options["enable_thinking"], bool):
        raise ValueError("enable_thinking must be a boolean")
    bound = value.get("reasoning_bound", 0)
    if isinstance(bound, bool) or not isinstance(bound, int) or not 0 <= bound <= 32768:
        raise ValueError("Reasoning reservation must be an integer from 0 to 32768 tokens")
    if options.get("enable_thinking") is True:
        if not bound or options.get("thinking_budget") != bound:
            raise ValueError(
                "Enabled reasoning needs a matching positive token reservation and budget"
            )
    elif bound or "thinking_budget" in options or "reasoning_effort" in options:
        raise ValueError("Reasoning settings require enabled thinking")
    if options.get("reasoning_effort", "low") not in {"low", "medium", "high"}:
        raise ValueError("Unsupported reasoning effort")
    source = value.get("price_source", {})
    try:
        day = date.fromisoformat(source["date"]).isoformat()
    except (TypeError, KeyError, ValueError):
        raise ValueError("Record the pricing date as YYYY-MM-DD") from None
    return {
        **rates,
        "label": label.strip(),
        "options": options,
        "reasoning_bound": bound,
        "price_source": {
            **PRICE_SOURCE,
            "date": day,
            "policy": "user-configured conservative rates; verify against provider pricing",
        },
    }


def save(app, request):
    from .credentials import idle_required

    with app.lock:
        idle_required(app)
        current = profiles(app)
        old = request.get("original_id")
        model = request.get("model_id")
        if request.get("action") == "remove":
            if model not in current:
                raise ValueError("Model profile does not exist")
            del current[model]
            affected = {model}
        else:
            value = validate(model, request.get("profile"))
            if old is not None and old not in current:
                raise ValueError("Original model profile does not exist")
            if model in current and model != old:
                raise ValueError("This model identifier already exists; edit its profile")
            if old:
                del current[old]
            current[model] = value
            affected = {model, old}
        if len(current) > 64:
            raise ValueError("At most 64 local model profiles are supported")
        # Keep the previous configuration as a content-addressed, immutable attachment.
        previous = profiles(app)
        history = app.workspace / "model-profile-history" / (sha(previous) + ".json")
        if not history.exists():
            write_json(history, previous, immutable=True)
        write_json(app.workspace / "model-profiles.json", current)
        caps = app.capabilities()
        for ident in affected:
            caps.pop(ident, None)
        write_json(app.workspace / "capabilities.json", caps)
        return {
            "profiles": current,
            "message": "Saved locally. New or changed profiles require a capability check.",
        }


def probe_bound(profile):
    # Upper bound covers the gateway's maximum permitted input, plus request metadata.
    return round(
        max(
            2.0,
            (
                50000 * profile["input_rate"]
                + (128 + profile["reasoning_bound"]) * profile["output_rate"]
            )
            / 1e6,
        ),
        6,
    )


def catalog(app):
    from .credentials import status

    if not status(app)["configured"]:
        raise ValueError("Add your SiliconFlow API key first")
    client = SiliconFlowClient(
        env_file=app.settings.get("env_file"),
        ledger=app.ledger,
        artifact_dir=app.workspace / "catalog-check",
        require_capabilities=False,
    )
    req = urllib.request.Request(
        "https://api.siliconflow.cn/v1/models",
        headers={"Authorization": "Bearer " + client.api_key},
    )
    try:
        with urllib.request.urlopen(
            req, timeout=25, context=ssl.create_default_context(cafile=certifi.where())
        ) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("catalog size")
        records = json.loads(raw)["data"]
        models = sorted(
            {
                r["id"]
                for r in records
                if isinstance(r, dict)
                and isinstance(r.get("id"), str)
                and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{1,199}", r["id"])
            }
        )
    except Exception:
        raise ValueError(
            "Could not read the SiliconFlow catalog. Check your connection and API key; no generation request was made."
        ) from None
    return {
        "models": models,
        "generation_calls": 0,
        "message": "Catalog identifiers only. Confirm chat/JSON support and enter current pricing before use.",
    }
