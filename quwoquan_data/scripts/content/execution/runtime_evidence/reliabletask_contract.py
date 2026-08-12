"""Typed identity and digest values for the ReliableTask live observer."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from content.execution.runtime_evidence.reliabletask_process import observer_error

OBSERVATION_FIELDS = frozenset(
    {
        "schema", "version", "executionId", "carrier", "stage",
        "requestBindingDigest", "executionEnvelopeDigest",
        "jobSetEnvelopeDigest", "jobSetDigest", "actualTaskDigest",
        "campaignBinding", "observedAt", "tasks", "pendingJobTimestamps",
        "readyJobTimestamps", "successfulJobCount", "terminalJobCount",
        "observationWindowSeconds", "latencyMilliseconds",
        "providerThrottleCount", "stuckJobCount", "redisEntryCount",
        "redisPendingCount", "activeLeaseCount", "expiredLeaseCount",
        "leaseEvidenceDigest", "observationDigest",
    }
)
TASK_REQUIRED_FIELDS = frozenset(
    {
        "jobId", "entityRef", "stage", "sourceRevision", "status",
        "attempts", "maxAttempts", "createdAt", "updatedAt", "leaseState",
    }
)
TASK_OPTIONAL_FIELDS = frozenset(
    {"nextAttemptAt", "leaseUntil", "failureCode"}
)
TASK_STATUSES = frozenset(
    {"ready", "processing", "retry_wait", "succeeded", "dead"}
)
LEASE_STATES = frozenset({"none", "active", "expired"})


@dataclass(frozen=True, slots=True)
class ExpectedTask:
    job_id: str
    entity_ref: str
    stage: str
    source_revision: str
    max_attempts: int

    def as_document(self) -> dict[str, object]:
        return {
            "jobId": self.job_id,
            "entityRef": self.entity_ref,
            "stage": self.stage,
            "sourceRevision": self.source_revision,
            "maxAttempts": self.max_attempts,
        }


@dataclass(frozen=True, slots=True)
class JobSetTarget:
    stage: str
    attempt_ordinal: int
    envelope_digest: str
    job_set_digest: str
    actual_task_digest: str
    expected_tasks: tuple[ExpectedTask, ...]


@dataclass(frozen=True, slots=True)
class ExecutionTarget:
    carrier: str
    execution_id: str
    execution_envelope_digest: str
    job_sets: tuple[JobSetTarget, ...]
    campaign_binding: dict[str, object]


def sha256_digest(value: object) -> str:
    text = str(value or "").strip()
    if (
        not text.startswith("sha256:")
        or len(text) != 71
        or any(character not in "0123456789abcdef" for character in text[7:])
    ):
        raise observer_error("RESPONSE_INVALID", "sha256 digest is invalid")
    return text


def canonical_digest_any(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _time(value: object, *, label: str) -> datetime:
    text = str(value or "").strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise observer_error("RESPONSE_INVALID", f"{label} must be RFC3339") from exc
    if parsed.tzinfo is None:
        raise observer_error(
            "RESPONSE_INVALID",
            f"{label} must include timezone",
        )
    return parsed.astimezone(timezone.utc)


def fault_event_time(
    row: Mapping[str, Any],
    *,
    fault_type: str,
    after: datetime,
) -> datetime | None:
    updated = _time(row.get("updatedAt"), label="fault task updatedAt")
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
        raise observer_error(
            "FAULT_REQUEST_INVALID",
            f"unsupported faultType={fault_type}",
        )
    if row.get("leaseState") == "expired" and row.get("leaseUntil"):
        lease_until = _time(row["leaseUntil"], label="fault leaseUntil")
        if lease_until >= after:
            return lease_until
    attempts = row.get("attempts")
    if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 0:
        raise observer_error(
            "RESPONSE_INVALID",
            "fault task attempts must be a nonnegative integer",
        )
    if (
        updated >= after
        and attempts > 0
        and row.get("status") in {"retry_wait", "succeeded", "dead"}
    ):
        return updated
    return None


def campaign_binding(envelope: Mapping[str, Any]) -> dict[str, object]:
    source_digest = envelope.get("sourceDigest")
    if not isinstance(source_digest, Mapping):
        raise observer_error(
            "FROZEN_TARGET_INVALID",
            "campaign sourceDigest is invalid",
        )
    binding: dict[str, object] = {
        "rootExecutionId": envelope.get("rootExecutionId"),
        "campaignRunId": envelope.get("campaignRunId"),
        "campaignGeneration": envelope.get("campaignGeneration"),
        "campaignFencingToken": envelope.get("campaignFencingToken"),
        "campaignPlanDigest": envelope.get("campaignPlanDigest"),
        "campaignSourceRevision": envelope.get("campaignSourceRevision"),
        "campaignSourceDigest": source_digest.get("digest"),
        "campaignEntityCatalogDigest": envelope.get(
            "campaignEntityCatalogDigest"
        ),
    }
    if (
        not isinstance(binding["campaignGeneration"], int)
        or isinstance(binding["campaignGeneration"], bool)
        or int(binding["campaignGeneration"]) < 1
        or any(
            not isinstance(binding[field], str) or not str(binding[field]).strip()
            for field in ("rootExecutionId", "campaignRunId")
        )
    ):
        raise observer_error(
            "FROZEN_TARGET_INVALID",
            "campaign run identity is invalid",
        )
    for field in (
        "campaignFencingToken",
        "campaignPlanDigest",
        "campaignSourceRevision",
        "campaignSourceDigest",
        "campaignEntityCatalogDigest",
    ):
        sha256_digest(binding[field])
    return binding


def job_set_targets(
    carrier: str,
    execution_id: str,
    backend_envelope: Mapping[str, Any],
    envelopes: tuple[dict[str, Any], ...],
) -> tuple[JobSetTarget, ...]:
    campaign = campaign_binding(backend_envelope)
    targets: list[JobSetTarget] = []
    for envelope in envelopes:
        stage = str(envelope.get("stage") or "").strip()
        attempt_ordinal = envelope.get("attemptOrdinal")
        raw_tasks = envelope.get("expectedTasks")
        if (
            envelope.get("executionId") != execution_id
            or envelope.get("carrier") != carrier
            or envelope.get("queueBackendEnvelopeDigest")
            != backend_envelope.get("envelopeDigest")
            or envelope.get("campaignBinding") != campaign
            or stage not in {"author", "publish"}
            or isinstance(attempt_ordinal, bool)
            or not isinstance(attempt_ordinal, int)
            or attempt_ordinal < 1
            or not isinstance(raw_tasks, list)
        ):
            raise observer_error(
                "FROZEN_TARGET_INVALID",
                f"{carrier}/{execution_id}/{stage} job-set identity drift",
            )
        rows: list[ExpectedTask] = []
        for raw in raw_tasks:
            if not isinstance(raw, Mapping):
                raise observer_error(
                    "FROZEN_TARGET_INVALID",
                    "expectedTasks row invalid",
                )
            fields = {
                name: str(raw.get(name) or "").strip()
                for name in (
                    "jobId",
                    "executionId",
                    "carrier",
                    "entityRef",
                    "stage",
                    "sourceRevision",
                )
            }
            max_attempts = raw.get("maxAttempts")
            if (
                not all(fields.values())
                or fields["executionId"] != execution_id
                or fields["carrier"] != carrier
                or fields["stage"] != stage
                or isinstance(max_attempts, bool)
                or not isinstance(max_attempts, int)
                or max_attempts < 1
            ):
                raise observer_error(
                    "FROZEN_TARGET_INVALID",
                    f"{carrier}/{execution_id}/{stage} expected task drift",
                )
            sha256_digest(fields["sourceRevision"])
            rows.append(
                ExpectedTask(
                    job_id=fields["jobId"],
                    entity_ref=fields["entityRef"],
                    stage=fields["stage"],
                    source_revision=fields["sourceRevision"],
                    max_attempts=max_attempts,
                )
            )
        rows.sort(key=lambda row: row.job_id)
        if not rows or len({row.job_id for row in rows}) != len(rows):
            raise observer_error(
                "FROZEN_TARGET_INVALID",
                f"{carrier}/{execution_id}/{stage} expected task set invalid",
            )
        targets.append(
            JobSetTarget(
                stage=stage,
                attempt_ordinal=attempt_ordinal,
                envelope_digest=sha256_digest(envelope.get("envelopeDigest")),
                job_set_digest=sha256_digest(envelope.get("jobSetDigest")),
                actual_task_digest=sha256_digest(envelope.get("jobSetDigest")),
                expected_tasks=tuple(rows),
            )
        )
    targets.sort(key=lambda row: (row.stage, row.attempt_ordinal))
    return tuple(targets)


__all__ = [
    "LEASE_STATES",
    "OBSERVATION_FIELDS",
    "TASK_OPTIONAL_FIELDS",
    "TASK_REQUIRED_FIELDS",
    "TASK_STATUSES",
    "ExecutionTarget",
    "ExpectedTask",
    "JobSetTarget",
    "campaign_binding",
    "canonical_digest_any",
    "fault_event_time",
    "job_set_targets",
    "sha256_digest",
]
