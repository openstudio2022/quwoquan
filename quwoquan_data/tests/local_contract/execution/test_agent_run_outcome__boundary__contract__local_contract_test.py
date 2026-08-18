"""Managed semantic-agent outcomes are typed after the provider boundary."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from content.execution.agent.history import (
    ManagedAgentRunRecord,
    ManagedAgentScheduler,
    dedupe_managed_agent_runs,
)
from content.execution.agent.agent_runner import (
    _cursor_provider_rejection,
    _managed_agent_runner_for_provider_unjournaled,
    _prompt_cursor_agent,
)
from content.execution.agent import agent_runner
from content.execution.agent.outcome import AgentRunOutcome, ManagedAgentJobOutcome
from core.control_types import AgentFailureKind, AgentProvider, AgentRunStatus, ExecutionStage
from core.data_issue import DataIssueCode, DataRecoveryAction
from core.runtime_policy import active_runtime_policy


def test_agent_run_outcome__failure__reliability__local_contract_test() -> None:
    outcome = AgentRunOutcome.failed(
        AgentFailureKind.SUBPROCESS_TIMEOUT,
        provider=AgentProvider.CURSOR_SDK,
        message="agent subprocess exceeded its deadline",
        retryable=True,
    )

    assert outcome.status is AgentRunStatus.ERROR
    issue = outcome.issue(ref="entities/地点/景区/测试实体甲")
    assert issue is not None
    assert issue.code is DataIssueCode.AGENT_TIMEOUT
    assert issue.recovery is DataRecoveryAction.RETRY_AGENT


def test_agent_run_outcome__provider_rejection__reliability__local_contract_test() -> None:
    outcome = AgentRunOutcome.failed(
        AgentFailureKind.PROVIDER_REJECTED,
        provider=AgentProvider.CURSOR_SDK,
        message="provider account is not ready",
        started=True,
        error_code=AgentFailureKind.PROVIDER_REJECTED.value,
    )

    issue = outcome.issue(ref="entities/地点/景区/测试实体甲")
    assert issue is not None
    assert issue.code is DataIssueCode.AGENT_PROVIDER_REJECTED
    assert issue.recovery is DataRecoveryAction.STOP


def test_cursor_usage_limit__provider_rejection__reliability__local_contract_test() -> None:
    message = (
        "You've hit your usage limit. Set a Spend Limit to continue with Auto; "
        "your usage limits reset when your monthly cycle ends."
    )

    assert _cursor_provider_rejection(message)
    assert not _cursor_provider_rejection(
        "Bridge request failed: ConnectError: connection refused",
        code="internal",
    )


def test_cursor_prompt__preserves_terminal_status_message__contract__local_contract_test() -> None:
    class StatusMessage:
        type = "status"
        status = "ERROR"
        message = "provider account is not ready"

    class Event:
        sdk_message = StatusMessage()

    class Run:
        def events(self):
            return iter((Event(),))

        def wait(self):
            return object()

    class AgentInstance:
        def send(self, _prompt):
            return Run()

        def close(self):
            return None

    class AgentClass:
        @staticmethod
        def create(_options, *, client):  # noqa: ARG004
            return AgentInstance()

    result, message = _prompt_cursor_agent(
        AgentClass,
        "prompt",
        object(),
        client=object(),
    )

    assert result is not None
    assert message == "provider account is not ready"


def test_managed_provider_dispatch_invokes_task_without_shared_admission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selection = active_runtime_policy().explicit_semantic_selection(
        "cursor_auto"
    ).binding.selection
    context = SimpleNamespace(
        agent_provider=AgentProvider.CURSOR_SDK,
        semantic_role="author",
        model_selection=selection,
    )
    expected = AgentRunOutcome.failed(
        AgentFailureKind.PROVIDER_REJECTED,
        provider=AgentProvider.CURSOR_SDK,
        message="this invocation was rejected",
        started=True,
        error_code="provider_rejected",
    )
    calls: list[str] = []
    monkeypatch.setattr(
        agent_runner,
        "_default_managed_agent_runner",
        lambda _ctx, prompt: calls.append(prompt) or expected,
    )

    actual = _managed_agent_runner_for_provider_unjournaled(context, "one task")

    assert actual is expected
    assert calls == ["one task"]


def test_agent_run_outcome__wire_decode__contract__local_contract_test() -> None:
    encoded = AgentRunOutcome.finished(
        provider=AgentProvider.CODEX_SDK,
        run_id="run-1",
        result_text="completed",
        attempts=1,
    ).to_document()

    decoded = AgentRunOutcome.from_document(encoded)

    assert decoded.succeeded
    assert decoded.run_id == "run-1"


def test_agent_run_outcome__invocation_attempt_and_retry_after__contract__local_contract_test() -> None:
    outcome = AgentRunOutcome.failed(
        AgentFailureKind.PROVIDER_REJECTED,
        provider=AgentProvider.CODEX_SDK,
        message="rate limited",
        started=True,
        retryable=True,
        error_code="semantic_provider_rate_limited",
        retry_after_seconds=45,
    ).with_invocation_attempt(
        attempt_ref="data/tasks/execution/_shared/semantic_tasks/work/attempts/0001.json",
        attempt_digest="sha256:" + "a" * 64,
    )

    decoded = AgentRunOutcome.from_document(outcome.to_document())

    assert decoded.retry_after_seconds == 45
    assert decoded.invocation_attempt_ref.endswith("0001.json")
    assert decoded.invocation_attempt_digest == "sha256:" + "a" * 64
    issue = decoded.issue()
    assert issue is not None
    assert dict(issue.attributes)["retryAfterSeconds"] == "45"


def test_agent_run_outcome__invalid_error__contract__local_contract_test() -> None:
    with pytest.raises(ValueError, match="failureKind"):
        AgentRunOutcome.from_document(
            {
                "started": False,
                "status": "error",
                "agentProvider": AgentProvider.CODEX_SDK.value,
            },
        )


def test_agent_run_outcome__rejects_weak_boolean__contract__local_contract_test() -> None:
    wire = AgentRunOutcome.finished(
        provider=AgentProvider.CODEX_SDK,
        run_id="run-1",
    ).to_document()
    wire["retryable"] = "false"

    with pytest.raises(ValueError, match="retryable must be a boolean"):
        AgentRunOutcome.from_document(wire)


def test_managed_agent_job_outcome__gate__reliability__local_contract_test() -> None:
    completed = ManagedAgentJobOutcome(
        outcome=AgentRunOutcome.finished(
            provider=AgentProvider.CODEX_SDK,
            run_id="run-1",
        ),
        job_index=0,
        lane="homepage",
        ref="entities/地点/景区/测试实体甲",
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
            effective_worker_count=1,
            runtime="managed-local",
            prompt_count=1,
            provider=AgentProvider.CURSOR_SDK,
            started_at="2026-07-18T00:00:00Z",
            finished_at="2026-07-18T00:01:00Z",
            elapsed_seconds=60.0,
        ),
        refs=("posts/article/example",),
        started_count=1,
        finished_count=1,
        infrastructure_failures=0,
        successful_refs=("posts/article/example",),
        excluded_refs=(),
        shortfall_count=0,
        repair_issue_records=(),
        outcomes=(
            ManagedAgentJobOutcome(
                outcome=AgentRunOutcome.finished(
                    provider=AgentProvider.CURSOR_SDK,
                    run_id="run-1",
                ),
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
    with pytest.raises(ValueError, match="repairIssueRecords"):
        ManagedAgentRunRecord.from_document(
            {
                "stage": ExecutionStage.POST_AUTHOR.value,
                "outcomes": [],
                "terminatedSubprocessPids": [],
                "status": "completed",
            },
        )
