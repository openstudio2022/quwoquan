"""存量 publish 实体标签回填（WP3-5）。

历史 H100 批次的 `publish/entities/**/_entity.json` 缺 `geoTagRef` 与
Entity 类型 tagRefs（index 分片全落 `unknown`）。本模块经受版本控制的
回填映射（`verticals/travel/coverage/legacy_h100_entity_tag_backfill.yaml`）
把地理/类型标签合并进发布态实体，并强制同一次操作内重建 lookup 索引——
「不许手改后不重建索引」由 apply 通路本身保证。

合并契约（对齐 build/homepage.py 物化形态与 schema/publish/entity.schema.json）：

- ``geoTagRef``：映射为准（须命中 ``Topic/地理/行政区/**`` 真实树节点）；
  既有非空且不同时记入报告 ``overriddenGeoTagRef``。
- ``geoTagRefs``：映射提供时写入，且必须包含 ``geoTagRef``。
- ``tagRefs``：既有 + typeTagRefs + geoTagRef(+geoTagRefs) 保序去重合并，
  不清除既有 Topic/Format 标签。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from _common.coverage_master_list import is_tag_node
from _common.entity_type_taxonomy import CONTRACT_TAGS_ROOT
from _common.io import read_json, write_json
from _common.paths import PUBLISH_ROOT

BACKFILL_SCHEMA_VERSION = "quwoquan_data.entity_tag_backfill/1"
GEO_TAG_PREFIX = "Topic/地理/行政区/"
ENTITY_TAG_PREFIX = "Entity/"


@dataclass
class BackfillChange:
    entity_ref: str
    entity_json: Path
    geo_tag_ref: str
    previous_geo_tag_ref: str
    geo_tag_refs: list[str]
    added_tag_refs: list[str]
    merged_tag_refs: list[str]

    @property
    def changed(self) -> bool:
        return bool(self.added_tag_refs) or self.geo_tag_ref != self.previous_geo_tag_ref


@dataclass
class BackfillPlan:
    changes: list[BackfillChange] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def load_backfill_map(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if data.get("schemaVersion") != BACKFILL_SCHEMA_VERSION:
        raise ValueError(
            f"回填映射 schemaVersion 必须是 {BACKFILL_SCHEMA_VERSION}: {path}"
        )
    entities = data.get("entities")
    if not isinstance(entities, list) or not entities:
        raise ValueError(f"回填映射 entities 必须是非空列表: {path}")
    rows: list[dict[str, Any]] = []
    for idx, row in enumerate(entities):
        if not isinstance(row, dict):
            raise ValueError(f"回填映射 entities[{idx}] 必须是对象: {path}")
        entity_ref = str(row.get("entityRef") or "").strip().strip("/")
        geo_tag_ref = str(row.get("geoTagRef") or "").strip()
        type_tag_refs = [str(t).strip() for t in (row.get("typeTagRefs") or []) if str(t).strip()]
        if not entity_ref or len(entity_ref.split("/")) < 3:
            raise ValueError(f"entities[{idx}].entityRef 必须是三段 domain/etype/name: {row}")
        if not geo_tag_ref or not type_tag_refs:
            raise ValueError(f"entities[{idx}] geoTagRef 与 typeTagRefs 均必填: {entity_ref}")
        rows.append(
            {
                "entityRef": entity_ref,
                "geoTagRef": geo_tag_ref,
                "geoTagRefs": [str(g).strip() for g in (row.get("geoTagRefs") or []) if str(g).strip()],
                "typeTagRefs": type_tag_refs,
            }
        )
    return rows


def _validate_row_tags(row: dict[str, Any], tags_root: Path, issues: list[str]) -> None:
    entity_ref = row["entityRef"]
    geo_tag_ref = row["geoTagRef"]
    if not geo_tag_ref.startswith(GEO_TAG_PREFIX):
        issues.append(f"{entity_ref}: geoTagRef 必须在 {GEO_TAG_PREFIX}** 树内: {geo_tag_ref}")
    elif not is_tag_node(tags_root, geo_tag_ref):
        issues.append(f"{entity_ref}: geoTagRef 未命中行政区契约树节点: {geo_tag_ref}")
    for geo_ref in row["geoTagRefs"]:
        if not is_tag_node(tags_root, geo_ref):
            issues.append(f"{entity_ref}: geoTagRefs 未命中行政区契约树节点: {geo_ref}")
    if row["geoTagRefs"] and geo_tag_ref not in row["geoTagRefs"]:
        issues.append(f"{entity_ref}: geoTagRefs 必须包含主归属 geoTagRef")
    for type_ref in row["typeTagRefs"]:
        if not type_ref.startswith(ENTITY_TAG_PREFIX):
            issues.append(f"{entity_ref}: typeTagRefs 必须在 {ENTITY_TAG_PREFIX}** 树内: {type_ref}")
        elif not is_tag_node(tags_root, type_ref):
            issues.append(f"{entity_ref}: typeTagRefs 未命中类型契约树节点: {type_ref}")


def plan_backfill(
    rows: list[dict[str, Any]],
    *,
    publish_root: Path | None = None,
    tags_root: Path | None = None,
) -> BackfillPlan:
    publish_root = publish_root or PUBLISH_ROOT
    tags_root = tags_root or CONTRACT_TAGS_ROOT
    plan = BackfillPlan()
    for row in rows:
        _validate_row_tags(row, tags_root, plan.issues)
        entity_ref = row["entityRef"]
        entity_json = publish_root / "entities" / entity_ref / "_entity.json"
        if not entity_json.is_file():
            plan.issues.append(f"{entity_ref}: publish 主线不存在 _entity.json: {entity_json}")
            continue
        data = read_json(entity_json)
        previous_geo = str(data.get("geoTagRef") or "").strip()
        existing_tags = [str(t) for t in (data.get("tagRefs") or []) if str(t).strip()]
        incoming = [*row["typeTagRefs"], row["geoTagRef"], *row["geoTagRefs"]]
        merged = list(dict.fromkeys([*existing_tags, *incoming]))
        added = [t for t in merged if t not in existing_tags]
        change = BackfillChange(
            entity_ref=entity_ref,
            entity_json=entity_json,
            geo_tag_ref=row["geoTagRef"],
            previous_geo_tag_ref=previous_geo,
            geo_tag_refs=list(row["geoTagRefs"]),
            added_tag_refs=added,
            merged_tag_refs=merged,
        )
        if change.changed:
            plan.changes.append(change)
        else:
            plan.unchanged.append(entity_ref)
    return plan


def apply_backfill(plan: BackfillPlan) -> list[dict[str, Any]]:
    """写回 _entity.json，返回逐实体变更记录（调用方负责随后重建索引）。"""
    if not plan.ok:
        raise ValueError("回填计划存在未解决 issue，禁止 apply：\n" + "\n".join(plan.issues))
    applied: list[dict[str, Any]] = []
    for change in plan.changes:
        data = read_json(change.entity_json)
        data["geoTagRef"] = change.geo_tag_ref
        if change.geo_tag_refs:
            data["geoTagRefs"] = change.geo_tag_refs
        data["tagRefs"] = change.merged_tag_refs
        write_json(change.entity_json, data)
        applied.append(
            {
                "entityRef": change.entity_ref,
                "geoTagRef": change.geo_tag_ref,
                "overriddenGeoTagRef": (
                    change.previous_geo_tag_ref
                    if change.previous_geo_tag_ref and change.previous_geo_tag_ref != change.geo_tag_ref
                    else ""
                ),
                "addedTagRefs": change.added_tag_refs,
            }
        )
    return applied


def plan_summary(plan: BackfillPlan) -> dict[str, Any]:
    return {
        "changedCount": len(plan.changes),
        "unchangedCount": len(plan.unchanged),
        "issueCount": len(plan.issues),
        "issues": plan.issues,
        "changes": [
            {
                "entityRef": c.entity_ref,
                "geoTagRef": c.geo_tag_ref,
                "previousGeoTagRef": c.previous_geo_tag_ref,
                "addedTagRefs": c.added_tag_refs,
            }
            for c in plan.changes
        ],
    }
