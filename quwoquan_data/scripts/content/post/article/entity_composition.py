"""通用实体类（非线路）evidence / writing-pack / review workflow（Agent 创作版）。

覆盖博物馆/景区/餐厅/古镇等单实体内容（体验/攻略/探店/科普/叙事 等角度）。
复用线路内容的资产挑选、载体路由、图片门、来源痕迹清洗与 review 检查；
仅在「章节意图」上改为单实体框架（初见/最打动/不足/去之前/适合谁），正文一律由创作 agent创作。
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from core.content_tags import resolved_content_tag_refs
from core.creative_brief import (
    creative_brief_contract_issues,
)
from core.data_issue import (
    DataIssueCode,
    DataIssueStage,
    DataRecoveryAction,
    data_issues,
)

from content.execution.stage_reports import (
    write_gate_report,
    write_repair_report,
    write_stage_result,
)
from content.post.article.article_media_contract import article_media_contract_issues
from content.post.article.draft_io import (
    GENERATOR_AGENT,
    read_draft_meta,
    write_image_evidence_draft,
    write_placeholder_draft,
    write_prompt,
    write_writing_pack,
)
from content.post.article.evidence_bundle import (
    gate_route_evidence_bundle,
    public_byline_label,
)
from content.post.article.prompt_renderer import render_prompt_md
from content.post.article.route_assets import _build_route_assets
from content.post.article.route_compose import _attach_base_draft_text
from content.post.article.route_core import (
    IMAGE_EVIDENCE_GENERATOR,
    _article_without_assets_allowed,
    _build_summary,
    _compact_public_text,
    _image_caption_from_brief,
    _publish_angle,
    _unique_strings,
    is_route_brief,
    load_compose_brief,
    resolve_carrier,
)
from content.post.article.writing_pack import build_writing_pack
from content.post.object_index import require_title_hint
from content.review.annotation.entity_annotation import merge_entity_refs


def is_entity_brief(brief: Mapping[str, Any]) -> bool:
    """非线路、且有 entityRefs 的内容（单实体或实体合集），归入实体 composer。"""
    if is_route_brief(brief):
        return False
    return bool(brief.get("entityRefs"))


def iter_entity_briefs(execution_id: str, refs: Sequence[str] | None = None) -> list[tuple[str, dict[str, Any]]]:
    from content.post.object_index import iter_content_refs

    wanted = {ref for ref in (refs or []) if ref}
    rows: list[tuple[str, dict[str, Any]]] = []
    for ref in iter_content_refs(execution_id):
        if wanted and ref not in wanted:
            continue
        brief = load_compose_brief(execution_id, ref)
        if brief and is_entity_brief(brief):
            rows.append((ref, brief))
    return rows


def _entity_name(evidence_bundle: Mapping[str, Any], brief: Mapping[str, Any]) -> str:
    nodes = [n for n in (evidence_bundle.get("routeNodes") or []) if n.get("entityName")]
    if nodes:
        return str(nodes[0]["entityName"])
    refs = [str(x) for x in (brief.get("entityRefs") or []) if x]
    return refs[0].split("/")[-1] if refs else ""


# 实体类别名词：用于 prompt 指代，避免线路话术（这条线/长线/转场/节点）。
_KIND_WORDS = {
    "博物馆": "这座博物馆",
    "古城": "这处古城",
    "古镇": "这座古镇",
    "景区": "这处景区",
    "公园": "这片园子",
    "寺": "这座寺院",
    "山": "这座山",
    "湖": "这片湖",
    "餐厅": "这家店",
    "店": "这家店",
}


def _kind_word(brief: Mapping[str, Any]) -> str:
    etype = str((brief.get("subject") or {}).get("type") or "")
    tail = etype.split("/")[-1] if etype else ""
    for key, word in _KIND_WORDS.items():
        if key in tail or key in etype:
            return word
    return "这个地方"


# ---------------------------------------------------------------------------
# prepare（compose-brief）
# ---------------------------------------------------------------------------


def _entity_section_intents(brief: Mapping[str, Any], name: str) -> list[str]:
    """章节意图：跟随底稿自身结构，仅给最小建议（不再下发固定 6 段骨架）。"""
    return [
        f"结构跟随底稿：保留底稿自身的小标题与叙述顺序（多目的地路书保留全部站点，不要裁成只讲 {name}），只做轻量编辑。",
        "轻改重点：去语病/纠错别字/理顺语句/补全可回溯证据/去平台与版权痕迹；不要从零另写，也不要套用固定模板小标题（如「它到底适合谁」）。",
    ]


def build_entity_writing_pack(
    execution_id: str,
    ref: str,
    brief: Mapping[str, Any],
    quality_payload: Mapping[str, Any],
) -> dict[str, Any]:
    if str(quality_payload.get("recommendation") or "") == "skip":
        raise ValueError(f"{ref}: evidence too weak (recommendation=skip), writing_pack must not be prepared")
    from content.post.object_index import content_type_from_brief, register_from_brief

    register_from_brief(execution_id, ref, brief, content_type=content_type_from_brief(brief))
    evidence_bundle = quality_payload.get("evidenceBundle") or {}
    name = _entity_name(evidence_bundle, brief)
    assets = _build_route_assets(execution_id, ref, brief, evidence_bundle)
    carrier = resolve_carrier(brief, evidence_bundle, assets)
    publish_layout = "image" if carrier == "image" else "entity"
    byline = public_byline_label(str(brief.get("templateId") or ""), brief.get("creator") or {})
    pack = build_writing_pack(
        ref=ref,
        kind="entity",
        brief=brief,
        evidence_bundle=evidence_bundle,
        assets=assets,
        carrier=carrier,
        byline=byline,
        publish_layout=publish_layout,
        section_intents=_entity_section_intents(brief, name),
        source_urls=quality_payload.get("sourceUrls") or [],
        source_paths=quality_payload.get("sourcePaths") or [],
        execution_id=execution_id,
    )
    _attach_base_draft_text(execution_id, pack)
    write_writing_pack(execution_id, ref, pack)
    write_prompt(
        execution_id,
        ref,
        render_prompt_md(pack),
        template_family="image_curation" if carrier == "image" else "article_author",
        variables={"writingPack": pack},
        output_refs=(
            [
                "4.draft/draft_meta.json",
                "4.draft/author_self_check.json",
                "4.draft/agent_result_envelope.json",
            ]
            if carrier == "image"
            else [
                "4.draft/draft.article.md",
                "4.draft/draft_meta.json",
                "4.draft/author_self_check.json",
                "4.draft/agent_result_envelope.json",
            ]
        ),
    )
    if carrier == "image":
        # 图片作品是结构化图集，不需要 agent 长文正文：写 image_evidence_pack 草稿元数据
        # 并清除任何残留 article 占位/正文（write_image_evidence_draft 幂等删除旧正文）。
        write_image_evidence_draft(
            execution_id,
            ref,
            selected_asset_ids=[
                str(a.get("assetId")) for a in assets if isinstance(a, Mapping) and a.get("assetId")
            ],
            cited_source_paths=quality_payload.get("sourcePaths") or [],
        )
    else:
        # 仅当尚无 agent 草稿时写占位，避免覆盖创作 agent已创作的正文。
        existing = read_draft_meta(execution_id, ref)
        if not existing or str(existing.get("generator")) != GENERATOR_AGENT:
            write_placeholder_draft(execution_id, ref)

    issues = list(gate_route_evidence_bundle(brief, evidence_bundle))
    issues.extend(creative_brief_contract_issues(pack))
    if not assets and not _article_without_assets_allowed(brief):
        issues.append("writing pack has no verifiable image assets")
    issues.extend(
        article_media_contract_issues(
            pack,
            str(pack.get("baseSourceRef") or brief.get("baseSourceRef") or ""),
        )
    )
    write_stage_result(execution_id, "post", "compose_brief", ref, pack)
    write_gate_report(
        execution_id=execution_id,
        command="post",
        step="compose_brief",
        ref=ref,
        passed=not issues,
        issues=data_issues(
            DataIssueCode.CONTRACT_INVALID,
            stage=DataIssueStage.COMPOSE_BRIEF,
            ref=ref,
            messages=issues,
            recovery=DataRecoveryAction.REWIND_DOWNLOAD,
        ),
        evidence_summary={"assetCount": len(assets), "carrier": carrier, "entity": name},
        next_step="agent_compose",
    )
    if issues:
        write_repair_report(
            execution_id=execution_id,
            command="post",
            ref=ref,
            failed_stage=DataIssueStage.COMPOSE_BRIEF,
            failed_gate="writingPackReadiness",
            issues=data_issues(
                DataIssueCode.CONTRACT_INVALID,
                stage=DataIssueStage.COMPOSE_BRIEF,
                ref=ref,
                messages=issues,
                recovery=DataRecoveryAction.REWIND_DOWNLOAD,
            ),
            fallback_stage="download",
            rerun_chain=["download", "quality_analysis", "compose-brief", "review", "materialize"],
        )
    return pack


# ---------------------------------------------------------------------------
# review：读 agent 草稿 + 三道门 + 既有质量门
# ---------------------------------------------------------------------------


def _source_ref_from_asset_path(value: Any) -> str:
    raw = str(value or "").replace("\\", "/").strip()
    if not raw:
        return ""
    if "/assets/" in raw:
        return raw.split("/assets/", 1)[0].rstrip("/") + "/source.md"
    if raw.endswith(("/source.md", "/source.clean.md")):
        return raw.rsplit("/", 1)[0].rstrip("/") + "/source.md"
    return ""


def _image_source_paths_from_assets(assets: list[Mapping[str, Any]]) -> list[str]:
    return _unique_strings(
        [
            _source_ref_from_asset_path(
                asset.get("sourceRef")
                or asset.get("sourceAssetRef")
                or asset.get("sourcePath")
            )
            for asset in assets
        ]
    )


def _image_source_urls_from_assets(assets: list[Mapping[str, Any]]) -> list[str]:
    return _unique_strings(
        [
            str(
                asset.get("collectionPageUrl")
                or asset.get("authorizationProof")
                or asset.get("sourceUrl")
                or asset.get("url")
                or ""
            )
            for asset in assets
        ]
    )


def _image_story_spine(
    brief: Mapping[str, Any],
    pack: Mapping[str, Any],
    assets: list[Mapping[str, Any]],
) -> dict[str, Any]:
    entity_refs = [
        str(ref) for ref in (brief.get("entityRefs") or []) if str(ref).strip()
    ]
    primary = entity_refs[0].rstrip("/").rsplit("/", 1)[-1] if entity_refs else ""
    captions = _unique_strings([str(asset.get("caption") or "") for asset in assets])
    collection_id = str(
        pack.get("sourceCollectionId")
        or next(
            (
                asset.get("sourceCollectionId")
                for asset in assets
                if asset.get("sourceCollectionId")
            ),
            "",
        )
        or ""
    )
    return {
        "primaryEntity": primary,
        "routeEntities": [primary] if primary else [],
        "beats": captions[:3],
        "sourceCollectionId": collection_id,
        "mustIncludeFacts": [
            str(item) for item in (brief.get("mustIncludeFacts") or [])[:3]
        ],
    }


def _compose_payload_from_pack(
    ref: str,
    brief: Mapping[str, Any],
    quality_payload: Mapping[str, Any],
    pack: Mapping[str, Any],
    article: str,
    draft_meta: Mapping[str, Any] | None,
) -> dict[str, Any]:
    from governance.creators.assignment import creator_from_payload

    evidence_bundle = quality_payload.get("evidenceBundle") or {}
    story_spine = (evidence_bundle.get("storySpine") or {}) if isinstance(evidence_bundle, Mapping) else {}
    carrier = str(pack.get("carrier") or "article")
    template = (brief.get("render") or {}).get("articleTemplate") or "journal"
    meta = draft_meta or {}
    is_image = carrier == "image"
    public_title_hint = str(brief.get("titleHint") or "").strip() if is_image else require_title_hint(brief, ref=ref)
    assets = list(pack.get("assets") or [])
    image_source_paths = _image_source_paths_from_assets(assets) if is_image else []
    image_source_urls = _image_source_urls_from_assets(assets) if is_image else []
    if is_image:
        story_spine = _image_story_spine(brief, pack, assets)
    creator_assignment = creator_from_payload(pack) or creator_from_payload(brief)
    payload = {
        "topicId": ref,
        "title": public_title_hint,
        "summary": _build_summary(article),
        "articleMarkdown": article,
        "carrier": carrier,
        "vertical": pack.get("vertical") or brief.get("vertical"),
        "entityRefs": merge_entity_refs(brief, draft_meta),
        "tagRefs": resolved_content_tag_refs(brief, carrier),
        "sourceUrls": image_source_urls if is_image else list(quality_payload.get("sourceUrls") or []),
        "sourcePaths": image_source_paths if is_image else list(quality_payload.get("sourcePaths") or []),
        "template": template,
        "assets": assets,
        "publishMediaMode": pack.get("publishMediaMode") or brief.get("publishMediaMode"),
        "baseSourceRef": pack.get("baseSourceRef") or brief.get("baseSourceRef"),
        "publishLayout": "image" if carrier == "image" else "entity",
        "publishAngle": _publish_angle(brief),
        "publishTitle": (
            _compact_public_text(meta.get("title") or public_title_hint, 80)
            if carrier == "image"
            else public_title_hint
        ),
        "publishSeq": 1,
        "composeBriefRef": ref,
        "storySpine": story_spine,
        "generator": IMAGE_EVIDENCE_GENERATOR if is_image else str(meta.get("generator") or "pending"),
        "generatorModel": None if is_image else meta.get("model"),
        "sourceUseMode": pack.get("sourceUseMode"),
        "citedSourceRefs": (
            image_source_paths
            if is_image
            else list(meta.get("citedSourcePaths") or [])
        ),
        "createdAt": meta.get("createdAt"),
        "updatedAt": meta.get("updatedAt"),
        "articleRenderProfile": {
            "template": template,
            "fontPreset": (brief.get("render") or {}).get("fontPreset", "clean"),
        },
        **creator_assignment,
    }
    if carrier == "image":
        caption = _image_caption_from_brief(brief, pack, meta, article)
        payload["title"] = _compact_public_text(meta.get("title") or public_title_hint, 80)
        payload["summary"] = caption
        payload["articleMarkdown"] = ""
        payload["caption"] = caption
    return payload
























