"""Anonymous Wikimedia Commons video discovery without execution runtime imports."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from content.source.research import network_io
from content.source.research.source_quality import license_allows_commercial_distribution
from content.source.research.text_match import _normalized_title
from content.source.research.wiki_common import _strip_html

def discover_commons_sourced_videos(
    entity_id: str,
    *,
    entity_aliases: list[str],
    limit: int = 50,
    selected_limit: int = 1,
    diagnostics: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Discover anonymous public Commons video candidates with an audit funnel."""

    pages: list[dict[str, Any]] = []
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
        # Commons 对 CC0/PD 历史条目返回 http:// 的 canonical license URL；
        # creativecommons.org 全站强制 TLS,协议归一不改变权利语义,
        # 否则 schema 的 ^https:// termsUrl 门会误拦 CC0 素材。
        if license_url.startswith("http://creativecommons.org/"):
            license_url = "https://" + license_url.removeprefix("http://")
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
            not license_allows_commercial_distribution(license_name, license_url)
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
                "distributionDecision": "research_allowed",
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
    if selected_limit < 1:
        raise ValueError("Commons video selected_limit must be at least one")
    selected = candidates[:selected_limit]
    funnel["selectedForAnonymousDownload"] = len(selected)
    if diagnostics is not None:
        diagnostics.append(funnel)
    return selected


__all__ = ["discover_commons_sourced_videos"]
