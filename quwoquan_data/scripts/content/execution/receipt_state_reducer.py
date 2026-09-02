"""Derive the only execution-state projection from immutable stage receipts."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from content.execution.execution_state_journal import (
    ExecutionStateIdentity,
    LoadedExecutionState,
    load_execution_state_document,
    save_execution_state_document,
)
from content.execution.stage_receipt import list_receipt_files, load_receipt, receipt_state_status
from content.execution.workspace import execution_state_path
from core.schema import assert_valid

STATE_SCHEMA = "quwoquan.content.execution_state_projection"


def reduce_receipt_projection(execution_id: str) -> Path:
    entries = list_receipt_files(execution_id)
    if not entries:
        raise ValueError("receipt reducer requires at least one stage receipt")
    completed: list[str] = []
    latest: dict[str, Any] | None = None
    latest_path: Path | None = None
    for sequence, stage, path in entries:
        from content.execution.stage_authority import validate_stage_receipt_authority

        receipt = validate_stage_receipt_authority(execution_id, path)
        if receipt.get("executionId") != execution_id or receipt.get("sequence") != sequence or receipt.get("stage") != stage:
            raise ValueError(f"stage receipt identity drift: {path}")
        if receipt.get("verdict") == "pass" and stage not in completed:
            completed.append(stage)
        latest, latest_path = receipt, path
    assert latest is not None and latest_path is not None
    projection = {
        "schema": STATE_SCHEMA,
        "executionId": execution_id,
        "completed": completed,
        "status": receipt_state_status(latest).value,
        "latestStage": str(latest["stage"]),
        "next": str(latest["next"]),
        "latestReceiptRef": f"_shared/receipts/{latest_path.name}",
        "latestReceiptDigest": "sha256:" + hashlib.sha256(latest_path.read_bytes()).hexdigest(),
        "updatedAt": str(latest["recordedAt"]),
    }
    assert_valid(projection, "execution", "execution_state", label=f"receipt projection:{execution_id}")
    state_path = execution_state_path(execution_id)
    loaded = load_execution_state_document(state_path, default_payload=projection)
    if loaded.payload == projection and loaded.identity.sequence > 0:
        return state_path
    expected = (
        loaded.identity
        if loaded.identity.sequence > 0
        else ExecutionStateIdentity(0, None, "absent")
    )
    try:
        saved = _write_receipt_projection(
            state_path=state_path,
            projection=projection,
            expected=expected,
        )
    except Exception:
        # Receipt create-once 先成功；projection 撕裂不应让 immutable receipt
        # 变成不可重放。下一次 stage-close 或显式 reducer replay 会确定性修复。
        if state_path.is_file():
            try:
                state = load_execution_state_document(
                    state_path, default_payload=projection
                )
            except Exception:
                raise
            if state.payload == projection:
                return state_path
        raise
    if saved.payload != projection:
        raise ValueError("receipt projection persistence drift")
    return state_path


def _write_receipt_projection(
    *,
    state_path: Path,
    projection: dict[str, Any],
    expected: ExecutionStateIdentity,
) -> LoadedExecutionState:
    """The single auditable writer gate for the receipt-derived projection."""
    return save_execution_state_document(state_path, projection, expected=expected)


__all__ = ["STATE_SCHEMA", "reduce_receipt_projection"]
