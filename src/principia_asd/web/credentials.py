"""Local-only credential settings and explicit, accounted capability checks.

Never returns a credential, provider error body, or private credential path to the browser.
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

from ..engine.search import decode_json
from ..io import read_json, sha, write_json
from ..llm.siliconflow import PRICE_SOURCE, SiliconFlowClient, read_env_file
from ..runtime import now
from . import model_settings


def load_settings(app):
    saved = app.workspace / "provider-settings.json"
    if saved.exists():
        value = read_json(saved)
        app.settings["credential_disabled"] = value.get("disabled", False)
        if value.get("managed"):
            app.settings["env_file"] = str(app.workspace / ".credentials/siliconflow.env")
    app.probe_pending = False


def status(app):
    if app.settings.get("credential_disabled"):
        return {"configured": False, "source": "none"}
    path = app.settings.get("env_file")
    try:
        key = (
            read_env_file(path).get("SILICONFLOW_API_KEY")
            if path and Path(path).is_file()
            else None
        )
    except OSError:
        key = None
    configured = bool(key or os.environ.get("SILICONFLOW_API_KEY"))
    managed = path == str(app.workspace / ".credentials/siliconflow.env")
    return {
        "configured": configured,
        "source": "saved_local"
        if managed and configured
        else "external_local"
        if configured
        else "none",
    }


def idle_required(app):
    if app.probe_pending or app.bound_pending or app.normal_pending or app.processes:
        raise ValueError("Wait for active checks and discovery runs before changing API settings")
    for run in app.list_runs():
        if run["status"] in {"queued", "running", "cancelling", "interrupted", "recovery_required"}:
            raise ValueError("Finish or cancel outstanding runs before changing API settings")


def save(app, request):
    with app.lock:
        idle_required(app)
        path = app.workspace / ".credentials/siliconflow.env"
        if request.get("action") == "remove":
            if path.exists():
                path.unlink()
            app.settings["credential_disabled"] = True
            # Never edit or delete an externally configured file.
            write_json(
                app.workspace / "provider-settings.json", {"disabled": True, "managed": False}
            )
        else:
            key = request.get("api_key", "")
            if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{12,512}", key):
                raise ValueError("Enter a valid SiliconFlow key without whitespace")
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            path.parent.chmod(0o700)
            if path.is_symlink():
                raise ValueError("Credential file must not be a symbolic link")
            temp = path.parent / (".pending-" + uuid.uuid4().hex)
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(fd, "w") as stream:
                    stream.write("SILICONFLOW_API_KEY=" + key + "\n")
                temp.replace(path)
            finally:
                temp.unlink(missing_ok=True)
            app.settings.update(env_file=str(path), credential_disabled=False)
            write_json(
                app.workspace / "provider-settings.json", {"disabled": False, "managed": True}
            )
        # Account-specific capability checks cannot transfer to a different key.
        write_json(app.workspace / "capabilities.json", {})
        write_json(app.workspace / "settings.json", app.settings)
        return status(app)


def probe_status(app):
    path = app.workspace / "provider-probe.json"
    value = read_json(path) if path.exists() else {"state": "idle"}
    if value["state"] in {"queued", "running"} and not app.probe_pending:
        value = value | {
            "state": "interrupted",
            "message": "Interrupted check: retained requests will not be replayed. Start a new explicit check if needed.",
        }
    return value


def start_probe(app, request):
    models = request.get("models")
    configured = model_settings.profiles(app)
    if (
        not isinstance(models, list)
        or not models
        or len(models) > 4
        or any(not isinstance(m, str) for m in models)
        or len(set(models)) != len(models)
        or any(not isinstance(m, str) or m not in configured for m in models)
    ):
        raise ValueError("Select one to four supported models")
    if request.get("confirm_cost") is not True:
        raise ValueError("Confirm the displayed capability-check reservation before dispatch")
    with app.lock:
        idle_required(app)
        if not status(app)["configured"]:
            raise ValueError("Add your SiliconFlow API key in API settings first")
        bound = sum(model_settings.probe_bound(configured[m]) for m in models)
        if app.ledger.summary()["remaining_cny"] < bound:
            raise ValueError("Insufficient remaining local API budget for these checks")
        ident = "probe-" + uuid.uuid4().hex
        value = {
            "probe_id": ident,
            "state": "queued",
            "models": models,
            "profiles": {m: configured[m] for m in models},
            "reservation_cny": bound,
            "started_at": now(),
            "results": {},
        }
        write_json(app.workspace / "provider-probe.json", value)
        app.probe_pending = True
        future = app.pool.submit(run_probe, app, value)

        def finished(result):
            if result.exception() is not None:
                write_json(
                    app.workspace / "provider-probe.json",
                    value
                    | {
                        "state": "failed",
                        "message": "Check stopped; inspect the private receipts. No automatic retry.",
                    },
                )
            app.probe_pending = False

        future.add_done_callback(finished)
        return value


def run_probe(app, value):
    """One small request per selected model. A new click creates new request identities."""
    value = value | {"state": "running"}
    root = app.workspace / "probes" / value["probe_id"]
    write_json(root / "request.json", value, immutable=True)
    client = SiliconFlowClient(
        env_file=app.settings.get("env_file"),
        ledger=app.ledger,
        artifact_dir=root / "receipts",
        require_capabilities=False,
        profiles=value["profiles"],
        attempt_cap_cny=value["reservation_cny"],
    )
    capabilities = app.capabilities()
    for model in value["models"]:
        try:
            response = client.complete(
                model=model,
                system="Return JSON only.",
                prompt='Reply with {"ok": true}.',
                max_tokens=128,
                request_id=value["probe_id"] + ":" + model,
            )
            if decode_json(response["text"]).get("ok") is not True:
                raise ValueError("JSON capability not confirmed")
            result = {
                "state": "verified",
                "model": model,
                "generation": value["profiles"][model],
                "profile_sha256": sha(value["profiles"][model]),
                "usage": response["usage"],
                "text": True,
                "json": True,
                "vision": "not_probed",
                "tools": "host structured JSON actions only",
                "price_source": value["profiles"][model].get("price_source", PRICE_SOURCE),
            }
        except Exception as exc:
            # Do not return provider content: some errors may echo request headers.
            result = {
                "state": "unavailable",
                "model": model,
                "reason": type(exc).__name__
                + ": capability check failed; no automatic retry or model substitution",
            }
        value["results"][model] = result
        capabilities[model] = result
        write_json(app.workspace / "capabilities.json", capabilities)
        write_json(app.workspace / "provider-probe.json", value)
    value |= {"state": "complete", "finished_at": now()}
    write_json(root / "outcome.json", value, immutable=True)
    write_json(app.workspace / "provider-probe.json", value)
