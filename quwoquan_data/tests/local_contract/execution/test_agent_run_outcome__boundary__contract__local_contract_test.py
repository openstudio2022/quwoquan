"""Managed semantic-agent outcomes are typed after the provider boundary."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from content.execution.agent.history import (
    ManagedAgentRunRecord,
    ManagedAgentScheduler,
    build_managed_agent_run_record,
    dedupe_managed_agent_runs,
)
from content.execution.agent.agent_runner import (
    _cursor_provider_rejection,
    _managed_agent_runner_for_provider_unjournaled,
    _prompt_cursor_agent,
)
from content.execution.agent import agent_runner
from content.execution.agent.outcome import AgentRunOutcome, ManagedAgentJobOutcome
from core.control_types import (
    AgentFailureKind,
    AgentProvider,
    AgentRunStatus,
    ExecutionStage,
    ManagedAgentCheckpointStatus,
)
from core.data_issue import DataIssueCode, DataRecoveryAction
from core.runtime_policy import active_runtime_policy
from core.schema import assert_valid


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


@pytest.mark.parametrize("failure_kind", tuple(AgentFailureKind))
def test_agent_failure_kind__always_maps_to_typed_issue__contract__local_contract_test(
    failure_kind: AgentFailureKind,
) -> None:
    outcome = AgentRunOutcome.failed(
        failure_kind,
        provider=AgentProvider.CURSOR_SDK,
        message=f"{failure_kind.value} terminal failure",
    )

    issue = outcome.issue(ref="posts/article/example")

    assert issue is not None
    assert issue.ref == "posts/article/example"


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


def _managed_scheduler(prompt_count: int = 1) -> ManagedAgentScheduler:
    return ManagedAgentScheduler(
        requested_max_workers=1,
        effective_worker_count=prompt_count,
        local_cursor_max_workers=1,
        runtime="local",
        prompt_count=prompt_count,
        estimated_min_waves=1,
        lane_limits=(("article", 1),),
        provider=AgentProvider.CURSOR_SDK,
        started_at="2026-07-18T00:00:00Z",
        finished_at="2026-07-18T00:01:00Z",
        elapsed_seconds=60.0,
    )


def _execution_state_with_run(record: ManagedAgentRunRecord) -> dict[str, object]:
    return {
        "schema": "quwoquan.content.execution_state",
        "executionId": "20260718--travel-article-workload--china--pilot-001",
        "completed": [],
        "status": "repairing",
        "updatedAt": "2026-07-18T00:01:00Z",
        "agentRunHistory": [record.to_document()],
        "lastAgentRun": record.to_document(),
    }


def test_managed_agent_run_record__wire_boundary__contract__local_contract_test() -> None:
    record = build_managed_agent_run_record(
        stage=ExecutionStage.POST_AUTHOR,
        planned_job_count=1,
        scheduler=_managed_scheduler(),
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
    assert_valid(
        _execution_state_with_run(decoded),
        "execution",
        "execution_state",
    )

    assert decoded.stage is ExecutionStage.POST_AUTHOR
    assert decoded.scheduler.requested_max_workers == 1
    assert decoded.successful_refs == ("posts/article/example",)
    assert decoded.excluded_refs == ()
    assert decoded.shortfall_count == 0
    assert decoded.status is ManagedAgentCheckpointStatus.COMPLETED
    assert decoded.outcomes[0].outcome.run_id == "run-1"
    recovered = decoded.with_recovery(
        recovered_at="2026-07-18T00:02:00Z",
        recovery_reason="checkpoint passed after retry",
    )
    assert dedupe_managed_agent_runs((decoded, recovered)) == (recovered,)


def test_managed_agent_run_record__derives_partial_exclusion_and_issue__contract__local_contract_test() -> None:
    outcomes = (
        ManagedAgentJobOutcome(
            outcome=AgentRunOutcome.finished(provider=AgentProvider.CURSOR_SDK),
            job_index=0,
            lane="article",
            ref="posts/article/succeeded",
        ),
        ManagedAgentJobOutcome(
            outcome=AgentRunOutcome.failed(
                AgentFailureKind.CHECKPOINT_GATE,
                provider=AgentProvider.CURSOR_SDK,
                message="article review gate failed",
                started=True,
                retryable=True,
            ),
            job_index=1,
            lane="article",
            ref="posts/article/excluded",
        ),
    )

    record = build_managed_agent_run_record(
        stage=ExecutionStage.POST_AUTHOR,
        planned_job_count=2,
        scheduler=_managed_scheduler(prompt_count=2),
        outcomes=outcomes,
        finished_at="2026-07-18T00:01:00Z",
    )

    assert record.status is ManagedAgentCheckpointStatus.PARTIAL
    assert record.successful_refs == ("posts/article/succeeded",)
    assert record.excluded_refs == ("posts/article/excluded",)
    assert record.shortfall_count == 1
    assert record.repair_issue_records[0]["ref"] == "posts/article/excluded"
    assert_valid(
        _execution_state_with_run(record),
        "execution",
        "execution_state",
    )


def test_managed_checkpoint_producer_persists_schema_valid_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from content.execution.agent import agent_checkpoint, checkpoint_prompts
    from content.execution.agent import managed_checkpoint
    from core.control_types import RuntimeEnvironment

    state = SimpleNamespace(agent_run_history=[], last_agent_run=None)
    monkeypatch.setattr(
        checkpoint_prompts,
        "_checkpoint_prompts",
        lambda _ctx, _stage: ("[AGENT_LANE:article]\n对象: 测试文章\n",),
    )
    monkeypatch.setattr(
        agent_checkpoint,
        "_managed_checkpoint_job_issues",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        agent_checkpoint,
        "_checkpoint_is_done",
        lambda *_args, **_kwargs: (True, []),
    )
    monkeypatch.setattr(managed_checkpoint, "load_execution_state", lambda _execution_id: state)
    monkeypatch.setattr(managed_checkpoint, "save_execution_state", lambda _state: None)
    context = SimpleNamespace(
        execution_id="20260718--travel-article-workload--china--pilot-001",
        max_workers=1,
        runtime=RuntimeEnvironment.LOCAL,
        agent_provider=AgentProvider.CURSOR_SDK,
        agent_runner=lambda _prompt: AgentRunOutcome.finished(
            provider=AgentProvider.CURSOR_SDK,
            run_id="run-producer-1",
        ),
    )

    assert managed_checkpoint._run_managed_checkpoint(context, "content_plan")
    persisted = ManagedAgentRunRecord.from_document(state.last_agent_run)
    assert persisted.status is ManagedAgentCheckpointStatus.COMPLETED
    assert persisted.scheduler.requested_max_workers == 1
    assert_valid(
        _execution_state_with_run(persisted),
        "execution",
        "execution_state",
    )


def test_managed_checkpoint_producer_freezes_failed_object_exclusion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from content.execution.agent import agent_checkpoint, checkpoint_exclusion
    from content.execution.agent import checkpoint_prompts, managed_checkpoint
    from content.execution.controller import homepage_author_finalization
    from core.control_types import RuntimeEnvironment

    state = SimpleNamespace(agent_run_history=[], last_agent_run=None)
    captured: list[tuple[ExecutionStage, str]] = []
    monkeypatch.setattr(
        checkpoint_prompts,
        "_checkpoint_prompts",
        lambda _ctx, _stage: ("[AGENT_LANE:homepage]\n对象: 测试主页\n",),
    )
    monkeypatch.setattr(
        agent_checkpoint,
        "_managed_checkpoint_job_issues",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        homepage_author_finalization,
        "_finalize_managed_homepage_outputs",
        lambda _ctx, _prompts, outcomes: tuple(outcomes),
    )
    monkeypatch.setattr(
        managed_checkpoint,
        "_managed_checkpoint_ref",
        lambda _ctx, _stage, _prompt: "/entity/地点/景区/测试主页",
    )
    monkeypatch.setattr(managed_checkpoint, "load_execution_state", lambda _execution_id: state)
    monkeypatch.setattr(managed_checkpoint, "save_execution_state", lambda _state: None)
    monkeypatch.setattr(
        checkpoint_exclusion,
        "write_semantic_checkpoint_exclusion",
        lambda _execution_id, *, stage, job_outcome, recorded_at: captured.append(
            (stage, job_outcome.ref)
        ),
    )
    context = SimpleNamespace(
        execution_id="20260718--travel-homepage-workload--china--pilot-001",
        max_workers=1,
        runtime=RuntimeEnvironment.LOCAL,
        agent_provider=AgentProvider.CURSOR_SDK,
        agent_runner=lambda _prompt: AgentRunOutcome.failed(
            AgentFailureKind.CHECKPOINT_GATE,
            provider=AgentProvider.CURSOR_SDK,
            message="homepage review gate failed",
            started=True,
            retryable=True,
        ),
    )

    assert not managed_checkpoint._run_managed_checkpoint(context, "build_homepage")
    persisted = ManagedAgentRunRecord.from_document(state.last_agent_run)
    assert persisted.status is ManagedAgentCheckpointStatus.BLOCKED
    assert persisted.excluded_refs == ("/entity/地点/景区/测试主页",)
    assert persisted.shortfall_count == 1
    assert persisted.repair_issue_records[0]["ref"] == "/entity/地点/景区/测试主页"
    assert captured == [
        (ExecutionStage.BUILD_HOMEPAGE, "/entity/地点/景区/测试主页")
    ]


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
