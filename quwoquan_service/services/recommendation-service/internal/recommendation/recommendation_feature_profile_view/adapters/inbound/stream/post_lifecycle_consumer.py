from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from .durable_projection_consumer import DurableProjectionConsumer


POST_LIFECYCLE_STREAM = "events.content.post_lifecycle"
POST_LIFECYCLE_DLQ = "events.content.post_lifecycle.recommendation-feature.dlq"
CONSUMER_GROUP = "recommendation-feature-post-lifecycle"
UPSERT_EVENTS = {
    "PostPublished",
    "PostUpdated",
    "PostSettingsUpdated",
    "PostPromotedToWork",
}
REMOVAL_EVENTS = {"PostDeleted", "PostPrivacyRedacted", "PostPurged"}


@dataclass(frozen=True, slots=True)
class PostLifecycleEvent:
    event_id: str
    event_type: str
    post_id: str
    post_version: int
    author_id: str
    author_display_name: str
    author_avatar_url: str
    homepage_id: str
    visited: bool
    occurred_at: datetime
    event_digest: str


def _time(value: Any, *, required: bool = True) -> datetime | None:
    normalized = str(value or "").strip()
    if not normalized:
        if required:
            raise ValueError("Post lifecycle timestamp is required")
        return None
    parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Post lifecycle timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def decode_post_lifecycle(values: dict[str, str]) -> PostLifecycleEvent | None:
    event_type = values.get("eventType", "").strip()
    if event_type not in UPSERT_EVENTS | REMOVAL_EVENTS:
        return None
    if values.get("aggregateType", "").strip() != "Post":
        raise ValueError("Post lifecycle aggregateType must be Post")
    try:
        version = int(values.get("aggregateVersion", ""))
    except ValueError as error:
        raise ValueError("Post lifecycle aggregateVersion is invalid") from error
    try:
        payload: Any = json.loads(values.get("payload", ""))
    except json.JSONDecodeError as error:
        raise ValueError("Post lifecycle payload is invalid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("Post lifecycle payload must be an object")
    event_id = values.get("eventId", "").strip()
    post_id = values.get("aggregateId", "").strip()
    if (
        not event_id
        or not post_id
        or str(payload.get("postId") or "").strip() != post_id
        or version <= 0
    ):
        raise ValueError("Post lifecycle identity is invalid")
    occurred_at = _time(values.get("occurredAt"))
    assert occurred_at is not None
    author_id = str(payload.get("authorId") or "").strip()
    homepage_id = str(payload.get("primaryHomepageId") or "").strip()
    visited_at = _time(payload.get("visitedAt"), required=False)
    if event_type in UPSERT_EVENTS:
        eligibility = {
            str(payload.get("status") or "").strip().lower(),
            str(payload.get("visibility") or "").strip().lower(),
            str(payload.get("moderationStatus") or "").strip().lower(),
        }
        if "" in eligibility:
            raise ValueError("Post lifecycle upsert eligibility snapshot is incomplete")
        visible = eligibility == {"published", "public", "approved"}
    else:
        visible = False
    canonical = {
        "authorId": author_id,
        "eventId": event_id,
        "eventType": event_type,
        "homepageId": homepage_id,
        "occurredAt": occurred_at.isoformat(),
        "postId": post_id,
        "postVersion": version,
        "visitedAt": visited_at.isoformat() if visited_at is not None else "",
        "visible": visible,
    }
    digest = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    return PostLifecycleEvent(
        event_id=event_id,
        event_type=event_type,
        post_id=post_id,
        post_version=version,
        author_id=author_id,
        author_display_name=str(payload.get("authorDisplayNameSnapshot") or "").strip(),
        author_avatar_url=str(payload.get("authorAvatarUrlSnapshot") or "").strip(),
        homepage_id=homepage_id,
        visited=visible and visited_at is not None and bool(homepage_id),
        occurred_at=occurred_at,
        event_digest=digest,
    )


class PostLifecycleConsumer(DurableProjectionConsumer):
    def __init__(self, *, redis_client, feature_store, projector, consumer: str) -> None:
        def apply(values: dict[str, str]) -> None:
            event = decode_post_lifecycle(values)
            if event is not None:
                projector.project_post_lifecycle(
                    event_id=event.event_id,
                    event_digest=event.event_digest,
                    event_type=event.event_type,
                    post_id=event.post_id,
                    post_version=event.post_version,
                    author_id=event.author_id,
                    author_display_name=event.author_display_name,
                    author_avatar_url=event.author_avatar_url,
                    homepage_id=event.homepage_id,
                    visited=event.visited,
                    occurred_at=event.occurred_at,
                )

        super().__init__(
            redis_client=redis_client,
            feature_store=feature_store,
            stream=POST_LIFECYCLE_STREAM,
            dead_letter_stream=POST_LIFECYCLE_DLQ,
            consumer_group=CONSUMER_GROUP,
            consumer=consumer,
            handler=apply,
            thread_name="recommendation-feature-post-lifecycle",
        )
