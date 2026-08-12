"""Governed ReliableTask queue observer bound to immutable execution inputs."""
from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from content.execution.queue.backend import load_reliabletask_job_set_envelopes
from content.execution.queue.reliabletask.transport import (
    ReliableTaskFleetTransport,
    resolve_reliabletask_fleet_transport,
)
from content.execution.runtime_evidence.contract import (
    CARRIERS,
    ProviderBinding,
    canonical_digest,
)
from content.execution.runtime_evidence.reliabletask_contract import (
    LEASE_STATES as _LEASE_STATES,
)
from content.execution.runtime_evidence.reliabletask_contract import (
    OBSERVATION_FIELDS as _OBSERVATION_FIELDS,
)
from content.execution.runtime_evidence.reliabletask_contract import (
    TASK_OPTIONAL_FIELDS as _TASK_OPTIONAL_FIELDS,
)
from content.execution.runtime_evidence.reliabletask_contract import (
    TASK_REQUIRED_FIELDS as _TASK_REQUIRED_FIELDS,
)
from content.execution.runtime_evidence.reliabletask_contract import (
    TASK_STATUSES as _TASK_STATUSES,
)
from content.execution.runtime_evidence.reliabletask_contract import (
    ExecutionTarget as _ExecutionTarget,
)
from content.execution.runtime_evidence.reliabletask_contract import (
    JobSetTarget as _JobSetTarget,
)
from content.execution.runtime_evidence.reliabletask_contract import (
    campaign_binding as _campaign_binding,
)
from content.execution.runtime_evidence.reliabletask_contract import (
    canonical_digest_any as _canonical_digest_any,
)
from content.execution.runtime_evidence.reliabletask_contract import (
    fault_event_time as _fault_event_time,
)
from content.execution.runtime_evidence.reliabletask_contract import (
    sha256_digest as _sha256,
)
from content.execution.runtime_evidence.reliabletask_process import (
    ReliableTaskObserverBinaryBinding,
    ReliableTaskObserverError,
    observer_command,
    observer_environment,
    observer_error,
    observer_timeout_seconds,
    run_observer_command,
)
from content.execution.runtime_evidence.reliabletask_targets import (
    load_job_set_targets as _load_job_set_targets,
)
from content.execution.runtime_evidence.sampling import (
    FaultQueueEvent,
    QueueObservation,
)


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


def _job_set_targets(
    carrier: str,
    execution_id: str,
    backend_envelope: Mapping[str, Any],
) -> tuple[_JobSetTarget, ...]:
    return _load_job_set_targets(
        carrier,
        execution_id,
        backend_envelope,
        load_envelopes=load_reliabletask_job_set_envelopes,
    )


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
    job_set: _JobSetTarget,
) -> tuple[dict[str, Any], ...]:
    raw_tasks = document.get("tasks")
    if not isinstance(raw_tasks, list):
        raise _typed("RESPONSE_INVALID", "tasks must be an array")
    rows: list[dict[str, Any]] = []
    identities: list[dict[str, object]] = []
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
        max_attempts = _count(
            row.get("maxAttempts"), label="task maxAttempts"
        )
        if max_attempts < 1:
            raise _typed("RESPONSE_INVALID", "task maxAttempts must be >= 1")
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
                "maxAttempts": max_attempts,
            }
        )
        rows.append(row)
    expected = [row.as_document() for row in job_set.expected_tasks]
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
    job_set: _JobSetTarget,
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
        or document.get("version") != 3
        or document.get("executionId") != target.execution_id
        or document.get("carrier") != target.carrier
        or document.get("stage") != job_set.stage
        or document.get("requestBindingDigest") != request_binding_digest
        or document.get("executionEnvelopeDigest")
        != target.execution_envelope_digest
        or document.get("jobSetEnvelopeDigest") != job_set.envelope_digest
        or document.get("jobSetDigest") != job_set.job_set_digest
        or document.get("actualTaskDigest") != job_set.actual_task_digest
        or document.get("campaignBinding") != target.campaign_binding
    ):
        raise _typed(
            "CAMPAIGN_IDENTITY_DRIFT",
            "observer response campaign generation/source identity drift",
        )
    _parse_time(document.get("observedAt"), label="observedAt")
    digest = _sha256(document.get("observationDigest"))
    if digest != canonical_digest(document, excluded="observationDigest"):
        raise _typed("DIGEST_DRIFT", "observer observationDigest drift")
    tasks = _task_rows(document, target=target, job_set=job_set)
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
                execution_envelope_digest=_sha256(
                    by_carrier[carrier].get("envelopeDigest")
                ),
                job_sets=_job_set_targets(
                    carrier,
                    str(by_carrier[carrier].get("executionId") or ""),
                    by_carrier[carrier],
                ),
                campaign_binding=_campaign_binding(by_carrier[carrier]),
            )
            for carrier in CARRIERS
        }
        campaign_rows = {
            json.dumps(
                target.campaign_binding,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            for target in targets.values()
        }
        if len(campaign_rows) != 1:
            raise _typed(
                "FROZEN_TARGET_INVALID",
                "four envelopes must bind one campaign generation and source",
            )
        self._targets = targets
        self._observer_binary = observer_binary
        self._binding = ProviderBinding(
            provider_id="reliabletask_mongo_redis_observer_v3",
            configuration_digest=canonical_digest(
                {
                    "schema": "quwoquan_data.reliabletask_queue_evidence_binding",
                    "version": 3,
                    "backend": "reliabletask",
                    "executionEnvelopes": [by_carrier[item] for item in CARRIERS],
                    "jobSets": {
                        carrier: [
                            {
                                "stage": job_set.stage,
                                "attemptOrdinal": job_set.attempt_ordinal,
                                "envelopeDigest": job_set.envelope_digest,
                                "jobSetDigest": job_set.job_set_digest,
                                "actualTaskDigest": job_set.actual_task_digest,
                                "expectedTasks": [
                                    row.as_document()
                                    for row in job_set.expected_tasks
                                ],
                            }
                            for job_set in targets[carrier].job_sets
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

    def _observe_job_set(
        self,
        target: _ExecutionTarget,
        job_set: _JobSetTarget,
        *,
        transport: ReliableTaskFleetTransport,
    ) -> tuple[QueueObservation, tuple[dict[str, Any], ...]]:
        command, cwd = observer_command(self._observer_binary)
        raw = run_observer_command(
            [
                *command,
                "--observe-execution",
                target.execution_id,
                "--observe-carrier",
                target.carrier,
                "--observe-stage",
                job_set.stage,
                "--observe-binding-digest",
                self.binding.configuration_digest,
                "--observe-execution-envelope-digest",
                target.execution_envelope_digest,
                "--observe-job-set-envelope-digest",
                job_set.envelope_digest,
                "--observe-job-set-digest",
                job_set.job_set_digest,
                "--observe-actual-task-digest",
                job_set.actual_task_digest,
                "--observe-campaign-binding",
                json.dumps(
                    target.campaign_binding,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            ],
            cwd=cwd,
            environment=observer_environment(transport),
            timeout_seconds=observer_timeout_seconds(),
        )
        observation, tasks, _ = _parse_observation(
            raw,
            target=target,
            job_set=job_set,
            request_binding_digest=self.binding.configuration_digest,
        )
        return observation, tasks

    def _observe(
        self,
        target: _ExecutionTarget,
        *,
        transport: ReliableTaskFleetTransport,
    ) -> QueueObservation:
        observations: list[QueueObservation] = []
        tasks: list[dict[str, Any]] = []
        for job_set in target.job_sets:
            observation, stage_tasks = self._observe_job_set(
                target,
                job_set,
                transport=transport,
            )
            observations.append(observation)
            tasks.extend(
                {
                    **row,
                    "_jobSetEnvelopeDigest": job_set.envelope_digest,
                }
                for row in stage_tasks
            )
        tasks.sort(
            key=lambda row: (
                str(row["stage"]),
                str(row["jobId"]),
                str(row["sourceRevision"]),
                str(row["_jobSetEnvelopeDigest"]),
            )
        )
        identities = {
            (
                str(row["jobId"]),
                str(row["sourceRevision"]),
                str(row["_jobSetEnvelopeDigest"]),
            )
            for row in tasks
        }
        if len(identities) != len(tasks):
            raise _typed("FROZEN_TARGET_DRIFT", "attempt task identity repeats")
        self._last_tasks[target.execution_id] = tuple(tasks)
        return QueueObservation(
            carrier=target.carrier,
            execution_id=target.execution_id,
            pending_job_timestamps=tuple(
                item
                for row in observations
                for item in row.pending_job_timestamps
            ),
            ready_job_timestamps=tuple(
                item
                for row in observations
                for item in row.ready_job_timestamps
            ),
            evidence_digest=_canonical_digest_any(
                [row.evidence_digest for row in observations]
            ),
            successful_job_count=sum(
                row.successful_job_count for row in observations
            ),
            terminal_job_count=sum(row.terminal_job_count for row in observations),
            observation_window_seconds=max(
                row.observation_window_seconds for row in observations
            ),
            latency_milliseconds=tuple(
                value
                for row in observations
                for value in row.latency_milliseconds
            ),
            provider_throttle_count=sum(
                row.provider_throttle_count for row in observations
            ),
            stuck_job_count=sum(row.stuck_job_count for row in observations),
        )

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


__all__ = [
    "ReliableTaskObserverError",
    "ReliableTaskQueueEvidenceProvider",
]
