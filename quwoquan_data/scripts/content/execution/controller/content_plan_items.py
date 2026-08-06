"""Materialize typed content-plan candidates into immutable plan items."""
from __future__ import annotations

from typing import Any

from core.entity_focus import VERDICT_STRONG

from content.execution.support import ExecutionContext
from content.post.article.source_unit_freeze import (
    write_article_source_unit_freeze,
)
from content.post.content_plan import ARTICLE_MIN_BASE_DRAFT_CHARS
from content.post.object_index import write_brief_object


def append_article_plan_items(
    *,
    ctx: ExecutionContext,
    scheduler: Any,
    entity_type: str,
    target: str,
    candidates: list[dict[str, Any]],
    items: list[dict[str, Any]],
) -> None:
    for candidate in candidates:
        intent = str(candidate.get("writingIntent") or "")
        title = str(candidate.get("draftTitle") or "").strip()
        source_id = str(candidate.get("sourceId") or "")
        ref = f"{target}__{source_id}".replace("/", "_")
        entity_ref = f"/entity/{entity_type}/{target}"
        entity_tags = list(candidate.get("entityTags") or [target])
        creator_assignment = scheduler.assign(
            carrier="article",
            target=target,
            intent=intent,
        )
        publish_schedule = scheduler.schedule(creator_assignment)
        asset_refs = list(candidate.get("assetRefs") or [])
        source_unit_freeze = (
            write_article_source_unit_freeze(
                execution_id=ctx.execution_id,
                source_dir=candidate["sourceDir"],
                asset_refs=asset_refs,
            )
            if asset_refs
            else None
        )
        brief = {
            "titleHint": title,
            "carrier": "article",
            "entityRefs": [entity_ref],
            "entityTags": entity_tags,
            "mustIncludeFacts": [],
            "templateId": "travel.entity.guide",
            "writingIntent": intent,
            "evidenceRequirements": {"emotion": {"required": False}},
            "baseSourceRef": candidate["sourceRef"],
            "assetRefs": asset_refs,
            "publishSchedule": publish_schedule,
            **creator_assignment,
        }
        if source_unit_freeze is not None:
            brief["articleSourceUnitFreeze"] = source_unit_freeze
        else:
            brief["publishMediaMode"] = "text_only"
        write_brief_object(ctx.execution_id, ref, brief, content_type="article")
        item = {
            "ref": ref,
            "kind": "entity",
            "carrier": "article",
            "researchLane": "article",
            "title": title,
            "entityRefs": [entity_ref],
            "entityTags": entity_tags,
            "evidenceRefs": [candidate["sourceRef"]],
            "rationale": (
                "底稿中心配额选源：单一 sourceRole=base 来源单元"
                f"（正文≥{ARTICLE_MIN_BASE_DRAFT_CHARS}），标题取自底稿，实体作多标签"
            ),
            "mustIncludeFacts": brief["mustIncludeFacts"],
            "writingIntent": intent,
            "evidenceRequirements": brief["evidenceRequirements"],
            "baseSourceRef": candidate["sourceRef"],
            "assetRefs": asset_refs,
            "sourceUseMode": candidate["sourceUseMode"],
            "entityFocusScore": float(candidate.get("entityFocusScore") or 0.0),
            "entityFocusVerdict": str(
                candidate.get("entityFocusVerdict") or VERDICT_STRONG
            ),
            "publishSchedule": publish_schedule,
            **creator_assignment,
        }
        if source_unit_freeze is not None:
            item["articleSourceUnitFreeze"] = source_unit_freeze
        else:
            item["publishMediaMode"] = "text_only"
        items.append(item)


def append_image_plan_items(
    *,
    ctx: ExecutionContext,
    scheduler: Any,
    entity_type: str,
    target: str,
    candidates: list[dict[str, Any]],
    items: list[dict[str, Any]],
) -> None:
    single_image = len(candidates) == 1
    for index, candidate in enumerate(candidates, start=1):
        ref = f"{target}_image" if single_image else f"{target}_image_{index}"
        title = str(candidate.get("title") or "").strip()[:80]
        caption = str(candidate.get("caption") or "").strip()[:300]
        entity_ref = f"/entity/{entity_type}/{target}"
        creator_assignment = scheduler.assign(
            carrier="image",
            target=target,
            intent="image",
        )
        publish_schedule = scheduler.schedule(creator_assignment)
        brief = {
            "titleHint": title,
            "carrier": "image",
            "entityRefs": [entity_ref],
            "entityTags": [target],
            "mustIncludeFacts": [
                f"{target} 开放许可图片作品",
                "图片来自同一授权来源集合（单一 source unit），禁止跨作者/页面/底稿混图",
            ],
            "templateId": "travel.entity.gallery",
            "sourceCollectionId": candidate["collectionId"],
            "baseSourceRef": candidate["sourceRef"],
            "assetRefs": [candidate["assetRef"]],
            "caption": caption,
            "publishSchedule": publish_schedule,
            **creator_assignment,
        }
        write_brief_object(ctx.execution_id, ref, brief, content_type="image")
        items.append(
            {
                "ref": ref,
                "kind": "entity",
                "carrier": "image",
                "researchLane": "image",
                "title": title,
                "caption": caption,
                "entityRefs": [entity_ref],
                "entityTags": [target],
                "evidenceRefs": [candidate["sourceRef"]],
                "rationale": (
                    "底稿中心配额选源：image research lane 下单一 "
                    "sourceCollectionId 的授权图片集合（一源一作品）"
                ),
                "sourceCollectionId": candidate["collectionId"],
                "baseSourceRef": candidate["sourceRef"],
                "assetRefs": [candidate["assetRef"]],
                "publishSchedule": publish_schedule,
                **creator_assignment,
            }
        )
