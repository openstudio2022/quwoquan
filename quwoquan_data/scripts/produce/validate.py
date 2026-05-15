"""Validate produce command results."""
from __future__ import annotations

from _common.paths import batch_results_dir
from _common.io import read_json


def validate_produce_results(task_id: str, batch_id: str) -> list[str]:
    """Validate produce outputs at each step."""
    errors = []

    for step in ("quality_analysis", "compose", "review", "reverse_extract"):
        results_dir = batch_results_dir(task_id, batch_id, "produce", step)
        if not results_dir.exists():
            errors.append(f"No {step} results directory")
            continue

        results = list(results_dir.glob("*.json"))
        if not results:
            errors.append(f"No {step} result files")

    return errors
