"""Fail-closed terminal evidence consumed by global historical-output gates."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from core.io import read_json
from core.schema import assert_valid

from content.execution.execution_state_journal import verify_execution_state_journal
from content.execution.execution_supersession import (
    load_execution_supersession_receipt,
)
from content.execution.terminal_state_integrity import verify_terminal_state_integrity


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class TerminalExecutionEvidence:
    decision: str
    receipt: dict[str, Any]
    path: Path


def _load_stale_receipt(
    execution_root: Path,
) -> tuple[dict[str, Any], Path] | None:
    candidates = sorted(
        (execution_root / "_shared/reconciliation").glob("stale-*.json")
    )
    if not candidates:
        return None
    if len(candidates) != 1:
        raise ValueError("execution has multiple stale reconciliation receipts")
    path = candidates[0]
    receipt = read_json(path)
    if not isinstance(receipt, dict):
        raise TypeError("execution reconciliation receipt must be an object")
    assert_valid(
        receipt,
        "execution",
        "execution_reconciliation_receipt",
        label=f"execution reconciliation receipt:{path}",
    )
    stable = {key: value for key, value in receipt.items() if key != "receiptDigest"}
    if receipt["receiptDigest"] != _digest(stable):
        raise ValueError("execution reconciliation receipt digest drift")
    if receipt["executionId"] != execution_root.name:
        raise ValueError("execution reconciliation executionId drift")
    previous_state = receipt["previousState"]
    if not isinstance(previous_state, Mapping):
        raise TypeError("execution reconciliation previousState must be an object")
    previous_digest = str(receipt["previousStateDigest"])
    if previous_digest != _digest(previous_state):
        raise ValueError("execution reconciliation previousState digest drift")
    lease = receipt["controllerLease"]
    expected_lease_digest = _digest(lease) if isinstance(lease, Mapping) else None
    if receipt["controllerLeaseDigest"] != expected_lease_digest:
        raise ValueError("execution reconciliation controller lease digest drift")
    expected_name = f"stale-{previous_digest.removeprefix('sha256:')}.json"
    if path.name != expected_name:
        raise ValueError("execution reconciliation receipt path drift")
    state_path = execution_root / "_shared/execution_state.json"
    state = read_json(state_path)
    if not isinstance(state, dict) or state.get("status") != "interrupted":
        raise ValueError("stale reconciliation lacks terminal execution state")
    if state.get("executionId") != execution_root.name:
        raise ValueError("stale reconciliation terminal state identity drift")
    reason = state.get("interruptReason")
    expected_ref = path.relative_to(execution_root).as_posix()
    if not isinstance(reason, Mapping) or reason.get("receiptRef") != expected_ref:
        raise ValueError(
            "terminal execution state does not bind reconciliation receipt"
        )
    if reason.get("code") != receipt["errorCode"]:
        raise ValueError("terminal execution state errorCode drift")
    expected_recovery = [
        *(previous_state.get("recoveryActions") or []),
        {
            "action": "stale_execution_reconciled",
            "receiptRef": expected_ref,
            "receiptDigest": str(receipt["receiptDigest"]),
            "at": str(receipt["observedAt"]),
        },
    ]
    expected_changes = {
        "status": "interrupted",
        "interruptReason": {
            "code": str(receipt["errorCode"]),
            "receiptRef": expected_ref,
        },
        "nextAction": "create a new execution with retryOf; never resume this generation",
        "activeAgentScheduler": None,
        "activeAutoResearch": None,
        "heartbeatAt": str(receipt["observedAt"]),
        "recoveryActions": expected_recovery,
    }
    for field, expected in expected_changes.items():
        if state.get(field) != expected:
            raise ValueError(f"stale reconciliation terminal state {field} drift")
    if set(state) != set(previous_state):
        raise ValueError("stale reconciliation terminal state field-set drift")
    allowed_changes = {*expected_changes, "updatedAt"}
    for field in set(state) - allowed_changes:
        if state[field] != previous_state[field]:
            raise ValueError(f"stale reconciliation protected field drift: {field}")
    try:
        observed_at = datetime.fromisoformat(
            str(receipt["observedAt"]).replace("Z", "+00:00")
        )
        updated_at = datetime.fromisoformat(
            str(state["updatedAt"]).replace("Z", "+00:00")
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("stale reconciliation terminal timestamp is invalid") from exc
    if updated_at < observed_at:
        raise ValueError("stale reconciliation terminal updatedAt precedes observation")
    return receipt, path


def load_terminal_execution_evidence(
    execution_root: Path,
) -> TerminalExecutionEvidence | None:
    """Return only cryptographically bound non-resumable historical evidence."""
    stale = _load_stale_receipt(execution_root)
    supersession = load_execution_supersession_receipt(execution_root)
    if stale is not None and supersession is not None:
        raise ValueError("execution has conflicting terminal evidence")
    if stale is not None:
        verify_terminal_state_integrity(
            execution_root / "_shared" / "execution_state.json"
        )
        return TerminalExecutionEvidence("interrupted", stale[0], stale[1])
    if supersession is not None:
        verify_terminal_state_integrity(
            execution_root / "_shared" / "execution_state.json",
            allow_missing=True,
        )
        return TerminalExecutionEvidence("superseded", supersession[0], supersession[1])
    verify_execution_state_journal(execution_root / "_shared" / "execution_state.json")
    return None


__all__ = ["TerminalExecutionEvidence", "load_terminal_execution_evidence"]
