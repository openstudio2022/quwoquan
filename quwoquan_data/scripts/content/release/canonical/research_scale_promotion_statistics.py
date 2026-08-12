"""Truthful non-blocking statistics for cumulative scale promotion."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.research_scale_source_mix import (
    ResearchScaleSourceMixError,
    validate_research_scale_source_mix,
)
from content.release.canonical.research_scale_video_popularity import (
    VIDEO_POPULARITY_EVIDENCE_ERROR,
    VIDEO_POPULARITY_SIGNALS,
    ResearchScaleVideoPopularityError,
    collect_m100_video_popularity_observations,
)


def rate_statistic(numerator: int, denominator: int) -> dict[str, int | float]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": round(numerator / denominator, 6) if denominator else 0.0,
    }


def article_media_statistics(
    coverage: object, *, expected_article_count: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(coverage, Mapping):
        raise ValueError("release article media statistics are missing")
    values: dict[str, int] = {}
    for key in ("articleCount", "illustratedCount", "textOnlyCount"):
        value = coverage.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"articleMediaCoverage.{key} must be non-negative")
        values[key] = value
    illustrated = rate_statistic(values["illustratedCount"], values["articleCount"])
    text_only = rate_statistic(values["textOnlyCount"], values["articleCount"])
    if (
        values["articleCount"] != expected_article_count
        or values["illustratedCount"] + values["textOnlyCount"]
        != values["articleCount"]
        or float(coverage.get("illustratedRate") or 0.0) != illustrated["rate"]
        or float(coverage.get("textOnlyRate") or 0.0) != text_only["rate"]
    ):
        raise ValueError("release article coverage statistics drift")
    return (
        {"statistical": True, "nonBlocking": True, **illustrated},
        {"statistical": True, "nonBlocking": True, **text_only},
    )


def automatic_recovery_statistics(
    fault_evidence: Mapping[str, Any], *, target_rate: float
) -> dict[str, Any]:
    eligible = fault_evidence.get("recoveryEligibleCount")
    recovered = fault_evidence.get("automaticRecoveredCount")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in (eligible, recovered)
    ):
        raise ValueError("automatic recovery counts must be non-negative")
    assert isinstance(eligible, int) and isinstance(recovered, int)
    status = "NOT_EXERCISED" if eligible == 0 else "MEASURED"
    rate = round(recovered / eligible, 6) if eligible else None
    raw_rate = fault_evidence.get("automaticRecoveryRate")
    if (
        recovered > eligible
        or (eligible == 0 and raw_rate is not None)
        or (
            eligible > 0
            and (
                isinstance(raw_rate, bool)
                or not isinstance(raw_rate, (int, float))
                or float(raw_rate) != rate
            )
        )
        or fault_evidence.get("automaticRecoveryStatus") != status
    ):
        raise ValueError("automatic recovery statistics drift")
    return {
        "statistical": True,
        "nonBlocking": True,
        "status": status,
        "eligibleCount": eligible,
        "automaticCount": recovered,
        "targetRate": target_rate,
        "rate": rate,
    }


def video_popularity_statistics(
    release: Path, *, expected_video_count: int
) -> dict[str, Any]:
    try:
        observations = collect_m100_video_popularity_observations(
            release,
            expected_video_count=expected_video_count,
        )
        denominator = len(observations)
        return {
            "signalAvailability": [
                {
                    "signal": signal,
                    **rate_statistic(
                        sum(row[field] is not None for row in observations),
                        denominator,
                    ),
                }
                for signal, field in VIDEO_POPULARITY_SIGNALS
            ],
            "rankingCoverage": rate_statistic(
                sum(row["rankingEligible"] is True for row in observations),
                denominator,
            ),
            "observations": observations,
            "observationIssues": [],
        }
    except (OSError, ResearchScaleVideoPopularityError, TypeError, ValueError) as exc:
        return {
            "signalAvailability": [
                {"signal": signal, **rate_statistic(0, expected_video_count)}
                for signal, _field in VIDEO_POPULARITY_SIGNALS
            ],
            "rankingCoverage": rate_statistic(0, expected_video_count),
            "observations": [],
            "observationIssues": [f"{VIDEO_POPULARITY_EVIDENCE_ERROR}: {exc}"],
        }


def professional_image_source_mix_statistics(
    admission: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        result = validate_research_scale_source_mix(admission)
    except ResearchScaleSourceMixError as exc:
        return {
            "statistical": True,
            "nonBlocking": True,
            "acceptedImageAssetCount": 0,
            "originalAssetClosureCount": 0,
            "pinterestAcceptedAssetCount": 0,
            "tuchongAcceptedAssetCount": 0,
            "pinterestTuchongAcceptedAssetCount": 0,
            "pinterestTuchongAcceptedAssetRatio": 0.0,
            "largestProvider": "",
            "maxProviderAcceptedAssetRatio": 0.0,
            "providerAssetCounts": [],
            "policyObservations": {
                "pinterestUniqueLargest": False,
                "tuchongPresent": False,
                "pinterestTuchongAtLeastHalf": False,
                "providerAboveSeventyPercent": [],
            },
            "observationIssues": list(exc.issues),
        }
    result.update(
        {
            "statistical": True,
            "nonBlocking": True,
            "observationIssues": [],
        }
    )
    return result


__all__ = [
    "article_media_statistics",
    "automatic_recovery_statistics",
    "professional_image_source_mix_statistics",
    "rate_statistic",
    "video_popularity_statistics",
]
