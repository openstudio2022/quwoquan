from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from content.execution.agent import agent_runner
from content.execution.agent import semantic_task_journal as journal
from content.execution.agent.outcome import AgentRunOutcome
from core.control_types import AgentFailureKind, AgentProvider
from core.runtime_policy import (
    DEFAULT_RUNTIME_PROFILE_ID,
    active_runtime_policy,
    runtime_profile_digest,
)
from core.source_digest import content_source_revision
from support.semantic_preflight_fixture import ready_semantic_preflight


def _execution_id(carrier: str, sequence: int = 1) -> str:
    return f"20260811--travel-{carrier}-m100--china--scale-{sequence:03d}"


def _context(
    carrier: str,
    *,
    role: str = "author",
    max_attempts: int | None = None,
) -> SimpleNamespace:
    selection = active_runtime_policy().explicit_semantic_selection("cursor_auto")
    return SimpleNamespace(
        execution_id=_execution_id(carrier),
        semantic_role=role,
        agent_provider=AgentProvider.CURSOR_SDK,
        model_selection=selection.binding.selection,
        semantic_max_attempts=max_attempts,
    )


@pytest.fixture
def journal_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    output_root = tmp_path / "output"
    _receipt_path, preflight_binding = ready_semantic_preflight(
        "cursor_auto",
        output_root=output_root,
    )
    monkeypatch.setattr(journal, "OUTPUT_ROOT", output_root)
    monkeypatch.setattr(
        journal,
        "execution_root",
        lambda execution_id: output_root / "data/tasks" / execution_id,
    )
    monkeypatch.setattr(
        journal,
        "load_frozen_execution_manifest",
        lambda execution_id: _manifest(execution_id, preflight_binding),
    )
    monkeypatch.setattr(
        journal,
        "load_frozen_target_set",
        lambda _execution_id: {"entityCatalogDigest": "sha256:" + "5" * 64},
    )
    return output_root


def _manifest(
    execution_id: str,
    preflight_binding: dict[str, str],
) -> dict[str, object]:
    return {
        "executionId": execution_id,
        "sourceDigest": {"digest": "sha256:" + "1" * 64},
        "targetSetDigest": "2" * 64,
        "runtimeProfileId": DEFAULT_RUNTIME_PROFILE_ID,
        "runtimeProfileDigest": runtime_profile_digest(DEFAULT_RUNTIME_PROFILE_ID),
        "semanticSelectionId": "cursor_auto",
        "semanticPreflightReceipt": preflight_binding,
    }


def test_semantic_task_request_and_attempts_are_create_once_and_redacted(
    journal_runtime: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _context("article")
    prompt = "Write one source-ready article without touching any environment."
    first = journal.begin_semantic_task(ctx, prompt)
    repeated = journal.begin_semantic_task(ctx, prompt)

    assert repeated.request == first.request
    assert repeated.next_attempt == 1
    assert first.request["carrier"] == "article"
    assert first.request["stage"] == "author"
    source_identity = first.request["sourceIdentity"]
    assert source_identity["sourceRevision"] == content_source_revision(
        source_digest=source_identity["sourceDigest"],
        entity_catalog_digest=source_identity["entityCatalogDigest"],
    )
    preflight_binding = first.request["semanticPreflightReceipt"]
    assert set(preflight_binding) == {
        "receiptRef",
        "receiptFileSha256",
        "receiptId",
        "selectionDigest",
    }
    assert preflight_binding["receiptId"].startswith("sha256:")
    assert first.request["workspaceRef"].startswith("data/tasks/")
    assert "queue" not in json.dumps(first.request).casefold()
    assert "environment" not in json.dumps(first.request).casefold()

    outcome = AgentRunOutcome.finished(
        provider=AgentProvider.CURSOR_SDK,
        result_text="private generated body that must not enter the journal",
        run_id="cursor-run-1",
        agent_id="cursor-agent-1",
        duration_ms=123,
    )
    attempt_path = journal.record_semantic_task_outcome(first, outcome)
    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    assert attempt["attempt"] == 1
    assert attempt["status"] == "finished"
    assert attempt["runId"] == "cursor-run-1"
    assert "private generated body" not in attempt_path.read_text(encoding="utf-8")

    second = journal.begin_semantic_task(ctx, prompt)
    assert second.next_attempt == 2
    failed = AgentRunOutcome.failed(
        AgentFailureKind.BRIDGE_UNAVAILABLE,
        provider=AgentProvider.CURSOR_SDK,
        message="host-specific diagnostic must not enter the journal",
        retryable=True,
        error_code="bridge_unavailable",
    )
    failed_path = journal.record_semantic_task_outcome(second, failed)
    failed_attempt = json.loads(failed_path.read_text(encoding="utf-8"))
    assert failed_attempt["failureKind"] == "bridge_unavailable"
    assert failed_attempt["retryable"] is True
    assert "host-specific diagnostic" not in failed_path.read_text(encoding="utf-8")

    monkeypatch.setattr(
        journal,
        "load_frozen_target_set",
        lambda _execution_id: {"entityCatalogDigest": "sha256:" + "6" * 64},
    )
    with pytest.raises(FileExistsError, match="create-once conflict"):
        journal.begin_semantic_task(ctx, prompt)


def test_semantic_task_journal_allows_four_independent_carrier_workspaces(
    journal_runtime: Path,
) -> None:
    carriers = ("homepage", "article", "image", "video")

    def run(carrier: str) -> tuple[str, str]:
        handle = journal.begin_semantic_task(
            _context(carrier, role="reviewer"),
            f"Review the frozen {carrier} object.",
        )
        path = journal.record_semantic_task_outcome(
            handle,
            AgentRunOutcome.finished(
                provider=AgentProvider.CURSOR_SDK,
                run_id=f"run-{carrier}",
            ),
        )
        assert "taskId" not in handle.request
        return str(handle.request["workUnitId"]), path.as_posix()

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(run, carriers))

    assert len({task_id for task_id, _path in results}) == 4
    assert all(Path(path).is_file() for _task_id, path in results)


def test_semantic_task_journal_enforces_frozen_max_attempts(
    journal_runtime: Path,
) -> None:
    ctx = _context("image", max_attempts=3)
    prompt = "Author one image post."
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        handle = journal.begin_semantic_task(ctx, prompt)
        assert handle.next_attempt == attempt
        journal.record_semantic_task_outcome(
            handle,
            AgentRunOutcome.failed(
                AgentFailureKind.BRIDGE_UNAVAILABLE,
                provider=AgentProvider.CURSOR_SDK,
                message="retryable",
                retryable=True,
            ),
        )
    with pytest.raises(
        journal.SemanticTaskAttemptsExhausted,
        match="maxAttempts exhausted",
    ) as exhausted:
        journal.begin_semantic_task(ctx, prompt)
    assert exhausted.value.work_unit_id.startswith("sha256:")
    assert exhausted.value.max_attempts == max_attempts


def test_exhausted_journal_is_typed_and_never_calls_provider(
    journal_runtime: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _context("article", max_attempts=2)
    monkeypatch.setattr(journal, "ExecutionContext", SimpleNamespace)
    prompt = "Author the one unfinished article object."
    for _attempt in range(2):
        handle = journal.begin_semantic_task(ctx, prompt)
        journal.record_semantic_task_outcome(
            handle,
            AgentRunOutcome.failed(
                AgentFailureKind.BRIDGE_UNAVAILABLE,
                provider=AgentProvider.CURSOR_SDK,
                message="provider attempt failed",
                retryable=True,
            ),
        )

    provider_calls: list[str] = []
    outcome = journal.run_journaled_semantic_task(
        ctx,
        prompt,
        lambda _ctx, value: provider_calls.append(value)
        or AgentRunOutcome.finished(provider=AgentProvider.CURSOR_SDK),
    )

    assert provider_calls == []
    assert outcome.started is False
    assert outcome.retryable is False
    assert outcome.attempts == 2
    assert outcome.error_code == "semantic_task_journal_attempts_exhausted"
    assert "maxAttempts exhausted" in outcome.message


def test_provider_exception_is_recorded_for_only_that_task(
    journal_runtime: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _context("video")
    monkeypatch.setattr(journal, "ExecutionContext", SimpleNamespace)

    def raise_provider(_ctx, _prompt):
        raise RuntimeError("task-local provider diagnostic")

    outcome = journal.run_journaled_semantic_task(
        ctx,
        "Review one video object.",
        raise_provider,
    )

    assert outcome.status.value == "error"
    assert outcome.error_code == "semantic_provider_invocation_exception"
    assert outcome.invocation_attempt_digest.startswith("sha256:")
    attempt_path = journal_runtime / outcome.invocation_attempt_ref
    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    assert attempt["status"] == "error"
    assert attempt["errorCode"] == "semantic_provider_invocation_exception"
    assert "task-local provider diagnostic" not in attempt_path.read_text(encoding="utf-8")


def test_semantic_task_journal_rejects_runtime_profile_digest_drift(
    journal_runtime: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _context("homepage")
    receipt = ready_semantic_preflight(
        "cursor_auto",
        output_root=journal_runtime,
    )[1]
    manifest = _manifest(ctx.execution_id, receipt)
    manifest["runtimeProfileDigest"] = "sha256:" + "0" * 64
    monkeypatch.setattr(
        journal,
        "load_frozen_execution_manifest",
        lambda _execution_id: manifest,
    )

    with pytest.raises(ValueError, match="runtime profile digest drift"):
        journal.begin_semantic_task(ctx, "Author one homepage.")


def test_provider_dispatch_records_local_journal_without_queue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeContext:
        semantic_role = "author"
        agent_provider = AgentProvider.CURSOR_SDK

    ctx = FakeContext()
    handle = object()
    outcome = AgentRunOutcome.finished(
        provider=AgentProvider.CURSOR_SDK,
        run_id="cursor-run",
    )
    observed: list[object] = []
    attempt_path = tmp_path / "attempt.json"
    attempt_path.write_text(
        json.dumps({"attemptDigest": "sha256:" + "a" * 64}),
        encoding="utf-8",
    )
    monkeypatch.setattr(journal, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(agent_runner, "ExecutionContext", FakeContext)
    monkeypatch.setattr(journal, "ExecutionContext", FakeContext)
    monkeypatch.setattr(
        journal,
        "begin_semantic_task",
        lambda actual_ctx, prompt: observed.extend((actual_ctx, prompt)) or handle,
    )
    monkeypatch.setattr(
        agent_runner,
        "_managed_agent_runner_for_provider_unjournaled",
        lambda actual_ctx, prompt: outcome,
    )
    monkeypatch.setattr(
        journal,
        "record_semantic_task_outcome",
        lambda actual_handle, actual_outcome: (
            observed.extend((actual_handle, actual_outcome)) or attempt_path
        ),
    )

    recorded = agent_runner._managed_agent_runner_for_provider(ctx, "prompt")
    assert recorded.succeeded
    assert recorded.invocation_attempt_ref == "attempt.json"
    assert recorded.invocation_attempt_digest == "sha256:" + "a" * 64
    assert observed == [ctx, "prompt", handle, outcome]
