"""Failure triage and per-object isolation.

Two failures that look alike at a stage boundary need opposite handling: an
unwritable transport or an exhausted provider quota says nothing about the
object and must be retried, while content judged unfit will be rejected again
and must be recorded and skipped. These cases lock the mapping, the escalation
of anything unrecognized, and the property that one object's failure cannot
take the batch down with it.
"""
from __future__ import annotations

import pytest

from content.execution.controller.failure_isolation import (
    FailureClass,
    IsolatedObjectFailure,
    classify_agent_failure,
    classify_issue,
    classify_issues,
    infrastructure_backoff_seconds,
    infrastructure_retry_budget,
    run_isolated_batch,
    stage_is_infrastructure_retryable,
)
from core.control_types import AgentFailureKind
from core.data_issue import (
    DataIssueCode,
    DataIssueError,
    DataIssueStage,
    data_issue,
)


def _issue(code: DataIssueCode, *, ref: str = "obj-a"):
    return data_issue(
        code,
        stage=DataIssueStage.POST_AUTHOR,
        ref=ref,
        message=f"{code.value} at {ref}",
    )


@pytest.mark.parametrize(
    "code",
    [
        DataIssueCode.ENVIRONMENT_NOT_READY,
        DataIssueCode.NETWORK_UNREACHABLE,
        DataIssueCode.AGENT_TIMEOUT,
        DataIssueCode.AGENT_PROVIDER_REJECTED,
        DataIssueCode.QUEUE_TIMEOUT,
        DataIssueCode.REMOTE_HOST_EXECUTOR_UNAVAILABLE,
    ],
)
def test_causes_outside_the_object_are_infrastructure(code: DataIssueCode) -> None:
    assert classify_issue(_issue(code)) is FailureClass.INFRASTRUCTURE


@pytest.mark.parametrize(
    "code",
    [
        DataIssueCode.QUALITY_FAILED,
        DataIssueCode.AGENT_RESULT_INVALID,
        DataIssueCode.CONTENT_CLASSIFICATION_REJECTED,
        DataIssueCode.SOURCE_MISSING,
        DataIssueCode.MEDIA_CAPTION_INVALID,
    ],
)
def test_verdicts_about_this_object_are_content_unfit(code: DataIssueCode) -> None:
    assert classify_issue(_issue(code)) is FailureClass.CONTENT_UNFIT


@pytest.mark.parametrize(
    "code",
    [
        DataIssueCode.CONTRACT_INVALID,
        DataIssueCode.SOURCE_QUALIFICATION_EXHAUSTED,
        DataIssueCode.POOL_DELIVERY_UNAVAILABLE,
        DataIssueCode.AGENT_SCALE_CALIBRATION_REQUIRED,
    ],
)
def test_contract_and_envelope_decisions_are_governance_blocks(
    code: DataIssueCode,
) -> None:
    assert classify_issue(_issue(code)) is FailureClass.GOVERNANCE_BLOCK


def test_an_unmapped_code_is_never_assumed_retryable() -> None:
    # Silently retrying an undiagnosed failure is how a batch burns its whole
    # budget on one defect.
    assert classify_issue(_issue(DataIssueCode.INTERNAL_UNEXPECTED)) is (
        FailureClass.UNCLASSIFIED
    )


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (AgentFailureKind.BRIDGE_UNAVAILABLE, FailureClass.INFRASTRUCTURE),
        (AgentFailureKind.CREDENTIAL_INVALID, FailureClass.INFRASTRUCTURE),
        (AgentFailureKind.PROVIDER_REJECTED, FailureClass.INFRASTRUCTURE),
        (AgentFailureKind.SUBPROCESS_TIMEOUT, FailureClass.INFRASTRUCTURE),
        (AgentFailureKind.SUBPROCESS_OUTPUT_INVALID, FailureClass.CONTENT_UNFIT),
        (AgentFailureKind.CHECKPOINT_GATE, FailureClass.CONTENT_UNFIT),
    ],
)
def test_provider_failure_kinds_map_to_the_same_two_classes(
    kind: AgentFailureKind, expected: FailureClass
) -> None:
    assert classify_agent_failure(kind) is expected


def test_the_strictest_class_in_a_mixed_stage_wins() -> None:
    mixed = [
        _issue(DataIssueCode.NETWORK_UNREACHABLE),
        _issue(DataIssueCode.CONTRACT_INVALID),
    ]

    assert classify_issues(mixed) is FailureClass.GOVERNANCE_BLOCK
    assert stage_is_infrastructure_retryable(mixed) is False


def test_a_purely_infrastructural_stage_is_retryable() -> None:
    assert stage_is_infrastructure_retryable(
        [
            _issue(DataIssueCode.ENVIRONMENT_NOT_READY),
            _issue(DataIssueCode.NETWORK_UNREACHABLE, ref="obj-b"),
        ]
    )


def test_a_stage_with_no_issues_is_not_silently_retryable() -> None:
    assert stage_is_infrastructure_retryable([]) is False
    with pytest.raises(ValueError):
        classify_issues([])


def test_untyped_input_is_refused_rather_than_defaulted() -> None:
    with pytest.raises(TypeError):
        classify_issue("DATA.NETWORK.UNREACHABLE")
    with pytest.raises(TypeError):
        classify_agent_failure("bridge_unavailable")


def test_backoff_grows_and_is_bounded_by_the_governed_cap() -> None:
    delays = [infrastructure_backoff_seconds(attempt) for attempt in range(1, 9)]

    assert delays == sorted(delays)
    assert delays[0] < delays[-1]
    assert len(set(delays[-2:])) == 1
    assert infrastructure_retry_budget() >= 1


def test_a_zero_or_negative_backoff_attempt_is_a_failure() -> None:
    for attempt in (0, -1):
        with pytest.raises(ValueError):
            infrastructure_backoff_seconds(attempt)


def test_one_object_failure_does_not_stop_the_batch() -> None:
    def runner(object_ref: str) -> str:
        if object_ref == "unfit":
            raise DataIssueError((_issue(DataIssueCode.QUALITY_FAILED, ref=object_ref),))
        if object_ref == "flaky":
            raise DataIssueError(
                (_issue(DataIssueCode.NETWORK_UNREACHABLE, ref=object_ref),)
            )
        return object_ref.upper()

    batch = run_isolated_batch(["a", "unfit", "flaky", "b"], runner)

    assert batch.succeeded_refs == ("a", "b")
    assert batch.failed_refs == ("unfit", "flaky")
    assert batch.report()["failedByClass"] == {
        "content_unfit": 1,
        "infrastructure": 1,
    }
    assert len(batch.failed_issue_records) == 2


def test_a_governance_block_escalates_instead_of_being_absorbed() -> None:
    def runner(object_ref: str) -> str:
        if object_ref == "bad-contract":
            raise DataIssueError(
                (_issue(DataIssueCode.CONTRACT_INVALID, ref=object_ref),)
            )
        return object_ref

    with pytest.raises(DataIssueError):
        run_isolated_batch(["a", "bad-contract", "b"], runner)


def test_an_unclassified_failure_escalates_instead_of_being_absorbed() -> None:
    def runner(object_ref: str) -> str:
        raise DataIssueError((_issue(DataIssueCode.INTERNAL_UNEXPECTED, ref=object_ref),))

    with pytest.raises(DataIssueError):
        run_isolated_batch(["a"], runner)


def test_a_non_issue_exception_is_never_swallowed_as_an_object_failure() -> None:
    def runner(object_ref: str) -> str:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_isolated_batch(["a"], runner)


def test_a_blank_object_ref_is_a_failure_not_an_isolated_object() -> None:
    with pytest.raises(ValueError):
        run_isolated_batch(["  "], lambda ref: ref)


def test_an_isolated_failure_must_carry_its_evidence() -> None:
    with pytest.raises(ValueError):
        IsolatedObjectFailure(
            object_ref="obj-a",
            failure_class=FailureClass.CONTENT_UNFIT,
            issues=(),
        )
