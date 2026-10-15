import copy

import numpy as np
import pytest

from principia_asd.engine.bindings import (
    StateRegistry,
    compile_program,
    execute_program,
    verify_program,
)
from principia_asd.io import sha


def registry():
    artifacts = [
        {
            "scope": "train",
            "status": "complete",
            "kind": "train_fitted",
            "values": {"a": 0.45, "b": -0.11, "c": 0.95},
        },
        {
            "scope": "train",
            "status": "complete",
            "kind": "train_statistic",
            "values": {"mean": 2.0, "std": 3.0},
        },
        {
            "scope": "fixed",
            "status": "complete",
            "kind": "fixed_scientific",
            "values": {"zero": 0.0, "one": 1.0},
        },
    ]
    host = StateRegistry({sha(a): a for a in artifacts})
    refs = {
        name: host.register(sha(a), ["values", name], a["kind"])
        for a in artifacts
        for name in a["values"]
    }
    return host, refs


def test_inherited_fit_and_normalization_are_distinct_and_predict_identically():
    host, refs = registry()
    bindings = {k: refs[k] for k in ["a", "b", "c", "mean", "std"]}
    rule = compile_program(
        "p0+p1*(a+b*(x-mean)/std+c*x)", ["x"], {"p0": 0.2, "p1": 2}, bindings, host
    )
    assert rule["simplicity"]["final_stage_parameters"] == 2
    assert rule["simplicity"]["inherited_fitted_scalars"] == 3
    assert rule["simplicity"]["train_statistic_scalars"] == 2
    assert rule["simplicity"]["learned_scalar_count"] == 7
    assert rule["simplicity"]["learned_state_bytes"] == 56
    assert rule["simplicity"]["degrees_of_freedom"] == "not_assessed"
    x = np.array([1.0, 2.0, 3.0])
    np.testing.assert_allclose(
        execute_program(rule, {"x": x}, host), 0.2 + 2 * (0.45 - 0.11 * (x - 2) / 3 + 0.95 * x)
    )


def test_kernel_renaming_and_inlining_do_not_hide_complexity():
    host, refs = registry()
    bindings = {"center": refs["mean"], "scale": refs["std"]}
    a = compile_program(
        "p0+p1*K",
        ["x"],
        {"p0": 1, "p1": 2},
        bindings,
        host,
        kernels={"K": "tanh((x-center)/scale)"},
    )
    b = compile_program("p0+p1*tanh((x-center)/scale)", ["x"], {"p0": 1, "p1": 2}, bindings, host)
    c = compile_program(
        "p0+p1*Renamed",
        ["x"],
        {"p0": 1, "p1": 2},
        {"other": refs["mean"], "denom": refs["std"]},
        host,
        kernels={"Renamed": "tanh((x-other)/denom)"},
    )
    assert a["simplicity"] == b["simplicity"] == c["simplicity"]
    assert a["expression"] == b["expression"] == c["expression"]


def test_same_learned_state_shared_twice_is_counted_once():
    host, refs = registry()
    p = compile_program("left*x+right*x", ["x"], {}, {"left": refs["a"], "right": refs["a"]}, host)
    assert p["simplicity"]["learned_scalar_count"] == 1
    assert p["simplicity"]["weighted_operator_count"] == 3


def test_equal_numbers_from_distinct_sources_are_not_merged():
    host, refs = registry()
    artifact = {
        "scope": "train",
        "status": "complete",
        "kind": "train_fitted",
        "values": {"other": 0.45},
    }
    host.artifacts[sha(artifact)] = artifact
    second = host.register(sha(artifact), ["values", "other"], "train_fitted")
    p = compile_program("left*x+right", ["x"], {}, {"left": refs["a"], "right": second}, host)
    assert p["simplicity"]["inherited_fitted_scalars"] == 2


def test_fixed_constants_expanded_but_not_claimed_as_learned():
    host, refs = registry()
    p = compile_program(
        "minimum(one,maximum(zero,p0*x))",
        ["x"],
        {"p0": 2},
        {"one": refs["one"], "zero": refs["zero"]},
        host,
    )
    assert p["simplicity"]["fixed_scientific_scalars"] == 2
    assert p["simplicity"]["learned_scalar_count"] == 1
    assert p["simplicity"]["ranking_authorized"] is False


@pytest.mark.parametrize("expression", ["0.4565726363721293*x", "x+1", "x**2", 'x+"opaque"'])
def test_unbound_literals_rejected_even_inside_kernels(expression):
    host, _ = registry()
    with pytest.raises(ValueError, match="Unbound literal"):
        compile_program("K", ["x"], {}, {}, host, kernels={"K": expression})


@pytest.mark.parametrize("scope", ["dev", "test", "confirmation", "unknown"])
def test_development_and_confirmation_state_rejected(scope):
    artifact = {"scope": scope, "status": "complete", "kind": "train_fitted", "values": {"a": 0.4}}
    host = StateRegistry({sha(artifact): artifact})
    with pytest.raises(ValueError, match="scope"):
        host.register(sha(artifact), ["values", "a"], "train_fitted")


@pytest.mark.parametrize("value", [[1, 2], {"lookup": 1}, True, None, float("inf"), 1e101])
def test_opaque_nonfinite_or_oversize_state_rejected(value):
    host, refs = registry()
    with pytest.raises((ValueError, TypeError)):
        compile_program("p0*x", ["x"], {"p0": value}, {}, host)


@pytest.mark.parametrize("field,value", [("status", "pending"), ("kind", "fixed_scientific")])
def test_trusted_artifact_status_and_kind_cannot_be_relabelled(field, value):
    artifact = {
        "scope": "train",
        "status": "complete",
        "kind": "train_fitted",
        "values": {"a": 0.4},
    }
    artifact[field] = value
    host = StateRegistry({sha(artifact): artifact})
    with pytest.raises(ValueError):
        host.register(sha(artifact), ["values", "a"], "train_fitted")


def test_mutated_artifact_detected_even_when_compiled_program_unchanged():
    host, refs = registry()
    p = compile_program("a*x", ["x"], {}, {"a": refs["a"]}, host)
    digest = host.records[refs["a"]]["artifact_sha256"]
    host.artifacts[digest]["values"]["a"] = 123
    with pytest.raises(ValueError, match="mutation"):
        execute_program(p, {"x": np.array([1.0])}, host)


@pytest.mark.parametrize(
    "field", ["expression", "execution_values", "simplicity", "states", "sha256"]
)
def test_compiled_artifact_mutations_rejected(field):
    host, refs = registry()
    p = compile_program("a*x", ["x"], {}, {"a": refs["a"]}, host)
    bad = copy.deepcopy(p)
    bad[field] = "tampered"
    with pytest.raises(ValueError, match="mutation"):
        verify_program(bad, host)


def test_unused_state_and_recursive_or_opaque_kernels_rejected():
    host, refs = registry()
    with pytest.raises(ValueError, match="Unused"):
        compile_program("x", ["x"], {}, {"a": refs["a"]}, host)
    with pytest.raises(ValueError, match="Recursive"):
        compile_program("K", ["x"], {}, {}, host, kernels={"K": "L", "L": "K"})
    with pytest.raises(ValueError, match="Unsupported"):
        compile_program("K", ["x"], {}, {}, host, kernels={"K": "lookup(x)"})


def test_parameter_budget_and_measurement_identity():
    host, _ = registry()
    with pytest.raises(ValueError, match="eight"):
        compile_program("x", ["x"], {f"p{i}": 1 for i in range(9)}, {}, host)
    p = compile_program("p0*x", ["x"], {"p0": 1}, {}, host)
    with pytest.raises(ValueError, match="inventory"):
        execute_program(p, {"x": np.array([1.0]), "target": np.array([2.0])}, host)


def test_unknown_binding_and_namespace_collision():
    host, _ = registry()
    with pytest.raises(KeyError):
        compile_program("a*x", ["x"], {}, {"a": "missing"}, host)
    with pytest.raises(ValueError, match="collide"):
        compile_program("x", ["x"], {}, {}, host, kernels={"x": "x"})


def test_inherited_fits_cannot_evade_total_parameter_capacity():
    host, refs = registry()
    with pytest.raises(ValueError, match="eight fitted scalars"):
        compile_program(
            "p0+p1+p2+p3+p4+p5+a+b+c+x",
            ["x"],
            {f"p{i}": 1 for i in range(6)},
            {k: refs[k] for k in ["a", "b", "c"]},
            host,
        )
