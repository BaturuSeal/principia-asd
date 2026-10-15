from __future__ import annotations

from .registry import METHODS


def cards() -> list[dict]:
    return [spec.as_dict() for spec in METHODS.values()]
