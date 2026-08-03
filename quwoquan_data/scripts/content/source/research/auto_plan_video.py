"""Build the formal video lane from individually rights-cleared source frames."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from datetime import UTC, datetime

from core.data_issue import DataIssueCode, DataRecoveryAction
from governance.content_supply_policy import load_content_supply_policy
from governance.coverage.distribution import (
    ProductLifecycleState,
    load_content_distribution_policy,
)
from content.source.research import network_io
from content.source.research.plan_state import (
    _record_unavailable,
    _safe_collection_id,
    _source_unavailable_for_entity,
    _write_lane,
)
from content.source.research.source_quality import (
    _collection_gate,
    _license_allows_app_publish,
)
from content.source.research.text_match import _normalized_title
from content.source.research.wiki_common import _strip_html


def discover_commons_sourced_videos(
    entity_id: str,
    *,
    entity_aliases: list[str],
    limit: int = 50,
    diagnostics: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Discover anonymous public Commons video candidates with an audit funnel."""

    pages: list[dict[str, Any]] = []
    lifecycle = load_content_distribution_policy().product_lifecycle_state
    seen_page_ids: set[str] = set()
    search_terms = list(dict.fromkeys([entity_id, *entity_aliases]))[:3]
    funnel = {
        "provider": "wikimedia_commons_video",
        "entityId": entity_id,
        "attempted": True,
        "queryCount": len(search_terms),
        "discovered": 0,
        "rejectedMalformed": 0,
        "rejectedByRelevance": 0,
        "rejectedByRights": 0,
        "rejectedByQuality": 0,
        "selectedForAnonymousDownload": 0,
        "notAttemptedProviders": [
            "pexels_videos",
            "pixabay_videos",
            "pond5",
            "storyblocks",
            "youtube",
            "vimeo",
            "bilibili",
            "douyin",
            "tiktok",
            "weibo",
            "toutiao_video",
        ],
    }
    for search_term in search_terms:
        data = network_io.wiki_api(
            "commons.wikimedia.org",
            {
                "action": "query",
                "generator": "search",
                "gsrsearch": f"{search_term} filetype:video",
                "gsrnamespace": "6",
                "gsrlimit": str(limit),
                "prop": "imageinfo",
                "iiprop": "url|size|mime|mediatype|extmetadata",
                "format": "json",
                "formatversion": "2",
            },
        )
        for page in (data.get("query") or {}).get("pages") or []:
            if not isinstance(page, dict):
                continue
            page_id = str(page.get("pageid") or page.get("title") or "")
            if page_id and page_id not in seen_page_ids:
                seen_page_ids.add(page_id)
                pages.append(page)
    aliases = [
        _normalized_title(value)
        for value in [entity_id, *entity_aliases]
        if _normalized_title(value)
    ]
    entity_key = _normalized_title(entity_id)
    qualifiers = {
        entity_key[: -len(alias)]
        for alias in aliases
        if alias != entity_key and entity_key.endswith(alias) and len(entity_key) > len(alias)
    }
    candidates: list[dict[str, Any]] = []
    for page in pages:
        if not isinstance(page, dict):
            funnel["rejectedMalformed"] += 1
            continue
        info = ((page.get("imageinfo") or [{}])[0] or {})
        metadata = info.get("extmetadata") or {}
        if not isinstance(info, dict) or not isinstance(metadata, dict):
            funnel["rejectedMalformed"] += 1
            continue
        funnel["discovered"] += 1
        url = str(info.get("url") or "").strip()
        source_url = str(
            info.get("descriptionurl") or info.get("descriptionshorturl") or ""
        ).strip()
        title = str(page.get("title") or "").removeprefix("File:").strip()
        description = _strip_html(
            str(((metadata.get("ImageDescription") or {}).get("value") or ""))
        )
        combined_key = _normalized_title(f"{title} {description}")
        if not any(alias in combined_key for alias in aliases):
            funnel["rejectedByRelevance"] += 1
            continue
        if qualifiers and not any(qualifier in combined_key for qualifier in qualifiers):
            funnel["rejectedByRelevance"] += 1
            continue
        license_name = _strip_html(
            str(((metadata.get("LicenseShortName") or {}).get("value") or ""))
        )
        license_url = _strip_html(
            str(((metadata.get("LicenseUrl") or {}).get("value") or ""))
        )
        categories = _strip_html(
            str(((metadata.get("Categories") or {}).get("value") or ""))
        ).lower()
        size = int(info.get("size") or 0)
        duration = float(info.get("duration") or 0)
        if (
            str(info.get("mediatype") or "") != "VIDEO"
            or not url.startswith("https://")
            or not source_url.startswith("https://")
            or size <= 0
            or size > 512 * 1024 * 1024
            or duration < 3
            or duration > 180
        ):
            funnel["rejectedByQuality"] += 1
            continue
        if (
            not _license_allows_app_publish(license_name, license_url)
            or "license review needed" in categories
        ):
            funnel["rejectedByRights"] += 1
            continue
        creator = _strip_html(
            str(
                ((metadata.get("Artist") or {}).get("value") or "")
                or ((metadata.get("Credit") or {}).get("value") or "")
            )
        )
        if not creator or not license_url:
            funnel["rejectedByRights"] += 1
            continue
        candidates.append(
            {
                "sourceId": "wikimedia_commons_video",
                "sourceKind": "tourism_video_site",
                "ordinal": 1,
                "title": title,
                "relevance": description or title,
                "platform": "Wikimedia Commons",
                "assetUrl": url,
                "sourcePostUrl": source_url,
                "authorizationProofUrl": source_url,
                "termsUrl": license_url,
                "rightsBasis": license_name,
                "originalCreatorName": creator,
                "attributionText": (
                    f"{title} — {creator} — {license_name} — {source_url}"
                ),
                "commercialAuthorizationStatus": "verified",
                # License metadata is prechecked here, but the remote bytes have
                # not yet passed probe/OCR/audio admission. Only that later gate
                # may change this candidate from unverified to publishable.
                "rightsStatus": "unverified",
                "rightsIssues": [
                    "downloaded bytes have not yet completed media and rights admission"
                ],
                "publicationAdmission": (
                    "research_release"
                    if lifecycle is ProductLifecycleState.RESEARCH
                    else "commercial_release"
                ),
                "modelReleaseStatus": "not_required",
                "propertyReleaseStatus": "not_required",
                "takedownPolicy": "quwoquan_standard_notice_and_takedown",
                "anonymousAccess": True,
                "credentialAssertion": "no_cookie_no_api_key_no_account_session",
                "downloadMethod": "anonymous_https_direct",
                "durationSeconds": duration,
                "sizeBytes": size,
                "popularitySignals": {
                    "playCount": None,
                    "likeCount": None,
                    "commentCount": None,
                    "shareCount": None,
                    "favoriteCount": None,
                    "observedAt": datetime.now(UTC).isoformat(),
                    "samePlatformTopicTimeBucketPercentile": None,
                    "rankingEligible": False,
                },
            }
        )
    candidates.sort(
        key=lambda item: (
            0 if entity_key in _normalized_title(str(item["title"])) else 1,
            float(item["durationSeconds"]),
            int(item["sizeBytes"]),
        )
    )
    selected = candidates[:1]
    funnel["selectedForAnonymousDownload"] = len(selected)
    if diagnostics is not None:
        diagnostics.append(funnel)
    return selected


def rank_video_candidates_by_popularity(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Rank only comparable candidates; missing metrics are never fabricated."""

    def key(item: dict[str, Any]) -> tuple[int, float, int]:
        signals = item.get("popularitySignals")
        payload = signals if isinstance(signals, dict) else {}
        raw_percentile = payload.get("samePlatformTopicTimeBucketPercentile")
        try:
            percentile = float(raw_percentile)
        except (TypeError, ValueError):
            return (1, 0.0, 0)
        engagement = sum(
            int(payload.get(field) or 0)
            for field in (
                "likeCount",
                "commentCount",
                "shareCount",
                "favoriteCount",
            )
        )
        return (0, -percentile, -engagement)

    return sorted(candidates, key=key)


def _minimum_source_frame_count(vertical: str) -> int:
    return load_content_supply_policy(vertical).video_delivery.minimum_source_frames


def _video_frame_candidate(
    raw: dict[str, Any],
    *,
    entity_id: str,
    ordinal: int,
    entity_aliases: list[str],
    vertical: str,
) -> tuple[dict[str, Any] | None, tuple[str, ...]]:
    item = dict(raw)
    collection_id = _safe_collection_id(
        "video_frame",
        entity_id,
        str(
            item.get("sourceCollectionId")
            or item.get("authorizationProof")
            or item.get("sourceUrl")
            or item.get("url")
            or ""
        ),
    )
    creator = str(
        item.get("creator")
        or item.get("credit")
        or "Wikimedia Commons contributor"
    ).strip()
    collection_page = str(
        item.get("collectionPageUrl")
        or item.get("sourceUrl")
        or item.get("authorizationProof")
        or item.get("url")
        or ""
    ).strip()
    item.update(
        {
            "sourceCollectionId": collection_id,
            "creator": creator,
            "credit": item.get("credit") or creator,
            "collectionPageUrl": collection_page,
            "authorizationProof": item.get("authorizationProof") or collection_page,
            "usageScope": item.get("usageScope") or "app_publish",
            "modelReleaseStatus": item.get("modelReleaseStatus") or "not_required",
            "researchLane": "video",
            "sourceId": f"video_frame_{ordinal}",
        }
    )
    collection = {
        "sourceCollectionId": collection_id,
        "creator": creator,
        "credit": item["credit"],
        "collectionPageUrl": collection_page,
        "platform": item.get("platform") or "Wikimedia Commons",
        "license": item.get("license") or "",
        "termsUrl": item.get("termsUrl") or "",
        "licenseSnapshot": item.get("licenseSnapshot") or "",
        "authorizationProof": item["authorizationProof"],
        "usageScope": item["usageScope"],
        "modelReleaseStatus": item["modelReleaseStatus"],
        "images": [item],
    }
    verdict = _collection_gate(
        collection,
        entity_id=entity_id,
        entity_aliases=entity_aliases,
        vertical=vertical,
    )
    issues = tuple(str(issue) for issue in verdict.get("issues") or ())
    return (item if verdict.get("passed") else None), issues


def _qualified_video_frames(
    *,
    entity_id: str,
    entity_aliases: list[str],
    vertical: str,
    image_pool: list[dict[str, Any]],
    limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Select only same-entity frames that already pass the collection gate."""

    frames: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for ordinal, raw in enumerate(image_pool, start=1):
        url = str(raw.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        frame, issues = _video_frame_candidate(
            raw,
            entity_id=entity_id,
            ordinal=ordinal,
            entity_aliases=entity_aliases,
            vertical=vertical,
        )
        diagnostics.append(
            {
                "entityId": entity_id,
                "url": url,
                "passed": frame is not None,
                "issues": list(issues),
            }
        )
        if frame is not None:
            frames.append(frame)
        if len(frames) >= limit:
            break
    return frames, diagnostics


def qualified_video_frame_count(
    *,
    entity_id: str,
    entity_aliases: list[str],
    vertical: str,
    image_pool: list[dict[str, Any]],
) -> int:
    """Count the production-qualified frames before deciding whether to rescue."""

    frames, _ = _qualified_video_frames(
        entity_id=entity_id,
        entity_aliases=entity_aliases,
        vertical=vertical,
        image_pool=image_pool,
        limit=_minimum_source_frame_count(vertical),
    )
    return len(frames)


def write_video_lane(
    *,
    entity_id: str,
    entity_aliases: list[str],
    vertical: str,
    plan_dir: Path,
    force: bool,
    report: dict[str, Any],
    updated: list[dict[str, Any]],
    open_license_image_pool: list[dict[str, Any]],
    sourced_video_pool: list[dict[str, Any]],
) -> None:
    minimum_frames = _minimum_source_frame_count(vertical)
    sourced_videos = list(sourced_video_pool[:1])
    # A direct video is only a candidate until download/probe/OCR/admission
    # completes. Keep a qualified frame sequence in the same frozen plan so a
    # transient or admission failure can fall back without restarting research.
    frames, frame_diagnostics = _qualified_video_frames(
        entity_id=entity_id,
        entity_aliases=entity_aliases,
        vertical=vertical,
        image_pool=open_license_image_pool,
        limit=minimum_frames,
    )
    report.setdefault("videoFrames", []).extend(frame_diagnostics)
    report.setdefault("videoDiscovery", []).append(
        {
            "entityId": entity_id,
            "directVideoCandidates": len(sourced_videos),
            "frameCandidates": len(frame_diagnostics),
            "qualifiedFrames": len(frames),
            "minimumFrames": minimum_frames,
        }
    )
    if not sourced_videos and len(frames) < minimum_frames:
        _record_unavailable(
            report,
            entity_id=entity_id,
            lane="video",
            reason=f"rights-cleared video frames={len(frames)} need>={minimum_frames}",
            code=DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
            recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
        )
    if _write_lane(
        plan_dir / "video_source_plan.json",
        "video",
        {
            "videos": sourced_videos,
            "assets": frames,
            "diagnostic": {
                "directVideoCandidates": len(sourced_videos),
                "qualifiedFrames": len(frames),
                "minimumFrames": minimum_frames,
                "fallbackFramesRetained": bool(sourced_videos and frames),
            },
            "sourceUnavailable": _source_unavailable_for_entity(
                report,
                entity_id=entity_id,
                lane="video",
            ),
        },
        force=force,
    ):
        updated.append(
            {
                "entityId": entity_id,
                "lane": "video",
                "videos": len(sourced_videos),
                "assets": len(frames),
            }
        )


__all__ = [
    "qualified_video_frame_count",
    "rank_video_candidates_by_popularity",
    "write_video_lane",
]
