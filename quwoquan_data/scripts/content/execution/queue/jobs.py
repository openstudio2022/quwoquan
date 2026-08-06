"""Typed object-queue job creation and definition refresh boundaries."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
from typing import Any

from core import ops_governance as og
from core.control_types import ContentType, QueueBackend, QueueJobStage
from governance.creators.assignment import creator_assignment_issues

from content.execution import store
from content.execution.queue.core import (
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_MAX_STARTUP_FAILURES,
    DEFAULT_MAX_WALL_CLOCK_SECONDS,
    DEFAULT_STUCK_THRESHOLD,
    DEFAULT_TOOL_PERMISSIONS,
    QUEUE_BACKEND_RELIABLETASK,
    _job_path,
    _read_job,
    _reliabletask_ref,
    _write_job,
    stable_job_id,
)
from content.execution.queue.model import QueueJob
from content.execution.queue_backend import resolve_execution_queue_backend


def _queue_stage(value: QueueJobStage | str) -> QueueJobStage:
    try:
        return QueueJobStage(str(value))
    except ValueError as exc:
        raise ValueError(f"unsupported object queue stage: {value!r}") from exc


def _optional_content_type(value: object, *, field_name: str) -> ContentType | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return ContentType(text)
    except ValueError as exc:
        raise ValueError(f"object job {field_name} is invalid: {text!r}") from exc


def _string_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise TypeError(f"object job {field_name} must be an array")
    return tuple(str(item).strip() for item in value if str(item).strip())


def _assignment_document(metadata: Mapping[str, object]) -> Mapping[str, object]:
    assignment = metadata.get("assignment")
    return assignment if isinstance(assignment, Mapping) else {}


def _backend_from_metadata(
    execution_id: str,
    metadata: Mapping[str, object],
    queue_backend: str | QueueBackend | None,
) -> QueueBackend:
    return resolve_execution_queue_backend(
        execution_id,
        requested=queue_backend,
        metadata_backend=metadata.get("queueBackend"),
    )


def _definition(
    *,
    execution_id: str,
    ref: str,
    stage: QueueJobStage,
    mutex_key: str | None,
    max_attempts: int,
    max_startup_failures: int,
    max_wall_clock_seconds: int,
    stuck_threshold: int,
    permissions: Iterable[str] | None,
    meta: Mapping[str, Any] | None,
    queue_backend: str | QueueBackend | None,
) -> dict[str, object]:
    """Decode the JSON-like enqueue request before it reaches queue control flow."""
    metadata: dict[str, object] = dict(meta or {})
    assignment = _assignment_document(metadata)
    strict_governance = bool(metadata.get("requireGovernance"))
    assignment_issues = og.validate_assignment_payload(assignment) if assignment else []
    if strict_governance and (not assignment or assignment_issues):
        details = "; ".join(assignment_issues or ["assignment required"])
        raise ValueError(f"object job governance assignment invalid for {ref}/{stage.value}: {details}")
    content_type = _optional_content_type(metadata.get("contentType"), field_name="contentType")
    carrier = _optional_content_type(metadata.get("carrier"), field_name="carrier")
    if stage is QueueJobStage.AUTHOR and (content_type or carrier) in {
        ContentType.ARTICLE,
        ContentType.IMAGE,
        ContentType.VIDEO,
    }:
        creator_issues = creator_assignment_issues(
            metadata,
            carrier=(content_type or carrier).value,
            prefix=f"objectJob[{ref}].creatorAssignment",
        )
        if creator_issues:
            raise ValueError("; ".join(creator_issues))
    backend = _backend_from_metadata(execution_id, metadata, queue_backend)
    partition_key = str(metadata.get("partitionKey") or mutex_key or ref).strip()
    if not partition_key:
        raise ValueError("object job partitionKey is required")
    return {
        "metadata": metadata,
        "assignment": assignment,
        "strictGovernance": strict_governance,
        "contentType": content_type,
        "carrier": carrier,
        "backend": backend,
        "partitionKey": partition_key,
        "mutexKey": str(mutex_key or ref).strip(),
        "maxAttempts": int(max_attempts),
        "maxStartupFailures": int(max_startup_failures),
        "maxWallClockSeconds": int(max_wall_clock_seconds),
        "stuckThreshold": int(stuck_threshold),
        "permissions": tuple(permissions) if permissions is not None else DEFAULT_TOOL_PERMISSIONS,
        "contentObjectDir": (
            str(metadata["contentObjectDir"]).strip().strip("/")
            if metadata.get("contentObjectDir") is not None
            else None
        ),
        "controllerRunId": str(metadata.get("controllerRunId") or assignment.get("controllerRunId") or "").strip(),
        "assignmentId": str(metadata.get("assignmentId") or assignment.get("assignmentId") or "").strip(),
        "assignmentPath": _string_tuple(metadata.get("assignmentPath") or assignment.get("assignmentPath"), field_name="assignmentPath"),
        "owner": str(metadata.get("owner") or assignment.get("role") or "").strip(),
        "allowedReadRoots": _string_tuple(metadata.get("allowedReadRoots") or assignment.get("allowedReadRoots"), field_name="allowedReadRoots"),
        "allowedWriteRoots": _string_tuple(metadata.get("allowedWriteRoots") or assignment.get("allowedWriteRoots"), field_name="allowedWriteRoots"),
        "sourceUnitId": str(metadata.get("sourceUnitId") or "").strip(),
        "sourceUnitIdRequired": bool(metadata.get("sourceUnitIdRequired")),
        "creatorProfileId": str(metadata.get("creatorProfileId") or "").strip(),
        "authorId": str(metadata.get("authorId") or "").strip(),
        "creatorArchetype": str(metadata.get("creatorArchetype") or "").strip(),
        "creatorProfileDigest": str(metadata.get("creatorProfileDigest") or "").strip(),
    }


def _reliable_task_reference(
    *,
    execution_id: str,
    job_id: str,
    ref: str,
    stage: QueueJobStage,
    definition: Mapping[str, object],
) -> Mapping[str, object] | None:
    backend = definition["backend"]
    if backend is not QUEUE_BACKEND_RELIABLETASK:
        return None
    metadata = definition["metadata"]
    if not isinstance(metadata, Mapping):
        raise TypeError("object job metadata decode failed")
    content_type = definition["contentType"]
    carrier = definition["carrier"]
    return _reliabletask_ref(
        execution_id=execution_id,
        job_id=job_id,
        ref=ref,
        stage=stage.value,
        partition_key=str(definition["partitionKey"]),
        entity_ref=str(metadata.get("entityRef") or metadata.get("targetRef") or ref),
        carrier=(carrier or content_type).value if carrier or content_type else "",
        source_revision=str(metadata.get("sourceRevision") or ""),
    )


def enqueue_ref_job(
    execution_id: str,
    ref: str,
    stage: QueueJobStage | str,
    *,
    mutex_key: str | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    max_startup_failures: int = DEFAULT_MAX_STARTUP_FAILURES,
    max_wall_clock_seconds: int = DEFAULT_MAX_WALL_CLOCK_SECONDS,
    stuck_threshold: int = DEFAULT_STUCK_THRESHOLD,
    permissions: Iterable[str] | None = None,
    meta: Mapping[str, Any] | None = None,
    queue_backend: str | QueueBackend | None = None,
) -> QueueJob:
    """Create one idempotent typed queue job.

    The request mapping is decoded here.  Existing jobs are never reset; an
    explicit retry uses the state-transition APIs in ``management`` instead.
    """
    queue_stage = _queue_stage(stage)
    job_id = stable_job_id(execution_id, ref, queue_stage.value)
    path = _job_path(execution_id, job_id)
    if path.is_file():
        return _read_job(execution_id, job_id)
    definition = _definition(
        execution_id=execution_id,
        ref=ref,
        stage=queue_stage,
        mutex_key=mutex_key,
        max_attempts=max_attempts,
        max_startup_failures=max_startup_failures,
        max_wall_clock_seconds=max_wall_clock_seconds,
        stuck_threshold=stuck_threshold,
        permissions=permissions,
        meta=meta,
        queue_backend=queue_backend,
    )
    job = QueueJob.create(
        job_id=job_id,
        execution_id=execution_id,
        ref=ref,
        stage=queue_stage,
        backend=definition["backend"],  # type: ignore[arg-type]
        partition_key=str(definition["partitionKey"]),
        content_object_dir=definition["contentObjectDir"],  # type: ignore[arg-type]
        mutex_key=str(definition["mutexKey"]),
        max_attempts=int(definition["maxAttempts"]),
        max_startup_failures=int(definition["maxStartupFailures"]),
        max_wall_clock_seconds=int(definition["maxWallClockSeconds"]),
        stuck_threshold=int(definition["stuckThreshold"]),
        permissions=definition["permissions"],  # type: ignore[arg-type]
        result_envelope_required=(
            definition["backend"] is QUEUE_BACKEND_RELIABLETASK
            or bool(definition["metadata"].get("resultEnvelopeRequired"))  # type: ignore[union-attr]
        ),
        reliable_task_ref=_reliable_task_reference(
            execution_id=execution_id,
            job_id=job_id,
            ref=ref,
            stage=queue_stage,
            definition=definition,
        ),
        metadata=definition["metadata"],  # type: ignore[arg-type]
        controller_run_id=str(definition["controllerRunId"]),
        assignment_id=str(definition["assignmentId"]),
        assignment_path=definition["assignmentPath"],  # type: ignore[arg-type]
        owner=str(definition["owner"]),
        allowed_read_roots=definition["allowedReadRoots"],  # type: ignore[arg-type]
        allowed_write_roots=definition["allowedWriteRoots"],  # type: ignore[arg-type]
        source_unit_id=str(definition["sourceUnitId"]),
        require_governance=bool(definition["strictGovernance"]),
        source_unit_id_required=bool(definition["sourceUnitIdRequired"]),
        creator_profile_id=str(definition["creatorProfileId"]),
        author_id=str(definition["authorId"]),
        creator_archetype=str(definition["creatorArchetype"]),
        creator_profile_digest=str(definition["creatorProfileDigest"]),
        content_type=definition["contentType"],  # type: ignore[arg-type]
        carrier=definition["carrier"],  # type: ignore[arg-type]
        created_at=store.now_iso(),
    )
    _write_job(job)
    return job


def enqueue_ref_jobs(
    execution_id: str,
    items: Iterable[Mapping[str, Any]],
    stage: QueueJobStage | str,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    max_startup_failures: int = DEFAULT_MAX_STARTUP_FAILURES,
    max_wall_clock_seconds: int = DEFAULT_MAX_WALL_CLOCK_SECONDS,
    queue_backend: str | QueueBackend | None = None,
) -> list[QueueJob]:
    """Decode a batch of enqueue packets at the sole queue input boundary."""
    jobs: list[QueueJob] = []
    for item in items:
        ref = str(item.get("ref") or "").strip()
        if not ref:
            raise ValueError("object queue item ref is required")
        item_meta = item.get("meta")
        metadata = item_meta if isinstance(item_meta, Mapping) else {}
        jobs.append(
            enqueue_ref_job(
                execution_id,
                ref,
                stage,
                mutex_key=str(item.get("baseSourceRef") or "") or ref,
                max_attempts=max_attempts,
                max_startup_failures=max_startup_failures,
                max_wall_clock_seconds=max_wall_clock_seconds,
                queue_backend=queue_backend,
                meta=metadata,
            )
        )
    return jobs


def refresh_job_definition(
    execution_id: str,
    ref: str,
    stage: QueueJobStage | str,
    *,
    mutex_key: str | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    max_startup_failures: int = DEFAULT_MAX_STARTUP_FAILURES,
    max_wall_clock_seconds: int = DEFAULT_MAX_WALL_CLOCK_SECONDS,
    stuck_threshold: int = DEFAULT_STUCK_THRESHOLD,
    permissions: Iterable[str] | None = None,
    meta: Mapping[str, Any] | None = None,
    queue_backend: str | QueueBackend | None = None,
) -> QueueJob | None:
    """Refresh immutable definition fields without resetting execution state."""
    queue_stage = _queue_stage(stage)
    job_id = stable_job_id(execution_id, ref, queue_stage.value)
    path = _job_path(execution_id, job_id)
    if not path.is_file():
        return None
    previous = _read_job(execution_id, job_id)
    definition = _definition(
        execution_id=execution_id,
        ref=ref,
        stage=queue_stage,
        mutex_key=mutex_key,
        max_attempts=max_attempts,
        max_startup_failures=max_startup_failures,
        max_wall_clock_seconds=max_wall_clock_seconds,
        stuck_threshold=stuck_threshold,
        permissions=permissions,
        meta=meta,
        queue_backend=queue_backend if queue_backend is not None else previous.backend,
    )
    backend = definition["backend"]
    refreshed = replace(
        previous,
        backend=backend,  # type: ignore[arg-type]
        partition_key=str(definition["partitionKey"]),
        content_object_dir=definition["contentObjectDir"],  # type: ignore[arg-type]
        mutex_key=str(definition["mutexKey"]),
        max_attempts=int(definition["maxAttempts"]),
        max_startup_failures=int(definition["maxStartupFailures"]),
        max_wall_clock_seconds=int(definition["maxWallClockSeconds"]),
        stuck_threshold=int(definition["stuckThreshold"]),
        permissions=definition["permissions"],  # type: ignore[arg-type]
        result_envelope_required=(
            backend is QUEUE_BACKEND_RELIABLETASK
            or bool(definition["metadata"].get("resultEnvelopeRequired"))  # type: ignore[union-attr]
        ),
        reliable_task_ref_json=(
            previous.reliable_task_ref_json
            if backend is not QUEUE_BACKEND_RELIABLETASK
            else QueueJob.create(
                job_id=previous.job_id,
                execution_id=previous.execution_id,
                ref=previous.ref,
                stage=previous.stage,
                backend=backend,  # type: ignore[arg-type]
                partition_key=str(definition["partitionKey"]),
                content_object_dir=definition["contentObjectDir"],  # type: ignore[arg-type]
                mutex_key=str(definition["mutexKey"]),
                max_attempts=int(definition["maxAttempts"]),
                max_startup_failures=int(definition["maxStartupFailures"]),
                max_wall_clock_seconds=int(definition["maxWallClockSeconds"]),
                stuck_threshold=int(definition["stuckThreshold"]),
                permissions=definition["permissions"],  # type: ignore[arg-type]
                result_envelope_required=True,
                reliable_task_ref=_reliable_task_reference(execution_id=execution_id, job_id=job_id, ref=ref, stage=queue_stage, definition=definition),
                metadata=definition["metadata"],  # type: ignore[arg-type]
                controller_run_id=str(definition["controllerRunId"]),
                assignment_id=str(definition["assignmentId"]),
                assignment_path=definition["assignmentPath"],  # type: ignore[arg-type]
                owner=str(definition["owner"]),
                allowed_read_roots=definition["allowedReadRoots"],  # type: ignore[arg-type]
                allowed_write_roots=definition["allowedWriteRoots"],  # type: ignore[arg-type]
                source_unit_id=str(definition["sourceUnitId"]),
                require_governance=bool(definition["strictGovernance"]),
                source_unit_id_required=bool(definition["sourceUnitIdRequired"]),
                creator_profile_id=str(definition["creatorProfileId"]),
                author_id=str(definition["authorId"]),
                creator_archetype=str(definition["creatorArchetype"]),
                creator_profile_digest=str(definition["creatorProfileDigest"]),
                content_type=definition["contentType"],  # type: ignore[arg-type]
                carrier=definition["carrier"],  # type: ignore[arg-type]
                created_at=previous.created_at,
            ).reliable_task_ref_json
        ),
        meta_json=QueueJob.create(
            job_id=previous.job_id,
            execution_id=previous.execution_id,
            ref=previous.ref,
            stage=previous.stage,
            backend=backend,  # type: ignore[arg-type]
            partition_key=str(definition["partitionKey"]),
            content_object_dir=definition["contentObjectDir"],  # type: ignore[arg-type]
            mutex_key=str(definition["mutexKey"]),
            max_attempts=int(definition["maxAttempts"]),
            max_startup_failures=int(definition["maxStartupFailures"]),
            max_wall_clock_seconds=int(definition["maxWallClockSeconds"]),
            stuck_threshold=int(definition["stuckThreshold"]),
            permissions=definition["permissions"],  # type: ignore[arg-type]
            result_envelope_required=backend is QUEUE_BACKEND_RELIABLETASK,
            reliable_task_ref=None,
            metadata=definition["metadata"],  # type: ignore[arg-type]
            controller_run_id=str(definition["controllerRunId"]),
            assignment_id=str(definition["assignmentId"]),
            assignment_path=definition["assignmentPath"],  # type: ignore[arg-type]
            owner=str(definition["owner"]),
            allowed_read_roots=definition["allowedReadRoots"],  # type: ignore[arg-type]
            allowed_write_roots=definition["allowedWriteRoots"],  # type: ignore[arg-type]
            source_unit_id=str(definition["sourceUnitId"]),
            require_governance=bool(definition["strictGovernance"]),
            source_unit_id_required=bool(definition["sourceUnitIdRequired"]),
            creator_profile_id=str(definition["creatorProfileId"]),
            author_id=str(definition["authorId"]),
            creator_archetype=str(definition["creatorArchetype"]),
            creator_profile_digest=str(definition["creatorProfileDigest"]),
            content_type=definition["contentType"],  # type: ignore[arg-type]
            carrier=definition["carrier"],  # type: ignore[arg-type]
            created_at=previous.created_at,
        ).meta_json,
        controller_run_id=str(definition["controllerRunId"]),
        assignment_id=str(definition["assignmentId"]),
        assignment_path=definition["assignmentPath"],  # type: ignore[arg-type]
        owner=str(definition["owner"]),
        allowed_read_roots=definition["allowedReadRoots"],  # type: ignore[arg-type]
        allowed_write_roots=definition["allowedWriteRoots"],  # type: ignore[arg-type]
        source_unit_id=str(definition["sourceUnitId"]),
        require_governance=bool(definition["strictGovernance"]),
        source_unit_id_required=bool(definition["sourceUnitIdRequired"]),
        creator_profile_id=str(definition["creatorProfileId"]),
        author_id=str(definition["authorId"]),
        creator_archetype=str(definition["creatorArchetype"]),
        creator_profile_digest=str(definition["creatorProfileDigest"]),
        content_type=definition["contentType"],  # type: ignore[arg-type]
        carrier=definition["carrier"],  # type: ignore[arg-type]
        updated_at=store.now_iso(),
    )
    _write_job(refreshed)
    return refreshed


__all__ = ["enqueue_ref_job", "enqueue_ref_jobs", "refresh_job_definition"]
