"""Create-once source-scoped reviewer journal without an execution identity."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from core.control_types import AgentProvider

from content.execution.agent.capacity_broker import SemanticCapacityBroker
from content.execution.agent.outcome import AgentRunOutcome

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
    body = json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != body:
            raise ValueError(f"source review create-once collision: {path}")
        return path
    path.write_text(body, encoding="utf-8")
    return path


def _write_once_bytes(path: Path, body: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != body:
            raise ValueError(f"source review create-once collision: {path}")
        return path
    path.write_bytes(body)
    return path


def _replay_finished_attempt(
    *,
    root: Path,
    request: Mapping[str, Any],
    request_path: Path,
    attempt: Mapping[str, Any],
    attempt_path: Path,
) -> tuple[dict[str, Any], Path]:
    """Rehydrate a fully persisted finished attempt, or fail typed.

    Historical attempts recorded only ``resultSha256``.  Replaying them used to
    return a journal without ``outcome``/``capacityReceipt`` keys, which made
    every consumer crash with ``KeyError``.  A finished attempt is replayable
    only when its result text and capacity receipt were persisted alongside it.
    """
    result_text = attempt.get("resultText")
    receipt_ref = str(attempt.get("capacityReceiptRef") or "")
    if not isinstance(result_text, str) or not receipt_ref:
        raise SourceReviewReplayError(
            "finished source review attempt did not persist its result: "
            f"{attempt_path}"
        )
    result_sha = "sha256:" + hashlib.sha256(result_text.encode()).hexdigest()
    if result_sha != attempt.get("resultSha256"):
        raise SourceReviewReplayError(
            f"persisted source review result drifted: {attempt_path}"
        )
    receipt_path = (root / receipt_ref).resolve()
    if (
        receipt_path.is_symlink()
        or not receipt_path.is_file()
        or root.resolve() not in receipt_path.parents
    ):
        raise SourceReviewReplayError(
            f"persisted capacity receipt is unavailable: {receipt_ref}"
        )
    receipt_sha = "sha256:" + hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    if receipt_sha != attempt.get("capacityReceiptSha256"):
        raise SourceReviewReplayError(
            f"persisted capacity receipt drifted: {receipt_ref}"
        )
    capacity = json.loads(receipt_path.read_text(encoding="utf-8"))
    if not isinstance(capacity, dict):
        raise SourceReviewReplayError(
            f"persisted capacity receipt is not an object: {receipt_ref}"
        )
    outcome = AgentRunOutcome.finished(
        provider=AgentProvider.CURSOR_SDK,
        run_id=str(attempt.get("runId") or ""),
        result_text=result_text,
    )
    return {
        "request": dict(request), "requestPath": request_path,
        "attempt": dict(attempt), "attemptPath": attempt_path,
        "capacityReceipt": capacity, "capacityReceiptPath": receipt_path,
        "outcome": outcome,
    }, attempt_path


def run_source_review(
    *,
    source_evidence_root: Path,
    source_review: Mapping[str, object],
    model: str,
    runtime_profile_id: str,
    prompt: str,
    broker: SemanticCapacityBroker,
    runner: Callable[[str], AgentRunOutcome],
    lane: str = "image",
) -> tuple[dict[str, Any], Path]:
    """Run one governed reviewer under the shared broker and source identity."""
    identity = dict(source_review)
    if (
        set(identity) != _IDENTITY_FIELDS
        or model != "grok-4.5"
        or lane not in {"image", "video"}
    ):
        raise ValueError("source review identity, model, or lane is invalid")
    request = {
        "schema": "quwoquan_data.semantic_source_review_request",
        "sourceReview": identity,
        "provider": "cursor_sdk",
        "model": model,
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
                root=evidence_root,
                request=request,
                request_path=request_path,
                attempt=existing,
                attempt_path=latest_path,
            )
    lease = broker.acquire(
        AgentProvider.CURSOR_SDK, lane=lane, capacity=4,
        wait_timeout_seconds=60, lease_ttl_seconds=900,
    )
    try:
        outcome = runner(prompt)
        capacity, capacity_path = broker.write_capacity_receipt(
            lease, source_review=identity, model=model, role="reviewer",
            prompt=prompt, outcome=outcome, runtime_profile_id=runtime_profile_id,
        )
    finally:
        lease.release()
    stored_receipt_path = _write_once_bytes(
        root / "capacity-receipts" / capacity_path.name,
        capacity_path.read_bytes(),
    )
    attempt = {
        "schema": "quwoquan_data.semantic_source_review_attempt",
        "requestDigest": request["journalDigest"],
        "capacityReceiptSha256": "sha256:" + hashlib.sha256(capacity_path.read_bytes()).hexdigest(),
        "capacityReceiptRef": stored_receipt_path.relative_to(evidence_root).as_posix(),
        "status": outcome.status.value,
        "runId": outcome.run_id,
        "resultSha256": "sha256:" + hashlib.sha256(outcome.result_text.encode()).hexdigest(),
        "resultText": outcome.result_text,
    }
    attempt["attemptDigest"] = _digest(attempt)
    attempt_path = _write_once(
        attempts_root / f"{len(existing_attempts) + 1:03}.json", attempt
    )
    return {
        "request": request, "requestPath": request_path, "attempt": attempt,
        "attemptPath": attempt_path, "capacityReceipt": capacity,
        "capacityReceiptPath": capacity_path, "outcome": outcome,
    }, attempt_path
