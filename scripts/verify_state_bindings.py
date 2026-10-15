"""Offline regression witness using synthetic inputs, not a new scientific trial."""

import inspect
from pathlib import Path

import numpy as np

from principia_asd.engine.bindings import StateRegistry, compile_program, execute_program
from principia_asd.engine.expression import execute
from principia_asd.io import file_sha, read_json, sha, write_json
from principia_asd.runtime import now


def verify():
    project = Path(__file__).resolve().parents[1]
    source = project / "docs/data-reviews/P100-015-embedded-fit-complexity-v1.json"
    witness = read_json(source)
    earlier = witness["earlier_fitted_program"]
    fitted = {
        "kind": "train_fitted",
        "scope": "train",
        "status": "complete",
        "parameters": earlier["parameters"],
        "expression": earlier["expression"],
        "archived_submission_sha256": witness["campaign_submission_sha256"],
        "trace_index": witness["earlier_trace_index"],
    }
    fixed = {
        "kind": "fixed_scientific",
        "scope": "fixed",
        "status": "complete",
        "values": {"zero": 0, "one": 1},
        "meaning": "Fixed binary probability clipping bounds",
    }
    artifacts = {sha(a): a for a in [fitted, fixed]}
    registry = StateRegistry(artifacts)
    bindings = {
        k: registry.register(sha(fitted), ["parameters", f"p{i}"], "train_fitted")
        for i, k in enumerate(["a", "b", "c"])
    }
    bindings.update(
        {
            k: registry.register(sha(fixed), ["values", k], "fixed_scientific")
            for k in ["zero", "one"]
        }
    )
    kernel = "minimum(one,maximum(zero,a+b*(log(income_proxy)-log1p(household_size))+c*(shock/income_proxy)))"
    record = compile_program(
        "minimum(one,maximum(zero,p0+p1*risk))",
        ["income_proxy", "household_size", "shock", "age"],
        witness["final_parameter_map"],
        bindings,
        registry,
        kernels={"risk": kernel},
    )
    columns = {
        "income_proxy": np.array([5.0, 17.5, 37.5, 62.5, 87.5, 125.0, 175.0]),
        "household_size": np.array([1.0, 2.0, 3.0, 4.0, 2.0, 3.0, 1.0]),
        "shock": np.array([0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0]),
        "age": np.arange(20.0, 27.0),
    }
    expected = execute(witness["final_expression"], columns, witness["final_parameter_map"])
    actual = execute_program(record, columns, registry)
    assert np.array_equal(expected, actual)
    assert record["simplicity"]["inherited_fitted_scalars"] == 3
    assert record["simplicity"]["final_stage_parameters"] == 2
    receipt = {
        "checked_at": now(),
        "status": "passed_development_fixture",
        "scope": "Synthetic-input execution equivalence; not a new discovery, fit, evaluation or ranking",
        "witness_sha256": file_sha(source),
        "binding_module_sha256": file_sha(Path(inspect.getfile(StateRegistry))),
        "source_is_installed_distribution": "site-packages" in inspect.getfile(StateRegistry),
        "api_calls": 0,
        "fitting_attempts": 0,
        "test_targets_accessed": False,
        "predictions_bit_identical": True,
        "synthetic_rows": len(expected),
        "active_campaign_implementation_changed": False,
        "integration_status": "not_yet_wired_into_discovery_or_ranking",
        "source_artifacts": artifacts,
        "compiled_program": record,
    }
    write_json(project / "docs/LINEAGE_BINDING_VERIFICATION.json", receipt)
    print({k: v for k, v in receipt.items() if k not in {"source_artifacts", "compiled_program"}})


if __name__ == "__main__":
    verify()
