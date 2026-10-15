from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from .hashing import digest


def now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class RuleCard:
    rule_id: str
    task_id: str
    method_id: str
    method_version: str
    model_ids: tuple[str, ...]
    expression: str
    inputs: tuple[str, ...]
    output: str
    parameters: dict[str, float] = field(default_factory=dict)
    applicability: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)
    execution_status: str = "complete"
    created_at: str = field(default_factory=now)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {
            "model_ids": list(self.model_ids),
            "inputs": list(self.inputs),
            "rule_sha256": digest(asdict(self)),
        }


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    scenario_id: str
    task_id: str
    method_id: str
    config_sha256: str
    data_edition: str
    model_ids: tuple[str, ...]
    budget_cny: float
    started_at: str = field(default_factory=now)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {
            "model_ids": list(self.model_ids),
            "manifest_sha256": digest(asdict(self)),
        }


@dataclass(frozen=True)
class EvaluationReceipt:
    receipt_id: str
    rule_id: str
    task_id: str
    status: str
    accuracy: dict[str, Any]
    simplicity: dict[str, Any]
    stability: dict[str, Any]
    coverage: dict[str, Any]
    evaluator_version: str
    test_exposure: str
    created_at: str = field(default_factory=now)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {"receipt_sha256": digest(asdict(self))}
