from __future__ import annotations

from datetime import datetime, timezone
import json
import threading
from typing import Any

from ....application.model_runtime_coordinator import (
    RecommendationModelRuntimeCoordinator,
)


STREAM = "events.recommendation.model_releases"
CONSUMER_GROUP = "recommendation-model-runtime"
DLQ = "events.recommendation.model_releases.runtime.dlq"
RETENTION_SECONDS = 7 * 24 * 60 * 60
SUPPORTED_EVENTS = {
    "RecommendationModelReleaseStaged",
    "RecommendationModelReleaseActivated",
    "RecommendationModelReleaseRetired",
}


class ModelReleaseRuntimeConsumer:
    def __init__(
        self,
        *,
        redis_client: Any,
        coordinator: RecommendationModelRuntimeCoordinator,
        consumer: str,
    ) -> None:
        if redis_client is None or coordinator is None:
            raise ValueError("model release runtime consumer requires Redis and coordinator")
        self._redis = redis_client
        self._coordinator = coordinator
        self._consumer = consumer.strip() or "recommendation-model-runtime"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_success: datetime | None = None
        self._last_failure: Exception | None = None

    def ensure_group(self) -> None:
        try:
            self._redis.xgroup_create(
                STREAM,
                CONSUMER_GROUP,
                id="0-0",
                mkstream=True,
            )
        except Exception as error:
            if "BUSYGROUP" not in str(error):
                raise

    def process_once(self) -> int:
        self.ensure_group()
        claimed = self._redis.xautoclaim(
            STREAM,
            CONSUMER_GROUP,
            self._consumer,
            min_idle_time=30_000,
            start_id="0-0",
            count=50,
        )
        claimed_entries = (
            claimed[1]
            if isinstance(claimed, (list, tuple)) and len(claimed) > 1
            else []
        )
        fresh = self._redis.xreadgroup(
            CONSUMER_GROUP,
            self._consumer,
            {STREAM: ">"},
            count=50,
        )
        messages: list[tuple[str, dict[str, str]]] = []
        for stream_id, fields in claimed_entries:
            messages.append((_text(stream_id), _values(fields)))
        for _stream, entries in fresh or []:
            for stream_id, fields in entries:
                messages.append((_text(stream_id), _values(fields)))
        processed = 0
        seen: set[str] = set()
        for stream_id, values in messages:
            if stream_id in seen:
                continue
            seen.add(stream_id)
            self._process(stream_id, values)
            processed += 1
        self._last_success = datetime.now(timezone.utc)
        self._last_failure = None
        return processed

    def healthy(self, *, max_staleness_seconds: float = 10.0) -> bool:
        if self._last_success is None or self._last_failure is not None:
            return False
        return (
            datetime.now(timezone.utc) - self._last_success
        ).total_seconds() <= max_staleness_seconds

    def _process(self, stream_id: str, values: dict[str, str]) -> None:
        try:
            event_type, payload = _decode(values)
            self._coordinator.apply_release_event(event_type, payload)
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            self._redis.xadd(
                DLQ,
                {
                    "sourceStreamId": stream_id,
                    "eventId": values.get("eventId", ""),
                    "reason": str(error)[:1024],
                    "deadLetteredAt": datetime.now(timezone.utc).isoformat(),
                },
            )
            self._refresh_retention(DLQ)
        self._redis.xack(STREAM, CONSUMER_GROUP, stream_id)

    def _refresh_retention(self, stream: str) -> None:
        server_time = self._redis.time()
        cutoff_ms = (int(server_time[0]) - RETENTION_SECONDS) * 1000
        self._redis.xtrim(
            stream,
            minid=f"{max(cutoff_ms, 0)}-0",
            approximate=False,
        )
        self._redis.expire(stream, RETENTION_SECONDS)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.process_once()
            except Exception as error:
                self._last_failure = error
            self._stop.wait(0.25)

    def start(self) -> None:
        self.ensure_group()
        if self._thread is not None:
            raise RuntimeError("model release runtime consumer already started")
        self._thread = threading.Thread(
            target=self._run,
            name="recommendation-model-runtime",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None


def _decode(values: dict[str, str]) -> tuple[str, dict[str, Any]]:
    event_type = values.get("eventType", "").strip()
    event_id = values.get("eventId", "").strip()
    aggregate_id = values.get("aggregateId", "").strip()
    if (
        event_type not in SUPPORTED_EVENTS
        or not event_id
        or values.get("aggregateType") != "RecommendationModelRelease"
        or not aggregate_id
        or int(values.get("aggregateVersion") or 0) <= 0
    ):
        raise ValueError("invalid recommendation model release event identity")
    payload = json.loads(values.get("payload") or "")
    if not isinstance(payload, dict) or str(payload.get("id") or "") != aggregate_id:
        raise ValueError("recommendation model release aggregate identity mismatch")
    return event_type, payload


def _text(value: Any) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def _values(fields: dict[Any, Any]) -> dict[str, str]:
    return {_text(key): _text(value) for key, value in fields.items()}


__all__ = [
    "CONSUMER_GROUP",
    "DLQ",
    "ModelReleaseRuntimeConsumer",
    "STREAM",
]
