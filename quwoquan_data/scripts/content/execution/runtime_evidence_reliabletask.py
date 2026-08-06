"""Governed ReliableTask queue observer bound to immutable execution inputs."""
from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from core.control_types import QueueBackend

from content.execution.queue.core import _load_jobs
from content.execution.reliabletask_transport import (
    ReliableTaskFleetTransport,
    resolve_reliabletask_fleet_transport,
)
from content.execution.runtime_evidence_contract import (
    CARRIERS,
    ProviderBinding,
    canonical_digest,
)
from content.execution.runtime_evidence_reliabletask_process import (
    ReliableTaskObserverBinaryBinding,
    ReliableTaskObserverError,
    observer_command,
    observer_environment,
    observer_error,
    observer_timeout_seconds,
    run_observer_command,
)
from content.execution.runtime_evidence_sampling import (
    FaultQueueEvent,
    QueueObservation,
)

_OBSERVATION_FIELDS = frozenset(
    {
        "schema",
        "version",
        "executionId",
        "carrier",
        "requestBindingDigest",
        "observedAt",
        "tasks",
        "pendingJobTimestamps",
        "readyJobTimestamps",
        "successfulJobCount",
        "terminalJobCount",
        "observationWindowSeconds",
        "latencyMilliseconds",
        "providerThrottleCount",
        "stuckJobCount",
        "redisEntryCount",
        "redisPendingCount",
        "activeLeaseCount",
        "expiredLeaseCount",
        "leaseEvidenceDigest",
        "observationDigest",
    }
)
_TASK_REQUIRED_FIELDS = frozenset(
    {
        "jobId",
        "entityRef",
        "stage",
        "sourceRevision",
        "status",
        "attempts",
        "createdAt",
        "updatedAt",
        "leaseState",
    }
)
_TASK_OPTIONAL_FIELDS = frozenset(
    {"nextAttemptAt", "leaseUntil", "failureCode"}
)
_TASK_STATUSES = frozenset(
    {"ready", "processing", "retry_wait", "succeeded", "dead"}
)
_LEASE_STATES = frozenset({"none", "active", "expired"})


@dataclass(frozen=True, slots=True)
class _ExpectedTask:
    job_id: str
    entity_ref: str
    stage: str
    source_revision: str

    def as_document(self) -> dict[str, str]:
        return {
            "jobId": self.job_id,
            "entityRef": self.entity_ref,
            "stage": self.stage,
            "sourceRevision": self.source_revision,
        }


@dataclass(frozen=True, slots=True)
class _ExecutionTarget:
    carrier: str
    execution_id: str
    expected_tasks: tuple[_ExpectedTask, ...]


def _typed(suffix: str, message: str) -> ReliableTaskObserverError:
    return observer_error(suffix, message)


def _parse_time(value: object, *, label: str) -> datetime:
    text = str(value or "").strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise _typed("RESPONSE_INVALID", f"{label} must be RFC3339") from exc
    if parsed.tzinfo is None:
        raise _typed("RESPONSE_INVALID", f"{label} must include timezone")
    return parsed.astimezone(timezone.utc)


def _sha256(value: object) -> str:
    text = str(value or "").strip()
    if (
        not text.startswith("sha256:")
        or len(text) != 71
        or any(character not in "0123456789abcdef" for character in text[7:])
    ):
        raise _typed("RESPONSE_INVALID", "sha256 digest is invalid")
    return text


def _canonical_digest_any(value: object) -> str:
    import hashlib

    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _expected_tasks(carrier: str, execution_id: str) -> tuple[_ExpectedTask, ...]:
    rows: list[_ExpectedTask] = []
    for job in _load_jobs(execution_id):
        if job.backend is not QueueBackend.RELIABLE_TASK:
            continue
        reliable_ref = job.reliable_task_ref_document()
        payload = (
            reliable_ref.get("payload")
            if isinstance(reliable_ref, Mapping)
            else None
        )
        if not isinstance(payload, Mapping):
            raise _typed(
                "FROZEN_TARGET_INVALID",
                f"{carrier}/{execution_id} has no typed ReliableTask payload",
            )
        fields = {
            name: str(payload.get(name) or "").strip()
            for name in (
                "jobId",
                "executionId",
                "carrier",
                "entityRef",
                "stage",
                "sourceRevision",
            )
        }
        if (
            not all(fields.values())
            or fields["jobId"] != job.job_id
            or fields["executionId"] != execution_id
            or fields["carrier"] != carrier
            or fields["stage"] not in {"author", "publish"}
        ):
            raise _typed(
                "FROZEN_TARGET_INVALID",
                f"{carrier}/{execution_id}/{job.job_id} identity drift",
            )
        _sha256(fields["sourceRevision"])
        rows.append(
            _ExpectedTask(
                job_id=fields["jobId"],
                entity_ref=fields["entityRef"],
                stage=fields["stage"],
                source_revision=fields["sourceRevision"],
            )
        )
    rows.sort(key=lambda row: row.job_id)
    if not rows or len({row.job_id for row in rows}) != len(rows):
        raise _typed(
            "FROZEN_TARGET_INVALID",
            f"{carrier}/{execution_id} requires unique materialized ReliableTask jobs",
        )
    return tuple(rows)


def _count(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _typed("RESPONSE_INVALID", f"{label} must be a nonnegative integer")
    return value


def _string_array(value: object, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise _typed("RESPONSE_INVALID", f"{label} must be a string array")
    for item in value:
        _parse_time(item, label=label)
    return tuple(value)


def _task_rows(
    document: Mapping[str, Any],
    *,
    target: _ExecutionTarget,
) -> tuple[dict[str, Any], ...]:
    raw_tasks = document.get("tasks")
    if not isinstance(raw_tasks, list):
        raise _typed("RESPONSE_INVALID", "tasks must be an array")
    rows: list[dict[str, Any]] = []
    identities: list[dict[str, str]] = []
    for raw in raw_tasks:
        if not isinstance(raw, Mapping):
            raise _typed("RESPONSE_INVALID", "task observation must be an object")
        fields = set(raw)
        if (
            not _TASK_REQUIRED_FIELDS.issubset(fields)
            or fields - _TASK_REQUIRED_FIELDS - _TASK_OPTIONAL_FIELDS
        ):
            raise _typed("RESPONSE_INVALID", "task observation fields are invalid")
        row = dict(raw)
        for field in ("jobId", "entityRef", "stage", "sourceRevision", "status"):
            if not isinstance(row.get(field), str) or not str(row[field]).strip():
                raise _typed("RESPONSE_INVALID", f"task {field} is invalid")
        _sha256(row["sourceRevision"])
        if row["stage"] not in {"author", "publish"} or row["status"] not in _TASK_STATUSES:
            raise _typed("RESPONSE_INVALID", "task stage or status is invalid")
        _count(row.get("attempts"), label="task attempts")
        _parse_time(row.get("createdAt"), label="task createdAt")
        _parse_time(row.get("updatedAt"), label="task updatedAt")
        if row.get("leaseState") not in _LEASE_STATES:
            raise _typed("RESPONSE_INVALID", "task leaseState is invalid")
        for field in ("nextAttemptAt", "leaseUntil"):
            if field in row:
                _parse_time(row[field], label=f"task {field}")
        if "failureCode" in row and not isinstance(row["failureCode"], str):
            raise _typed("RESPONSE_INVALID", "task failureCode is invalid")
        identities.append(
            {
                "jobId": str(row["jobId"]),
                "entityRef": str(row["entityRef"]),
                "stage": str(row["stage"]),
                "sourceRevision": str(row["sourceRevision"]),
            }
        )
        rows.append(row)
    expected = [row.as_document() for row in target.expected_tasks]
    identities.sort(key=lambda row: row["jobId"])
    if identities != expected:
        raise _typed(
            "FROZEN_TARGET_DRIFT",
            f"{target.carrier}/{target.execution_id} live job identity set drift",
        )
    rows.sort(key=lambda row: str(row["jobId"]))
    return tuple(rows)


def _parse_observation(
    raw: str,
    *,
    target: _ExecutionTarget,
    request_binding_digest: str,
) -> tuple[QueueObservation, tuple[dict[str, Any], ...], str]:
    try:
        document = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise _typed("JSON_INVALID", "observer stdout is not one JSON object") from exc
    if not isinstance(document, dict) or set(document) != _OBSERVATION_FIELDS:
        raise _typed("RESPONSE_INVALID", "observer document fields are invalid")
    if (
        document.get("schema") != "quwoquan.reliabletask_execution_observation"
        or document.get("version") != 1
        or document.get("executionId") != target.execution_id
        or document.get("carrier") != target.carrier
        or document.get("requestBindingDigest") != request_binding_digest
    ):
        raise _typed("IDENTITY_DRIFT", "observer response identity drift")
    _parse_time(document.get("observedAt"), label="observedAt")
    digest = _sha256(document.get("observationDigest"))
    if digest != canonical_digest(document, excluded="observationDigest"):
        raise _typed("DIGEST_DRIFT", "observer observationDigest drift")
    tasks = _task_rows(document, target=target)
    pending = _string_array(
        document.get("pendingJobTimestamps"),
        label="pendingJobTimestamps",
    )
    ready = _string_array(
        document.get("readyJobTimestamps"),
        label="readyJobTimestamps",
    )
    successful = _count(document.get("successfulJobCount"), label="successfulJobCount")
    terminal = _count(document.get("terminalJobCount"), label="terminalJobCount")
    window = _count(
        document.get("observationWindowSeconds"),
        label="observationWindowSeconds",
    )
    if window < 1:
        raise _typed("RESPONSE_INVALID", "observation window must be positive")
    latencies_raw = document.get("latencyMilliseconds")
    if not isinstance(latencies_raw, list):
        raise _typed("RESPONSE_INVALID", "latencyMilliseconds must be an array")
    latencies = tuple(
        _count(value, label="latencyMilliseconds") for value in latencies_raw
    )
    throttled = _count(
        document.get("providerThrottleCount"),
        label="providerThrottleCount",
    )
    stuck = _count(document.get("stuckJobCount"), label="stuckJobCount")
    redis_entries = _count(document.get("redisEntryCount"), label="redisEntryCount")
    redis_pending = _count(document.get("redisPendingCount"), label="redisPendingCount")
    active_leases = _count(document.get("activeLeaseCount"), label="activeLeaseCount")
    expired_leases = _count(document.get("expiredLeaseCount"), label="expiredLeaseCount")
    if redis_entries < len(ready) or redis_pending > redis_entries:
        raise _typed("RESPONSE_INVALID", "Redis queue counts are inconsistent")
    expected_successful = sum(row["status"] == "succeeded" for row in tasks)
    expected_terminal = sum(
        row["status"] in {"succeeded", "dead"} for row in tasks
    )
    expected_active = sum(row["leaseState"] == "active" for row in tasks)
    expected_expired = sum(row["leaseState"] == "expired" for row in tasks)
    expected_pending = sum(
        row["status"] in {"ready", "processing", "retry_wait"} for row in tasks
    )
    if (
        successful != expected_successful
        or terminal != expected_terminal
        or active_leases != expected_active
        or expired_leases != expected_expired
        or stuck != expected_expired
        or len(pending) != expected_pending
    ):
        raise _typed("RESPONSE_INVALID", "Mongo queue counts are inconsistent")
    lease_rows = [
        {
            "jobId": row["jobId"],
            "status": row["status"],
            "leaseState": row["leaseState"],
            "leaseUntil": row.get("leaseUntil", ""),
        }
        for row in tasks
    ]
    if _sha256(document.get("leaseEvidenceDigest")) != _canonical_digest_any(
        lease_rows
    ):
        raise _typed("DIGEST_DRIFT", "observer leaseEvidenceDigest drift")
    return (
        QueueObservation(
            carrier=target.carrier,
            execution_id=target.execution_id,
            pending_job_timestamps=pending,
            ready_job_timestamps=ready,
            evidence_digest=digest,
            successful_job_count=successful,
            terminal_job_count=terminal,
            observation_window_seconds=window,
            latency_milliseconds=latencies,
            provider_throttle_count=throttled,
            stuck_job_count=stuck,
        ),
        tasks,
        str(document["observedAt"]),
    )


class ReliableTaskQueueEvidenceProvider:
    """Read Mongo+Redis through the canonical Service observer process."""

    def __init__(self, *, envelopes: Sequence[Mapping[str, Any]]) -> None:
        by_carrier = {
            str(row.get("carrier") or ""): dict(row) for row in envelopes
        }
        if set(by_carrier) != set(CARRIERS):
            raise _typed("FROZEN_TARGET_INVALID", "exact four envelopes are required")
        binary_fields = ("observerBinaryRef", "observerBinarySha256")
        binary_rows = {
            tuple(str(row.get(field) or "").strip() for field in binary_fields)
            for row in by_carrier.values()
        }
        if len(binary_rows) != 1:
            raise _typed(
                "FROZEN_TARGET_INVALID", "four envelopes must bind one observer binary"
            )
        observer_binary = ReliableTaskObserverBinaryBinding(*next(iter(binary_rows)))
        observer_command(observer_binary)
        targets = {
            carrier: _ExecutionTarget(
                carrier=carrier,
                execution_id=str(by_carrier[carrier].get("executionId") or ""),
                expected_tasks=_expected_tasks(
                    carrier,
                    str(by_carrier[carrier].get("executionId") or ""),
                ),
            )
            for carrier in CARRIERS
        }
        self._targets = targets
        self._observer_binary = observer_binary
        self._binding = ProviderBinding(
            provider_id="reliabletask_mongo_redis_observer_v1",
            configuration_digest=canonical_digest(
                {
                    "schema": "quwoquan_data.reliabletask_queue_evidence_binding",
                    "version": 1,
                    "backend": QueueBackend.RELIABLE_TASK.value,
                    "executionEnvelopes": [by_carrier[item] for item in CARRIERS],
                    "expectedTasks": {
                        carrier: [
                            row.as_document()
                            for row in targets[carrier].expected_tasks
                        ]
                        for carrier in CARRIERS
                    },
                }
            ),
        )
        self._last_tasks: dict[str, tuple[dict[str, Any], ...]] = {}

    @property
    def binding(self) -> ProviderBinding:
        return self._binding

    def _transport(self) -> ReliableTaskFleetTransport:
        try:
            return resolve_reliabletask_fleet_transport()
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise _typed(
                "TRANSPORT_UNAVAILABLE",
                f"Ops-owned fleet transport unavailable ({type(exc).__name__})",
            ) from exc

    def _observe(
        self,
        target: _ExecutionTarget,
        *,
        transport: ReliableTaskFleetTransport,
    ) -> QueueObservation:
        command, cwd = observer_command(self._observer_binary)
        raw = run_observer_command(
            [
                *command,
                "--observe-execution",
                target.execution_id,
                "--observe-carrier",
                target.carrier,
                "--observe-binding-digest",
                self.binding.configuration_digest,
            ],
            cwd=cwd,
            environment=observer_environment(transport),
            timeout_seconds=observer_timeout_seconds(),
        )
        observation, tasks, _ = _parse_observation(
            raw,
            target=target,
            request_binding_digest=self.binding.configuration_digest,
        )
        self._last_tasks[target.execution_id] = tasks
        return observation

    def sample(
        self,
        execution_ids: Mapping[str, str],
    ) -> tuple[QueueObservation, ...]:
        expected = {
            carrier: target.execution_id
            for carrier, target in self._targets.items()
        }
        actual = {str(key): str(value) for key, value in execution_ids.items()}
        if actual != expected:
            raise _typed("IDENTITY_DRIFT", "runtime execution lane set drift")
        transport = self._transport()
        with ThreadPoolExecutor(max_workers=len(CARRIERS)) as pool:
            futures = {
                carrier: pool.submit(
                    self._observe,
                    self._targets[carrier],
                    transport=transport,
                )
                for carrier in CARRIERS
            }
            return tuple(futures[carrier].result() for carrier in CARRIERS)

    def _observe_execution(self, execution_id: str) -> tuple[dict[str, Any], ...]:
        matches = [
            target
            for target in self._targets.values()
            if target.execution_id == execution_id
        ]
        if len(matches) != 1:
            raise _typed("IDENTITY_DRIFT", "fault execution is not frozen")
        self._observe(matches[0], transport=self._transport())
        return self._last_tasks[execution_id]

    def assert_job_target(self, *, execution_id: str, job_id: str) -> None:
        rows = self._observe_execution(execution_id)
        if sum(row["jobId"] == job_id for row in rows) != 1:
            raise _typed(
                "FAULT_TARGET_INVALID",
                f"fault job is not registered: {execution_id}/{job_id}",
            )

    def wait_for_fault_event(
        self,
        *,
        execution_id: str,
        job_id: str,
        fault_type: str,
        after: str,
        timeout_seconds: float,
    ) -> FaultQueueEvent:
        if timeout_seconds <= 0:
            raise _typed("FAULT_REQUEST_INVALID", "fault timeout must be positive")
        after_time = _parse_time(after, label="fault action timestamp")
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            rows = self._observe_execution(execution_id)
            matches = [row for row in rows if row["jobId"] == job_id]
            if len(matches) != 1:
                raise _typed("FAULT_TARGET_INVALID", "fault job identity drift")
            row = matches[0]
            event_at = _fault_event_time(row, fault_type=fault_type, after=after_time)
            if event_at is not None:
                event_text = event_at.isoformat()
                return FaultQueueEvent(
                    event_at=event_text,
                    evidence_digest=_canonical_digest_any(
                        {
                            "provider": self.binding.as_document(),
                            "executionId": execution_id,
                            "jobId": job_id,
                            "faultType": fault_type,
                            "eventAt": event_text,
                            "task": row,
                        }
                    ),
                )
            time.sleep(min(0.2, max(0.0, deadline - time.monotonic())))
        raise _typed(
            "FAULT_EVENT_NOT_OBSERVED",
            f"no typed queue event for {execution_id}/{job_id}",
        )


def _fault_event_time(
    row: Mapping[str, Any],
    *,
    fault_type: str,
    after: datetime,
) -> datetime | None:
    updated = _parse_time(row.get("updatedAt"), label="fault task updatedAt")
    failure = str(row.get("failureCode") or "").upper()
    if fault_type == "provider_timeout":
        return updated if updated >= after and "TIMEOUT" in failure else None
    if fault_type == "provider_rate_limit":
        return (
            updated
            if updated >= after
            and ("RATE_LIMIT" in failure or "THROTTL" in failure)
            else None
        )
    if fault_type not in {
        "worker_termination",
        "lease_expiry",
        "redis_restart",
        "mongo_reconnect",
    }:
        raise _typed("FAULT_REQUEST_INVALID", f"unsupported faultType={fault_type}")
    if row.get("leaseState") == "expired" and row.get("leaseUntil"):
        lease_until = _parse_time(row["leaseUntil"], label="fault leaseUntil")
        if lease_until >= after:
            return lease_until
    if (
        updated >= after
        and _count(row.get("attempts"), label="fault task attempts") > 0
        and row.get("status") in {"retry_wait", "succeeded", "dead"}
    ):
        return updated
    return None


__all__ = [
    "ReliableTaskObserverError",
    "ReliableTaskQueueEvidenceProvider",
]
