from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import threading
from typing import Any, Protocol


USER_ACCOUNT_STREAM = "events.user.account"
USER_ACCOUNT_RESTRICTION_DLQ = (
    "events.user.account.recommendation-candidate-restriction.dlq"
)

from internal.recommendation.recommendation_candidate_index_view.adapters.inbound.stream.projection_metrics import (
    record_projection_outcome,
)
CONSUMER_GROUP = "recommendation-candidate-account-restriction"
MAX_ATTEMPTS = 5
RETENTION_SECONDS = 7 * 24 * 60 * 60
SUPPORTED_EVENTS = {"UserSuspended", "UserRestored"}


class SubjectClosureReader(Protocol):
    def exists(self, subject_id: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class UserAccountRestrictionEvent:
    event_id: str
    event_name: str
    account_id: str
    account_version: int
    subject_ids: tuple[str, ...]
    auth_epoch: int
    decision_ref: str
    occurred_at: datetime
    event_digest: str

    @property
    def restricted(self) -> bool:
        return self.event_name == "UserSuspended"


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _values(raw: dict[Any, Any]) -> dict[str, str]:
    return {_text(key): _text(value) for key, value in raw.items()}


def _parse_time(value: Any) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("account restriction occurredAt is required")
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("account restriction occurredAt must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def decode_user_account_restriction(
    values: dict[str, str],
) -> UserAccountRestrictionEvent | None:
    event_name = values.get("eventName", "").strip()
    if event_name not in SUPPORTED_EVENTS:
        return None
    event_id = values.get("eventId", "").strip()
    account_id = values.get("accountId", "").strip()
    try:
        account_version = int(values.get("accountVersion", ""))
    except ValueError as error:
        raise ValueError("account restriction accountVersion is invalid") from error
    try:
        payload = json.loads(values.get("payload", ""))
    except json.JSONDecodeError as error:
        raise ValueError("account restriction payload is invalid JSON") from error
    if not isinstance(payload, dict) or set(payload) != {
        "userId",
        "personaIds",
        "accountState",
        "authEpoch",
        "decisionRef",
        "occurredAt",
    }:
        raise ValueError("account restriction payload fields are invalid")
    user_id = str(payload.get("userId") or "").strip()
    persona_ids = payload.get("personaIds")
    if not isinstance(persona_ids, list):
        raise ValueError("account restriction personaIds must be an array")
    normalized_personas = tuple(sorted(str(value).strip() for value in persona_ids))
    if (
        any(not value for value in normalized_personas)
        or len(set(normalized_personas)) != len(normalized_personas)
    ):
        raise ValueError("account restriction personaIds must be non-empty and unique")
    try:
        auth_epoch = int(payload.get("authEpoch"))
    except (TypeError, ValueError) as error:
        raise ValueError("account restriction authEpoch is invalid") from error
    decision_ref = str(payload.get("decisionRef") or "").strip()
    occurred_at = _parse_time(values.get("occurredAt"))
    if _parse_time(payload.get("occurredAt")) != occurred_at:
        raise ValueError("account restriction payload/envelope occurredAt mismatch")
    expected_state = "suspended" if event_name == "UserSuspended" else "active"
    if (
        not event_id
        or not account_id
        or account_version <= 0
        or user_id != account_id
        or str(payload.get("accountState") or "").strip() != expected_state
        or auth_epoch <= 0
        or not decision_ref
    ):
        raise ValueError("account restriction identity or state is invalid")
    subject_ids = tuple(sorted({account_id, user_id, *normalized_personas}))
    canonical = {
        "accountId": account_id,
        "accountVersion": account_version,
        "authEpoch": auth_epoch,
        "decisionRef": decision_ref,
        "eventId": event_id,
        "eventName": event_name,
        "occurredAt": occurred_at.isoformat(),
        "subjectIds": subject_ids,
    }
    event_digest = hashlib.sha256(
        json.dumps(
            canonical,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return UserAccountRestrictionEvent(
        event_id=event_id,
        event_name=event_name,
        account_id=account_id,
        account_version=account_version,
        subject_ids=subject_ids,
        auth_epoch=auth_epoch,
        decision_ref=decision_ref,
        occurred_at=occurred_at,
        event_digest=event_digest,
    )


class UserAccountRestrictionConsumer:
    def __init__(
        self,
        *,
        redis_client: Any,
        projection: Any,
        subject_closures: SubjectClosureReader,
        consumer: str,
    ) -> None:
        self._redis = redis_client
        self._projection = projection
        self._subject_closures = subject_closures
        self._consumer = consumer.strip() or "recommendation-candidate-restriction"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_success: datetime | None = None
        self._last_failure: Exception | None = None

    def ensure_group(self) -> None:
        try:
            self._redis.xgroup_create(
                USER_ACCOUNT_STREAM,
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
            USER_ACCOUNT_RESTRICTION_DLQ,
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
        self._trim_and_expire(USER_ACCOUNT_RESTRICTION_DLQ)

    def _process(self, stream_id: str, values: dict[str, str]) -> None:
        failure_id = f"account-restriction:{stream_id}"
        try:
            event = decode_user_account_restriction(values)
            if event is not None:
                terminal = any(
                    self._subject_closures.exists(subject_id)
                    for subject_id in event.subject_ids
                )
                self._projection.apply_account_restriction_event(
                    event_id=event.event_id,
                    event_digest=event.event_digest,
                    account_id=event.account_id,
                    account_version=event.account_version,
                    subject_ids=event.subject_ids,
                    restricted=event.restricted,
                    terminal=terminal,
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
            self._redis.xack(USER_ACCOUNT_STREAM, CONSUMER_GROUP, stream_id)
            self._projection.clear_source_failure(failure_id)
            return
        self._redis.xack(USER_ACCOUNT_STREAM, CONSUMER_GROUP, stream_id)
        self._projection.clear_source_failure(failure_id)

    def process_once(self) -> int:
        try:
            processed = self._process_once_inner()
        except Exception:
            record_projection_outcome("user_account_restriction", "error")
            raise
        record_projection_outcome("user_account_restriction", "ok")
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
            raise RuntimeError("User account restriction consumer is already started")
        self._thread = threading.Thread(
            target=self._run,
            name="recommendation-candidate-account-restriction",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
