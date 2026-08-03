from datetime import datetime, timezone

import pytest

from internal.recommendation.ranked_recommendation_window.domain.model import (
    RecommendationObjectCard,
    RankedCandidate,
    RankedRecommendationWindow,
    RankingResult,
)
from internal.recommendation.ranked_recommendation_window.infrastructure.redis_store import (
    RedisWindowStore,
    WindowIdentityConflictError,
    WindowShardByteQuotaError,
    WindowShardRecordQuotaError,
)


_NOW = datetime(2026, 7, 31, 12, 1, tzinfo=timezone.utc)


class _Redis:
    """Bounded semantic double for store orchestration; real Lua has API coverage."""

    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.indexes: dict[str, dict[str, int]] = {}
        self.metadata: dict[str, dict[str, str]] = {}
        self.now_us = int(_NOW.timestamp() * 1_000_000)
        self.mutations = 0

    def get(self, key):
        return self.values.get(key)

    def zrange(self, key, start, end):
        ordered = sorted(
            self.indexes.get(key, {}),
            key=lambda member: (self.indexes[key][member], member),
        )
        return ordered[start : end + 1]

    def eval(self, script, numkeys, *keys_and_args):
        keys = [str(value) for value in keys_and_args[:numkeys]]
        args = keys_and_args[numkeys:]
        if "bounded subject erase policy" in script:
            return self._erase(keys, args)
        return self._create(keys, args)

    def _clean(self, index_key: str, metadata_key: str) -> None:
        index = self.indexes.setdefault(index_key, {})
        metadata = self.metadata.setdefault(metadata_key, {})
        for key, expires_at_us in list(index.items()):
            if expires_at_us <= self.now_us or key not in self.values:
                index.pop(key, None)
                metadata.pop(key, None)
                if expires_at_us <= self.now_us:
                    self.values.pop(key, None)

    def _create(self, keys, args):
        record_key, index_key, metadata_key = keys[:3]
        payload = args[0]
        payload = payload if isinstance(payload, bytes) else str(payload).encode()
        ttl_ms = int(args[1])
        owner = str(args[2])
        max_owner = int(args[3])
        max_records = int(args[4])
        max_bytes = int(args[5])
        declared = {record_key, *keys[3:]}
        indexed = self.zrange(index_key, 0, max_records)
        if len(indexed) > max_records:
            return [b"", -4, 0, len(indexed), 0]
        if any(key not in declared for key in indexed):
            return [b"", -1, 0, len(indexed), 0]
        self._clean(index_key, metadata_key)
        index = self.indexes.setdefault(index_key, {})
        metadata = self.metadata.setdefault(metadata_key, {})
        live = self.zrange(index_key, 0, max_records)
        live_bytes = sum(int(metadata[key].split(":", 1)[1]) for key in live)
        if record_key in self.values:
            return [self.values[record_key], 0, 0, len(live), live_bytes]
        owner_records = [
            key for key in live if metadata[key].split(":", 1)[0] == owner
        ]
        evict_count = max(len(owner_records) - max_owner + 1, 0)
        victims = owner_records[:evict_count]
        projected_records = len(live) - len(victims) + 1
        projected_bytes = (
            live_bytes
            - sum(int(metadata[key].split(":", 1)[1]) for key in victims)
            + len(payload)
        )
        if projected_records > max_records:
            return [b"", -2, 0, len(live), live_bytes]
        if projected_bytes > max_bytes:
            return [b"", -3, 0, len(live), live_bytes]
        for key in victims:
            self.values.pop(key, None)
            index.pop(key, None)
            metadata.pop(key, None)
        self.values[record_key] = payload
        index[record_key] = self.now_us + ttl_ms * 1000
        metadata[record_key] = f"{owner}:{len(payload)}"
        self.mutations += 1
        return [b"", 1, len(victims), projected_records, projected_bytes]

    def _erase(self, keys, args):
        index_key, metadata_key = keys[:2]
        max_records = int(args[0])
        owner = str(args[1])
        declared = set(keys[2:])
        indexed = self.zrange(index_key, 0, max_records)
        if len(indexed) > max_records:
            return [-4, 0]
        if any(key not in declared for key in indexed):
            return [-1, 0]
        self._clean(index_key, metadata_key)
        index = self.indexes.setdefault(index_key, {})
        metadata = self.metadata.setdefault(metadata_key, {})
        deleted = 0
        for key in list(self.zrange(index_key, 0, max_records)):
            value = metadata.get(key)
            if value is None or ":" not in value:
                return [-4, deleted]
            if value.split(":", 1)[0] != owner:
                continue
            deleted += int(key in self.values)
            self.values.pop(key, None)
            index.pop(key, None)
            metadata.pop(key, None)
        self.mutations += 1
        return [0, deleted]


def _window(
    *,
    window_id: str = "window-001",
    subject_id: str = "persona-001",
    item_snapshot=None,
) -> RankedRecommendationWindow:
    created_at = datetime(2026, 7, 31, 12, tzinfo=timezone.utc)
    return RankedRecommendationWindow.create(
        window_id=window_id,
        subject_id=subject_id,
        scenario="content_feed",
        request_digest=f"request-{window_id}",
        ranking=RankingResult(
            model_bucket="model",
            model_channel="champion",
            model_release_id="release-001",
            policy_digest="sha256:2f8a57089882835170b77224eb7ef2db78c5d5d26ae4637b210dbe195713f094",
            feature_snapshot_at=created_at,
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
            object_cards=(
                RecommendationObjectCard(
                    object_kind="entity_homepage",
                    object_id="homepage-001",
                    title="公开对象页",
                    subtitle="公开副标题",
                    cover_url=None,
                    tag_refs=("旅行",),
                    reason_key="affinity",
                    recall_path="entity_card_affinity",
                ),
            ),
        ),
        now=created_at,
    )


def _store(redis: _Redis, **quota) -> RedisWindowStore:
    return RedisWindowStore(redis, now=lambda: _NOW, **quota)


def test_store_uses_privacy_safe_same_slot_keys_and_non_sliding_reads() -> None:
    redis = _Redis()
    store = _store(redis)
    persisted = store.create_or_get(_window())

    assert len(redis.values) == 1
    key = next(iter(redis.values))
    assert key.startswith("rec:ranked_feed_window:{rfw-")
    assert ":persona-001:" not in key
    assert "recommendation:ranked-window" not in key
    tag = key[key.index("{") : key.index("}") + 1]
    assert next(iter(redis.indexes)).endswith(tag)
    assert next(iter(redis.metadata)).endswith(tag)

    mutations_before_read = redis.mutations
    restored = store.get("persona-001", persisted.window_id)
    assert restored == persisted
    assert restored.items[0].item_feature_snapshot == {"quality": 0.8}
    assert restored.object_cards[0].object_id == "homepage-001"
    assert redis.mutations == mutations_before_read
    assert store.get("persona-other", persisted.window_id) is None


def test_subject_erasure_scans_only_one_bounded_shard_and_preserves_other_owner() -> None:
    redis = _Redis()
    store = _store(redis, quota_shard_count=1)
    first = store.create_or_get(_window(window_id="window-first"))
    other = store.create_or_get(
        _window(window_id="window-other", subject_id="persona-other")
    )

    assert store.erase_subject("persona-001") == 1
    assert store.get("persona-001", first.window_id) is None
    assert store.get("persona-other", other.window_id) == other
    assert all("persona-001" not in key for key in redis.indexes)


def test_store_evicts_only_oldest_window_of_same_owner_at_eight() -> None:
    redis = _Redis()
    store = _store(redis, quota_shard_count=1)
    windows = [
        store.create_or_get(_window(window_id=f"window-{index:02d}"))
        for index in range(9)
    ]

    assert store.get("persona-001", windows[0].window_id) is None
    assert all(
        store.get("persona-001", window.window_id) == window
        for window in windows[1:]
    )


def test_store_rejects_shard_record_and_byte_caps_without_evicting_other_owner() -> None:
    redis = _Redis()
    store = _store(
        redis,
        quota_shard_count=1,
        maximum_live_records_per_shard=8,
    )
    owners = [
        store.create_or_get(
            _window(window_id=f"window-{index}", subject_id=f"persona-{index}")
        )
        for index in range(8)
    ]
    with pytest.raises(WindowShardRecordQuotaError):
        store.create_or_get(_window(window_id="window-overflow", subject_id="overflow"))
    assert all(store.get(window.subject_id, window.window_id) == window for window in owners)

    byte_redis = _Redis()
    probe = _store(byte_redis, quota_shard_count=1)
    first = _window(window_id="window-byte-first", subject_id="byte-first")
    first_size = len(probe._encode_window(first))
    byte_store = _store(
        byte_redis,
        quota_shard_count=1,
        maximum_live_bytes_per_shard=first_size + 32,
    )
    byte_store.create_or_get(first)
    with pytest.raises(WindowShardByteQuotaError):
        byte_store.create_or_get(
            _window(window_id="window-byte-second", subject_id="byte-second")
        )
    assert byte_store.get(first.subject_id, first.window_id) == first


def test_store_returns_identical_winner_and_rejects_different_immutable_content() -> None:
    redis = _Redis()
    store = _store(redis)
    winner = store.create_or_get(_window())
    assert store.create_or_get(_window()) == winner

    with pytest.raises(WindowIdentityConflictError):
        store.create_or_get(_window(item_snapshot={"quality": 0.1}))


def test_store_rejects_unbounded_or_noncanonical_encoded_window() -> None:
    redis = _Redis()
    store = _store(redis)
    oversized = _window(
        item_snapshot={"payload": "x" * RedisWindowStore.MAX_WINDOW_PAYLOAD_BYTES}
    )
    with pytest.raises(ValueError, match="2 MiB"):
        store.create_or_get(oversized)
    assert redis.values == {}

    valid = store.create_or_get(_window())
    key = next(iter(redis.values))
    redis.values[key] = redis.values[key][:-1] + b',"unknown":true}'
    with pytest.raises(RuntimeError, match="payload is invalid"):
        store.get(valid.subject_id, valid.window_id)
