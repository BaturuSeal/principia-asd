import copy
import json

import numpy as np
import pytest

from principia_asd.engine.equations import execute_system, system_complexity, validate
from principia_asd.engine.scientific_templates import (
    atmosphere_templates,
    relaxation_templates,
    resin_templates,
)
from principia_asd.engine.search import execute_method
from principia_asd.evaluate.metrics import evaluate_rule
from principia_asd.web.rule_families import structure_id
from principia_asd.web.rule_view import rule_view


def task():
    return {
        "task_id": "coupled-v1",
        "scenario_id": "FIXTURE",
        "inputs": ["omega", "temperature", "response_kind"],
        "output": "target",
        "quantity_units": {
            "omega": "rad/s",
            "temperature": "K",
            "response_kind": "1",
            "target": "Pa",
        },
        "metric": {"primary": "log_mae"},
        "stability": {"domain": "fixture", "categorical_inputs": ["response_kind"]},
        "equation_templates": relaxation_templates(),
    }


def initial(system):
    return {k: v["initial"] for k, v in system["parameters"].items()}


@pytest.mark.parametrize(
    "factory,units",
    [
        (
            relaxation_templates,
            {"omega": "rad/s", "temperature": "K", "response_kind": "1", "target": "Pa"},
        ),
        (resin_templates, {"temperature": "K", "shear_rate": "s^-1", "target": "Pa*s"}),
        (atmosphere_templates, {"temperature": "K", "vapor_pressure": "Pa", "target": "W/m2"}),
    ],
)
def test_all_priors_are_dimensionally_consistent(factory, units):
    t = {
        "inputs": list(units)[:-1],
        "output": "target",
        "quantity_units": units,
        "equation_templates": factory(),
    }
    for s in factory():
        validate(s, t)


def test_shared_maxwell_response_and_fractional_limit():
    t = task()
    simple = relaxation_templates()[0]
    x = {
        "omega": np.array([1 / 0.03, 1 / 0.03]),
        "temperature": np.array([313.15, 313.15]),
        "response_kind": np.array([0, 1]),
    }
    y = execute_system(simple, x, initial(simple), t)
    assert np.allclose(y, [2.5e7, 2.5e7])
    fractional = relaxation_templates()[2]
    params = initial(fractional) | {"alpha": 1, "G": 5e7, "tau": 0.03}
    assert np.allclose(execute_system(fractional, x, params, t), y)
    mid = execute_system(simple, x, initial(simple), t, intermediates=True)
    assert np.allclose(mid["z1"], 1)
    assert set(mid) == {n["id"] for n in simple["nodes"]}


@pytest.mark.parametrize(
    "defect",
    [
        "wrong_unit",
        "dimensional_exp",
        "future_node",
        "hidden_state",
        "target_alias",
        "unapproved_constant",
        "unknown_unit",
        "literal_coefficient",
    ],
)
def test_rejects_invalid_or_hidden_equations(defect):
    t = task()
    s = copy.deepcopy(t["equation_templates"][0])
    if defect == "wrong_unit":
        s["nodes"][1]["unit"] = "Pa"
    if defect == "dimensional_exp":
        s["nodes"][0]["expression"] = "exp(temperature)"
    if defect == "future_node":
        s["nodes"][0]["expression"] = "z1"
    if defect == "hidden_state":
        s["parameters"]["hidden"] = dict(
            initial=1, bounds=[0, 2], unit="1", meaning="Hidden coefficient"
        )
    if defect == "target_alias":
        s["nodes"][0]["expression"] = "target"
    if defect == "unapproved_constant":
        s["constants"]["T_ref"]["value"] = 313.159999
    if defect == "unknown_unit":
        t["quantity_units"]["omega"] = "unknown"
    if defect == "literal_coefficient":
        s["nodes"][0]["expression"] = "0.3715 * exp(activation * (1 / temperature - 1 / T_ref))"
    with pytest.raises(ValueError):
        validate(s, t)


def test_complexity_expands_shared_subgraphs_and_counts_parameters_once():
    s = relaxation_templates()[2]
    c = system_complexity(s, initial(s))
    assert c["free_parameters"] == 4
    assert c["weighted_operator_count"] > c["dag_weighted_operator_count"]
    assert c["intermediate_quantities"] == 8


def test_presentation_keeps_values_out_of_equations_and_explains_quantities():
    t = task()
    s = relaxation_templates()[2]
    card = dict(
        representation="equation-system-v1",
        equation_system=s,
        parameters=initial(s),
        rule_id="fixture",
    )
    v = rule_view(card, t)
    assert len(v["equations"]) == 9
    assert "313.15" not in v["latex"] and "10000" not in v["latex"]
    assert any(p["value"] == 313.15 for p in v["parameters"])
    assert all(q["meaning"] and q["dependencies"] for q in v["equations"])
    assert {p["key"]: p["symbol"] for p in v["parameters"]}["tau"] == r"\tau"
    assert {q["id"]: q["symbol"] for q in v["equations"]}["storage_modulus"] == "G'"
    symbols = [x["symbol"] for x in v["equations"] + v["parameters"]]
    assert len(set(symbols)) == len(symbols)
    assert "not" in v["interpretation_scope"]


def test_frozen_graph_parameter_mutation_fails_domain():
    t = task()
    s = t["equation_templates"][0]
    x = {"omega": np.array([1]), "temperature": np.array([313.15]), "response_kind": np.array([0])}
    with pytest.raises(ValueError):
        execute_system(s, x, initial(s) | {"tau1": -1}, t)


def test_deterministic_evaluation_uses_the_graph_not_display_or_method_name():
    t = task()
    s = t["equation_templates"][0]
    rows = [
        dict(omega=1 / 0.03, temperature=313.15, response_kind=c, group="fixture") for c in [0, 1]
    ]
    card = dict(representation="equation-system-v1", equation_system=s, parameters=initial(s))
    a = evaluate_rule(card, rows, [2.5e7] * 2, t)
    b = evaluate_rule(
        card | {"method_id": "another", "expression": "wrong display"}, rows, [2.5e7] * 2, t
    )
    assert a == b and a["accuracy"]["primary_error"] < 1e-10
    assert a["simplicity"]["free_parameters"] == 3


def test_unknown_units_are_explicitly_unsupported():
    out = execute_method("equation_search", {"inputs": ["x"], "output": "target"}, [], [])
    assert out["status"] == "unsupported" and not out["rules"]


def test_structural_grouping_is_conservative_and_method_blind():
    t = {"inputs": ["x"], "output": "target", "task_id": "one"}
    a = {"expression": "a + b*x", "parameters": {"a": 1, "b": 2}}
    b = {
        "expression": "offset + slope * x",
        "parameters": {"offset": 1.0001, "slope": 5},
        "method_id": "another",
    }
    assert structure_id(a, t) == structure_id(b, t)
    assert structure_id(a, t) != structure_id({"expression": "a+a*x", "parameters": {"a": 1}}, t)
    assert structure_id(a, t) != structure_id(a, t | {"task_id": "two"})
    assert structure_id({"expression": "1.01*x"}, t) != structure_id({"expression": "1.02*x"}, t)


def test_adaptive_search_executes_rejections_feedback_and_shared_fitting():
    t = {
        "scenario_id": "S",
        "task_id": "T",
        "inputs": ["temperature"],
        "output": "target",
        "quantity_units": {"temperature": "K", "target": "W/m2"},
        "metric": {"primary": "mae"},
        "stability": {"domain": "fixture"},
        "equation_templates": atmosphere_templates()[:1],
    }
    t["equation_templates"][0]["parameters"]["emissivity"]["initial"] = 0.6
    rows = [
        {
            "sample_id": str(i),
            "group": "g",
            "temperature": float(k),
            "target": 0.75 * 5.670374419e-8 * k**4,
        }
        for i, k in enumerate(range(270, 310, 4))
    ]

    class Gateway:
        def __init__(self):
            self.calls = []

        def complete(self, **req):
            self.calls.append(req)
            bad = copy.deepcopy(t["equation_templates"][0])
            bad["nodes"][0]["expression"] = "exp(temperature)"
            if len(self.calls) == 2:
                bad = copy.deepcopy(t["equation_templates"][0])
                bad["name"] = "Emission with background offset"
                bad["parameters"]["background"] = dict(
                    initial=0,
                    bounds=[-100, 100],
                    unit="W/m2",
                    meaning="Unresolved background irradiance",
                )
                bad["nodes"][-1]["expression"] += " + background"
            return {"text": json.dumps({"systems": [bad]})}

    g = Gateway()
    result = execute_method(
        "equation_agent",
        t,
        rows[:6],
        rows[6:],
        gateway=g,
        roles={"coder": "explicit-model"},
        run_id="fixture",
    )
    assert result["status"] == "complete" and len(g.calls) == 2
    assert (
        result["accounting"]["residual_evaluations"] > result["accounting"]["optimizer_evaluations"]
    )
    assert result["accounting"]["fitting_attempts"] == 4
    assert result["rules"][0]["parameters"]["emissivity"] == pytest.approx(0.75)
    assert "dimensionless" in g.calls[1]["prompt"]
    assert result["method_evidence"]["failures"]
    assert all(c["model"] == "explicit-model" for c in g.calls)
