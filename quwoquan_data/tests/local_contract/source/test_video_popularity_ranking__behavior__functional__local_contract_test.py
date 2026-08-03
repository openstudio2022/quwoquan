from __future__ import annotations

from content.source.research.auto_plan_video import (
    rank_video_candidates_by_popularity,
)


def _candidate(
    candidate_id: str,
    *,
    percentile: float | None,
    likes: int = 0,
    comments: int = 0,
    shares: int = 0,
    favorites: int = 0,
) -> dict[str, object]:
    return {
        "candidateId": candidate_id,
        "popularitySignals": {
            "playCount": None,
            "likeCount": likes,
            "commentCount": comments,
            "shareCount": shares,
            "favoriteCount": favorites,
            "observedAt": "2026-08-02T00:00:00Z",
            "samePlatformTopicTimeBucketPercentile": percentile,
            "rankingEligible": percentile is not None,
        },
    }


def test_video_popularity_ranking_prefers_comparable_percentile_then_engagement() -> None:
    ranked = rank_video_candidates_by_popularity(
        [
            _candidate("missing", percentile=None, likes=1_000_000),
            _candidate("lower", percentile=0.82, likes=1_000),
            _candidate("higher-low-engagement", percentile=0.95, likes=10),
            _candidate(
                "higher-high-engagement",
                percentile=0.95,
                likes=10,
                comments=4,
                shares=3,
                favorites=2,
            ),
        ]
    )

    assert [row["candidateId"] for row in ranked] == [
        "higher-high-engagement",
        "higher-low-engagement",
        "lower",
        "missing",
    ]


def test_video_popularity_ranking_does_not_invent_missing_metrics() -> None:
    candidate = _candidate("missing", percentile=None)

    ranked = rank_video_candidates_by_popularity([candidate])

    assert ranked == [candidate]
    assert ranked[0]["popularitySignals"][
        "samePlatformTopicTimeBucketPercentile"
    ] is None
