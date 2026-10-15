"""Installed-package, synthetic two-stage fitting/assessment proof. No paid calls."""

import inspect
import json
from pathlib import Path

import numpy as np

from principia_asd.engine.bound_search import BoundSearch
from principia_asd.evaluate.bound import evaluate_bound_candidate
from principia_asd.evaluate.metrics import pareto_front
from principia_asd.io import file_sha, write_json
from principia_asd.runtime import now


def verify():
    task = {
        "inputs": ["x"],
        "output": "y",
        "metric": {"primary": "rmse"},
        "stability": {"ranking": False, "relative_noise": 0.01},
    }

    def rows(label, values):
        return [
            {
                "sample_id": f"{label}-{i}",
                "group": label,
                "x": float(x),
                "y": float(0.4 + 0.2 * np.tanh(x / 2)),
            }
            for i, x in enumerate(values)
        ]

    host = BoundSearch(
        task, rows("train", range(-3, 4)), rows("dev", [-2.5, -0.5, 1.5]), max_fits=4
    )
    stats = host.normalization("x")
    first = host.fit(
        "p0+p1*z", {"p0": 0, "p1": 1}, bindings=stats, kernels={"z": "tanh((x-center)/scale)"}
    )
    assert first is not None
    patch = host.promote(first["candidate_id"])
    second = host.fit(
        "p0+p1*K",
        {"p0": 0, "p1": 1},
        bindings=patch["bindings"],
        kernels={"K": patch["expression"]},
    )
    assert second is not None
    assert host.fit("0.123*x") is None  # Copied coefficients cannot claim to be fixed.
    assert host.fit("p0*log(x)", {"p0": 1}) is None  # Preserve an executed domain failure.
    frozen = json.loads(json.dumps(host.freeze()))
    inputs = [{"x": x, "group": "synthetic-assessment"} for x in [-4.0, -0.75, 1.25, 4.0]]
    targets = [0.4 + 0.2 * np.tanh(r["x"] / 2) for r in inputs]
    receipt = evaluate_bound_candidate(
        frozen, frozen["sha256"], second["candidate_id"], inputs, targets
    )
    assert receipt["accuracy"]["primary_error"] < 1e-8
    assert receipt == evaluate_bound_candidate(
        frozen, frozen["sha256"], second["candidate_id"], inputs, targets
    )
    assert not pareto_front([receipt])
    profile = receipt["simplicity"]
    assert [
        profile[k]
        for k in ["final_stage_parameters", "inherited_fitted_scalars", "train_statistic_scalars"]
    ] == [2, 2, 2]
    assert frozen["accounting"]["fitting_attempts"] == 3
    assert len(frozen["failures"]) == 2
    try:
        host.fit("x")
    except ValueError:
        pass
    else:
        raise AssertionError("Assessment epoch permitted revision")
    report = {
        "checked_at": now(),
        "status": "passed_development_integration",
        "scope": "Synthetic host normalization, real fitting, kernel promotion, freeze and zero-fit assessment",
        "module_sha256": file_sha(Path(inspect.getfile(BoundSearch))),
        "evaluator_sha256": file_sha(Path(inspect.getfile(evaluate_bound_candidate))),
        "source_is_installed_distribution": "site-packages" in inspect.getfile(BoundSearch),
        "historical_campaign_changed": False,
        "private_data_accessed": False,
        "api_calls": 0,
        "real_scientific_trial": False,
        "ranking_authorized": False,
        "integration_remaining": [
            "multi-role model protocol",
            "bounded worker and UI method option",
            "symmetric control/adaptation integration",
            "new configuration freeze and pilot",
        ],
        "frozen_inquiry": frozen,
        "assessment": receipt,
    }
    project = Path(__file__).resolve().parents[1]
    write_json(project / "docs/BOUND_SEARCH_VERIFICATION.json", report)
    print({k: v for k, v in report.items() if k not in {"frozen_inquiry", "assessment"}})


if __name__ == "__main__":
    verify()
