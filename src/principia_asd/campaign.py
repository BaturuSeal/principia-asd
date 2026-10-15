"""Public compatibility entry point; new runs use immutable IDs and separate evaluation."""

from .io import read_csv as read_rows
from .runtime import discover_run, evaluate_run

__all__ = ["discover_run", "evaluate_run", "read_rows"]
