from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import threading
from typing import Any

from internal.recommendation.recommendation_feedback_fact.application.appender import (
    Appender,
)
from internal.recommendation.recommendation_feedback_fact.domain.fact import (
    RecommendationFeedbackFact,
)

from prometheus_client import Counter

# 契约 runtime_entrypoints[].telemetry.metric 同名计数器（outcome=ok|error）。
_INGEST_OUTCOMES = Counter(
    "recommendation_feedback_ingest",
    "Contract runtime entrypoint outcome counter (ContentBehavior ingest).",
    ["outcome"],
)


CONTENT_BEHAVIOR_STREAM = "events.content.behavior_facts"
CONTENT_BEHAVIOR_DLQ = "events.content.behavior_facts.recommendation-feedback.dlq"
CONSUMER_GROUP = "recommendation-feedback-fact"
MAX_ATTEMPTS = 5
RETENTION_SECONDS = 7 * 24 * 60 * 60


@dataclass(frozen=True, slots=True)
class ContentBehaviorEvent:
    event_id: str
    source_sequence: int
    subject_id: str
    feed_request_id: str
    target_id: str
    payload: dict[str, Any]
    occurred_at: datetime


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _values(raw: dict[Any, Any]) -> dict[str, str]:
    return {_text(key): _text(value) for key, value in raw.items()}


def _parse_time(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value or "").strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("ContentBehaviorRecorded occurredAt must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def decode_content_behavior(values: dict[str, str]) -> ContentBehaviorEvent:
    if values.get("eventName", "").strip() != "ContentBehaviorRecorded":
        raise ValueError("unsupported recommendation feedback source event")
    payload = json.loads(values.get("payload", ""))
    if not isinstance(payload, dict):
        raise ValueError("ContentBehaviorRecorded payload must be an object")
    subject_id = values.get("subjectId", "").strip()
    client_event_id = str(payload.get("clientEventId") or "").strip()
    expected_event_id = hashlib.sha256(
        f"ContentBehaviorRecorded:{subject_id}:{client_event_id}".encode("utf-8")
    ).hexdigest()
    event_id = values.get("eventId", "").strip()
    if not subject_id or not client_event_id or event_id != expected_event_id:
        raise ValueError("ContentBehaviorRecorded identity is invalid")
    source_sequence_raw = values.get("sourceSequence", "").strip()
    try:
        source_sequence = int(source_sequence_raw, 16)
    except ValueError as error:
        raise ValueError("ContentBehaviorRecorded sourceSequence is invalid") from error
    if source_sequence <= 0:
        raise ValueError("ContentBehaviorRecorded sourceSequence must be positive")
    feed_request_id = values.get("feedRequestId", "").strip()
    target_id = values.get("targetId", "").strip()
    if feed_request_id != str(payload.get("feedRequestId") or "").strip():
        raise ValueError("ContentBehaviorRecorded feedRequestId mismatch")
    if target_id != str(payload.get("contentId") or "").strip():
        raise ValueError("ContentBehaviorRecorded targetId mismatch")
    occurred_at = _parse_time(values.get("occurredAt"))
    if occurred_at != _parse_time(payload.get("occurredAt")):
        raise ValueError("ContentBehaviorRecorded occurredAt mismatch")
    return ContentBehaviorEvent(
        event_id=event_id,
        source_sequence=source_sequence,
        subject_id=subject_id,
        feed_request_id=feed_request_id,
        target_id=target_id,
        payload=payload,
        occurred_at=occurred_at,
    )


class ContentBehaviorConsumer:
    def __init__(
        self,
        *,
        redis_client: Any,
        feedback_store: Any,
        exposure_store: Any,
        subject_closures: Any,
        feature_projector: Any,
        consumer: str,
    ) -> None:
        self._redis = redis_client
        self._feedback_store = feedback_store
        self._exposure_store = exposure_store
        self._appender = Appender(feedback_store, exposure_store, subject_closures)
        self._feature_projector = feature_projector
        self._consumer = consumer.strip() or "recommendation-feedback-fact"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_success: datetime | None = None
        self._last_failure: Exception | None = None

    def ensure_group(self) -> None:
        try:
            self._redis.xgroup_create(
                CONTENT_BEHAVIOR_STREAM,
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
            CONTENT_BEHAVIOR_STREAM,
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
                {CONTENT_BEHAVIOR_STREAM: ">"},
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
            CONTENT_BEHAVIOR_DLQ,
            {
                "sourceStream": CONTENT_BEHAVIOR_STREAM,
                "streamId": stream_id,
                "eventId": values.get("eventId", ""),
                "attempts": str(attempts),
                "error": str(error)[:1024],
                "deadLetteredAt": datetime.now(timezone.utc).isoformat(),
            },
        )
        self._trim_and_expire(CONTENT_BEHAVIOR_DLQ)

    def _process(self, stream_id: str, values: dict[str, str]) -> None:
        try:
            event = decode_content_behavior(values)
            if not event.feed_request_id or not event.target_id:
                self._redis.xack(CONTENT_BEHAVIOR_STREAM, CONSUMER_GROUP, stream_id)
                self._feedback_store.clear_failure(stream_id)
                return
            exposure = self._exposure_store.find_by_attribution(
                event.feed_request_id,
                event.target_id,
            )
            if exposure is None:
                raise LookupError("matching recommendation exposure is not available")
            if exposure.subject_id != event.subject_id:
                raise ValueError("ContentBehaviorRecorded subject does not match exposure")
            feedback_id = hashlib.sha256(
                f"RecommendationFeedbackFact:{event.event_id}".encode("utf-8")
            ).hexdigest()
            action = str(event.payload.get("action") or "").strip()
            value = event.payload.get("duration") if action in {"dwell", "play"} else 1.0
            feedback, _created = self._appender.append(
                RecommendationFeedbackFact(
                    feedback_id=feedback_id,
                    source_event_id=event.event_id,
                    exposure_id=exposure.exposure_id,
                    feed_request_id=event.feed_request_id,
                    experiment_bucket=exposure.experiment_bucket,
                    subject_id=event.subject_id,
                    persona_id=(str(event.payload.get("personaId") or "").strip() or None),
                    target_type=(str(event.payload.get("contentType") or "").strip() or "post"),
                    target_id=event.target_id,
                    feedback_type=action,
                    value=float(value) if value is not None else None,
                    occurred_at=event.occurred_at,
                    recorded_at=datetime.now(timezone.utc),
                )
            )
            self._feature_projector.project_behavior(
                event_id=event.event_id,
                source_sequence=event.source_sequence,
                subject_id=event.subject_id,
                payload=event.payload,
                feedback_fact_id=feedback.feedback_id,
                exposure_fact_id=feedback.exposure_id,
                occurred_at=event.occurred_at,
            )
        except Exception as error:
            attempts = self._feedback_store.record_failure(
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
            self._redis.xack(CONTENT_BEHAVIOR_STREAM, CONSUMER_GROUP, stream_id)
            self._feedback_store.clear_failure(stream_id)
            return
        self._redis.xack(CONTENT_BEHAVIOR_STREAM, CONSUMER_GROUP, stream_id)
        self._feedback_store.clear_failure(stream_id)

    def process_once(self) -> int:
        try:
            processed = self._process_once_inner()
        except Exception:
            _INGEST_OUTCOMES.labels(outcome="error").inc()
            raise
        _INGEST_OUTCOMES.labels(outcome="ok").inc()
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
        return (datetime.now(timezone.utc) - self._last_success).total_seconds() <= max_staleness_seconds

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
            raise RuntimeError("ContentBehavior consumer is already started")
        self._thread = threading.Thread(
            target=self._run,
            name="recommendation-feedback-content-behavior",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
