"""Download repair hint strategies for task workflow runs."""
from __future__ import annotations

import re
from typing import Any

from task.run_context import PipelineContext

_SOURCE_CATEGORY_REPAIR_MARKERS = (
    "missing core source categories",
    "source categories",
)


def _download_source_category_issue_lane(issue_text: str) -> str:
    lowered = str(issue_text or "").casefold()
    if not any(marker in lowered for marker in _SOURCE_CATEGORY_REPAIR_MARKERS):
        return ""
    homepage_markers = ("encyclopedia", "official evidence", "homepage", "主页", "百科")
    if any(marker in lowered for marker in homepage_markers):
        return "homepage"
    article_markers = (
        "travelogue",
        "guidebook",
        "official_article",
        "vertical_professional",
        "ugc_longform",
        "community_post",
        "media_article",
        "platform_article",
        "forum_thread",
        "review_note",
    )
    if any(marker in lowered for marker in article_markers):
        return "article"
    return ""


def _declared_pixel_issue(image: dict, *, asset_id: str) -> str | None:
    """Validate declared dimensions exactly as provided by the research plan."""
    from _common.image_rules import pixel_size_issue

    raw_width = str(image.get("width") or "").strip()
    raw_height = str(image.get("height") or "").strip()
    if not raw_width and not raw_height:
        return None
    try:
        width = int(float(raw_width or "0"))
        height = int(float(raw_height or "0"))
    except ValueError:
        return f"imagePixels: {asset_id} 像素尺寸字段不可解析 width={raw_width!r} height={raw_height!r}"
    return pixel_size_issue(width, height, asset_id=asset_id)


def _planned_pixel_issue(image: dict, *, asset_id: str) -> str | None:
    """Validate declared dimensions when the research plan provides them."""
    issue = _declared_pixel_issue(image, asset_id=asset_id)
    if issue:
        try:
            from download.fetch import candidate_image_urls

            if len(candidate_image_urls(str(image.get("url") or ""))) > 1:
                return None
        except Exception:  # noqa: BLE001
            pass
    return issue


def _image_repair_hint(
    image: dict,
    *,
    lane: str,
    entity_id: str,
    asset_id: str,
    source_id: str = "",
    image_index: int = 0,
) -> dict[str, Any] | None:
    issue = _declared_pixel_issue(image, asset_id=asset_id)
    if not issue:
        return None
    try:
        from download.fetch import candidate_image_urls

        candidates = candidate_image_urls(str(image.get("url") or ""))
    except Exception:  # noqa: BLE001
        candidates = [str(image.get("url") or "")]
    high_res_candidate = candidates[1] if len(candidates) > 1 else ""
    return {
        "lane": lane,
        "entityId": entity_id,
        "sourceId": source_id,
        "imageIndex": image_index,
        "assetId": asset_id,
        "url": str(image.get("url") or ""),
        "width": image.get("width") or "",
        "height": image.get("height") or "",
        "issue": issue,
        "sameSourceHighResCandidate": high_res_candidate,
        "candidateUrls": candidates[:3],
        "action": (
            "retry_with_same_source_high_resolution_url"
            if high_res_candidate
            else "replace_image_or_source_unit"
        ),
    }


def _image_rights_repair_hint(
    image: dict[str, Any],
    issues: list[str],
    *,
    lane: str,
    entity_id: str,
    asset_id: str,
    source_id: str = "",
    image_index: int = 0,
) -> dict[str, Any] | None:
    if not issues:
        return None
    issue_text = "; ".join(str(issue) for issue in issues)
    license_value = str(image.get("license") or "").strip()
    action = "replace_image_or_source_unit_with_explicit_publishable_image_rights"
    if license_value in {"factual_reference_only", "licensed_adaptation", "blocked"}:
        action = "replace_image_or_source_unit_do_not_use_sourceUseMode_as_image_license"
    return {
        "lane": lane,
        "entityId": entity_id,
        "sourceId": source_id,
        "imageIndex": image_index,
        "assetId": asset_id,
        "url": str(image.get("url") or ""),
        "width": image.get("width") or "",
        "height": image.get("height") or "",
        "issue": issue_text,
        "sameSourceHighResCandidate": "",
        "candidateUrls": [str(image.get("url") or "")] if str(image.get("url") or "") else [],
        "action": action,
    }


def _research_image_repair_hints(
    ctx: PipelineContext,
    entity_id: str,
    etype: str,
) -> list[dict[str, Any]]:
    """Return actionable image-resolution repair hints for the research lanes."""
    from download.source_inputs import curated_images_for_entity, curated_sources_for_entity
    from vertical.license import validate_image_rights

    hints: list[dict[str, Any]] = []
    for lane in ("homepage", "article"):
        for source in curated_sources_for_entity(
            ctx.task_id,
            ctx.batch_id,
            entity_id,
            etype,
            research_lane=lane,
        ):
            source_id = str(source.get("source_id") or "")
            for index, image in enumerate(source.get("imageUrls") or [], start=1):
                rights_hint = _image_rights_repair_hint(
                    image,
                    validate_image_rights(
                        image,
                        vertical=str(ctx.spec.get("vertical") or "travel"),
                    ),
                    lane=lane,
                    entity_id=entity_id,
                    source_id=source_id,
                    image_index=index,
                    asset_id=f"{entity_id}/{source_id}#{index}",
                )
                if rights_hint:
                    hints.append(rights_hint)
                hint = _image_repair_hint(
                    image,
                    lane=lane,
                    entity_id=entity_id,
                    source_id=source_id,
                    image_index=index,
                    asset_id=f"{entity_id}/{source_id}#{index}",
                )
                if hint:
                    hints.append(hint)
    for index, image in enumerate(
        [
            item
            for item in curated_images_for_entity(ctx.task_id, ctx.batch_id, entity_id, etype)
            if str(item.get("researchLane") or "image") == "image"
        ],
        start=1,
    ):
        rights_hint = _image_rights_repair_hint(
            image,
            validate_image_rights(
                image,
                vertical=str(ctx.spec.get("vertical") or "travel"),
            ),
            lane="image",
            entity_id=entity_id,
            source_id=str(image.get("sourceCollectionId") or ""),
            image_index=index,
            asset_id=f"{entity_id}/image#{index}",
        )
        if rights_hint:
            hints.append(rights_hint)
        hint = _image_repair_hint(
            image,
            lane="image",
            entity_id=entity_id,
            source_id=str(image.get("sourceCollectionId") or ""),
            image_index=index,
            asset_id=f"{entity_id}/image#{index}",
        )
        if hint:
            hints.append(hint)
    return hints


def _download_diagnostic_image_repair_hints(
    diagnostics: dict[str, Any],
    *,
    entity_id: str,
) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    for index, raw in enumerate(diagnostics.get("sampleRejected") or [], start=1):
        text = str(raw or "")
        if not text:
            continue
        source_id = ""
        url = ""
        source_match = re.search(r"sourceImage:([^:\s]+):", text)
        if source_match:
            source_id = source_match.group(1)
        url_match = re.search(r"\((https?://[^)]+)\)", text)
        if url_match:
            url = url_match.group(1)
        if source_id.startswith("article") or "article" in text:
            lane = "article"
        elif source_id.startswith("home") or "homepage" in text or "主页" in text:
            lane = "homepage"
        else:
            lane = "image"
        action = "replace_image_or_source_unit"
        if "imageSafety" in text or "watermark" in text:
            action = "replace_unsafe_or_watermarked_image"
        elif "imageFetch" in text or "non-image" in text or "too small" in text:
            action = "replace_unfetchable_or_low_quality_image"
        hints.append(
            {
                "lane": lane,
                "entityId": entity_id,
                "sourceId": source_id,
                "imageIndex": index,
                "assetId": f"{entity_id}/{source_id or 'rejected'}#{index}",
                "url": url,
                "width": "",
                "height": "",
                "issue": text,
                "sameSourceHighResCandidate": "",
                "candidateUrls": [url] if url else [],
                "action": action,
            }
        )
    return hints


def _download_issue_repair_hints(
    issues: list[str],
    *,
    entity_id: str,
) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    for index, raw in enumerate(issues, start=1):
        text = str(raw or "")
        if not text:
            continue
        lane = ""
        action = ""
        category_lane = _download_source_category_issue_lane(text)
        if category_lane == "homepage":
            lane = "homepage"
            action = "add_or_replace_homepage_encyclopedia_or_official_seed_source"
        elif category_lane == "article":
            lane = "article"
            action = "add_or_replace_article_text_sources_with_fetchable_quality_evidence"
        elif (
            "text-qualified base sources" in text
            or "article base sources" in text
            or "article sources" in text
            or "文章" in text
        ):
            lane = "article"
            action = "add_or_replace_article_text_sources_with_fetchable_quality_evidence"
        elif (
            "unique publishable image" in text
            or "imageCount" in text
            or "imageFetch" in text
            or "未下到真实图片" in text
            or "合格去重图" in text
            or "source collection" in text
            or "image gates failed" in text
            or "image_fetch_gate" in text
            or "image_rights_gate" in text
            or "图片作品" in text
        ):
            lane = "image"
            action = "add_or_replace_image_source_collections_with_complete_rights"
        elif "homepage" in text or "主页" in text:
            lane = "homepage"
            action = "add_or_replace_homepage_source_images_with_complete_rights"
        if not lane:
            continue
        hints.append(
            {
                "lane": lane,
                "entityId": entity_id,
                "sourceId": "",
                "imageIndex": index,
                "assetId": f"{entity_id}/download_repair#{index}",
                "url": "",
                "width": "",
                "height": "",
                "issue": text,
                "sameSourceHighResCandidate": "",
                "candidateUrls": [],
                "action": action,
            }
        )
    return hints


def _download_repair_lanes(repair: dict[str, Any]) -> set[str]:
    issue_text = " ".join(str(item) for item in (repair.get("issues") or []))
    lanes: set[str] = set()
    category_lane = _download_source_category_issue_lane(issue_text)
    if category_lane:
        lanes.add(category_lane)
    if "article" in issue_text or "文章" in issue_text or "source unit(s) with images" in issue_text:
        lanes.add("article")
    if "homepage" in issue_text or "主页" in issue_text:
        lanes.add("homepage")
    if (
        "image research" in issue_text
        or "imageCount" in issue_text
        or "imageFetch" in issue_text
        or "未下到真实图片" in issue_text
        or "合格去重图" in issue_text
        or "publishable image" in issue_text
        or "sourceCollection" in issue_text
        or "image gates failed" in issue_text
        or "image_fetch_gate" in issue_text
        or "image_rights_gate" in issue_text
        or "图片作品" in issue_text
    ):
        lanes.add("image")
    research_issues = repair.get("researchLaneIssues") or {}
    if isinstance(research_issues, dict):
        lanes.update(
            lane for lane, lane_issues in research_issues.items()
            if lane in {"homepage", "article", "image"} and lane_issues
        )
    if lanes:
        return lanes
    for hint in repair.get("imageRepairHints") or []:
        if isinstance(hint, dict) and str(hint.get("lane") or "") in {"homepage", "article", "image"}:
            lanes.add(str(hint.get("lane")))
    return lanes
