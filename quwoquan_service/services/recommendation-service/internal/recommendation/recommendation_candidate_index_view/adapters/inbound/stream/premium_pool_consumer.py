from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import threading
from typing import Any

from internal.recommendation.recommendation_candidate_index_view.application.projector import (
    PremiumAdmissionSnapshot,
    Projector,
)

from internal.recommendation.recommendation_candidate_index_view.adapters.inbound.stream.projection_metrics import (
    record_projection_outcome,
)


PREMIUM_POOL_STREAM = "events.ops.premium_pool_entry"
PREMIUM_POOL_DLQ = "events.ops.premium_pool_entry.recommendation_candidate.dlq"
CONSUMER_GROUP = "recommendation-candidate-premium"
MAX_ATTEMPTS = 5
RETENTION_SECONDS = 7 * 24 * 60 * 60
EVENT_STATUSES = {
    "PremiumPoolEntryUpserted": "active",
    "PremiumPoolEntryRolledBack": "rolled_back",
    "PremiumPoolEntryTakedownEjected": "takedown_ejected",
}


@dataclass(frozen=True, slots=True)
class PremiumPoolEvent:
    event_id: str
    event_type: str
    content_id: str
    occurred_at: datetime
    snapshot: PremiumAdmissionSnapshot


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _values(raw: dict[Any, Any]) -> dict[str, str]:
    return {_text(key): _text(value) for key, value in raw.items()}


def _required_time(value: Any, name: str) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(f"premium pool {name} is required")
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"premium pool {name} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _optional_text(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def decode_premium_pool_event(values: dict[str, str]) -> PremiumPoolEvent:
    event_type = values.get("eventType", "").strip()
    expected_status = EVENT_STATUSES.get(event_type)
    if expected_status is None:
        raise ValueError("premium pool eventType is invalid")
    if values.get("aggregateType", "").strip() != "PremiumPoolEntry":
        raise ValueError("premium pool aggregateType must be PremiumPoolEntry")
    if values.get("producer", "").strip() != "product-ops-service":
        raise ValueError("premium pool producer must be product-ops-service")
    event_id = values.get("eventId", "").strip()
    content_id = values.get("aggregateId", "").strip()
    if not event_id or not content_id:
        raise ValueError("premium pool event identity is incomplete")
    payload = json.loads(values.get("payloadJson", ""))
    if not isinstance(payload, dict):
        raise ValueError("premium pool payload must be an object")
    if str(payload.get("contentId") or "").strip() != content_id:
        raise ValueError("premium pool content identity mismatch")
    status = str(payload.get("status") or "").strip()
    if status != expected_status:
        raise ValueError("premium pool event type and status mismatch")
    try:
        quality_score = float(payload.get("qualityScore"))
    except (TypeError, ValueError) as error:
        raise ValueError("premium pool qualityScore is invalid") from error
    takedown_ejected = payload.get("takedownEjected")
    if not isinstance(takedown_ejected, bool):
        raise ValueError("premium pool takedownEjected must be boolean")
    snapshot = PremiumAdmissionSnapshot(
        content_id=content_id,
        status=status,
        scope=str(payload.get("scope") or "").strip(),
        quality_admission=str(payload.get("qualityAdmission") or "").strip(),
        quality_score=quality_score,
        supply_source=_optional_text(payload.get("supplySource")),
        source_task_id=_optional_text(payload.get("sourceTaskId")),
        audit_id=str(payload.get("auditId") or "").strip(),
        rollback_token=str(payload.get("rollbackToken") or "").strip(),
        featured_at=_required_time(payload.get("featuredAt"), "featuredAt"),
        expires_at=_required_time(payload.get("expiresAt"), "expiresAt"),
        takedown_ejected=takedown_ejected,
        updated_at=_required_time(payload.get("updatedAt"), "updatedAt"),
    )
    return PremiumPoolEvent(
        event_id=event_id,
        event_type=event_type,
        content_id=content_id,
        occurred_at=_required_time(values.get("occurredAt"), "occurredAt"),
        snapshot=snapshot,
    )


class PremiumPoolConsumer:
    def __init__(self, *, redis_client: Any, store: Any, consumer: str) -> None:
        self._redis = redis_client
        self._store = store
        self._projection = Projector(store)
        self._consumer = consumer.strip() or "recommendation-candidate-premium"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_success: datetime | None = None
        self._last_failure: Exception | None = None

    def ensure_group(self) -> None:
        try:
            self._redis.xgroup_create(
                PREMIUM_POOL_STREAM,
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
            PREMIUM_POOL_STREAM,
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
                {PREMIUM_POOL_STREAM: ">"},
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
            PREMIUM_POOL_DLQ,
            {
                "sourceStream": PREMIUM_POOL_STREAM,
                "streamId": stream_id,
                "eventId": values.get("eventId", ""),
                "eventType": values.get("eventType", ""),
                "aggregateId": values.get("aggregateId", ""),
                "attempts": str(attempts),
                "error": str(error)[:1024],
                "deadLetteredAt": datetime.now(timezone.utc).isoformat(),
            },
        )
        self._trim_and_expire(PREMIUM_POOL_DLQ)

    def _process(self, stream_id: str, values: dict[str, str]) -> None:
        try:
            event = decode_premium_pool_event(values)
            self._projection.apply_premium_source_event(
                event_id=event.event_id,
                snapshot=event.snapshot,
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
            self._redis.xack(PREMIUM_POOL_STREAM, CONSUMER_GROUP, stream_id)
            self._store.clear_source_failure(stream_id)
            return
        self._redis.xack(PREMIUM_POOL_STREAM, CONSUMER_GROUP, stream_id)
        self._store.clear_source_failure(stream_id)

    def process_once(self) -> int:
        try:
            processed = self._process_once_inner()
        except Exception:
            record_projection_outcome("premium_pool", "error")
            raise
        record_projection_outcome("premium_pool", "ok")
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
            raise RuntimeError("Premium pool consumer is already started")
        self._thread = threading.Thread(
            target=self._run,
            name="recommendation-candidate-premium",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
