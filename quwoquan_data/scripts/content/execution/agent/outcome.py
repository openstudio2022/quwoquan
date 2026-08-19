"""Typed boundary for managed semantic-agent terminal outcomes.

Provider adapters and the isolated subprocess both expose untrusted, JSON-like
values.  They are admitted here exactly once; execution control flow receives
an immutable :class:`AgentRunOutcome`, never a status-bearing dictionary.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

from core.codec import JsonObject, JsonObjectDecodeError
from core.control_types import AgentFailureKind, AgentProvider, AgentRunStatus
from core.data_issue import (
    DataIssue,
    DataIssueCode,
    DataIssueLane,
    DataIssueStage,
    DataRecoveryAction,
    data_issue,
)


def _text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"agent outcome {field_name} must be a string")
    return value.strip()


def _optional_text(value: object, *, field_name: str) -> str:
    if value is None:
        return ""
    return _text(value, field_name=field_name)


def _non_negative_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"agent outcome {field_name} must be a non-negative integer")
    return value


def _value_or_default(value: object, default: object) -> object:
    return default if value is None else value


def _boolean_or_default(value: object, *, field_name: str, default: bool = False) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError(f"agent outcome {field_name} must be a boolean")
    return value


def _failure_code(kind: AgentFailureKind) -> DataIssueCode:
    return {
        AgentFailureKind.CREDENTIAL_INVALID: DataIssueCode.AGENT_CREDENTIAL_INVALID,
        AgentFailureKind.AUTHENTICATION_REJECTED: DataIssueCode.AGENT_CREDENTIAL_INVALID,
        AgentFailureKind.PROVIDER_REJECTED: DataIssueCode.AGENT_PROVIDER_REJECTED,
        AgentFailureKind.SUBPROCESS_TIMEOUT: DataIssueCode.AGENT_TIMEOUT,
        AgentFailureKind.FUTURE_TIMEOUT: DataIssueCode.AGENT_TIMEOUT,
        AgentFailureKind.SUBPROCESS_OUTPUT_INVALID: DataIssueCode.AGENT_RESULT_INVALID,
        AgentFailureKind.NO_RESULT: DataIssueCode.AGENT_RESULT_INVALID,
        AgentFailureKind.SDK_UNAVAILABLE: DataIssueCode.AGENT_EXECUTION_FAILED,
        AgentFailureKind.BRIDGE_UNAVAILABLE: DataIssueCode.AGENT_EXECUTION_FAILED,
        AgentFailureKind.SDK_EXECUTION_FAILED: DataIssueCode.AGENT_EXECUTION_FAILED,
        AgentFailureKind.SUBPROCESS_EXITED: DataIssueCode.AGENT_EXECUTION_FAILED,
        AgentFailureKind.CHECKPOINT_GATE: DataIssueCode.AGENT_EXECUTION_FAILED,
        AgentFailureKind.CAPACITY_UNPROVEN: DataIssueCode.AGENT_EXECUTION_FAILED,
    }[kind]


@dataclass(frozen=True, slots=True)
class AgentRunOutcome:
    """Terminal result of one managed-agent invocation."""

    started: bool
    status: AgentRunStatus
    provider: AgentProvider
    failure_kind: AgentFailureKind | None = None
    message: str = ""
    retryable: bool = False
    auth_failure: bool = False
    error_code: str = ""
    retry_after_seconds: int = 0
    request_id: str = ""
    attempts: int = 0
    warm_attempts: int = 0
    result_text: str = ""
    agent_id: str = ""
    run_id: str = ""
    capacity_receipt_ref: str = ""
    capacity_receipt_digest: str = ""
    invocation_attempt_ref: str = ""
    invocation_attempt_digest: str = ""
    duration_ms: int = 0
    completion_mode: str = ""
    stdout_tail: str = ""
    stderr_tail: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.status, AgentRunStatus):
            raise TypeError("agent outcome status must be AgentRunStatus")
        if not isinstance(self.provider, AgentProvider):
            raise TypeError("agent outcome provider must be AgentProvider")
        if self.failure_kind is not None and not isinstance(
            self.failure_kind,
            AgentFailureKind,
        ):
            raise TypeError("agent outcome failure_kind must be AgentFailureKind")
        if self.status is AgentRunStatus.FINISHED:
            if not self.started:
                raise ValueError("a finished agent outcome must have started")
            if self.failure_kind is not None:
                raise ValueError("a finished agent outcome must not have a failure kind")
        elif self.failure_kind is None:
            raise ValueError("an error agent outcome requires a failure kind")
        auth_kinds = {
            AgentFailureKind.CREDENTIAL_INVALID,
            AgentFailureKind.AUTHENTICATION_REJECTED,
        }
        if self.auth_failure != (self.failure_kind in auth_kinds):
            raise ValueError("agent outcome auth_failure must match credential failure kind")
        for field_name in (
            "message",
            "error_code",
            "request_id",
            "result_text",
            "agent_id",
            "run_id",
            "capacity_receipt_ref",
            "capacity_receipt_digest",
            "invocation_attempt_ref",
            "invocation_attempt_digest",
            "completion_mode",
            "stdout_tail",
            "stderr_tail",
        ):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"agent outcome {field_name} must be a string")
        for field_name in (
            "attempts",
            "warm_attempts",
            "duration_ms",
            "retry_after_seconds",
        ):
            _non_negative_int(getattr(self, field_name), field_name=field_name)
        if self.status is AgentRunStatus.ERROR and not self.message:
            raise ValueError("an error agent outcome requires a message")

    @property
    def succeeded(self) -> bool:
        return self.status is AgentRunStatus.FINISHED

    @classmethod
    def finished(
        cls,
        *,
        provider: AgentProvider,
        result_text: str = "",
        agent_id: str = "",
        run_id: str = "",
        duration_ms: int = 0,
        completion_mode: str = "",
        stdout_tail: str = "",
        stderr_tail: str = "",
        attempts: int = 0,
        warm_attempts: int = 0,
        request_id: str = "",
        retry_after_seconds: int = 0,
        capacity_receipt_ref: str = "",
        capacity_receipt_digest: str = "",
    ) -> "AgentRunOutcome":
        return cls(
            started=True,
            status=AgentRunStatus.FINISHED,
            provider=provider,
            result_text=result_text,
            agent_id=agent_id,
            run_id=run_id,
            duration_ms=duration_ms,
            completion_mode=completion_mode,
            stdout_tail=stdout_tail,
            stderr_tail=stderr_tail,
            attempts=attempts,
            warm_attempts=warm_attempts,
            request_id=request_id,
            retry_after_seconds=retry_after_seconds,
            capacity_receipt_ref=capacity_receipt_ref,
            capacity_receipt_digest=capacity_receipt_digest,
        )

    @classmethod
    def failed(
        cls,
        kind: AgentFailureKind,
        *,
        message: str,
        provider: AgentProvider,
        started: bool = False,
        retryable: bool = False,
        error_code: str = "",
        retry_after_seconds: int = 0,
        request_id: str = "",
        attempts: int = 0,
        warm_attempts: int = 0,
        duration_ms: int = 0,
        stdout_tail: str = "",
        stderr_tail: str = "",
        capacity_receipt_ref: str = "",
        capacity_receipt_digest: str = "",
    ) -> "AgentRunOutcome":
        return cls(
            started=started,
            status=AgentRunStatus.ERROR,
            provider=provider,
            failure_kind=kind,
            message=message.strip(),
            retryable=retryable,
            auth_failure=kind in {
                AgentFailureKind.CREDENTIAL_INVALID,
                AgentFailureKind.AUTHENTICATION_REJECTED,
            },
            error_code=error_code.strip(),
            retry_after_seconds=retry_after_seconds,
            request_id=request_id.strip(),
            attempts=attempts,
            warm_attempts=warm_attempts,
            duration_ms=duration_ms,
            stdout_tail=stdout_tail,
            stderr_tail=stderr_tail,
            capacity_receipt_ref=capacity_receipt_ref,
            capacity_receipt_digest=capacity_receipt_digest,
        )

    def with_capacity_receipt(
        self,
        *,
        receipt_ref: str,
        receipt_digest: str,
    ) -> "AgentRunOutcome":
        if not str(receipt_ref or "").strip() or not str(receipt_digest or "").strip():
            raise ValueError("capacity receipt ref and digest are required")
        return replace(
            self,
            capacity_receipt_ref=str(receipt_ref).strip(),
            capacity_receipt_digest=str(receipt_digest).strip(),
        )

    def with_invocation_attempt(
        self,
        *,
        attempt_ref: str,
        attempt_digest: str,
    ) -> "AgentRunOutcome":
        """Bind the journaled attempt record this outcome was written into.

        The retry scope re-reads the attempt file by this digest to decide which
        author refs exhausted their attempts, so an outcome that claims an
        attempt without naming it would leave that decision unanchored.
        """
        if not str(attempt_ref or "").strip() or not str(attempt_digest or "").strip():
            raise ValueError("invocation attempt ref and digest are required")
        return replace(
            self,
            invocation_attempt_ref=str(attempt_ref).strip(),
            invocation_attempt_digest=str(attempt_digest).strip(),
        )

    def with_checkpoint_gate_failure(self, *, message: str) -> "AgentRunOutcome":
        if not self.succeeded:
            raise ValueError("only a finished agent outcome can fail a checkpoint gate")
        gated = AgentRunOutcome.failed(
            AgentFailureKind.CHECKPOINT_GATE,
            message=message,
            provider=self.provider,
            started=True,
            retryable=True,
            error_code=self.error_code,
            retry_after_seconds=self.retry_after_seconds,
            request_id=self.request_id,
            attempts=self.attempts,
            warm_attempts=self.warm_attempts,
            duration_ms=self.duration_ms,
            stdout_tail=self.stdout_tail,
            stderr_tail=self.stderr_tail,
            capacity_receipt_ref=self.capacity_receipt_ref,
            capacity_receipt_digest=self.capacity_receipt_digest,
        )
        if not self.invocation_attempt_ref:
            return gated
        return gated.with_invocation_attempt(
            attempt_ref=self.invocation_attempt_ref,
            attempt_digest=self.invocation_attempt_digest,
        )

    def issue(self, *, ref: str = "", lane: DataIssueLane = DataIssueLane.ALL) -> DataIssue | None:
        if self.succeeded or self.failure_kind is None:
            return None
        return data_issue(
            _failure_code(self.failure_kind),
            stage=DataIssueStage.AGENT_COMPOSE,
            ref=ref,
            lane=lane,
            recovery=(
                DataRecoveryAction.RETRY_AGENT
                if self.retryable
                else DataRecoveryAction.STOP
            ),
            message=self.message,
            attributes={
                "failureKind": self.failure_kind.value,
                "errorCode": self.error_code,
                "retryAfterSeconds": str(self.retry_after_seconds),
                "requestId": self.request_id,
            },
        )

    def to_document(self) -> dict[str, object]:
        return {
            "started": self.started,
            "status": self.status.value,
            "agentProvider": self.provider.value,
            "failureKind": self.failure_kind.value if self.failure_kind else None,
            "error": self.message or None,
            "retryable": self.retryable,
            "authFailure": self.auth_failure,
            "errorCode": self.error_code or None,
            "retryAfterSeconds": self.retry_after_seconds,
            "requestId": self.request_id or None,
            "attempts": self.attempts,
            "warmAttempts": self.warm_attempts,
            "result": self.result_text,
            "agentId": self.agent_id or None,
            "runId": self.run_id or None,
            "capacityReceiptRef": self.capacity_receipt_ref or None,
            "capacityReceiptDigest": self.capacity_receipt_digest or None,
            "invocationAttemptRef": self.invocation_attempt_ref or None,
            "invocationAttemptDigest": self.invocation_attempt_digest or None,
            "durationMs": self.duration_ms,
            "completionMode": self.completion_mode or None,
            "stdoutTail": self.stdout_tail or None,
            "stderrTail": self.stderr_tail or None,
        }

    @classmethod
    def from_document(cls, value: object, *, label: str = "agent outcome") -> "AgentRunOutcome":
        try:
            doc = JsonObject.from_value(value, label=label)
            status = AgentRunStatus(doc.string("status"))
            provider = AgentProvider(
                _text(doc.value("agentProvider"), field_name="agentProvider")
            )
            started = doc.boolean("started")
            failure_raw = _optional_text(doc.value("failureKind"), field_name="failureKind")
            failure_kind = AgentFailureKind(failure_raw) if failure_raw else None
            attempts = _non_negative_int(
                _value_or_default(doc.value("attempts"), 0),
                field_name="attempts",
            )
            warm_attempts = _non_negative_int(
                _value_or_default(doc.value("warmAttempts"), 0),
                field_name="warmAttempts",
            )
            duration_ms = _non_negative_int(
                _value_or_default(doc.value("durationMs"), 0),
                field_name="durationMs",
            )
            retry_after_seconds = _non_negative_int(
                _value_or_default(doc.value("retryAfterSeconds"), 0),
                field_name="retryAfterSeconds",
            )
        except (JsonObjectDecodeError, ValueError) as exc:
            raise ValueError(f"{label} is invalid: {exc}") from exc
        message = _optional_text(doc.value("error"), field_name="error")
        if status is AgentRunStatus.ERROR and failure_kind is None:
            raise ValueError(f"{label} error requires failureKind")
        return cls(
            started=started,
            status=status,
            provider=provider,
            failure_kind=failure_kind,
            message=message,
            retryable=_boolean_or_default(doc.value("retryable"), field_name="retryable"),
            auth_failure=_boolean_or_default(doc.value("authFailure"), field_name="authFailure"),
            error_code=_optional_text(doc.value("errorCode"), field_name="errorCode"),
            retry_after_seconds=retry_after_seconds,
            request_id=_optional_text(doc.value("requestId"), field_name="requestId"),
            attempts=attempts,
            warm_attempts=warm_attempts,
            result_text=_optional_text(doc.value("result"), field_name="result"),
            agent_id=_optional_text(doc.value("agentId"), field_name="agentId"),
            run_id=_optional_text(doc.value("runId"), field_name="runId"),
            capacity_receipt_ref=_optional_text(
                doc.value("capacityReceiptRef"),
                field_name="capacityReceiptRef",
            ),
            capacity_receipt_digest=_optional_text(
                doc.value("capacityReceiptDigest"),
                field_name="capacityReceiptDigest",
            ),
            invocation_attempt_ref=_optional_text(
                doc.value("invocationAttemptRef"),
                field_name="invocationAttemptRef",
            ),
            invocation_attempt_digest=_optional_text(
                doc.value("invocationAttemptDigest"),
                field_name="invocationAttemptDigest",
            ),
            duration_ms=duration_ms,
            completion_mode=_optional_text(doc.value("completionMode"), field_name="completionMode"),
            stdout_tail=_optional_text(doc.value("stdoutTail"), field_name="stdoutTail"),
            stderr_tail=_optional_text(doc.value("stderrTail"), field_name="stderrTail"),
        )


@dataclass(frozen=True, slots=True)
class ManagedAgentJobOutcome:
    """One typed checkpoint outcome plus its scheduler-owned metadata."""

    outcome: AgentRunOutcome
    job_index: int
    lane: str
    ref: str = ""
    timing: tuple[tuple[str, object], ...] = ()
    gate_issues: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, AgentRunOutcome):
            raise TypeError("managed agent job outcome must hold AgentRunOutcome")
        if self.job_index < 0:
            raise ValueError("managed agent job index must be non-negative")
        if not self.lane.strip():
            raise ValueError("managed agent job lane is required")

    @property
    def succeeded(self) -> bool:
        return self.outcome.succeeded

    def with_gate_issues(self, issues: tuple[str, ...]) -> "ManagedAgentJobOutcome":
        cleaned = tuple(str(item).strip() for item in issues if str(item).strip())
        if not cleaned:
            return self
        return replace(
            self,
            outcome=self.outcome.with_checkpoint_gate_failure(
                message="agent finished but checkpoint lane gate still fails: " + "; ".join(cleaned[:8]),
            ),
            gate_issues=cleaned[:20],
        )

    def to_document(self) -> dict[str, object]:
        return {
            **self.outcome.to_document(),
            "jobIndex": self.job_index,
            "lane": self.lane,
            "ref": self.ref or None,
            "timing": {key: value for key, value in self.timing},
            "gateIssues": list(self.gate_issues),
            "issueRecords": [self.outcome.issue(ref=self.ref).as_dict()]
            if self.outcome.issue(ref=self.ref) is not None
            else [],
        }

    @classmethod
    def from_document(
        cls,
        value: object,
        *,
        label: str = "managed agent job outcome",
    ) -> "ManagedAgentJobOutcome":
        try:
            doc = JsonObject.from_value(value, label=label)
            timing_document = doc.value("timing")
            if timing_document is None:
                timing: tuple[tuple[str, object], ...] = ()
            else:
                timing_object = JsonObject.from_value(
                    timing_document,
                    label=f"{label}.timing",
                )
                timing = tuple(sorted(timing_object.to_document().items()))
            raw_gate_issues = doc.value("gateIssues")
            if raw_gate_issues is None:
                gate_issues: tuple[str, ...] = ()
            elif isinstance(raw_gate_issues, list) and all(
                isinstance(item, str) for item in raw_gate_issues
            ):
                gate_issues = tuple(item.strip() for item in raw_gate_issues if item.strip())
            else:
                raise ValueError("gateIssues must be a string array")
            return cls(
                outcome=AgentRunOutcome.from_document(doc.to_document(), label=label),
                job_index=_non_negative_int(doc.value("jobIndex"), field_name="jobIndex"),
                lane=doc.string("lane").strip(),
                ref=_optional_text(doc.value("ref"), field_name="ref"),
                timing=timing,
                gate_issues=gate_issues,
            )
        except (JsonObjectDecodeError, ValueError) as exc:
            raise ValueError(f"{label} is invalid: {exc}") from exc


def coerce_agent_outcome(value: object, *, label: str) -> AgentRunOutcome:
    """Admit a test double or subprocess wire value at the runner boundary."""
    if isinstance(value, AgentRunOutcome):
        return value
    return AgentRunOutcome.from_document(value, label=label)


__all__ = ["AgentRunOutcome", "ManagedAgentJobOutcome", "coerce_agent_outcome"]
