"""通用来源计划读取（取代任务/区域专属 curated 语料）。

来源候选由任务/Agent 在 download source_plan 输入中给出，主线不内置任何区域语料。
对象优先布局：
  data/tasks/{executionId}/entities/{domain}/{type}/{name}/1.download/<lane>_source_plan.json
统一 payload 形态：
  homepage/article: {"sources": [{"source_id","platform","url","body?","imageUrls?"}]}
  image: {"collections": [{"sourceCollectionId", "creator", "images": [...]}]}
  video: {"videos": [{"assetUrl", "sourcePostUrl", ...}], "assets": [...]}
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable
import re

from core.io import read_json
from core.carrier_contract import research_plan_files
from core.control_types import ContentType
from core.paths import STAGE_DOWNLOAD
from content.source.source_unit import resolve_entity_object_dir

SOURCE_USE_LICENSED_ADAPTATION = "licensed_adaptation"
SOURCE_USE_FACTUAL_REFERENCE = "factual_reference_only"
SOURCE_USE_BLOCKED = "blocked"
VALID_SOURCE_USE_MODES = {
    SOURCE_USE_LICENSED_ADAPTATION,
    SOURCE_USE_FACTUAL_REFERENCE,
    SOURCE_USE_BLOCKED,
}
RESEARCH_PLAN_FILES = research_plan_files()


def content_type_for_lane(lane: str) -> str:
    """research lane → 发布内容类型路由真相源。

    每条来源按 carrier contract 路由：homepage=实体，其余 lane 与发布内容类型同名。
    未知/空 lane 直接失败，禁止把弱类型来源静默路由成 article。
    """
    normalized = str(lane or "").strip()
    try:
        content_type = ContentType(normalized)
    except ValueError:
        raise ValueError(f"unsupported or missing research lane: {normalized!r}")
    return "entity" if content_type is ContentType.HOMEPAGE else content_type.value


def _source_plan_files(
    execution_id: str,
    entity_id: str,
    entity_type: str = "",
    *,
    lanes: Iterable[str] | None = None,
) -> list[tuple[str, Path]]:
    """Return independent lane plans.

    A lane-specific caller is strict: it reads only the carrier contract file.
    Mixed ``source_plan.json`` is not consumable truth.
    """
    obj = resolve_entity_object_dir(execution_id, entity_id, etype_hint=entity_type)
    selected = list(lanes or ("homepage", "article"))
    found: list[tuple[str, Path]] = []
    for lane in selected:
        filename = RESEARCH_PLAN_FILES.get(lane)
        if not filename:
            continue
        path = obj / STAGE_DOWNLOAD / filename
        if path.is_file():
            found.append((lane, path))
    return found


def _extract_sources(data: Any) -> list[dict[str, Any]]:
    """读取 source_plan 的 sources（顶层或 envelope payload.sources）。"""
    if not isinstance(data, dict):
        return []
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    raw = (
        data.get("sources")
        or payload.get("sources")
        or []
    )
    return raw if isinstance(raw, list) else []


def _extract_collections(data: Any, key: str) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    raw = data.get(key) or payload.get(key) or []
    return [dict(row) for row in raw if isinstance(row, dict)] if isinstance(raw, list) else []


def _plan_has_payload(path: Path) -> bool:
    try:
        data = read_json(path)
    except (OSError, ValueError, TypeError):
        return False
    if _extract_sources(data):
        return True
    if not isinstance(data, dict):
        return False
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    for key in ("imageUrls", "collections", "videos", "assets"):
        raw = data.get(key) or payload.get(key) or []
        if isinstance(raw, list) and raw:
            return True
    return False


def curated_sourced_videos_for_entity(
    execution_id: str,
    entity_id: str,
    entity_type: str = "",
) -> list[dict[str, Any]]:
    """Read typed real-video candidates from the video lane plan."""
    files = _source_plan_files(
        execution_id,
        entity_id,
        entity_type,
        lanes=("video",),
    )
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _lane, path in files:
        for raw in _extract_collections(read_json(path), "videos"):
            asset_url = str(raw.get("assetUrl") or "").strip()
            if not asset_url or asset_url in seen:
                continue
            seen.add(asset_url)
            candidates.append(raw)
    return candidates


def curated_sources_for_entity(
    execution_id: str,
    entity_id: str,
    entity_type: str = "",
    *,
    research_lane: str | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    lanes = (research_lane,) if research_lane else None
    seen: set[tuple[str, str]] = set()
    for lane, plan_file in _source_plan_files(
        execution_id, entity_id, entity_type, lanes=lanes
    ):
        sources = _extract_sources(read_json(plan_file))
        for idx, src in enumerate(sources, start=1):
            if not isinstance(src, dict):
                continue
            url = src.get("url") or src.get("link")
            if not url:
                continue
            source_id = (
                src.get("source_id")
                or src.get("sourceId")
                or src.get("id")
                or f"{lane}_source_{idx}"
            )
            dedupe_key = (str(source_id), str(url))
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            out.append(
                {
                    "source_id": source_id,
                    "platform": src.get("platform") or "web",
                    "url": url,
                    "canonicalUrl": src.get("canonicalUrl") or "",
                    "finalUrl": src.get("finalUrl") or "",
                    "sourceKind": src.get("sourceKind") or "",
                    "sourceTitle": src.get("sourceTitle") or "",
                    "qualifiedAuthorityTitle": src.get("qualifiedAuthorityTitle") or "",
                    "extractor": src.get("extractor") or "",
                    "policyRevision": src.get("policyRevision") or "",
                    "body": src.get("body", ""),
                    "title": src.get("title") or "",
                    "sourceUseMode": src.get("sourceUseMode") or "",
                    "license": src.get("license") or "",
                    "credit": src.get("credit") or "",
                    "termsUrl": src.get("termsUrl") or "",
                    "licenseSnapshot": src.get("licenseSnapshot") or "",
                    "authorizationProof": src.get("authorizationProof") or "",
                    "category": src.get("category") or "",
                    "discoveryProvider": src.get("discoveryProvider") or "",
                    "matchConfidence": src.get("matchConfidence") or "",
                    "evidenceReason": src.get("evidenceReason") or "",
                    "sourceRole": src.get("sourceRole") or "",
                    "imageEvidenceMode": src.get("imageEvidenceMode") or "",
                    "entityMatch": src.get("entityMatch") or "",
                    "candidateGate": src.get("candidateGate") if isinstance(src.get("candidateGate"), dict) else {},
                    "researchLane": lane,
                    "fetchable": src.get("fetchable"),
                    "fetchableOverride": src.get("fetchableOverride"),
                    "imageUrls": _normalize_image_specs(src.get("imageUrls") or []),
                }
            )
    return out


def _normalize_image_specs(raw: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, str):
            spec = {"url": item, "license": "", "credit": ""}
        elif isinstance(item, dict):
            url = item.get("url") or item.get("link") or ""
            spec = {
                "url": url,
                "license": item.get("license", ""),
                "credit": item.get("credit") or item.get("author") or "",
                "sourceUrl": item.get("sourceUrl") or url,
                "termsUrl": item.get("termsUrl", ""),
                "licenseSnapshot": item.get("licenseSnapshot", ""),
                "usageScope": item.get("usageScope", ""),
                "platform": item.get("platform") or item.get("sourcePlatform") or "",
                "modelReleaseRequired": item.get("modelReleaseRequired", ""),
                "modelReleaseStatus": item.get("modelReleaseStatus", ""),
                "authorizationProof": item.get("authorizationProof", ""),
                "generationModel": item.get("generationModel", ""),
                "generationPromptHash": item.get("generationPromptHash", ""),
                "generatedAt": item.get("generatedAt", ""),
                "syntheticDisclosure": item.get("syntheticDisclosure", ""),
                # 相关性/说明/类型/尺寸：供 relevance 门、caption 与像素门消费。
                "caption": item.get("caption", ""),
                "relevance": item.get("relevance") or item.get("caption") or "",
                "contentType": item.get("contentType", ""),
                "width": item.get("width", ""),
                "height": item.get("height", ""),
                "sourceCollectionId": item.get("sourceCollectionId", ""),
                "creator": item.get("creator") or item.get("author") or "",
                "collectionPageUrl": item.get("collectionPageUrl") or item.get("sourceUrl") or "",
                "placeholderId": item.get("placeholderId", ""),
                "placementType": item.get("placementType", ""),
                "groupId": item.get("groupId", ""),
                "sectionSlug": item.get("sectionSlug", ""),
                "sourceOrder": item.get("sourceOrder", 0),
                "coverCandidateRank": item.get("coverCandidateRank", 0),
                "subjectKey": item.get("subjectKey", ""),
                "isMapLike": bool(item.get("isMapLike")),
                "fileTitle": item.get("fileTitle", ""),
                "pageResolvedTitle": item.get("pageResolvedTitle", ""),
                "pageId": item.get("pageId", 0),
                "pageRevisionId": item.get("pageRevisionId", 0),
                "pageContentSha256": item.get("pageContentSha256", ""),
                "renderedImageCount": item.get("renderedImageCount", 0),
            }
        else:
            continue
        url = spec["url"]
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(spec)
    return out


def curated_images_for_entity(
    execution_id: str,
    entity_id: str,
    entity_type: str = "",
    *,
    research_lane: str | None = None,
) -> list[dict[str, Any]]:
    """读 source_plan 中实体级 imageUrls（顶层/payload）+ 各 source 的 imageUrls，去重合并。

    每项规范化为 {url, license, credit}。Agent 在 source_plan 输入里给出真实可用图（CC/PD/授权），
    download 据此下图到来源单元 assets/，供 post 选图与 imageGate 体检。
    """
    selected_lane = str(research_lane or "").strip() or None
    if selected_lane not in {None, "homepage", "image", "video"}:
        return []
    files: list[tuple[str, Path]] = []
    if selected_lane in {None, "image", "video"}:
        visual_lanes = ("image", "video") if selected_lane is None else (selected_lane,)
        files = _source_plan_files(
            execution_id, entity_id, entity_type, lanes=visual_lanes
        )
    specs: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for lane_name, plan_file in files:
        data = read_json(plan_file)
        if not isinstance(data, dict):
            continue
        payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
        raw_specs = data.get("imageUrls") or payload.get("imageUrls") or []
        for extra in _normalize_image_specs(raw_specs):
            lane_key = str(extra.get("researchLane") or lane_name or "image")
            key = (lane_key, extra["url"])
            if key not in seen:
                seen.add(key)
                specs.append(extra)
        raw_assets = data.get("assets") or payload.get("assets") or []
        for extra in _normalize_image_specs(raw_assets):
            extra["researchLane"] = lane_name
            lane_key = str(extra.get("researchLane") or lane_name)
            key = (lane_key, extra["url"])
            if key not in seen:
                seen.add(key)
                specs.append(extra)
        for collection in payload.get("collections") or data.get("collections") or []:
            if not isinstance(collection, dict):
                continue
            inherited = {
                "sourceCollectionId": collection.get("sourceCollectionId") or "",
                "creator": collection.get("creator") or "",
                "credit": collection.get("credit") or collection.get("creator") or "",
                "collectionPageUrl": collection.get("collectionPageUrl") or "",
                "license": collection.get("license") or "",
                "termsUrl": collection.get("termsUrl") or "",
                "licenseSnapshot": collection.get("licenseSnapshot") or "",
                "authorizationProof": collection.get("authorizationProof") or "",
                "usageScope": collection.get("usageScope") or "",
                "platform": collection.get("platform") or "",
                "modelReleaseRequired": collection.get("modelReleaseRequired") or "",
                "modelReleaseStatus": collection.get("modelReleaseStatus") or "",
            }
            images = collection.get("images") or []
            for extra in _normalize_image_specs(images):
                merged = {**inherited, **{k: v for k, v in extra.items() if v not in ("", None)}}
                if inherited.get("collectionPageUrl"):
                    merged["collectionPageUrl"] = inherited["collectionPageUrl"]
                if inherited.get("creator"):
                    merged["creator"] = inherited["creator"]
                if inherited.get("credit"):
                    merged["credit"] = inherited["credit"]
                lane_key = str(merged.get("researchLane") or lane_name or "image")
                key = (lane_key, merged["url"])
                if key not in seen:
                    seen.add(key)
                    specs.append(merged)
        for src in _extract_sources(data):
            if not isinstance(src, dict):
                continue
            for extra in _normalize_image_specs(src.get("imageUrls") or []):
                lane_key = str(extra.get("researchLane") or lane_name or "image")
                key = (lane_key, extra["url"])
                if key not in seen:
                    seen.add(key)
                    specs.append(extra)
    if selected_lane in {None, "homepage"}:
        for extra in curated_homepage_media_for_entity(
            execution_id,
            entity_id,
            entity_type,
        ):
            key = ("homepage", extra["url"])
            if key not in seen:
                seen.add(key)
                specs.append(extra)
        # Homepage imagery is sourced from the homepage evidence itself, not from
        # the image-work research lane. Keep it distinguishable so downstream
        # selection cannot accidentally publish it as an image work.
        for source in curated_sources_for_entity(
            execution_id,
            entity_id,
            entity_type,
            research_lane="homepage",
        ):
            plan_files = _source_plan_files(
                execution_id,
                entity_id,
                entity_type,
                lanes=("homepage",),
            )
            for _lane, plan_file in plan_files:
                data = read_json(plan_file)
                for raw_source in _extract_sources(data):
                    raw_id = str(
                        raw_source.get("source_id")
                        or raw_source.get("sourceId")
                        or raw_source.get("id")
                        or ""
                    )
                    if raw_id != str(source.get("source_id") or ""):
                        continue
                    inherited = {
                        "sourceCollectionId": f"homepage:{raw_id}",
                        "creator": raw_source.get("credit") or raw_source.get("creator") or "",
                        "collectionPageUrl": raw_source.get("url") or "",
                        "license": raw_source.get("license") or "",
                        "termsUrl": raw_source.get("termsUrl") or "",
                        "licenseSnapshot": raw_source.get("licenseSnapshot") or "",
                        "authorizationProof": raw_source.get("authorizationProof") or "",
                        "usageScope": raw_source.get("usageScope") or "",
                        "modelReleaseRequired": raw_source.get("modelReleaseRequired") or "",
                        "modelReleaseStatus": raw_source.get("modelReleaseStatus") or "",
                        "platform": raw_source.get("platform") or "",
                        "researchLane": "homepage",
                        "sourceId": raw_id,
                    }
                    for extra in _normalize_image_specs(raw_source.get("imageUrls") or []):
                        merged = {
                            **inherited,
                            **{k: v for k, v in extra.items() if v not in ("", None)},
                        }
                        key = ("homepage", merged["url"])
                        if key not in seen:
                            seen.add(key)
                            specs.append(merged)
    for spec in specs:
        spec.setdefault("researchLane", selected_lane or "image")
    return specs


def curated_homepage_media_for_entity(
    execution_id: str,
    entity_id: str,
    entity_type: str = "",
) -> list[dict[str, Any]]:
    """Read independent homepage media collections with their own rights chain."""
    specs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _lane, plan_file in _source_plan_files(
        execution_id,
        entity_id,
        entity_type,
        lanes=("homepage",),
    ):
        data = read_json(plan_file)
        for collection in _extract_collections(data, "homepageMediaCollections"):
            inherited = {
                "sourceCollectionId": collection.get("sourceCollectionId") or "",
                "creator": collection.get("creator") or "",
                "credit": collection.get("credit") or collection.get("creator") or "",
                "collectionPageUrl": collection.get("collectionPageUrl") or "",
                "license": collection.get("license") or "",
                "termsUrl": collection.get("termsUrl") or "",
                "licenseSnapshot": collection.get("licenseSnapshot") or "",
                "authorizationProof": collection.get("authorizationProof") or "",
                "usageScope": collection.get("usageScope") or "",
                "platform": collection.get("platform") or "",
                "modelReleaseStatus": collection.get("modelReleaseStatus") or "",
                "researchLane": "homepage",
                "mediaEvidenceMode": "independent_rights_cleared",
            }
            for extra in _normalize_image_specs(collection.get("images") or []):
                merged = {**inherited, **{k: v for k, v in extra.items() if v not in ("", None)}}
                merged["researchLane"] = "homepage"
                merged["mediaEvidenceMode"] = "independent_rights_cleared"
                url = str(merged.get("url") or "").strip()
                if not url or url in seen:
                    continue
                seen.add(url)
                specs.append(merged)
    return specs


def source_frontmatter(source: dict[str, Any], entity_id: str) -> str:
    """来源 frontmatter：只记录真实抓取元信息，source.md 正文不再允许 task body 冒充。"""
    use_mode = str(source.get("sourceUseMode") or SOURCE_USE_FACTUAL_REFERENCE)
    allowed_use = (
        "licensed_adaptation"
        if use_mode == SOURCE_USE_LICENSED_ADAPTATION
        else "facts_only"
    )
    return (
        f"---\n"
        f"url: {source.get('url', '')}\n"
        f"platform: {source.get('platform', 'web')}\n"
        f"sourceUseMode: {use_mode}\n"
        f"license: {source.get('license') or 'reference-only'}\n"
        f"allowedUse: {allowed_use}\n"
        f"credit: {source.get('credit', '')}\n"
        f"termsUrl: {source.get('termsUrl', '')}\n"
        f"licenseSnapshot: {source.get('licenseSnapshot', '')}\n"
        f"authorizationProof: {source.get('authorizationProof', '')}\n"
        f"entity: {entity_id}\n"
        f"retained: false\n"
        f"taskProvidedBody: {'true' if str(source.get('body') or '').strip() else 'false'}\n"
        f"---\n\n"
    )


def source_plan_rights_issues(
    execution_id: str,
    entity_id: str,
    entity_type: str = "",
    require_explicit: bool = False,
    research_lane: str | None = None,
) -> list[str]:
    """校验 source_plan 的文字来源权利分层，阻断缺模式和伪授权。"""
    issues: list[str] = []
    for source in curated_sources_for_entity(
        execution_id,
        entity_id,
        entity_type,
        research_lane=research_lane,
    ):
        sid = str(source.get("source_id") or "?")
        mode = str(source.get("sourceUseMode") or "").strip()
        if not mode and not require_explicit:
            mode = SOURCE_USE_FACTUAL_REFERENCE
        if mode not in VALID_SOURCE_USE_MODES:
            issues.append(f"{sid}: sourceUseMode must be one of {sorted(VALID_SOURCE_USE_MODES)}")
            continue
        if mode == SOURCE_USE_BLOCKED:
            issues.append(f"{sid}: blocked source must not enter a consumable source plan")
            continue
        if mode == SOURCE_USE_LICENSED_ADAPTATION:
            for field in ("license", "termsUrl", "licenseSnapshot"):
                if not str(source.get(field) or "").strip():
                    issues.append(f"{sid}: licensed_adaptation missing {field}")
    return issues


def manual_body_note(source: dict[str, Any], *, max_chars: int = 180) -> str:
    """task/source_plan 里的 body 仅作为人工计划备注，不得充当 source.md 正文。"""
    body = re.sub(r"\s+", " ", str(source.get("body") or "")).strip()
    if not body:
        return ""
    clipped = body[:max_chars]
    if len(body) > max_chars:
        clipped += "..."
    return f"manual_source_plan_note: {clipped}"
