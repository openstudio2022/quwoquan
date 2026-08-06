"""Bind a fresh semantic preflight receipt into immutable execution identity."""
from __future__ import annotations

from collections.abc import Mapping
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
        require_execution_admission=True,
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
        "semantic_preflight_receipt_ref",
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
        "semantic_preflight_receipt_ref",
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
        require_execution_admission=require_fresh,
    )
    if not bool(receipt.get("executionAdmissionReady")):
        raise ValueError("semantic preflight receipt is not execution-admission ready")
    if (
        receipt.get("receiptId") != binding["receiptId"]
        or receipt.get("selectionDigest") != binding["selectionDigest"]
    ):
        raise ValueError("semantic preflight receipt binding identity drift")
    return receipt, path


def resolve_manifest_preflight_binding(
    *,
    existing_manifest: Mapping[str, Any] | None,
    requested_binding: Mapping[str, Any] | None,
    semantic_selection_id: str,
    output_root: Path = paths.OUTPUT_ROOT,
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
        validate_semantic_preflight_binding(
            requested,
            semantic_selection_id=semantic_selection_id,
            output_root=output_root,
            require_fresh=existing_manifest is None,
        )
    if frozen is not None and requested is not None and frozen != requested:
        raise ValueError(
            "resume may not change the frozen semantic preflight receipt; create retryOf"
        )
    selected = requested or frozen
    if semantic_selection_id == "cursor_auto" and selected is None:
        raise ValueError(
            "cursor_auto requires a fresh semantic preflight/soak receipt"
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
        )
    return resolve_manifest_preflight_binding(
        existing_manifest=existing_manifest,
        requested_binding=requested_binding,
        semantic_selection_id=semantic_selection_id,
        output_root=output_root,
    )


__all__ = [
    "bind_semantic_preflight_receipt",
    "resolve_cli_preflight_binding",
    "resolve_manifest_preflight_binding",
    "validate_semantic_preflight_binding",
]
