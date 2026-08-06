from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import threading
from typing import Any


TAG_FEEDBACK_STREAM = "events.tag.feedback"
TAG_FEEDBACK_DLQ = "events.tag.feedback.recommendation-feature.dlq"
CONSUMER_GROUP = "recommendation-feature-tag-feedback"
MAX_ATTEMPTS = 5
RETENTION_SECONDS = 7 * 24 * 60 * 60


@dataclass(frozen=True, slots=True)
class TagFeedbackRecorded:
    event_id: str
    subject_id: str
    actor_kind: str
    tag_ref: str
    action: str
    recorded_at: datetime


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _values(raw: dict[Any, Any]) -> dict[str, str]:
    return {_text(key): _text(value) for key, value in raw.items()}


def _parse_time(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value or "").strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("TagFeedbackRecorded recordedAt must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def decode_tag_feedback(values: dict[str, str]) -> TagFeedbackRecorded:
    if values.get("eventName", "").strip() != "TagFeedbackRecorded":
        raise ValueError("unsupported recommendation tag feedback source event")
    event_id = values.get("eventId", "").strip()
    if not event_id or values.get("id", "").strip() != event_id:
        raise ValueError("TagFeedbackRecorded identity is invalid")
    subject_id = values.get("actorId", "").strip()
    actor_kind = values.get("actorKind", "").strip()
    tag_ref = values.get("tagRef", "").strip()
    action = values.get("action", "").strip()
    if (
        not subject_id
        or actor_kind not in {"persona", "device"}
        or not tag_ref
        or action not in {"click", "dislike", "ignore", "correct"}
    ):
        raise ValueError("TagFeedbackRecorded payload is invalid")
    return TagFeedbackRecorded(
        event_id=event_id,
        subject_id=subject_id,
        actor_kind=actor_kind,
        tag_ref=tag_ref,
        action=action,
        recorded_at=_parse_time(values.get("recordedAt")),
    )


class TagFeedbackConsumer:
    def __init__(
        self,
        *,
        redis_client: Any,
        feature_store: Any,
        feature_projector: Any,
        subject_closures: Any,
        consumer: str,
    ) -> None:
        self._redis = redis_client
        self._store = feature_store
        self._projector = feature_projector
        self._subject_closures = subject_closures
        self._consumer = consumer.strip() or "recommendation-feature-tag-feedback"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_success: datetime | None = None
        self._last_failure: Exception | None = None

    def ensure_group(self) -> None:
        try:
            self._redis.xgroup_create(
                TAG_FEEDBACK_STREAM,
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
            TAG_FEEDBACK_STREAM,
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
                {TAG_FEEDBACK_STREAM: ">"},
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
            TAG_FEEDBACK_DLQ,
            {
                "sourceStream": TAG_FEEDBACK_STREAM,
                "streamId": stream_id,
                "eventId": values.get("eventId", ""),
                "attempts": str(attempts),
                "error": str(error)[:1024],
                "deadLetteredAt": datetime.now(timezone.utc).isoformat(),
            },
        )
        self._trim_and_expire(TAG_FEEDBACK_DLQ)

    def _process(self, stream_id: str, values: dict[str, str]) -> None:
        try:
            event = decode_tag_feedback(values)
            if self._subject_closures.exists(event.subject_id):
                raise ValueError("TagFeedbackRecorded subject is closed")
            self._projector.project_tag_feedback(
                event_id=event.event_id,
                subject_id=event.subject_id,
                actor_kind=event.actor_kind,
                tag_ref=event.tag_ref,
                action=event.action,
                recorded_at=event.recorded_at,
            )
        except Exception as error:
            attempts = self._store.record_source_failure(
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
            self._redis.xack(TAG_FEEDBACK_STREAM, CONSUMER_GROUP, stream_id)
            self._store.clear_source_failure(stream_id)
            return
        self._redis.xack(TAG_FEEDBACK_STREAM, CONSUMER_GROUP, stream_id)
        self._store.clear_source_failure(stream_id)

    def process_once(self) -> int:
        self.ensure_group()
        seen: set[str] = set()
        messages: list[tuple[str, dict[str, str]]] = []
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
            raise RuntimeError("Tag feedback consumer is already started")
        self._thread = threading.Thread(
            target=self._run,
            name="recommendation-feature-tag-feedback",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
