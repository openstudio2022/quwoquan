from __future__ import annotations

import threading
import time
from typing import Any

from redis.exceptions import ResponseError


class BoundedEmptyPollBackoff:
    """Cancellation-aware backoff for successful empty stream polls."""

    def __init__(
        self,
        *,
        initial_seconds: float = 0.1,
        maximum_seconds: float = 0.5,
    ) -> None:
        if initial_seconds <= 0 or maximum_seconds < initial_seconds:
            raise ValueError("stream poll backoff bounds are invalid")
        self._initial_seconds = initial_seconds
        self._maximum_seconds = maximum_seconds
        self._empty_polls = 0
        self._next_empty_delay = initial_seconds

    def next_delay(self, processed_count: int) -> float:
        if processed_count > 0:
            self._empty_polls = 0
            self._next_empty_delay = self._initial_seconds
            return 0.0
        self._empty_polls += 1
        delay = self._next_empty_delay
        self._next_empty_delay = min(delay * 2, self._maximum_seconds)
        return delay

    def wait(self, stop: threading.Event, *, processed_count: int) -> bool:
        return stop.wait(self.next_delay(processed_count))


class StreamConsumerRedis:
    """Redis facade governing group initialization and successful empty polls."""

    def __init__(self, inner: Any) -> None:
        if inner is None:
            raise ValueError("stream consumer Redis client is required")
        self._inner = inner
        self._group_lock = threading.Lock()
        self._initialized_groups: set[tuple[str, str]] = set()
        self._poll_lock = threading.Lock()
        self._polls: dict[tuple[str, str], BoundedEmptyPollBackoff] = {}
        self._next_poll_at: dict[tuple[str, str], float] = {}
        self._poll_shutdown = threading.Event()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def xgroup_create(
        self,
        name: str,
        groupname: str,
        id: str = "$",
        mkstream: bool = False,
        entries_read: int | None = None,
    ) -> bool:
        key = (str(name).strip(), str(groupname).strip())
        if not all(key):
            raise ValueError("stream and consumer group are required")
        with self._group_lock:
            if key in self._initialized_groups:
                return True
            try:
                result = self._inner.xgroup_create(
                    name,
                    groupname,
                    id=id,
                    mkstream=mkstream,
                    entries_read=entries_read,
                )
            except ResponseError as error:
                if not str(error).startswith("BUSYGROUP "):
                    raise
                result = True
            self._initialized_groups.add(key)
            return bool(result)

    @staticmethod
    def _stream_key(
        groupname: str,
        consumername: str,
        streams: dict[str, str],
    ) -> tuple[str, str, str]:
        names = "\x00".join(sorted(str(stream).strip() for stream in streams))
        return names, str(groupname).strip(), str(consumername).strip()

    def _wait_for_poll_slot(self, key: tuple[str, ...]) -> bool:
        while True:
            with self._poll_lock:
                delay = max(self._next_poll_at.get(key, 0.0) - time.monotonic(), 0.0)
            if delay <= 0:
                return not self._poll_shutdown.is_set()
            if self._poll_shutdown.wait(delay):
                return False

    @staticmethod
    def _message_count(result: Any) -> int:
        return sum(len(entries) for _stream, entries in (result or []))

    def _record_poll(self, key: tuple[str, ...], result: Any) -> None:
        count = self._message_count(result)
        with self._poll_lock:
            backoff = self._polls.setdefault(key, BoundedEmptyPollBackoff())
            delay = backoff.next_delay(count)
            if delay <= 0:
                self._next_poll_at.pop(key, None)
            else:
                self._next_poll_at[key] = time.monotonic() + delay

    def _record_poll_failure(self, key: tuple[str, ...]) -> None:
        with self._poll_lock:
            backoff = self._polls.setdefault(key, BoundedEmptyPollBackoff())
            self._next_poll_at[key] = time.monotonic() + backoff.next_delay(0)

    def _record_delivery(self, key: tuple[str, ...], count: int) -> None:
        if count <= 0:
            return
        with self._poll_lock:
            backoff = self._polls.setdefault(key, BoundedEmptyPollBackoff())
            backoff.next_delay(count)
            self._next_poll_at.pop(key, None)

    @staticmethod
    def _is_no_group(error: Exception) -> bool:
        return isinstance(error, ResponseError) and str(error).startswith("NOGROUP ")

    def _invalidate_groups(self, groupname: str, streams: list[str]) -> None:
        group = str(groupname).strip()
        with self._group_lock:
            for stream in streams:
                self._initialized_groups.discard((str(stream).strip(), group))

    def xautoclaim(
        self,
        name: str,
        groupname: str,
        consumername: str,
        min_idle_time: int,
        start_id: str = "0-0",
        count: int | None = None,
        justid: bool = False,
    ) -> Any:
        key = (
            str(name).strip(),
            str(groupname).strip(),
            str(consumername).strip(),
        )
        if not self._wait_for_poll_slot(key):
            return ["0-0", [], []]
        try:
            result = self._inner.xautoclaim(
                name,
                groupname,
                consumername,
                min_idle_time=min_idle_time,
                start_id=start_id,
                count=count,
                justid=justid,
            )
        except Exception as error:
            if self._is_no_group(error):
                self._invalidate_groups(groupname, [name])
            self._record_poll_failure(key)
            raise
        entries = result[1] if isinstance(result, (list, tuple)) and len(result) > 1 else []
        self._record_delivery(key, len(entries))
        return result

    def xreadgroup(
        self,
        groupname: str,
        consumername: str,
        streams: dict[str, str],
        count: int | None = None,
        block: int | None = None,
        noack: bool = False,
    ) -> Any:
        key = self._stream_key(groupname, consumername, streams)
        if not self._wait_for_poll_slot(key):
            return []
        try:
            result = self._inner.xreadgroup(
                groupname,
                consumername,
                streams,
                count=count,
                block=block,
                noack=noack,
            )
        except Exception as error:
            if self._is_no_group(error):
                self._invalidate_groups(groupname, list(streams))
            self._record_poll_failure(key)
            raise
        self._record_poll(key, result)
        return result

    def interrupt_stream_waits(self) -> None:
        self._poll_shutdown.set()

    def close(self, *args: object, **kwargs: object) -> Any:
        self.interrupt_stream_waits()
        return self._inner.close(*args, **kwargs)
