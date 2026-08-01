from datetime import datetime, timezone

import pytest

from internal.recommendation.ranked_recommendation_window.domain.model import (
    RankedCandidate,
    RankedRecommendationWindow,
    RankingResult,
)
from internal.recommendation.ranked_recommendation_window.infrastructure.redis_store import (
    RedisWindowStore,
)


class _Redis:
    def __init__(self) -> None:
        self.values = {}
        self.sets = {}
        self.expirations = []

    def set(self, key, value, *, ex, nx):
        if nx and key in self.values:
            return False
        self.values[key] = value
        self.expirations.append((key, ex))
        return True

    def get(self, key):
        return self.values.get(key)

    def sadd(self, key, *values):
        target = self.sets.setdefault(key, set())
        before = len(target)
        target.update(values)
        return len(target) - before

    def srem(self, key, *values):
        target = self.sets.get(key, set())
        before = len(target)
        target.difference_update(values)
        return before - len(target)

    def smembers(self, key):
        return set(self.sets.get(key, set()))

    def expire(self, key, seconds):
        self.expirations.append((key, seconds))
        return True

    def delete(self, *keys):
        removed = 0
        for key in keys:
            if key in self.values:
                del self.values[key]
                removed += 1
            if key in self.sets:
                del self.sets[key]
                removed += 1
        return removed


def _window(*, item_snapshot=None) -> RankedRecommendationWindow:
    now = datetime(2026, 7, 31, 12, tzinfo=timezone.utc)
    return RankedRecommendationWindow.create(
        window_id="window-001",
        subject_id="persona-001",
        scenario="content_feed",
        request_digest="request-digest-001",
        ranking=RankingResult(
            model_bucket="model",
            model_channel="champion",
            model_release_id="release-001",
            policy_digest="sha256:policy-001",
            feature_snapshot_at=now,
            ranking_snapshot_digest="ranking-digest-001",
            user_feature_snapshot={"engagement": 0.7},
            candidates=(
                RankedCandidate(
                    content_id="post-001",
                    score=0.8,
                    feature_snapshot_digest="feature-digest-001",
                    item_feature_snapshot=item_snapshot or {"quality": 0.8},
                ),
            ),
        ),
        now=now,
    )


def test_store_round_trips_immutable_attribution_without_sliding_window_ttl() -> None:
    redis = _Redis()
    store = RedisWindowStore(redis)
    persisted = store.create_or_get(_window())

    expiration_calls_before_read = list(redis.expirations)
    restored = store.get(persisted.window_id)

    assert restored == persisted
    assert restored.items[0].item_feature_snapshot == {"quality": 0.8}
    assert redis.expirations == expiration_calls_before_read


def test_subject_privacy_index_erases_every_active_window_immediately() -> None:
    redis = _Redis()
    store = RedisWindowStore(redis)
    window = store.create_or_get(_window())

    assert store.erase_subject("persona-001") == 1
    assert store.get(window.window_id) is None
    assert RedisWindowStore._subject_key("persona-001") not in redis.sets


def test_store_rejects_unbounded_encoded_window() -> None:
    redis = _Redis()
    store = RedisWindowStore(redis)
    oversized = _window(
        item_snapshot={"payload": "x" * RedisWindowStore.MAX_WINDOW_PAYLOAD_BYTES}
    )

    with pytest.raises(ValueError, match="2 MiB"):
        store.create_or_get(oversized)
    assert redis.values == {}
    assert redis.sets == {}
