from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import threading
from typing import Any, Protocol

from redis.exceptions import ResponseError

from internal.recommendation.recommendation_subject_closure_fact.application.appender import (
    Appender,
    SubjectClosureFact,
)


USER_ACCOUNT_STREAM = "events.user.account"
USER_ACCOUNT_DLQ = "events.user.account.recommendation-service.dlq"
CONSUMER_GROUP = "recommendation-subject-closure"
MAX_ATTEMPTS = 5
RETENTION_SECONDS = 7 * 24 * 60 * 60


class SubjectDataEraser(Protocol):
    def erase_subject(self, subject_id: str) -> int: ...


@dataclass(frozen=True, slots=True)
class UserAccountClosedEvent:
    event_id: str
    account_id: str
    account_version: int
    payload: dict[str, Any]
    occurred_at: datetime
    source_digest: str


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _values(raw: dict[Any, Any]) -> dict[str, str]:
    return {_text(key): _text(value) for key, value in raw.items()}


def _parse_time(value: Any) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("UserAccountClosed timestamp is required")
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("UserAccountClosed timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def decode_user_account_closed(values: dict[str, str]) -> UserAccountClosedEvent | None:
    event_name = values.get("eventName", "").strip()
    if event_name != "UserAccountClosed":
        return None
    event_id = values.get("eventId", "").strip()
    account_id = values.get("accountId", "").strip()
    expected_event_id = hashlib.sha256(
        f"UserAccountClosed:{account_id}".encode("utf-8")
    ).hexdigest()
    if not event_id or not account_id or event_id != expected_event_id:
        raise ValueError("UserAccountClosed event identity does not match accountId")
    try:
        account_version = int(values.get("accountVersion", ""))
    except ValueError as error:
        raise ValueError("UserAccountClosed accountVersion is invalid") from error
    if account_version <= 0:
        raise ValueError("UserAccountClosed accountVersion must be positive")
    payload = json.loads(values.get("payload", ""))
    if not isinstance(payload, dict):
        raise ValueError("UserAccountClosed payload must be an object")
    if (
        str(payload.get("userId") or "").strip() != account_id
        or str(payload.get("accountState") or "").strip() != "closed"
    ):
        raise ValueError("UserAccountClosed payload identity or state is invalid")
    persona_ids = payload.get("personaIds")
    if not isinstance(persona_ids, list):
        raise ValueError("UserAccountClosed personaIds must be an array")
    normalized_persona_ids = [str(value).strip() for value in persona_ids]
    if (
        any(not value for value in normalized_persona_ids)
        or len(set(normalized_persona_ids)) != len(normalized_persona_ids)
    ):
        raise ValueError("UserAccountClosed personaIds must be non-empty and unique")
    occurred_at = _parse_time(values.get("occurredAt"))
    updated_at = _parse_time(payload.get("updatedAt"))
    if occurred_at != updated_at:
        raise ValueError("UserAccountClosed occurredAt and updatedAt must match")
    canonical = {
        "accountId": account_id,
        "accountVersion": account_version,
        "eventId": event_id,
        "eventName": event_name,
        "occurredAt": occurred_at.isoformat(),
        "payload": payload,
    }
    source_digest = hashlib.sha256(
        json.dumps(
            canonical,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return UserAccountClosedEvent(
        event_id=event_id,
        account_id=account_id,
        account_version=account_version,
        payload=payload,
        occurred_at=occurred_at,
        source_digest=source_digest,
    )


class UserAccountClosedConsumer:
    def __init__(
        self,
        *,
        redis_client: Any,
        store: Any,
        erasers: tuple[SubjectDataEraser, ...],
        consumer: str,
    ) -> None:
        if not erasers:
            raise ValueError("recommendation subject closure requires local privacy erasers")
        self._redis = redis_client
        self._store = store
        self._appender = Appender(store)
        self._erasers = erasers
        self._consumer = consumer.strip() or "recommendation-subject-closure"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_success: datetime | None = None
        self._last_failure: Exception | None = None

    def ensure_group(self) -> None:
        try:
            self._redis.xgroup_create(USER_ACCOUNT_STREAM, CONSUMER_GROUP, id="0-0", mkstream=True)
        except ResponseError as error:
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
            USER_ACCOUNT_STREAM,
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
                {USER_ACCOUNT_STREAM: ">"},
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
            USER_ACCOUNT_DLQ,
            {
                "sourceStream": USER_ACCOUNT_STREAM,
                "streamId": stream_id,
                "eventId": values.get("eventId", ""),
                "eventName": values.get("eventName", ""),
                "attempts": str(attempts),
                "error": str(error)[:1024],
                "deadLetteredAt": datetime.now(timezone.utc).isoformat(),
            },
        )
        self._trim_and_expire(USER_ACCOUNT_DLQ)

    def _process(self, stream_id: str, values: dict[str, str]) -> None:
        try:
            event = decode_user_account_closed(values)
            if event is not None:
                now = datetime.now(timezone.utc)
                persisted, _created = self._appender.append(
                    SubjectClosureFact(
                        account_id=event.account_id,
                        subject_ids=tuple(
                            dict.fromkeys(
                                [
                                    event.account_id,
                                    *(
                                        str(value).strip()
                                        for value in event.payload.get("personaIds", [])
                                        if str(value).strip()
                                    ),
                                ]
                            )
                        ),
                        source_event_id=event.event_id,
                        source_digest=event.source_digest,
                        closed_at=event.occurred_at,
                        recorded_at=now,
                    )
                )
                for subject_id in persisted.subject_ids:
                    for eraser in self._erasers:
                        eraser.erase_subject(subject_id)
        except Exception as error:
            attempts = self._store.record_failure(
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
            self._redis.xack(USER_ACCOUNT_STREAM, CONSUMER_GROUP, stream_id)
            self._store.clear_failure(stream_id)
            return
        self._redis.xack(USER_ACCOUNT_STREAM, CONSUMER_GROUP, stream_id)
        self._store.clear_failure(stream_id)

    def process_once(self) -> int:
        self.ensure_group()
        seen: set[str] = set()
        messages = []
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
            raise RuntimeError("UserAccountClosed consumer is already started")
        self._thread = threading.Thread(
            target=self._run,
            name="recommendation-subject-closure",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
