"""Validate download command results."""
from __future__ import annotations

from _common.paths import batch_results_dir, batch_command_root
from _common.io import read_json


def validate_download_results(task_id: str, batch_id: str) -> list[str]:
    """Validate download step results."""
    errors = []

    source_plan_dir = batch_results_dir(task_id, batch_id, "download", "source_plan")
    if not source_plan_dir.exists():
        errors.append("No source_plan results")
        return errors

    for f in sorted(source_plan_dir.glob("*.json")):
        result = read_json(f)
        sources = result.get("payload", {}).get("sources", [])
        if len(sources) < 2:
            errors.append(f"{f.name}: fewer than 2 sources planned")

    return errors
