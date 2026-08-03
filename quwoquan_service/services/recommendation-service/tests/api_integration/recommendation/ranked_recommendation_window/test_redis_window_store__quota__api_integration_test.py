from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

import pytest
from redis import Redis

from internal.recommendation.ranked_recommendation_window.domain.model import (
    RankedCandidate,
    RankedRecommendationWindow,
    RankingResult,
)
from internal.recommendation.ranked_recommendation_window.infrastructure.redis_store import (
    RedisWindowStore,
    WindowShardRecordQuotaError,
)


# spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-001


@pytest.fixture()
def real_redis():
    binary = shutil.which("redis-server")
    if not binary:
        pytest.fail("redis-server is required for ranked-window api_integration")
    with tempfile.TemporaryDirectory(prefix="qwq-rfw-", dir="/tmp") as runtime_dir:
        socket_path = Path(runtime_dir) / "redis.sock"
        process = subprocess.Popen(
            [
                binary,
                "--port",
                "0",
                "--unixsocket",
                str(socket_path),
                "--unixsocketperm",
                "700",
                "--save",
                "",
                "--appendonly",
                "no",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        client = Redis(unix_socket_path=str(socket_path), decode_responses=False)
        try:
            for _ in range(100):
                if process.poll() is not None:
                    output = process.stdout.read() if process.stdout else ""
                    pytest.fail(
                        f"redis-server exited before becoming ready: {output}"
                    )
                try:
                    if client.ping():
                        break
                except Exception:
                    time.sleep(0.02)
            else:
                pytest.fail("redis-server did not become ready")
            yield client
        finally:
            try:
                client.close()
            finally:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)


def _window(window_id: str, subject_id: str) -> RankedRecommendationWindow:
    now = datetime.now(timezone.utc)
    return RankedRecommendationWindow.create(
        window_id=window_id,
        subject_id=subject_id,
        scenario="content_feed",
        request_digest=f"request-{window_id}",
        ranking=RankingResult(
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
