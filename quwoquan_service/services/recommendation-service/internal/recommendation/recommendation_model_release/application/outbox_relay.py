from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import uuid4

from ..domain.outbox import (
    OutboxEvent,
    TransactionalOutbox,
    validate_model_release_event_payload,
)

OUTBOX_LEASE_SECONDS = 30.0
_LOGGER = logging.getLogger(__name__)


class OutboxPublisher(Protocol):
    def publish(self, event: OutboxEvent) -> None: ...


class RecommendationModelReleaseOutboxRelay:
    def __init__(
        self,
        outbox: TransactionalOutbox,
        publisher: OutboxPublisher,
        *,
        interval_seconds: float = 1.0,
    ) -> None:
        if outbox is None or publisher is None:
            raise ValueError("model release outbox and publisher are required")
        if interval_seconds <= 0:
            raise ValueError("model release outbox interval must be positive")
        self._outbox = outbox
        self._publisher = publisher
        self._interval_seconds = interval_seconds
        self._owner_id = f"recommendation-model-release-relay-{uuid4()}"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._health_lock = threading.Lock()
        self._last_successful_scan: datetime | None = None
        self._last_failure: Exception | None = None

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    def drain(self, limit: int = 100) -> int:
        bounded_limit = limit if 0 < limit <= 200 else 100
        published = 0
        while published < bounded_limit:
            now = self._now()
            event = self._outbox.claim_pending_outbox(
                self._owner_id,
                now,
                OUTBOX_LEASE_SECONDS,
            )
            if event is None:
                self._record_success(now, recovered=published > 0)
                return published
            try:
                self._validate(event)
            except Exception as error:
                self._schedule_retry(event, now, "invalid_event")
                self._record_failure(error)
                raise
            try:
                self._publisher.publish(event)
            except Exception as error:
                self._schedule_retry(event, now, "publish_failed")
                self._record_failure(error)
                raise
            try:
                self._outbox.mark_outbox_published(
                    event.event_id,
                    self._owner_id,
                    self._now(),
                )
            except Exception as error:
                self._record_failure(error)
                raise
            published += 1
        self._record_success(self._now(), recovered=published > 0)
        return published

    def _schedule_retry(
        self,
        event: OutboxEvent,
        now: datetime,
        failure_code: str,
    ) -> None:
        attempt = max(1, min(event.attempt_count, 6))
        self._outbox.schedule_outbox_retry(
            event.event_id,
            self._owner_id,
            now + timedelta(seconds=2 ** (attempt - 1)),
            failure_code,
        )

    @staticmethod
    def _validate(event: OutboxEvent) -> None:
        if (
            not event.event_id.strip()
            or not event.aggregate_id.strip()
            or event.aggregate_version <= 0
            or event.occurred_at is None
            or event.occurred_at.tzinfo is None
            or not isinstance(event.payload, dict)
            or not event.payload
        ):
            raise ValueError("model release outbox event is incomplete")
        validate_model_release_event_payload(event.event_type, event.payload)
        if event.payload["id"] != event.aggregate_id:
            raise ValueError("model release event aggregate identity does not match")
        json.dumps(
            event.payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    def run_once(self) -> None:
        try:
            self.drain()
        except Exception:
            _LOGGER.exception("recommendation model release outbox drain failed")

    def _run(self) -> None:
        self.run_once()
        while not self._stop.wait(self._interval_seconds):
            self.run_once()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="recommendation-model-release-outbox",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(2.0, self._interval_seconds * 2))
        self._thread = None

    def healthy(self, *, max_staleness_seconds: float = 10.0) -> bool:
        with self._health_lock:
            last_scan = self._last_successful_scan
            last_failure = self._last_failure
        if last_failure is not None or last_scan is None:
            return False
        return (self._now() - last_scan).total_seconds() <= max_staleness_seconds

    def _record_success(self, at: datetime, *, recovered: bool) -> None:
        with self._health_lock:
            self._last_successful_scan = at
            if recovered:
                self._last_failure = None

    def _record_failure(self, error: Exception) -> None:
        with self._health_lock:
            self._last_failure = error


__all__ = ["RecommendationModelReleaseOutboxRelay"]
