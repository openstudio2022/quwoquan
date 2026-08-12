from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from content.execution.planning.semantic_failover_admission import (
    require_cursor_auto_retry_admission,
)
from content.execution.preflight.selection import resolve_semantic_preflight_selection
from core.io import write_json
from core.runtime_policy import runtime_profile_digest


PREDECESSOR_ID = "20260812--travel-article-m100--china--scale-101"


def _digest(payload: dict[str, object]) -> str:
    body = (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _write_predecessor(
    output_root: Path,
    *,
    failure_kind: str = "provider_rejected",
    error_code: str = "semantic_provider_model_unavailable",
    status: str = "error",
) -> None:
    root = output_root / "data/tasks" / PREDECESSOR_ID
    selection = resolve_semantic_preflight_selection("cursor_grok")
    manifest = {
        "executionId": PREDECESSOR_ID,
        "familyRef": {"ref": "content/travel/article/article", "sha256": "1" * 64},
        "sourceDigest": {
            "algorithm": "sha256",
            "digest": "sha256:" + "2" * 64,
            "inputs": ["quwoquan_data/reference"],
        },
        "modelBinding": {
            "provider": "cursor_sdk",
            "authorModel": "grok-4.5",
            "authorModelFamily": "grok",
            "authorModelParameters": [],
            "reviewerModel": "grok-4.5",
            "reviewerModelFamily": "grok",
            "reviewerModelParameters": [],
        },
        "runtimeProfileId": selection.runtime_profile_id,
        "runtimeProfileDigest": selection.runtime_profile_digest,
        "semanticSelectionId": "cursor_grok",
        "semanticPreflightReceipt": {
            "receiptRef": "data/local/cache/semantic-preflight/grok.json",
            "receiptFileSha256": "sha256:" + "3" * 64,
            "receiptId": "sha256:" + "4" * 64,
            "selectionDigest": selection.selection_digest,
        },
        "semanticRuntime": "local",
        "requestRef": "0.plan/request.json",
        "targetSetRef": "0.plan/target_set.json",
        "targetSetDigest": "5" * 64,
        "retryOf": None,
    }
    write_json(root / "execution_manifest.json", manifest)
    request_stable: dict[str, object] = {
        "schema": "quwoquan_data.semantic_task_journal_request",
        "workUnitId": "sha256:" + "6" * 64,
        "executionId": PREDECESSOR_ID,
        "carrier": "article",
        "stage": "author",
        "promptSha256": "sha256:" + "7" * 64,
        "sourceIdentity": {
            "sourceRevision": "sha256:" + "8" * 64,
            "sourceDigest": "sha256:" + "2" * 64,
            "entityCatalogDigest": "sha256:" + "9" * 64,
            "targetSetDigest": "5" * 64,
        },
        "semanticPreflightReceipt": manifest["semanticPreflightReceipt"],
        "workspaceRef": f"data/tasks/{PREDECESSOR_ID}",
        "provider": "cursor_sdk",
        "model": "grok-4.5",
        "modelParameters": [],
        "runtimeProfileId": selection.runtime_profile_id,
        "runtimeProfileDigest": runtime_profile_digest(selection.runtime_profile_id),
        "semanticSelectionDigest": selection.selection_digest,
        "maxAttempts": 2,
    }
    request = {**request_stable, "requestDigest": _digest(request_stable)}
    journal = root / "_shared/semantic_tasks" / ("6" * 64)
    write_json(journal / "request.json", request)
    attempt_stable: dict[str, object] = {
        "schema": "quwoquan_data.semantic_task_journal_attempt",
        "workUnitId": request["workUnitId"],
        "requestDigest": request["requestDigest"],
        "attempt": 1,
        "recordedAt": "2026-08-12T00:00:00Z",
        "status": status,
        "provider": "cursor_sdk",
        "runId": "run-1",
        "agentId": "agent-1",
        "requestId": "request-1",
        "durationMs": 1,
        "resultSha256": "sha256:" + "a" * 64,
        "failureKind": failure_kind,
        "errorCode": error_code,
        "retryable": False,
        "capacityReceiptRef": "",
        "capacityReceiptDigest": "",
    }
    write_json(
        journal / "attempts/0001.json",
        {**attempt_stable, "attemptDigest": _digest(attempt_stable)},
    )


def test_cursor_auto_admits_only_explicit_retry_of_typed_grok_failure(
    tmp_path: Path,
) -> None:
    _write_predecessor(tmp_path)

    proof = require_cursor_auto_retry_admission(PREDECESSOR_ID, output_root=tmp_path)

    assert proof["retryOf"] == PREDECESSOR_ID
    assert proof["failureKind"] == "provider_rejected"
    assert proof["errorCode"] == "semantic_provider_model_unavailable"
    assert proof["attemptRef"].endswith("/attempts/0001.json")


@pytest.mark.parametrize(
    ("failure_kind", "error_code", "status"),
    (
        ("authentication_rejected", "semantic_provider_authentication_rejected", "error"),
        ("sdk_execution_failed", "semantic_provider_execution_failed", "error"),
        ("provider_rejected", "semantic_provider_model_unavailable", "finished"),
    ),
)
def test_cursor_auto_rejects_untyped_or_nonterminal_grok_journal(
    tmp_path: Path,
    failure_kind: str,
    error_code: str,
    status: str,
) -> None:
    _write_predecessor(
        tmp_path,
        failure_kind=failure_kind,
        error_code=error_code,
        status=status,
    )

    with pytest.raises(ValueError, match="TYPED_FAILURE_MISSING"):
        require_cursor_auto_retry_admission(PREDECESSOR_ID, output_root=tmp_path)


def test_cursor_auto_rejects_first_use_without_retry_of(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="CURSOR_AUTO_RETRY_REQUIRED"):
        require_cursor_auto_retry_admission(None, output_root=tmp_path)
