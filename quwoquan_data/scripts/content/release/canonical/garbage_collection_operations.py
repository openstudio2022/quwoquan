"""Digest-bound, recoverable canonical GC plan and apply operations."""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content.release.canonical.garbage_collection_contract import (
    GC_APPLY_SCHEMA,
    GC_PLAN_SCHEMA,
    file_digest,
    json_digest,
    validate_apply_receipt,
    validate_plan_document,
    write_create_once_json,
)
from content.release.canonical.garbage_collection_reachability import (
    reachability_snapshot,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
    _safe_id,
    _safe_rel,
)
from content.release.canonical.object_transaction_lock import canonical_publish_lock
from content.release.canonical.release_identity_incident import (
    release_identity_protection_lock,
)
from content.release.canonical.release_operation_lock import (
    ReleaseOperationConflict,
    release_operation_guard,
    release_operation_lock_root,
)
from core.paths import DATA_GC_WORKSPACE_ROOT, DATA_QUARANTINE_ROOT, OUTPUT_ROOT
from core.tree_integrity import tree_integrity_stats


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _gc_root(output_root: Path) -> Path:
    return output_root.resolve() / DATA_GC_WORKSPACE_ROOT.relative_to(OUTPUT_ROOT)


def _quarantine_root(output_root: Path, plan_id: str) -> Path:
    return (
        output_root.resolve()
        / DATA_QUARANTINE_ROOT.relative_to(OUTPUT_ROOT)
        / "canonical-gc"
        / plan_id
    )


@contextmanager
def _gc_lock(output_root: Path) -> Iterator[None]:
    path = _gc_root(output_root) / "gc.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ObjectTransactionError(
                "GATE_BLOCK another canonical GC owns the lock"
            ) from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _gc_reachability_guard(
    *,
    publish_root: Path,
    release_root: Path,
) -> Iterator[None]:
    try:
        with (
            release_operation_guard(
                lock_root=release_operation_lock_root(release_root),
                global_exclusive=True,
            ),
            canonical_publish_lock(publish_root),
        ):
            yield
    except ReleaseOperationConflict as exc:
        raise ObjectTransactionError(str(exc)) from exc


def plan_canonical_gc(
    *,
    plan_id: str,
    output_root: Path,
    publish_root: Path,
    release_root: Path | None = None,
    min_age_hours: float = 168.0,
    now: datetime | None = None,
) -> tuple[dict[str, Any], Path]:
    """Create one immutable GC plan without moving or deleting output."""

    plan_id = _safe_id(plan_id, label="planId")
    if min_age_hours < 0:
        raise ValueError("minAgeHours must be non-negative")
    output_root = output_root.resolve()
    publish_root = publish_root.resolve()
    release_root = (release_root or output_root / "data/releases").resolve()
    path = _gc_root(output_root) / "plans" / plan_id / "plan.json"
    with (
        release_identity_protection_lock(
            output_root=output_root,
            exclusive=True,
        ),
        _gc_lock(output_root),
        _gc_reachability_guard(
            publish_root=publish_root,
            release_root=release_root,
        ),
    ):
        if path.is_file():
            persisted = _read_json(path)
            validate_plan_document(persisted, plan_id=plan_id)
            if (
                persisted.get("minAgeHours") != min_age_hours
                or persisted.get("publishRoot") != str(publish_root)
                or persisted.get("releaseRoot") != str(release_root)
            ):
                raise ObjectTransactionError("persisted GC plan request drift")
            return persisted, path
        measured_at = now or _now()
        snapshot = reachability_snapshot(
            output_root=output_root,
            publish_root=publish_root,
            release_root=release_root,
            min_age_hours=min_age_hours,
            now=measured_at,
        )
        document: dict[str, Any] = {
            "schema": GC_PLAN_SCHEMA,
            "planId": plan_id,
            "status": "planned",
            "plannedAt": _iso(measured_at),
            "minAgeHours": min_age_hours,
            "publishRoot": str(publish_root),
            "releaseRoot": str(release_root),
            **snapshot,
            "candidateCount": len(snapshot["candidates"]),
            "reclaimableBytes": sum(
                int(row["bytes"]) for row in snapshot["candidates"]
            ),
        }
        document["planDigest"] = json_digest(document, excluded="planDigest")
        validate_plan_document(document, plan_id=plan_id)
        if write_create_once_json(path, document):
            return document, path
        persisted = _read_json(path)
        validate_plan_document(persisted, plan_id=plan_id)
        if persisted != document:
            raise ObjectTransactionError("persisted GC plan create-once collision")
        return persisted, path


def _journal_rows(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict) or not isinstance(value.get("ref"), str):
            raise ObjectTransactionError("GC apply journal is invalid")
        if value.get("status") not in {"prepared", "quarantined"}:
            raise ObjectTransactionError("GC apply journal status is invalid")
        if value.get("pathType") not in {"file", "directory"} or not isinstance(
            value.get("kind"), str
        ):
            raise ObjectTransactionError("GC apply journal candidate type is invalid")
        prior = rows.get(value["ref"])
        if prior is not None:
            if prior.get("status") == "quarantined":
                raise ObjectTransactionError(
                    "GC apply journal contains an event after quarantine"
                )
            if value.get("status") != "quarantined":
                raise ObjectTransactionError(
                    "GC apply journal contains duplicate prepared events"
                )
        rows[value["ref"]] = value
    return rows


def _append_journal(path: Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _candidate_target(output_root: Path, candidate: Mapping[str, Any]) -> Path:
    ref = str(candidate.get("ref") or "")
    relative = _safe_rel(ref, label="gc.candidate.ref")
    if relative.parts[:2] not in {("data", "tasks"), ("data", "local")}:
        raise ObjectTransactionError(f"GC candidate scope is invalid: {ref}")
    if (
        relative.parts[:3] == ("data", "local", "workspace")
        and len(relative.parts) >= 4
        and relative.parts[3] in {"gc", "quarantine"}
    ):
        raise ObjectTransactionError(f"GC cannot collect its own evidence: {ref}")
    allowed = any(
        relative.parts[: len(prefix)] == prefix
        for prefix in (
            ("data", "tasks"),
            ("data", "local", "workspace", "object-transactions"),
            ("data", "local", "workspace", "source-acquisition"),
            (
                "data",
                "local",
                "cache",
                "content-campaign-workspaces",
                "content-addressed-capsules",
            ),
            ("data", "local", "cache", "executor-bundles"),
        )
    )
    if not allowed:
        raise ObjectTransactionError(f"GC candidate is outside governed roots: {ref}")
    return output_root / relative


def _validate_quarantined_candidate(
    path: Path,
    candidate: Mapping[str, Any],
) -> None:
    path_type = str(candidate.get("pathType") or "")
    if (
        path.is_symlink()
        or (path_type == "directory" and not path.is_dir())
        or (path_type == "file" and not path.is_file())
    ):
        raise ObjectTransactionError(
            f"GATE_BLOCK GC quarantine candidate is missing: {path}"
        )
    if path_type == "file":
        observed = {
            "merkleRoot": file_digest(path),
            "fileCount": 1,
            "bytes": path.stat().st_size,
        }
    elif path_type == "directory":
        stats = tree_integrity_stats(path)
        observed = {
            "merkleRoot": stats["merkleRoot"],
            "fileCount": stats["fileCount"],
            "bytes": stats["totalBytes"],
        }
    else:
        raise ObjectTransactionError("GATE_BLOCK GC candidate pathType is invalid")
    if any(observed[key] != candidate[key] for key in observed):
        raise ObjectTransactionError(f"GATE_BLOCK GC quarantine drift: {path}")


def apply_canonical_gc(
    *,
    plan_id: str,
    plan_digest: str,
    output_root: Path,
    publish_root: Path,
    release_root: Path | None = None,
    now: datetime | None = None,
) -> tuple[dict[str, Any], Path]:
    """Revalidate a frozen plan and atomically quarantine exact candidates."""

    plan_id = _safe_id(plan_id, label="planId")
    output_root = output_root.resolve()
    publish_root = publish_root.resolve()
    release_root = (release_root or output_root / "data/releases").resolve()
    plan_root = _gc_root(output_root) / "plans" / plan_id
    plan_path = plan_root / "plan.json"
    receipt_path = plan_root / "apply.json"
    quarantine_root = _quarantine_root(output_root, plan_id)
    with (
        release_identity_protection_lock(
            output_root=output_root,
            exclusive=True,
        ),
        _gc_lock(output_root),
        _gc_reachability_guard(
            publish_root=publish_root,
            release_root=release_root,
        ),
    ):
        plan = _read_json(plan_path)
        actual_digest = validate_plan_document(
            plan,
            plan_id=plan_id,
            plan_digest=plan_digest,
        )
        if plan.get("publishRoot") != str(publish_root):
            raise ObjectTransactionError("GC apply publish root drift")
        if plan.get("releaseRoot") != str(release_root):
            raise ObjectTransactionError("GC apply release root drift")
        if receipt_path.is_file():
            persisted = _read_json(receipt_path)
            validate_apply_receipt(
                persisted,
                plan_id=plan_id,
                plan_digest=actual_digest,
            )
            return {**persisted, "idempotent": True}, receipt_path

        measured_at = now or _now()
        current = reachability_snapshot(
            output_root=output_root,
            publish_root=publish_root,
            release_root=release_root,
            min_age_hours=float(plan.get("minAgeHours") or 0.0),
            now=measured_at,
        )
        current_by_ref = {row["ref"]: row for row in current["candidates"]}
        journal_path = plan_root / "apply.journal.jsonl"
        completed = _journal_rows(journal_path)
        for candidate in plan["candidates"]:
            ref = str(candidate["ref"])
            target = _candidate_target(output_root, candidate)
            quarantine = quarantine_root / _safe_rel(ref, label="gc.candidate.ref")
            expected_quarantine_ref = quarantine.relative_to(output_root).as_posix()
            journal = completed.get(ref)
            if journal is not None and any(
                journal.get(key) != candidate.get(key)
                for key in (
                    "kind",
                    "pathType",
                    "merkleRoot",
                    "fileCount",
                    "bytes",
                )
            ):
                raise ObjectTransactionError(
                    f"GC journal candidate binding drift: {ref}"
                )
            if (
                journal is not None
                and journal.get("quarantineRef") != expected_quarantine_ref
            ):
                raise ObjectTransactionError(
                    f"GC journal quarantine binding drift: {ref}"
                )
            if journal is not None and journal["status"] == "quarantined":
                if target.exists():
                    raise ObjectTransactionError(
                        f"GC quarantined target reappeared: {ref}"
                    )
                _validate_quarantined_candidate(quarantine, candidate)
                continue
            if journal is not None and not target.exists():
                _validate_quarantined_candidate(quarantine, candidate)
                continue
            current_candidate = current_by_ref.get(ref)
            if current_candidate is None:
                raise ObjectTransactionError(
                    f"GATE_BLOCK GC candidate became protected or ineligible: {ref}"
                )
            if any(
                current_candidate.get(key) != candidate.get(key)
                for key in (
                    "kind",
                    "pathType",
                    "merkleRoot",
                    "fileCount",
                    "bytes",
                )
            ):
                raise ObjectTransactionError(f"GATE_BLOCK GC candidate drift: {ref}")
            if (
                target.is_symlink()
                or (candidate["pathType"] == "directory" and not target.is_dir())
                or (candidate["pathType"] == "file" and not target.is_file())
            ):
                raise ObjectTransactionError(f"GC candidate is missing: {ref}")
            if quarantine.exists() or quarantine.is_symlink():
                raise ObjectTransactionError(
                    f"GATE_BLOCK GC quarantine destination exists: {quarantine}"
                )

        intent_path = plan_root / "apply_intent.json"
        intent_stable = {
            "schema": "quwoquan_data.canonical_gc_apply_intent",
            "planId": plan_id,
            "planDigest": actual_digest,
            "candidateCount": int(plan["candidateCount"]),
        }
        if intent_path.is_file():
            persisted_intent = _read_json(intent_path)
            if any(
                persisted_intent.get(key) != value
                for key, value in intent_stable.items()
            ):
                raise ObjectTransactionError("persisted GC apply intent drift")
        else:
            intent = {**intent_stable, "preparedAt": _iso(measured_at)}
            if not write_create_once_json(intent_path, intent):
                persisted_intent = _read_json(intent_path)
                if persisted_intent != intent:
                    raise ObjectTransactionError(
                        "persisted GC apply intent create-once collision"
                    )

        quarantined_rows: list[dict[str, Any]] = []
        completed = _journal_rows(journal_path)
        for candidate in plan["candidates"]:
            ref = str(candidate["ref"])
            target = _candidate_target(output_root, candidate)
            quarantine = quarantine_root / _safe_rel(ref, label="gc.candidate.ref")
            journal = completed.get(ref)
            if journal is None:
                prepared = {
                    "ref": ref,
                    "kind": candidate["kind"],
                    "pathType": candidate["pathType"],
                    "status": "prepared",
                    "merkleRoot": candidate["merkleRoot"],
                    "fileCount": candidate["fileCount"],
                    "bytes": candidate["bytes"],
                    "quarantineRef": quarantine.relative_to(output_root).as_posix(),
                    "preparedAt": _iso(_now()),
                }
                _append_journal(journal_path, prepared)
                completed[ref] = prepared
                journal = prepared
            if journal["status"] == "prepared":
                if target.exists():
                    if (
                        target.is_symlink()
                        or (
                            candidate["pathType"] == "directory" and not target.is_dir()
                        )
                        or (candidate["pathType"] == "file" and not target.is_file())
                    ):
                        raise ObjectTransactionError(
                            f"GC candidate is not a regular directory: {ref}"
                        )
                    _validate_quarantined_candidate(target, candidate)
                    quarantine.parent.mkdir(parents=True, exist_ok=True)
                    target.replace(quarantine)
                _validate_quarantined_candidate(quarantine, candidate)
                row = {
                    "ref": ref,
                    "kind": candidate["kind"],
                    "pathType": candidate["pathType"],
                    "status": "quarantined",
                    "merkleRoot": candidate["merkleRoot"],
                    "fileCount": candidate["fileCount"],
                    "bytes": candidate["bytes"],
                    "quarantineRef": quarantine.relative_to(output_root).as_posix(),
                    "quarantinedAt": _iso(_now()),
                }
                _append_journal(journal_path, row)
                completed[ref] = row
            quarantined_rows.append(dict(completed[ref]))

        receipt: dict[str, Any] = {
            "schema": GC_APPLY_SCHEMA,
            "planId": plan_id,
            "planDigest": actual_digest,
            "status": "applied",
            "appliedAt": _iso(_now()),
            "quarantined": quarantined_rows,
            "quarantinedCount": len(quarantined_rows),
            "quarantinedBytes": sum(int(row["bytes"]) for row in quarantined_rows),
            "permanentDeletion": False,
            "idempotent": False,
        }
        receipt["receiptDigest"] = json_digest(receipt, excluded="receiptDigest")
        validate_apply_receipt(
            receipt,
            plan_id=plan_id,
            plan_digest=actual_digest,
        )
        if write_create_once_json(receipt_path, receipt):
            return receipt, receipt_path
        persisted = _read_json(receipt_path)
        validate_apply_receipt(
            persisted,
            plan_id=plan_id,
            plan_digest=actual_digest,
        )
        if persisted != receipt:
            raise ObjectTransactionError(
                "persisted GC apply receipt create-once collision"
            )
        return persisted, receipt_path


__all__ = [
    "GC_APPLY_SCHEMA",
    "GC_PLAN_SCHEMA",
    "apply_canonical_gc",
    "plan_canonical_gc",
]
