"""Validate produce command results."""
from __future__ import annotations

from _common.paths import batch_results_dir
from _common.io import read_json
from _common.schema import validate_result


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
            continue

        schema_name = step if step in {"quality_analysis", "compose", "review", "reverse_extract"} else None
        for result_file in results:
            envelope = read_json(result_file)
            payload = envelope.get("payload", envelope)
            if schema_name:
                file_errors = validate_result(payload, "produce", schema_name)
                for error in file_errors:
                    errors.append(f"{result_file.name}: {error}")

    return errors
