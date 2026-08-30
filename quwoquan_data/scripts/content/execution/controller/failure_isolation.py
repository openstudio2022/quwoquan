"""Per-object failure isolation and infrastructure/content triage.

Two failures that look alike at a stage boundary need opposite handling. An
unwritable Mongo/Redis transport, an exhausted provider quota or a network
timeout says nothing about the object; retrying the same object after a backoff
is the correct response and failing the whole batch destroys work that was
already done. Content judged unfit says everything about the object; retrying it
re-spends provider quota on a candidate that will be rejected again, so it must
be recorded as a failed object and the batch must move to the next one.

Getting the triage wrong in either direction is expensive, so classification is
an explicit closed mapping. An unrecognized cause is never assumed retryable:
it is escalated, because silently retrying an unknown failure is how a whole
batch burns its budget on a defect nobody has diagnosed.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Generic, TypeVar

from core.control_types import AgentFailureKind
from core.data_issue import DataIssue, DataIssueCode, DataIssueError


class FailureClass(StrEnum):
    """How one failure must be handled."""

    INFRASTRUCTURE = "infrastructure"
    CONTENT_UNFIT = "content_unfit"
    GOVERNANCE_BLOCK = "governance_block"
    UNCLASSIFIED = "unclassified"


# Causes outside the authored object: the object is untouched, so a retry after
# backoff can still succeed with the identical input.
_INFRASTRUCTURE_CODES = frozenset(
    {
        DataIssueCode.NETWORK_UNREACHABLE,
        DataIssueCode.ENVIRONMENT_NOT_READY,
        DataIssueCode.AGENT_TIMEOUT,
        DataIssueCode.AGENT_REVIEW_UNAVAILABLE,
        DataIssueCode.AGENT_CREDENTIAL_INVALID,
        DataIssueCode.AGENT_PROVIDER_REJECTED,
        DataIssueCode.QUEUE_TIMEOUT,
        DataIssueCode.QUEUE_STARTUP_FAILED,
        DataIssueCode.QUEUE_EXECUTION_FAILED,
        DataIssueCode.REMOTE_HOST_EXECUTOR_UNAVAILABLE,
        DataIssueCode.MEDIA_FETCH_FAILED,
    }
)

# Verdicts about this object's content or sources: the same input will be
# rejected again, so the object is abandoned and the batch continues.
_CONTENT_CODES = frozenset(
    {
        DataIssueCode.QUALITY_FAILED,
        DataIssueCode.AGENT_RESULT_INVALID,
        DataIssueCode.AGENT_REVIEW_INVALID,
        DataIssueCode.CONTENT_CLASSIFICATION_REJECTED,
        DataIssueCode.SOURCE_MISSING,
        DataIssueCode.SOURCE_UNREADABLE,
        DataIssueCode.SOURCE_CONTENT_INCOMPLETE,
        DataIssueCode.SOURCE_ENTITY_MISMATCH,
        DataIssueCode.SOURCE_PAGE_TYPE_INVALID,
        DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING,
        DataIssueCode.SOURCE_RETAINED_SHORTFALL,
        DataIssueCode.SOURCE_CATEGORY_SHORTFALL,
        DataIssueCode.MEDIA_CAPTION_INVALID,
        DataIssueCode.MEDIA_COVER_CONFLICT,
        DataIssueCode.MEDIA_DOWNLOAD_INCOMPLETE,
        DataIssueCode.MEDIA_ENUMERATION_INCOMPLETE,
        DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
        DataIssueCode.MEDIA_RIGHTS_UNAVAILABLE,
    }
)

# Contract, governance and supply-envelope decisions: neither a retry nor an
# object-level abandon is correct; the execution must stop and be inspected.
_GOVERNANCE_CODES = frozenset(
    {
        DataIssueCode.CONTRACT_INVALID,
        DataIssueCode.QUEUE_GOVERNANCE_INVALID,
        DataIssueCode.QUEUE_RESULT_ENVELOPE_INVALID,
        DataIssueCode.SOURCE_PLAN_INVALID,
        DataIssueCode.SOURCE_QUALIFICATION_EXHAUSTED,
        DataIssueCode.POOL_DELIVERY_UNAVAILABLE,
        DataIssueCode.AGENT_SCALE_CALIBRATION_REQUIRED,
    }
)

_INFRASTRUCTURE_AGENT_KINDS = frozenset(
    {
        AgentFailureKind.SDK_UNAVAILABLE,
        AgentFailureKind.BRIDGE_UNAVAILABLE,
        AgentFailureKind.CREDENTIAL_INVALID,
        AgentFailureKind.AUTHENTICATION_REJECTED,
        AgentFailureKind.PROVIDER_REJECTED,
        AgentFailureKind.SUBPROCESS_TIMEOUT,
        AgentFailureKind.FUTURE_TIMEOUT,
        AgentFailureKind.SUBPROCESS_EXITED,
        AgentFailureKind.NO_RESULT,
    }
)

_CONTENT_AGENT_KINDS = frozenset(
    {
        AgentFailureKind.SUBPROCESS_OUTPUT_INVALID,
        AgentFailureKind.CHECKPOINT_GATE,
    }
)


def classify_issue(issue: DataIssue) -> FailureClass:
    """Classify one typed data issue into its handling class."""

    if not isinstance(issue, DataIssue):
        raise TypeError("classify_issue requires a DataIssue")
    if issue.code in _INFRASTRUCTURE_CODES:
        return FailureClass.INFRASTRUCTURE
    if issue.code in _CONTENT_CODES:
        return FailureClass.CONTENT_UNFIT
    if issue.code in _GOVERNANCE_CODES:
        return FailureClass.GOVERNANCE_BLOCK
    return FailureClass.UNCLASSIFIED


def classify_agent_failure(kind: AgentFailureKind) -> FailureClass:
    """Classify one semantic-provider failure kind into its handling class."""

    if not isinstance(kind, AgentFailureKind):
        raise TypeError("classify_agent_failure requires an AgentFailureKind")
    if kind in _INFRASTRUCTURE_AGENT_KINDS:
        return FailureClass.INFRASTRUCTURE
    if kind in _CONTENT_AGENT_KINDS:
        return FailureClass.CONTENT_UNFIT
    return FailureClass.UNCLASSIFIED


def classify_issues(issues: Sequence[DataIssue]) -> FailureClass:
    """Classify a stage's issue set; the strictest class present wins.

    A stage that mixes a transport fault with a governance block must not be
    retried as if only the transport had failed.
    """

    classes = {classify_issue(issue) for issue in issues}
    if not classes:
        raise ValueError("classify_issues requires at least one issue")
    for candidate in (
        FailureClass.UNCLASSIFIED,
        FailureClass.GOVERNANCE_BLOCK,
        FailureClass.CONTENT_UNFIT,
    ):
        if candidate in classes:
            return candidate
    return FailureClass.INFRASTRUCTURE


def stage_is_infrastructure_retryable(issues: Sequence[DataIssue]) -> bool:
    """Whether every issue in this stage failure is an infrastructure fault."""

    return bool(issues) and classify_issues(issues) is FailureClass.INFRASTRUCTURE


def infrastructure_backoff_seconds(attempt: int) -> int:
    """Exponential backoff bounded by the runtime policy queue backoff cap."""

    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise ValueError("infrastructure backoff attempt must be >= 1")
    from core.runtime_policy import active_runtime_policy

    policy = active_runtime_policy()
    base = policy.queue_backoff_base_seconds
    cap = policy.queue_backoff_cap_seconds
    return min(cap, base * (2 ** (attempt - 1)))


def infrastructure_retry_budget() -> int:
    """Retry attempts admitted for one stage's infrastructure faults."""

    from core.runtime_policy import active_runtime_policy

    return active_runtime_policy().queue_max_attempts


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class IsolatedObjectFailure:
    """One abandoned object plus the evidence that abandoned it."""

    object_ref: str
    failure_class: FailureClass
    issues: tuple[DataIssue, ...]

    def __post_init__(self) -> None:
        if not self.object_ref.strip():
            raise ValueError("isolated failure requires an objectRef")
        if not self.issues:
            raise ValueError("isolated failure requires at least one issue")


@dataclass(slots=True)
class IsolatedBatch(Generic[T]):
    """Outcome of running one batch with per-object failure isolation."""

    succeeded: list[tuple[str, T]] = field(default_factory=list)
    failed: list[IsolatedObjectFailure] = field(default_factory=list)

    @property
    def succeeded_refs(self) -> tuple[str, ...]:
        return tuple(ref for ref, _value in self.succeeded)

    @property
    def failed_refs(self) -> tuple[str, ...]:
        return tuple(row.object_ref for row in self.failed)

    @property
    def failed_issue_records(self) -> list[dict[str, Any]]:
        return [issue.as_dict() for row in self.failed for issue in row.issues]

    def report(self) -> dict[str, Any]:
        by_class: dict[str, int] = {}
        for row in self.failed:
            by_class[row.failure_class.value] = (
                by_class.get(row.failure_class.value, 0) + 1
            )
        return {
            "succeededCount": len(self.succeeded),
            "failedCount": len(self.failed),
            "failedByClass": dict(sorted(by_class.items())),
            "failedRefs": list(self.failed_refs),
        }


def run_isolated_batch(
    object_refs: Iterable[str],
    runner: Callable[[str], T],
    *,
    escalating_classes: frozenset[FailureClass] = frozenset(
        {FailureClass.GOVERNANCE_BLOCK, FailureClass.UNCLASSIFIED}
    ),
) -> IsolatedBatch[T]:
    """Run ``runner`` per object so one object's failure cannot stop the batch.

    Content and infrastructure failures are isolated to their object. Governance
    blocks and unclassified failures re-raise: they are statements about the
    execution rather than about one object, and swallowing them would let a
    contract defect quietly consume the whole batch.
    """

    batch: IsolatedBatch[T] = IsolatedBatch()
    for raw_ref in object_refs:
        object_ref = str(raw_ref).strip()
        if not object_ref:
            raise ValueError("isolated batch objectRefs must be non-empty")
        try:
            batch.succeeded.append((object_ref, runner(object_ref)))
        except DataIssueError as exc:
            failure_class = classify_issues(exc.issues)
            if failure_class in escalating_classes:
                raise
            batch.failed.append(
                IsolatedObjectFailure(
                    object_ref=object_ref,
                    failure_class=failure_class,
                    issues=tuple(exc.issues),
                )
            )
    return batch


__all__ = [
    "FailureClass",
    "IsolatedBatch",
    "IsolatedObjectFailure",
    "classify_agent_failure",
    "classify_issue",
    "classify_issues",
    "infrastructure_backoff_seconds",
    "infrastructure_retry_budget",
    "run_isolated_batch",
    "stage_is_infrastructure_retryable",
]
