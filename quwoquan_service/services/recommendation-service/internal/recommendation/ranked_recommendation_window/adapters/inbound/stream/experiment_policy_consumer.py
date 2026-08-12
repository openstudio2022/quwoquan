from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import threading
import time
from typing import Any

from ....application.experiment_policy_stream import (
    ExperimentPolicyDependencyUnavailable,
    ExperimentPolicyStore,
    ExperimentPolicyStream,
    ExperimentPolicyStreamRecord,
)
from ....domain.experiment_policy import (
    EXPERIMENT_ID,
    ExperimentAssignments,
    ExperimentPolicy,
    PolicyVariant,
    canonical_policy,
)


class ExperimentPolicyConsumer:
    def __init__(
        self,
        *,
        stream: ExperimentPolicyStream,
        store: ExperimentPolicyStore,
        assignments: ExperimentAssignments,
        consumer: str,
    ) -> None:
        if stream is None or store is None or assignments is None:
            raise ValueError(
                "recommendation Experiment policy consumer requires stream, store and assignments"
            )
        self._stream = stream
        self._store = store
        self._assignments = assignments
        self._consumer = consumer.strip() or "recommendation-experiment-policy"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_success: datetime | None = None
        self._last_failure: Exception | None = None

    def ensure_group(self) -> None:
        self._stream.ensure_consumer_group()

    def process_once(self) -> int:
        self.ensure_group()
        messages = self._stream.read(consumer=self._consumer)
        processed = 0
        seen: set[str] = set()
        for record in messages:
            if record.stream_id in seen:
                continue
            seen.add(record.stream_id)
            self._process(record)
            processed += 1
        self._last_success = datetime.now(timezone.utc)
        self._last_failure = None
        return processed

    def wait_for_active_policy(
        self,
        *,
        timeout_seconds: float,
        poll_interval_seconds: float = 0.25,
    ) -> bool:
        """Consume the authored policy stream until one active policy exists.

        A fresh runtime can start immediately after Product Ops commits the
        policy while its transactional outbox is still being dispatched.  The
        startup boundary therefore waits for the same typed consumer and store
        projection used at runtime; it never manufactures a policy or reads a
        private configuration fallback.
        """

        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError(
                "recommendation Experiment policy startup timeout must be positive"
            )
        if (
            isinstance(poll_interval_seconds, bool)
            or not isinstance(poll_interval_seconds, (int, float))
            or not math.isfinite(poll_interval_seconds)
            or poll_interval_seconds <= 0
        ):
            raise ValueError(
                "recommendation Experiment policy startup poll interval must be positive"
            )

        deadline = time.monotonic() + float(timeout_seconds)
        while True:
            try:
                self.process_once()
            except ExperimentPolicyDependencyUnavailable as error:
                self._last_failure = error
            if self._assignments.healthy():
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            self._stop.wait(min(float(poll_interval_seconds), remaining))

    def healthy(self, *, max_staleness_seconds: float = 10.0) -> bool:
        if self._last_success is None or self._last_failure is not None:
            return False
        return (
            datetime.now(timezone.utc) - self._last_success
        ).total_seconds() <= max_staleness_seconds

    def _process(self, record: ExperimentPolicyStreamRecord) -> None:
        try:
            policy = decode_policy(dict(record.values))
            if policy is not None:
                effective = self._store.apply(policy)
                self._assignments.apply_policy(effective)
        except ValueError as error:
            self._stream.dead_letter(
                stream_id=record.stream_id,
                event_id=record.values.get("eventId", ""),
                reason=str(error),
                dead_lettered_at=datetime.now(timezone.utc),
            )
            self._stream.acknowledge(record.stream_id)
            return
        self._stream.acknowledge(record.stream_id)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.process_once()
            except ExperimentPolicyDependencyUnavailable as error:
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
