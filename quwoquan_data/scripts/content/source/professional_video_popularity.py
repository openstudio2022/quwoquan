"""Comparable-bucket popularity ranking for acquired professional videos."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

_COUNT_FIELDS = (
    "playCount",
    "likeCount",
    "commentCount",
    "shareCount",
    "favoriteCount",
)
_WEIGHTS = {
    "playCount": 1,
    "likeCount": 20,
    "commentCount": 30,
    "shareCount": 50,
    "favoriteCount": 25,
}


def initial_popularity_signals(raw: dict[str, Any]) -> dict[str, Any]:
    score = popularity_score(raw)
    return {
        **{field: raw.get(field) for field in _COUNT_FIELDS},
        "observedAt": str(raw.get("observedAt") or ""),
        "provider": str(raw.get("provider") or ""),
        "topic": str(raw.get("topic") or ""),
        "timeBucket": str(raw.get("timeBucket") or ""),
        "popularityScore": score,
        "popularityPercentile": None,
        "rankingEligible": False,
        "rankingIneligibleReason": "not_evaluated",
        "comparisonCandidateCount": 0,
    }


def popularity_score(signals: dict[str, Any]) -> int | None:
    values: dict[str, int] = {}
    for field in _COUNT_FIELDS:
        value = signals.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return None
        values[field] = value
    return sum(values[field] * _WEIGHTS[field] for field in _COUNT_FIELDS)


def apply_popularity_percentiles(rows: list[dict[str, Any]]) -> None:
    """Mutate receipt rows only when at least two accepted peers are comparable."""
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        signals = row["popularitySignals"]
        if row.get("distributionDecision") not in {
            "research_allowed",
            "commercial_allowed",
        }:
            signals["rankingIneligibleReason"] = "asset_not_accepted"
            continue
        if signals.get("popularityScore") is None:
            signals["rankingIneligibleReason"] = "incomplete_popularity_signals"
            continue
        key = (
            str(signals["provider"]),
            str(signals["topic"]),
            str(signals["timeBucket"]),
        )
        groups[key].append(row)

    for group in groups.values():
        count = len(group)
        if count < 2:
            group[0]["popularitySignals"].update(
                rankingIneligibleReason="insufficient_comparable_candidates",
                comparisonCandidateCount=count,
            )
            continue
        scores = [int(row["popularitySignals"]["popularityScore"]) for row in group]
        for row, score in zip(group, scores):
            lower = sum(candidate < score for candidate in scores)
            equal = sum(candidate == score for candidate in scores)
            percentile = (lower + (equal - 1) / 2) / (count - 1)
            row["popularitySignals"].update(
                popularityPercentile=round(percentile, 6),
                rankingEligible=True,
                rankingIneligibleReason="",
                comparisonCandidateCount=count,
            )


def popularity_sort_key(candidate: dict[str, Any]) -> tuple[int, float, float, str]:
    signals = candidate.get("popularitySignals")
    payload = signals if isinstance(signals, dict) else {}
    eligible = payload.get("rankingEligible") is True
    percentile = payload.get("popularityPercentile")
    score = payload.get("popularityScore")
    return (
        0 if eligible else 1,
        -float(percentile) if eligible and isinstance(percentile, (int, float)) else 0.0,
        -float(score) if eligible and isinstance(score, (int, float)) else 0.0,
        str(candidate.get("professionalAssetId") or candidate.get("assetId") or ""),
    )


__all__ = [
    "apply_popularity_percentiles",
    "initial_popularity_signals",
    "popularity_score",
    "popularity_sort_key",
]
