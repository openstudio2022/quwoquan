"""Crash-recoverable append-only Objective/Increment execution-state journal."""
from __future__ import annotations

import contextlib
import errno
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

sys.dont_write_bytecode = True

from .contract import (
    ContractError, ObjectiveExecutionError, canonical_payload_digest, closed_values,
    reducer_version, validate_exact_fields,
)
from .reducer import reduce_events
from .secure_storage import (
    StorageError, StorageLease, StorageView, acquire_lease, entry_exists, list_entries,
    open_regular_at, open_view, publish_staged_event, read_all, remove_staging_entries,
    replace_regular_at, validate_lease, validate_view,
)

DIGEST_PREFIX = "sha256:"
GENESIS_HEAD = "absent"
Failpoint = Callable[[str], None]


class JournalError(ObjectiveExecutionError):
    def __init__(
        self, detail: str, *, tampered: bool = False, recovery_required: bool = False,
    ) -> None:
        code = (
            "OEX.JOURNAL_RECOVERY_REQUIRED" if recovery_required
            else ("OEX.JOURNAL_TAMPERED" if tampered else "OEX.JOURNAL_FAILED")
        )
        super().__init__(code, detail)


class CASConflict(ObjectiveExecutionError):
    def __init__(self, detail: str) -> None:
        super().__init__("OEX.CAS_CONFLICT", detail)


class WriterLeaseConflict(ObjectiveExecutionError):
    def __init__(self, detail: str) -> None:
        super().__init__("OEX.WRITER_LEASE_CONFLICT", detail)


@dataclass(frozen=True, slots=True)
class JournalIdentity:
    head: str
    generation: int


@dataclass(frozen=True, slots=True)
class JournalReadback:
    status: str
    subject_kind: str
    subject_id: str
    reduced_state: str | None
    head: str | None
    generation: int | None
    last_authority_receipt_ref: str | None
    last_effect_readback: dict[str, Any] | None
    terminal: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status, "subject_kind": self.subject_kind,
            "subject_id": self.subject_id, "reduced_state": self.reduced_state,
            "head": self.head, "generation": self.generation,
            "last_authority_receipt_ref": self.last_authority_receipt_ref,
            "last_effect_readback": self.last_effect_readback, "terminal": self.terminal,
        }


def canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def payload_digest(payload: Mapping[str, Any]) -> str:
    return canonical_payload_digest(payload)


def event_digest(payload: Mapping[str, Any]) -> str:
    return payload_digest({key: value for key, value in payload.items() if key != "event_digest"})


def subject_directory(root: Path, subject_kind: str, subject_id: str) -> Path:
    if subject_kind not in closed_values("subject_kind"):
        raise ContractError(f"unknown subject kind {subject_kind}")
    if not subject_id or subject_id in {".", ".."} or "/" in subject_id or "\\" in subject_id:
        raise ContractError("subject id is unsafe")
    return root / subject_kind / subject_id


def _translate_storage(error: StorageError, *, recovery_required: bool = False) -> JournalError:
    return JournalError(
        error.detail, tampered=error.tampered, recovery_required=recovery_required,
    )


@contextlib.contextmanager
def writer_lease(root: Path, subject_kind: str, subject_id: str) -> Iterator[StorageLease]:
    """Acquire the only capability accepted by private under-lease operations."""
    subject_directory(root, subject_kind, subject_id)
    try:
        with acquire_lease(root, subject_kind, subject_id) as lease:
            yield lease
    except StorageError as error:
        cause = error.__cause__
        if isinstance(cause, BlockingIOError):
            raise WriterLeaseConflict(error.detail) from error
        raise _translate_storage(error) from error


def _read_json_at(
    parent_fd: int, name: str, label: str, owner_uid: int, *, derived: bool = False,
) -> dict[str, Any]:
    try:
        descriptor = open_regular_at(parent_fd, name, label, owner_uid)
    except StorageError as error:
        cause = error.__cause__
        if derived and isinstance(cause, OSError) and cause.errno == errno.ENOENT:
            raise JournalError(f"{label} is missing", recovery_required=True) from error
        raise _translate_storage(error) from error
    try:
        raw = read_all(descriptor, label)
    except StorageError as error:
        raise _translate_storage(error) from error
    finally:
        os.close(descriptor)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise JournalError(
            f"{label} is incomplete", recovery_required=derived, tampered=not derived,
        ) from error
    if not isinstance(value, dict):
        raise JournalError(
            f"{label} must be an object", recovery_required=derived, tampered=not derived,
        )
    return value


def _load_events(
    view: StorageView, subject_kind: str, subject_id: str,
) -> list[dict[str, Any]]:
    try:
        validate_view(view)
        all_names = list_entries(view.events_fd)
    except StorageError as error:
        raise _translate_storage(error) from error
    staging_names = [name for name in all_names if name.startswith(".event.")]
    if any(not name.endswith(".staging") for name in staging_names):
        raise JournalError("event storage contains an unbound staging entry", tampered=True)
    for name in staging_names:
        try:
            staging_fd = open_regular_at(
                view.events_fd, name, "private staging file", view.owner_uid,
            )
        except StorageError as error:
            raise _translate_storage(error) from error
        else:
            os.close(staging_fd)
    authoritative_names = [name for name in all_names if not name.startswith(".event.")]
    if any(name.startswith(".") for name in authoritative_names):
        raise JournalError("event storage contains an unbound hidden entry", tampered=True)
    expected_names = [
        f"{generation:020d}.json" for generation in range(1, len(authoritative_names) + 1)
    ]
    if authoritative_names != expected_names:
        raise JournalError("event sequence has a gap or unbound file", tampered=True)
    events: list[dict[str, Any]] = []
    previous = GENESIS_HEAD
    for generation, name in enumerate(authoritative_names, 1):
        try:
            event = _read_json_at(
                view.events_fd, name, "transition event", view.owner_uid,
            )
            validate_exact_fields(event, "transition_event")
        except JournalError as error:
            if error.code == "OEX.JOURNAL_FAILED":
                raise
            raise JournalError(str(error), tampered=True) from error
        except ContractError as error:
            raise JournalError(str(error), tampered=True) from error
        if (
            event.get("schema_version") != 2
            or event.get("reducer_version") != reducer_version()
            or event.get("subject_kind") != subject_kind
            or event.get("subject_id") != subject_id
        ):
            raise JournalError("event identity/version drifted", tampered=True)
        if event.get("generation") != generation or event.get("expected_generation") != generation - 1:
            raise JournalError("event generation drifted", tampered=True)
        if event.get("previous_event_digest") != previous or event.get("expected_head") != previous:
            raise JournalError("event hash chain drifted", tampered=True)
        if event.get("event_digest") != event_digest(event):
            raise JournalError("event digest drifted", tampered=True)
        previous = str(event["event_digest"])
        events.append(event)
    try:
        reduce_events(subject_kind, events)
    except (ContractError, ObjectiveExecutionError) as error:
        raise JournalError(f"event reducer verification failed: {error}", tampered=True) from error
    try:
        validate_view(view)
    except StorageError as error:
        raise _translate_storage(error) from error
    return events


def _snapshot_document(
    subject_kind: str, subject_id: str, events: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    reduced = reduce_events(subject_kind, events)
    head = str(events[-1]["event_digest"]) if events else GENESIS_HEAD
    return {
        "schema_version": 2, "reducer_version": reducer_version(),
        "subject_kind": subject_kind, "subject_id": subject_id, "head": head,
        "generation": len(events), "reduced_state": reduced["reduced_state"],
        "last_authority_receipt_ref": reduced["last_authority_receipt_ref"],
        "last_effect_readback": reduced["last_effect_readback"],
    }


def _head_document(
    subject_kind: str, subject_id: str, snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 2, "reducer_version": reducer_version(),
        "subject_kind": subject_kind, "subject_id": subject_id,
        "head": snapshot["head"], "generation": snapshot["generation"],
        "snapshot_digest": payload_digest(snapshot),
    }


def _derived_match(
    view: StorageView, subject_kind: str, subject_id: str, snapshot: Mapping[str, Any],
) -> bool:
    try:
        snapshot_exists = entry_exists(
            view.subject_fd, "snapshot.json", directory=False,
            label="execution snapshot", owner_uid=view.owner_uid,
        )
        head_exists = entry_exists(
            view.subject_fd, "head.json", directory=False,
            label="execution head", owner_uid=view.owner_uid,
        )
    except StorageError as error:
        raise _translate_storage(error) from error
    if not snapshot_exists or not head_exists:
        return False
    try:
        persisted_snapshot = _read_json_at(
            view.subject_fd, "snapshot.json", "execution snapshot", view.owner_uid,
            derived=True,
        )
        persisted_head = _read_json_at(
            view.subject_fd, "head.json", "execution head", view.owner_uid,
            derived=True,
        )
    except JournalError as error:
        if error.code == "OEX.JOURNAL_RECOVERY_REQUIRED":
            return False
        raise
    return (
        persisted_snapshot == snapshot
        and persisted_head == _head_document(subject_kind, subject_id, snapshot)
    )


def _load_verified(
    view: StorageView, subject_kind: str, subject_id: str, *, require_materialized: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    events = _load_events(view, subject_kind, subject_id)
    snapshot = _snapshot_document(subject_kind, subject_id, events)
    if not events:
        try:
            derived_exists = any(
                entry_exists(
                    view.subject_fd, name, directory=False, label=label,
                    owner_uid=view.owner_uid,
                )
                for name, label in (
                    ("head.json", "execution head"),
                    ("snapshot.json", "execution snapshot"),
                )
            )
        except StorageError as error:
            raise _translate_storage(error) from error
        if derived_exists and require_materialized:
            raise JournalError(
                "derived state exists without authoritative events", recovery_required=True,
            )
        return events, snapshot
    if require_materialized and not _derived_match(view, subject_kind, subject_id, snapshot):
        raise JournalError(
            "derived snapshot/head require writer materialization", recovery_required=True,
        )
    return events, snapshot


def _materialize(
    lease: StorageLease, subject_kind: str, subject_id: str,
    events: Sequence[Mapping[str, Any]], *, failpoint: Failpoint | None = None,
) -> dict[str, Any]:
    snapshot = _snapshot_document(subject_kind, subject_id, events)
    try:
        replace_regular_at(
            lease, "snapshot.json", canonical_bytes(snapshot) + b"\n",
            failpoint=failpoint,
        )
        replace_regular_at(
            lease, "head.json",
            canonical_bytes(_head_document(subject_kind, subject_id, snapshot)) + b"\n",
            failpoint=failpoint,
        )
    except StorageError as error:
        raise _translate_storage(error) from error
    return snapshot


def _readback_from_snapshot(
    subject_kind: str, subject_id: str, events: Sequence[Mapping[str, Any]],
    snapshot: Mapping[str, Any],
) -> JournalReadback:
    if not events:
        return JournalReadback(
            "absent", subject_kind, subject_id, None, GENESIS_HEAD, 0, None, None, None,
        )
    return JournalReadback(
        "present", subject_kind, subject_id,
        str(snapshot["reduced_state"]) if snapshot["reduced_state"] is not None else None,
        str(snapshot["head"]), int(snapshot["generation"]),
        snapshot["last_authority_receipt_ref"], snapshot["last_effect_readback"], None,
    )


def readback(root: Path, subject_kind: str, subject_id: str) -> JournalReadback:
    """Read-only query: verify trusted events and derived artifacts without mutation."""
    try:
        subject_directory(root, subject_kind, subject_id)
        with open_view(root, subject_kind, subject_id) as view:
            if view is None:
                return JournalReadback(
                    "absent", subject_kind, subject_id, None, GENESIS_HEAD, 0,
                    None, None, None,
                )
            events, snapshot = _load_verified(
                view, subject_kind, subject_id, require_materialized=True,
            )
            return _readback_from_snapshot(subject_kind, subject_id, events, snapshot)
    except (ObjectiveExecutionError, StorageError, OSError, ValueError, TypeError) as error:
        if isinstance(error, ObjectiveExecutionError):
            code = error.code
        elif isinstance(error, StorageError) and error.tampered:
            code = "OEX.JOURNAL_TAMPERED"
        else:
            code = "OEX.JOURNAL_FAILED"
        return JournalReadback(
            "failed", subject_kind, subject_id, None, None, None, None, None, code,
        )


def _recover_under_lease(
    lease: StorageLease, *, failpoint: Failpoint | None = None,
) -> dict[str, Any]:
    try:
        validate_lease(lease)
        remove_staging_entries(lease)
    except StorageError as error:
        raise _translate_storage(error) from error
    subject_kind, subject_id = lease.subject_kind, lease.subject_id
    events, expected_snapshot = _load_verified(
        lease, subject_kind, subject_id, require_materialized=False,
    )
    if not events:
        try:
            derived_exists = any(
                entry_exists(
                    lease.subject_fd, name, directory=False, label=label,
                    owner_uid=lease.owner_uid,
                )
                for name, label in (
                    ("snapshot.json", "execution snapshot"),
                    ("head.json", "execution head"),
                )
            )
        except StorageError as error:
            raise _translate_storage(error) from error
        if derived_exists:
            raise JournalError("derived state exists without authoritative events", tampered=True)
        return {
            "result": "duplicate",
            "readback": _readback_from_snapshot(
                subject_kind, subject_id, events, expected_snapshot,
            ).as_dict(),
        }
    already_materialized = _derived_match(
        lease, subject_kind, subject_id, expected_snapshot,
    )
    snapshot = (
        expected_snapshot if already_materialized
        else _materialize(
            lease, subject_kind, subject_id, events, failpoint=failpoint,
        )
    )
    final_events, final_snapshot = _load_verified(
        lease, subject_kind, subject_id, require_materialized=True,
    )
    return {
        "result": "duplicate" if already_materialized else "recovered",
        "readback": _readback_from_snapshot(
            subject_kind, subject_id, final_events, final_snapshot,
        ).as_dict(),
        "snapshot_digest": payload_digest(snapshot),
    }


def recover_materialization(
    root: Path, subject_kind: str, subject_id: str, *, failpoint: Failpoint | None = None,
) -> dict[str, Any]:
    """Public recovery always acquires its own non-forgeable writer capability."""
    with writer_lease(root, subject_kind, subject_id) as lease:
        return _recover_under_lease(lease, failpoint=failpoint)


def _read_events_under_lease(lease: StorageLease) -> tuple[dict[str, Any], ...]:
    try:
        validate_lease(lease)
    except StorageError as error:
        raise _translate_storage(error) from error
    events, _ = _load_verified(
        lease, lease.subject_kind, lease.subject_id, require_materialized=False,
    )
    return tuple(events)


def read_events(
    root: Path, subject_kind: str, subject_id: str,
) -> tuple[dict[str, Any], ...]:
    subject_directory(root, subject_kind, subject_id)
    try:
        with open_view(root, subject_kind, subject_id) as view:
            if view is None:
                return ()
            events, _ = _load_verified(
                view, subject_kind, subject_id, require_materialized=True,
            )
            return tuple(events)
    except StorageError as error:
        raise _translate_storage(error) from error


def _append_event_under_lease(
    lease: StorageLease, command: Mapping[str, Any], *, failpoint: Failpoint | None = None,
) -> dict[str, Any]:
    validate_exact_fields(command, "append_transition_command")
    subject_kind, subject_id = str(command["subject_kind"]), str(command["subject_id"])
    if subject_kind != lease.subject_kind or subject_id != lease.subject_id:
        raise JournalError("writer lease capability scope mismatch", tampered=True)
    try:
        validate_lease(lease)
        remove_staging_entries(lease)
    except StorageError as error:
        raise _translate_storage(error) from error
    events, snapshot = _load_verified(
        lease, subject_kind, subject_id, require_materialized=False,
    )
    if events and not _derived_match(lease, subject_kind, subject_id, snapshot):
        snapshot = _materialize(lease, subject_kind, subject_id, events)
    expected_head, expected_generation = (
        command["expected_head"], command["expected_generation"],
    )
    duplicate = next((
        event for event in events
        if event["event_kind"] == command["event_kind"]
        and event["effect_idempotency_key"] == command["effect_idempotency_key"]
    ), None)
    if duplicate is not None:
        for field in (
            "subject_kind", "subject_id", "event_kind", "reducer_version", "action",
            "from_state", "to_state", "authority_receipt_ref", "effect_idempotency_key",
            "command_envelope_digest", "effect_id", "effect_readback", "occurred_at", "payload",
        ):
            if duplicate[field] != command[field]:
                raise ContractError(f"idempotency key payload drifted at {field}")
        final = _readback_from_snapshot(subject_kind, subject_id, events, snapshot)
        return {"result": "duplicate", "event": duplicate, "readback": final.as_dict()}
    if expected_head != snapshot["head"] or expected_generation != snapshot["generation"]:
        raise CASConflict(
            "expected head/generation "
            f"{expected_head}/{expected_generation}, current "
            f"{snapshot['head']}/{snapshot['generation']}"
        )
    generation = int(snapshot["generation"]) + 1
    unsigned = {
        "schema_version": 2, "reducer_version": command["reducer_version"],
        "event_id": f"{subject_kind}:{subject_id}:{generation:020d}",
        "subject_kind": subject_kind, "subject_id": subject_id,
        "event_kind": command["event_kind"], "action": command["action"],
        "from_state": command["from_state"], "to_state": command["to_state"],
        "expected_head": expected_head, "expected_generation": expected_generation,
        "generation": generation, "previous_event_digest": expected_head,
        "authority_receipt_ref": command["authority_receipt_ref"],
        "effect_idempotency_key": command["effect_idempotency_key"],
        "command_envelope_digest": command["command_envelope_digest"],
        "effect_id": command["effect_id"], "effect_readback": command["effect_readback"],
        "occurred_at": command["occurred_at"], "payload": command["payload"],
    }
    event = {**unsigned, "event_digest": event_digest(unsigned)}
    reduce_events(subject_kind, [*events, event])
    try:
        publish_staged_event(
            lease, f"{generation:020d}.json", canonical_bytes(event) + b"\n",
            failpoint=failpoint,
        )
    except StorageError as error:
        raise _translate_storage(error) from error
    next_events = [*events, event]
    next_snapshot = _materialize(
        lease, subject_kind, subject_id, next_events, failpoint=failpoint,
    )
    final_events, final_snapshot = _load_verified(
        lease, subject_kind, subject_id, require_materialized=True,
    )
    final = _readback_from_snapshot(subject_kind, subject_id, final_events, final_snapshot)
    if final.status != "present" or final.head != event["event_digest"] or final.generation != generation:
        raise JournalError("post-commit readback did not confirm the event")
    return {
        "result": "committed", "event": event, "readback": final.as_dict(),
        "snapshot_digest": payload_digest(next_snapshot),
    }


def append_event(
    root: Path, command: Mapping[str, Any], *, failpoint: Failpoint | None = None,
) -> dict[str, Any]:
    """Public append always acquires its own non-forgeable writer capability."""
    validate_exact_fields(command, "append_transition_command")
    subject_kind, subject_id = str(command["subject_kind"]), str(command["subject_id"])
    with writer_lease(root, subject_kind, subject_id) as lease:
        return _append_event_under_lease(lease, command, failpoint=failpoint)
