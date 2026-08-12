"""Create-once local journal for provider-bound author and reviewer tasks.

The journal freezes semantic work before a provider call and appends only
redacted terminal summaries afterwards. It deliberately has no queue,
ReliableTask, Mongo, Redis, release, or environment dependency.
"""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.paths import OUTPUT_ROOT
from core.runtime_policy import (
    load_runtime_policy,
    runtime_profile_digest,
)
from core.schema import assert_valid
from core.source_digest import content_source_revision

from content.execution.context import ExecutionContext
from content.execution.identity import parse_execution_id
from content.execution.planning.semantic_preflight_admission import (
    validate_semantic_preflight_binding,
)
from content.execution.preflight.selection import resolve_semantic_preflight_selection
from content.execution.workspace import (
    execution_root,
    load_frozen_execution_manifest,
    load_frozen_target_set,
)

if TYPE_CHECKING:
    from content.execution.agent.outcome import AgentRunOutcome


@dataclass(frozen=True, slots=True)
class SemanticTaskJournalHandle:
    request: Mapping[str, Any]
    journal_root: Path
    next_attempt: int


class SemanticTaskAttemptsExhausted(RuntimeError):
    """Frozen work unit spent every admitted attempt without changing policy."""

    error_code = "semantic_task_journal_attempts_exhausted"

    def __init__(self, *, work_unit_id: str, max_attempts: int) -> None:
        self.work_unit_id = work_unit_id
        self.max_attempts = max_attempts
        super().__init__(
            "semantic task maxAttempts exhausted: "
            f"{work_unit_id} ({max_attempts})"
        )


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _digest(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _text_digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_create_once(path: Path, payload: Mapping[str, Any], *, label: str) -> Path:
    body = _canonical_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.is_symlink() or not path.is_file() or path.read_bytes() != body:
            raise FileExistsError(f"{label} create-once conflict: {path}") from None
        return path
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def _request_for_context(ctx: ExecutionContext, prompt: str) -> dict[str, Any]:
    role = str(ctx.semantic_role or "").strip()
    if role not in {"author", "reviewer"}:
        raise ValueError("semantic task journal only accepts author or reviewer")
    manifest = load_frozen_execution_manifest(ctx.execution_id)
    target_set = load_frozen_target_set(ctx.execution_id)
    identity = parse_execution_id(ctx.execution_id)
    source = manifest.get("sourceDigest")
    source = source if isinstance(source, Mapping) else {}
    preflight = manifest.get("semanticPreflightReceipt")
    preflight = preflight if isinstance(preflight, Mapping) else {}
    selection = resolve_semantic_preflight_selection(
        str(manifest.get("semanticSelectionId") or "")
    )
    runtime_profile_id = str(manifest.get("runtimeProfileId") or "").strip()
    frozen_runtime_digest = str(
        manifest.get("runtimeProfileDigest") or ""
    ).strip()
    if (
        not runtime_profile_id
        or runtime_profile_digest(runtime_profile_id) != frozen_runtime_digest
    ):
        raise ValueError("semantic task runtime profile digest drift")
    runtime_policy = load_runtime_policy(runtime_profile_id)
    task_max_attempts = getattr(ctx, "semantic_max_attempts", None)
    if task_max_attempts is None:
        task_max_attempts = runtime_policy.queue_max_attempts
    if (
        isinstance(task_max_attempts, bool)
        or not isinstance(task_max_attempts, int)
        or task_max_attempts < 1
    ):
        raise ValueError("semantic task maxAttempts must be >= 1")
    frozen_selection_digest = str(preflight.get("selectionDigest") or "")
    if frozen_selection_digest and frozen_selection_digest != selection.selection_digest:
        raise ValueError("semantic task preflight selection digest drift")
    if selection.provider.value == "cursor_sdk" and not preflight:
        raise ValueError("cursor semantic task requires a frozen preflight receipt")
    if preflight:
        validate_semantic_preflight_binding(
            preflight,
            semantic_selection_id=selection.selection_id,
            output_root=OUTPUT_ROOT,
            require_fresh=False,
        )
    workspace = execution_root(ctx.execution_id).resolve()
    try:
        workspace_ref = workspace.relative_to(OUTPUT_ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("semantic task workspace must be under output root") from exc
    prompt_sha256 = _text_digest(prompt)
    work_identity = {
        "executionId": ctx.execution_id,
        "stage": role,
        "promptSha256": prompt_sha256,
    }
    source_digest = str(source.get("digest") or "")
    entity_catalog_digest = str(target_set.get("entityCatalogDigest") or "")
    stable: dict[str, Any] = {
        "schema": "quwoquan_data.semantic_task_journal_request",
        "workUnitId": _digest(work_identity),
        "executionId": ctx.execution_id,
        "carrier": identity.content_type.value,
        "stage": role,
        "promptSha256": prompt_sha256,
        "sourceIdentity": {
            "sourceRevision": content_source_revision(
                source_digest=source_digest,
                entity_catalog_digest=entity_catalog_digest,
            ),
            "sourceDigest": source_digest,
            "entityCatalogDigest": entity_catalog_digest,
            "targetSetDigest": str(manifest.get("targetSetDigest") or ""),
        },
        "semanticPreflightReceipt": dict(preflight) if preflight else None,
        "workspaceRef": workspace_ref,
        "provider": ctx.agent_provider.value,
        "model": ctx.model_selection.model_id,
        "modelParameters": ctx.model_selection.parameters_document(),
        "runtimeProfileId": runtime_profile_id,
        "runtimeProfileDigest": frozen_runtime_digest,
        "semanticSelectionDigest": selection.selection_digest,
        "maxAttempts": task_max_attempts,
    }
    request = {**stable, "requestDigest": _digest(stable)}
    assert_valid(
        request,
        "execution",
        "semantic_task_journal_request",
        label=f"semantic task journal request:{ctx.execution_id}",
    )
    return request


def begin_semantic_task(
    ctx: ExecutionContext,
    prompt: str,
) -> SemanticTaskJournalHandle:
    """Freeze one task request and reserve its next append-only attempt ordinal."""

    request = _request_for_context(ctx, prompt)
    journal_root = (
        execution_root(ctx.execution_id)
        / "_shared/semantic_tasks"
        / str(request["workUnitId"]).removeprefix("sha256:")
    )
    _write_create_once(
        journal_root / "request.json",
        request,
        label="semantic task request",
    )
    attempts_root = journal_root / "attempts"
    attempts = sorted(attempts_root.glob("*.json")) if attempts_root.is_dir() else []
    next_attempt = len(attempts) + 1
    if next_attempt > int(request["maxAttempts"]):
        raise SemanticTaskAttemptsExhausted(
            work_unit_id=str(request["workUnitId"]),
            max_attempts=int(request["maxAttempts"]),
        )
    return SemanticTaskJournalHandle(
        request=request,
        journal_root=journal_root,
        next_attempt=next_attempt,
    )


def record_semantic_task_outcome(
    handle: SemanticTaskJournalHandle,
    outcome: AgentRunOutcome,
) -> Path:
    """Append one redacted result summary without copying prompt or result text."""

    failure_kind = outcome.failure_kind.value if outcome.failure_kind else ""
    stable: dict[str, Any] = {
        "schema": "quwoquan_data.semantic_task_journal_attempt",
        "workUnitId": handle.request["workUnitId"],
        "requestDigest": handle.request["requestDigest"],
        "attempt": handle.next_attempt,
        "recordedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": outcome.status.value,
        "provider": outcome.provider.value,
        "runId": outcome.run_id,
        "agentId": outcome.agent_id,
        "requestId": outcome.request_id,
        "durationMs": outcome.duration_ms,
        "resultSha256": _text_digest(outcome.result_text),
        "failureKind": failure_kind,
        "errorCode": outcome.error_code,
        "retryable": outcome.retryable,
        "capacityReceiptRef": outcome.capacity_receipt_ref,
        "capacityReceiptDigest": outcome.capacity_receipt_digest,
    }
    attempt = {**stable, "attemptDigest": _digest(stable)}
    assert_valid(
        attempt,
        "execution",
        "semantic_task_journal_attempt",
        label=f"semantic task journal attempt:{handle.request['workUnitId']}",
    )
    return _write_create_once(
        handle.journal_root / "attempts" / f"{handle.next_attempt:04d}.json",
        attempt,
        label="semantic task attempt",
    )


def run_journaled_semantic_task(
    ctx: ExecutionContext,
    prompt: str,
    provider_runner: Callable[[ExecutionContext, str], AgentRunOutcome],
) -> AgentRunOutcome:
    """Run one content semantic task with fail-closed local journal evidence."""

    from core.control_types import AgentFailureKind, AgentProvider

    from content.execution.agent.outcome import AgentRunOutcome

    if not isinstance(ctx, ExecutionContext) or ctx.semantic_role == "calibration":
        return provider_runner(ctx, prompt)
    provider = ctx.agent_provider
    if not isinstance(provider, AgentProvider):
        provider = AgentProvider(str(provider))
    try:
        handle = begin_semantic_task(ctx, prompt)
    except SemanticTaskAttemptsExhausted as exc:
        return AgentRunOutcome.failed(
            AgentFailureKind.SDK_EXECUTION_FAILED,
            provider=provider,
            message=str(exc),
            retryable=False,
            error_code=exc.error_code,
            attempts=exc.max_attempts,
        )
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        return AgentRunOutcome.failed(
            AgentFailureKind.SDK_EXECUTION_FAILED,
            provider=provider,
            message=f"semantic task journal admission failed: {type(exc).__name__}",
            retryable=False,
            error_code="semantic_task_journal_admission_failed",
        )
    outcome = provider_runner(ctx, prompt)
    try:
        record_semantic_task_outcome(handle, outcome)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return AgentRunOutcome.failed(
            AgentFailureKind.SDK_EXECUTION_FAILED,
            provider=provider,
            message=f"semantic task journal result failed: {type(exc).__name__}",
            started=outcome.started,
            retryable=False,
            error_code="semantic_task_journal_result_failed",
        )
    return outcome


__all__ = [
    "SemanticTaskJournalHandle",
    "SemanticTaskAttemptsExhausted",
    "begin_semantic_task",
    "record_semantic_task_outcome",
    "run_journaled_semantic_task",
]
