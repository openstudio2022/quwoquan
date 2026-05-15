"""Validate reconcile results."""
from __future__ import annotations

from _common.paths import batch_results_dir
from _common.io import read_json


def validate_reconcile_results(task_id: str, batch_id: str) -> list[str]:
    """Validate patch_plan results."""
    errors = []
    results_dir = batch_results_dir(task_id, batch_id, "reconcile", "patch_plan")

    if not results_dir.exists():
        return errors

    for f in sorted(results_dir.glob("*.json")):
        result = read_json(f)
        payload = result.get("payload", result)
        patches = payload.get("patches", [])
        for i, patch in enumerate(patches):
            if "action" not in patch:
                errors.append(f"{f.name}: patch[{i}] missing 'action'")

    return errors
