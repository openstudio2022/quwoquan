"""Fail-closed admission for the explicit Cursor Auto retry lane.

``cursor_auto`` is not a first-use selector and this module never chooses it.
It only proves that an explicitly requested new retry points at a governed
``cursor_grok`` execution whose append-only semantic journal ended in a typed
provider/model failure.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core import paths
from core.io import read_json
from core.schema import assert_valid

from content.execution.identity import validate_execution_id
from content.execution.model_contract import (
    CURSOR_GROK_SEMANTIC_SELECTION_ID,
)
from content.execution.preflight.selection import (
    resolve_semantic_preflight_selection,
)
from content.execution.workspace import MANIFEST_FILENAME


_TYPED_PROVIDER_MODEL_FAILURES = frozenset(
    {
        ("provider_rejected", "semantic_provider_quota_exhausted"),
        ("provider_rejected", "semantic_provider_rate_limited"),
        ("provider_rejected", "semantic_provider_capacity_unavailable"),
        ("provider_rejected", "semantic_provider_model_unavailable"),
        ("sdk_execution_failed", "semantic_provider_dns_unavailable"),
        ("sdk_execution_failed", "semantic_provider_transport_timeout"),
        ("sdk_execution_failed", "semantic_provider_transport_unavailable"),
    }
)


def _canonical_digest(payload: Mapping[str, Any]) -> str:
    body = (
        json.dumps(
            dict(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _validated_document(path: Path, *, schema_name: str, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular file: {path}")
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise TypeError(f"{label} must be an object")
    assert_valid(payload, "execution", schema_name, label=label)
    return payload


def require_cursor_auto_retry_admission(
    retry_of: str | None,
    *,
    output_root: Path = paths.OUTPUT_ROOT,
) -> dict[str, str]:
    """Prove a manually selected Auto retry is derived from typed Grok failure."""

    if retry_of is None or not str(retry_of).strip():
        raise ValueError(
            "GATE_BLOCK DATA.AGENT.CURSOR_AUTO_RETRY_REQUIRED: cursor_auto is "
            "allowed only on a new execution with retryOf"
        )
    predecessor_id = validate_execution_id(str(retry_of))
    predecessor_root = Path(output_root) / "data" / "tasks" / predecessor_id
    manifest = _validated_document(
        predecessor_root / MANIFEST_FILENAME,
        schema_name="content_execution_manifest",
        label=f"cursor_auto predecessor manifest:{predecessor_id}",
    )
    binding = manifest.get("modelBinding")
    binding = binding if isinstance(binding, Mapping) else {}
    expected_selection = resolve_semantic_preflight_selection(
        CURSOR_GROK_SEMANTIC_SELECTION_ID
    )
    if (
        manifest.get("executionId") != predecessor_id
        or manifest.get("semanticSelectionId") != CURSOR_GROK_SEMANTIC_SELECTION_ID
        or binding.get("provider") != "cursor_sdk"
        or binding.get("authorModel") != "grok-4.5"
        or binding.get("authorModelFamily") != "grok"
        or binding.get("authorModelParameters") != []
        or binding.get("reviewerModel") != "grok-4.5"
        or binding.get("reviewerModelFamily") != "grok"
        or binding.get("reviewerModelParameters") != []
    ):
        raise ValueError(
            "GATE_BLOCK DATA.AGENT.CURSOR_AUTO_PREDECESSOR_INVALID: retryOf must "
            "reference an exact cursor_grok/grok-4.5 execution"
        )

    journals_root = predecessor_root / "_shared" / "semantic_tasks"
    if journals_root.is_symlink() or not journals_root.is_dir():
        raise ValueError(
            "GATE_BLOCK DATA.AGENT.CURSOR_AUTO_TYPED_FAILURE_MISSING: cursor_grok "
            "predecessor has no semantic task journal"
        )
    typed_failures: list[tuple[dict[str, Any], dict[str, Any], Path]] = []
    for request_path in sorted(journals_root.glob("*/request.json")):
        request = _validated_document(
            request_path,
            schema_name="semantic_task_journal_request",
            label=f"cursor_grok semantic request:{request_path.parent.name}",
        )
        request_stable = dict(request)
        request_digest = str(request_stable.pop("requestDigest", ""))
        if request_digest != _canonical_digest(request_stable):
            raise ValueError("cursor_grok semantic requestDigest drift")
        if (
            request.get("executionId") != predecessor_id
            or request.get("provider") != "cursor_sdk"
            or request.get("model") != "grok-4.5"
            or request.get("modelParameters") != []
            or request.get("semanticSelectionDigest")
            != expected_selection.selection_digest
        ):
            raise ValueError("cursor_grok semantic task identity drift")
        attempt_paths = sorted((request_path.parent / "attempts").glob("*.json"))
        if not attempt_paths:
            continue
        latest_path = attempt_paths[-1]
        latest = _validated_document(
            latest_path,
            schema_name="semantic_task_journal_attempt",
            label=f"cursor_grok semantic attempt:{latest_path.name}",
        )
        attempt_stable = dict(latest)
        attempt_digest = str(attempt_stable.pop("attemptDigest", ""))
        if attempt_digest != _canonical_digest(attempt_stable):
            raise ValueError("cursor_grok semantic attemptDigest drift")
        if (
            latest.get("workUnitId") != request.get("workUnitId")
            or latest.get("requestDigest") != request_digest
            or latest.get("provider") != "cursor_sdk"
        ):
            raise ValueError("cursor_grok semantic attempt lineage drift")
        failure = (str(latest.get("failureKind") or ""), str(latest.get("errorCode") or ""))
        if latest.get("status") == "error" and failure in _TYPED_PROVIDER_MODEL_FAILURES:
            typed_failures.append((request, latest, latest_path))

    if not typed_failures:
        raise ValueError(
            "GATE_BLOCK DATA.AGENT.CURSOR_AUTO_TYPED_FAILURE_MISSING: latest "
            "cursor_grok journal has no typed provider/model failure"
        )
    request, attempt, attempt_path = typed_failures[0]
    return {
        "retryOf": predecessor_id,
        "workUnitId": str(request["workUnitId"]),
        "failureKind": str(attempt["failureKind"]),
        "errorCode": str(attempt["errorCode"]),
        "attemptDigest": str(attempt["attemptDigest"]),
        "attemptRef": attempt_path.relative_to(Path(output_root)).as_posix(),
    }


__all__ = ["require_cursor_auto_retry_admission"]
