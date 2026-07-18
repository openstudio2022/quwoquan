"""Download repair hint strategies for task execution runs."""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from core.data_issue import DataIssue, DataIssueCode, DataIssueLane
from content.execution.context import ExecutionContext


def _declared_pixel_issue(image: dict, *, asset_id: str) -> str | None:
    """Validate declared dimensions exactly as provided by the research content.execution.planning."""
    from core.image_rules import pixel_size_issue

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
        from content.source.fetch_image_candidates import candidate_image_urls

        if len(candidate_image_urls(str(image.get("url") or ""))) > 1:
            return None
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
    from content.source.fetch_image_candidates import candidate_image_urls

    candidates = candidate_image_urls(str(image.get("url") or ""))
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
    ctx: ExecutionContext,
    entity_id: str,
    etype: str,
) -> list[dict[str, Any]]:
    """Return actionable image-resolution repair hints for the research lanes."""
    from content.source.source_inputs import curated_images_for_entity, curated_sources_for_entity
    from governance.coverage.license import validate_image_rights

    hints: list[dict[str, Any]] = []
    for lane in ("homepage", "article"):
        for source in curated_sources_for_entity(
            ctx.execution_id,
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
                        vertical=ctx.spec.vertical,
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
            for item in curated_images_for_entity(ctx.execution_id, entity_id, etype)
            if str(item.get("researchLane") or "image") == "image"
        ],
        start=1,
    ):
        rights_hint = _image_rights_repair_hint(
            image,
            validate_image_rights(
                image,
                vertical=ctx.spec.vertical,
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
    categories = diagnostics.get("rejectedByCategory")
    if not isinstance(categories, Mapping):
        return hints
    actions = {
        "fetch_or_non_image": "replace_unfetchable_or_non_image_asset",
        "pixel_too_small": "replace_low_resolution_asset",
        "safety_or_watermark": "replace_unsafe_or_watermarked_image",
        "rights": "replace_image_with_explicit_publishable_rights",
        "duplicate": "add_distinct_publishable_image",
        "other": "review_structured_image_rejection",
    }
    for index, category in enumerate(actions, start=1):
        try:
            count = int(categories.get(category) or 0)
        except (TypeError, ValueError):
            count = 0
        if count <= 0:
            continue
        hints.append(
            {
                "lane": "image",
                "entityId": entity_id,
                "sourceId": "",
                "imageIndex": index,
                "assetId": f"{entity_id}/rejected/{category}",
                "url": "",
                "width": "",
                "height": "",
                "issue": f"{category} rejected images={count}",
                "sameSourceHighResCandidate": "",
                "candidateUrls": [],
                "action": actions[category],
            }
        )
    return hints


def _download_issue_repair_hints(
    issues: Sequence[DataIssue],
    *,
    entity_id: str,
) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    source_codes = {
        DataIssueCode.SOURCE_MISSING,
        DataIssueCode.SOURCE_PLAN_INVALID,
        DataIssueCode.SOURCE_RETAINED_SHORTFALL,
        DataIssueCode.SOURCE_CATEGORY_SHORTFALL,
        DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING,
    }
    media_codes = {
        DataIssueCode.MEDIA_FETCH_FAILED,
        DataIssueCode.MEDIA_RIGHTS_UNAVAILABLE,
        DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
        DataIssueCode.MEDIA_DOWNLOAD_INCOMPLETE,
    }
    for index, issue in enumerate(issues, start=1):
        lane = issue.lane.value
        if lane not in {"homepage", "article", "image"}:
            continue
        if issue.code in source_codes and lane == "homepage":
            action = "add_or_replace_homepage_encyclopedia_seed_source"
        elif issue.code in source_codes and lane == "article":
            action = "add_or_replace_article_text_sources_with_fetchable_quality_evidence"
        elif issue.code in media_codes and lane == "homepage":
            action = "add_or_replace_homepage_source_images_with_complete_rights"
        elif issue.code in media_codes:
            action = "add_or_replace_image_source_collections_with_complete_rights"
        else:
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
                "issue": str(issue),
                "sameSourceHighResCandidate": "",
                "candidateUrls": [],
                "action": action,
            }
        )
    return hints


def _download_repair_lanes(repair: dict[str, Any]) -> set[str]:
    lanes: set[str] = set()
    records = repair.get("issueRecords")
    for raw in records if isinstance(records, list) else []:
        if not isinstance(raw, Mapping):
            continue
        try:
            issue = DataIssue.from_dict(raw)
        except (TypeError, ValueError):
            continue
        if issue.lane is not DataIssueLane.ALL:
            lanes.add(issue.lane.value)
    if lanes:
        return lanes
    for hint in repair.get("imageRepairHints") or []:
        if isinstance(hint, dict) and str(hint.get("lane") or "") in {"homepage", "article", "image"}:
            lanes.add(str(hint.get("lane")))
    return lanes
