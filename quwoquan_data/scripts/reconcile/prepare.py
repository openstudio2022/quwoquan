"""Prepare patch_plan input for Agent."""
from __future__ import annotations

from pathlib import Path

from _common.paths import batch_inputs_dir, batch_assistant_tasks, batch_command_root
from _common.io import read_json, write_json, write_assistant_task


def prepare_patch_plan(task_id: str, batch_id: str) -> Path | None:
    """Generate patch_plan input from diff_report. Returns None if no patches needed."""
    rec_root = batch_command_root(task_id, batch_id, "reconcile")
    diff_path = rec_root / "diff_report.json"

    if not diff_path.exists():
        return None

    diff_report = read_json(diff_path)
    if diff_report.get("totalDrifts", 0) == 0 and not diff_report.get("pendingEntities") and not diff_report.get("pendingTags"):
        return None

    inputs_dir = batch_inputs_dir(task_id, batch_id, "reconcile", "patch_plan")
    inputs_dir.mkdir(parents=True, exist_ok=True)

    ref = f"{task_id}_{batch_id}"
    write_json(inputs_dir / f"{ref}.json", {
        "schemaVersion": "quwoquan_data.stage_envelope",
        "taskId": task_id, "batchId": batch_id,
        "step": "patch_plan", "ref": ref,
        "payload": diff_report,
    })

    manifest_path = batch_assistant_tasks(task_id, batch_id, "reconcile", "patch_plan")
    results_dir = inputs_dir.parent.parent / "results" / "patch_plan"
    write_assistant_task(manifest_path, step="patch_plan", input_dir=inputs_dir, result_dir=results_dir, refs=[ref])
    return inputs_dir
