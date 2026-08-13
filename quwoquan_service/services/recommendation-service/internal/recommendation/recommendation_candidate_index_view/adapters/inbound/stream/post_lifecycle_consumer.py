from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import threading
import time
from typing import Any

from internal.recommendation.recommendation_candidate_index_view.application.projector import (
    CandidateLifecycleSnapshot,
    RecommendationObjectCardCandidate,
)

from internal.recommendation.recommendation_candidate_index_view.adapters.inbound.stream.projection_metrics import (
    record_projection_outcome,
)


POST_LIFECYCLE_STREAM = "events.content.post_lifecycle"
POST_LIFECYCLE_DLQ = "events.content.post_lifecycle.recommendation_candidate.dlq"
CONSUMER_GROUP = "recommendation-candidate-index"
MAX_ATTEMPTS = 5
RETENTION_SECONDS = 7 * 24 * 60 * 60

UPSERT_EVENTS = {
    "PostPublished",
    "PostUpdated",
    "PostSettingsUpdated",
    "PostPromotedToWork",
}
REMOVAL_EVENTS = {
    "PostDeleted",
    "PostPrivacyRedacted",
    "PostPurged",
}


@dataclass(frozen=True, slots=True)
class PostLifecycleEvent:
    event_id: str
    event_type: str
    post_id: str
    post_version: int
    payload: dict[str, Any]
    occurred_at: datetime


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _values(raw: dict[Any, Any]) -> dict[str, str]:
    return {_text(key): _text(value) for key, value in raw.items()}


def _parse_time(value: Any, *, fallback: datetime | None = None) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        if fallback is None:
            raise ValueError("Post lifecycle timestamp is required")
        return fallback.astimezone(timezone.utc)
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Post lifecycle timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def decode_post_lifecycle(values: dict[str, str]) -> PostLifecycleEvent:
    if values.get("aggregateType", "").strip() != "Post":
        raise ValueError("Post lifecycle aggregateType must be Post")
    try:
        version = int(values.get("aggregateVersion", ""))
    except ValueError as error:
        raise ValueError("Post lifecycle aggregateVersion is invalid") from error
    if version <= 0:
        raise ValueError("Post lifecycle aggregateVersion must be positive")
    payload = json.loads(values.get("payload", ""))
    if not isinstance(payload, dict):
        raise ValueError("Post lifecycle payload must be an object")
    post_id = values.get("aggregateId", "").strip()
    payload_post_id = str(payload.get("postId") or "").strip()
    if not post_id or not payload_post_id or payload_post_id != post_id:
        raise ValueError("Post lifecycle aggregate identity mismatch")
    event = PostLifecycleEvent(
        event_id=values.get("eventId", "").strip(),
        event_type=values.get("eventType", "").strip(),
        post_id=post_id,
        post_version=version,
        payload=payload,
        occurred_at=_parse_time(values.get("occurredAt")),
    )
    if not event.event_id or not event.event_type:
        raise ValueError("Post lifecycle event identity is incomplete")
    return event


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("Post lifecycle references must be arrays")
    normalized = tuple(str(item).strip() for item in value)
    if any(not item for item in normalized) or len(set(normalized)) != len(normalized):
        raise ValueError("Post lifecycle references must be non-empty and unique")
    return normalized


def _eligible(payload: dict[str, Any]) -> bool:
    required_state = {
        "status": str(payload.get("status") or "").strip().lower(),
        "visibility": str(payload.get("visibility") or "").strip().lower(),
        "moderationStatus": str(payload.get("moderationStatus") or "").strip().lower(),
    }
    if not all(required_state.values()):
        raise ValueError(
            "Post lifecycle upsert must carry the complete eligibility snapshot"
        )
    return (
        required_state["status"] == "published"
        and required_state["visibility"] == "public"
        and required_state["moderationStatus"] == "approved"
    )


def lifecycle_snapshot(event: PostLifecycleEvent) -> CandidateLifecycleSnapshot | None:
    if event.event_type not in UPSERT_EVENTS or not _eligible(event.payload):
        return None
    tag_refs = _string_tuple(event.payload.get("tagRefs"))
    published_at = _parse_time(event.payload.get("publishedAt"))
    updated_at = _parse_time(event.payload.get("updatedAt"))
    homepage_id = str(event.payload.get("primaryHomepageId") or "").strip()
    raw_homepage = event.payload.get("primaryHomepageSnapshot")
    object_card = None
    if homepage_id:
        if not isinstance(raw_homepage, dict):
            raise ValueError(
                "Post lifecycle primaryHomepageId requires primaryHomepageSnapshot"
            )
        canonical_entity_id = str(
            raw_homepage.get("canonicalEntityId") or ""
        ).strip()
        title = str(raw_homepage.get("title") or "").strip()
        if not canonical_entity_id or not title:
            raise ValueError(
                "Post lifecycle Homepage snapshot identity and title are required"
            )
        object_card = RecommendationObjectCardCandidate(
            homepage_id=homepage_id,
            canonical_entity_id=canonical_entity_id,
            title=title,
            subtitle=(str(raw_homepage.get("subtitle") or "").strip() or None),
            cover_url=(str(raw_homepage.get("coverUrl") or "").strip() or None),
            tag_refs=tag_refs,
        )
    elif raw_homepage not in (None, {}):
        raise ValueError(
            "Post lifecycle primaryHomepageSnapshot requires primaryHomepageId"
        )
    return CandidateLifecycleSnapshot(
        scenario="content_feed",
        content_id=event.post_id,
        content_type=str(event.payload.get("contentType") or "").strip(),
        author_id=str(event.payload.get("authorId") or "").strip(),
        tag_refs=tag_refs,
        entity_refs=_string_tuple(event.payload.get("entityRefs")),
        published_at=published_at,
        content_vertical=(str(event.payload.get("contentVertical") or "").strip() or None),
        entity_tag_ids=tuple(tag for tag in tag_refs if tag.startswith("Entity/")),
        source_sequence=event.post_version,
        updated_at=updated_at,
        object_card=object_card,
    )


class PostLifecycleConsumer:
    def __init__(
        self,
        *,
        redis_client: Any,
        projection: Any,
        subject_closures: Any,
        consumer: str,
    ) -> None:
        self._redis = redis_client
        self._projection = projection
        self._subject_closures = subject_closures
        self._consumer = consumer.strip() or "recommendation-candidate-projection"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_success: datetime | None = None
        self._last_failure: Exception | None = None

    def ensure_group(self) -> None:
        try:
            self._redis.xgroup_create(
                POST_LIFECYCLE_STREAM,
                CONSUMER_GROUP,
                id="0-0",
                mkstream=True,
            )
        except Exception as error:
            if "BUSYGROUP" not in str(error):
                raise

    @staticmethod
    def _messages(raw: Any) -> list[tuple[str, dict[str, str]]]:
        messages: list[tuple[str, dict[str, str]]] = []
        for _stream, entries in raw or []:
            for stream_id, fields in entries:
                messages.append((_text(stream_id), _values(fields)))
        return messages

    def _claimed(self) -> list[tuple[str, dict[str, str]]]:
        result = self._redis.xautoclaim(
            POST_LIFECYCLE_STREAM,
            CONSUMER_GROUP,
            self._consumer,
            min_idle_time=30_000,
            start_id="0-0",
            count=50,
        )
        entries = result[1] if isinstance(result, (list, tuple)) and len(result) > 1 else []
        return [(_text(stream_id), _values(fields)) for stream_id, fields in entries]

    def _new(self) -> list[tuple[str, dict[str, str]]]:
        return self._messages(
            self._redis.xreadgroup(
                CONSUMER_GROUP,
                self._consumer,
                {POST_LIFECYCLE_STREAM: ">"},
                count=50,
            )
        )

    def _trim_and_expire(self, stream: str) -> None:
        server_time = self._redis.time()
        cutoff_ms = (int(server_time[0]) - RETENTION_SECONDS) * 1000
        self._redis.xtrim(stream, minid=f"{max(cutoff_ms, 0)}-0", approximate=False)
        self._redis.expire(stream, RETENTION_SECONDS)

    def _dead_letter(
        self,
        *,
        stream_id: str,
        values: dict[str, str],
        attempts: int,
        error: Exception,
    ) -> None:
        self._redis.xadd(
            POST_LIFECYCLE_DLQ,
            {
                "sourceStream": POST_LIFECYCLE_STREAM,
                "streamId": stream_id,
                "eventId": values.get("eventId", ""),
                "eventType": values.get("eventType", ""),
                "aggregateId": values.get("aggregateId", ""),
                "attempts": str(attempts),
                "error": str(error)[:1024],
                "deadLetteredAt": datetime.now(timezone.utc).isoformat(),
            },
        )
        self._trim_and_expire(POST_LIFECYCLE_DLQ)

    def _process(self, stream_id: str, values: dict[str, str]) -> None:
        try:
            event = decode_post_lifecycle(values)
            snapshot = lifecycle_snapshot(event)
            removal = None
            if snapshot is not None and self._subject_closures.exists(snapshot.author_id):
                snapshot = None
                removal = ("content_feed", event.post_id, event.post_version)
            if event.event_type in REMOVAL_EVENTS or (
                event.event_type in UPSERT_EVENTS and snapshot is None
            ):
                removal = ("content_feed", event.post_id, event.post_version)
            self._projection.apply_source_event(
                event_id=event.event_id,
                snapshot=snapshot,
                removal=removal,
            )
        except Exception as error:
            attempts = self._projection.record_source_failure(
                stream_id,
                values.get("eventId", ""),
                error,
            )
            if attempts < MAX_ATTEMPTS:
                raise
            self._dead_letter(
                stream_id=stream_id,
                values=values,
                attempts=attempts,
                error=error,
            )
            self._redis.xack(POST_LIFECYCLE_STREAM, CONSUMER_GROUP, stream_id)
            self._projection.clear_source_failure(stream_id)
            return
        self._redis.xack(POST_LIFECYCLE_STREAM, CONSUMER_GROUP, stream_id)
        self._projection.clear_source_failure(stream_id)

    def process_once(self) -> int:
        try:
            processed = self._process_once_inner()
        except Exception:
            record_projection_outcome("post_lifecycle", "error")
            raise
        record_projection_outcome("post_lifecycle", "ok")
        return processed

    def _process_once_inner(self) -> int:
        self.ensure_group()
        seen: set[str] = set()
        messages = []
        for stream_id, values in (*self._claimed(), *self._new()):
            if stream_id in seen:
                continue
            seen.add(stream_id)
            messages.append((stream_id, values))
        processed = 0
        first_error: Exception | None = None
        for stream_id, values in messages:
            try:
                self._process(stream_id, values)
                processed += 1
            except Exception as error:
                if first_error is None:
                    first_error = error
        if first_error is not None:
            self._last_failure = first_error
            raise first_error
        self._last_success = datetime.now(timezone.utc)
        self._last_failure = None
        return processed

    def healthy(self, *, max_staleness_seconds: float = 10.0) -> bool:
        if self._last_success is None or self._last_failure is not None:
            return False
        return (
            datetime.now(timezone.utc) - self._last_success
        ).total_seconds() <= max_staleness_seconds

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.process_once()
            except Exception:
                pass
            self._stop.wait(0.25)

    def start(self) -> None:
        self.ensure_group()
        if self._thread is not None:
            raise RuntimeError("Post lifecycle consumer is already started")
        self._thread = threading.Thread(
            target=self._run,
            name="recommendation-candidate-post-lifecycle",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
