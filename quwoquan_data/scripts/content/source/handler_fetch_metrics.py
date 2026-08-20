"""Per-source metrics and accepted result projection for download fetch."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from content.source.contracts import MediaProvenance
from content.source.html_text import html_has_inline_video


def page_has_inline_video(html_bytes: bytes | None, fetched_text: str) -> bool:
    if html_bytes and html_has_inline_video(html_bytes.decode("utf-8", errors="replace")):
        return True
    return bool(fetched_text and html_has_inline_video(fetched_text))


def apply_source_image_rejections(
    rejected_by_category: dict[str, int],
    drop_categories: object,
) -> None:
    if not isinstance(drop_categories, Mapping):
        return
    category_map = {
        "fetch_failure": "fetch_or_non_image",
        "pixel_policy": "pixel_too_small",
        "decode_policy": "safety_or_watermark",
        "safety_policy": "safety_or_watermark",
        "rights_policy": "rights",
        "relevance_policy": "other",
        "invalid_payload": "other",
        "duplicate": "other",
    }
    for category, count in drop_categories.items():
        rejected_by_category[category_map.get(str(category), "other")] += int(count or 0)


def source_with_fetch_runtime(
    source: Mapping[str, Any], fetch_runtime: Mapping[str, Any]
) -> dict[str, Any]:
    projected = dict(source)
    for key in ("requestedTitle", "resolvedTitle", "redirectChain", "fetchFinalUrl"):
        if key in fetch_runtime:
            projected["finalUrl" if key == "fetchFinalUrl" else key] = fetch_runtime[key]
    return projected


def build_source_asset_count_row(
    *,
    manifest: Mapping[str, Any],
    source: Mapping[str, Any],
    quality: Mapping[str, Any],
    source_image_funnel: Mapping[str, Any],
    source_images: list[dict[str, Any]],
    vertical: str,
) -> dict[str, Any]:
    candidate_count = int(source_image_funnel.get("candidateCount") or 0)
    accepted_count = (
        int(manifest.get("assetCount") or 0)
        if str(quality.get("quality") or "") != "Reject"
        else 0
    )
    fetch_failures = source_image_funnel.get("fetchFailures")
    downloaded_count = candidate_count - (
        len(fetch_failures) if isinstance(fetch_failures, list) else 0
    )
    rights_counts = {
        "verifiedAssetCount": 0,
        "unverifiedAssetCount": 0,
        "restrictedAssetCount": 0,
        "unknownAssetCount": 0,
    }
    for image in source_images if accepted_count else ():
        status = MediaProvenance.from_mapping(
            image,
            vertical=vertical,
        ).rights_audit_status.value
        rights_counts[f"{status}AssetCount"] += 1
    return {
        "displayName": str(manifest.get("title") or source["source_id"]),
        "provider": str(manifest.get("platform") or "web"),
        "plannedAssetCount": candidate_count,
        "discoveredAssetCount": candidate_count,
        "downloadedAssetCount": max(0, downloaded_count),
        "acceptedAssetCount": accepted_count,
        "rejectedAssetCount": max(0, candidate_count - accepted_count),
        **rights_counts,
    }


def accepted_source_rows(
    *,
    source: Mapping[str, Any],
    quality: Mapping[str, Any],
    entity_id: str,
    status_code: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    retained = bool(quality.get("retainedFromCache"))
    return (
        {
            "sourceId": source["source_id"],
            "quality": quality.get("quality"),
            "score": quality.get("score"),
            "url": source["url"],
            "statusCode": quality.get("statusCode", status_code),
            "retainedFromCache": retained,
        },
        {
            "sourceId": source["source_id"],
            "url": source["url"],
            "quality": quality.get("quality"),
            "score": quality.get("score"),
            "entityId": entity_id,
            "retainedFromCache": retained,
        },
    )
