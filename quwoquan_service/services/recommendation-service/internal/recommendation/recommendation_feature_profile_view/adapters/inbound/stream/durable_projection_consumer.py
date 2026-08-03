from __future__ import annotations

from datetime import datetime, timezone
import threading
from typing import Any, Callable


MAX_ATTEMPTS = 5
RETENTION_SECONDS = 7 * 24 * 60 * 60


def text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def values(raw: dict[Any, Any]) -> dict[str, str]:
    return {text(key): text(value) for key, value in raw.items()}


class DurableProjectionConsumer:
    """Object-local Redis stream consumer with retry, claim and bounded DLQ."""

    def __init__(
        self,
        *,
        redis_client: Any,
        feature_store: Any,
        stream: str,
        dead_letter_stream: str,
        consumer_group: str,
        consumer: str,
        handler: Callable[[dict[str, str]], None],
        thread_name: str,
    ) -> None:
        if (
            redis_client is None
            or feature_store is None
            or not stream.strip()
            or not dead_letter_stream.strip()
            or not consumer_group.strip()
            or handler is None
        ):
            raise ValueError("durable projection consumer dependencies are required")
        self._redis = redis_client
        self._store = feature_store
        self._stream = stream
        self._dead_letter_stream = dead_letter_stream
        self._consumer_group = consumer_group
        self._consumer = consumer.strip() or thread_name
        self._handler = handler
        self._thread_name = thread_name
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_success: datetime | None = None
        self._last_failure: Exception | None = None

    def ensure_group(self) -> None:
        try:
            self._redis.xgroup_create(
                self._stream,
                self._consumer_group,
                id="0-0",
                mkstream=True,
            )
        except Exception as error:
            if "BUSYGROUP" not in str(error):
                raise

    def _messages(self, raw: Any) -> list[tuple[str, dict[str, str]]]:
        messages: list[tuple[str, dict[str, str]]] = []
        for _stream, entries in raw or []:
            for stream_id, fields in entries:
                messages.append((text(stream_id), values(fields)))
        return messages

    def _claimed(self) -> list[tuple[str, dict[str, str]]]:
        result = self._redis.xautoclaim(
            self._stream,
            self._consumer_group,
            self._consumer,
            min_idle_time=30_000,
            start_id="0-0",
            count=50,
        )
        entries = result[1] if isinstance(result, (list, tuple)) and len(result) > 1 else []
        return [(text(stream_id), values(fields)) for stream_id, fields in entries]

    def _new(self) -> list[tuple[str, dict[str, str]]]:
        return self._messages(
            self._redis.xreadgroup(
                self._consumer_group,
                self._consumer,
                {self._stream: ">"},
                count=50,
            )
        )

    def _trim_and_expire(self) -> None:
        server_time = self._redis.time()
        cutoff_ms = (int(server_time[0]) - RETENTION_SECONDS) * 1000
        self._redis.xtrim(
            self._dead_letter_stream,
            minid=f"{max(cutoff_ms, 0)}-0",
            approximate=False,
        )
        self._redis.expire(self._dead_letter_stream, RETENTION_SECONDS)

    def _dead_letter(
        self,
        *,
        stream_id: str,
        event_values: dict[str, str],
        attempts: int,
        error: Exception,
    ) -> None:
        self._redis.xadd(
            self._dead_letter_stream,
            {
                "sourceStream": self._stream,
                "streamId": stream_id,
                "eventId": event_values.get("eventId", ""),
                "eventName": event_values.get("eventName", "")
                or event_values.get("eventType", ""),
                "attempts": str(attempts),
                "error": str(error)[:1024],
                "deadLetteredAt": datetime.now(timezone.utc).isoformat(),
            },
        )
        self._trim_and_expire()

    def _process(self, stream_id: str, event_values: dict[str, str]) -> None:
        failure_id = f"{self._consumer_group}:{stream_id}"
        try:
            self._handler(event_values)
        except Exception as error:
            attempts = self._store.record_source_failure(
                failure_id,
                event_values.get("eventId", ""),
                error,
            )
            if attempts < MAX_ATTEMPTS:
                raise
            self._dead_letter(
                stream_id=stream_id,
                event_values=event_values,
                attempts=attempts,
                error=error,
            )
            self._redis.xack(self._stream, self._consumer_group, stream_id)
            self._store.clear_source_failure(failure_id)
            return
        self._redis.xack(self._stream, self._consumer_group, stream_id)
        self._store.clear_source_failure(failure_id)

    def process_once(self) -> int:
        self.ensure_group()
        seen: set[str] = set()
        messages: list[tuple[str, dict[str, str]]] = []
        for stream_id, event_values in (*self._claimed(), *self._new()):
            if stream_id in seen:
                continue
            seen.add(stream_id)
            messages.append((stream_id, event_values))
        first_error: Exception | None = None
        processed = 0
        for stream_id, event_values in messages:
            try:
                self._process(stream_id, event_values)
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
            raise RuntimeError("durable projection consumer is already started")
        self._thread = threading.Thread(
            target=self._run,
            name=self._thread_name,
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
