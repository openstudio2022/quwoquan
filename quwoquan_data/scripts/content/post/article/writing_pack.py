"""Writing pack：CLI prepare 产出的"写作契约"，供创作 agent 创作正文。

writing_pack 把证据、选好的图、必须覆盖的事实、约束、章节意图等结构化下发；
`prompt.md` 是其人类可读版本（创作 agent 据此创作）。CLI 不再拼接任何正文句子。

指令区（人设 / 能力 / 约束 / 输出格式）已外置到 `quwoquan_data/prompts/` 模板，
本模块只负责把动态数据块（底稿 / 证据点 / 素材 / 必覆盖事实等）构造好交给
`core.prompt_render.render(...)`，不再在脚本里硬编码 prompt 正文（review gate 细则收回 review）。
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from content.post.object_index import require_title_hint
from core.creative_brief import build_creative_brief
from governance.creators.assignment import creator_from_payload
from core.prompt_render import render
from core.quality_gates import WRITING_INTENTS
from core.style_catalog import opening_guidance


def primary_entity_name(obj: Mapping[str, Any]) -> str:
    """从 brief/writing_pack 提取本篇主实体名，作为底稿主线对齐的强信号。

    软信号：缺失不致命（writingIntent 桶匹配仍可独立工作）。优先级
    entityRefs 末段 -> evidencePoints[0].entityName -> title 分隔符前缀。
    route/entity 两条 article 审稿管线共用本入口，避免重复实现（R24）。
    """
    refs = obj.get("entityRefs") or []
    if isinstance(refs, Sequence) and not isinstance(refs, (str, bytes)):
        for ref in refs:
            name = str(ref or "").rstrip("/").rsplit("/", 1)[-1].strip()
            if name:
                return name
    for point in obj.get("evidencePoints") or []:
        if isinstance(point, Mapping):
            name = str(point.get("entityName") or "").strip()
            if name:
                return name
    title = str(obj.get("title") or "")
    for sep in ("·", "|", "-"):
        if sep in title:
            head = title.split(sep, 1)[0].strip()
            if head:
                return head
    return title.strip()


def _evidence_points(evidence_bundle: Mapping[str, Any]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for node in evidence_bundle.get("routeNodes") or []:
        name = str(node.get("entityName") or "")
        if not name:
            continue
        emotion = node.get("emotionEvidence") or {}
        points.append(
            {
                "entityName": name,
                "sequence": node.get("sequence"),
                "topExcerpt": node.get("topExcerpt") or "",
                "mainline": [str(x) for x in (node.get("mainlineEvidence") or []) if x],
                "likes": [str(x) for x in (emotion.get("likes") or []) if x],
                "pains": [str(x) for x in (emotion.get("painPoints") or []) if x],
                "facts": [
                    {"category": str(e.get("category") or ""), "text": str(e.get("text") or e.get("sentence") or "")}
                    for e in (node.get("factEvidence") or [])
                ][:6],
            }
        )
    return points


def _compact_assets(
    assets: Sequence[Mapping[str, Any]],
    *,
    caption_max_chars: int | None = None,
) -> list[dict[str, Any]]:
    keep = (
        "assetId",
        "fileName",
        "caption",
        "kind",
        "role",
        "entityName",
        "sourcePath",
        "sourceRef",
        "sourceAssetRef",
        "researchLane",
        "imageLayout",
        "sourceCollectionId",
        "creator",
        "collectionPageUrl",
        "license",
        "termsUrl",
        "authorizationProof",
    )
    rows: list[dict[str, Any]] = []
    for asset in assets:
        row = {key: asset.get(key) for key in keep if asset.get(key)}
        if caption_max_chars is not None and isinstance(row.get("caption"), str):
            row["caption"] = row["caption"][:caption_max_chars].strip()
        if row.get("assetId"):
            rows.append(row)
    return rows


def _asset_figure_id(asset: Mapping[str, Any], index: int) -> str:
    role = str(asset.get("role") or "")
    if role == "cover":
        return "cover"
    if role == "closing":
        return "closing"
    return f"fig{index}"


def build_writing_pack(
    *,
    ref: str,
    kind: str,
    brief: Mapping[str, Any],
    evidence_bundle: Mapping[str, Any],
    assets: Sequence[Mapping[str, Any]],
    carrier: str,
    byline: str,
    publish_layout: str,
    section_intents: Sequence[str],
    source_urls: Sequence[str],
    source_paths: Sequence[str],
    execution_id: str = "",
) -> dict[str, Any]:
    is_image_carrier = str(carrier or "").lower() == "image"
    title = str(brief.get("titleHint") or "").strip() if is_image_carrier else require_title_hint(brief, ref=ref)
    source_caption = str(brief.get("caption") or "").strip()
    if is_image_carrier:
        source_caption = source_caption[:300]
    narrative = {
        "requireMotivation": bool((brief.get("openingTension") or {}).get("required", True)),
        "requireLike": bool((brief.get("explicitFeelings") or {}).get("requireLike", True)),
        "requireDislike": bool((brief.get("explicitFeelings") or {}).get("requireDislike", True)),
        "minDecisionPoints": int((brief.get("decisionPoints") or {}).get("minPoints", 2)),
        "forbidStandaloneTips": bool((brief.get("tipsEmbeddingPolicy") or {}).get("forbidStandaloneBlock", True)),
    }
    style_family = str(brief.get("styleFamily") or "")
    creative_brief = build_creative_brief(
        brief,
        title=title,
        carrier=carrier,
        byline=byline,
        writing_intent=brief.get("writingIntent"),
        style_family=style_family,
    )
    creator_assignment = creator_from_payload(brief)
    # 图片作品/画报是结构化图集 + 短配文，不携带长文叙事的章节意图与证据点。
    from content.execution.runtime_contract import stage_execution_context

    return {
        "schema": "quwoquan_data.writing_pack",
        "stage": "3.compose",
        **stage_execution_context(execution_id),
        "selectedSourceUrls": [str(x) for x in source_urls if x],
        "ref": ref,
        "kind": kind,
        "title": title,
        "caption": source_caption,
        "byline": byline,
        "carrier": carrier,
        "publishLayout": publish_layout,
        "publishMediaMode": brief.get("publishMediaMode"),
        "sourceCollectionId": brief.get("sourceCollectionId"),
        # 图片作品的标题/配文长度策略，与 handoff 图片草稿契约同源（短配文，非长文）。
        "captionPolicy": {"titleMaxChars": 80, "captionMaxChars": 300} if is_image_carrier else {},
        "templateId": brief.get("templateId"),
        "wordCount": brief.get("wordCount") or {"min": 700, "max": 1600},
        "forbiddenPhrases": [str(x) for x in (brief.get("forbiddenPhrases") or []) if x],
        "mustIncludeFacts": [str(x) for x in (brief.get("mustIncludeFacts") or []) if x],
        "sectionIntents": [] if is_image_carrier else list(section_intents),
        "narrativeContract": narrative,
        "styleFamily": style_family,
        "creativeBrief": creative_brief,
        **creator_assignment,
        "evidencePoints": [] if is_image_carrier else _evidence_points(evidence_bundle),
        "assets": _compact_assets(
            assets,
            caption_max_chars=300 if is_image_carrier else None,
        ),
        "sourceUrls": [str(x) for x in source_urls if x],
        "sourcePaths": [str(x) for x in source_paths if x],
        "writingIntent": brief.get("writingIntent"),
        "baseSourceRef": brief.get("baseSourceRef"),
        "baseSourceReusePolicy": brief.get("baseSourceReusePolicy"),
        "sourceUseMode": brief.get("sourceUseMode"),
        "bannedRegisterTerms": [str(x) for x in (brief.get("bannedRegisterTerms") or []) if x],
    }











































