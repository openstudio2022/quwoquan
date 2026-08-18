"""Create-once source-scoped reviewer journal without an execution identity."""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.control_types import AgentFailureKind, AgentProvider

from content.execution.agent.outcome import AgentRunOutcome
from content.execution.model_contract import governed_cursor_grok_model

_IDENTITY_FIELDS = {
    "sourceRevision", "sourceDigest", "entityCatalogDigest",
    "executionBundleDigest", "handoffDigest", "requestDigest",
}

REVIEW_RESULT_UNAVAILABLE = "DATA.AGENT.REVIEW_RESULT_UNAVAILABLE"


class SourceReviewReplayError(ValueError):
    """Typed replay failure: a finished attempt cannot rehydrate its result."""

    def __init__(self, detail: str) -> None:
        self.code = REVIEW_RESULT_UNAVAILABLE
        super().__init__(f"{REVIEW_RESULT_UNAVAILABLE}: {detail}")


def _digest(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _write_once(path: Path, value: Mapping[str, Any]) -> Path:
    body = (
        json.dumps(
            dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        + "\n"
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.is_symlink() or not path.is_file() or path.read_bytes() != body:
            raise ValueError(f"source review create-once collision: {path}") from None
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


def _replay_finished_attempt(
    *,
    request: Mapping[str, Any],
    request_path: Path,
    attempt: Mapping[str, Any],
    attempt_path: Path,
) -> tuple[dict[str, Any], Path]:
    """Rehydrate a fully persisted finished attempt, or fail typed.

    A finished attempt is replayable only when its exact result and invocation
    identity were persisted alongside it.
    """
    result_text = attempt.get("resultText")
    provider = str(attempt.get("provider") or "")
    if not isinstance(result_text, str) or provider != AgentProvider.CURSOR_SDK.value:
        raise SourceReviewReplayError(
            "finished source review attempt did not persist its invocation: "
            f"{attempt_path}"
        )
    result_sha = "sha256:" + hashlib.sha256(result_text.encode()).hexdigest()
    if result_sha != attempt.get("resultSha256"):
        raise SourceReviewReplayError(
            f"persisted source review result drifted: {attempt_path}"
        )
    stable_attempt = {key: value for key, value in attempt.items() if key != "attemptDigest"}
    if _digest(stable_attempt) != attempt.get("attemptDigest"):
        raise SourceReviewReplayError(
            f"persisted source review attempt drifted: {attempt_path}"
        )
    outcome = AgentRunOutcome.finished(
        provider=AgentProvider.CURSOR_SDK,
        run_id=str(attempt.get("runId") or ""),
        agent_id=str(attempt.get("agentId") or ""),
        request_id=str(attempt.get("requestId") or ""),
        duration_ms=int(attempt.get("durationMs") or 0),
        attempts=int(attempt.get("attempts") or 0),
        warm_attempts=int(attempt.get("warmAttempts") or 0),
        retry_after_seconds=int(attempt.get("retryAfterSeconds") or 0),
        result_text=result_text,
    )
    return {
        "request": dict(request), "requestPath": request_path,
        "attempt": dict(attempt), "attemptPath": attempt_path,
        "outcome": outcome,
    }, attempt_path


def run_source_review(
    *,
    source_evidence_root: Path,
    source_review: Mapping[str, object],
    model: str,
    prompt: str,
    runner: Callable[[str], AgentRunOutcome],
) -> tuple[dict[str, Any], Path]:
    """Invoke one governed reviewer and append its task-local terminal attempt."""
    identity = dict(source_review)
    if set(identity) != _IDENTITY_FIELDS or model != governed_cursor_grok_model():
        raise ValueError("source review identity or model is invalid")
    request = {
        "schema": "quwoquan_data.semantic_source_review_request",
        "sourceReview": identity,
        "provider": "cursor_sdk",
        "model": model,
        "role": "reviewer",
        "promptSha256": "sha256:" + hashlib.sha256(prompt.encode()).hexdigest(),
    }
    request["journalDigest"] = _digest(request)
    token = str(request["journalDigest"]).removeprefix("sha256:")
    evidence_root = source_evidence_root.resolve()
    root = evidence_root / "source-reviews" / token
    request_path = _write_once(root / "request.json", request)
    attempts_root = root / "attempts"
    existing_attempts = sorted(attempts_root.glob("*.json"))
    if existing_attempts:
        latest_path = existing_attempts[-1]
        existing = json.loads(latest_path.read_text(encoding="utf-8"))
        if not isinstance(existing, dict) or existing.get("requestDigest") != request["journalDigest"]:
            raise ValueError("source review attempt drift")
        if existing.get("status") == "finished":
            return _replay_finished_attempt(
                request=request,
                request_path=request_path,
                attempt=existing,
                attempt_path=latest_path,
            )
    try:
        outcome = runner(prompt)
    except Exception as exc:  # noqa: BLE001
        outcome = AgentRunOutcome.failed(
            AgentFailureKind.SDK_EXECUTION_FAILED,
            provider=AgentProvider.CURSOR_SDK,
            message=f"source reviewer invocation raised {type(exc).__name__}",
            error_code="semantic_source_review_invocation_exception",
        )
    if not isinstance(outcome, AgentRunOutcome):
        outcome = AgentRunOutcome.failed(
            AgentFailureKind.SDK_EXECUTION_FAILED,
            provider=AgentProvider.CURSOR_SDK,
            message="source reviewer invocation returned an invalid outcome",
            error_code="semantic_source_review_outcome_invalid",
        )
    elif outcome.provider is not AgentProvider.CURSOR_SDK:
        outcome = AgentRunOutcome.failed(
            AgentFailureKind.SDK_EXECUTION_FAILED,
            provider=AgentProvider.CURSOR_SDK,
            message="source reviewer invocation returned a provider mismatch",
            error_code="semantic_source_review_provider_mismatch",
        )
    stable_attempt = {
        "schema": "quwoquan_data.semantic_source_review_attempt",
        "requestDigest": request["journalDigest"],
        "attempt": len(existing_attempts) + 1,
        "recordedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "started": outcome.started,
        "status": outcome.status.value,
        "provider": outcome.provider.value,
        "runId": outcome.run_id,
        "agentId": outcome.agent_id,
        "requestId": outcome.request_id,
        "durationMs": outcome.duration_ms,
        "resultSha256": "sha256:" + hashlib.sha256(outcome.result_text.encode()).hexdigest(),
        "resultText": outcome.result_text,
        "failureKind": outcome.failure_kind.value if outcome.failure_kind else "",
        "messageSha256": "sha256:" + hashlib.sha256(outcome.message.encode()).hexdigest(),
        "errorCode": outcome.error_code,
        "retryable": outcome.retryable,
        "retryAfterSeconds": outcome.retry_after_seconds,
        "attempts": outcome.attempts,
        "warmAttempts": outcome.warm_attempts,
    }
    attempt = {**stable_attempt, "attemptDigest": _digest(stable_attempt)}
    attempt_path = _write_once(
        attempts_root / f"{len(existing_attempts) + 1:03}.json", attempt
    )
    return {
        "request": request, "requestPath": request_path, "attempt": attempt,
        "attemptPath": attempt_path, "outcome": outcome,
    }, attempt_path
