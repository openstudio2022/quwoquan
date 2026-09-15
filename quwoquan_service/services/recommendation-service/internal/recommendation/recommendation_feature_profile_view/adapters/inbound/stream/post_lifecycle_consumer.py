from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from .durable_projection_consumer import DurableProjectionConsumer
from generated.recommendation.recommendation_feature_profile_view.events.content_post_PostPublished import PostLifecycleProjectionPayload
from generated.recommendation.recommendation_feature_profile_view.events.content_post_PostDeleted import PostDeletedPayload
from generated.recommendation.recommendation_feature_profile_view.events.content_post_PostPrivacyRedacted import PostPrivacyRedactedPayload
from generated.recommendation.recommendation_feature_profile_view.events.content_post_PostPurged import PostPurgedPayload


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
    gathering_id: str
    recap: bool
    tag_refs: tuple[str, ...]
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
    if event_type not in UPSERT_EVENTS | REMOVAL_EVENTS | {"PostModerationRejected"}:
        raise ValueError("unsupported or unimplemented Content lifecycle event")
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
    source_keys = {"environment", "sourceOwner", "releaseId", "manifestDigest", "releaseDigest", "sourceVersion"}
    if not source_keys <= payload.keys() or type(payload["sourceVersion"]) is not int or payload["sourceVersion"] != version:
        raise ValueError("Post source presence/version mismatch")
    model = PostLifecycleProjectionPayload if event_type in UPSERT_EVENTS | {"PostModerationRejected"} else {"PostDeleted": PostDeletedPayload, "PostPrivacyRedacted": PostPrivacyRedactedPayload, "PostPurged": PostPurgedPayload}[event_type]
    if type(payload.get("safetyRevision")) is not int or payload["safetyRevision"] < 1:
        raise ValueError("Post safetyRevision must be explicit and positive")
    model.model_validate_json(json.dumps(payload))
    if any(payload[key] is not None for key in source_keys - {"sourceVersion"}):
        raise ValueError("Data lifecycle requires authoritative partition/safety reconciliation")
    if model is PostLifecycleProjectionPayload:
        if "publishedAt" not in payload or "visitedAt" not in payload:
            raise ValueError("Post nullable timestamps must be explicit")
        if payload["status"] == "published" and payload["publishedAt"] is None:
            raise ValueError("published Post requires actual publication time")
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
    gathering_id = str(payload.get("gatheringRef") or "").strip()
    # 内容标签（发布确认页真实采集的公开事实）：漏斗类目镜头的维度源；
    # 缺失按空处理，不臆造。
    raw_tag_refs = payload.get("tagRefs") or []
    tag_refs = tuple(
        str(tag).strip()
        for tag in (raw_tag_refs if isinstance(raw_tag_refs, list) else [])
        if str(tag).strip()
    )
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
        "gatheringRef": gathering_id,
        "homepageId": homepage_id,
        "occurredAt": occurred_at.isoformat(),
        "postId": post_id,
        "postVersion": version,
        "tagRefs": list(tag_refs),
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
        gathering_id=gathering_id,
        # 公开回顾事实：作者主动关联 gatheringRef 且内容公开可见时才成立；
        # 删除/隐私撤回事件回落为 False（经历交集据此收敛）。
        recap=visible and bool(gathering_id) and bool(author_id),
        tag_refs=tag_refs,
        occurred_at=occurred_at,
        event_digest=digest,
    )


class PostLifecycleConsumer(DurableProjectionConsumer):
    def _process(self, stream_id: str, event_values: dict[str, str]) -> None:
        # 本Post流不允许未知/未实现事实经公共consumer的DLQ次数阈值被ACK。
        failure_id = f"{self._consumer_group}:{stream_id}"
        if event_values.get("eventType") == "ContentReleaseFenceChanged":
            self._unresolved_fences.add(stream_id)
        try:
            self._handler(event_values)
        except Exception as error:
            self._store.record_source_failure(failure_id, event_values.get("eventId", ""), ValueError(type(error).__name__))
            raise
        self._redis.xack(self._stream, self._consumer_group, stream_id)
        self._store.clear_source_failure(failure_id)
        self._unresolved_fences.discard(stream_id)

    def healthy(self, *, max_staleness_seconds: float = 10.0) -> bool:
        return not self._unresolved_fences and super().healthy(max_staleness_seconds=max_staleness_seconds)

    def __init__(self, *, redis_client, feature_store, projector, consumer: str, fence_reconciler=None) -> None:
        self._unresolved_fences: set[str] = set()
        def apply(values: dict[str, str]) -> None:
            if values.get("eventType") == "ContentReleaseFenceChanged":
                if fence_reconciler is None:
                    raise ValueError("Content fence credentials/proof port not configured")
                fence_reconciler.apply(values)
                return
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
                    gathering_id=event.gathering_id,
                    recap=event.recap,
                    tag_refs=event.tag_refs,
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
