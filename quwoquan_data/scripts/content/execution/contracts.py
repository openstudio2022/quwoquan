"""Immutable execution documents after schema/codec admission."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from core.control_types import ExecutionStateStatus


@dataclass(frozen=True, slots=True)
class ExecutionRuntimeState:
    """Immutable audit state for commands applied to one execution workspace."""

    schema: str
    execution_id: str
    target_set_digest: str
    command_chain: tuple[str, ...]
    created_at: str
    updated_at: str
    execution_sequence: int

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ExecutionRuntimeState":
        required = {
            "schema",
            "executionId",
            "targetSetDigest",
            "commandChain",
            "createdAt",
            "updatedAt",
            "executionSequence",
        }
        missing = sorted(required - set(payload))
        if missing:
            raise ValueError(f"execution runtime state is missing fields: {missing}")
        command_chain = payload["commandChain"]
        if not isinstance(command_chain, list) or not all(
            isinstance(item, str) and item for item in command_chain
        ):
            raise TypeError("execution runtime state commandChain must contain strings")
        sequence = payload["executionSequence"]
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise ValueError("execution runtime state executionSequence must be positive")
        strings = {
            key: payload[key]
            for key in required - {"commandChain", "executionSequence"}
        }
        if not all(isinstance(value, str) and value for value in strings.values()):
            raise TypeError("execution runtime state identity fields must be non-empty strings")
        return cls(
            schema=strings["schema"],
            execution_id=strings["executionId"],
            target_set_digest=strings["targetSetDigest"],
            command_chain=tuple(command_chain),
            created_at=strings["createdAt"],
            updated_at=strings["updatedAt"],
            execution_sequence=sequence,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "executionId": self.execution_id,
            "targetSetDigest": self.target_set_digest,
            "commandChain": list(self.command_chain),
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "executionSequence": self.execution_sequence,
        }


@dataclass(frozen=True, slots=True)
class FrozenObject:
    """Deeply immutable JSON object admitted by the execution-state codec."""

    items: tuple[tuple[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class FrozenArray:
    """Deeply immutable JSON array admitted by the execution-state codec."""

    items: tuple[object, ...] = ()


def _freeze_json(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return FrozenObject(
            tuple(
                (str(key), _freeze_json(item))
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            )
        )
    if isinstance(value, (list, tuple)):
        return FrozenArray(tuple(_freeze_json(item) for item in value))
    raise TypeError(f"execution state contains non-JSON value: {type(value).__name__}")


def _thaw_json(value: object) -> object:
    if isinstance(value, FrozenObject):
        return {key: _thaw_json(item) for key, item in value.items}
    if isinstance(value, FrozenArray):
        return [_thaw_json(item) for item in value.items]
    return value


def _string_tuple(value: object, *, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"execution state {field} must contain strings")
    return tuple(value)


def _counter_tuple(value: object, *, field: str) -> tuple[tuple[str, int], ...]:
    if value is None:
        return ()
    if not isinstance(value, Mapping):
        raise TypeError(f"execution state {field} must be an object")
    rows: list[tuple[str, int]] = []
    for key, raw_count in value.items():
        if isinstance(raw_count, bool) or not isinstance(raw_count, int) or raw_count < 0:
            raise TypeError(f"execution state {field}.{key} must be a non-negative integer")
        rows.append((str(key), raw_count))
    return tuple(sorted(rows))


def _optional_string(payload: Mapping[str, Any], field: str) -> str | None:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"execution state {field} must be a string or null")
    return value


@dataclass(frozen=True, slots=True)
class ExecutionState:
    """Deeply immutable persisted workflow state.

    Domain code never mutates this snapshot. A controller opens one explicit
    :class:`ExecutionStateTransition`, applies changes, and freezes it again at
    the schema-validated persistence boundary.
    """

    schema: str
    execution_id: str
    completed: tuple[str, ...]
    status: ExecutionStateStatus
    updated_at: str
    waiting_checkpoint: str | None = None
    owner: str | None = None
    heartbeat_at: str | None = None
    started_at: str | None = None
    next_action: object = None
    stopped_at_stage: str | None = None
    interrupt_reason: object = None
    last_failed_stage: str | None = None
    retry_counts: tuple[tuple[str, int], ...] = ()
    infrastructure_retry_counts: tuple[tuple[str, int], ...] = ()
    failed_objects: tuple[object, ...] = ()
    failed_issue_records: tuple[object, ...] = ()
    baseline_packet_path: str | None = None
    baseline_packet_summary: object = None
    workspace_cleanup_reports: tuple[object, ...] = ()
    completion_gate_issues: tuple[object, ...] = ()
    quality: object = FrozenObject()
    throughput: object = FrozenObject()
    controller: object = FrozenObject()
    controller_yield: object = None
    controller_yield_recovery_actions: tuple[object, ...] = ()
    recovery_actions: tuple[object, ...] = ()
    scheduler_recovery_actions: tuple[object, ...] = ()
    auto_research_recovery_actions: tuple[object, ...] = ()
    active_agent_scheduler: object = None
    active_auto_research: object = None
    agent_run_history: tuple[object, ...] = ()
    last_agent_run: object = None
    react_rewinds: object = FrozenObject()
    managed_checkpoint_interruption: object = None
    managed_infra_recovery_cutoffs: object = FrozenObject()
    manual_repair_resumes: tuple[object, ...] = ()
    produce_review_retry_history: object = FrozenArray()
    last_author_finalize_count: int = 0
    last_object_queue_author_finalize_count: int = 0
    quarantine: object = FrozenObject()

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ExecutionState":
        schema = payload.get("schema")
        execution_id = payload.get("executionId")
        updated_at = payload.get("updatedAt")
        if not isinstance(schema, str) or not schema:
            raise TypeError("execution state schema must be a non-empty string")
        if not isinstance(execution_id, str) or not execution_id:
            raise TypeError("execution state executionId must be a non-empty string")
        if not isinstance(updated_at, str) or not updated_at:
            raise TypeError("execution state updatedAt must be a non-empty string")
        try:
            status = ExecutionStateStatus(str(payload.get("status") or ""))
        except ValueError as exc:
            raise ValueError(
                f"execution state has invalid status: {payload.get('status')!r}"
            ) from exc

        def frozen(field: str, default: object = None) -> object:
            return _freeze_json(payload.get(field, default))

        def frozen_rows(field: str) -> tuple[object, ...]:
            value = frozen(field, [])
            if not isinstance(value, FrozenArray):
                raise TypeError(f"execution state {field} must be an array")
            return value.items

        def non_negative_int(field: str) -> int:
            value = payload.get(field, 0)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise TypeError(f"execution state {field} must be a non-negative integer")
            return value

        return cls(
            schema=schema,
            execution_id=execution_id,
            completed=_string_tuple(payload.get("completed"), field="completed"),
            status=status,
            updated_at=updated_at,
            waiting_checkpoint=_optional_string(payload, "waitingCheckpoint"),
            owner=_optional_string(payload, "owner"),
            heartbeat_at=_optional_string(payload, "heartbeatAt"),
            started_at=_optional_string(payload, "startedAt"),
            next_action=frozen("nextAction"),
            stopped_at_stage=_optional_string(payload, "stoppedAtStage"),
            interrupt_reason=frozen("interruptReason"),
            last_failed_stage=_optional_string(payload, "lastFailedStage"),
            retry_counts=_counter_tuple(payload.get("retryCounts"), field="retryCounts"),
            infrastructure_retry_counts=_counter_tuple(
                payload.get("infrastructureRetryCounts"),
                field="infrastructureRetryCounts",
            ),
            failed_objects=frozen_rows("failedObjects"),
            failed_issue_records=frozen_rows("failedIssueRecords"),
            baseline_packet_path=_optional_string(payload, "baselinePacketPath"),
            baseline_packet_summary=frozen("baselinePacketSummary"),
            workspace_cleanup_reports=frozen_rows("workspaceCleanupReports"),
            completion_gate_issues=frozen_rows("completionGateIssues"),
            quality=frozen("quality", {}),
            throughput=frozen("throughput", {}),
            controller=frozen("controller", {}),
            controller_yield=frozen("controllerYield"),
            controller_yield_recovery_actions=frozen_rows(
                "controllerYieldRecoveryActions"
            ),
            recovery_actions=frozen_rows("recoveryActions"),
            scheduler_recovery_actions=frozen_rows("schedulerRecoveryActions"),
            auto_research_recovery_actions=frozen_rows("autoResearchRecoveryActions"),
            active_agent_scheduler=frozen("activeAgentScheduler"),
            active_auto_research=frozen("activeAutoResearch"),
            agent_run_history=frozen_rows("agentRunHistory"),
            last_agent_run=frozen("lastAgentRun"),
            react_rewinds=frozen("reactRewinds", {}),
            managed_checkpoint_interruption=frozen("managedCheckpointInterruption"),
            managed_infra_recovery_cutoffs=frozen("managedInfraRecoveryCutoffs", {}),
            manual_repair_resumes=frozen_rows("manualRepairResumes"),
            produce_review_retry_history=frozen("produceReviewRetryHistory", []),
            last_author_finalize_count=non_negative_int("lastAuthorFinalizeCount"),
            last_object_queue_author_finalize_count=non_negative_int(
                "lastObjectQueueAuthorFinalizeCount"
            ),
            quarantine=frozen("quarantine", {}),
        )

    def open_transition(self) -> "ExecutionStateTransition":
        return ExecutionStateTransition(self)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "executionId": self.execution_id,
            "completed": list(self.completed),
            "status": self.status.value,
            "updatedAt": self.updated_at,
            "waitingCheckpoint": self.waiting_checkpoint,
            "owner": self.owner,
            "heartbeatAt": self.heartbeat_at,
            "startedAt": self.started_at,
            "nextAction": _thaw_json(self.next_action),
            "stoppedAtStage": self.stopped_at_stage,
            "interruptReason": _thaw_json(self.interrupt_reason),
            "lastFailedStage": self.last_failed_stage,
            "retryCounts": dict(self.retry_counts),
            "infrastructureRetryCounts": dict(self.infrastructure_retry_counts),
            "failedObjects": [_thaw_json(item) for item in self.failed_objects],
            "failedIssueRecords": [
                _thaw_json(item) for item in self.failed_issue_records
            ],
            "baselinePacketPath": self.baseline_packet_path,
            "baselinePacketSummary": _thaw_json(self.baseline_packet_summary),
            "workspaceCleanupReports": [
                _thaw_json(item) for item in self.workspace_cleanup_reports
            ],
            "completionGateIssues": [
                _thaw_json(item) for item in self.completion_gate_issues
            ],
            "quality": _thaw_json(self.quality),
            "throughput": _thaw_json(self.throughput),
            "controller": _thaw_json(self.controller),
            "controllerYield": _thaw_json(self.controller_yield),
            "controllerYieldRecoveryActions": [
                _thaw_json(item) for item in self.controller_yield_recovery_actions
            ],
            "recoveryActions": [_thaw_json(item) for item in self.recovery_actions],
            "schedulerRecoveryActions": [
                _thaw_json(item) for item in self.scheduler_recovery_actions
            ],
            "autoResearchRecoveryActions": [
                _thaw_json(item) for item in self.auto_research_recovery_actions
            ],
            "activeAgentScheduler": _thaw_json(self.active_agent_scheduler),
            "activeAutoResearch": _thaw_json(self.active_auto_research),
            "agentRunHistory": [_thaw_json(item) for item in self.agent_run_history],
            "lastAgentRun": _thaw_json(self.last_agent_run),
            "reactRewinds": _thaw_json(self.react_rewinds),
            "managedCheckpointInterruption": _thaw_json(
                self.managed_checkpoint_interruption
            ),
            "managedInfraRecoveryCutoffs": _thaw_json(
                self.managed_infra_recovery_cutoffs
            ),
            "manualRepairResumes": [
                _thaw_json(item) for item in self.manual_repair_resumes
            ],
            "produceReviewRetryHistory": _thaw_json(
                self.produce_review_retry_history
            ),
            "lastAuthorFinalizeCount": self.last_author_finalize_count,
            "lastObjectQueueAuthorFinalizeCount": (
                self.last_object_queue_author_finalize_count
            ),
            "quarantine": _thaw_json(self.quarantine),
        }


class ExecutionStateTransition:
    """Mutable transaction over one immutable :class:`ExecutionState`."""

    def __init__(self, snapshot: ExecutionState) -> None:
        payload = snapshot.to_dict()
        self.schema = snapshot.schema
        self.execution_id = snapshot.execution_id
        self.completed = list(snapshot.completed)
        self.status = snapshot.status
        self.updated_at = snapshot.updated_at
        self.waiting_checkpoint = snapshot.waiting_checkpoint
        self.owner = snapshot.owner
        self.heartbeat_at = snapshot.heartbeat_at
        self.started_at = snapshot.started_at
        self.next_action = payload["nextAction"]
        self.stopped_at_stage = snapshot.stopped_at_stage
        self.interrupt_reason = payload["interruptReason"]
        self.last_failed_stage = snapshot.last_failed_stage
        self.retry_counts = dict(snapshot.retry_counts)
        self.infrastructure_retry_counts = dict(snapshot.infrastructure_retry_counts)
        self.failed_objects = list(payload["failedObjects"])
        self.failed_issue_records = list(payload["failedIssueRecords"])
        self.baseline_packet_path = snapshot.baseline_packet_path
        self.baseline_packet_summary = payload["baselinePacketSummary"]
        self.workspace_cleanup_reports = list(payload["workspaceCleanupReports"])
        self.completion_gate_issues = list(payload["completionGateIssues"])
        self.quality = payload["quality"]
        self.throughput = payload["throughput"]
        self.controller = payload["controller"]
        self.controller_yield = payload["controllerYield"]
        self.controller_yield_recovery_actions = list(
            payload["controllerYieldRecoveryActions"]
        )
        self.recovery_actions = list(payload["recoveryActions"])
        self.scheduler_recovery_actions = list(payload["schedulerRecoveryActions"])
        self.auto_research_recovery_actions = list(
            payload["autoResearchRecoveryActions"]
        )
        self.active_agent_scheduler = payload["activeAgentScheduler"]
        self.active_auto_research = payload["activeAutoResearch"]
        self.agent_run_history = list(payload["agentRunHistory"])
        self.last_agent_run = payload["lastAgentRun"]
        self.react_rewinds = payload["reactRewinds"]
        self.managed_checkpoint_interruption = payload[
            "managedCheckpointInterruption"
        ]
        self.managed_infra_recovery_cutoffs = payload["managedInfraRecoveryCutoffs"]
        self.manual_repair_resumes = list(payload["manualRepairResumes"])
        self.produce_review_retry_history = payload["produceReviewRetryHistory"]
        self.last_author_finalize_count = snapshot.last_author_finalize_count
        self.last_object_queue_author_finalize_count = (
            snapshot.last_object_queue_author_finalize_count
        )
        self.quarantine = payload["quarantine"]

    def freeze(self) -> ExecutionState:
        if not isinstance(self.status, ExecutionStateStatus):
            raise TypeError("execution state status must be ExecutionStateStatus")
        return ExecutionState.from_mapping(self.to_dict())

    def replace_with(self, replacement: "ExecutionStateTransition") -> None:
        """Replace this transaction with a freshly loaded validated state."""
        if not isinstance(replacement, ExecutionStateTransition):
            raise TypeError("replacement must be an ExecutionStateTransition")
        if replacement.execution_id != self.execution_id:
            raise ValueError("replacement executionId must match current transition")
        if replacement.schema != self.schema:
            raise ValueError("replacement schema must match current transition")
        journal_identity = getattr(replacement, "_journal_identity", None)
        refreshed = replacement.freeze().open_transition()
        self.__dict__.clear()
        self.__dict__.update(refreshed.__dict__)
        if journal_identity is not None:
            self._journal_identity = journal_identity

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "executionId": self.execution_id,
            "completed": list(self.completed),
            "status": self.status.value,
            "updatedAt": self.updated_at,
            "waitingCheckpoint": self.waiting_checkpoint,
            "owner": self.owner,
            "heartbeatAt": self.heartbeat_at,
            "startedAt": self.started_at,
            "nextAction": self.next_action,
            "stoppedAtStage": self.stopped_at_stage,
            "interruptReason": self.interrupt_reason,
            "lastFailedStage": self.last_failed_stage,
            "retryCounts": dict(self.retry_counts),
            "infrastructureRetryCounts": dict(self.infrastructure_retry_counts),
            "failedObjects": list(self.failed_objects),
            "failedIssueRecords": list(self.failed_issue_records),
            "baselinePacketPath": self.baseline_packet_path,
            "baselinePacketSummary": self.baseline_packet_summary,
            "workspaceCleanupReports": list(self.workspace_cleanup_reports),
            "completionGateIssues": list(self.completion_gate_issues),
            "quality": self.quality,
            "throughput": self.throughput,
            "controller": self.controller,
            "controllerYield": self.controller_yield,
            "controllerYieldRecoveryActions": list(
                self.controller_yield_recovery_actions
            ),
            "recoveryActions": list(self.recovery_actions),
            "schedulerRecoveryActions": list(self.scheduler_recovery_actions),
            "autoResearchRecoveryActions": list(
                self.auto_research_recovery_actions
            ),
            "activeAgentScheduler": self.active_agent_scheduler,
            "activeAutoResearch": self.active_auto_research,
            "agentRunHistory": list(self.agent_run_history),
            "lastAgentRun": self.last_agent_run,
            "reactRewinds": self.react_rewinds,
            "managedCheckpointInterruption": self.managed_checkpoint_interruption,
            "managedInfraRecoveryCutoffs": self.managed_infra_recovery_cutoffs,
            "manualRepairResumes": list(self.manual_repair_resumes),
            "produceReviewRetryHistory": self.produce_review_retry_history,
            "lastAuthorFinalizeCount": self.last_author_finalize_count,
            "lastObjectQueueAuthorFinalizeCount": (
                self.last_object_queue_author_finalize_count
            ),
            "quarantine": self.quarantine,
        }
