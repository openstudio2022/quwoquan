"""Freeze an incident quarantine as immutable forensic evidence.

The receipt never makes quarantined bytes reusable. The quarantine's own
``QUARANTINE.json`` is the only provenance credential and is included in the
frozen tree digest; migration provenance is intentionally unsupported.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from governance.protected_quarantine_validation import (
    FORENSIC_DEFAULT_REASON,
    FORENSIC_MARKER_NAME,
    FORENSIC_QUARANTINE_DIRECTORY,
    FORENSIC_REQUIRED_CONSUMPTION,
    FORENSIC_REQUIRED_RECOVERY,
    RECEIPT_DIRECTORY,
    SCHEMA,
    ProtectedQuarantineEvidenceError,
    _canonical_digest,
    _forensic_quarantine_ref,
    _now,
    _stable_manifest,
    _tree_inventory,
    _validate_forensic_marker,
    validate_protected_quarantine_receipt,
)
from core.paths import DATA_OUTPUT_ROOT
from core.schema import assert_valid

def load_protected_quarantine_receipts(
    *,
    data_output_root: Path = DATA_OUTPUT_ROOT,
) -> tuple[dict[Path, dict[str, object]], list[str]]:
    root = data_output_root.expanduser().resolve()
    receipt_root = root / RECEIPT_DIRECTORY
    if not receipt_root.is_dir():
        return {}, []
    protected: dict[Path, dict[str, object]] = {}
    issues: list[str] = []
    for receipt_path in sorted(receipt_root.glob("*/receipt.json")):
        try:
            payload, quarantine_root = validate_protected_quarantine_receipt(
                receipt_path,
                data_output_root=root,
            )
        except ProtectedQuarantineEvidenceError as exc:
            issues.append(str(exc))
            continue
        if quarantine_root in protected:
            issues.append(
                f"multiple protected quarantine receipts claim {quarantine_root}"
            )
            protected.pop(quarantine_root, None)
            continue
        protected[quarantine_root] = payload
    return protected, issues


@contextmanager
def _receipt_lock(root: Path) -> Iterator[None]:
    lock_path = root / RECEIPT_DIRECTORY / ".protect.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _write_create_once(path: Path, payload: Mapping[str, object]) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProtectedQuarantineEvidenceError(
                f"protected quarantine create-once conflict: {path}"
            ) from exc
        if existing != payload:
            raise ProtectedQuarantineEvidenceError(
                f"protected quarantine create-once conflict: {path}"
            )
        return
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())


def _issue_protection_receipt(
    *,
    root: Path,
    quarantine_path: Path,
    quarantine_ref: str,
    provenance: Mapping[str, object],
    tree: Mapping[str, object],
    reason: str,
    recheck_provenance: Callable[[], Mapping[str, object]],
    provenance_drift_message: str,
) -> tuple[dict[str, object], Path]:
    stable: dict[str, object] = {
        "schema": SCHEMA,
        "status": "protected_read_only",
        "quarantineRef": quarantine_ref,
        "reason": reason,
        "reusableSourceTruthAllowed": False,
        **provenance,
        **tree,
    }
    manifest_digest = _canonical_digest(stable)
    payload = {
        **stable,
        "manifestDigest": manifest_digest,
        "recordedAt": _now(),
    }
    assert_valid(
        payload,
        "governance",
        "protected_quarantine_evidence",
        label=SCHEMA,
    )
    destination = (
        root
        / RECEIPT_DIRECTORY
        / manifest_digest.removeprefix("sha256:")
        / "receipt.json"
    )
    with _receipt_lock(root):
        existing, issues = load_protected_quarantine_receipts(data_output_root=root)
        if issues:
            raise ProtectedQuarantineEvidenceError(
                "existing protected quarantine receipt is invalid: " + "; ".join(issues)
            )
        current = existing.get(quarantine_path)
        if current is not None:
            if current.get("manifestDigest") != manifest_digest:
                raise ProtectedQuarantineEvidenceError(
                    f"quarantine reference is already protected: {quarantine_ref}"
                )
            current_path = (
                root
                / RECEIPT_DIRECTORY
                / str(current["manifestDigest"]).removeprefix("sha256:")
                / "receipt.json"
            )
            return current, current_path
        if _tree_inventory(quarantine_path) != tree:
            raise ProtectedQuarantineEvidenceError(
                "quarantine tree drifted while its receipt was being created"
            )
        if dict(recheck_provenance()) != dict(provenance):
            raise ProtectedQuarantineEvidenceError(provenance_drift_message)
        _write_create_once(destination, payload)
    return payload, destination


def protect_forensic_quarantine(
    *,
    quarantine_root: Path,
    data_output_root: Path = DATA_OUTPUT_ROOT,
    reason: str = FORENSIC_DEFAULT_REASON,
) -> tuple[dict[str, object], Path]:
    """Register an incident quarantine with its own QUARANTINE.json as credential."""
    root = data_output_root.expanduser().resolve()
    normalized_reason = str(reason).strip()
    if not normalized_reason:
        raise ProtectedQuarantineEvidenceError("protection reason must not be empty")
    quarantine_candidate = quarantine_root.expanduser()
    quarantine_ref = _forensic_quarantine_ref(
        quarantine_candidate, data_output_root=root
    )
    quarantine_path = quarantine_candidate.resolve()
    provenance = _validate_forensic_marker(quarantine_path)
    tree = _tree_inventory(quarantine_path)
    return _issue_protection_receipt(
        root=root,
        quarantine_path=quarantine_path,
        quarantine_ref=quarantine_ref,
        provenance=provenance,
        tree=tree,
        reason=normalized_reason,
        recheck_provenance=lambda: _validate_forensic_marker(quarantine_path),
        provenance_drift_message=(
            "forensic marker drifted while the receipt was being created"
        ),
    )


__all__ = [
    "FORENSIC_DEFAULT_REASON",
    "FORENSIC_MARKER_NAME",
    "FORENSIC_REQUIRED_CONSUMPTION",
    "FORENSIC_REQUIRED_RECOVERY",
    "ProtectedQuarantineEvidenceError",
    "load_protected_quarantine_receipts",
    "protect_forensic_quarantine",
    "validate_protected_quarantine_receipt",
]
