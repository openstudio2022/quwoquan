"""Test-only builder for a ready, short-lived semantic preflight receipt."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from content.execution.planning.semantic_preflight_admission import (
    bind_semantic_preflight_receipt,
)
from content.execution.preflight.receipt import (
    build_semantic_preflight_receipt,
    write_semantic_preflight_receipt,
)
from content.execution.preflight.selection import (
    resolve_semantic_preflight_selection,
)
from core.io import write_json
from core.paths import OUTPUT_ROOT


def _canonical_digest(payload: dict[str, object]) -> str:
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


def ready_semantic_preflight(
    semantic_selection_id: str,
    *,
    output_root: Path = OUTPUT_ROOT,
    effective_concurrency: int = 4,
) -> tuple[Path, dict[str, str]]:
    selection = resolve_semantic_preflight_selection(semantic_selection_id)
    report = {
        **selection.document(),
        "selectionDigest": selection.selection_digest,
        "fallbackPolicy": "forbidden",
        "prepare": {"ready": True, "python": sys.executable, "missing": []},
        "preflight": {
            "provider": selection.provider.value,
            "runtime": {"ready": True, "resolvedPython": sys.executable},
            "network": {"checked": True, "ready": True, "issues": []},
            "ready": True,
            "issues": [],
        },
        "provider": selection.provider.value,
        "semanticAgentCredential": {
            "provider": selection.provider.value,
            "source": "local_contract",
            "present": True,
            "valid": True,
            "issues": [],
        },
        "semanticAgentStartup": {
            "provider": selection.provider.value,
            "checked": True,
            "ready": True,
            "runtime": selection.runtime.value,
            "model": selection.model_selection.model_id,
            "issues": [],
        },
        "capacitySoak": {
            "semanticSelectionId": selection.selection_id,
            "selectionDigest": selection.selection_digest,
            "provider": selection.provider.value,
            "model": selection.model_selection.model_id,
            "modelParameters": selection.model_selection.parameters_document(),
            "runtimeProfileDigest": selection.runtime_profile_digest,
            "ready": True,
            "attempts": max(8, effective_concurrency),
            "successCount": max(8, effective_concurrency),
            "effectiveConcurrency": effective_concurrency,
            "bridgeDisconnectCount": 0,
            "issues": [],
        },
        "workspaceSmoke": {
            "ready": True,
            "workspaceCount": 4,
            "successCount": 4,
            "configuredConcurrency": 4,
            "effectiveConcurrency": 4,
            "cleanupStatus": "cleaned",
            "issues": [],
        },
        "startupRequested": True,
        "soakRequested": True,
        "workspaceSmokeRequested": True,
        "ready": True,
    }
    receipt = build_semantic_preflight_receipt(selection=selection, report=report)
    path = (
        output_root
        / "data/local/cache/semantic-preflight/local-contract"
        / f"{receipt['receiptId'].removeprefix('sha256:')}.json"
    )
    write_semantic_preflight_receipt(path, receipt)
    return path, bind_semantic_preflight_receipt(
        path,
        semantic_selection_id=semantic_selection_id,
        output_root=output_root,
    )


def write_typed_cursor_grok_failure(
    execution_id: str,
    *,
    output_root: Path,
) -> None:
    """Write a schema-valid Grok predecessor with one typed provider failure."""

    _, preflight_binding = ready_semantic_preflight(
        "cursor_grok",
        output_root=output_root,
    )
    selection = resolve_semantic_preflight_selection("cursor_grok")
    # Derive the model binding from the governed profile so a model-version
    # change stays a profile edit instead of a fixture edit.
    grok_model = selection.model_selection.model_id
    grok_parameters = selection.model_selection.parameters_document()
    execution_root = output_root / "data/tasks" / execution_id
    manifest: dict[str, object] = {
        "executionId": execution_id,
        "familyRef": {
            "ref": "content/travel/article/article",
            "sha256": "1" * 64,
        },
        "sourceDigest": {
            "algorithm": "sha256",
            "digest": "sha256:" + "2" * 64,
            "inputs": ["quwoquan_data/reference"],
        },
        "executionBundle": {
            "algorithm": "sha256",
            "digest": "sha256:" + "b" * 64,
            "inputs": ["quwoquan_data/scripts"],
        },
        "modelBinding": {
            "provider": "cursor_sdk",
            "authorModel": grok_model,
            "authorModelFamily": "grok",
            "authorModelParameters": grok_parameters,
            "reviewerModel": grok_model,
            "reviewerModelFamily": "grok",
            "reviewerModelParameters": grok_parameters,
        },
        "runtimeProfileId": selection.runtime_profile_id,
        "runtimeProfileDigest": selection.runtime_profile_digest,
        "semanticSelectionId": "cursor_grok",
        "semanticPreflightReceipt": preflight_binding,
        "semanticRuntime": "local",
        "requestRef": "0.plan/request.json",
        "targetSetRef": "0.plan/target_set.json",
        "targetSetDigest": "5" * 64,
        "retryOf": None,
    }
    write_json(execution_root / "execution_manifest.json", manifest)

    request_stable: dict[str, object] = {
        "schema": "quwoquan_data.semantic_task_journal_request",
        "workUnitId": "sha256:" + "6" * 64,
        "executionId": execution_id,
        "carrier": "article",
        "stage": "author",
        "promptSha256": "sha256:" + "7" * 64,
        "sourceIdentity": {
            "sourceRevision": "sha256:" + "8" * 64,
            "sourceDigest": "sha256:" + "2" * 64,
            "entityCatalogDigest": "sha256:" + "9" * 64,
            "targetSetDigest": "5" * 64,
        },
        "semanticPreflightReceipt": preflight_binding,
        "workspaceRef": f"data/tasks/{execution_id}",
        "provider": "cursor_sdk",
        "model": grok_model,
        "modelParameters": grok_parameters,
        "runtimeProfileId": selection.runtime_profile_id,
        "runtimeProfileDigest": selection.runtime_profile_digest,
        "semanticSelectionDigest": selection.selection_digest,
        "maxAttempts": 2,
    }
    request = {
        **request_stable,
        "requestDigest": _canonical_digest(request_stable),
    }
    journal = execution_root / "_shared/semantic_tasks" / ("6" * 64)
    write_json(journal / "request.json", request)

    attempt_stable: dict[str, object] = {
        "schema": "quwoquan_data.semantic_task_journal_attempt",
        "workUnitId": request["workUnitId"],
        "requestDigest": request["requestDigest"],
        "attempt": 1,
        "recordedAt": "2026-08-14T00:00:00Z",
        "started": False,
        "status": "error",
        "provider": "cursor_sdk",
        "runId": "run-1",
        "agentId": "agent-1",
        "requestId": "request-1",
        "durationMs": 1,
        "resultSha256": "sha256:" + "a" * 64,
        "failureKind": "provider_rejected",
        "messageSha256": "sha256:" + hashlib.sha256(b"").hexdigest(),
        "errorCode": "semantic_provider_model_unavailable",
        "retryable": False,
        "retryAfterSeconds": 0,
        "attempts": 1,
        "warmAttempts": 1,
    }
    write_json(
        journal / "attempts/0001.json",
        {
            **attempt_stable,
            "attemptDigest": _canonical_digest(attempt_stable),
        },
    )


__all__ = ["ready_semantic_preflight", "write_typed_cursor_grok_failure"]
