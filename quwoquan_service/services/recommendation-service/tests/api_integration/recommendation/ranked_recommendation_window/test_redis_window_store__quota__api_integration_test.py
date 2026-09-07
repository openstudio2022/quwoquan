from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from redis import Redis

from internal.recommendation.ranked_recommendation_window.domain.model import (
    RankedCandidate,
    RankedRecommendationWindow,
    RankingResult,
)
from internal.recommendation.ranked_recommendation_window.infrastructure.redis_store import (
    RedisWindowStore,
    _ATOMIC_CREATE_SCRIPT,
    WindowShardRecordQuotaError,
)
from tests.support.recommendation_redis import real_redis, real_redis_cluster


# spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-001


def _window(window_id: str, subject_id: str) -> RankedRecommendationWindow:
    now = datetime.now(timezone.utc)
    return RankedRecommendationWindow.create(
        window_id=window_id,
        subject_id=subject_id,
        scenario="content_feed",
        request_digest=f"request-{window_id}",
        ranking=RankingResult(
            experiment_bucket="rule",
            model_bucket="rule",
            model_channel=None,
            model_release_id=None,
            policy_digest="sha256:2f8a57089882835170b77224eb7ef2db78c5d5d26ae4637b210dbe195713f094",
            feature_snapshot_at=now,
            ranking_snapshot_digest=f"ranking-{window_id}",
            user_feature_snapshot={},
            candidates=(
                RankedCandidate(
                    content_id=f"post-{window_id}",
                    score=1.0,
                    feature_snapshot_digest=f"feature-{window_id}",
                    item_feature_snapshot={"quality": 1.0},
                ),
            ),
        ),
        now=now,
    )


def test_real_redis_lua_enforces_owner_and_shard_caps_without_sliding_ttl(
    real_redis: Redis,
) -> None:
    store = RedisWindowStore(
        real_redis,
        quota_shard_count=1,
        maximum_live_records_per_shard=8,
        maximum_live_bytes_per_shard=8 * 1024 * 1024,
    )
    windows = [
        store.create_or_get(_window(f"window-{index:02d}", "persona-primary"))
        for index in range(9)
    ]
    assert store.get("persona-primary", windows[0].window_id) is None
    assert all(
        store.get("persona-primary", window.window_id) == window
        for window in windows[1:]
    )

    value_keys = sorted(real_redis.scan_iter("rec:ranked_feed_window:{rfw-0000}:*"))
    assert len(value_keys) == 8
    assert all(b"persona-primary" not in key for key in value_keys)
    assert real_redis.zcard("rec:ranked_feed_window_index:{rfw-0000}") == 8
    assert real_redis.hlen("rec:ranked_feed_window_metadata:{rfw-0000}") == 8
    ttl_before = real_redis.pttl(value_keys[0])
    assert 0 < ttl_before <= RedisWindowStore.TTL_SECONDS * 1000
    assert store.get("persona-primary", windows[-1].window_id) == windows[-1]
    ttl_after = real_redis.pttl(value_keys[0])
    assert 0 < ttl_after <= ttl_before

    real_redis.delete(value_keys[0])
    real_redis.zadd(
        "rec:ranked_feed_window_index:{rfw-0000}",
        {value_keys[1]: 0},
    )
    repaired_missing = store.create_or_get(
        _window("window-repair-missing", "persona-primary")
    )
    repaired_expired = store.create_or_get(
        _window("window-repair-expired", "persona-primary")
    )
    assert store.get(repaired_missing.subject_id, repaired_missing.window_id) == repaired_missing
    assert store.get(repaired_expired.subject_id, repaired_expired.window_id) == repaired_expired
    assert real_redis.zcard("rec:ranked_feed_window_index:{rfw-0000}") == 8
    assert real_redis.hlen("rec:ranked_feed_window_metadata:{rfw-0000}") == 8

    with pytest.raises(WindowShardRecordQuotaError):
        store.create_or_get(_window("window-other", "persona-other"))
    assert len(list(real_redis.scan_iter("rec:ranked_feed_window:{rfw-0000}:*"))) == 8

    assert store.erase_subject("persona-primary") == 8
    assert list(real_redis.scan_iter("rec:ranked_feed_window:{rfw-0000}:*")) == []
    assert real_redis.zcard("rec:ranked_feed_window_index:{rfw-0000}") == 0
    assert real_redis.hlen("rec:ranked_feed_window_metadata:{rfw-0000}") == 0

    contender = _window("window-concurrent", "persona-concurrent")
    with ThreadPoolExecutor(max_workers=8) as pool:
        winners = list(pool.map(lambda _index: store.create_or_get(contender), range(8)))
    assert winners == [contender] * 8
    assert store.create_or_get(contender) == contender
    assert real_redis.zcard("rec:ranked_feed_window_index:{rfw-0000}") == 1
    assert real_redis.hlen("rec:ranked_feed_window_metadata:{rfw-0000}") == 1


# spec_ref: specs/feature-tree/runtime/runtime-redis/spec.md#sit-001
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md#dec-032
def test_real_redis_cluster_executes_the_production_multikey_script_in_one_slot(
    real_redis_cluster,
) -> None:
    client = real_redis_cluster.client
    store = RedisWindowStore(
        client,
        quota_shard_count=1,
        maximum_live_records_per_shard=8,
        maximum_live_bytes_per_shard=8 * 1024 * 1024,
    )
    first = _window("cluster-window-01", "cluster-persona")
    second = _window("cluster-window-02", "cluster-persona")

    assert store.create_or_get(first) == first
    assert store.create_or_get(second) == second

    subject_hash = store._subject_hash(second.subject_id)
    record_key, index_key, metadata_key = store._keys(
        subject_hash,
        second.window_id,
    )
    indexed_keys = [
        value.decode("utf-8") if isinstance(value, bytes) else str(value)
        for value in client.zrange(index_key, 0, -1)
    ]
    production_keys = [record_key, index_key, metadata_key, *indexed_keys]
    server_slots = {client.cluster_keyslot(key) for key in production_keys}
    assert len(server_slots) == 1

    untagged_keys = tuple(
        key.replace("{rfw-0000}", "rfw-0000")
        for key in production_keys[:3]
    )
    untagged_slots = {
        real_redis_cluster.direct.execute_command("CLUSTER", "KEYSLOT", key)
        for key in untagged_keys
    }
    assert len(untagged_slots) > 1
    assert real_redis_cluster.raw_eval_error(
        _ATOMIC_CREATE_SCRIPT,
        untagged_keys,
    ).startswith(b"-CROSSSLOT ")

    assert store.erase_subject("cluster-persona") == 2
    assert client.zcard(index_key) == 0
    assert client.hlen(metadata_key) == 0
