"""Operational governance contracts for company-style data production.

This module is intentionally small and file-backed.  It gives the workflow a
single execution controller, explicit assignment ownership, source-unit atomicity
checks, and auditable failure/conflict ledgers without introducing a second
runtime service.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from core.io import read_json, write_json
from core.paths import execution_root, now_iso
from core.runtime_policy import active_runtime_policy

CONTROLLER_LEASE_SCHEMA = "quwoquan_data.controller_lease"
RUNTIME_PROTECTION_SCHEMA = "quwoquan_data.runtime_protection"
ASSIGNMENT_SCHEMA = "quwoquan_data.assignment"
ASSIGNMENT_STATE_SCHEMA = "quwoquan_data.assignment_state"
ASSIGNMENT_EVENT_SCHEMA = "quwoquan_data.assignment_event"
CONFLICT_LEDGER_SCHEMA = "quwoquan_data.conflict_ledger"
FAILURE_LEDGER_SCHEMA = "quwoquan_data.failure_ledger"
QUALITY_TARGET_REPORT_SCHEMA = "quwoquan_data.quality_target_report"

_RUNTIME_POLICY = active_runtime_policy()
DEFAULT_CONTROLLER_STALE_SECONDS = _RUNTIME_POLICY.controller_lease_stale_seconds
DEFAULT_ASSIGNMENT_DEADLINE_SECONDS = _RUNTIME_POLICY.assignment_deadline_seconds

FAILURE_INFRA_RETRY = "retry.infra"
FAILURE_DATA_RETRY = "retry.data"
FAILURE_QUALITY_REPAIR = "repair.quality"
FAILURE_ABANDON = "abandon"
FAILURE_CONFLICT = "conflict"
FAILURE_GATE_BLOCK = "blocked.gate"
FAILURE_MANUAL_REVIEW = "manual_review"

FINAL_FAILURE_CATEGORIES = {
    FAILURE_INFRA_RETRY,
    FAILURE_DATA_RETRY,
    FAILURE_QUALITY_REPAIR,
    FAILURE_ABANDON,
    FAILURE_CONFLICT,
    FAILURE_GATE_BLOCK,
    FAILURE_MANUAL_REVIEW,
}


def _shared_dir(execution_id: str, *, create: bool = True) -> Path:
    path = execution_root(execution_id) / "_shared"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path

def controller_lease_path(execution_id: str, *, create: bool = False) -> Path:
    return _shared_dir(execution_id, create=create) / "controller_lease.json"

def controller_lease_lock_path(execution_id: str) -> Path:
    return _shared_dir(execution_id) / "controller_lease.lock"

def assignment_state_path(execution_id: str) -> Path:
    return _shared_dir(execution_id) / "assignment_state.json"

def assignment_events_path(execution_id: str) -> Path:
    return _shared_dir(execution_id) / "assignment_events.jsonl"

def conflict_ledger_path(execution_id: str) -> Path:
    return _shared_dir(execution_id) / "conflict_ledger.jsonl"

def failure_ledger_path(execution_id: str) -> Path:
    return _shared_dir(execution_id) / "failure_ledger.jsonl"

def quality_target_report_path(execution_id: str) -> Path:
    return _shared_dir(execution_id) / "quality_target_report.json"

def runtime_protection_manifest_path(execution_id: str, *, create: bool = False) -> Path:
    return _shared_dir(execution_id, create=create) / "runtime_protection.json"

def _now_epoch() -> float:
    return time.time()

def _parse_iso_seconds(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None

def pid_alive(pid: object) -> bool:
    try:
        value = int(pid or 0)
    except (TypeError, ValueError):
        return False
    if value <= 0:
        return False
    try:
        os.kill(value, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True

def new_controller_run_id(execution_id: str, *, pid: int | None = None) -> str:
    seed = f"{execution_id}|{execution_id}|{pid or os.getpid()}|{socket.gethostname()}|{now_iso()}|{time.monotonic_ns()}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]

def read_controller_lease(execution_id: str) -> dict[str, Any] | None:
    path = controller_lease_path(execution_id, create=False)
    if not path.is_file():
        return None
    data = read_json(path)
    return data if isinstance(data, dict) else None

def controller_lease_active(
    lease: Mapping[str, Any] | None,
    *,
    current_pid: int | None = None,
    stale_seconds: int = DEFAULT_CONTROLLER_STALE_SECONDS,
) -> bool:
    if not isinstance(lease, Mapping):
        return False
    if str(lease.get("status") or "active") != "active":
        return False
    pid = int(lease.get("pid") or 0)
    if current_pid is not None and pid == current_pid:
        return False
    if pid_alive(pid):
        return True
    heartbeat = _parse_iso_seconds(lease.get("heartbeatAt") or lease.get("startedAt"))
    return heartbeat is not None and (_now_epoch() - heartbeat) < stale_seconds and not pid

def active_controller_issue(
    execution_id: str,
    *,
    current_pid: int | None = None,
    stale_seconds: int = DEFAULT_CONTROLLER_STALE_SECONDS,
) -> str | None:
    lease = read_controller_lease(execution_id)
    if not controller_lease_active(lease, current_pid=current_pid, stale_seconds=stale_seconds):
        return None
    owner = dict(lease or {})
    return (
        "GATE_BLOCK controller lease active for execution: "
        f"controllerRunId={owner.get('controllerRunId')} pid={owner.get('pid')} "
        f"hostname={owner.get('hostname')} startedAt={owner.get('startedAt')}"
    )

@contextmanager
def controller_lease(
    execution_id: str,
    *,
    role: str = "execution_controller",
    stale_seconds: int = DEFAULT_CONTROLLER_STALE_SECONDS,
):
    """Acquire the only active controller lease for one execution."""

    try:
        import fcntl  # type: ignore
    except Exception:  # noqa: BLE001
        fcntl = None  # type: ignore

    lock_path = controller_lease_lock_path(execution_id)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    run_id = new_controller_run_id(execution_id)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        if fcntl is not None:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                issue = active_controller_issue(execution_id, stale_seconds=stale_seconds)
                raise RuntimeError(
                    issue
                    or "GATE_BLOCK controller lease lock held for execution; refusing to wait"
                ) from exc
        issue = active_controller_issue(execution_id, stale_seconds=stale_seconds)
        if issue:
            raise RuntimeError(issue)
        now = now_iso()
        lease = {
            "schema": CONTROLLER_LEASE_SCHEMA,
            "status": "active",
            "role": role,
            "executionId": execution_id,
            "controllerRunId": run_id,
            "pid": os.getpid(),
            "pgid": os.getpgrp(),
            "hostname": socket.gethostname(),
            "startedAt": now,
            "heartbeatAt": now,
            "expiresAfterSeconds": stale_seconds,
        }
        write_json(controller_lease_path(execution_id, create=True), lease)
        try:
            yield lease
        finally:
            current = read_controller_lease(execution_id) or {}
            if str(current.get("controllerRunId") or "") == run_id:
                released = dict(current)
                released["status"] = "released"
                released["releasedAt"] = now_iso()
                released["heartbeatAt"] = released["releasedAt"]
                write_json(controller_lease_path(execution_id, create=True), released)

def heartbeat_controller_lease(execution_id: str, controller_run_id: str) -> None:
    lease = read_controller_lease(execution_id)
    if not lease or str(lease.get("controllerRunId") or "") != str(controller_run_id):
        return
    lease["heartbeatAt"] = now_iso()
    write_json(controller_lease_path(execution_id, create=True), lease)
