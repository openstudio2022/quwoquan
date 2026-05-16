"""Prepare inputs for download command steps."""
from __future__ import annotations

from pathlib import Path

from _common.paths import batch_inputs_dir, batch_assistant_tasks
from _common.io import write_json, write_assistant_task


def prepare_source_plan(task_id: str, batch_id: str, entities: list[dict]) -> Path:
    """Prepare source_plan inputs from entity catalog."""
    inputs_dir = batch_inputs_dir(task_id, batch_id, "download", "source_plan")
    inputs_dir.mkdir(parents=True, exist_ok=True)

    refs = []
    for ent in entities:
        ref = ent.get("entityId", ent.get("id"))
        write_json(inputs_dir / f"{ref}.json", {
            "schemaVersion": "quwoquan_data.stage_envelope",
            "taskId": task_id, "batchId": batch_id,
            "step": "source_plan", "ref": ref,
            "payload": {
                "entityId": ref,
                "canonicalName": ent.get("canonicalName", ""),
                "entityType": ent.get("entityType", ""),
                "existingSources": ent.get("existingSources", []),
            },
        })
        refs.append(ref)

    manifest_path = batch_assistant_tasks(task_id, batch_id, "download", "source_plan")
    results_dir = inputs_dir.parent.parent / "results" / "source_plan"
    write_assistant_task(manifest_path, step="source_plan", input_dir=inputs_dir, result_dir=results_dir, refs=refs)
    return inputs_dir


def prepare_source_screen(task_id: str, batch_id: str, fetched_sources: list[dict]) -> Path:
    """Prepare source_screen inputs from fetched source summaries."""
    inputs_dir = batch_inputs_dir(task_id, batch_id, "download", "source_screen")
    inputs_dir.mkdir(parents=True, exist_ok=True)

    refs = []
    for src in fetched_sources:
        ref = src.get("sourceId", src.get("id"))
        write_json(inputs_dir / f"{ref}.json", {
            "schemaVersion": "quwoquan_data.stage_envelope",
            "taskId": task_id, "batchId": batch_id,
            "step": "source_screen", "ref": ref,
            "payload": src,
        })
        refs.append(ref)

    manifest_path = batch_assistant_tasks(task_id, batch_id, "download", "source_screen")
    results_dir = inputs_dir.parent.parent / "results" / "source_screen"
    write_assistant_task(manifest_path, step="source_screen", input_dir=inputs_dir, result_dir=results_dir, refs=refs)
    return inputs_dir
