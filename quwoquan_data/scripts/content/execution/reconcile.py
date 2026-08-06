"""Audited reconciliation for orphaned execution controller snapshots."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import socket
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.control_types import ExecutionStateStatus
from core.io import read_json, write_json
from core.schema import assert_valid

from content.execution.context import load_execution_state, save_execution_state
from content.execution.execution_state_journal import verify_execution_state_journal
from content.execution.identity import validate_execution_id
from content.execution.workspace import execution_root

_ELIGIBLE = {
    ExecutionStateStatus.RUNNING,
    ExecutionStateStatus.WAITING_AGENT,
    ExecutionStateStatus.REPAIRING,
}


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _age_seconds(value: object) -> float:
    text = str(value or "").strip()
    if not text:
        return float("inf")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds())


def _process_alive(pid: int | None) -> bool:
    if pid is None or pid <= 1:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _process_group_alive(pgid: int | None) -> bool:
    if pgid is None or pgid <= 1:
        return False
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _optional_positive_int(value: object) -> int | None:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 1 else None


@contextmanager
def _reconciliation_lock(root: Path) -> Iterator[None]:
    path = root / "_shared" / "reconciliation" / ".lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _validated_receipt(path: Path) -> dict[str, Any]:
    receipt = read_json(path)
    assert_valid(
        receipt,
        "execution",
        "execution_reconciliation_receipt",
        label=f"execution reconciliation receipt:{path}",
    )
    stable = {key: value for key, value in receipt.items() if key != "receiptDigest"}
    if receipt.get("receiptDigest") != _digest(stable):
        raise ValueError(f"execution reconciliation receipt digest drift: {path}")
    return receipt


def reconcile_stale_execution(
    execution_id: str,
    *,
    min_stale_seconds: int = 1800,
) -> tuple[dict[str, Any], Path]:
    """Mark a provably orphaned snapshot interrupted without deleting evidence."""

    normalized = validate_execution_id(execution_id)
    root = execution_root(normalized)
    if min_stale_seconds < 60:
        raise ValueError("min_stale_seconds must be at least 60")
    if not root.is_dir():
        raise FileNotFoundError(f"execution root is missing: {root}")
    with _reconciliation_lock(root):
        state = load_execution_state(normalized)
        verify_execution_state_journal(
            root / "_shared" / "execution_state.json"
        )
        receipts_root = root / "_shared" / "reconciliation"
        if state.status is ExecutionStateStatus.INTERRUPTED:
            candidates = sorted(receipts_root.glob("stale-*.json"))
            if not candidates:
                raise ValueError("interrupted execution lacks reconciliation receipt")
            path = candidates[-1]
            return _validated_receipt(path), path
        if state.status not in _ELIGIBLE:
            raise ValueError(
                f"execution status is not stale-reconcilable: {state.status.value}"
            )
        state_payload = state.to_dict()
        if _age_seconds(state_payload.get("heartbeatAt")) < min_stale_seconds:
            raise ValueError("execution heartbeat is not stale")

        lease_path = root / "_shared" / "controller_lease.json"
        lease = read_json(lease_path) if lease_path.is_file() else None
        if lease is not None and not isinstance(lease, dict):
            raise ValueError("controller lease must be an object")
        local_hostname = socket.gethostname()
        if lease and str(lease.get("status") or "") == "active":
            owner_hostname = str(lease.get("hostname") or "").strip()
            if owner_hostname and owner_hostname != local_hostname:
                raise ValueError(
                    "active controller lease belongs to another host; absence cannot be proven"
                )
            expiry = max(
                min_stale_seconds,
                int(lease.get("expiresAfterSeconds") or min_stale_seconds),
            )
            if _age_seconds(lease.get("heartbeatAt")) < expiry:
                raise ValueError("controller lease is not stale")

        controller = state_payload.get("controller")
        controller_row = controller if isinstance(controller, Mapping) else {}
        pid = _optional_positive_int(
            (lease or {}).get("pid") or controller_row.get("pid")
        )
        pgid = _optional_positive_int((lease or {}).get("pgid"))
        pid_alive = _process_alive(pid)
        group_alive = _process_group_alive(pgid)
        if pid_alive or group_alive:
            raise ValueError(
                "execution controller/process group is still alive; reconciliation refused"
            )
        previous_state_digest = _digest(state_payload)
        receipt_path = receipts_root / (
            f"stale-{previous_state_digest.removeprefix('sha256:')}.json"
        )
        if receipt_path.is_file():
            receipt = _validated_receipt(receipt_path)
            if receipt.get("previousStateDigest") != previous_state_digest:
                raise ValueError("execution reconciliation receipt/state collision")
        else:
            stable = {
                "schema": "quwoquan_data.execution_reconciliation_receipt",
                "executionId": normalized,
                "decision": "interrupted",
                "errorCode": "DATA.CAMPAIGN.STALE_EXECUTION_RECONCILED",
                "observedAt": _now(),
                "previousStateDigest": previous_state_digest,
                "previousState": state_payload,
                "controllerLeaseDigest": _digest(lease) if lease else None,
                "controllerLease": lease,
                "processEvidence": {
                    "hostname": local_hostname,
                    "pid": pid,
                    "pgid": pgid,
                    "pidAlive": False,
                    "processGroupAlive": False,
                },
                "retryPolicy": "new_execution_with_retryOf",
            }
            receipt = {**stable, "receiptDigest": _digest(stable)}
            assert_valid(
                receipt,
                "execution",
                "execution_reconciliation_receipt",
                label=f"execution reconciliation receipt:{normalized}",
            )
            write_json(receipt_path, receipt)

        relative_receipt = receipt_path.relative_to(root).as_posix()
        state.status = ExecutionStateStatus.INTERRUPTED
        state.interrupt_reason = {
            "code": "DATA.CAMPAIGN.STALE_EXECUTION_RECONCILED",
            "receiptRef": relative_receipt,
        }
        state.next_action = "create a new execution with retryOf; never resume this generation"
        state.active_agent_scheduler = None
        state.active_auto_research = None
        state.heartbeat_at = str(receipt["observedAt"])
        state.recovery_actions.append(
            {
                "action": "stale_execution_reconciled",
                "receiptRef": relative_receipt,
                "receiptDigest": str(receipt["receiptDigest"]),
                "at": str(receipt["observedAt"]),
            }
        )
        save_execution_state(state)
        return receipt, receipt_path


def _handle(args: argparse.Namespace) -> None:
    receipt, path = reconcile_stale_execution(
        args.execution_id,
        min_stale_seconds=int(args.min_stale_seconds),
    )
    # The immutable receipt deliberately retains the exact pre-reconciliation
    # snapshot.  Do not echo that potentially large evidence blob to the CLI;
    # callers only need the stable identity and process proof needed to locate
    # and verify it.
    summary = {
        "executionId": receipt["executionId"],
        "decision": receipt["decision"],
        "errorCode": receipt["errorCode"],
        "observedAt": receipt["observedAt"],
        "previousStateDigest": receipt["previousStateDigest"],
        "processEvidence": receipt["processEvidence"],
        "receiptDigest": receipt["receiptDigest"],
        "receiptRef": str(path),
    }
    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        )
    )


def register_reconcile_stale_parser(
    subparsers: argparse._SubParsersAction,
) -> None:
    parser = subparsers.add_parser(
        "reconcile-stale",
        help="以 create-once receipt 收敛无存活进程的陈旧 execution",
    )
    parser.add_argument("execution_id")
    parser.add_argument("--min-stale-seconds", type=int, default=1800)
    parser.set_defaults(handler=_handle)


__all__ = ["reconcile_stale_execution", "register_reconcile_stale_parser"]
