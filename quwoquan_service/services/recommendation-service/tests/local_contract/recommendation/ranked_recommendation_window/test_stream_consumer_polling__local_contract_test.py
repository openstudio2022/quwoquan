from __future__ import annotations

import threading
import time

import pytest
from redis.exceptions import ResponseError

from stream_redis import BoundedEmptyPollBackoff, StreamConsumerRedis


class _RedisSpy:
    def __init__(
        self,
        group_error: Exception | None = None,
        read_results: list[object] | None = None,
        claim_results: list[object] | None = None,
    ) -> None:
        self.group_error = group_error
        self.group_commands = 0
        self.read_results = list(read_results or [])
        self.read_commands = 0
        self.claim_results = list(claim_results or [])
        self.claim_commands = 0

    def xgroup_create(self, *_args: object, **_kwargs: object) -> bool:
        self.group_commands += 1
        if self.group_error is not None:
            raise self.group_error
        return True

    def xreadgroup(self, *_args: object, **_kwargs: object) -> object:
        self.read_commands += 1
        if self.read_results:
            result = self.read_results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        return []

    def xautoclaim(self, *_args: object, **_kwargs: object) -> object:
        self.claim_commands += 1
        if self.claim_results:
            result = self.claim_results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        return ["0-0", [], []]


def test_group_initialization_is_idempotent_under_concurrency() -> None:
    inner = _RedisSpy()
    client = StreamConsumerRedis(inner)
    workers = [
        threading.Thread(
            target=lambda: client.xgroup_create(
                "events:recommendation",
                "recommendation-consumers",
                id="0-0",
                mkstream=True,
            )
        )
        for _ in range(32)
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=1.0)

    assert inner.group_commands == 1


def test_only_typed_busy_group_is_classified_as_initialized() -> None:
    busy = _RedisSpy(ResponseError("BUSYGROUP Consumer Group name already exists"))
    client = StreamConsumerRedis(busy)
    assert client.xgroup_create("events", "group", id="0-0", mkstream=True)
    assert client.xgroup_create("events", "group", id="0-0", mkstream=True)
    assert busy.group_commands == 1

    misleading = StreamConsumerRedis(
        _RedisSpy(RuntimeError("upstream text contained BUSYGROUP but was not Redis"))
    )
    with pytest.raises(RuntimeError):
        misleading.xgroup_create("events", "group", id="0-0", mkstream=True)

    wrong_code = StreamConsumerRedis(_RedisSpy(ResponseError("NOGROUP missing group")))
    with pytest.raises(ResponseError):
        wrong_code.xgroup_create("events", "group", id="0-0", mkstream=True)


def test_empty_poll_backoff_is_bounded_cancelable_and_resets_on_delivery() -> None:
    backoff = BoundedEmptyPollBackoff(
        initial_seconds=0.005,
        maximum_seconds=0.02,
    )
    stop = threading.Event()

    assert [backoff.next_delay(0) for _ in range(5)] == [
        0.005,
        0.01,
        0.02,
        0.02,
        0.02,
    ]
    assert backoff.next_delay(1) == 0.0
    assert backoff.next_delay(0) == 0.005

    stop.set()
    started = time.monotonic()
    assert backoff.wait(stop, processed_count=0)
    assert time.monotonic() - started < 0.02


def test_empty_poll_backoff_caps_the_exponent_before_long_idle_overflows() -> None:
    backoff = BoundedEmptyPollBackoff(
        initial_seconds=0.1,
        maximum_seconds=0.5,
    )

    delays = [backoff.next_delay(0) for _ in range(2048)]

    assert delays[-1] == 0.5
    assert max(delays) == 0.5


def test_stream_facade_bounds_empty_commands_and_resets_after_message() -> None:
    message = [[b"events", [[b"1-0", {b"eventId": b"event-1"}]]]]
    inner = _RedisSpy(read_results=[[], [], message, []])
    client = StreamConsumerRedis(inner)
    streams = {"events": ">"}

    started = time.monotonic()
    assert client.xreadgroup("group", "consumer", streams) == []
    assert client.xreadgroup("group", "consumer", streams) == []
    assert client.xreadgroup("group", "consumer", streams) == message
    bounded_elapsed = time.monotonic() - started
    assert bounded_elapsed >= 0.29
    assert inner.read_commands == 3

    # A delivered message resets the next poll to immediate rather than
    # carrying a stale idle delay into live traffic.
    started = time.monotonic()
    assert client.xreadgroup("group", "consumer", streams) == []
    assert time.monotonic() - started < 0.05

    blocked_result: list[object] = []
    blocked = threading.Thread(
        target=lambda: blocked_result.append(
            client.xreadgroup("group", "consumer", streams)
        )
    )
    blocked.start()
    time.sleep(0.01)
    client.interrupt_stream_waits()
    blocked.join(timeout=0.1)
    assert not blocked.is_alive()
    assert blocked_result == [[]]
    assert inner.read_commands == 4


def test_stream_facade_backs_off_transient_reclaim_failures() -> None:
    inner = _RedisSpy(
        claim_results=[
            RuntimeError("redis unavailable"),
            ["0-0", [], []],
        ]
    )
    client = StreamConsumerRedis(inner)
    with pytest.raises(RuntimeError):
        client.xautoclaim(
            "events",
            "group",
            "consumer",
            min_idle_time=30_000,
        )

    started = time.monotonic()
    assert client.xautoclaim(
        "events",
        "group",
        "consumer",
        min_idle_time=30_000,
    ) == ["0-0", [], []]
    assert time.monotonic() - started >= 0.09
    assert inner.claim_commands == 2


def test_stream_backoff_is_isolated_per_consumer() -> None:
    inner = _RedisSpy()
    client = StreamConsumerRedis(inner)
    assert client.xreadgroup("group", "consumer-a", {"events": ">"}) == []

    started = time.monotonic()
    assert client.xreadgroup("group", "consumer-b", {"events": ">"}) == []
    assert time.monotonic() - started < 0.05
    assert inner.read_commands == 2


def test_no_group_invalidates_only_the_missing_group() -> None:
    inner = _RedisSpy(read_results=[ResponseError("NOGROUP missing group")])
    client = StreamConsumerRedis(inner)
    assert client.xgroup_create("events", "group", id="0-0", mkstream=True)
    with pytest.raises(ResponseError):
        client.xreadgroup("group", "consumer", {"events": ">"})
    assert client.xgroup_create("events", "group", id="0-0", mkstream=True)
    assert inner.group_commands == 2
