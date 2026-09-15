from datetime import datetime, timezone

import pytest

from internal.recommendation.recommendation_candidate_index_view.infrastructure.mongo_store import (
    MongoCandidateIndexStore,
)


def test_candidate_ranking_audiences_share_one_content_feed_projection() -> None:
    now = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)
    assert MongoCandidateIndexStore.ranking_query("content_feed") == {
        "sourcePartition": "ordinary",
        "scenario": "content_feed",
        "accountRestricted": {"$ne": True},
    }
    assert MongoCandidateIndexStore.ranking_query("premium_stream", now=now) == {
        "sourcePartition": "ordinary",
        "scenario": "content_feed",
        "accountRestricted": {"$ne": True},
        "premiumEligible": True,
        "premiumExpiresAt": {"$gt": now},
    }
    assert MongoCandidateIndexStore.ranking_query("travel_photography") == {
        "sourcePartition": "ordinary",
        "scenario": "content_feed",
        "accountRestricted": {"$ne": True},
        "contentVertical": "travel_photography",
    }


def test_candidate_ranking_rejects_an_unowned_audience() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        MongoCandidateIndexStore.ranking_query("following")
