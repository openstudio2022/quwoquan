"""Live process, queue, heartbeat, progress, and workspace sampling."""
from __future__ import annotations

import fcntl
import math
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from core.control_types import QueueBackend, QueueJobState
from core.io import read_json, write_json
from core.schema import assert_valid

from content.execution.campaign_workspace import CampaignRuntimePaths
from content.execution.queue.core import _load_jobs
from content.execution.runtime_evidence_contract import (
    CARRIERS,
    ProcessInspector,
    ProviderBinding,
    RuntimeEvidenceError,
    RuntimeEvidenceIdentity,
    assert_current_session,
    canonical_digest,
    load_runtime_evidence_session,
    safe_ref,
    session_root,
    write_create_once,
)
from content.execution.runtime_evidence_observation import (
    SystemProcessInspector,
    process_measurements,
    progress_and_heartbeat_age,
    workspace_measurements,
)


@dataclass(frozen=True, slots=True)
class QueueObservation:
    carrier: str
    execution_id: str
    pending_job_timestamps: tuple[str, ...]
    ready_job_timestamps: tuple[str, ...]
    evidence_digest: str
    successful_job_count: int = 0
    terminal_job_count: int = 0
    observation_window_seconds: int = 0
    latency_milliseconds: tuple[int, ...] = ()
    provider_throttle_count: int = 0
    stuck_job_count: int = 0


@dataclass(frozen=True, slots=True)
class FaultQueueEvent:
    event_at: str
    evidence_digest: str


class QueueEvidenceProvider(Protocol):
    @property
    def binding(self) -> ProviderBinding:
        ...

    def sample(self, execution_ids: Mapping[str, str]) -> tuple[QueueObservation, ...]:
        ...

    def assert_job_target(self, *, execution_id: str, job_id: str) -> None:
        ...

    def wait_for_fault_event(
        self,
        *,
        execution_id: str,
        job_id: str,
        fault_type: str,
        after: str,
        timeout_seconds: float,
    ) -> FaultQueueEvent:
        ...


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: object, *, label: str) -> datetime:
    text = str(value or "").strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise RuntimeEvidenceError(f"{label} must be RFC3339 date-time") from exc
    if parsed.tzinfo is None:
        raise RuntimeEvidenceError(f"{label} must include timezone")
    return parsed.astimezone(timezone.utc)


def _age_seconds(value: object, *, now: datetime, label: str) -> int:
    return max(0, int((now - _parse_time(value, label=label)).total_seconds()))


_LOCAL_QUEUE_CONFIG = canonical_digest(
    {
        "schema": "quwoquan_data.local_queue_evidence_provider",
        "backend": "local_file",
        "version": 1,
    }
)
_FAULT_EVENTS = {
    "worker_termination": {"reclaimed"},
    "lease_expiry": {"reclaimed"},
    "redis_restart": {"failed", "reclaimed"},
    "mongo_reconnect": {"failed"},
    "provider_timeout": {"failed"},
    "provider_rate_limit": {"failed"},
}


class LocalQueueEvidenceProvider:

    def __init__(self, *, binding: ProviderBinding | None = None) -> None:
        self._binding = binding or ProviderBinding(
            "local_object_queue_v1", _LOCAL_QUEUE_CONFIG
        )

    @property
    def binding(self) -> ProviderBinding:
        return self._binding

    @staticmethod
    def _jobs(execution_id: str) -> list[Any]:
        jobs = _load_jobs(execution_id)
        if any(job.backend is QueueBackend.RELIABLE_TASK for job in jobs):
            raise RuntimeEvidenceError(
                "ReliableTask live evidence requires a governed Mongo/Redis provider"
            )
        return jobs

    def sample(self, execution_ids: Mapping[str, str]) -> tuple[QueueObservation, ...]:
        now_epoch = time.time()
        observed_at = datetime.fromtimestamp(now_epoch, timezone.utc)
        rows: list[QueueObservation] = []
        for carrier in CARRIERS:
            execution_id = str(execution_ids[carrier])
            jobs = self._jobs(execution_id)
            pending: list[str] = []
            ready: list[str] = []
            latencies: list[int] = []
            successful = 0
            terminal = 0
            throttled = 0
            stuck = 0
            evidence_rows: list[dict[str, object]] = []
            for job in jobs:
                is_ready = (
                    job.state is QueueJobState.QUEUED
                    or (
                        job.state is QueueJobState.FAILED
                        and job.same_run_retryable
                        and job.not_before_epoch <= now_epoch
                    )
                    or (
                        job.state is QueueJobState.LEASED
                        and job.lease.is_expired(now_epoch)
                    )
                )
                is_pending = (
                    job.state in {QueueJobState.QUEUED, QueueJobState.LEASED}
                    or (
                        job.state is QueueJobState.FAILED
                        and job.same_run_retryable
                    )
                )
                evidence_rows.append(
                    {
                        "jobId": job.job_id,
                        "state": job.state.value,
                        "updatedAt": job.updated_at,
                        "isPending": is_pending,
                        "isReady": is_ready,
                    }
                )
                if job.state in {
                    QueueJobState.SUCCEEDED,
                    QueueJobState.BLOCKED,
                    QueueJobState.DEAD,
                }:
                    terminal += 1
                if job.state is QueueJobState.SUCCEEDED:
                    successful += 1
                if job.stuck_detected:
                    stuck += 1
                issue_code = job.last_issue.code.value if job.last_issue else ""
                timing_text = " ".join(
                    str(timing.to_document()) for timing in job.timings
                )
                fault_text = f"{issue_code} {timing_text}".upper()
                if "RATE_LIMIT" in fault_text or "THROTTL" in fault_text:
                    throttled += 1
                leased_at: datetime | None = None
                for timing in job.timings:
                    timing_at = _parse_time(timing.at, label="queue timing")
                    if timing.event.value == "leased":
                        leased_at = timing_at
                    elif (
                        timing.event.value in {"succeeded", "failed", "blocked"}
                        and leased_at is not None
                        and timing_at >= leased_at
                    ):
                        latencies.append(
                            int((timing_at - leased_at).total_seconds() * 1000)
                        )
                        leased_at = None
                if is_pending:
                    pending.append(job.updated_at or job.created_at)
                if is_ready:
                    ready.append(job.updated_at or job.created_at)
            rows.append(
                QueueObservation(
                    carrier=carrier,
                    execution_id=execution_id,
                    pending_job_timestamps=tuple(pending),
                    ready_job_timestamps=tuple(ready),
                    evidence_digest=canonical_digest(
                        {
                            "provider": self.binding.as_document(),
                            "executionId": execution_id,
                            "jobs": evidence_rows,
                        }
                    ),
                    successful_job_count=successful,
                    terminal_job_count=terminal,
                    observation_window_seconds=max(
                        1,
                        int(
                            (
                                observed_at
                                - min(
                                    (
                                        _parse_time(
                                            job.created_at,
                                            label="queue job createdAt",
                                        )
                                        for job in jobs
                                    ),
                                    default=observed_at,
                                )
                            ).total_seconds()
                        ),
                    ),
                    latency_milliseconds=tuple(latencies),
                    provider_throttle_count=throttled,
                    stuck_job_count=stuck,
                )
            )
        return tuple(rows)

    def assert_job_target(self, *, execution_id: str, job_id: str) -> None:
        matches = [job for job in self._jobs(execution_id) if job.job_id == job_id]
        if len(matches) != 1 or matches[0].execution_id != execution_id:
            raise RuntimeEvidenceError(
                f"queue fault target is not registered: {execution_id}/{job_id}"
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
        if fault_type not in _FAULT_EVENTS or timeout_seconds <= 0:
            raise RuntimeEvidenceError("fault queue observation request is invalid")
        after_time = _parse_time(after, label="fault action timestamp")
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            matches = []
            for job in self._jobs(execution_id):
                if job.job_id != job_id:
                    continue
                matches.extend(
                    timing
                    for timing in job.timings
                    if timing.event.value in _FAULT_EVENTS[fault_type]
                    and _parse_time(timing.at, label="queue timing") >= after_time
                )
            if matches:
                event = matches[0]
                return FaultQueueEvent(
                    event_at=event.at,
                    evidence_digest=canonical_digest(
                        {
                            "executionId": execution_id,
                            "jobId": job_id,
                            "faultType": fault_type,
                            "event": event.to_document(),
                        }
                    ),
                )
            time.sleep(min(0.1, timeout_seconds))
        raise RuntimeEvidenceError(
            f"typed queue fault event was not observed: {execution_id}/{job_id}"
        )


def _assert_provider(
    session: Mapping[str, Any], provider: QueueEvidenceProvider
) -> None:
    if session.get("queueEvidenceProvider") != provider.binding.as_document():
        raise RuntimeEvidenceError("queue evidence provider identity drift")


def _queue_measurements(
    session: Mapping[str, Any], provider: QueueEvidenceProvider
) -> list[dict[str, Any]]:
    execution_ids = {
        str(row["carrier"]): str(row["executionId"])
        for row in session["workers"]
    }
    observations = provider.sample(execution_ids)
    if {row.carrier for row in observations} != set(CARRIERS):
        raise RuntimeEvidenceError("queue provider did not return exactly four lanes")
    rows: list[dict[str, Any]] = []
    for carrier in CARRIERS:
        matches = [row for row in observations if row.carrier == carrier]
        if len(matches) != 1 or matches[0].execution_id != execution_ids[carrier]:
            raise RuntimeEvidenceError(f"queue provider lane identity drift: {carrier}")
        row = matches[0]
        latencies = sorted(row.latency_milliseconds)
        latency_p95 = (
            latencies[max(0, math.ceil(len(latencies) * 0.95) - 1)]
            if latencies
            else 0
        )
        oldest = min(
            (_parse_time(value, label="queue ready timestamp") for value in row.ready_job_timestamps),
            default=None,
        )
        rows.append(
            {
                "carrier": carrier,
                "executionId": row.execution_id,
                "queueDepth": len(row.pending_job_timestamps),
                "readyDepth": len(row.ready_job_timestamps),
                "oldestReadyAt": oldest.isoformat() if oldest else None,
                "successfulJobCount": row.successful_job_count,
                "terminalJobCount": row.terminal_job_count,
                "observationWindowSeconds": row.observation_window_seconds,
                "throughputPerHour": round(
                    row.successful_job_count
                    * 3600
                    / max(1, row.observation_window_seconds),
                    4,
                ),
                "latencyP95Milliseconds": latency_p95,
                "providerThrottleCount": row.provider_throttle_count,
                "stuckJobCount": row.stuck_job_count,
                "providerEvidenceDigest": row.evidence_digest,
            }
        )
    return rows


def _load_sample(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise RuntimeEvidenceError(f"resource sample receipt must be an object: {path}")
    assert_valid(
        payload,
        "execution",
        "runtime_resource_sample_receipt",
        label=f"runtime resource sample:{path}",
    )
    if payload.get("receiptDigest") != canonical_digest(
        payload, excluded="receiptDigest"
    ):
        raise RuntimeEvidenceError(f"resource sample receipt digest drift: {path}")
    return payload


def capture_resource_sample(
    *,
    runtime: CampaignRuntimePaths,
    identity: RuntimeEvidenceIdentity,
    session_id: str,
    sample_id: str,
    inspector: ProcessInspector,
    queue_provider: QueueEvidenceProvider,
) -> tuple[dict[str, Any], Path]:
    """Capture one create-once sample without accepting metric values."""
    if re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{2,127}", sample_id) is None:
        raise RuntimeEvidenceError("resource sampleId is unsafe")
    session = load_runtime_evidence_session(runtime, identity, session_id)
    _assert_provider(session, queue_provider)
    path = session_root(runtime, identity, session_id) / "samples" / f"{sample_id}.json"
    if path.is_file():
        existing = _load_sample(path)
        if existing.get("sampleId") != sample_id:
            raise RuntimeEvidenceError(f"resource sample create-once collision: {path}")
        return existing, path
    captured = _now()
    processes = process_measurements(session, inspector)
    queues = _queue_measurements(session, queue_provider)
    workspaces = workspace_measurements(session, output_root=runtime.output_root)
    group_rss: dict[tuple[str, object, int], int] = {}
    registered: set[tuple[str, object, int]] = set()
    for row in processes:
        key = (str(row["role"]), row["carrier"], int(row["registrationPid"]))
        group_rss[key] = group_rss.get(key, 0) + int(row["rssBytes"])
        if row["isRegisteredProcess"]:
            registered.add(key)
    if set(group_rss) != registered:
        raise RuntimeEvidenceError("runtime process group has no registered leader")
    controller = [
        value for (role, _carrier, _pid), value in group_rss.items()
        if role == "controller"
    ]
    non_video = [
        value for (role, carrier, _pid), value in group_rss.items()
        if role == "worker" and carrier != "video"
    ]
    video = [
        value for (role, carrier, _pid), value in group_rss.items()
        if role == "worker" and carrier == "video"
    ]
    if len(controller) != 1 or len(non_video) != 3 or len(video) != 1:
        raise RuntimeEvidenceError("runtime process registry is not one controller/four lanes")
    progress_age, heartbeat_age = progress_and_heartbeat_age(
        session,
        runtime=runtime,
        identity=identity,
        now=captured,
    )
    raw = {
        "capturedAt": captured.isoformat(),
        "controllerRssBytes": controller[0],
        "nonVideoWorkerMaxRssBytes": max(non_video),
        "videoWorkerMaxRssBytes": max(video),
        "totalRssBytes": sum(int(row["rssBytes"]) for row in processes),
        "temporaryWorkspaceBytes": sum(int(row["bytes"]) for row in workspaces),
        "terminalResidualBytes": sum(
            int(row["bytes"])
            for row in workspaces
            if row["kind"] == "transaction_staging"
        ),
        "openFdCount": sum(int(row["openFdCount"]) for row in processes),
        "queueDepth": sum(int(row["queueDepth"]) for row in queues),
        "oldestReadyAgeSeconds": max(
            (
                _age_seconds(row["oldestReadyAt"], now=captured, label="oldest ready")
                for row in queues
                if row["oldestReadyAt"] is not None
            ),
            default=0,
        ),
        "progressAgeSeconds": progress_age,
        "heartbeatAgeSeconds": heartbeat_age,
    }
    stable = {
        "schema": "quwoquan_data.runtime_resource_sample_receipt",
        "sampleId": sample_id,
        "sessionRef": safe_ref(
            session_root(runtime, identity, session_id) / "session.json",
            output_root=runtime.output_root,
        ),
        "sessionDigest": session["receiptDigest"],
        **identity.as_document(),
        "capturedAt": raw["capturedAt"],
        "processMeasurements": processes,
        "queueMeasurements": queues,
        "workspaceMeasurements": workspaces,
        "rawSample": raw,
    }
    assert_current_session(
        runtime,
        session,
        identity,
        require_active_lease=True,
    )
    document = write_create_once(
        path,
        stable=stable,
        schema_name="runtime_resource_sample_receipt",
        digest_field="receiptDigest",
    )
    return document, path


def _write_raw_create_once(path: Path, payload: Mapping[str, Any], *, schema: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.parent / f".{path.name}.lock"
    with lock.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        if path.is_file():
            existing = read_json(path)
            if existing != dict(payload):
                raise RuntimeEvidenceError(f"raw evidence create-once collision: {path}")
            return
        assert_valid(payload, "release", schema, label=f"runtime raw evidence:{path}")
        write_json(path, dict(payload))


def finalize_resource_samples(
    *,
    runtime: CampaignRuntimePaths,
    identity: RuntimeEvidenceIdentity,
    session_id: str,
) -> tuple[dict[str, Any], Path]:
    """Freeze sample receipts into the exact existing release raw schema."""
    session = load_runtime_evidence_session(
        runtime, identity, session_id, require_active_lease=False
    )
    sample_root = session_root(runtime, identity, session_id) / "samples"
    receipts = [_load_sample(path) for path in sorted(sample_root.glob("*.json"))]
    if len(receipts) < 2:
        raise RuntimeEvidenceError("resource raw evidence requires at least two samples")
    expected = {
        "sessionDigest": session["receiptDigest"],
        **identity.as_document(),
    }
    for receipt in receipts:
        if any(receipt.get(key) != value for key, value in expected.items()):
            raise RuntimeEvidenceError("resource sample/session identity drift")
    ordered = sorted(receipts, key=lambda row: _parse_time(row["capturedAt"], label="sample"))
    instants = [row["capturedAt"] for row in ordered]
    if len(instants) != len(set(instants)):
        raise RuntimeEvidenceError("resource sample timestamps must be unique")
    raw = {
        "schema": "quwoquan_data.resource_soak_samples",
        "rootExecutionId": identity.root_execution_id,
        "sourceRevision": session["sourceRevision"],
        "sourceDigest": session["sourceDigest"],
        "entityCatalogDigest": session["entityCatalogDigest"],
        "samples": [dict(row["rawSample"]) for row in ordered],
    }
    path = session_root(runtime, identity, session_id) / "raw/resource-soak-samples.json"
    _write_raw_create_once(path, raw, schema="resource_soak_samples")
    return raw, path


__all__ = ["FaultQueueEvent", "LocalQueueEvidenceProvider", "QueueEvidenceProvider",
           "QueueObservation", "SystemProcessInspector", "capture_resource_sample",
           "finalize_resource_samples"]
