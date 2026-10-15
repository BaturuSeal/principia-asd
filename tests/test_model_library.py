"""Editable provider profiles: isolation, immutable runs and no accidental billing."""

import json

import pytest
from test_cloud_preparation import app as app
from test_cloud_preparation import public_fixture
from test_product_workspace import example as example

from principia_asd.io import read_json, sha, write_json
from principia_asd.methods.registry import DEFAULT_ROLES
from principia_asd.web import credentials, model_settings
from principia_asd.web.public_site import build_site


def profile(**changes):
    return (
        dict(
            input_rate=2,
            output_rate=8,
            label="Future model",
            options={"enable_thinking": False},
            reasoning_bound=0,
            price_source={"date": "2026-10-15"},
        )
        | changes
    )


def add(app, model="vendor/new-model"):
    return model_settings.save(app, {"model_id": model, "profile": profile()})


def test_profile_crud_invalidates_only_edited_capability_and_retains_history(app):
    add(app)
    value = model_settings.profiles(app)["vendor/new-model"]
    write_json(
        app.workspace / "capabilities.json",
        {
            "vendor/new-model": {"state": "verified", "profile_sha256": sha(value)},
            "untouched": {"state": "verified"},
        },
    )
    model_settings.save(
        app,
        {
            "original_id": "vendor/new-model",
            "model_id": "vendor/new-model",
            "profile": profile(output_rate=12),
        },
    )
    assert (
        "vendor/new-model" not in app.capabilities()
        and app.capabilities()["untouched"]["state"] == "verified"
    )
    model_settings.save(app, {"action": "remove", "model_id": "vendor/new-model"})
    add(app)  # returning to an earlier configuration does not overwrite its immutable history
    assert len(list((app.workspace / "model-profile-history").glob("*.json"))) == 3
    assert app.ledger.summary()["requests"] == 0


@pytest.mark.parametrize(
    "value",
    [
        profile(input_rate=float("nan")),
        profile(output_rate=-1),
        profile(options={"headers": {"Authorization": "secret"}}),
        profile(options={"enable_thinking": True}),
        profile(price_source={"date": "yesterday"}),
        profile(reasoning_bound=True),
    ],
)
def test_reject_unsafe_profiles(app, value):
    with pytest.raises(ValueError):
        model_settings.save(app, {"model_id": "vendor/new", "profile": value})
    assert not (app.workspace / "model-profiles.json").exists()


def test_custom_model_run_freezes_profile_and_cannot_edit_while_queued(app):
    credentials.save(app, {"api_key": "offline-model-test-credential"})
    add(app)
    value = model_settings.profiles(app)["vendor/new-model"]
    write_json(
        app.workspace / "capabilities.json",
        {"vendor/new-model": {"state": "verified", "profile_sha256": sha(value)}},
    )
    roles = {k: "vendor/new-model" for k in DEFAULT_ROLES}
    result = app.start({"scenario_id": "P100-054", "method_id": "direct", "model_roles": roles})
    request = read_json(app.runs / result["run_id"] / "request.json")
    assert request["provider_profiles"]["vendor/new-model"] == value
    assert request["provider_capabilities"]["vendor/new-model"]["profile_sha256"] == sha(value)
    assert "offline-model-test-credential" not in json.dumps(request)
    with pytest.raises(ValueError, match="active"):
        model_settings.save(app, {"action": "remove", "model_id": "vendor/new-model"})


def test_empty_library_keeps_numerical_controls_and_fixed_aliases_do_not_switch(app):
    for model in list(model_settings.profiles(app)):
        model_settings.save(app, {"action": "remove", "model_id": model})
    assert app.config()["models"] == []
    assert app.start({"scenario_id": "P100-054", "method_id": "mean_control"})["status"] == "queued"
    assert app.config()["model_aliases"]["deepseek"] == "deepseek-ai/DeepSeek-V4-Flash"


def test_profile_tamper_rejected_before_dispatch(app):
    credentials.save(app, {"api_key": "offline-model-test-credential"})
    add(app)
    write_json(
        app.workspace / "capabilities.json",
        {"vendor/new-model": {"state": "verified", "profile_sha256": "wrong"}},
    )
    with pytest.raises(ValueError, match="profile changed"):
        app.start(
            {
                "scenario_id": "P100-054",
                "method_id": "direct",
                "model_roles": dict.fromkeys(DEFAULT_ROLES, "vendor/new-model"),
            }
        )
    assert app.ledger.summary()["requests"] == 0


def test_catalog_is_explicit_get_no_generation_or_key_echo(app, monkeypatch):
    credentials.save(app, {"api_key": "offline-catalog-test-credential"})
    seen = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def read(self, limit):
            return b'{"data":[{"id":"vendor/new"},{"id":"<unsafe>"}]}'

    def send(request, **kwargs):
        seen.append((request.full_url, request.get_method()))
        return Response()

    monkeypatch.setattr(model_settings.urllib.request, "urlopen", send)
    assert model_settings.catalog(app)["models"] == ["vendor/new"]
    assert seen == [("https://api.siliconflow.cn/v1/models", "GET")]
    assert app.ledger.summary()["requests"] == 0


def test_site_subpath_assets_and_manifest(example, tmp_path):
    data, boards = public_fixture(example)
    receipt = build_site(data, boards, tmp_path / "site", preview=True, base_path="/web/asd-test/")
    html = (tmp_path / "site/index.html").read_text()
    assert 'data-base-path="/web/asd-test/"' in html
    assert 'src="/web/asd-test/app.js"' in html
    assert 'href="/web/asd-test/style.css"' in html
    assert receipt["base_path"] == "/web/asd-test/"
    with pytest.raises(ValueError, match="Base path"):
        build_site(data, boards, tmp_path / "unsafe", preview=True, base_path="/../")


def test_removed_default_role_is_not_silently_substituted(app):
    model_settings.save(app, {"action": "remove", "model_id": DEFAULT_ROLES["planner"]})
    assert app.config()["model_roles"]["planner"] == ""
    assert app.config()["model_roles"]["coder"] == DEFAULT_ROLES["coder"]


def test_direct_uses_only_its_selected_coder_profile(app):
    credentials.save(app, {"api_key": "offline-model-test-credential"})
    add(app)
    value = model_settings.profiles(app)["vendor/new-model"]
    write_json(
        app.workspace / "capabilities.json",
        {"vendor/new-model": {"state": "verified", "profile_sha256": sha(value)}},
    )
    roles = dict.fromkeys(DEFAULT_ROLES, "") | {"coder": "vendor/new-model"}
    assert (
        app.start({"scenario_id": "P100-054", "method_id": "direct", "model_roles": roles})[
            "status"
        ]
        == "queued"
    )
