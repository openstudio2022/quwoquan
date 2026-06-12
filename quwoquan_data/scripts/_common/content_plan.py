"""证据驱动篇目规划包（content_plan_packet）校验。

真相源：batches/{batch}/_shared/content_plan_packet.json
见 content_pipeline_spec.md §1.2.1
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from _common.content_object import BRIEF_FILE, content_object_stage_dir, load_index
from _common.io import read_json
from _common.paths import (
    STAGE_COMPOSE,
    batch_content_plan_packet_path,
    batch_results_dir,
    batch_root,
)
from _common.quality_gates import writing_intent_issues

CONTENT_PLAN_SCHEMA = "quwoquan_data.content_plan_packet/1"


def reject_source_ids(task_id: str, batch_id: str) -> set[str]:
    """收集 source_screen_gate 判定 reject 的 sourceId，用于证据准入硬阻断。"""
    rejected: set[str] = set()
    results_dir = batch_results_dir(task_id, batch_id, "download", "source_screen")
    if not results_dir.is_dir():
        return rejected
    for path in results_dir.glob("*.json"):
        try:
            data = read_json(path)
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and str(data.get("decision") or "").lower() == "reject":
            sid = str(data.get("sourceId") or path.stem).strip()
            if sid:
                rejected.add(sid)
    return rejected


def load_content_plan_packet(task_id: str, batch_id: str) -> dict[str, Any] | None:
    path = batch_content_plan_packet_path(task_id, batch_id)
    if not path.is_file():
        return None
    data = read_json(path)
    return data if isinstance(data, dict) else None


def _items(packet: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = packet.get("items") or []
    return [i for i in raw if isinstance(i, dict)]


def validate_content_plan(task_id: str, batch_id: str, spec: Mapping[str, Any]) -> list[str]:
    """校验 content_plan 是否满足配额与证据链。"""
    issues: list[str] = []
    packet = load_content_plan_packet(task_id, batch_id)
    if packet is None:
        return ["content_plan_packet.json missing under batch _shared/"]

    items = _items(packet)
    if not items:
        return ["content_plan_packet.items is empty"]

    content = spec.get("content") if isinstance(spec.get("content"), Mapping) else {}
    quotas = content.get("quotas") if isinstance(content.get("quotas"), Mapping) else {}
    want_entity = int(quotas.get("entityArticles") or 0)
    want_route = int(quotas.get("routeArticles") or 0)
    want_gallery = int(quotas.get("galleryPosts") or 0)

    def _item_carrier(item: Mapping[str, Any]) -> str:
        return str(item.get("carrier") or item.get("contentType") or "article")

    if want_entity or want_route or want_gallery:
        entity_article_n = sum(
            1 for i in items
            if str(i.get("kind") or "") == "entity" and _item_carrier(i) != "gallery"
        )
        gallery_n = sum(1 for i in items if _item_carrier(i) == "gallery")
        route_n = sum(1 for i in items if str(i.get("kind") or "") == "route")
        if want_entity and entity_article_n != want_entity:
            issues.append(f"entityArticles quota {want_entity} but packet has {entity_article_n}")
        if want_gallery and gallery_n != want_gallery:
            issues.append(f"galleryPosts quota {want_gallery} but packet has {gallery_n}")
        if want_route and route_n != want_route:
            issues.append(f"routeArticles quota {want_route} but packet has {route_n}")

    root = batch_root(task_id, batch_id)
    index = load_index(task_id, batch_id)
    rejected_sources = reject_source_ids(task_id, batch_id)
    seen_refs: set[str] = set()

    for idx, item in enumerate(items, start=1):
        ref = str(item.get("ref") or "").strip()
        kind = str(item.get("kind") or "").strip()
        title = str(item.get("title") or "").strip()
        if not ref:
            issues.append(f"item[{idx}]: missing ref")
            continue
        if ref in seen_refs:
            issues.append(f"item[{idx}]: duplicate ref {ref!r}")
        seen_refs.add(ref)
        if kind not in ("entity", "route"):
            issues.append(f"item[{ref}]: kind must be entity|route, got {kind!r}")
        if not title:
            issues.append(f"item[{ref}]: missing title")
        entity_refs = item.get("entityRefs") or []
        if not isinstance(entity_refs, list) or not entity_refs:
            issues.append(f"item[{ref}]: entityRefs required")
        elif kind == "route" and len(entity_refs) < 3:
            issues.append(f"item[{ref}]: route needs entityRefs>=3")
        evidence = item.get("evidenceRefs") or []
        if not isinstance(evidence, list) or not evidence:
            issues.append(f"item[{ref}]: evidenceRefs required")
        else:
            for ev in evidence:
                ev_path = root / str(ev)
                if not ev_path.is_file():
                    issues.append(f"item[{ref}]: evidence not found: {ev}")
        # 证据准入硬门：content_plan 不得引用 source_screen_gate=reject 的来源。
        cited = [str(e) for e in (evidence if isinstance(evidence, list) else [])]
        if item.get("baseSourceRef"):
            cited.append(str(item.get("baseSourceRef")))
        for sid in sorted(rejected_sources):
            for c in cited:
                if sid and sid in c:
                    issues.append(
                        f"item[{ref}]: cites rejected source {sid!r} "
                        f"(source_screen_gate=reject 必须 fallback download_fetch，不得进入 content_plan)"
                    )
                    break
        if not str(item.get("rationale") or "").strip():
            issues.append(f"item[{ref}]: missing rationale")
        for msg in writing_intent_issues(item.get("writingIntent")):
            issues.append(f"item[{ref}]: {msg}")
        if ref not in index:
            issues.append(f"item[{ref}]: not registered in content_object_index")
        else:
            brief_path = content_object_stage_dir(task_id, batch_id, ref, STAGE_COMPOSE) / BRIEF_FILE
            if not brief_path.is_file():
                issues.append(f"item[{ref}]: missing 3.compose/brief.json")

    return issues


def content_plan_quotas_required(spec: Mapping[str, Any]) -> bool:
    content = spec.get("content") if isinstance(spec.get("content"), Mapping) else {}
    quotas = content.get("quotas") if isinstance(content.get("quotas"), Mapping) else {}
    return bool(
        int(quotas.get("entityArticles") or 0)
        or int(quotas.get("routeArticles") or 0)
        or int(quotas.get("galleryPosts") or 0)
    )


def load_writing_intent_overrides(task_id: str, batch_id: str) -> dict[str, dict[str, Any]]:
    """从 content_plan_packet 读取每篇 writingIntent / baseSourceRef，供 compose 注入 brief。

    返回 {ref: {"writingIntent": ..., "baseSourceRef": ...}}（仅含已声明的字段）。
    这是 content_plan(任务层) → brief(写作契约) 的单一贯通点，保证即使 Agent 没把
    writingIntent 写进 brief.json，writing_pack/prompt 仍有正确主线。
    """
    packet = load_content_plan_packet(task_id, batch_id) or {}
    overrides: dict[str, dict[str, Any]] = {}
    for item in _items(packet):
        ref = str(item.get("ref") or "").strip()
        if not ref:
            continue
        row: dict[str, Any] = {}
        if item.get("writingIntent"):
            row["writingIntent"] = item.get("writingIntent")
        if item.get("baseSourceRef"):
            row["baseSourceRef"] = item.get("baseSourceRef")
        if row:
            overrides[ref] = row
    return overrides
