"""Derived provider-mix and video-readiness metrics for scale source pools."""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Mapping
from typing import Any

_PIN_ALIASES = frozenset({"pinterest", "pinterest.com", "www.pinterest.com"})
_TUCHONG_ALIASES = frozenset(
    {
        "tuchong",
        "tuchong.com",
        "www.tuchong.com",
        "图虫",
        "图虫社区",
        "图虫创意",
        "tuchong stock",
        "tuchong_stock_authorized",
    }
)


def normalized_provider(value: object) -> str:
    provider = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    provider = re.sub(r"\s+", " ", provider)
    if provider in _PIN_ALIASES:
        return "pinterest"
    if provider in _TUCHONG_ALIASES:
        return "tuchong"
    return provider


def video_popularity_ready(candidate: Mapping[str, Any]) -> bool:
    readiness = candidate.get("videoReadiness")
    if not isinstance(readiness, Mapping):
        return False
    for field in (
        "playCount",
        "likeCount",
        "commentCount",
        "shareCount",
        "favoriteCount",
    ):
        value = readiness.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return False
    if not str(readiness.get("observedAt") or "").strip():
        return False
    percentile = readiness.get("popularityPercentile")
    if (
        isinstance(percentile, bool)
        or not isinstance(percentile, (int, float))
        or not 0 <= float(percentile) <= 1
    ):
        return False
    comparison = readiness.get("comparisonBucket")
    if not isinstance(comparison, Mapping):
        return False
    if normalized_provider(comparison.get("provider")) != normalized_provider(
        candidate.get("provider")
    ):
        return False
    if any(
        not str(comparison.get(field) or "").strip()
        for field in ("topic", "timeBucket")
    ):
        return False
    count = comparison.get("candidateCount")
    return not isinstance(count, bool) and isinstance(count, int) and count >= 2


def image_mix(counts: Counter[str], *, total: int) -> dict[str, Any]:
    pinterest = counts["pinterest"]
    tuchong = counts["tuchong"]
    professional = pinterest + tuchong
    largest_other = max(
        (count for provider, count in counts.items() if provider != "pinterest"),
        default=0,
    )
    dominant = sorted(
        provider for provider, count in counts.items() if count * 10 > total * 7
    )
    rows = [
        {
            "provider": provider,
            "candidateCount": count,
            "candidateRatio": round(count / total, 6) if total else 0.0,
        }
        for provider, count in sorted(counts.items())
    ]
    largest_provider = (
        min(
            provider
            for provider, count in counts.items()
            if count == max(counts.values())
        )
        if counts
        else ""
    )
    return {
        "totalCandidateCount": total,
        "pinterestCandidateCount": pinterest,
        "tuchongCandidateCount": tuchong,
        "pinterestTuchongCandidateRatio": (
            round(professional / total, 6) if total else 0.0
        ),
        "largestProvider": largest_provider,
        "maxProviderCandidateRatio": max(
            (round(count / total, 6) for count in counts.values()),
            default=0.0,
        ),
        "providerCandidateCounts": rows,
        "policyObservations": {
            "pinterestUniqueLargest": bool(pinterest > largest_other),
            "tuchongPresent": bool(tuchong),
            "pinterestTuchongAtLeastHalf": bool(
                total and professional * 2 >= total
            ),
            "providerAboveSeventyPercent": dominant,
        },
    }


__all__ = ["image_mix", "normalized_provider", "video_popularity_ready"]
