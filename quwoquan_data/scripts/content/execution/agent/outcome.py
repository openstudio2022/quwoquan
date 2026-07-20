"""Typed boundary for managed Cursor-agent terminal outcomes.

The Cursor SDK and the isolated subprocess both expose untrusted, JSON-like
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


def _non_negative_float(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"agent outcome {field_name} must be a non-negative number")
    return float(value)


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
        AgentFailureKind.BUDGET_EXCEEDED: DataIssueCode.QUEUE_BUDGET_EXCEEDED,
        AgentFailureKind.SUBPROCESS_TIMEOUT: DataIssueCode.AGENT_TIMEOUT,
        AgentFailureKind.FUTURE_TIMEOUT: DataIssueCode.AGENT_TIMEOUT,
        AgentFailureKind.SUBPROCESS_OUTPUT_INVALID: DataIssueCode.AGENT_RESULT_INVALID,
        AgentFailureKind.NO_RESULT: DataIssueCode.AGENT_RESULT_INVALID,
        AgentFailureKind.SDK_UNAVAILABLE: DataIssueCode.AGENT_EXECUTION_FAILED,
        AgentFailureKind.BRIDGE_UNAVAILABLE: DataIssueCode.AGENT_EXECUTION_FAILED,
        AgentFailureKind.SDK_EXECUTION_FAILED: DataIssueCode.AGENT_EXECUTION_FAILED,
        AgentFailureKind.SUBPROCESS_EXITED: DataIssueCode.AGENT_EXECUTION_FAILED,
        AgentFailureKind.CHECKPOINT_GATE: DataIssueCode.AGENT_EXECUTION_FAILED,
    }[kind]


@dataclass(frozen=True, slots=True)
class AgentRunOutcome:
    """Terminal result of one managed-agent invocation."""

    started: bool
    status: AgentRunStatus
    provider: AgentProvider = AgentProvider.CURSOR_SDK
    failure_kind: AgentFailureKind | None = None
    message: str = ""
    retryable: bool = False
    auth_failure: bool = False
    error_code: str = ""
    request_id: str = ""
    attempts: int = 0
    warm_attempts: int = 0
    result_text: str = ""
    agent_id: str = ""
    run_id: str = ""
    duration_ms: int = 0
    used_tokens: int = 0
    cost_usd: float = 0.0
    retry_cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_known: bool = False
    cost_source: str = ""
    cost_issue: str = ""
    resolved_model_id: str = ""
    pricing_revision: str = ""
    usage_measurement_mode: str = ""
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
        if self.auth_failure != (self.failure_kind is AgentFailureKind.CREDENTIAL_INVALID):
            raise ValueError("agent outcome auth_failure must match credential failure kind")
        for field_name in (
            "message",
            "error_code",
            "request_id",
            "result_text",
            "agent_id",
            "run_id",
            "cost_source",
            "cost_issue",
            "resolved_model_id",
            "pricing_revision",
            "usage_measurement_mode",
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
            "used_tokens",
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
        ):
            _non_negative_int(getattr(self, field_name), field_name=field_name)
        _non_negative_float(self.cost_usd, field_name="cost_usd")
        _non_negative_float(self.retry_cost_usd, field_name="retry_cost_usd")
        if not isinstance(self.cost_known, bool):
            raise TypeError("agent outcome cost_known must be a boolean")
        if self.status is AgentRunStatus.ERROR and not self.message:
            raise ValueError("an error agent outcome requires a message")

    @property
    def succeeded(self) -> bool:
        return self.status is AgentRunStatus.FINISHED

    @classmethod
    def finished(
        cls,
        *,
        provider: AgentProvider = AgentProvider.CURSOR_SDK,
        result_text: str = "",
        agent_id: str = "",
        run_id: str = "",
        duration_ms: int = 0,
        used_tokens: int = 0,
        cost_usd: float = 0.0,
        retry_cost_usd: float = 0.0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        cost_known: bool = False,
        cost_source: str = "",
        cost_issue: str = "",
        resolved_model_id: str = "",
        pricing_revision: str = "",
        usage_measurement_mode: str = "",
        completion_mode: str = "",
        stdout_tail: str = "",
        stderr_tail: str = "",
        attempts: int = 0,
        warm_attempts: int = 0,
        request_id: str = "",
    ) -> "AgentRunOutcome":
        return cls(
            started=True,
            status=AgentRunStatus.FINISHED,
            provider=provider,
            result_text=result_text,
            agent_id=agent_id,
            run_id=run_id,
            duration_ms=duration_ms,
            used_tokens=used_tokens,
            cost_usd=cost_usd,
            retry_cost_usd=retry_cost_usd,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            cost_known=cost_known,
            cost_source=cost_source,
            cost_issue=cost_issue,
            resolved_model_id=resolved_model_id,
            pricing_revision=pricing_revision,
            usage_measurement_mode=usage_measurement_mode,
            completion_mode=completion_mode,
            stdout_tail=stdout_tail,
            stderr_tail=stderr_tail,
            attempts=attempts,
            warm_attempts=warm_attempts,
            request_id=request_id,
        )

    @classmethod
    def failed(
        cls,
        kind: AgentFailureKind,
        *,
        message: str,
        provider: AgentProvider = AgentProvider.CURSOR_SDK,
        started: bool = False,
        retryable: bool = False,
        error_code: str = "",
        request_id: str = "",
        attempts: int = 0,
        warm_attempts: int = 0,
        duration_ms: int = 0,
        used_tokens: int = 0,
        cost_usd: float = 0.0,
        retry_cost_usd: float = 0.0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        cost_known: bool = False,
        cost_source: str = "",
        cost_issue: str = "",
        resolved_model_id: str = "",
        pricing_revision: str = "",
        usage_measurement_mode: str = "",
        stdout_tail: str = "",
        stderr_tail: str = "",
    ) -> "AgentRunOutcome":
        return cls(
            started=started,
            status=AgentRunStatus.ERROR,
            provider=provider,
            failure_kind=kind,
            message=message.strip(),
            retryable=retryable,
            auth_failure=kind is AgentFailureKind.CREDENTIAL_INVALID,
            error_code=error_code.strip(),
            request_id=request_id.strip(),
            attempts=attempts,
            warm_attempts=warm_attempts,
            duration_ms=duration_ms,
            used_tokens=used_tokens,
            cost_usd=cost_usd,
            retry_cost_usd=retry_cost_usd,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            cost_known=cost_known,
            cost_source=cost_source,
            cost_issue=cost_issue,
            resolved_model_id=resolved_model_id,
            pricing_revision=pricing_revision,
            usage_measurement_mode=usage_measurement_mode,
            stdout_tail=stdout_tail,
            stderr_tail=stderr_tail,
        )

    def with_checkpoint_gate_failure(self, *, message: str) -> "AgentRunOutcome":
        if not self.succeeded:
            raise ValueError("only a finished agent outcome can fail a checkpoint gate")
        return AgentRunOutcome.failed(
            AgentFailureKind.CHECKPOINT_GATE,
            message=message,
            provider=self.provider,
            started=True,
            retryable=True,
            error_code=self.error_code,
            request_id=self.request_id,
            attempts=self.attempts,
            warm_attempts=self.warm_attempts,
            duration_ms=self.duration_ms,
            used_tokens=self.used_tokens,
            cost_usd=self.cost_usd,
            retry_cost_usd=self.retry_cost_usd,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cache_read_tokens=self.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens,
            cost_known=self.cost_known,
            cost_source=self.cost_source,
            cost_issue=self.cost_issue,
            resolved_model_id=self.resolved_model_id,
            pricing_revision=self.pricing_revision,
            usage_measurement_mode=self.usage_measurement_mode,
            stdout_tail=self.stdout_tail,
            stderr_tail=self.stderr_tail,
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
            "requestId": self.request_id or None,
            "attempts": self.attempts,
            "warmAttempts": self.warm_attempts,
            "result": self.result_text,
            "agentId": self.agent_id or None,
            "runId": self.run_id or None,
            "durationMs": self.duration_ms,
            "usedTokens": self.used_tokens,
            "inputTokens": self.input_tokens,
            "outputTokens": self.output_tokens,
            "cacheReadTokens": self.cache_read_tokens,
            "cacheWriteTokens": self.cache_write_tokens,
            "costUsd": self.cost_usd if self.cost_known else None,
            "retryCostUsd": self.retry_cost_usd if self.cost_known else None,
            "costKnown": self.cost_known,
            "costSource": self.cost_source or None,
            "costIssue": self.cost_issue or None,
            "resolvedModelId": self.resolved_model_id or None,
            "pricingRevision": self.pricing_revision or None,
            "usageMeasurementMode": self.usage_measurement_mode or None,
            "completionMode": self.completion_mode or None,
            "stdoutTail": self.stdout_tail or None,
            "stderrTail": self.stderr_tail or None,
        }

    @classmethod
    def from_document(cls, value: object, *, label: str = "agent outcome") -> "AgentRunOutcome":
        try:
            doc = JsonObject.from_value(value, label=label)
            status = AgentRunStatus(doc.string("status"))
            provider = AgentProvider(_optional_text(doc.value("agentProvider"), field_name="agentProvider") or AgentProvider.CURSOR_SDK.value)
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
            used_tokens = _non_negative_int(
                _value_or_default(doc.value("usedTokens"), 0),
                field_name="usedTokens",
            )
            input_tokens = _non_negative_int(
                _value_or_default(doc.value("inputTokens"), 0),
                field_name="inputTokens",
            )
            output_tokens = _non_negative_int(
                _value_or_default(doc.value("outputTokens"), 0),
                field_name="outputTokens",
            )
            cache_read_tokens = _non_negative_int(
                _value_or_default(doc.value("cacheReadTokens"), 0),
                field_name="cacheReadTokens",
            )
            cache_write_tokens = _non_negative_int(
                _value_or_default(doc.value("cacheWriteTokens"), 0),
                field_name="cacheWriteTokens",
            )
            cost_usd = _non_negative_float(
                _value_or_default(doc.value("costUsd"), 0.0),
                field_name="costUsd",
            )
            retry_cost_usd = _non_negative_float(
                _value_or_default(doc.value("retryCostUsd"), 0.0),
                field_name="retryCostUsd",
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
            request_id=_optional_text(doc.value("requestId"), field_name="requestId"),
            attempts=attempts,
            warm_attempts=warm_attempts,
            result_text=_optional_text(doc.value("result"), field_name="result"),
            agent_id=_optional_text(doc.value("agentId"), field_name="agentId"),
            run_id=_optional_text(doc.value("runId"), field_name="runId"),
            duration_ms=duration_ms,
            used_tokens=used_tokens,
            cost_usd=cost_usd,
            retry_cost_usd=retry_cost_usd,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            cost_known=_boolean_or_default(
                doc.value("costKnown"),
                field_name="costKnown",
            ),
            cost_source=_optional_text(
                doc.value("costSource"),
                field_name="costSource",
            ),
            cost_issue=_optional_text(
                doc.value("costIssue"),
                field_name="costIssue",
            ),
            resolved_model_id=_optional_text(
                doc.value("resolvedModelId"),
                field_name="resolvedModelId",
            ),
            pricing_revision=_optional_text(
                doc.value("pricingRevision"),
                field_name="pricingRevision",
            ),
            usage_measurement_mode=_optional_text(doc.value("usageMeasurementMode"), field_name="usageMeasurementMode"),
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
