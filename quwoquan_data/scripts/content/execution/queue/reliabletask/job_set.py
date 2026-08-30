"""Content-addressed append-only ReliableTask stage-attempt envelopes."""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from core.control_types import QueueBackend
from core.io import read_json
from core.schema import assert_valid

from content.execution.identity import parse_execution_id, validate_execution_id
from content.execution.queue.partition import (
    PARTITION_ALGORITHM,
    checkpoint_policy_document,
    partition_count,
    partition_key,
)
from content.execution.workspace import execution_root

RELIABLETASK_JOB_SET_ENVELOPE_DIR = "0.plan/reliabletask_job_sets"
_SCHEMA = "quwoquan_data.reliabletask_job_set_envelope"
_STAGES = ("author", "publish")
_TASK_FIELDS = (
    "entityRef", "carrier", "sourceRevision", "idempotencyKey", "jobId",
    "executionId", "ref", "stage", "partitionKey",
)


class ReliableTaskJobSetCollisionError(ValueError):
    """One content-addressed attempt path was observed with different bytes."""


def _digest(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _pool_delivery_binding(
    execution_id: str,
    stage: str,
) -> dict[str, object] | None:
    if stage != "publish":
        return None
    from content.execution.preflight.pool_delivery import (
        load_current_pool_delivery_preflight_receipt,
    )

    receipt, path = load_current_pool_delivery_preflight_receipt(execution_id)
    return {
        "receiptId": receipt["receiptId"],
        "receiptRef": path.relative_to(execution_root(execution_id)).as_posix(),
        "evidenceDigest": receipt["evidenceDigest"],
        "transportDigest": receipt["transportDigest"],
        "deliveryGeneration": receipt["deliveryGeneration"],
        "deliveryFencingToken": receipt["deliveryFencingToken"],
        "workerRef": receipt["workerRef"],
        "workerSha256": receipt["workerSha256"],
        "campaignBinding": receipt["campaignBinding"],
    }


def _worker_host_binding(execution_id: str) -> dict[str, Any] | None:
    from content.execution import store

    policy = store.load_spec(execution_id).get("executionPolicy") or {}
    binding = policy.get("workerHostSetBinding")
    if binding is None:
        return None
    if not isinstance(binding, Mapping):
        raise TypeError("ReliableTask worker host-set binding is invalid")
    assert_valid(
        dict(binding),
        "execution",
        "governed_worker_host_binding",
        label=f"ReliableTask worker host-set:{execution_id}",
    )
    return dict(binding)


def job_set_envelope_path(
    execution_id: str,
    stage: str,
    job_set_digest: str,
) -> Path:
    normalized_stage = str(stage or "").strip()
    digest = str(job_set_digest or "").strip()
    if normalized_stage not in _STAGES:
        raise ValueError(f"ReliableTask job-set stage is invalid: {stage!r}")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError("ReliableTask jobSetDigest is invalid")
    return (
        execution_root(validate_execution_id(execution_id))
        / RELIABLETASK_JOB_SET_ENVELOPE_DIR
        / normalized_stage
        / f"{digest[7:]}.json"
    )


def _normalize_tasks(
    execution_id: str,
    stage: str,
    tasks: Sequence[Mapping[str, Any]],
    *,
    governed_partition_count: int,
) -> list[dict[str, object]]:
    carrier = parse_execution_id(execution_id).content_type.value
    normalized: list[dict[str, object]] = []
    for raw in tasks:
        row: dict[str, object] = {
            field: str(raw.get(field) or "").strip() for field in _TASK_FIELDS
        }
        missing = [field for field, value in row.items() if not value]
        if missing:
            raise ValueError(
                "ReliableTask expected task fields are incomplete: "
                + ", ".join(missing)
            )
        max_attempts = raw.get("maxAttempts")
        if (
            isinstance(max_attempts, bool)
            or not isinstance(max_attempts, int)
            or max_attempts < 1
        ):
            raise ValueError(
                "ReliableTask expected task maxAttempts must be an integer >= 1"
            )
        row["maxAttempts"] = max_attempts
        if (
            row["executionId"] != execution_id
            or row["carrier"] != carrier
            or row["stage"] != stage
        ):
            raise ValueError(
                "ReliableTask expected task execution/carrier/stage identity drift"
            )
        revision = str(row["sourceRevision"])
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", revision):
            raise ValueError("ReliableTask expected task sourceRevision is invalid")
        expected_key = (
            f"{execution_id}|{row['entityRef']}|{carrier}|{revision}|{stage}"
        )
        if row["idempotencyKey"] != expected_key:
            raise ValueError("ReliableTask expected task idempotencyKey identity drift")
        row["partitionKey"] = partition_key(
            carrier, str(row["ref"]), governed_partition_count
        )
        normalized.append(row)
    normalized.sort(key=lambda row: str(row["jobId"]))
    job_ids = {row["jobId"] for row in normalized}
    keys = {row["idempotencyKey"] for row in normalized}
    if not normalized or len(job_ids) != len(normalized) or len(keys) != len(normalized):
        raise ValueError(
            "ReliableTask job-set requires unique jobId and idempotencyKey values"
        )
    return normalized


def _load(
    execution_id: str,
    backend: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    root = execution_root(execution_id) / RELIABLETASK_JOB_SET_ENVELOPE_DIR
    if root.is_dir() and any(root.glob("*.json")):
        raise ValueError(
            "retired single-file ReliableTask job-set layout is not observable"
        )
    for stage in _STAGES:
        stage_root = root / stage
        paths = sorted(stage_root.glob("*.json")) if stage_root.is_dir() else []
        stage_rows: list[dict[str, Any]] = []
        for path in paths:
            payload = read_json(path)
            if not isinstance(payload, dict):
                raise TypeError("ReliableTask job-set envelope must be an object")
            if path.name != f"{str(payload.get('jobSetDigest') or '')[7:]}.json":
                raise ValueError("ReliableTask job-set content-addressed path drift")
            stage_rows.append(payload)
        stage_rows.sort(key=lambda row: int(row.get("attemptOrdinal") or 0))
        previous_digest: str | None = None
        previous_host_binding: Mapping[str, Any] | None = None
        for ordinal, payload in enumerate(stage_rows, start=1):
            stable = {
                key: value for key, value in payload.items()
                if key != "envelopeDigest"
            }
            if payload.get("envelopeDigest") != _digest(stable):
                raise ValueError("ReliableTask job-set envelope digest mismatch")
            assert_valid(
                payload, "execution", "reliabletask_job_set_envelope",
                label=f"ReliableTask job-set:{execution_id}/{stage}/{ordinal}",
            )
            expected_tasks = payload.get("expectedTasks")
            host_binding = payload.get("workerHostSetBinding")
            pool_delivery_binding = payload.get("poolDeliveryBinding")
            if host_binding is not None and not isinstance(host_binding, Mapping):
                raise TypeError("ReliableTask worker host-set binding is invalid")
            if previous_host_binding is not None and host_binding is None:
                raise ValueError("ReliableTask worker host-set generation cannot regress")
            if (
                previous_host_binding is not None
                and host_binding is not None
                and host_binding != previous_host_binding
                and int(host_binding.get("generation") or 0)
                <= int(previous_host_binding.get("generation") or 0)
            ):
                raise ValueError("ReliableTask worker host-set generation cannot regress")
            if (
                not isinstance(expected_tasks, list)
                or payload.get("jobSetDigest")
                != _digest(
                    {
                        "expectedTasks": expected_tasks,
                        "workerHostSetBinding": host_binding,
                        "poolDeliveryBinding": pool_delivery_binding,
                    }
                )
            ):
                raise ValueError("ReliableTask expectedTasks/jobSetDigest mismatch")
            partitions = partition_count(len(expected_tasks))
            if _normalize_tasks(
                execution_id, stage, expected_tasks,
                governed_partition_count=partitions,
            ) != expected_tasks:
                raise ValueError("ReliableTask expectedTasks partition identity drift")
            expected = {
                "version": 4,
                "executionId": execution_id,
                "carrier": parse_execution_id(execution_id).content_type.value,
                "stage": stage,
                "attemptOrdinal": ordinal,
                "previousJobSetEnvelopeDigest": previous_digest,
                "queueBackendEnvelopeDigest": backend.get("envelopeDigest"),
                "executionManifestDigest": backend.get("executionManifestDigest"),
                "sourceDigest": backend.get("sourceDigest"),
                "targetSetDigest": backend.get("targetSetDigest"),
                "partitionCount": partitions,
                "partitionAlgorithm": PARTITION_ALGORITHM,
                "checkpointPolicy": checkpoint_policy_document(),
                "campaignBinding": (
                    pool_delivery_binding.get("campaignBinding")
                    if isinstance(pool_delivery_binding, Mapping)
                    else None
                ),
                "poolDeliveryBinding": pool_delivery_binding,
            }
            drift = [
                field for field, value in expected.items()
                if (field in payload or value is not None)
                and payload.get(field) != value
            ]
            if drift:
                raise ValueError(
                    "ReliableTask job-set immutable input drift: "
                    + ", ".join(drift)
                )
            previous_digest = str(payload["envelopeDigest"])
            previous_host_binding = host_binding
            rows.append(payload)
    return rows


def frozen_capacity_policy(execution_id: str) -> dict[str, Any]:
    """Read the capacity facts a job set carries from the frozen execution spec.

    `DEC-002` keeps the work-unit count, the capacity plan digest and the
    calibration binding on one truth source. The job set copies them from the
    frozen spec instead of accepting them from its caller, so no dispatch path
    can hand the fleet a ceiling the execution never froze.
    """
    from content.execution import store

    policy = (store.load_spec(execution_id) or {}).get("executionPolicy")
    if not isinstance(policy, Mapping):
        raise ValueError(
            f"ReliableTask job set requires a frozen executionPolicy: {execution_id}"
        )
    target_object_count = policy.get("targetObjectCount")
    if (
        isinstance(target_object_count, bool)
        or not isinstance(target_object_count, int)
        or target_object_count < 1
    ):
        raise ValueError("ReliableTask job set targetObjectCount is invalid")
    capacity_plan_digest = str(policy.get("capacityPlanDigest") or "").strip()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", capacity_plan_digest):
        raise ValueError("ReliableTask job set capacityPlanDigest is invalid")
    calibration = policy.get("capacityCalibration")
    if not isinstance(calibration, Mapping):
        raise ValueError("ReliableTask job set capacityCalibration is missing")
    from content.execution.planning.capacity_policy import frozen_capacity_calibration

    return {
        "targetObjectCount": target_object_count,
        "capacityPlanDigest": capacity_plan_digest,
        "capacityCalibration": frozen_capacity_calibration(calibration),
    }


def freeze_job_set(
    execution_id: str,
    stage: str,
    *,
    expected_tasks: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    from content.execution.queue.backend import load_execution_queue_backend
    from content.execution.queue.core import _queue_lock

    normalized = validate_execution_id(execution_id)
    with _queue_lock(normalized):
        backend = load_execution_queue_backend(normalized)
        backend_field = (
            "poolDeliveryBackend" if stage == "publish" else "queueBackend"
        )
        if backend.get(backend_field) != QueueBackend.RELIABLE_TASK.value:
            raise ValueError(
                f"ReliableTask {stage} job-set requires a reliabletask backend"
            )
        partitions = partition_count(len(expected_tasks))
        tasks = _normalize_tasks(
            normalized, stage, expected_tasks,
            governed_partition_count=partitions,
        )
        host_binding = _worker_host_binding(normalized)
        pool_delivery_binding = _pool_delivery_binding(normalized, stage)
        job_set_digest = _digest(
            {
                "expectedTasks": tasks,
                "workerHostSetBinding": host_binding,
                "poolDeliveryBinding": pool_delivery_binding,
            }
        )
        path = job_set_envelope_path(normalized, stage, job_set_digest)
        attempts = [row for row in _load(normalized, backend) if row["stage"] == stage]
        existing = read_json(path) if path.is_file() else None
        if existing is not None and not isinstance(existing, dict):
            raise ReliableTaskJobSetCollisionError(
                "immutable ReliableTask job-set attempt is not an object"
            )
        previous = max(
            attempts, key=lambda row: int(row["attemptOrdinal"]), default=None
        )
        ordinal = (
            int(existing["attemptOrdinal"])
            if existing is not None
            else int(previous["attemptOrdinal"]) + 1 if previous else 1
        )
        previous_digest = (
            existing.get("previousJobSetEnvelopeDigest")
            if existing is not None
            else previous.get("envelopeDigest") if previous else None
        )
        stable: dict[str, object] = {
            "schema": _SCHEMA,
            "version": 4,
            "executionId": normalized,
            "carrier": parse_execution_id(normalized).content_type.value,
            "stage": stage,
            "attemptOrdinal": ordinal,
            "previousJobSetEnvelopeDigest": previous_digest,
            "queueBackendEnvelopeDigest": backend["envelopeDigest"],
            "executionManifestDigest": backend["executionManifestDigest"],
            "sourceDigest": backend["sourceDigest"],
            "targetSetDigest": backend["targetSetDigest"],
            **frozen_capacity_policy(normalized),
            "partitionCount": partitions,
            "partitionAlgorithm": PARTITION_ALGORITHM,
            "checkpointPolicy": checkpoint_policy_document(),
            "expectedTasks": tasks,
            "jobSetDigest": job_set_digest,
        }
        campaign = (
            pool_delivery_binding.get("campaignBinding")
            if pool_delivery_binding is not None
            else None
        )
        if campaign is not None:
            stable["campaignBinding"] = campaign
        if pool_delivery_binding is not None:
            stable["poolDeliveryBinding"] = pool_delivery_binding
        if host_binding is not None:
            stable["workerHostSetBinding"] = host_binding
        envelope = {**stable, "envelopeDigest": _digest(stable)}
        assert_valid(
            envelope, "execution", "reliabletask_job_set_envelope",
            label=f"ReliableTask job-set:{normalized}/{stage}",
        )
        if existing is not None:
            if existing != envelope:
                raise ReliableTaskJobSetCollisionError(
                    f"immutable ReliableTask job-set attempt collision: {stage}/{job_set_digest}"
                )
            return envelope
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = (json.dumps(envelope, ensure_ascii=False, indent=2) + "\n").encode()
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            observed = read_json(path)
            if observed != envelope:
                raise ReliableTaskJobSetCollisionError(
                    f"immutable ReliableTask job-set attempt collision: {stage}/{job_set_digest}"
                )
            return envelope
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        return envelope


def load_job_sets(execution_id: str) -> tuple[dict[str, Any], ...]:
    from content.execution.queue.backend import load_execution_queue_backend

    normalized = validate_execution_id(execution_id)
    rows = _load(normalized, load_execution_queue_backend(normalized))
    if not rows:
        raise ValueError(
            "ReliableTask job-set envelope is missing; freeze jobs before observation"
        )
    return tuple(rows)


__all__ = [
    "RELIABLETASK_JOB_SET_ENVELOPE_DIR",
    "ReliableTaskJobSetCollisionError",
    "freeze_job_set",
    "job_set_envelope_path",
    "load_job_sets",
]
