"""Prepare inputs for download command steps."""
from __future__ import annotations

from pathlib import Path

from _common.paths import (
    STAGE_DOWNLOAD,
    batch_assistant_task,
    batch_assistant_tasks_dir,
    batch_root,
    batch_shared_dir,
)
from _common.io import write_json, write_assistant_task
from _common.source_catalog import source_plan_guidance, vertical_from_task_id
from _common.source_unit import resolve_entity_object_dir
from vertical.source_registry import build_travel_source_guidance


def prepare_source_plan(task_id: str, batch_id: str, entities: list[dict]) -> Path:
    """对象优先 source_plan：每个实体的采源计划落对象目录 1.download/source_plan.json。

    规格 §15：source_plan 是实体对象自身的过程输入，不在批次顶层 inputs/results 平铺。
    会话任务清单落 _shared/assistant_tasks（批次工作区，可清理可重投）。
    """
    guidance = source_plan_guidance(vertical_from_task_id(task_id))
    vertical = vertical_from_task_id(task_id)
    registry_guidance = build_travel_source_guidance() if vertical == "travel" else {}
    refs = []
    for ent in entities:
        ref = ent.get("entityId", ent.get("id"))
        etype = ent.get("entityType", "")
        obj = resolve_entity_object_dir(task_id, batch_id, ref, etype_hint=etype)
        plan_path = obj / STAGE_DOWNLOAD / "source_plan.json"
        if not plan_path.is_file():
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            write_json(plan_path, {
                "schemaVersion": "quwoquan_data.stage_envelope",
                "taskId": task_id, "batchId": batch_id,
                "step": "source_plan", "ref": ref,
                "payload": {
                    "entityId": ref,
                    "canonicalName": ent.get("canonicalName", ""),
                    "entityType": ent.get("entityType", ""),
                    # 源类别引导（「全」）：agent 据此按类别全面采源、按 examplePlatforms 标 platform
                    "sourceCategoryGuidance": guidance,
                    "sourceRegistryGuidance": registry_guidance,
                    "sources": ent.get("sources", []),
                },
            })
        refs.append(ref)

    manifest_path = batch_assistant_tasks_dir(task_id, batch_id) / "download_source_plan.json"
    write_assistant_task(
        manifest_path,
        step="source_plan",
        input_dir=batch_root(task_id, batch_id) / "entities",
        result_dir=batch_root(task_id, batch_id) / "entities",
        refs=refs,
    )
    return batch_root(task_id, batch_id) / "entities"


def prepare_source_screen(task_id: str, batch_id: str, fetched_sources: list[dict]) -> Path:
    """Prepare source_screen inputs from fetched source summaries."""
    inputs_dir = batch_shared_dir(task_id, batch_id) / "download_source_screen"
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

    manifest_path = batch_assistant_task(task_id, batch_id, "download", "source_screen")
    write_assistant_task(manifest_path, step="source_screen", input_dir=inputs_dir, result_dir=inputs_dir, refs=refs)
    return inputs_dir
