"""Governed stock-video discovery for the registered Pexels/Pixabay providers.

Both providers are already registered in ``content_source_registry.yaml``
(``pexels_videos`` / ``pixabay_videos``: publish_candidate, research and
commercial admission).  Their official platform APIs require an API key; the
key lives outside the repository exactly like the Cursor key, and a missing
key is a typed provider-credential blocker instead of a silent fallback or a
scraping bypass.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.runtime_policy import active_runtime_policy

from content.source.research import network_io
from content.source.research.text_match import _normalized_title

PROVIDER_CREDENTIAL_MISSING = "DATA.SOURCE.PROVIDER_CREDENTIAL_MISSING"

_KEY_FILES = {
    "pexels_videos": ("QWQ_PEXELS_API_KEY_FILE", "pexels_api_key"),
    "pixabay_videos": ("QWQ_PIXABAY_API_KEY_FILE", "pixabay_api_key"),
}
_PEXELS_TERMS_URL = "https://www.pexels.com/license/"
_PIXABAY_TERMS_URL = "https://pixabay.com/service/license-summary/"
_MIN_DURATION_SECONDS = 3
_MAX_DURATION_SECONDS = 180


class StockVideoProviderCredentialMissing(RuntimeError):
    """The registered provider requires an API key that is not configured."""

    def __init__(self, provider: str, detail: str) -> None:
        self.provider = provider
        self.code = PROVIDER_CREDENTIAL_MISSING
        super().__init__(f"{self.code}: provider={provider}; {detail}")


def stock_video_api_key(provider: str) -> str:
    """Return the out-of-repo API key for one registered stock provider."""

    if provider not in _KEY_FILES:
        raise ValueError(f"unsupported stock video provider: {provider}")
    env_name, default_name = _KEY_FILES[provider]
    override = str(os.environ.get(env_name) or "").strip()
    path = (
        Path(override).expanduser()
        if override
        else Path.home() / ".config" / "quwoquan" / default_name
    )
    try:
        key = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        key = ""
    except OSError as exc:
        raise StockVideoProviderCredentialMissing(
            provider, f"api key file is unreadable: {path} ({exc})"
        ) from exc
    if not key:
        raise StockVideoProviderCredentialMissing(
            provider,
            "official platform API rejects anonymous requests "
            f"(HTTP 401/400 typed evidence) and no key exists at {path}; "
            f"set {env_name} or create the file to enable this provider",
        )
    return key


def _alias_keys(entity_id: str, aliases: list[str]) -> list[str]:
    return [
        _normalized_title(value)
        for value in [entity_id, *aliases]
        if _normalized_title(value)
    ]


def _observed_at() -> str:
    return datetime.now(UTC).isoformat()


def _popularity(observed_at: str) -> dict[str, Any]:
    return {
        "playCount": None,
        "likeCount": None,
        "commentCount": None,
        "shareCount": None,
        "favoriteCount": None,
        "observedAt": observed_at,
        "samePlatformTopicTimeBucketPercentile": None,
        "rankingEligible": False,
    }


def _pexels_slug_title(page_url: str) -> str:
    slug = urllib.parse.urlsplit(page_url).path.strip("/").split("/")[-1]
    slug = re.sub(r"-\d+$", "", slug)
    return slug.replace("-", " ").strip()


def _best_pexels_file(video: dict[str, Any]) -> dict[str, Any] | None:
    files = [
        row
        for row in (video.get("video_files") or [])
        if isinstance(row, dict)
        and str(row.get("file_type") or "") == "video/mp4"
        and str(row.get("link") or "").startswith("https://")
        and int(row.get("width") or 0) > 0
    ]
    if not files:
        return None
    # Prefer the largest frame at or below full HD; App playback does not
    # need 4K masters and oversized bytes only slow the probe/safety chain.
    bounded = [row for row in files if int(row["width"]) <= 1920]
    pool = bounded or files
    return max(pool, key=lambda row: int(row["width"]))


def discover_pexels_sourced_videos(
    entity_id: str,
    *,
    entity_aliases: list[str],
    limit: int = 15,
    selected_limit: int = 1,
    diagnostics: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Discover exact-entity Pexels video candidates through the official API."""

    api_key = stock_video_api_key("pexels_videos")
    timeout = active_runtime_policy().provider_timeouts.encyclopedia_seconds
    search_terms = list(dict.fromkeys([entity_id, *entity_aliases]))[:4]
    alias_keys = _alias_keys(entity_id, list(entity_aliases))
    funnel = {
        "provider": "pexels_videos",
        "entityId": entity_id,
        "attempted": True,
        "queryCount": len(search_terms),
        "discovered": 0,
        "rejectedMalformed": 0,
        "rejectedByRelevance": 0,
        "rejectedByRights": 0,
        "rejectedByQuality": 0,
        "selectedForAnonymousDownload": 0,
    }
    candidates: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for term in search_terms:
        query = urllib.parse.urlencode({"query": term, "per_page": max(1, limit)})
        search_url = f"https://api.pexels.com/videos/search?{query}"
        response = network_io.fetch_http(
            search_url,
            timeout=timeout,
            headers={"Authorization": api_key},
        )
        if not response.ok:
            continue
        try:
            payload = json.loads(response.body.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            continue
        for video in payload.get("videos") or []:
            if not isinstance(video, dict):
                funnel["rejectedMalformed"] += 1
                continue
            video_id = str(video.get("id") or "")
            if not video_id or video_id in seen_ids:
                continue
            seen_ids.add(video_id)
            funnel["discovered"] += 1
            page_url = str(video.get("url") or "").strip()
            title = _pexels_slug_title(page_url)
            tags = " ".join(
                str(tag) for tag in (video.get("tags") or []) if str(tag).strip()
            )
            combined_key = _normalized_title(f"{title} {tags}")
            if not any(alias in combined_key for alias in alias_keys):
                funnel["rejectedByRelevance"] += 1
                continue
            duration = float(video.get("duration") or 0)
            best = _best_pexels_file(video)
            if (
                best is None
                or not page_url.startswith("https://")
                or duration < _MIN_DURATION_SECONDS
                or duration > _MAX_DURATION_SECONDS
            ):
                funnel["rejectedByQuality"] += 1
                continue
            user = video.get("user") or {}
            creator = str(user.get("name") or "").strip()
            if not creator:
                funnel["rejectedByRights"] += 1
                continue
            observed_at = _observed_at()
            candidates.append(
                {
                    "sourceId": "pexels_videos",
                    "sourceKind": "tourism_video_site",
                    "ordinal": 1,
                    "title": title,
                    "relevance": f"{title} {tags}".strip(),
                    "platform": "Pexels Videos",
                    "assetUrl": str(best["link"]),
                    "sourcePostUrl": page_url,
                    "authorizationProofUrl": page_url,
                    "termsUrl": _PEXELS_TERMS_URL,
                    "rightsBasis": "Pexels License",
                    "originalCreatorName": creator,
                    "attributionText": (
                        f"{title} — {creator} — Pexels License — {page_url}"
                    ),
                    "commercialAuthorizationStatus": "verified",
                    "rightsStatus": "unverified",
                    "rightsIssues": [
                        "downloaded bytes have not yet completed media and rights admission"
                    ],
                    "distributionDecision": "research_allowed",
                    "modelReleaseStatus": "not_required",
                    "propertyReleaseStatus": "not_required",
                    "takedownPolicy": "quwoquan_standard_notice_and_takedown",
                    "anonymousAccess": True,
                    "credentialAssertion": "api_key_discovery_anonymous_asset_download",
                    "downloadMethod": "anonymous_https_direct",
                    "durationSeconds": duration,
                    "sizeBytes": int(best.get("size") or 0),
                    "apiEvidenceUrl": search_url,
                    "popularitySignals": _popularity(observed_at),
                }
            )
    candidates.sort(
        key=lambda item: (
            float(item["durationSeconds"]),
            str(item["sourcePostUrl"]),
        )
    )
    if selected_limit < 1:
        raise ValueError("Pexels video selected_limit must be at least one")
    selected = candidates[:selected_limit]
    funnel["selectedForAnonymousDownload"] = len(selected)
    if diagnostics is not None:
        diagnostics.append(funnel)
    return selected


def discover_pixabay_sourced_videos(
    entity_id: str,
    *,
    entity_aliases: list[str],
    limit: int = 15,
    selected_limit: int = 1,
    diagnostics: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Discover exact-entity Pixabay video candidates through the official API."""

    api_key = stock_video_api_key("pixabay_videos")
    timeout = active_runtime_policy().provider_timeouts.encyclopedia_seconds
    search_terms = list(dict.fromkeys([entity_id, *entity_aliases]))[:4]
    alias_keys = _alias_keys(entity_id, list(entity_aliases))
    funnel = {
        "provider": "pixabay_videos",
        "entityId": entity_id,
        "attempted": True,
        "queryCount": len(search_terms),
        "discovered": 0,
        "rejectedMalformed": 0,
        "rejectedByRelevance": 0,
        "rejectedByRights": 0,
        "rejectedByQuality": 0,
        "selectedForAnonymousDownload": 0,
    }
    candidates: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for term in search_terms:
        query = urllib.parse.urlencode(
            {"key": api_key, "q": term, "per_page": max(3, limit)}
        )
        search_url = f"https://pixabay.com/api/videos/?{query}"
        response = network_io.fetch_http(search_url, timeout=timeout)
        if not response.ok:
            continue
        try:
            payload = json.loads(response.body.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            continue
        for video in payload.get("hits") or []:
            if not isinstance(video, dict):
                funnel["rejectedMalformed"] += 1
                continue
            video_id = str(video.get("id") or "")
            if not video_id or video_id in seen_ids:
                continue
            seen_ids.add(video_id)
            funnel["discovered"] += 1
            tags = str(video.get("tags") or "")
            page_url = str(video.get("pageURL") or "").strip()
            combined_key = _normalized_title(tags)
            if not any(alias in combined_key for alias in alias_keys):
                funnel["rejectedByRelevance"] += 1
                continue
            duration = float(video.get("duration") or 0)
            files = video.get("videos") or {}
            best = None
            for quality in ("large", "medium", "small"):
                row = files.get(quality)
                if (
                    isinstance(row, dict)
                    and str(row.get("url") or "").startswith("https://")
                    and int(row.get("width") or 0) > 0
                ):
                    best = row
                    break
            if (
                best is None
                or not page_url.startswith("https://")
                or duration < _MIN_DURATION_SECONDS
                or duration > _MAX_DURATION_SECONDS
            ):
                funnel["rejectedByQuality"] += 1
                continue
            creator = str(video.get("user") or "").strip()
            if not creator:
                funnel["rejectedByRights"] += 1
                continue
            observed_at = _observed_at()
            candidates.append(
                {
                    "sourceId": "pixabay_videos",
                    "sourceKind": "tourism_video_site",
                    "ordinal": 1,
                    "title": tags or f"pixabay video {video_id}",
                    "relevance": tags,
                    "platform": "Pixabay Videos",
                    "assetUrl": str(best["url"]),
                    "sourcePostUrl": page_url,
                    "authorizationProofUrl": page_url,
                    "termsUrl": _PIXABAY_TERMS_URL,
                    "rightsBasis": "Pixabay Content License",
                    "originalCreatorName": creator,
                    "attributionText": (
                        f"{tags} — {creator} — Pixabay Content License — {page_url}"
                    ),
                    "commercialAuthorizationStatus": "verified",
                    "rightsStatus": "unverified",
                    "rightsIssues": [
                        "downloaded bytes have not yet completed media and rights admission"
                    ],
                    "distributionDecision": "research_allowed",
                    "modelReleaseStatus": "not_required",
                    "propertyReleaseStatus": "not_required",
                    "takedownPolicy": "quwoquan_standard_notice_and_takedown",
                    "anonymousAccess": True,
                    "credentialAssertion": "api_key_discovery_anonymous_asset_download",
                    "downloadMethod": "anonymous_https_direct",
                    "durationSeconds": duration,
                    "sizeBytes": int(best.get("size") or 0),
                    "apiEvidenceUrl": (
                        "https://pixabay.com/api/videos/?"
                        + urllib.parse.urlencode(
                            {"key": "***", "q": term, "per_page": max(3, limit)}
                        )
                    ),
                    "popularitySignals": _popularity(observed_at),
                }
            )
    candidates.sort(
        key=lambda item: (
            float(item["durationSeconds"]),
            str(item["sourcePostUrl"]),
        )
    )
    if selected_limit < 1:
        raise ValueError("Pixabay video selected_limit must be at least one")
    selected = candidates[:selected_limit]
    funnel["selectedForAnonymousDownload"] = len(selected)
    if diagnostics is not None:
        diagnostics.append(funnel)
    return selected


STOCK_VIDEO_DISCOVERIES = {
    "pexels_videos": discover_pexels_sourced_videos,
    "pixabay_videos": discover_pixabay_sourced_videos,
}


__all__ = [
    "PROVIDER_CREDENTIAL_MISSING",
    "STOCK_VIDEO_DISCOVERIES",
    "StockVideoProviderCredentialMissing",
    "discover_pexels_sourced_videos",
    "discover_pixabay_sourced_videos",
    "stock_video_api_key",
]
