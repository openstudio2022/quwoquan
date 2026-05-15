"""Apply patches from Agent's patch_plan results."""
from __future__ import annotations

from pathlib import Path

from _common.paths import task_entities, task_tags, task_graph, batch_results_dir
from _common.io import read_json, read_ndjson, write_ndjson


def apply_patches(task_id: str, batch_id: str) -> dict:
    """Apply patch_plan results to entities/tags/graph. Returns summary."""
    results_dir = batch_results_dir(task_id, batch_id, "reconcile", "patch_plan")
    summary = {"entitiesAdded": 0, "tagsAdded": 0, "relationsAdded": 0}

    if not results_dir.exists():
        return summary

    for result_file in results_dir.glob("*.json"):
        result = read_json(result_file)
        payload = result.get("payload", result)
        patches = payload.get("patches", [])

        for patch in patches:
            action = patch.get("action")
            if action == "add_entity":
                _append_entity(task_id, patch.get("entity", {}))
                summary["entitiesAdded"] += 1
            elif action == "add_tag":
                _append_tag(task_id, patch.get("tag", {}))
                summary["tagsAdded"] += 1
            elif action == "add_relation":
                _append_relation(task_id, patch.get("relation", {}))
                summary["relationsAdded"] += 1

    return summary


def _append_entity(task_id: str, entity: dict) -> None:
    path = task_entities(task_id)
    rows = read_ndjson(path) if path.exists() else []
    rows.append(entity)
    write_ndjson(path, rows)


def _append_tag(task_id: str, tag: dict) -> None:
    path = task_tags(task_id)
    rows = read_ndjson(path) if path.exists() else []
    rows.append(tag)
    write_ndjson(path, rows)


def _append_relation(task_id: str, relation: dict) -> None:
    path = task_graph(task_id) / "relations.ndjson"
    rows = read_ndjson(path) if path.exists() else []
    rows.append(relation)
    write_ndjson(path, rows)
