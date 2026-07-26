"""Typed object-queue records and their JSON boundary codec.

Queue documents are runtime artefacts.  They are decoded once here and the
queue controller only receives immutable value objects; no lifecycle decision
may be based on a raw JSON mapping.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Any, Mapping

from core.control_types import (
    ContentType,
    QueueBackend,
    QueueFailureKind,
    QueueJobStage,
    QueueJobState,
    QueueTimelineEvent,
)
from core.data_issue import (
    DataIssue,
    DataIssueCode,
    DataIssueLane,
    DataIssueStage,
    DataRecoveryAction,
    data_issue,
)
from core.schema import assert_valid
from content.execution import production_contracts as pc


def _required_text(value: object, *, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"object queue {field_name} is required")
    return text


def _text(value: object) -> str:
    return str(value or "").strip()


def _integer(value: object, *, field_name: str, minimum: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"object queue {field_name} must be an integer") from exc
    if parsed < minimum:
        raise ValueError(f"object queue {field_name} must be >= {minimum}")
    return parsed


def _number(value: object, *, field_name: str, minimum: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"object queue {field_name} must be a number") from exc
    if parsed < minimum:
        raise ValueError(f"object queue {field_name} must be >= {minimum}")
    return parsed


def _string_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"object queue {field_name} must be an array")
    return tuple(_required_text(item, field_name=field_name) for item in value)


def _document_json(value: object, *, field_name: str) -> str:
    if value is None:
        value = {}
    if not isinstance(value, Mapping):
        raise ValueError(f"object queue {field_name} must be an object")
    try:
        return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"object queue {field_name} must be JSON-serializable") from exc


def _decode_document(value: str, *, field_name: str) -> dict[str, object]:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"object queue {field_name} is invalid JSON") from exc
    if not isinstance(decoded, dict):
        raise ValueError(f"object queue {field_name} must decode to an object")
    return decoded


def _array_json(value: str, *, field_name: str) -> list[object]:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"object queue {field_name} is invalid JSON") from exc
    if not isinstance(decoded, list):
        raise ValueError(f"object queue {field_name} must decode to an array")
    return decoded


def _optional_content_type(value: object, *, field_name: str) -> ContentType | None:
    text = _text(value)
    if not text:
        return None
    try:
        return ContentType(text)
    except ValueError as exc:
        raise ValueError(f"object queue {field_name} is invalid: {text!r}") from exc


def _queue_issue_stage(stage: QueueJobStage) -> DataIssueStage:
    return {
        QueueJobStage.DOWNLOAD: DataIssueStage.DOWNLOAD,
        QueueJobStage.AUTHOR: DataIssueStage.AUTHOR,
        QueueJobStage.PUBLISH: DataIssueStage.PUBLISH,
    }[stage]


def _issue_code(kind: QueueFailureKind) -> DataIssueCode:
    return {
        QueueFailureKind.EXECUTION: DataIssueCode.QUEUE_EXECUTION_FAILED,
        QueueFailureKind.GOVERNANCE: DataIssueCode.QUEUE_GOVERNANCE_INVALID,
        QueueFailureKind.STARTUP: DataIssueCode.QUEUE_STARTUP_FAILED,
        QueueFailureKind.RESULT_ENVELOPE: DataIssueCode.QUEUE_RESULT_ENVELOPE_INVALID,
        QueueFailureKind.TIMEOUT: DataIssueCode.QUEUE_TIMEOUT,
    }[kind]


@dataclass(frozen=True, slots=True)
class QueueLease:
    holder: str | None = None
    expires_epoch: float = 0.0
    deadline_epoch: float = 0.0

    def is_expired(self, now: float) -> bool:
        return bool(self.holder) and self.expires_epoch <= now

    def to_document(self) -> tuple[str | None, float, float]:
        return self.holder, self.expires_epoch, self.deadline_epoch


@dataclass(frozen=True, slots=True)
class QueueTiming:
    event: QueueTimelineEvent
    at: str
    attributes_json: str = "{}"

    @classmethod
    def create(
        cls,
        event: QueueTimelineEvent,
        *,
        at: str,
        attributes: Mapping[str, object] | None = None,
    ) -> "QueueTiming":
        return cls(event=event, at=_required_text(at, field_name="timing.at"), attributes_json=_document_json(attributes, field_name="timing.attributes"))

    @classmethod
    def from_document(cls, value: object) -> "QueueTiming":
        if not isinstance(value, Mapping):
            raise ValueError("object queue timing must be an object")
        try:
            event = QueueTimelineEvent(_required_text(value.get("event"), field_name="timing.event"))
        except ValueError as exc:
            raise ValueError(f"object queue timing event is invalid: {exc}") from exc
        attributes = {key: raw for key, raw in value.items() if key not in {"event", "at"}}
        return cls.create(event, at=_required_text(value.get("at"), field_name="timing.at"), attributes=attributes)

    def to_document(self) -> dict[str, object]:
        return {"event": self.event.value, "at": self.at, **_decode_document(self.attributes_json, field_name="timing.attributes")}


@dataclass(frozen=True, slots=True)
class QueueJob:
    job_id: str
    execution_id: str
    ref: str
    stage: QueueJobStage
    backend: QueueBackend
    partition_key: str
    state: QueueJobState
    content_object_dir: str | None
    mutex_key: str
    max_attempts: int
    max_startup_failures: int
    max_wall_clock_seconds: int
    stuck_threshold: int
    permissions: tuple[str, ...]
    result_envelope_required: bool
    result_envelope_ref: str | None
    attempt: int = 0
    lease: QueueLease = field(default_factory=QueueLease)
    not_before_epoch: float = 0.0
    same_run_retryable: bool = True
    startup_failure_count: int = 0
    failure_fingerprints: tuple[str, ...] = ()
    stuck_detected: bool = False
    last_issue: DataIssue | None = None
    gate_verdicts_json: str = "[]"
    reliable_task_ref_json: str = "null"
    meta_json: str = "{}"
    timings: tuple[QueueTiming, ...] = ()
    controller_run_id: str = ""
    assignment_id: str = ""
    assignment_path: tuple[str, ...] = ()
    owner: str = ""
    allowed_read_roots: tuple[str, ...] = ()
    allowed_write_roots: tuple[str, ...] = ()
    source_unit_id: str = ""
    require_governance: bool = False
    source_unit_id_required: bool = False
    creator_profile_id: str = ""
    author_id: str = ""
    creator_archetype: str = ""
    creator_profile_version: str = ""
    content_type: ContentType | None = None
    carrier: ContentType | None = None
    agent_run_id: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        for field_name in ("job_id", "execution_id", "ref", "partition_key", "mutex_key", "created_at", "updated_at"):
            _required_text(getattr(self, field_name), field_name=field_name)
        if self.max_attempts < 1 or self.max_startup_failures < 1:
            raise ValueError("object queue attempt limits must be positive")
        if self.max_wall_clock_seconds < 1 or self.stuck_threshold < 1:
            raise ValueError("object queue execution limits must be positive")
        if self.attempt < 0 or self.startup_failure_count < 0:
            raise ValueError("object queue counters must not be negative")
        _array_json(self.gate_verdicts_json, field_name="gateVerdicts")
        _decode_document(self.meta_json, field_name="meta")
        try:
            parsed_ref = json.loads(self.reliable_task_ref_json)
        except json.JSONDecodeError as exc:
            raise ValueError("object queue JSON field is invalid") from exc
        if parsed_ref is not None and not isinstance(parsed_ref, dict):
            raise ValueError("object queue reliableTaskRef must be an object or null")

    @classmethod
    def create(
        cls,
        *,
        job_id: str,
        execution_id: str,
        ref: str,
        stage: QueueJobStage,
        backend: QueueBackend,
        partition_key: str,
        content_object_dir: str | None,
        mutex_key: str,
        max_attempts: int,
        max_startup_failures: int,
        max_wall_clock_seconds: int,
        stuck_threshold: int,
        permissions: tuple[str, ...],
        result_envelope_required: bool,
        reliable_task_ref: Mapping[str, object] | None,
        metadata: Mapping[str, object],
        controller_run_id: str,
        assignment_id: str,
        assignment_path: tuple[str, ...],
        owner: str,
        allowed_read_roots: tuple[str, ...],
        allowed_write_roots: tuple[str, ...],
        source_unit_id: str,
        require_governance: bool,
        source_unit_id_required: bool,
        creator_profile_id: str,
        author_id: str,
        creator_archetype: str,
        creator_profile_version: str,
        content_type: ContentType | None,
        carrier: ContentType | None,
        created_at: str,
    ) -> "QueueJob":
        return cls(
            job_id=job_id,
            execution_id=execution_id,
            ref=ref,
            stage=stage,
            backend=backend,
            partition_key=partition_key,
            state=QueueJobState.QUEUED,
            content_object_dir=content_object_dir,
            mutex_key=mutex_key,
            max_attempts=max_attempts,
            max_startup_failures=max_startup_failures,
            max_wall_clock_seconds=max_wall_clock_seconds,
            stuck_threshold=stuck_threshold,
            permissions=permissions,
            result_envelope_required=result_envelope_required,
            result_envelope_ref=None,
            reliable_task_ref_json=json.dumps(reliable_task_ref, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            meta_json=_document_json(metadata, field_name="meta"),
            controller_run_id=controller_run_id,
            assignment_id=assignment_id,
            assignment_path=assignment_path,
            owner=owner,
            allowed_read_roots=allowed_read_roots,
            allowed_write_roots=allowed_write_roots,
            source_unit_id=source_unit_id,
            require_governance=require_governance,
            source_unit_id_required=source_unit_id_required,
            creator_profile_id=creator_profile_id,
            author_id=author_id,
            creator_archetype=creator_archetype,
            creator_profile_version=creator_profile_version,
            content_type=content_type,
            carrier=carrier,
            created_at=created_at,
            updated_at=created_at,
        )

    @classmethod
    def from_document(cls, value: object) -> "QueueJob":
        if not isinstance(value, Mapping):
            raise ValueError("object queue document must be an object")
        document = dict(value)
        assert_valid(document, "content", "object_job", label="object queue job")
        try:
            stage = QueueJobStage(_required_text(document.get("stage"), field_name="stage"))
            backend = QueueBackend(_required_text(document.get("queueBackend"), field_name="queueBackend"))
            state = QueueJobState(_required_text(document.get("state"), field_name="state"))
        except ValueError as exc:
            raise ValueError(f"object queue closed field is invalid: {exc}") from exc
        timing_value = document.get("timings") or []
        if not isinstance(timing_value, list):
            raise ValueError("object queue timings must be an array")
        last_issue_value = document.get("lastIssue")
        issue = DataIssue.from_dict(last_issue_value) if last_issue_value is not None else None
        metadata = document.get("meta") or {}
        raw_content_object_dir = document.get("contentObjectDir")
        if raw_content_object_dir is None:
            content_object_dir = None
        elif isinstance(raw_content_object_dir, str) and raw_content_object_dir.strip():
            content_object_dir = raw_content_object_dir.strip().strip("/")
        else:
            raise ValueError(
                "object queue contentObjectDir must be a non-empty string or null"
            )
        return cls(
            job_id=_required_text(document.get("jobId"), field_name="jobId"),
            execution_id=_required_text(document.get("executionId"), field_name="executionId"),
            ref=_required_text(document.get("ref"), field_name="ref"),
            stage=stage,
            backend=backend,
            partition_key=_required_text(document.get("partitionKey"), field_name="partitionKey"),
            state=state,
            content_object_dir=content_object_dir,
            mutex_key=_required_text(document.get("mutexKey") or document.get("ref"), field_name="mutexKey"),
            max_attempts=_integer(document.get("maxAttempts"), field_name="maxAttempts", minimum=1),
            max_startup_failures=_integer(document.get("maxStartupFailures"), field_name="maxStartupFailures", minimum=1),
            max_wall_clock_seconds=_integer(document.get("maxWallClockSeconds"), field_name="maxWallClockSeconds", minimum=1),
            stuck_threshold=_integer(document.get("stuckThreshold"), field_name="stuckThreshold", minimum=1),
            permissions=_string_tuple(document.get("permissions"), field_name="permissions"),
            result_envelope_required=bool(document.get("resultEnvelopeRequired")),
            result_envelope_ref=_text(document.get("resultEnvelopeRef")) or None,
            attempt=_integer(document.get("attempt"), field_name="attempt"),
            lease=QueueLease(
                holder=_text(document.get("lease")) or None,
                expires_epoch=_number(document.get("leaseExpiresEpoch"), field_name="leaseExpiresEpoch"),
                deadline_epoch=_number(document.get("deadlineEpoch"), field_name="deadlineEpoch"),
            ),
            not_before_epoch=_number(document.get("notBeforeEpoch"), field_name="notBeforeEpoch"),
            same_run_retryable=bool(document.get("sameRunRetryable", True)),
            startup_failure_count=_integer(document.get("startupFailureCount"), field_name="startupFailureCount"),
            failure_fingerprints=_string_tuple(document.get("failureFingerprints"), field_name="failureFingerprints"),
            stuck_detected=bool(document.get("stuckDetected")),
            last_issue=issue,
            gate_verdicts_json=json.dumps(document.get("gateVerdicts") or [], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            reliable_task_ref_json=json.dumps(document.get("reliableTaskRef"), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            meta_json=_document_json(metadata, field_name="meta"),
            timings=tuple(QueueTiming.from_document(item) for item in timing_value),
            controller_run_id=_text(document.get("controllerRunId")),
            assignment_id=_text(document.get("assignmentId")),
            assignment_path=_string_tuple(document.get("assignmentPath"), field_name="assignmentPath"),
            owner=_text(document.get("owner")),
            allowed_read_roots=_string_tuple(document.get("allowedReadRoots"), field_name="allowedReadRoots"),
            allowed_write_roots=_string_tuple(document.get("allowedWriteRoots"), field_name="allowedWriteRoots"),
            source_unit_id=_text(document.get("sourceUnitId")),
            require_governance=bool(document.get("requireGovernance")),
            source_unit_id_required=bool(document.get("sourceUnitIdRequired")),
            creator_profile_id=_text(document.get("creatorProfileId")),
            author_id=_text(document.get("authorId")),
            creator_archetype=_text(document.get("creatorArchetype")),
            creator_profile_version=_text(document.get("creatorProfileVersion")),
            content_type=_optional_content_type(document.get("contentType"), field_name="contentType"),
            carrier=_optional_content_type(document.get("carrier"), field_name="carrier"),
            agent_run_id=_text(document.get("agentRunId")),
            created_at=_required_text(document.get("createdAt"), field_name="createdAt"),
            updated_at=_required_text(document.get("updatedAt"), field_name="updatedAt"),
        )

    def metadata_document(self) -> dict[str, object]:
        return _decode_document(self.meta_json, field_name="meta")

    def gate_verdicts_document(self) -> list[object]:
        return _array_json(self.gate_verdicts_json, field_name="gateVerdicts")

    def reliable_task_ref_document(self) -> dict[str, object] | None:
        value = json.loads(self.reliable_task_ref_json)
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError("object queue reliableTaskRef must be an object or null")
        return value

    def governance_issues(self) -> tuple[str, ...]:
        if not self.require_governance:
            return ()
        missing: list[str] = []
        if not self.controller_run_id:
            missing.append("controllerRunId required")
        if not self.assignment_id:
            missing.append("assignmentId required")
        if not self.assignment_path:
            missing.append("assignmentPath required")
        if not self.owner:
            missing.append("owner required")
        if self.source_unit_id_required and not self.source_unit_id:
            missing.append("sourceUnitId required")
        return tuple(missing)

    def with_timing(
        self,
        event: QueueTimelineEvent,
        *,
        at: str,
        attributes: Mapping[str, object] | None = None,
        **changes: object,
    ) -> "QueueJob":
        return replace(
            self,
            timings=(*self.timings, QueueTiming.create(event, at=at, attributes=attributes)),
            updated_at=at,
            **changes,
        )

    def issue(
        self,
        kind: QueueFailureKind,
        *,
        message: str,
        recovery: DataRecoveryAction,
    ) -> DataIssue:
        return data_issue(
            _issue_code(kind),
            stage=_queue_issue_stage(self.stage),
            message=message,
            ref=self.ref,
            lane=DataIssueLane.ALL,
            recovery=recovery,
            attributes={"jobId": self.job_id, "queueStage": self.stage.value},
        )

    def to_document(self) -> dict[str, object]:
        lease, lease_expiry, deadline = self.lease.to_document()
        return {
            "schema": pc.OBJECT_JOB_SCHEMA,
            "jobId": self.job_id,
            "executionId": self.execution_id,
            "ref": self.ref,
            "stage": self.stage.value,
            "queueBackend": self.backend.value,
            "partitionKey": self.partition_key,
            "contentObjectDir": self.content_object_dir,
            "controllerRunId": self.controller_run_id,
            "assignmentId": self.assignment_id,
            "assignmentPath": list(self.assignment_path),
            "owner": self.owner,
            "allowedReadRoots": list(self.allowed_read_roots),
            "allowedWriteRoots": list(self.allowed_write_roots),
            "sourceUnitId": self.source_unit_id,
            "requireGovernance": self.require_governance,
            "sourceUnitIdRequired": self.source_unit_id_required,
            "reliableTaskRef": self.reliable_task_ref_document(),
            "resultEnvelopeRequired": self.result_envelope_required,
            "resultEnvelopeRef": self.result_envelope_ref,
            "gateVerdicts": self.gate_verdicts_document(),
            "creatorProfileId": self.creator_profile_id or None,
            "authorId": self.author_id or None,
            "creatorArchetype": self.creator_archetype or None,
            "creatorProfileVersion": self.creator_profile_version or None,
            "contentType": self.content_type.value if self.content_type else None,
            "carrier": self.carrier.value if self.carrier else None,
            "agentRunId": self.agent_run_id or None,
            "state": self.state.value,
            "attempt": self.attempt,
            "maxAttempts": self.max_attempts,
            "maxStartupFailures": self.max_startup_failures,
            "maxWallClockSeconds": self.max_wall_clock_seconds,
            "stuckThreshold": self.stuck_threshold,
            "permissions": list(self.permissions),
            "failureFingerprints": list(self.failure_fingerprints),
            "mutexKey": self.mutex_key,
            "lease": lease,
            "leaseExpiresEpoch": lease_expiry,
            "deadlineEpoch": deadline,
            "notBeforeEpoch": self.not_before_epoch,
            "sameRunRetryable": self.same_run_retryable,
            "startupFailureCount": self.startup_failure_count,
            "stuckDetected": self.stuck_detected,
            "lastIssue": self.last_issue.as_dict() if self.last_issue else None,
            "timings": [item.to_document() for item in self.timings],
            "meta": self.metadata_document(),
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


__all__ = [
    "QueueJob",
    "QueueLease",
    "QueueTiming",
]
