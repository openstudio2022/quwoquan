from __future__ import annotations

from datetime import datetime
from typing import Any

from redis.exceptions import RedisError, ResponseError

from ..application.experiment_policy_stream import (
    ExperimentPolicyStreamRecord,
    ExperimentPolicyStreamUnavailable,
)


STREAM = "events.ops.experiment_policy_activated"
CONSUMER_GROUP = "recommendation-service"
DLQ = "events.ops.experiment_policy_activated.recommendation.dlq"
RETENTION_SECONDS = 7 * 24 * 60 * 60


class RedisExperimentPolicyStream:
    def __init__(self, redis_client: Any) -> None:
        if redis_client is None:
            raise ValueError("recommendation Experiment policy stream requires Redis")
        self._redis = redis_client

    def ensure_consumer_group(self) -> None:
        try:
            self._redis.xgroup_create(
                STREAM,
                CONSUMER_GROUP,
                id="0-0",
                mkstream=True,
            )
        except ResponseError as error:
            if "BUSYGROUP" in str(error):
                return
            raise _unavailable("prepare") from error
        except RedisError as error:
            raise _unavailable("prepare") from error

    def read(self, *, consumer: str) -> tuple[ExperimentPolicyStreamRecord, ...]:
        try:
            claimed = self._redis.xautoclaim(
                STREAM,
                CONSUMER_GROUP,
                consumer,
                min_idle_time=30_000,
                start_id="0-0",
                count=50,
            )
            fresh = self._redis.xreadgroup(
                CONSUMER_GROUP,
                consumer,
                {STREAM: ">"},
                count=50,
            )
        except RedisError as error:
            raise _unavailable("read") from error

        claimed_entries = (
            claimed[1]
            if isinstance(claimed, (list, tuple)) and len(claimed) > 1
            else []
        )
        records = [
            ExperimentPolicyStreamRecord(_text(stream_id), _values(fields))
            for stream_id, fields in claimed_entries
        ]
        for _stream, entries in fresh or []:
            records.extend(
                ExperimentPolicyStreamRecord(_text(stream_id), _values(fields))
                for stream_id, fields in entries
            )
        return tuple(records)

    def replay(self) -> tuple[ExperimentPolicyStreamRecord, ...]:
        """Read the retained stream history without consuming or acknowledging.

        A projection volume can be recreated while the Redis stream keeps its
        already-acknowledged ExperimentPolicyActivated facts. XRANGE rebuilds
        the projection from the same authored truth source; it never touches
        consumer-group state.
        """

        try:
            entries = self._redis.xrange(STREAM, min="-", max="+")
        except RedisError as error:
            raise _unavailable("replay") from error
        return tuple(
            ExperimentPolicyStreamRecord(_text(stream_id), _values(fields))
            for stream_id, fields in entries or []
        )

    def acknowledge(self, stream_id: str) -> None:
        try:
            self._redis.xack(STREAM, CONSUMER_GROUP, stream_id)
        except RedisError as error:
            raise _unavailable("acknowledge") from error

    def dead_letter(
        self,
        *,
        stream_id: str,
        event_id: str,
        reason: str,
        dead_lettered_at: datetime,
    ) -> None:
        try:
            self._redis.xadd(
                DLQ,
                {
                    "sourceStreamId": stream_id,
                    "eventId": event_id,
                    "reason": reason[:1024],
                    "deadLetteredAt": dead_lettered_at.isoformat(),
                },
            )
            server_time = self._redis.time()
            cutoff_ms = (int(server_time[0]) - RETENTION_SECONDS) * 1000
            self._redis.xtrim(
                DLQ,
                minid=f"{max(cutoff_ms, 0)}-0",
                approximate=False,
            )
            self._redis.expire(DLQ, RETENTION_SECONDS)
        except RedisError as error:
            raise _unavailable("dead-letter") from error


def _unavailable(operation: str) -> ExperimentPolicyStreamUnavailable:
    return ExperimentPolicyStreamUnavailable(
        f"recommendation Experiment policy stream {operation} unavailable"
    )


def _text(value: Any) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def _values(fields: dict[Any, Any]) -> dict[str, str]:
    return {_text(key): _text(value) for key, value in fields.items()}
