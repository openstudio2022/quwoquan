"""任务级 publish 输入物化。"""
from __future__ import annotations

import shutil
from collections import Counter
from pathlib import Path
from typing import Any

from _common.io import read_json, write_ndjson
from _common.paths import batch_post_roots, task_data, task_entities, task_entity_pages, task_graph, task_tags


def _entity_row(entity_dir: Path, task_id: str) -> dict[str, Any] | None:
    entity_json = entity_dir / "_entity.json"
    if not entity_json.is_file():
        return None
    data = read_json(entity_json)
    parts = entity_dir.relative_to(task_data(task_id).entities_dir()).parts
    if len(parts) < 3:
        return None
    domain, etype = parts[0], parts[1]
    name = "/".join(parts[2:])
    entity_ref = f"/entity/{domain}/{etype}/{name}"
    tag_refs = [str(t) for t in (data.get("tagRefs") or []) if str(t)]
    geo_tag = str(data.get("geoTagRef") or "").strip()
    if geo_tag:
        tag_refs.append(geo_tag)
    return {
        "entityRef": entity_ref,
        "entityPath": f"entities/{domain}/{etype}/{name}",
        "domain": domain,
        "etype": etype,
        "name": name,
        "label": data.get("label") or name,
        "tagRefs": sorted(set(tag_refs)),
        "geoTagRef": geo_tag,
        "sourceTaskId": data.get("sourceTaskId") or task_id,
        "updatedAt": data.get("updatedAt") or "",
    }


def materialize_task_publish_inputs(task_id: str, batch_id: str) -> dict[str, int]:
    """把 task 级 publish 门所需汇总输入物化出来。"""
    entities_dir = task_data(task_id).entities_dir()
    entity_page_root = task_entity_pages(task_id)
    if entity_page_root.exists():
        shutil.rmtree(entity_page_root)
    entity_page_root.parent.mkdir(parents=True, exist_ok=True)
    if entities_dir.is_dir():
        shutil.copytree(entities_dir, entity_page_root)

    entity_rows: list[dict[str, Any]] = []
    tag_counts: Counter[str] = Counter()
    graph_rows: list[dict[str, Any]] = []

    if entities_dir.is_dir():
        for entity_json in sorted(entities_dir.rglob("_entity.json")):
            row = _entity_row(entity_json.parent, task_id)
            if not row:
                continue
            entity_rows.append(row)
            for tag in row["tagRefs"]:
                tag_counts[tag] += 1
                graph_rows.append(
                    {
                        "source": row["entityRef"],
                        "target": tag,
                        "kind": "entity-tag",
                        "weight": 1,
                    }
                )

    post_tag_counts: Counter[str] = Counter()
    post_count = 0
    for posts_root in batch_post_roots(task_id, batch_id):
        for manifest in sorted(posts_root.rglob("manifest.json")):
            try:
                data = read_json(manifest)
            except Exception:  # noqa: BLE001
                continue
            post_count += 1
            rel = manifest.parent.relative_to(posts_root).as_posix()
            tag_refs = [str(t) for t in (data.get("tagRefs") or []) if str(t)]
            geo_tag = str(data.get("geoTagRef") or "").strip()
            if geo_tag:
                tag_refs.append(geo_tag)
            tag_refs = sorted(set(tag_refs))
            for tag in tag_refs:
                tag_counts[tag] += 1
                post_tag_counts[tag] += 1
                graph_rows.append(
                    {
                        "source": f"posts/{rel}",
                        "target": tag,
                        "kind": "post-tag",
                        "weight": 1,
                    }
                )

    tag_rows = [
        {
            "tagRef": tag,
            "label": tag.split("/")[-1],
            "objectCount": count,
            "entityCount": count - post_tag_counts.get(tag, 0),
            "postCount": post_tag_counts.get(tag, 0),
        }
        for tag, count in sorted(tag_counts.items())
    ]

    write_ndjson(task_entities(task_id), entity_rows)
    write_ndjson(task_tags(task_id), tag_rows)
    write_ndjson(task_graph(task_id) / "relations.ndjson", graph_rows)

    return {
        "entityCount": len(entity_rows),
        "postCount": post_count,
        "tagCount": len(tag_rows),
        "relationCount": len(graph_rows),
    }
