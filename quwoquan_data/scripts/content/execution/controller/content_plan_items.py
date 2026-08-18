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


def canonical_article_plan_title(*, target: str, draft_title: str) -> str:
    """Freeze an entity-specific title before authoring.

    Source pages often describe a wider city or province than the selected
    entity.  Reusing that wider page title as the immutable object coordinate
    makes an unrelated canonical article look like the same object.  Preserve
    a source title only when it names the exact target; otherwise freeze one
    deterministic target-scoped guide title.
    """
    normalized_target = str(target or "").strip()
    normalized_title = str(draft_title or "").strip()
    if not normalized_target:
        raise ValueError("article target is required for immutable object routing")
    if normalized_target in normalized_title:
        return normalized_title
    return f"{normalized_target}攻略"


def bind_article_plan_source_unit_freezes(ctx: ExecutionContext) -> list[str]:
    """Complete deterministic illustrated-article bindings after semantic planning."""
    from core.io import write_json
    from core.paths import execution_root
    from content.execution.workspace import execution_content_plan_packet_path
    from content.post import object_index as content_object
    from content.post.article.source_unit_freeze import (
        validate_article_source_unit_freeze,
    )
    from content.post.content_plan_state import load_content_plan_packet

    packet = load_content_plan_packet(ctx.execution_id)
    if not isinstance(packet, dict):
        return []
    root = execution_root(ctx.execution_id)
    items = packet.get("items")
    if not isinstance(items, list):
        return []
    changed = False
    issues: list[str] = []
    for raw in items:
        if not isinstance(raw, dict) or str(raw.get("carrier") or "") != "article":
            continue
        ref = str(raw.get("ref") or "").strip()
        asset_refs = [
            str(item).strip()
            for item in raw.get("assetRefs") or []
            if str(item).strip()
        ]
        media_mode = str(raw.get("publishMediaMode") or "").strip()
        binding = raw.get("articleSourceUnitFreeze")
        if media_mode == "text_only":
            if asset_refs or binding is not None:
                issues.append(f"{ref}: text-only article carries illustrated source binding")
            continue
        if not asset_refs:
            issues.append(f"{ref}: illustrated article has no source assets")
            continue
        try:
            if isinstance(binding, dict):
                resolved = validate_article_source_unit_freeze(
                    binding,
                    execution_id=ctx.execution_id,
                )
            else:
                source_ref = str(raw.get("baseSourceRef") or "").strip()
                source_path = (root / source_ref).resolve()
                sources_root = (root / "sources").resolve()
                if (
                    not source_ref
                    or source_path.name != "source.md"
                    or sources_root not in source_path.parents
                ):
                    raise ValueError(
                        "illustrated article baseSourceRef must identify one execution source unit"
                    )
                resolved = write_article_source_unit_freeze(
                    execution_id=ctx.execution_id,
                    source_dir=source_path.parent,
                    asset_refs=asset_refs,
                )
                raw["articleSourceUnitFreeze"] = resolved
                changed = True
            brief = content_object.read_brief_object(ctx.execution_id, ref) or {}
            if not brief:
                raise ValueError("content-plan brief is missing")
            if brief.get("articleSourceUnitFreeze") != resolved:
                brief["articleSourceUnitFreeze"] = resolved
                write_brief_object(
                    ctx.execution_id,
                    ref,
                    brief,
                    content_type="article",
                )
        except (OSError, TypeError, ValueError) as exc:
            issues.append(f"{ref}: article source-unit freeze invalid: {exc}")
    if changed:
        write_json(execution_content_plan_packet_path(ctx.execution_id), packet)
    return issues


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
        article_category = str(candidate.get("articleCategory") or "")
        topic_tag_refs = [
            str(ref)
            for ref in candidate.get("topicTagRefs") or []
            if str(ref).strip()
        ]
        title = canonical_article_plan_title(
            target=target,
            draft_title=str(candidate.get("draftTitle") or ""),
        )
        source_id = str(candidate.get("sourceId") or "")
        ref = f"{target}__{source_id}".replace("/", "_")
        entity_ref = f"/entity/{entity_type}/{target}"
        entity_tags = list(candidate.get("entityTags") or [target])
        creator_assignment = scheduler.assign(
            carrier="article",
            target=target,
            intent=intent,
            topic_tag_refs=topic_tag_refs,
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
                f"（正文≥{ARTICLE_MIN_BASE_DRAFT_CHARS}），对象标题精确绑定目标实体，实体作多标签"
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
        if article_category:
            brief["articleCategory"] = article_category
            brief["tagRefs"] = topic_tag_refs
            item["articleCategory"] = article_category
            item["tagRefs"] = topic_tag_refs
        write_brief_object(ctx.execution_id, ref, brief, content_type="article")
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
        work_unit_id = str(candidate.get("workUnitId") or "").strip()
        ref = (
            f"{target}_image_{work_unit_id.removeprefix('sha256:')[:12]}"
            if work_unit_id
            else f"{target}_image"
            if single_image
            else f"{target}_image_{index}"
        )
        raw_title = str(candidate.get("title") or "").strip()
        source_id = str(candidate.get("sourceId") or "").strip()
        title = "" if raw_title.casefold() == source_id.casefold() else raw_title[:80]
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
        if work_unit_id:
            brief["workUnitId"] = work_unit_id
        write_brief_object(ctx.execution_id, ref, brief, content_type="image")
        item = {
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
        if work_unit_id:
            item["workUnitId"] = work_unit_id
        items.append(item)
