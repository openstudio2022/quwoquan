"""任务级 publish 输入物化。

runtime task 根只持久化任务级索引输入（entities/tags ndjson）；release 所需的
entity_pages / relations 作为 assemble 阶段派生物，不再长驻 runtime task 目录。
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from core.entity_object import collect_execution_entity_objects
from core.io import read_json, write_ndjson
from core.paths import (
    execution_post_roots,
    iter_execution_ids,
    execution_entities,
    execution_tags,
)


def _entity_row(entity_dir: Path, execution_id: str, *, entity_rel: str) -> dict[str, Any] | None:
    entity_json = entity_dir / "_entity.json"
    if not entity_json.is_file():
        return None
    data = read_json(entity_json)
    parts = Path(entity_rel).parts
    if parts and parts[0] == "entities":
        parts = parts[1:]
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
        "executionId": data.get("executionId") or execution_id,
        "updatedAt": data.get("updatedAt") or "",
    }


def _candidate_batches(execution_id: str) -> list[str]:
    if execution_id.strip():
        return [execution_id]
    # 当前 execution 工作包是唯一过程产物来源。
    return iter_execution_ids(execution_id)


def _collect_task_publish_inputs(execution_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], int]:
    """聚合任务级 publish 输入，不决定落盘位置。"""
    entity_rows: list[dict[str, Any]] = []
    tag_counts: Counter[str] = Counter()
    graph_rows: list[dict[str, Any]] = []

    for item in collect_execution_entity_objects(
        execution_id=execution_id,
        enforce_type_consistency=True,
    ):
        row = _entity_row(Path(item["entityDir"]), execution_id, entity_rel=str(item["entityRel"]))
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
    for candidate_batch in _candidate_batches(execution_id):
        for posts_root in execution_post_roots(candidate_batch):
            for manifest in sorted(posts_root.rglob("manifest.json")):
                try:
                    data = read_json(manifest)
                except Exception:  # noqa: BLE001
                    continue
                rel = manifest.parent.relative_to(posts_root).as_posix()
                post_count += 1
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

    return entity_rows, tag_rows, graph_rows, post_count


def collect_task_publish_inputs(execution_id: str) -> dict[str, Any]:
    """收集 release/publish 组装所需的任务级输入（不写 runtime 镜像目录）。"""
    entity_rows, tag_rows, graph_rows, post_count = _collect_task_publish_inputs(execution_id)
    return {
        "entityRows": entity_rows,
        "tagRows": tag_rows,
        "graphRows": graph_rows,
        "entityCount": len(entity_rows),
        "postCount": post_count,
        "tagCount": len(tag_rows),
        "relationCount": len(graph_rows),
    }


def materialize_task_publish_inputs(execution_id: str) -> dict[str, int]:
    """把 task 级 publish 门所需索引输入物化出来。

    注意：entity_pages / graph/relations.ndjson 不再长驻 runtime task 目录。
    release 如仍需兼容产物，由 assemble 阶段即时派生。
    """
    entity_rows, tag_rows, graph_rows, post_count = _collect_task_publish_inputs(execution_id)
    write_ndjson(execution_entities(execution_id), entity_rows)
    write_ndjson(execution_tags(execution_id), tag_rows)

    return {
        "entityCount": len(entity_rows),
        "postCount": post_count,
        "tagCount": len(tag_rows),
        "relationCount": len(graph_rows),
    }
