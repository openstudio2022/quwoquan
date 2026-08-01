from __future__ import annotations

from datetime import datetime, timezone
import json
import threading
from typing import Any

from ....domain.experiment_policy import (
    EXPERIMENT_ID,
    ExperimentAssignments,
    ExperimentPolicy,
    PolicyVariant,
    canonical_policy,
)


STREAM = "events.ops.experiment_policy_activated"
CONSUMER_GROUP = "recommendation-service"
DLQ = "events.ops.experiment_policy_activated.recommendation.dlq"
RETENTION_SECONDS = 7 * 24 * 60 * 60


class ExperimentPolicyConsumer:
    def __init__(
        self,
        *,
        redis_client: Any,
        store: Any,
        assignments: ExperimentAssignments,
        consumer: str,
    ) -> None:
        if redis_client is None or store is None or assignments is None:
            raise ValueError(
                "recommendation Experiment policy consumer requires Redis, store and assignments"
            )
        self._redis = redis_client
        self._store = store
        self._assignments = assignments
        self._consumer = consumer.strip() or "recommendation-experiment-policy"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_success: datetime | None = None
        self._last_failure: Exception | None = None

    def ensure_group(self) -> None:
        try:
            self._redis.xgroup_create(STREAM, CONSUMER_GROUP, id="0-0", mkstream=True)
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
            policy = decode_policy(values)
            if policy is not None:
                effective = self._store.apply(policy)
                self._assignments.apply_policy(effective)
        except ValueError as error:
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
            return
        self._redis.xack(STREAM, CONSUMER_GROUP, stream_id)

    def _refresh_retention(self, stream: str) -> None:
        server_time = self._redis.time()
        cutoff_ms = (int(server_time[0]) - RETENTION_SECONDS) * 1000
        self._redis.xtrim(stream, minid=f"{max(cutoff_ms, 0)}-0", approximate=False)
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
            raise RuntimeError("recommendation Experiment policy consumer already started")
        self._thread = threading.Thread(
            target=self._run,
            name="recommendation-experiment-policy",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None


def decode_policy(values: dict[str, str]) -> ExperimentPolicy | None:
    if (
        values.get("eventType") != "ExperimentPolicyActivated"
        or not values.get("eventId")
        or values.get("producer") != "product-ops-service"
        or values.get("aggregateType") != "Experiment"
        or not values.get("experimentId")
    ):
        raise ValueError("invalid ExperimentPolicyActivated identity")
    try:
        payload = json.loads(values.get("payloadJson") or "")
    except json.JSONDecodeError as error:
        raise ValueError("invalid ExperimentPolicyActivated payload") from error
    if payload.get("id") != values["experimentId"]:
        raise ValueError("ExperimentPolicyActivated aggregate identity mismatch")
    if payload.get("id") != EXPERIMENT_ID:
        return None
    return canonical_policy(
        ExperimentPolicy(
            experiment_id=str(payload.get("id") or ""),
            revision=int(payload.get("version") or 0),
            status=str(payload.get("status") or ""),
            variants=tuple(
                PolicyVariant(
                    key=str(item.get("key") or ""),
                    allocation_basis_points=int(
                        item.get("allocationBasisPoints") or 0
                    ),
                )
                for item in payload.get("variants") or []
            ),
            starts_at=_timestamp(payload.get("startsAt")),
            ends_at=_timestamp(payload.get("endsAt")),
            updated_at=_timestamp(payload.get("updatedAt"))
            or datetime.min.replace(tzinfo=timezone.utc),
            digest="",
        )
    )


def _timestamp(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _text(value: Any) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def _values(fields: dict[Any, Any]) -> dict[str, str]:
    return {_text(key): _text(value) for key, value in fields.items()}
