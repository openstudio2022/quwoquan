from pathlib import Path

import yaml

from internal.recommendation.ranked_recommendation_window.infrastructure.redis_store import (
    RedisWindowStore,
)


# spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-001


def test_ranked_window_quota_config_has_one_recommendation_owned_baseline() -> None:
    recommendation_root = Path(__file__).resolve().parents[4]
    schema = yaml.safe_load(
        (recommendation_root / "config/schema.yaml").read_text(encoding="utf-8")
    )
    entries = {entry["key"]: entry for entry in schema["configs"]}
    expected = {
        "sys.recommendation-service.ranked_window.quota_shard_count": (
            RedisWindowStore.DEFAULT_QUOTA_SHARD_COUNT
        ),
        "sys.recommendation-service.ranked_window.maximum_live_records_per_shard": (
            RedisWindowStore.DEFAULT_MAXIMUM_LIVE_RECORDS_PER_SHARD
        ),
        "sys.recommendation-service.ranked_window.maximum_live_bytes_per_shard": (
            RedisWindowStore.DEFAULT_MAXIMUM_LIVE_BYTES_PER_SHARD
        ),
    }
    for key, default in expected.items():
        assert entries[key] == {
            "key": key,
            "type": "int",
            "scope": "workload",
            "reload": "restart",
            "rollout": "progressive",
            "sensitive": False,
            "default": default,
        }

    content_schema = yaml.safe_load(
        (
            recommendation_root.parent
            / "content-service/config/schema.yaml"
        ).read_text(encoding="utf-8")
    )
    content_keys = {entry["key"] for entry in content_schema["configs"]}
    assert not any("ranked_window" in key for key in content_keys)
