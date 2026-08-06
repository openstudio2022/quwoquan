from __future__ import annotations

import json
from typing import Any

from ..domain.outbox import OutboxEvent


MODEL_RELEASE_EVENT_STREAM = "events.recommendation.model_releases"
MODEL_RELEASE_EVENT_RETENTION_SECONDS = 7 * 24 * 60 * 60


class RedisRecommendationModelReleaseEventPublisher:
    def __init__(self, redis_client: Any) -> None:
        if redis_client is None:
            raise ValueError("model release event publisher requires Redis")
        self._redis = redis_client

    def publish(self, event: OutboxEvent) -> None:
        payload = json.dumps(
            event.payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        self._redis.xadd(
            MODEL_RELEASE_EVENT_STREAM,
            {
                "eventId": event.event_id,
                "eventType": event.event_type,
                "aggregateType": "RecommendationModelRelease",
                "aggregateId": event.aggregate_id,
                "aggregateVersion": str(event.aggregate_version),
                "occurredAt": event.occurred_at.isoformat(),
                "payload": payload,
            },
        )
        server_time = self._redis.time()
        cutoff_ms = (
            int(server_time[0]) - MODEL_RELEASE_EVENT_RETENTION_SECONDS
        ) * 1000
        self._redis.xtrim(
            MODEL_RELEASE_EVENT_STREAM,
            minid=f"{max(cutoff_ms, 0)}-0",
            approximate=False,
        )
        self._redis.expire(
            MODEL_RELEASE_EVENT_STREAM,
            MODEL_RELEASE_EVENT_RETENTION_SECONDS,
        )


__all__ = [
    "MODEL_RELEASE_EVENT_RETENTION_SECONDS",
    "MODEL_RELEASE_EVENT_STREAM",
    "RedisRecommendationModelReleaseEventPublisher",
]
