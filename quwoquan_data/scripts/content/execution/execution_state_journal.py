"""Crash-safe append-only journal behind the execution-state facade.

``execution_state.json`` remains the atomic current snapshot consumed by the
rest of Data.  This module adds a small head plus create-once delta events so a
controller restart can distinguish a committed update from a torn write.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.schema import assert_valid

EVENT_SCHEMA = "quwoquan.content.execution_state_event"
HEAD_SCHEMA = "quwoquan.content.execution_state_head"
ABSENT_SNAPSHOT_DIGEST = "absent"
_DIGEST_PREFIX = "sha256:"
_HISTORY_LIMITS = {
    "agentRunHistory": 20,
    "autoResearchRecoveryActions": 20,
    "controllerYieldRecoveryActions": 20,
    "manualRepairResumes": 20,
    "produceReviewRetryHistory": 50,
    "recoveryActions": 64,
    "schedulerRecoveryActions": 20,
    "workspaceCleanupReports": 20,
}


class ExecutionStateJournalError(ValueError):
    """The persisted journal cannot be proven complete and consistent."""


class StaleExecutionStateError(ExecutionStateJournalError):
    """A transition was opened from a snapshot that is no longer current."""


@dataclass(frozen=True, slots=True)
class ExecutionStateIdentity:
    sequence: int
    event_digest: str | None
    snapshot_digest: str


@dataclass(frozen=True, slots=True)
class LoadedExecutionState:
    payload: dict[str, Any]
    identity: ExecutionStateIdentity


def compact_execution_state(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Bound historical arrays while keeping current state and last* fields."""
    compacted = dict(payload)
    for field, limit in _HISTORY_LIMITS.items():
        value = compacted.get(field)
        if isinstance(value, list) and len(value) > limit:
            compacted[field] = value[-limit:]
    return compacted


def load_execution_state_document(
    state_path: Path,
    *,
    default_payload: Mapping[str, Any],
) -> LoadedExecutionState:
    """Load or deterministically recover one state under its execution lock."""
    with _execution_lock(state_path):
        loaded = _recover_locked(state_path)
        if loaded is not None:
            return loaded
        payload = compact_execution_state(default_payload)
        _validate_snapshot(payload, state_path)
        return LoadedExecutionState(
            payload=payload,
            identity=ExecutionStateIdentity(0, None, ABSENT_SNAPSHOT_DIGEST),
        )


def save_execution_state_document(
    state_path: Path,
    payload: Mapping[str, Any],
    *,
    expected: ExecutionStateIdentity | None,
) -> LoadedExecutionState:
    """Append a delta and atomically advance snapshot/head with CAS semantics."""
    if expected is None:
        raise StaleExecutionStateError(
            "execution state transition has no loaded snapshot identity; reload first"
        )
    next_payload = compact_execution_state(payload)
    _validate_snapshot(next_payload, state_path)
    with _execution_lock(state_path):
        current = _recover_locked(state_path)
        current_identity = (
            current.identity
            if current is not None
            else ExecutionStateIdentity(0, None, ABSENT_SNAPSHOT_DIGEST)
        )
        if current_identity != expected:
            raise StaleExecutionStateError(
                "execution state stale writer rejected: "
                f"expected={expected!r} current={current_identity!r}"
            )
        prior_payload = current.payload if current is not None else {}
        event = _build_event(
            execution_id=str(next_payload["executionId"]),
            sequence=current_identity.sequence + 1,
            previous_event_digest=current_identity.event_digest,
            previous_snapshot_digest=current_identity.snapshot_digest,
            prior_payload=prior_payload,
            next_payload=next_payload,
        )
        event_path = _event_path(state_path, int(event["sequence"]))
        _write_create_once_json(event_path, event)
        _atomic_write_json(state_path, next_payload)
        identity = ExecutionStateIdentity(
            sequence=int(event["sequence"]),
            event_digest=str(event["eventDigest"]),
            snapshot_digest=str(event["resultSnapshotDigest"]),
        )
        _write_head(state_path, identity)
        return LoadedExecutionState(payload=next_payload, identity=identity)


def verify_execution_state_journal(state_path: Path) -> ExecutionStateIdentity:
    """Perform the explicit O(events) audit, including every immutable link."""
    if not state_path.parent.is_dir():
        return ExecutionStateIdentity(0, None, ABSENT_SNAPSHOT_DIGEST)
    with _execution_lock(state_path):
        loaded = _recover_locked(state_path)
        if loaded is None:
            return ExecutionStateIdentity(0, None, ABSENT_SNAPSHOT_DIGEST)
        head = _read_head(state_path)
        if head is None:
            return loaded.identity
        sequence = int(head["sequence"])
        names = sorted(
            path.name
            for path in _events_dir(state_path).iterdir()
            if path.is_file()
        )
        expected_names = [f"{item:020d}.json" for item in range(1, sequence + 1)]
        if names != expected_names:
            raise ExecutionStateJournalError(
                "execution state event sequence has a gap or unbound file"
            )
        prior_event_digest: str | None = None
        prior_snapshot_digest: str | None = None
        materialized: dict[str, Any] | None = {}
        for item in range(1, sequence + 1):
            event = _read_event(
                _event_path(state_path, item),
                expected_sequence=item,
                expected_execution_id=state_path.parent.parent.name,
            )
            if event["previousEventDigest"] != prior_event_digest:
                raise ExecutionStateJournalError("execution state event digest chain drift")
            event_previous = str(event["previousSnapshotDigest"])
            if prior_snapshot_digest is not None and event_previous != prior_snapshot_digest:
                raise ExecutionStateJournalError("execution state snapshot digest chain drift")
            if item == 1 and event_previous != ABSENT_SNAPSHOT_DIGEST:
                materialized = None
            if materialized is not None:
                materialized = _apply_delta(materialized, event["stateDelta"])
                if _snapshot_digest(materialized) != event["resultSnapshotDigest"]:
                    raise ExecutionStateJournalError("execution state delta replay drift")
            prior_event_digest = str(event["eventDigest"])
            prior_snapshot_digest = str(event["resultSnapshotDigest"])
        if sequence and prior_event_digest != head["eventDigest"]:
            raise ExecutionStateJournalError("execution state head event digest drift")
        if loaded.identity.snapshot_digest != head["snapshotDigest"]:
            raise ExecutionStateJournalError("execution state head snapshot digest drift")
        return loaded.identity


def verify_execution_state_journal_for_execution(
    execution_id: str,
) -> ExecutionStateIdentity:
    """Resolve the canonical snapshot and run the explicit terminal-gate audit."""
    from content.execution.workspace import execution_state_path

    return verify_execution_state_journal(execution_state_path(execution_id))


@contextmanager
def _execution_lock(state_path: Path) -> Iterator[None]:
    lock_path = state_path.with_name("execution_state.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _events_dir(state_path: Path) -> Path:
    return state_path.with_name("execution_state_events")


def _head_path(state_path: Path) -> Path:
    return state_path.with_name("execution_state_head.json")


def _event_path(state_path: Path, sequence: int) -> Path:
    return _events_dir(state_path) / f"{sequence:020d}.json"


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _payload_digest(payload: Mapping[str, Any]) -> str:
    return _DIGEST_PREFIX + hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _snapshot_digest(payload: Mapping[str, Any]) -> str:
    return _payload_digest(payload)


def _event_digest(payload: Mapping[str, Any]) -> str:
    unsigned = {key: value for key, value in payload.items() if key != "eventDigest"}
    return _payload_digest(unsigned)


def _state_delta(
    prior_payload: Mapping[str, Any],
    next_payload: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "set": {
            key: value
            for key, value in next_payload.items()
            if key not in prior_payload or prior_payload[key] != value
        },
        "remove": sorted(set(prior_payload) - set(next_payload)),
    }


def _apply_delta(
    prior_payload: Mapping[str, Any],
    delta: object,
) -> dict[str, Any]:
    if not isinstance(delta, Mapping):
        raise ExecutionStateJournalError("execution state delta must be an object")
    raw_set = delta.get("set")
    raw_remove = delta.get("remove")
    if not isinstance(raw_set, Mapping) or not isinstance(raw_remove, list):
        raise ExecutionStateJournalError("execution state delta fields are invalid")
    if not all(isinstance(item, str) for item in raw_remove):
        raise ExecutionStateJournalError("execution state delta remove must be strings")
    result = dict(prior_payload)
    for field in raw_remove:
        result.pop(field, None)
    result.update(raw_set)
    return result


def _build_event(
    *,
    execution_id: str,
    sequence: int,
    previous_event_digest: str | None,
    previous_snapshot_digest: str,
    prior_payload: Mapping[str, Any],
    next_payload: Mapping[str, Any],
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "schema": EVENT_SCHEMA,
        "executionId": execution_id,
        "sequence": sequence,
        "previousEventDigest": previous_event_digest,
        "previousSnapshotDigest": previous_snapshot_digest,
        "resultSnapshotDigest": _snapshot_digest(next_payload),
        "createdAt": str(next_payload["updatedAt"]),
        "stateDelta": _state_delta(prior_payload, next_payload),
    }
    event["eventDigest"] = _event_digest(event)
    assert_valid(
        event,
        "execution",
        "execution_state_event",
        label=f"execution_state_event:{execution_id}:{sequence}",
    )
    return event


def _validate_snapshot(payload: Mapping[str, Any], state_path: Path) -> None:
    assert_valid(
        payload,
        "execution",
        "execution_state",
        label=f"execution_state:{state_path.parent.parent.name}",
    )
    if payload.get("executionId") != state_path.parent.parent.name:
        raise ExecutionStateJournalError("execution state snapshot identity drift")


def _read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExecutionStateJournalError(f"{label} is unreadable: {path}") from exc
    if not isinstance(payload, dict):
        raise ExecutionStateJournalError(f"{label} must be an object: {path}")
    return payload


def _read_event(
    path: Path,
    *,
    expected_sequence: int,
    expected_execution_id: str,
) -> dict[str, Any]:
    event = _read_json_object(path, label="execution state event")
    assert_valid(event, "execution", "execution_state_event", label=str(path))
    if event["sequence"] != expected_sequence:
        raise ExecutionStateJournalError("execution state event sequence drift")
    if event["executionId"] != expected_execution_id:
        raise ExecutionStateJournalError("execution state event identity drift")
    if event["eventDigest"] != _event_digest(event):
        raise ExecutionStateJournalError("execution state event payload digest drift")
    return event


def _read_head(state_path: Path) -> dict[str, Any] | None:
    path = _head_path(state_path)
    if not path.exists():
        return None
    head = _read_json_object(path, label="execution state head")
    assert_valid(head, "execution", "execution_state_head", label=str(path))
    if head["executionId"] != state_path.parent.parent.name:
        raise ExecutionStateJournalError("execution state head identity drift")
    return head


def _events_dir_mtime_ns(state_path: Path) -> int:
    directory = _events_dir(state_path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory.stat().st_mtime_ns


def _head_document(
    state_path: Path,
    identity: ExecutionStateIdentity,
) -> dict[str, Any]:
    return {
        "schema": HEAD_SCHEMA,
        "executionId": state_path.parent.parent.name,
        "sequence": identity.sequence,
        "eventDigest": identity.event_digest,
        "snapshotDigest": identity.snapshot_digest,
        "eventsDirectoryMtimeNs": _events_dir_mtime_ns(state_path),
    }


def _write_head(state_path: Path, identity: ExecutionStateIdentity) -> None:
    head = _head_document(state_path, identity)
    assert_valid(head, "execution", "execution_state_head", label=str(_head_path(state_path)))
    _atomic_write_json(_head_path(state_path), head)


def _load_snapshot(state_path: Path) -> dict[str, Any] | None:
    if not state_path.exists():
        return None
    payload = _read_json_object(state_path, label="execution state snapshot")
    _validate_snapshot(payload, state_path)
    return payload


def _recover_without_head(state_path: Path) -> LoadedExecutionState | None:
    snapshot = _load_snapshot(state_path)
    events_dir = _events_dir(state_path)
    if not events_dir.exists():
        if snapshot is None:
            return None
        return LoadedExecutionState(
            snapshot,
            ExecutionStateIdentity(0, None, _snapshot_digest(snapshot)),
        )
    if not events_dir.is_dir():
        raise ExecutionStateJournalError("execution state events path must be a directory")
    event_paths = sorted(path for path in events_dir.iterdir() if path.is_file())
    if not event_paths:
        if snapshot is None:
            return None
        identity = ExecutionStateIdentity(0, None, _snapshot_digest(snapshot))
        return LoadedExecutionState(snapshot, identity)
    if [path.name for path in event_paths] != ["00000000000000000001.json"]:
        raise ExecutionStateJournalError("execution state journal has no head and a broken sequence")
    event = _read_event(
        event_paths[0],
        expected_sequence=1,
        expected_execution_id=state_path.parent.parent.name,
    )
    current_digest = (
        _snapshot_digest(snapshot) if snapshot is not None else ABSENT_SNAPSHOT_DIGEST
    )
    if current_digest == event["resultSnapshotDigest"]:
        assert snapshot is not None
        recovered = snapshot
    elif current_digest == event["previousSnapshotDigest"]:
        recovered = _apply_delta(snapshot or {}, event["stateDelta"])
        _validate_snapshot(recovered, state_path)
        if _snapshot_digest(recovered) != event["resultSnapshotDigest"]:
            raise ExecutionStateJournalError("execution state pending delta digest drift")
        _atomic_write_json(state_path, recovered)
    else:
        raise ExecutionStateJournalError("execution state snapshot is not bound to pending event")
    identity = ExecutionStateIdentity(
        1,
        str(event["eventDigest"]),
        str(event["resultSnapshotDigest"]),
    )
    _write_head(state_path, identity)
    return LoadedExecutionState(recovered, identity)


def _recover_locked(state_path: Path) -> LoadedExecutionState | None:
    head = _read_head(state_path)
    if head is None:
        return _recover_without_head(state_path)
    sequence = int(head["sequence"])
    event_digest = head["eventDigest"]
    snapshot_digest = str(head["snapshotDigest"])
    if sequence == 0 and event_digest is not None:
        raise ExecutionStateJournalError("execution state genesis head cannot bind an event")
    if sequence > 0:
        current_event = _read_event(
            _event_path(state_path, sequence),
            expected_sequence=sequence,
            expected_execution_id=state_path.parent.parent.name,
        )
        if current_event["eventDigest"] != event_digest:
            raise ExecutionStateJournalError("execution state head event digest drift")
        if current_event["resultSnapshotDigest"] != snapshot_digest:
            raise ExecutionStateJournalError("execution state head result digest drift")
    snapshot = _load_snapshot(state_path)
    if snapshot is None:
        raise ExecutionStateJournalError("execution state head exists without snapshot")
    current_identity = ExecutionStateIdentity(sequence, event_digest, snapshot_digest)
    while True:
        pending_path = _event_path(state_path, current_identity.sequence + 1)
        if not pending_path.exists():
            break
        pending = _read_event(
            pending_path,
            expected_sequence=current_identity.sequence + 1,
            expected_execution_id=state_path.parent.parent.name,
        )
        if pending["previousEventDigest"] != current_identity.event_digest:
            raise ExecutionStateJournalError("execution state pending event chain drift")
        if pending["previousSnapshotDigest"] != current_identity.snapshot_digest:
            raise ExecutionStateJournalError("execution state pending snapshot chain drift")
        actual_snapshot_digest = _snapshot_digest(snapshot)
        if actual_snapshot_digest == pending["previousSnapshotDigest"]:
            snapshot = _apply_delta(snapshot, pending["stateDelta"])
            _validate_snapshot(snapshot, state_path)
            if _snapshot_digest(snapshot) != pending["resultSnapshotDigest"]:
                raise ExecutionStateJournalError("execution state pending delta replay drift")
            _atomic_write_json(state_path, snapshot)
        elif actual_snapshot_digest != pending["resultSnapshotDigest"]:
            raise ExecutionStateJournalError("execution state torn snapshot is unbound")
        current_identity = ExecutionStateIdentity(
            int(pending["sequence"]),
            str(pending["eventDigest"]),
            str(pending["resultSnapshotDigest"]),
        )
        _write_head(state_path, current_identity)
    if _snapshot_digest(snapshot) != current_identity.snapshot_digest:
        raise ExecutionStateJournalError("execution state snapshot digest drift")
    if int(head["eventsDirectoryMtimeNs"]) != _events_dir_mtime_ns(state_path):
        refreshed_head = _read_head(state_path)
        if refreshed_head is None or int(refreshed_head["sequence"]) == sequence:
            raise ExecutionStateJournalError(
                "execution state events directory changed without a contiguous event"
            )
    return LoadedExecutionState(snapshot, current_identity)


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            handle.write(_json_bytes(payload))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def _write_create_once_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(_json_bytes(payload))
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(descriptor)
    _fsync_directory(path.parent)


__all__ = [
    "ExecutionStateIdentity",
    "ExecutionStateJournalError",
    "LoadedExecutionState",
    "StaleExecutionStateError",
    "compact_execution_state",
    "load_execution_state_document",
    "save_execution_state_document",
    "verify_execution_state_journal",
    "verify_execution_state_journal_for_execution",
]
