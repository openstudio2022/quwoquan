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
from enum import StrEnum
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


class SemanticTaskRecoveryReason(StrEnum):
    """Why a work unit is granted attempts beyond its frozen budget.

    Every reason names a cause outside the authored content: an interrupted
    host, an exhausted provider quota, an unwritable transport, or an explicit
    operator disposition. Content that was authored and judged unfit is never a
    recovery reason, because retrying it would only re-spend provider quota on
    the same rejected candidate.
    """

    INFRASTRUCTURE_INTERRUPTION = "infrastructure_interruption"
    PROVIDER_QUOTA_EXHAUSTED = "provider_quota_exhausted"
    TRANSPORT_UNAVAILABLE = "transport_unavailable"
    OPERATOR_DISPOSITION = "operator_disposition"


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
    if preflight:
        validate_semantic_preflight_binding(
            preflight,
            semantic_selection_id=selection.selection_id,
            output_root=OUTPUT_ROOT,
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


def recovery_grants_root(journal_root: Path) -> Path:
    return journal_root / "recovery_grants"


def granted_extra_attempts(journal_root: Path, *, request_digest: str) -> int:
    """Sum the append-only attempt grants bound to this exact frozen request.

    A grant recorded against a different request digest belongs to a different
    frozen work unit and must not widen this one's budget.
    """

    grants_root = recovery_grants_root(journal_root)
    if not grants_root.is_dir():
        return 0
    total = 0
    for path in sorted(grants_root.glob("*.json")):
        grant = json.loads(path.read_text(encoding="utf-8"))
        assert_valid(
            grant,
            "execution",
            "semantic_task_recovery_grant",
            label=f"semantic task recovery grant:{path.name}",
        )
        if str(grant.get("requestDigest") or "") != request_digest:
            raise ValueError(
                f"semantic task recovery grant is bound to another request: {path}"
            )
        total += int(grant["grant"])
    return total


def grant_semantic_task_attempts(
    journal_root: Path,
    *,
    request: Mapping[str, Any],
    grant: int,
    reason: SemanticTaskRecoveryReason,
    granted_by: str,
) -> Path:
    """Append one attempt grant so an unfinished work unit can resume in place.

    This is the only sanctioned way to move a work unit past its frozen attempt
    budget. It appends; it never edits ``request.json`` and never removes or
    rewrites an attempt record, so the audit trail after recovery still shows
    every attempt that was actually made plus who authorized the extra ones.
    """

    if isinstance(grant, bool) or not isinstance(grant, int) or grant < 1:
        raise ValueError("semantic task attempt grant must be a positive integer")
    if not isinstance(reason, SemanticTaskRecoveryReason):
        raise TypeError("semantic task recovery reason must be typed")
    owner = str(granted_by or "").strip()
    if not owner:
        raise ValueError("semantic task attempt grant requires grantedBy")
    request_digest = str(request["requestDigest"])
    attempts_root = journal_root / "attempts"
    existing_attempts = (
        sorted(attempts_root.glob("*.json")) if attempts_root.is_dir() else []
    )
    for path in existing_attempts:
        attempt = json.loads(path.read_text(encoding="utf-8"))
        if str(attempt.get("status") or "") == "succeeded":
            raise ValueError(
                "semantic task already has a succeeded attempt; granting more "
                "attempts would put completed evidence back at risk"
            )
    grants_root = recovery_grants_root(journal_root)
    ordinal = (
        len(sorted(grants_root.glob("*.json"))) + 1 if grants_root.is_dir() else 1
    )
    stable: dict[str, Any] = {
        "schema": "quwoquan_data.semantic_task_recovery_grant",
        "workUnitId": str(request["workUnitId"]),
        "requestDigest": request_digest,
        "grant": grant,
        "grantedAttempts": int(request["maxAttempts"])
        + granted_extra_attempts(journal_root, request_digest=request_digest)
        + grant,
        "attemptsBeforeGrant": len(existing_attempts),
        "reason": reason.value,
        "grantedBy": owner,
        "grantedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    document = {**stable, "grantDigest": _digest(stable)}
    assert_valid(
        document,
        "execution",
        "semantic_task_recovery_grant",
        label=f"semantic task recovery grant:{request['workUnitId']}",
    )
    return _write_create_once(
        grants_root / f"{ordinal:04d}.json",
        document,
        label="semantic task recovery grant",
    )


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
    admitted_attempts = int(request["maxAttempts"]) + granted_extra_attempts(
        journal_root,
        request_digest=str(request["requestDigest"]),
    )
    if next_attempt > admitted_attempts:
        raise SemanticTaskAttemptsExhausted(
            work_unit_id=str(request["workUnitId"]),
            max_attempts=admitted_attempts,
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
        "started": outcome.started,
        "status": outcome.status.value,
        "provider": outcome.provider.value,
        "runId": outcome.run_id,
        "agentId": outcome.agent_id,
        "requestId": outcome.request_id,
        "durationMs": outcome.duration_ms,
        "resultSha256": _text_digest(outcome.result_text),
        "failureKind": failure_kind,
        "messageSha256": _text_digest(outcome.message),
        "errorCode": outcome.error_code,
        "retryable": outcome.retryable,
        "retryAfterSeconds": outcome.retry_after_seconds,
        "attempts": outcome.attempts,
        "warmAttempts": outcome.warm_attempts,
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
    try:
        outcome = provider_runner(ctx, prompt)
    except Exception as exc:  # noqa: BLE001
        outcome = AgentRunOutcome.failed(
            AgentFailureKind.SDK_EXECUTION_FAILED,
            provider=provider,
            message=f"semantic provider invocation raised {type(exc).__name__}",
            retryable=False,
            error_code="semantic_provider_invocation_exception",
        )
    if not isinstance(outcome, AgentRunOutcome):
        outcome = AgentRunOutcome.failed(
            AgentFailureKind.SDK_EXECUTION_FAILED,
            provider=provider,
            message="semantic provider invocation returned an invalid outcome",
            retryable=False,
            error_code="semantic_provider_outcome_invalid",
        )
    try:
        attempt_path = record_semantic_task_outcome(handle, outcome)
        attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
        attempt_digest = str(attempt.get("attemptDigest") or "")
        attempt_ref = attempt_path.resolve().relative_to(OUTPUT_ROOT.resolve()).as_posix()
        outcome = outcome.with_invocation_attempt(
            attempt_ref=attempt_ref,
            attempt_digest=attempt_digest,
        )
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
    "SemanticTaskRecoveryReason",
    "begin_semantic_task",
    "grant_semantic_task_attempts",
    "granted_extra_attempts",
    "record_semantic_task_outcome",
    "recovery_grants_root",
    "run_journaled_semantic_task",
]
