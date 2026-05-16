"""Prepare inputs for produce command steps."""
from __future__ import annotations

from pathlib import Path

from _common.paths import batch_inputs_dir, batch_assistant_tasks
from _common.io import write_json, write_assistant_task


def prepare_quality_analysis(task_id: str, batch_id: str, sources: list[dict]) -> Path:
    """Prepare quality_analysis inputs from downloaded sources."""
    inputs_dir = batch_inputs_dir(task_id, batch_id, "produce", "quality_analysis")
    inputs_dir.mkdir(parents=True, exist_ok=True)

    refs = []
    for src in sources:
        ref = src.get("topicId", src.get("ref"))
        write_json(inputs_dir / f"{ref}.json", {
            "schemaVersion": "quwoquan_data.stage_envelope",
            "taskId": task_id, "batchId": batch_id,
            "step": "quality_analysis", "ref": ref,
            "payload": src,
        })
        refs.append(ref)

    manifest_path = batch_assistant_tasks(task_id, batch_id, "produce", "quality_analysis")
    results_dir = inputs_dir.parent.parent / "results" / "quality_analysis"
    write_assistant_task(manifest_path, step="quality_analysis", input_dir=inputs_dir, result_dir=results_dir, refs=refs)
    return inputs_dir


def prepare_compose(task_id: str, batch_id: str, quality_results: list[dict]) -> Path:
    """Prepare compose inputs from quality analysis results (only high-scoring)."""
    inputs_dir = batch_inputs_dir(task_id, batch_id, "produce", "compose")
    inputs_dir.mkdir(parents=True, exist_ok=True)

    refs = []
    for qr in quality_results:
        ref = qr.get("ref")
        write_json(inputs_dir / f"{ref}.json", {
            "schemaVersion": "quwoquan_data.stage_envelope",
            "taskId": task_id, "batchId": batch_id,
            "step": "compose", "ref": ref,
            "payload": qr,
        })
        refs.append(ref)

    manifest_path = batch_assistant_tasks(task_id, batch_id, "produce", "compose")
    results_dir = inputs_dir.parent.parent / "results" / "compose"
    write_assistant_task(manifest_path, step="compose", input_dir=inputs_dir, result_dir=results_dir, refs=refs)
    return inputs_dir


def prepare_review(task_id: str, batch_id: str, compose_results: list[dict]) -> Path:
    """Prepare review inputs from compose results."""
    inputs_dir = batch_inputs_dir(task_id, batch_id, "produce", "review")
    inputs_dir.mkdir(parents=True, exist_ok=True)

    refs = []
    for cr in compose_results:
        ref = cr.get("ref")
        write_json(inputs_dir / f"{ref}.json", {
            "schemaVersion": "quwoquan_data.stage_envelope",
            "taskId": task_id, "batchId": batch_id,
            "step": "review", "ref": ref,
            "payload": cr,
        })
        refs.append(ref)

    manifest_path = batch_assistant_tasks(task_id, batch_id, "produce", "review")
    results_dir = inputs_dir.parent.parent / "results" / "review"
    write_assistant_task(manifest_path, step="review", input_dir=inputs_dir, result_dir=results_dir, refs=refs)
    return inputs_dir


def prepare_reverse_extract(task_id: str, batch_id: str, approved_posts: list[dict]) -> Path:
    """Prepare reverse_extract inputs from approved posts."""
    inputs_dir = batch_inputs_dir(task_id, batch_id, "produce", "reverse_extract")
    inputs_dir.mkdir(parents=True, exist_ok=True)

    refs = []
    for post in approved_posts:
        ref = post.get("ref")
        write_json(inputs_dir / f"{ref}.json", {
            "schemaVersion": "quwoquan_data.stage_envelope",
            "taskId": task_id, "batchId": batch_id,
            "step": "reverse_extract", "ref": ref,
            "payload": post,
        })
        refs.append(ref)

    manifest_path = batch_assistant_tasks(task_id, batch_id, "produce", "reverse_extract")
    results_dir = inputs_dir.parent.parent / "results" / "reverse_extract"
    write_assistant_task(manifest_path, step="reverse_extract", input_dir=inputs_dir, result_dir=results_dir, refs=refs)
    return inputs_dir
