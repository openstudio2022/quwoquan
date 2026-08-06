"""Schema-independent integrity audit for immutable terminal executions.

Historical execution snapshots retain the schema that was current when they
were terminalized.  Global repository gates must verify their bytes and any
append-only journal without reinterpreting those bytes through today's runtime
schema.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.schema import assert_valid

_ABSENT = "absent"


class TerminalStateIntegrityError(ValueError):
    """Historical terminal state or its journal is not byte-consistent."""


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TerminalStateIntegrityError(f"{label} is unreadable: {path}") from exc
    if not isinstance(value, dict):
        raise TerminalStateIntegrityError(f"{label} must be an object: {path}")
    return value


def _apply_delta(payload: Mapping[str, Any], delta: object) -> dict[str, Any]:
    if not isinstance(delta, Mapping):
        raise TerminalStateIntegrityError("execution state delta must be an object")
    fields = delta.get("set")
    removed = delta.get("remove")
    if not isinstance(fields, Mapping) or not isinstance(removed, list):
        raise TerminalStateIntegrityError("execution state delta fields are invalid")
    if not all(isinstance(field, str) for field in removed):
        raise TerminalStateIntegrityError(
            "execution state delta remove must be strings"
        )
    result = dict(payload)
    for field in removed:
        result.pop(field, None)
    result.update(fields)
    return result


def verify_terminal_state_integrity(
    state_path: Path,
    *,
    allow_missing: bool = False,
) -> None:
    """Verify raw snapshot identity and every existing journal digest link.

    This deliberately does not validate the snapshot with the current
    ``execution_state`` schema.  A valid create-once terminal receipt owns the
    historical interpretation; this audit owns byte identity and journal
    completeness only.
    """

    execution_id = state_path.parent.parent.name
    lock_path = state_path.with_name("execution_state.lock")
    descriptor = os.open(lock_path, os.O_RDONLY) if lock_path.is_file() else None
    try:
        if descriptor is not None:
            fcntl.flock(descriptor, fcntl.LOCK_SH)
        head_path = state_path.with_name("execution_state_head.json")
        events_dir = state_path.with_name("execution_state_events")
        if not state_path.is_file():
            event_files = tuple(events_dir.iterdir()) if events_dir.is_dir() else ()
            if allow_missing and not head_path.exists() and not event_files:
                return
            raise TerminalStateIntegrityError(
                f"terminal execution state is missing: {state_path}"
            )
        snapshot = _read_object(state_path, label="terminal execution state")
        if snapshot.get("executionId") != execution_id:
            raise TerminalStateIntegrityError("terminal execution state identity drift")

        if not head_path.exists():
            event_files = tuple(events_dir.iterdir()) if events_dir.is_dir() else ()
            if event_files:
                raise TerminalStateIntegrityError(
                    "terminal execution journal has events without a committed head"
                )
            return

        head = _read_object(head_path, label="execution state head")
        assert_valid(head, "execution", "execution_state_head", label=str(head_path))
        if head["executionId"] != execution_id:
            raise TerminalStateIntegrityError("execution state head identity drift")
        if not events_dir.is_dir():
            raise TerminalStateIntegrityError(
                "execution state journal directory is missing"
            )

        sequence = int(head["sequence"])
        paths = sorted(path for path in events_dir.iterdir() if path.is_file())
        expected_names = [f"{item:020d}.json" for item in range(1, sequence + 1)]
        if [path.name for path in paths] != expected_names:
            raise TerminalStateIntegrityError(
                "execution state event sequence has a gap or unbound file"
            )
        prior_event_digest: str | None = None
        prior_snapshot_digest: str | None = None
        materialized: dict[str, Any] | None = {}
        for item, path in enumerate(paths, start=1):
            event = _read_object(path, label="execution state event")
            assert_valid(event, "execution", "execution_state_event", label=str(path))
            unsigned = {
                key: value for key, value in event.items() if key != "eventDigest"
            }
            if event["eventDigest"] != _digest(unsigned):
                raise TerminalStateIntegrityError(
                    "execution state event payload digest drift"
                )
            if event["executionId"] != execution_id or event["sequence"] != item:
                raise TerminalStateIntegrityError(
                    "execution state event identity drift"
                )
            if event["previousEventDigest"] != prior_event_digest:
                raise TerminalStateIntegrityError(
                    "execution state event digest chain drift"
                )
            previous = str(event["previousSnapshotDigest"])
            if prior_snapshot_digest is not None and previous != prior_snapshot_digest:
                raise TerminalStateIntegrityError(
                    "execution state snapshot digest chain drift"
                )
            if item == 1 and previous != _ABSENT:
                materialized = None
            if materialized is not None:
                materialized = _apply_delta(materialized, event["stateDelta"])
                if _digest(materialized) != event["resultSnapshotDigest"]:
                    raise TerminalStateIntegrityError(
                        "execution state delta replay drift"
                    )
            prior_event_digest = str(event["eventDigest"])
            prior_snapshot_digest = str(event["resultSnapshotDigest"])

        if sequence == 0 and head["eventDigest"] is not None:
            raise TerminalStateIntegrityError(
                "execution state genesis head binds an event"
            )
        if prior_event_digest != head["eventDigest"]:
            raise TerminalStateIntegrityError("execution state head event digest drift")
        if _digest(snapshot) != head["snapshotDigest"]:
            raise TerminalStateIntegrityError("execution state snapshot digest drift")
        if (
            prior_snapshot_digest is not None
            and prior_snapshot_digest != head["snapshotDigest"]
        ):
            raise TerminalStateIntegrityError(
                "execution state head result digest drift"
            )
        if int(head["eventsDirectoryMtimeNs"]) != events_dir.stat().st_mtime_ns:
            raise TerminalStateIntegrityError(
                "execution state events directory changed without a contiguous event"
            )
    finally:
        if descriptor is not None:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


__all__ = ["TerminalStateIntegrityError", "verify_terminal_state_integrity"]
