"""Prepare inputs for explore command steps."""
from __future__ import annotations

from pathlib import Path

from _common.paths import batch_inputs_dir, batch_assistant_tasks, ensure_batch_layout
from _common.io import write_json, write_assistant_task


def prepare_deduplicate(task_id: str, batch_id: str, catalog_rows: list[dict]) -> Path:
    """Generate deduplicate inputs from raw geo query results."""
    ensure_batch_layout(task_id, batch_id)
    inputs_dir = batch_inputs_dir(task_id, batch_id, "explore", "deduplicate")
    inputs_dir.mkdir(parents=True, exist_ok=True)

    refs = []
    for row in catalog_rows:
        ref = row.get("topic_id", row.get("id", "unknown"))
        write_json(inputs_dir / f"{ref}.json", {
            "schemaVersion": "quwoquan_data.stage_envelope",
            "taskId": task_id,
            "batchId": batch_id,
            "step": "deduplicate",
            "ref": ref,
            "payload": row,
        })
        refs.append(ref)

    manifest_path = batch_assistant_tasks(task_id, batch_id, "explore", "deduplicate")
    results_dir = batch_inputs_dir(task_id, batch_id, "explore", "deduplicate").parent.parent / "results" / "deduplicate"
    write_assistant_task(manifest_path, step="deduplicate", input_dir=inputs_dir, result_dir=results_dir, refs=refs)
    return inputs_dir
