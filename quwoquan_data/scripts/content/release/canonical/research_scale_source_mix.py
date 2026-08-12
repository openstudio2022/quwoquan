"""Professional image-provider observations for research scale milestones."""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

SOURCE_POOL_SHORTFALL = "DATA.SOURCE.POOL_SHORTFALL"
_ACCEPTED_DECISIONS = frozenset({"research_allowed", "commercial_allowed"})
_PINTEREST_ALIASES = frozenset(
    {
        "pinterest",
        "pinterest.com",
        "www.pinterest.com",
    }
)
_TUCHONG_ALIASES = frozenset(
    {
        "tuchong",
        "tuchong.com",
        "www.tuchong.com",
        "tuchong stock",
        "tuchong_stock_authorized",
        "图虫",
        "图虫社区",
        "图虫创意",
    }
)
_WIKIMEDIA_ALIASES = frozenset(
    {"wikimedia_commons", "wikimedia commons", "wikimedia commons image"}
)
_THUMBNAIL_MARKERS = (
    "thumbnail",
    "thumb",
    "preview",
    "compressed",
    "236x",
    "474x",
    "736x",
    "75x75",
    "140x140",
    "600x600",
    "r_720x480",
)


class ResearchScaleSourceMixError(ValueError):
    """Typed milestone blocker for an insufficient professional source pool."""

    code = SOURCE_POOL_SHORTFALL

    def __init__(self, issues: list[str] | tuple[str, ...]) -> None:
        normalized = tuple(str(issue).strip() for issue in issues if str(issue).strip())
        if not normalized:
            raise ValueError("source mix error requires at least one issue")
        self.issues = normalized
        super().__init__(f"{self.code}: " + "; ".join(normalized))


def _normalized_provider(value: object) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    normalized = re.sub(r"\s+", " ", normalized)
    if normalized in _PINTEREST_ALIASES:
        return "pinterest"
    if normalized in _TUCHONG_ALIASES:
        return "tuchong"
    if normalized in _WIKIMEDIA_ALIASES:
        return "wikimedia_commons"
    return normalized


def _provider(asset: Mapping[str, Any], *, asset_id: str) -> str:
    values = [
        _normalized_provider(asset.get(field))
        for field in ("provider", "platform")
        if str(asset.get(field) or "").strip()
    ]
    if not values:
        raise ResearchScaleSourceMixError(
            [f"image asset {asset_id} lacks provider/platform"]
        )
    if len(set(values)) != 1:
        raise ResearchScaleSourceMixError(
            [f"image asset {asset_id} provider/platform identity drift"]
        )
    return values[0]


def _is_image_post(object_ref: object) -> bool:
    normalized = str(object_ref or "").strip().strip("/")
    return normalized == "posts/image" or normalized.startswith("posts/image/")


def _original_closure_issues(asset: Mapping[str, Any], *, asset_id: str) -> list[str]:
    issues: list[str] = []
    source_url = str(asset.get("sourceUrl") or "").strip()
    parsed = urlsplit(source_url)
    content_sha256 = str(asset.get("contentSha256") or "").strip()
    if not asset_id:
        issues.append("image assetId is missing")
    if parsed.scheme != "https" or not parsed.netloc:
        issues.append(f"image asset {asset_id or '<unknown>'} lacks HTTPS sourceUrl")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", content_sha256):
        issues.append(f"image asset {asset_id or '<unknown>'} lacks contentSha256")
    if not isinstance(asset.get("generated"), bool):
        issues.append(f"image asset {asset_id or '<unknown>'} lacks generated flag")
    elif bool(asset.get("generated")):
        issues.append(f"image asset {asset_id or '<unknown>'} is generated")
    if str(asset.get("creator") or "").strip().casefold() in {"", "unknown"}:
        issues.append(f"image asset {asset_id or '<unknown>'} lacks creator")
    url_evidence = f"{parsed.path}?{parsed.query}".casefold()
    if any(marker in url_evidence for marker in _THUMBNAIL_MARKERS):
        issues.append(f"image asset {asset_id or '<unknown>'} is a thumbnail/preview")
    return issues


def _ratio(count: int, total: int) -> float:
    return round(count / total, 6) if total else 0.0


def validate_research_scale_source_mix(
    asset_admission: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate and project the accepted ``posts/image`` provider mix.

    The release admission is already the immutable safety/quality boundary.
    This helper revalidates the projected physical-original proof fields and
    rejects thumbnail-shaped URLs before a scale milestone consumes the mix.
    """

    raw_assets = asset_admission.get("assets")
    if not isinstance(raw_assets, list):
        raise ResearchScaleSourceMixError(["release asset admission assets is invalid"])
    counts: Counter[str] = Counter()
    original_count = 0
    closure_issues: list[str] = []
    for raw in raw_assets:
        if not isinstance(raw, Mapping):
            closure_issues.append("release asset admission contains a non-object asset")
            continue
        if not _is_image_post(raw.get("objectRef")):
            continue
        if (
            str(raw.get("acquisitionStatus") or "").strip() != "acquired"
            or str(raw.get("distributionDecision") or "").strip()
            not in _ACCEPTED_DECISIONS
        ):
            continue
        asset_id = str(raw.get("assetId") or "").strip()
        issues = _original_closure_issues(raw, asset_id=asset_id)
        if issues:
            closure_issues.extend(issues)
            continue
        provider = _provider(raw, asset_id=asset_id)
        if not provider:
            closure_issues.append(f"image asset {asset_id} provider is empty")
            continue
        counts[provider] += 1
        original_count += 1
    if closure_issues:
        raise ResearchScaleSourceMixError(closure_issues)
    total = sum(counts.values())
    pinterest = counts["pinterest"]
    tuchong = counts["tuchong"]
    professional = pinterest + tuchong
    provider_rows = [
        {
            "provider": provider,
            "acceptedAssetCount": count,
            "acceptedAssetRatio": _ratio(count, total),
        }
        for provider, count in sorted(counts.items())
    ]
    if total < 1:
        raise ResearchScaleSourceMixError(
            ["accepted posts/image asset pool is empty"]
        )
    largest_other = max(
        (count for provider, count in counts.items() if provider != "pinterest"),
        default=0,
    )
    dominant = [
        provider
        for provider, count in counts.items()
        if count * 10 > total * 7
    ]
    largest_provider = min(
        provider for provider, count in counts.items()
        if count == max(counts.values())
    )
    return {
        "acceptedImageAssetCount": total,
        "originalAssetClosureCount": original_count,
        "pinterestAcceptedAssetCount": pinterest,
        "tuchongAcceptedAssetCount": tuchong,
        "pinterestTuchongAcceptedAssetCount": professional,
        "pinterestTuchongAcceptedAssetRatio": _ratio(professional, total),
        "largestProvider": largest_provider,
        "maxProviderAcceptedAssetRatio": max(
            (_ratio(count, total) for count in counts.values()),
            default=0.0,
        ),
        "providerAssetCounts": provider_rows,
        "policyObservations": {
            "pinterestUniqueLargest": pinterest > largest_other,
            "tuchongPresent": tuchong > 0,
            "pinterestTuchongAtLeastHalf": professional * 2 >= total,
            "providerAboveSeventyPercent": sorted(dominant),
        },
    }


__all__ = [
    "SOURCE_POOL_SHORTFALL",
    "ResearchScaleSourceMixError",
    "validate_research_scale_source_mix",
]
