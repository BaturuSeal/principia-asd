"""Scientific structure and multi-role workflow checks on disclosed synthetic fixtures."""

import copy
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from principia_asd.catalog.equation_sources import number, thermal
from principia_asd.engine.equations import execute_system, mathematical_signature, validate
from principia_asd.engine.search import execute_method
from principia_asd.engine.transport_templates import TEMPLATES
from principia_asd.io import file_sha, read_json, write_json
from principia_asd.web.equation_view import equation_view
from principia_asd.web.rule_families import structure_id
from principia_asd.web.tasks import resolve_task, task_entries

spec = importlib.util.spec_from_file_location(
    "mechanism_builder", Path(__file__).parents[1] / "scripts/prepare_mechanism_pack.py"
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def contract(case):
    units = builder.NEW_UNITS.get(case) or (
        {k: v[2] for k, v in builder.OLD_MAPS[case].items()}
        | {"target": builder.OUTPUT_UNITS[case]}
    )
    return {
        "task_id": case,
        "scenario_id": case,
        "inputs": [k for k in units if k != "target"],
        "output": "target",
        "quantity_units": units,
        "equation_templates": TEMPLATES[case](),
        "metric": {"primary": "mae"},
        "equation_protocol": "multi-role-equations-v2",
    }


@pytest.mark.parametrize("case", list(TEMPLATES))
def test_every_constitutive_template_has_checked_units_and_connected_state(case):
    t = contract(case)
    for s in t["equation_templates"]:
        info = validate(s, t)
        assert len(info["dependencies"]) >= 3
        assert any(
            "exp(" in n["expression"] or "sqrt(" in n["expression"] or "**" in n["expression"]
            for n in s["nodes"]
        )
        assert set(s["parameters"])
        assert s["assumptions"]


def test_thermal_network_energy_balance_and_zero_horizon():
    t = contract("069")
    s = t["equation_templates"][0]
    p = {k: v["initial"] for k, v in s["parameters"].items()}
    x = {
        "lubricant_temperature": np.array([300.0, 300.0, 300.0]),
        "housing_temperature": np.array([300.0] * 3),
        "environment_temperature": np.array([300.0] * 3),
        "speed": np.array([1.0, 1.0, 0.0]),
        "torque": np.array([2.0] * 3),
        "horizon": np.array([0.0, 60.0, 60.0]),
    }
    v = execute_system(s, x, p, t, intermediates=True)
    assert v["temperature_increment"][0] == 0 and v["temperature_increment"][2] == 0
    assert 0 < v["temperature_increment"][1] < 2 * 60 / p["capacity"]
    assert np.allclose(
        v["net_power"], v["friction_power"] - v["housing_loss"] - v["environment_loss"]
    )


def test_membrane_transport_zero_drive_and_positive_components():
    t = contract("061")
    s = t["equation_templates"][1]
    p = {k: v["initial"] for k, v in s["parameters"].items()}
    x = {
        "temperature": np.array([300.0, 400.0]),
        "pressure_feed": np.array([1e5, 3e5]),
        "pressure_permeate": np.array([1e5, 1e5]),
    }
    v = execute_system(s, x, p, t, intermediates=True)
    assert v["total_flux"][0] == 0 and v["total_flux"][1] > 0
    assert np.allclose(v["total_flux"], v["knudsen_flux"] + v["viscous_flux"])


def test_renamed_or_refactored_hypothesis_does_not_create_a_new_mathematical_structure():
    s = TEMPLATES["013"]()[0]
    other = copy.deepcopy(s)
    other["name"] = "Misleading new name"
    other["parameters"]["k1"]["initial"] *= 2
    assert mathematical_signature(s) == mathematical_signature(other)
    other["nodes"][-1]["expression"] = "thermal_rate * depletion + thermal_rate"
    assert mathematical_signature(s) != mathematical_signature(other)


@pytest.mark.parametrize("offset", [0, 273.15, 10000])
def test_linear_reference_is_invariant_to_constant_coordinates_and_origin(offset):
    # Constant horizons used to overwhelm the least-squares rank threshold.
    t = {
        "task_id": "constant-coordinate-fixture",
        "inputs": ["x", "horizon"],
        "output": "target",
        "metric": {"primary": "mae"},
    }
    rows = [
        dict(x=float(i) + offset, horizon=0.2, target=2.0 * i + 3, group="train") for i in range(12)
    ]
    dev = [
        dict(x=float(i) + offset, horizon=0.2, target=2.0 * i + 3, group="dev")
        for i in range(12, 16)
    ]
    out = execute_method("linear_control", t, rows, dev)
    assert out["status"] == "complete"
    assert out["rules"][0]["dev_error"] < 1e-8


def test_equation_families_ignore_renaming_but_keep_all_card_interpretations():
    t = contract("069")
    s = t["equation_templates"][0]
    a = dict(
        representation="equation-system-v1",
        equation_system=s,
        parameters={k: v["initial"] for k, v in s["parameters"].items()},
    )
    b = copy.deepcopy(a)
    b["equation_system"]["name"] = "Renamed mechanism"
    b["equation_system"]["nodes"][0]["meaning"] = "Alternative unverified interpretation"
    assert structure_id(a, t) == structure_id(b, t)
    assert (
        equation_view(a, t)["equations"][0]["meaning"]
        != equation_view(b, t)["equations"][0]["meaning"]
    )


@pytest.mark.parametrize("case", list(TEMPLATES))
def test_equation_presentation_has_unique_symbols_and_complete_quantities(case):
    t = contract(case)
    for s in t["equation_templates"]:
        card = dict(
            equation_system=s, parameters={k: v["initial"] for k, v in s["parameters"].items()}
        )
        view = equation_view(card, t)
        symbols = [
            r["symbol"] for key in ["parameters", "variables", "equations"] for r in view[key]
        ]
        # Output occurs once in variables and once as the final equation.
        assert len(set(symbols)) == len(symbols) - 1
        assert len(view["equations"]) == len(s["nodes"])


def test_stored_formula_cannot_masquerade_as_measurement():
    with pytest.raises(ValueError, match="workbook formula"):
        number({"A1": "1"}, {"A1"}, "A1")


def test_forecast_reader_never_uses_future_power(tmp_path):
    p = tmp_path / "raw/identification/theta_dot=1p2566.csv"
    p.parent.mkdir(parents=True)
    p.write_text(
        "t,T_L,T_H,T_E,theta_dot,tau_f\n"
        + "\n".join(f"{i},20,19,18,{100 if i else 1},2" for i in range(181))
    )
    rows, excluded, _ = thermal(tmp_path)
    assert rows[0]["speed"] == 1 and rows[0]["torque"] == 2
    assert rows[0]["horizon"] == 60 and rows[0]["target"] == 0
    assert not excluded


def test_bound_task_extension_preserves_the_old_contract_and_isolated_paths(tmp_path):
    from principia_asd.io import write_csv

    base = tmp_path / "base/S"
    extension = tmp_path / "pack/scenarios/S"
    w = tmp_path / "workspace"
    t = {
        "task_id": "old",
        "scenario_id": "S",
        "split": {k: "public/" + k + ".csv" for k in ["train", "dev", "test"]},
    }
    write_json(base / "scenario.json", {"scenario_id": "S", "title": "Old"})
    write_json(base / "task-contracts/task-001.json", t)
    for k in t["split"]:
        write_csv(base / t["split"][k], [{"x": 1}], ["x"])
    new = t | {"task_id": "new", "equation_templates": [{"name": "physical"}]}
    write_json(
        extension / "scenario.json",
        {
            "scenario_id": "S",
            "extends_scenario_sha256": file_sha(base / "scenario.json"),
            "extends_task_sha256": file_sha(base / "task-contracts/task-001.json"),
        },
    )
    write_json(extension / "task-contracts/task-001.json", new)
    write_json(w / "scenario-packs.json", {"packs": [{"data_root": str(tmp_path / "pack")}]})
    entries = task_entries(base, w)
    assert [read_json(f)["task_id"] for _, f in entries] == ["new", "old"]
    assert resolve_task(base, w, "old")[0] == base
    assert resolve_task(base, w, "new")[0] == extension
    write_json(base / "task-contracts/task-001.json", t | {"task_id": "tampered"})
    with pytest.raises(ValueError, match="base contract"):
        task_entries(base, w)


def test_multirole_handoffs_use_distinct_models_and_executed_development_diagnostics():
    t = contract("013")
    s = t["equation_templates"][0]
    xs = {
        "temperature": np.linspace(380, 450, 24),
        "conversion": np.linspace(0.1, 0.9, 24),
        "heating_rate": np.full(24, 0.1),
    }
    y = execute_system(s, xs, {k: v["initial"] for k, v in s["parameters"].items()}, t)
    rows = [
        {k: float(v[i]) for k, v in xs.items()}
        | {"target": float(y[i]), "group": "g" + str(i // 4)}
        for i in range(24)
    ]

    class Gateway:
        def __init__(self):
            self.calls = []

        def complete(self, **req):
            self.calls.append(req)
            assert len((req["prompt"] + req["system"]).encode()) < 48000
            if req["model"] != "code":
                return {
                    "text": json.dumps(
                        {
                            "summary": "Engineering fixture",
                            "limitations": ["Not scientific evidence"],
                        }
                    )
                }
            candidate = copy.deepcopy(s)
            candidate["name"] = "Fixture modified depletion"
            candidate["parameters"]["power"] = dict(
                initial=1, bounds=[0.5, 2], unit="1", meaning="Fixture extra exponent"
            )
            candidate["nodes"][-1]["expression"] = "thermal_rate * depletion ** power"
            return {"text": json.dumps({"systems": [candidate]})}

    gateway = Gateway()
    out = execute_method(
        "equation_agent",
        t,
        rows[:16],
        rows[16:],
        gateway=gateway,
        roles={"planner": "plan", "coder": "code", "critic": "critique", "reporter": "report"},
        limits={"max_calls": 5, "max_fits": 16},
    )
    assert [x["model"] for x in gateway.calls] == ["plan", "code", "critique", "code", "report"]
    assert out["accounting"]["model_requests"] == 5
    assert len(out["method_evidence"]["role_handoffs"]) == 3
    assert "input_strata" in gateway.calls[2]["prompt"]
    assert out["status"] == "complete"
    assert any("Duplicate expanded" in f["reason"] for f in out["method_evidence"]["failures"])


def test_no_change_reference_needs_explicit_task_contract():
    t = {"task_id": "T", "inputs": ["x"], "output": "target", "metric": {"primary": "mae"}}
    rows = [{"x": float(i), "target": float(i), "group": str(i)} for i in range(4)]
    assert execute_method("persistence_control", t, rows, rows)["status"] == "unsupported"
    out = execute_method("persistence_control", t | {"reference_expression": "x"}, rows, rows)
    assert out["status"] == "complete" and out["rules"][0]["dev_error"] == 0
    assert not out["rules"][0]["parameters"]
