"""Deterministic diff: compare entities/tags/graph with post references."""
from __future__ import annotations

from pathlib import Path

from _common.paths import task_entities, task_tags, task_graph, batch_command_root
from _common.io import read_ndjson, write_json


def compute_diff(task_id: str, batch_id: str) -> dict:
    """Compare catalog with post manifests. Returns diff report."""
    entities = []
    entities_path = task_entities(task_id)
    if entities_path.exists():
        entities = read_ndjson(entities_path)

    tags = []
    tags_path = task_tags(task_id)
    if tags_path.exists():
        tags = read_ndjson(tags_path)

    entity_ids = {e.get("entityId") for e in entities}
    tag_ids = {t.get("tagId") for t in tags}

    produce_root = batch_command_root(task_id, batch_id, "produce")
    posts_dir = produce_root / "posts"

    drifts = []

    if posts_dir.exists():
        for manifest_path in posts_dir.rglob("manifest.json"):
            from _common.io import read_json
            manifest = read_json(manifest_path)
            for eref in manifest.get("entityRefs", []):
                if eref not in entity_ids:
                    drifts.append({"type": "missing_entity", "ref": eref, "source": str(manifest_path)})
            for tref in manifest.get("tagRefs", []):
                if tref not in tag_ids:
                    drifts.append({"type": "missing_tag", "ref": tref, "source": str(manifest_path)})

    # Check reverse-extract pending candidates
    re_results_dir = produce_root / "results" / "reverse_extract"
    pending_entities = []
    pending_tags = []
    if re_results_dir.exists():
        for f in re_results_dir.glob("*.json"):
            from _common.io import read_json
            result = read_json(f)
            payload = result.get("payload", result)
            pending_entities.extend(payload.get("extractedEntities", []))
            pending_tags.extend(payload.get("extractedTags", []))

    diff_report = {
        "totalEntities": len(entities),
        "totalTags": len(tags),
        "totalDrifts": len(drifts),
        "drifts": drifts,
        "pendingEntities": pending_entities,
        "pendingTags": pending_tags,
    }

    output_path = batch_command_root(task_id, batch_id, "reconcile") / "diff_report.json"
    write_json(output_path, diff_report)
    return diff_report
