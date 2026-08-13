from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any


INTERSECTION_EVENT_STREAM = "events.recommendation.intersections"
INTERSECTION_EVENT_RETENTION_SECONDS = 7 * 24 * 60 * 60


class RedisIntersectionFacilitationEventPublisher:
    """IntersectionFacilitationRecorded 的 durable stream 出口。

    只在经历级首次达成时按 (gathering, creator, seedPost) 发布一次促成事实；
    payload 只携带计数与公开经历引用，不含参与者名单（契约
    recommendation_feature_profile_view/events.yaml 单一真相源）。
    """

    def __init__(self, redis_client: Any) -> None:
        if redis_client is None:
            raise ValueError("facilitation event publisher requires Redis")
        self._redis = redis_client

    def publish_facilitation(
        self,
        *,
        gathering_id: str,
        creator_persona_id: str,
        seed_post_id: str,
        occurred_at: datetime,
    ) -> None:
        gathering = gathering_id.strip()
        creator = creator_persona_id.strip()
        seed_post = seed_post_id.strip()
        if not gathering or not creator or not seed_post:
            raise ValueError("facilitation event identity is incomplete")
        if occurred_at.tzinfo is None:
            raise ValueError("facilitation occurredAt must be timezone-aware")
        facilitation_id = hashlib.sha256(
            f"IntersectionFacilitationRecorded:{gathering}:{creator}:{seed_post}".encode()
        ).hexdigest()
        payload = json.dumps(
            {
                "facilitationId": facilitation_id,
                "gatheringId": gathering,
                "creatorPersonaId": creator,
                "seedPostId": seed_post,
                "occurredAt": occurred_at.isoformat(),
            },
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        self._redis.xadd(
            INTERSECTION_EVENT_STREAM,
            {
                "eventId": facilitation_id,
                "eventType": "IntersectionFacilitationRecorded",
                "aggregateType": "RecommendationFeatureProfileView",
                "aggregateId": gathering,
                "aggregateVersion": "1",
                "occurredAt": occurred_at.isoformat(),
                "payload": payload,
            },
        )
        self._redis.expire(
            INTERSECTION_EVENT_STREAM,
            INTERSECTION_EVENT_RETENTION_SECONDS,
        )


__all__ = [
    "INTERSECTION_EVENT_RETENTION_SECONDS",
    "INTERSECTION_EVENT_STREAM",
    "RedisIntersectionFacilitationEventPublisher",
]
