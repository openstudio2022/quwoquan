# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-004
"""Per-job failure isolation for a partially successful semantic checkpoint.

`REQ-001` requires every semantic task that actually started to write its own
create-once typed terminal result, and forbids queued items, not-yet-started
items, capacity samples and workspace samples from being merged into a task
success or failure.  `REQ-006` adds that each frozen work unit must get an
independent typed terminal state and that a single unit failing or timing out
terminates only that unit.  `GWT-004` states that campaign only aggregates those
per-task results, and `GWT-008` that one entity failing does not stop the rest
from reaching their own terminal state.
"""
from __future__ import annotations

import pytest
from content.execution.agent.outcome import (
    AgentRunOutcome,
    ManagedAgentJobOutcome,
    coerce_agent_outcome,
)
from core.control_types import AgentFailureKind, AgentProvider, AgentRunStatus
from core.data_issue import DataIssueCode, DataRecoveryAction

PROVIDER = AgentProvider.CURSOR_SDK


def _finished(*, ref: str, index: int) -> ManagedAgentJobOutcome:
    return ManagedAgentJobOutcome(
        outcome=AgentRunOutcome.finished(
            provider=PROVIDER,
            result_text=f"drafted {ref}",
            run_id=f"run-{index}",
            duration_ms=1200,
        ),
        job_index=index,
        lane="article",
        ref=ref,
    )


def _timed_out(*, ref: str, index: int) -> ManagedAgentJobOutcome:
    return ManagedAgentJobOutcome(
        outcome=AgentRunOutcome.failed(
            AgentFailureKind.SUBPROCESS_TIMEOUT,
            message=f"{ref} exceeded its single-object wall clock",
            provider=PROVIDER,
            started=True,
            retryable=True,
            duration_ms=660_000,
        ),
        job_index=index,
        lane="article",
        ref=ref,
    )


def _never_started(*, ref: str, index: int) -> ManagedAgentJobOutcome:
    return ManagedAgentJobOutcome(
        outcome=AgentRunOutcome.failed(
            AgentFailureKind.BRIDGE_UNAVAILABLE,
            message=f"{ref} never reached the provider bridge",
            provider=PROVIDER,
            started=False,
            retryable=True,
        ),
        job_index=index,
        lane="article",
        ref=ref,
    )


def test_a_partial_batch_keeps_one_typed_terminal_state_per_work_unit() -> None:
    """One failing unit terminates only itself; siblings keep their results."""

    batch = (
        _finished(ref="posts/a1", index=0),
        _timed_out(ref="posts/a2", index=1),
        _finished(ref="posts/a3", index=2),
    )

    assert [job.succeeded for job in batch] == [True, False, True]
    assert len({job.job_index for job in batch}) == 3
    assert len({job.ref for job in batch}) == 3
    for job in batch:
        assert job.outcome.status in {AgentRunStatus.FINISHED, AgentRunStatus.ERROR}


def test_the_failing_unit_does_not_rewrite_a_sibling_result() -> None:
    """A partial checkpoint is not a batch-level failure."""

    ok = _finished(ref="posts/a1", index=0)
    failed = _timed_out(ref="posts/a2", index=1)

    assert ok.outcome.succeeded is True
    assert ok.outcome.failure_kind is None
    assert failed.outcome.succeeded is False
    assert failed.outcome.failure_kind is AgentFailureKind.SUBPROCESS_TIMEOUT
    assert ok.outcome.result_text
    assert failed.outcome.result_text == ""


def test_each_started_unit_carries_its_own_operator_readable_issue() -> None:
    """`REQ-006` lets the operator decide from the receipt, not from logs."""

    timed_out = _timed_out(ref="posts/a2", index=1)
    issue = timed_out.outcome.issue(ref=timed_out.ref)

    assert issue is not None
    assert issue.code is DataIssueCode.AGENT_TIMEOUT
    assert issue.recovery is DataRecoveryAction.RETRY_AGENT
    assert issue.ref == "posts/a2"
    assert dict(issue.attributes)["failureKind"] == (
        AgentFailureKind.SUBPROCESS_TIMEOUT.value
    )


def test_a_successful_unit_produces_no_issue_record() -> None:
    """A qualified object must not carry a failure record."""

    ok = _finished(ref="posts/a1", index=0)

    assert ok.outcome.issue(ref=ok.ref) is None
    assert ok.to_document()["issueRecords"] == []


def test_a_non_retryable_failure_stops_instead_of_retrying() -> None:
    """The typed recovery action is closed and derived from the failure."""

    rejected = AgentRunOutcome.failed(
        AgentFailureKind.PROVIDER_REJECTED,
        message="provider rejected the request",
        provider=PROVIDER,
        started=True,
        retryable=False,
    )
    issue = rejected.issue(ref="posts/a4")

    assert issue is not None
    assert issue.code is DataIssueCode.AGENT_PROVIDER_REJECTED
    assert issue.recovery is DataRecoveryAction.STOP


def test_a_never_started_unit_is_still_a_typed_failure_not_a_success() -> None:
    """A queued or unstarted item may not be merged into a task success."""

    unstarted = _never_started(ref="posts/a5", index=3)

    assert unstarted.outcome.started is False
    assert unstarted.outcome.succeeded is False
    assert unstarted.outcome.failure_kind is AgentFailureKind.BRIDGE_UNAVAILABLE
    assert unstarted.outcome.message


def test_started_and_succeeded_stay_two_separate_facts() -> None:
    """`started` describes dispatch; `succeeded` describes the terminal result."""

    started_and_failed = _timed_out(ref="posts/a2", index=1)

    assert started_and_failed.outcome.started is True
    assert started_and_failed.outcome.succeeded is False


def test_a_finished_outcome_may_not_carry_a_failure_kind() -> None:
    """Success and failure may not be expressed at the same time."""

    with pytest.raises(ValueError, match="must not have a failure kind"):
        AgentRunOutcome(
            started=True,
            status=AgentRunStatus.FINISHED,
            provider=PROVIDER,
            failure_kind=AgentFailureKind.NO_RESULT,
        )


def test_an_error_outcome_requires_a_failure_kind() -> None:
    """A failure may not degrade into an untyped error."""

    with pytest.raises(ValueError, match="requires a failure kind"):
        AgentRunOutcome(
            started=True,
            status=AgentRunStatus.ERROR,
            provider=PROVIDER,
            message="something went wrong",
        )


def test_an_error_outcome_requires_a_message() -> None:
    """A typed failure must remain readable, not collapse to an empty string."""

    with pytest.raises(ValueError, match="requires a message"):
        AgentRunOutcome(
            started=True,
            status=AgentRunStatus.ERROR,
            provider=PROVIDER,
            failure_kind=AgentFailureKind.NO_RESULT,
            message="",
        )


def test_a_finished_outcome_must_have_started() -> None:
    """A task result only exists for a task that actually started."""

    with pytest.raises(ValueError, match="must have started"):
        AgentRunOutcome(
            started=False,
            status=AgentRunStatus.FINISHED,
            provider=PROVIDER,
        )


def test_auth_failure_may_not_be_claimed_without_a_credential_failure() -> None:
    """Failure classes stay disjoint; one may not stand in for another."""

    with pytest.raises(ValueError, match="auth_failure must match"):
        AgentRunOutcome(
            started=True,
            status=AgentRunStatus.ERROR,
            provider=PROVIDER,
            failure_kind=AgentFailureKind.SUBPROCESS_TIMEOUT,
            message="timed out",
            auth_failure=True,
        )


def test_a_finished_agent_whose_lane_gate_fails_becomes_a_typed_failure() -> None:
    """A capacity or gate observation may not be reported as a task success."""

    gated = _finished(ref="posts/a1", index=0).with_gate_issues(
        ("article body is below the frozen floor",)
    )

    assert gated.succeeded is False
    assert gated.outcome.failure_kind is AgentFailureKind.CHECKPOINT_GATE
    assert gated.outcome.started is True
    assert gated.outcome.retryable is True
    assert gated.gate_issues == ("article body is below the frozen floor",)


def test_empty_gate_issues_leave_a_successful_unit_untouched() -> None:
    """An absent gate issue is not a failure signal."""

    ok = _finished(ref="posts/a1", index=0)

    assert ok.with_gate_issues(()) is ok
    assert ok.with_gate_issues(("   ",)) is ok


def test_a_gate_failure_only_applies_to_a_finished_unit() -> None:
    """A gate verdict may not overwrite an already-typed failure."""

    failed = _timed_out(ref="posts/a2", index=1)

    with pytest.raises(ValueError, match="only a finished agent outcome"):
        failed.outcome.with_checkpoint_gate_failure(message="lane gate still fails")


def test_every_job_outcome_requires_its_own_lane_identity() -> None:
    """A per-unit terminal state must be attributable to one lane."""

    with pytest.raises(ValueError, match="lane is required"):
        ManagedAgentJobOutcome(
            outcome=AgentRunOutcome.finished(provider=PROVIDER),
            job_index=0,
            lane="  ",
        )


def test_a_negative_job_index_fails_closed() -> None:
    """Job identity is the frozen work-unit index and never negative."""

    with pytest.raises(ValueError, match="job index must be non-negative"):
        ManagedAgentJobOutcome(
            outcome=AgentRunOutcome.finished(provider=PROVIDER),
            job_index=-1,
            lane="article",
        )


def test_a_status_bearing_dictionary_is_not_accepted_as_a_result() -> None:
    """Control flow receives a typed outcome, never a raw status mapping."""

    with pytest.raises(TypeError, match="status must be AgentRunStatus"):
        AgentRunOutcome(
            started=True,
            status="finished",  # type: ignore[arg-type]
            provider=PROVIDER,
        )


def test_each_typed_terminal_state_round_trips_for_create_once_replay() -> None:
    """The create-once record must replay to the same typed terminal state."""

    for job in (
        _finished(ref="posts/a1", index=0),
        _timed_out(ref="posts/a2", index=1),
        _never_started(ref="posts/a5", index=3),
    ):
        replayed = ManagedAgentJobOutcome.from_document(job.to_document())
        assert replayed.outcome == job.outcome
        assert replayed.job_index == job.job_index
        assert replayed.lane == job.lane
        assert replayed.ref == job.ref


def test_an_error_document_without_a_failure_kind_fails_closed() -> None:
    """A persisted failure may not be read back as an untyped error."""

    document = _timed_out(ref="posts/a2", index=1).to_document()
    document["failureKind"] = None

    with pytest.raises(ValueError, match="error requires failureKind"):
        ManagedAgentJobOutcome.from_document(document)


def test_the_runner_boundary_admits_a_typed_outcome_unchanged() -> None:
    """An already-typed outcome is not re-decoded at the runner boundary."""

    outcome = AgentRunOutcome.finished(provider=PROVIDER, run_id="run-0")

    assert coerce_agent_outcome(outcome, label="managed run") is outcome


def test_the_runner_boundary_rejects_an_untyped_value() -> None:
    """An untrusted value must be admitted exactly once or fail closed."""

    with pytest.raises(ValueError):
        coerce_agent_outcome("finished", label="managed run")


def test_a_capacity_receipt_needs_both_ref_and_digest() -> None:
    """A capacity sample is diagnostic evidence and must be fully bound."""

    outcome = AgentRunOutcome.finished(provider=PROVIDER)

    with pytest.raises(ValueError, match="ref and digest are required"):
        outcome.with_capacity_receipt(
            receipt_ref="", receipt_digest="sha256:" + "a" * 64
        )
    with pytest.raises(ValueError, match="ref and digest are required"):
        outcome.with_capacity_receipt(receipt_ref="receipt.json", receipt_digest="  ")


def test_a_capacity_sample_does_not_change_the_task_terminal_state() -> None:
    """Capacity observations may not alter a task success or failure."""

    outcome = AgentRunOutcome.finished(provider=PROVIDER, run_id="run-0")
    bound = outcome.with_capacity_receipt(
        receipt_ref="control_plane/receipt.json",
        receipt_digest="sha256:" + "1" * 64,
    )

    assert bound.succeeded is outcome.succeeded
    assert bound.status is outcome.status
    assert bound.failure_kind is outcome.failure_kind
    assert bound.capacity_receipt_ref == "control_plane/receipt.json"
