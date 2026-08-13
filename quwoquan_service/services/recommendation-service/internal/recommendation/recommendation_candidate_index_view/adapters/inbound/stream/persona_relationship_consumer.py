from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import threading
from typing import Any


PERSONA_RELATIONSHIP_STREAM = "events.user.persona_relationship"
PERSONA_RELATIONSHIP_DLQ = (
    "events.user.persona_relationship.recommendation-candidate.dlq"
)

from internal.recommendation.recommendation_candidate_index_view.adapters.inbound.stream.projection_metrics import (
    record_projection_outcome,
)
CONSUMER_GROUP = "recommendation-candidate-persona-relationship"
MAX_ATTEMPTS = 5
RETENTION_SECONDS = 7 * 24 * 60 * 60
SUPPORTED_EVENTS = {
    "PersonaFollowStateChanged",
    "PersonaBlocked",
    "PersonaUnblocked",
}


@dataclass(frozen=True, slots=True)
class PersonaRelationshipEvent:
    event_id: str
    event_name: str
    source_persona_id: str
    target_persona_id: str
    following: bool
    version: int
    occurred_at: datetime
    event_digest: str


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _values(raw: dict[Any, Any]) -> dict[str, str]:
    return {_text(key): _text(value) for key, value in raw.items()}


def _parse_bool(value: str, *, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"persona relationship {name} is invalid")


def _parse_time(value: str) -> datetime:
    normalized = value.strip()
    if not normalized:
        raise ValueError("persona relationship occurredAt is required")
    parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("persona relationship occurredAt must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def decode_persona_relationship(
    values: dict[str, str],
) -> PersonaRelationshipEvent | None:
    event_name = values.get("eventName", "").strip()
    if event_name not in SUPPORTED_EVENTS:
        return None
    event_id = values.get("eventId", "").strip()
    source_persona_id = values.get("sourcePersonaId", "").strip()
    target_persona_id = values.get("targetPersonaId", "").strip()
    following = _parse_bool(values.get("following", ""), name="following")
    try:
        version = int(values.get("version", ""))
    except ValueError as error:
        raise ValueError("persona relationship version is invalid") from error
    occurred_at = _parse_time(values.get("occurredAt", ""))
    if (
        not event_id
        or not source_persona_id
        or not target_persona_id
        or source_persona_id == target_persona_id
        or version <= 0
    ):
        raise ValueError("persona relationship identity is invalid")
    if event_name in {"PersonaBlocked", "PersonaUnblocked"} and following:
        raise ValueError("block lifecycle event cannot retain following=true")
    canonical = {
        "eventId": event_id,
        "eventName": event_name,
        "following": following,
        "occurredAt": occurred_at.isoformat(),
        "sourcePersonaId": source_persona_id,
        "targetPersonaId": target_persona_id,
        "version": version,
    }
    event_digest = hashlib.sha256(
        json.dumps(
            canonical,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return PersonaRelationshipEvent(
        event_id=event_id,
        event_name=event_name,
        source_persona_id=source_persona_id,
        target_persona_id=target_persona_id,
        following=following,
        version=version,
        occurred_at=occurred_at,
        event_digest=event_digest,
    )


class PersonaRelationshipConsumer:
    def __init__(self, *, redis_client: Any, projection: Any, consumer: str) -> None:
        self._redis = redis_client
        self._projection = projection
        self._consumer = consumer.strip() or "recommendation-candidate-persona-relationship"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_success: datetime | None = None
        self._last_failure: Exception | None = None

    def ensure_group(self) -> None:
        try:
            self._redis.xgroup_create(
                PERSONA_RELATIONSHIP_STREAM,
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
            PERSONA_RELATIONSHIP_STREAM,
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
                {PERSONA_RELATIONSHIP_STREAM: ">"},
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
            PERSONA_RELATIONSHIP_DLQ,
            {
                "sourceStream": PERSONA_RELATIONSHIP_STREAM,
                "streamId": stream_id,
                "eventId": values.get("eventId", ""),
                "eventName": values.get("eventName", ""),
                "attempts": str(attempts),
                "error": str(error)[:1024],
                "deadLetteredAt": datetime.now(timezone.utc).isoformat(),
            },
        )
        self._trim_and_expire(PERSONA_RELATIONSHIP_DLQ)

    def _process(self, stream_id: str, values: dict[str, str]) -> None:
        failure_id = f"persona-relationship:{stream_id}"
        try:
            event = decode_persona_relationship(values)
            if event is not None:
                self._projection.apply_persona_relationship_event(
                    event_id=event.event_id,
                    event_digest=event.event_digest,
                    event_name=event.event_name,
                    source_persona_id=event.source_persona_id,
                    target_persona_id=event.target_persona_id,
                    following=event.following,
                    version=event.version,
                    occurred_at=event.occurred_at,
                )
        except Exception as error:
            attempts = self._projection.record_source_failure(
                failure_id,
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
            self._redis.xack(PERSONA_RELATIONSHIP_STREAM, CONSUMER_GROUP, stream_id)
            self._projection.clear_source_failure(failure_id)
            return
        self._redis.xack(PERSONA_RELATIONSHIP_STREAM, CONSUMER_GROUP, stream_id)
        self._projection.clear_source_failure(failure_id)

    def process_once(self) -> int:
        try:
            processed = self._process_once_inner()
        except Exception:
            record_projection_outcome("persona_relationship", "error")
            raise
        record_projection_outcome("persona_relationship", "ok")
        return processed

    def _process_once_inner(self) -> int:
        self.ensure_group()
        seen: set[str] = set()
        messages: list[tuple[str, dict[str, str]]] = []
        for stream_id, values in (*self._claimed(), *self._new()):
            if stream_id in seen:
                continue
            seen.add(stream_id)
            messages.append((stream_id, values))
        first_error: Exception | None = None
        processed = 0
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
            raise RuntimeError("Persona relationship consumer is already started")
        self._thread = threading.Thread(
            target=self._run,
            name="recommendation-candidate-persona-relationship",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
