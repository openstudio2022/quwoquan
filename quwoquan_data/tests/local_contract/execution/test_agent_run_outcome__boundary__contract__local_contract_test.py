"""Managed Cursor outcomes are typed after the SDK/subprocess boundary."""
from __future__ import annotations

import pytest

from content.execution.agent.history import (
    ManagedAgentRunRecord,
    ManagedAgentScheduler,
    dedupe_managed_agent_runs,
)
from content.execution.agent.outcome import AgentRunOutcome, ManagedAgentJobOutcome
from core.control_types import AgentFailureKind, AgentProvider, AgentRunStatus, ExecutionStage
from core.data_issue import DataIssueCode, DataRecoveryAction


def test_agent_run_outcome__failure__reliability__local_contract_test() -> None:
    outcome = AgentRunOutcome.failed(
        AgentFailureKind.SUBPROCESS_TIMEOUT,
        message="agent subprocess exceeded its deadline",
        retryable=True,
    )

    assert outcome.status is AgentRunStatus.ERROR
    issue = outcome.issue(ref="entities/地点/景区/普陀山")
    assert issue is not None
    assert issue.code is DataIssueCode.AGENT_TIMEOUT
    assert issue.recovery is DataRecoveryAction.RETRY_AGENT


def test_agent_run_outcome__wire_decode__contract__local_contract_test() -> None:
    encoded = AgentRunOutcome.finished(
        run_id="run-1",
        result_text="completed",
        attempts=1,
    ).to_document()

    decoded = AgentRunOutcome.from_document(encoded)

    assert decoded.succeeded
    assert decoded.run_id == "run-1"


def test_agent_run_outcome__invalid_error__contract__local_contract_test() -> None:
    with pytest.raises(ValueError, match="failureKind"):
        AgentRunOutcome.from_document(
            {
                "started": False,
                "status": "error",
            },
        )


def test_agent_run_outcome__rejects_weak_boolean__contract__local_contract_test() -> None:
    wire = AgentRunOutcome.finished(run_id="run-1").to_document()
    wire["retryable"] = "false"

    with pytest.raises(ValueError, match="retryable must be a boolean"):
        AgentRunOutcome.from_document(wire)


def test_managed_agent_job_outcome__gate__reliability__local_contract_test() -> None:
    completed = ManagedAgentJobOutcome(
        outcome=AgentRunOutcome.finished(run_id="run-1"),
        job_index=0,
        lane="homepage",
        ref="entities/地点/景区/普陀山",
    )

    blocked = completed.with_gate_issues(("page.md remains placeholder",))

    assert not blocked.succeeded
    assert blocked.outcome.failure_kind is AgentFailureKind.CHECKPOINT_GATE
    assert blocked.to_document()["gateIssues"] == ["page.md remains placeholder"]


def test_managed_agent_run_record__wire_boundary__contract__local_contract_test() -> None:
    record = ManagedAgentRunRecord(
        stage=ExecutionStage.POST_AUTHOR,
        job_count=1,
        planned_job_count=1,
        scheduler=ManagedAgentScheduler(
            requested_max_workers=1,
            effective_worker_count=1,
            local_cursor_max_workers=1,
            runtime="managed-local",
            prompt_count=1,
            estimated_min_waves=1,
            lane_limits=(("article", 1),),
            provider=AgentProvider.CURSOR_SDK,
            started_at="2026-07-18T00:00:00Z",
            finished_at="2026-07-18T00:01:00Z",
            elapsed_seconds=60.0,
        ),
        refs=("posts/article/example",),
        started_count=1,
        finished_count=1,
        infrastructure_failures=0,
        outcomes=(
            ManagedAgentJobOutcome(
                outcome=AgentRunOutcome.finished(run_id="run-1"),
                job_index=0,
                lane="article",
                ref="posts/article/example",
            ),
        ),
        finished_at="2026-07-18T00:01:00Z",
    )

    decoded = ManagedAgentRunRecord.from_document(record.to_document())

    assert decoded.stage is ExecutionStage.POST_AUTHOR
    assert decoded.outcomes[0].outcome.run_id == "run-1"
    recovered = decoded.with_recovery(
        recovered_at="2026-07-18T00:02:00Z",
        recovery_reason="checkpoint passed after retry",
    )
    assert dedupe_managed_agent_runs((decoded, recovered)) == (recovered,)


def test_managed_agent_run_record__rejects_incomplete_wire__contract__local_contract_test() -> None:
    with pytest.raises(ValueError, match="jobCount"):
        ManagedAgentRunRecord.from_document(
            {
                "stage": ExecutionStage.POST_AUTHOR.value,
                "outcomes": [],
                "terminatedSubprocessPids": [],
                "status": "completed",
            },
        )
