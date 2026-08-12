"""Bind a fresh semantic preflight receipt into immutable execution identity."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core import paths
from core.io import read_json
from core.schema import assert_valid

from content.execution.preflight.receipt import (
    validate_semantic_preflight_receipt,
)
from content.execution.preflight.selection import (
    resolve_semantic_preflight_selection,
)
from content.execution.runtime_contract import file_sha256


def _receipt_path(ref: str, *, output_root: Path) -> Path:
    root = output_root.expanduser().resolve()
    candidate = (root / str(ref).strip().strip("/")).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("semantic preflight receipt ref escapes output root")
    if not candidate.is_file() or candidate.is_symlink():
        raise ValueError(f"semantic preflight receipt is missing: {candidate}")
    return candidate


def bind_semantic_preflight_receipt(
    receipt_path: Path,
    *,
    semantic_selection_id: str,
    output_root: Path = paths.OUTPUT_ROOT,
    require_fresh: bool = True,
) -> dict[str, str]:
    root = output_root.expanduser().resolve()
    path = receipt_path.expanduser().resolve()
    if not path.is_relative_to(root):
        raise ValueError("semantic preflight receipt must be under the output root")
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"semantic preflight receipt is missing: {path}")
    receipt = read_json(path)
    if not isinstance(receipt, Mapping):
        raise TypeError("semantic preflight receipt must be an object")
    selection = resolve_semantic_preflight_selection(semantic_selection_id)
    validate_semantic_preflight_receipt(
        receipt,
        expected_selection=selection,
        require_semantic_execution_ready=require_fresh,
    )
    binding = {
        "receiptRef": path.relative_to(root).as_posix(),
        "receiptFileSha256": file_sha256(path),
        "receiptId": str(receipt["receiptId"]),
        "selectionDigest": str(receipt["selectionDigest"]),
    }
    assert_valid(
        binding,
        "execution",
        "semantic_provider_preflight_receipt_ref",
        label=f"semantic preflight binding:{semantic_selection_id}",
    )
    return binding


def validate_semantic_preflight_binding(
    value: Mapping[str, Any],
    *,
    semantic_selection_id: str,
    output_root: Path = paths.OUTPUT_ROOT,
    require_fresh: bool = True,
) -> tuple[dict[str, Any], Path]:
    binding = dict(value)
    assert_valid(
        binding,
        "execution",
        "semantic_provider_preflight_receipt_ref",
        label=f"semantic preflight binding:{semantic_selection_id}",
    )
    path = _receipt_path(str(binding["receiptRef"]), output_root=output_root)
    if file_sha256(path) != binding["receiptFileSha256"]:
        raise ValueError("semantic preflight receipt file digest drift")
    receipt = read_json(path)
    if not isinstance(receipt, dict):
        raise TypeError("semantic preflight receipt must be an object")
    selection = resolve_semantic_preflight_selection(semantic_selection_id)
    validate_semantic_preflight_receipt(
        receipt,
        expected_selection=selection,
        require_semantic_execution_ready=require_fresh,
    )
    if not bool(receipt.get("semanticExecutionReady")):
        raise ValueError("semantic provider preflight is not execution-ready")
    if (
        receipt.get("receiptId") != binding["receiptId"]
        or receipt.get("selectionDigest") != binding["selectionDigest"]
    ):
        raise ValueError("semantic preflight receipt binding identity drift")
    return receipt, path


def _timestamp(value: object, *, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"semantic preflight {label} is invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"semantic preflight {label} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def validate_semantic_preflight_binding_at(
    value: Mapping[str, Any],
    *,
    semantic_selection_id: str,
    admitted_at: str,
    output_root: Path = paths.OUTPUT_ROOT,
) -> tuple[dict[str, Any], Path]:
    """Validate exact receipt identity at one immutable admission timestamp."""

    receipt, path = validate_semantic_preflight_binding(
        value,
        semantic_selection_id=semantic_selection_id,
        output_root=output_root,
        require_fresh=False,
    )
    frozen_at = _timestamp(admitted_at, label="admission timestamp")
    recorded_at = _timestamp(receipt["recordedAt"], label="recordedAt")
    valid_until = _timestamp(receipt["validUntil"], label="validUntil")
    if frozen_at < recorded_at or frozen_at > valid_until:
        raise ValueError(
            "semantic preflight admission timestamp is outside its validity window"
        )
    return receipt, path


def resolve_manifest_preflight_binding(
    *,
    existing_manifest: Mapping[str, Any] | None,
    requested_binding: Mapping[str, Any] | None,
    semantic_selection_id: str,
    output_root: Path = paths.OUTPUT_ROOT,
    require_requested_fresh: bool | None = None,
) -> dict[str, Any] | None:
    frozen = (
        dict(existing_manifest["semanticPreflightReceipt"])
        if isinstance(
            (existing_manifest or {}).get("semanticPreflightReceipt"),
            Mapping,
        )
        else None
    )
    if frozen is not None:
        validate_semantic_preflight_binding(
            frozen,
            semantic_selection_id=semantic_selection_id,
            output_root=output_root,
            require_fresh=False,
        )
    requested = dict(requested_binding) if requested_binding is not None else None
    if requested is not None:
        requested_fresh = (
            existing_manifest is None
            if require_requested_fresh is None
            else require_requested_fresh
        )
        validate_semantic_preflight_binding(
            requested,
            semantic_selection_id=semantic_selection_id,
            output_root=output_root,
            require_fresh=requested_fresh,
        )
    if frozen is not None and requested is not None and frozen != requested:
        raise ValueError(
            "resume may not change the frozen semantic preflight receipt; create retryOf"
        )
    selected = requested or frozen
    selection = resolve_semantic_preflight_selection(semantic_selection_id)
    if selection.provider.value == "cursor_sdk" and selected is None:
        raise ValueError(
            f"{semantic_selection_id} requires a fresh semantic preflight/soak receipt"
        )
    return selected


def resolve_cli_preflight_binding(
    *,
    existing_manifest: Mapping[str, Any] | None,
    requested_receipt_ref: str | None,
    semantic_selection_id: str,
    output_root: Path = paths.OUTPUT_ROOT,
) -> dict[str, Any] | None:
    requested_binding = None
    normalized_ref = str(requested_receipt_ref or "").strip()
    if normalized_ref:
        receipt_path = Path(normalized_ref).expanduser()
        if not receipt_path.is_absolute():
            receipt_path = output_root / receipt_path
        requested_binding = bind_semantic_preflight_receipt(
            receipt_path,
            semantic_selection_id=semantic_selection_id,
            output_root=output_root,
            require_fresh=existing_manifest is None,
        )
    return resolve_manifest_preflight_binding(
        existing_manifest=existing_manifest,
        requested_binding=requested_binding,
        semantic_selection_id=semantic_selection_id,
        output_root=output_root,
        require_requested_fresh=existing_manifest is None,
    )


__all__ = [
    "bind_semantic_preflight_receipt",
    "resolve_cli_preflight_binding",
    "resolve_manifest_preflight_binding",
    "validate_semantic_preflight_binding",
    "validate_semantic_preflight_binding_at",
]
