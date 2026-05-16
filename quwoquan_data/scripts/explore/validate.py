"""Validate explore command results."""
from __future__ import annotations

from pathlib import Path

from _common.io import read_json
from _common.schema import validate_result


def validate_explore_results(task_id: str, batch_id: str) -> list[str]:
    """Validate all explore step results. Returns list of error messages."""
    from _common.paths import batch_results_dir
    errors = []

    results_dir = batch_results_dir(task_id, batch_id, "explore", "deduplicate")
    if not results_dir.exists():
        errors.append(f"No deduplicate results directory: {results_dir}")
        return errors

    for result_file in sorted(results_dir.glob("*.json")):
        result = read_json(result_file)
        file_errors = validate_result(result, "explore", "explore_result")
        for e in file_errors:
            errors.append(f"{result_file.name}: {e}")

    return errors
