#!/usr/bin/env python3
"""校验目录候选层、语义归并结果、实体层、标签层的一致性。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

REPO_ROOT = Path(os.getenv("QWQ_REPO_ROOT", Path(__file__).resolve().parents[3])).resolve()
DATA_ROOT = Path(os.getenv("QWQ_DATA_ROOT", REPO_ROOT / "quwoquan_data")).resolve()
RUNTIME_ROOT = Path(os.getenv("QWQ_RUNTIME_ROOT", DATA_ROOT / "runtime")).resolve()
SEED_ROOT = RUNTIME_ROOT / "seed"


def read_ndjson(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _default_entity_catalog() -> Path:
    return SEED_ROOT / "entity_catalog" / "entities.ndjson"


def _default_tag_catalog() -> Path:
    return SEED_ROOT / "tag_catalog" / "tags.ndjson"


def _default_semantic_candidates() -> Path:
    return SEED_ROOT / "entity_catalog" / "semantic_cluster_candidates.ndjson"


def _entity_lookup_by_name(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    entities_by_name: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        canonical = str(row.get("canonicalName") or "").strip()
        if canonical:
            entities_by_name.setdefault(canonical, []).append(row)
    return entities_by_name


def _resolve_entity_for_catalog_row(
    *,
    topic_id: str,
    normalized_name: str,
    entity_by_topic: dict[str, dict[str, Any]],
    entities_by_name: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    entity_row = entity_by_topic.get(topic_id)
    if entity_row:
        return entity_row
    if normalized_name:
        same_name_rows = entities_by_name.get(normalized_name) or []
        if len(same_name_rows) == 1:
            return same_name_rows[0]
    return None


def _member_listed_in_root(root_entity: dict[str, Any], *, topic_id: str, canonical_name: str) -> bool:
    extensions = root_entity.get("extensions") or {}
    members = extensions.get("members") or []
    for member in members:
        if not isinstance(member, dict):
            continue
        member_name = str(member.get("nameCanonicalZhHans") or "").strip()
        if member_name and member_name == canonical_name:
            return True
        for catalog_topic_id in member.get("catalogTopicIds") or []:
            if str(catalog_topic_id).strip() == topic_id:
                return True
    return False


def _alias_listed_in_root(root_entity: dict[str, Any], *, alias_name: str) -> bool:
    aliases = [str(item).strip() for item in root_entity.get("aliases") or [] if str(item).strip()]
    return bool(alias_name and alias_name in aliases)


def _validate_entity_admission(entity_rows: list[dict[str, Any]], errors: list[str], entity_catalog_path: Path) -> None:
    for row in entity_rows:
        extensions = row.get("extensions") or {}
        if not isinstance(extensions, dict):
            continue
        admission_track = str(extensions.get("admissionTrack") or "").strip()
        evidence_urls = [str(item).strip() for item in extensions.get("evidenceArticleUrls") or [] if str(item).strip()]
        conflict_status = str(extensions.get("conflictCheckStatus") or "").strip()
        authority_refs = [str(item).strip() for item in extensions.get("authorityRefs") or [] if str(item).strip()]
        wiki_title = str(extensions.get("wikiTitle") or "").strip()
        baike_item = str(extensions.get("baikeItem") or "").strip()
        if admission_track == "post_evidence":
            if len(evidence_urls) < 2:
                errors.append(
                    f"{entity_catalog_path}: entityId={row.get('entityId')} post_evidence 需要至少 2 条 evidenceArticleUrls"
                )
            if conflict_status != "pass":
                errors.append(
                    f"{entity_catalog_path}: entityId={row.get('entityId')} post_evidence 需要 conflictCheckStatus=pass"
                )
        if admission_track in {"authority", "authority_plus_post"}:
            if not authority_refs and not wiki_title and not baike_item:
                errors.append(
                    f"{entity_catalog_path}: entityId={row.get('entityId')} authority 轨缺少 authorityRefs 或等价权威字段"
                )


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 geo catalog / entity / tag 一致性")
    parser.add_argument("--catalog", default="", help="catalog NDJSON；省略则扫描 runtime/seed/*_catalog.ndjson")
    parser.add_argument("--entity-catalog", default="", help="entity catalog；省略则用 runtime/seed/entity_catalog/entities.ndjson")
    parser.add_argument("--tag-catalog", default="", help="tag catalog；省略则用 runtime/seed/tag_catalog/tags.ndjson")
    parser.add_argument(
        "--semantic-candidates",
        default="",
        help="语义归并候选 NDJSON；省略则用 runtime/seed/entity_catalog/semantic_cluster_candidates.ndjson",
    )
    args = parser.parse_args()

    catalog_paths = [Path(args.catalog).resolve()] if str(args.catalog or "").strip() else sorted(SEED_ROOT.glob("*_catalog.ndjson"))
    if not catalog_paths:
        print("OK: geo catalog/entity consistency (no catalog files, skipped)")
        return 0

    entity_catalog_path = Path(args.entity_catalog).resolve() if str(args.entity_catalog or "").strip() else _default_entity_catalog()
    tag_catalog_path = Path(args.tag_catalog).resolve() if str(args.tag_catalog or "").strip() else _default_tag_catalog()
    semantic_candidates_path = (
        Path(args.semantic_candidates).resolve()
        if str(args.semantic_candidates or "").strip()
        else _default_semantic_candidates()
    )
    if not entity_catalog_path.exists():
        print(f"FAIL: 缺少 entity catalog {entity_catalog_path}")
        return 1
    if not tag_catalog_path.exists():
        print(f"FAIL: 缺少 tag catalog {tag_catalog_path}")
        return 1
    if not semantic_candidates_path.exists():
        print(f"FAIL: 缺少 semantic candidates {semantic_candidates_path}")
        return 1

    entity_rows = read_ndjson(entity_catalog_path)
    entity_by_topic = {
        str(row.get("topicId") or "").strip(): row for row in entity_rows if str(row.get("topicId") or "").strip()
    }
    entities_by_name = _entity_lookup_by_name(entity_rows)
    semantic_rows = read_ndjson(semantic_candidates_path)
    semantic_by_topic = {
        str(row.get("topicId") or "").strip(): row
        for row in semantic_rows
        if str(row.get("topicId") or "").strip()
    }
    tag_ids = {str(row.get("tagId") or "").strip() for row in read_ndjson(tag_catalog_path) if str(row.get("tagId") or "").strip()}
    tag_refs = {str(row.get("tagRef") or "").strip() for row in read_ndjson(tag_catalog_path) if str(row.get("tagRef") or "").strip()}

    errors: list[str] = []
    for catalog_path in catalog_paths:
        for index, row in enumerate(read_ndjson(catalog_path), start=1):
            topic_id = str(row.get("topic_id") or "").strip()
            normalized_name = str(row.get("normalized_name") or row.get("name") or "").strip()
            semantic_row = semantic_by_topic.get(topic_id)
            if not semantic_row:
                errors.append(f"{catalog_path}:{index}: topic_id={topic_id} 缺少语义归并决策")
                continue
            decision = str(semantic_row.get("decision") or "").strip()
            direct_entity_row = entity_by_topic.get(topic_id)
            entity_row = _resolve_entity_for_catalog_row(
                topic_id=topic_id,
                normalized_name=normalized_name,
                entity_by_topic=entity_by_topic,
                entities_by_name=entities_by_name,
            )
            if decision in {"member"}:
                if direct_entity_row:
                    errors.append(f"{catalog_path}:{index}: member 决策的 topic_id={topic_id} 不应保留为顶层实体")
                root_topic_id = str(semantic_row.get("rootTopicId") or "").strip()
                root_canonical = str(semantic_row.get("rootCanonicalName") or "").strip()
                root_entity = _resolve_entity_for_catalog_row(
                    topic_id=root_topic_id,
                    normalized_name=root_canonical,
                    entity_by_topic=entity_by_topic,
                    entities_by_name=entities_by_name,
                )
                if not root_entity:
                    errors.append(f"{catalog_path}:{index}: member topic_id={topic_id} 缺少根实体映射")
                    continue
                if not _member_listed_in_root(root_entity, topic_id=topic_id, canonical_name=normalized_name):
                    errors.append(f"{catalog_path}:{index}: member topic_id={topic_id} 未写入根实体 extensions.members")
                continue
            if decision == "alias":
                if direct_entity_row:
                    errors.append(f"{catalog_path}:{index}: alias 决策的 topic_id={topic_id} 不应保留为顶层实体")
                root_topic_id = str(semantic_row.get("rootTopicId") or "").strip()
                root_canonical = str(semantic_row.get("rootCanonicalName") or "").strip()
                root_entity = _resolve_entity_for_catalog_row(
                    topic_id=root_topic_id,
                    normalized_name=root_canonical,
                    entity_by_topic=entity_by_topic,
                    entities_by_name=entities_by_name,
                )
                if not root_entity:
                    errors.append(f"{catalog_path}:{index}: alias topic_id={topic_id} 缺少根实体映射")
                    continue
                alias_name = str(semantic_row.get("rawName") or normalized_name).strip()
                if not _alias_listed_in_root(root_entity, alias_name=alias_name):
                    errors.append(f"{catalog_path}:{index}: alias topic_id={topic_id} 未写入根实体 aliases")
                continue
            if decision in {"pending_review", "reject"}:
                if direct_entity_row:
                    errors.append(f"{catalog_path}:{index}: {decision} 的 topic_id={topic_id} 不应保留为顶层实体")
                continue
            if decision not in {"standalone", "parallel_entity"}:
                errors.append(f"{catalog_path}:{index}: 未知 semantic decision={decision!r}")
                continue
            if not entity_row:
                errors.append(f"{catalog_path}:{index}: topic_id={topic_id} 未映射到 entity_catalog.topicId")
                continue
            name = normalized_name
            canonical = str(entity_row.get("canonicalName") or "").strip()
            if name and canonical and name != canonical:
                errors.append(f"{catalog_path}:{index}: catalog name={name} 与 entity canonical={canonical} 不一致")

            ext = entity_row.get("extensions") or {}
            if str(ext.get("labelZh") or "").strip() != str(row.get("label_zh") or "").strip():
                errors.append(f"{catalog_path}:{index}: label_zh 与 entity.extensions.labelZh 不一致")
            if str(ext.get("wikiTitle") or "").strip() != str(row.get("wiki_title") or "").strip():
                errors.append(f"{catalog_path}:{index}: wiki_title 与 entity.extensions.wikiTitle 不一致")
            if str(ext.get("baikeItem") or "").strip() != str(row.get("baike_item") or "").strip():
                errors.append(f"{catalog_path}:{index}: baike_item 与 entity.extensions.baikeItem 不一致")

            for tag_ref in row.get("tagRefs") or []:
                tag_ref = str(tag_ref).strip()
                if not tag_ref:
                    continue
                if tag_ref not in tag_refs and tag_ref not in tag_ids:
                    errors.append(f"{catalog_path}:{index}: tagRefs 无法解析 {tag_ref}")
            for tag_ref in entity_row.get("tagRefs") or []:
                tag_ref = str(tag_ref).strip()
                if not tag_ref:
                    continue
                if tag_ref not in tag_refs and tag_ref not in tag_ids:
                    errors.append(f"{entity_catalog_path}: entity topicId={topic_id} 的 tagRefs 无法解析 {tag_ref}")

    _validate_entity_admission(entity_rows, errors, entity_catalog_path)

    if errors:
        print("FAIL: geo catalog/entity consistency gate")
        for error in errors[:120]:
            print(f"- {error}")
        if len(errors) > 120:
            print(f"... and {len(errors) - 120} more")
        return 1

    print("OK: geo catalog/entity consistency gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
