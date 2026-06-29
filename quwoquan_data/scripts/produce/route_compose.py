"""Writing-pack preparation and compose payload helpers for route production."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from _common.content_evidence import gate_route_evidence_bundle, public_byline_label
from _common.content_object import require_title_hint
from _common.creative_brief import creative_brief_contract_issues
from _common.draft_io import (
    GENERATOR_AGENT,
    read_draft_meta,
    write_image_evidence_draft,
    write_placeholder_draft,
    write_prompt,
    write_writing_pack,
)
from _common.content_tags import resolved_content_tag_refs
from _common.entity_annotation import merge_entity_refs
from _common.stage_reports import write_gate_report, write_repair_report, write_stage_result
from _common.writing_pack import build_writing_pack, render_prompt_md
from produce.route_assets import _build_route_assets
from produce.route_core import (
    IMAGE_EVIDENCE_GENERATOR,
    _article_without_assets_allowed,
    _build_summary,
    _compact_public_text,
    _image_caption_from_brief,
    _publish_angle,
    _route_section_intents,
    _unique_strings,
    resolve_carrier,
)

def build_route_writing_pack(
    task_id: str,
    batch_id: str,
    ref: str,
    brief: Mapping[str, Any],
    quality_payload: Mapping[str, Any],
) -> dict[str, Any]:
    if str(quality_payload.get("recommendation") or "") == "skip":
        raise ValueError(f"{ref}: evidence too weak (recommendation=skip), writing_pack must not be prepared")
    from _common.content_object import content_type_from_brief, register_from_brief

    register_from_brief(task_id, batch_id, ref, brief, content_type=content_type_from_brief(brief))
    evidence_bundle = quality_payload.get("evidenceBundle") or {}
    assets = _build_route_assets(task_id, batch_id, ref, brief, evidence_bundle)
    carrier = resolve_carrier(brief, evidence_bundle, assets)
    publish_layout = "image" if carrier in ("image", "gallery") else "travel"
    byline = public_byline_label(str(brief.get("templateId") or ""), brief.get("creator") or {})
    pack = build_writing_pack(
        ref=ref,
        kind="route",
        brief=brief,
        evidence_bundle=evidence_bundle,
        assets=assets,
        carrier=carrier,
        byline=byline,
        publish_layout=publish_layout,
        section_intents=_route_section_intents(brief, evidence_bundle),
        source_urls=quality_payload.get("sourceUrls") or [],
        source_paths=quality_payload.get("sourcePaths") or [],
    )
    _attach_base_draft_text(task_id, batch_id, pack)
    write_writing_pack(task_id, batch_id, ref, pack)
    write_prompt(task_id, batch_id, ref, render_prompt_md(pack))
    if carrier in ("image", "gallery"):
        # 图片作品是结构化图集，不需要 agent 长文正文：写 image_evidence_pack 草稿元数据
        # 并清除任何残留 article 正文（write_image_evidence_draft 幂等删除旧正文）。
        write_image_evidence_draft(
            task_id,
            batch_id,
            ref,
            selected_asset_ids=[
                str(a.get("assetId")) for a in assets if isinstance(a, Mapping) and a.get("assetId")
            ],
            cited_source_paths=quality_payload.get("sourcePaths") or [],
        )
    else:
        # 仅当尚无 agent 草稿时写占位，避免覆盖会话模型已创作的正文。
        existing = read_draft_meta(task_id, batch_id, ref)
        if not existing or str(existing.get("generator")) != GENERATOR_AGENT:
            write_placeholder_draft(task_id, batch_id, ref)

    issues = _writing_pack_readiness_issues(brief, evidence_bundle, assets)
    issues.extend(creative_brief_contract_issues(pack))
    write_stage_result(task_id, batch_id, "produce", "compose_brief", ref, pack)
    write_gate_report(
        task_id=task_id,
        batch_id=batch_id,
        command="produce",
        step="compose_brief",
        ref=ref,
        passed=not issues,
        issues=issues,
        evidence_summary={"assetCount": len(assets), "carrier": carrier, "routeNodeCount": len(evidence_bundle.get("routeNodes") or [])},
        next_step="agent_compose",
        fallback_stage="download" if issues else None,
    )
    if issues:
        write_repair_report(
            task_id=task_id,
            batch_id=batch_id,
            command="produce",
            ref=ref,
            failed_stage="compose_brief",
            failed_gate="writingPackReadiness",
            issues=issues,
            fallback_stage="download",
            rerun_chain=["download", "quality_analysis", "compose-brief", "review", "materialize"],
        )
    return pack


def _writing_pack_readiness_issues(
    brief: Mapping[str, Any],
    evidence_bundle: Mapping[str, Any],
    assets: Sequence[Mapping[str, Any]],
) -> list[str]:
    issues = list(gate_route_evidence_bundle(brief, evidence_bundle))
    if not assets and not _article_without_assets_allowed(brief):
        issues.append("writing pack has no verifiable image assets")
    return issues


# ---------------------------------------------------------------------------
# review：读 agent 草稿 + 三道门 + 既有质量门
# ---------------------------------------------------------------------------


def _compose_payload_from_pack(
    ref: str,
    brief: Mapping[str, Any],
    quality_payload: Mapping[str, Any],
    pack: Mapping[str, Any],
    article: str,
    draft_meta: Mapping[str, Any] | None,
) -> dict[str, Any]:
    from _common.creator_assignment import creator_from_payload

    evidence_bundle = quality_payload.get("evidenceBundle") or {}
    story_spine = (evidence_bundle.get("storySpine") or {}) if isinstance(evidence_bundle, Mapping) else {}
    carrier = str(pack.get("carrier") or "article")
    template = (brief.get("render") or {}).get("articleTemplate") or "journal"
    meta = draft_meta or {}
    is_image = carrier in ("image", "gallery")
    title_hint = require_title_hint(brief, ref=ref)
    assets = list(pack.get("assets") or [])
    image_source_paths = _image_source_paths_from_assets(assets) if is_image else []
    image_source_urls = _image_source_urls_from_assets(assets) if is_image else []
    if is_image:
        story_spine = _image_story_spine(brief, pack, assets)
    creator_assignment = creator_from_payload(pack) or creator_from_payload(brief)
    payload = {
        "topicId": ref,
        "title": title_hint,
        "summary": _build_summary(article),
        "articleMarkdown": article,
        "carrier": carrier,
        "entityRefs": merge_entity_refs(brief, draft_meta),
        "tagRefs": resolved_content_tag_refs(brief, carrier),
        "sourceUrls": image_source_urls if is_image else list(quality_payload.get("sourceUrls") or []),
        "sourcePaths": image_source_paths if is_image else list(quality_payload.get("sourcePaths") or []),
        "template": template,
        "assets": assets,
        "publishMediaMode": pack.get("publishMediaMode") or brief.get("publishMediaMode"),
        "publishLayout": "image" if carrier in ("image", "gallery") else "travel",
        "publishAngle": _publish_angle(brief),
        "publishTitle": (
            _compact_public_text(title_hint, 80)
            if carrier in ("image", "gallery")
            else title_hint
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
    if carrier in ("image", "gallery"):
        caption = _image_caption_from_brief(brief, pack, article)
        payload["title"] = _compact_public_text(title_hint, 80)
        payload["summary"] = caption
        payload["articleMarkdown"] = ""
        payload["caption"] = caption
    return payload


def _source_ref_from_asset_path(value: Any) -> str:
    raw = str(value or "").replace("\\", "/").strip()
    if not raw:
        return ""
    if "/assets/" in raw:
        return raw.split("/assets/", 1)[0].rstrip("/") + "/source.md"
    if raw.endswith("/source.md") or raw.endswith("/source.clean.md"):
        return raw.rsplit("/", 1)[0].rstrip("/") + "/source.md"
    return ""


def _image_source_paths_from_assets(assets: list[Mapping[str, Any]]) -> list[str]:
    return _unique_strings(
        [
            _source_ref_from_asset_path(asset.get("sourceRef") or asset.get("sourceAssetRef") or asset.get("sourcePath"))
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
    entity_refs = [str(ref) for ref in (brief.get("entityRefs") or []) if str(ref).strip()]
    primary = entity_refs[0].rstrip("/").rsplit("/", 1)[-1] if entity_refs else ""
    captions = _unique_strings([str(asset.get("caption") or "") for asset in assets])
    collection_id = str(
        pack.get("sourceCollectionId")
        or next((asset.get("sourceCollectionId") for asset in assets if asset.get("sourceCollectionId")), "")
        or ""
    )
    return {
        "primaryEntity": primary,
        "routeEntities": [primary] if primary else [],
        "beats": captions[:3],
        "sourceCollectionId": collection_id,
        "mustIncludeFacts": [str(item) for item in (brief.get("mustIncludeFacts") or [])[:3]],
    }


def _attach_base_draft_text(task_id: str, batch_id: str, pack: dict[str, Any]) -> None:
    """把底稿正文内联进 writing pack，供 prompt 渲染「在此基础上适度加工」。

    底稿中心 1:1：内联整篇单一底稿正文，prompt 与 review 门（baseDraftFidelity）消费同一份
    整篇底稿；成品只来自这一篇底稿，不再按 writingIntent 收窄分母（避免误杀，也防逐字照搬）。
    """
    from _common.base_draft import base_source_use_mode, load_base_draft_text

    base_ref = str(pack.get("baseSourceRef") or "")
    if not base_ref:
        return
    pack["sourceUseMode"] = base_source_use_mode(task_id, batch_id, base_ref)
    text = load_base_draft_text(task_id, batch_id, base_ref).strip()
    if text:
        pack["baseDraftText"] = text[:4000]

__all__ = [name for name in globals() if not name.startswith("__")]
