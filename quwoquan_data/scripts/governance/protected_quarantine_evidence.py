"""Freeze a historical quarantine tree as read-only evidence.

The receipt does not make quarantined policy/template bytes reusable.  It only
lets the output isolation gate distinguish a byte-exact historical package from
an active second source of truth.  A quarantine reference can be protected
once: later tree drift cannot be blessed by issuing a replacement receipt.

Two provenance classes are supported:

- migration: a tree relocated by the one-shot output-layout migration under
  ``local/workspace/quarantine/<child>``; the credential is the migration
  apply receipt.
- forensic: an incident quarantine under ``quarantine/<child>``; the
  credential is the tree's own ``QUARANTINE.json`` marker, which must declare
  ``recovery: retain_for_forensics_only``.  The marker file is itself part of
  the frozen tree digest, so tampering with the credential is tree drift; the
  receipt artifact lives outside the tree so the digest has no self reference.
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

from core.paths import DATA_OUTPUT_ROOT
from core.schema import assert_valid

SCHEMA = "quwoquan_data.protected_quarantine_evidence"
RECEIPT_DIRECTORY = Path("local/cache/protected-quarantines")
QUARANTINE_DIRECTORY = Path("local/workspace/quarantine")
DEFAULT_REASON = "historical release evidence preserved after output layout migration"
FORENSIC_QUARANTINE_DIRECTORY = Path("quarantine")
FORENSIC_MARKER_NAME = "QUARANTINE.json"
FORENSIC_REQUIRED_CONSUMPTION = "forbidden"
FORENSIC_REQUIRED_RECOVERY = "retain_for_forensics_only"
FORENSIC_DEFAULT_REASON = (
    "forensic quarantine preserved as tamper-evident incident evidence"
)


class ProtectedQuarantineEvidenceError(ValueError):
    """Historical evidence cannot be protected without an exact identity."""


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_digest(value: object) -> str:
    return _sha256_bytes(_canonical_bytes(value))


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _relative_to_output(path: Path, *, data_output_root: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(data_output_root).as_posix()
    except ValueError as exc:
        raise ProtectedQuarantineEvidenceError(
            f"path escaped the governed Data output root: {resolved}"
        ) from exc


def _quarantine_ref(path: Path, *, data_output_root: Path) -> str:
    if path.is_symlink():
        raise ProtectedQuarantineEvidenceError("quarantine root must not be a symlink")
    relative = _relative_to_output(path, data_output_root=data_output_root)
    parts = Path(relative).parts
    expected = QUARANTINE_DIRECTORY.parts
    if len(parts) != len(expected) + 1 or parts[: len(expected)] != expected:
        raise ProtectedQuarantineEvidenceError(
            "quarantine must be one direct child of local/workspace/quarantine"
        )
    if not path.is_dir():
        raise ProtectedQuarantineEvidenceError(f"quarantine is missing: {path}")
    return relative


def _forensic_quarantine_ref(path: Path, *, data_output_root: Path) -> str:
    if path.is_symlink():
        raise ProtectedQuarantineEvidenceError("quarantine root must not be a symlink")
    relative = _relative_to_output(path, data_output_root=data_output_root)
    parts = Path(relative).parts
    expected = FORENSIC_QUARANTINE_DIRECTORY.parts
    if len(parts) != len(expected) + 1 or parts[: len(expected)] != expected:
        raise ProtectedQuarantineEvidenceError(
            "forensic quarantine must be one direct child of quarantine"
        )
    if not path.is_dir():
        raise ProtectedQuarantineEvidenceError(f"quarantine is missing: {path}")
    return relative


def _validate_forensic_marker(quarantine_root: Path) -> dict[str, str]:
    """The quarantine's own ``QUARANTINE.json`` is the provenance credential."""
    marker = quarantine_root / FORENSIC_MARKER_NAME
    if marker.is_symlink() or not marker.is_file():
        raise ProtectedQuarantineEvidenceError(
            f"forensic marker is missing or not a regular file: {marker}"
        )
    body = marker.read_bytes()
    try:
        payload = json.loads(body)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ProtectedQuarantineEvidenceError(
            f"forensic marker is not valid JSON: {marker}: {exc}"
        ) from exc
    if not isinstance(payload, Mapping):
        raise ProtectedQuarantineEvidenceError(
            f"forensic marker must be a JSON object: {marker}"
        )
    decision = payload.get("decision")
    consumption = payload.get("consumption")
    recovery = payload.get("recovery")
    if not isinstance(decision, str) or not decision.strip():
        raise ProtectedQuarantineEvidenceError(
            f"forensic marker requires a non-empty decision: {marker}"
        )
    if consumption != FORENSIC_REQUIRED_CONSUMPTION:
        raise ProtectedQuarantineEvidenceError(
            f"forensic marker must declare consumption: {FORENSIC_REQUIRED_CONSUMPTION}: {marker}"
        )
    if recovery != FORENSIC_REQUIRED_RECOVERY:
        raise ProtectedQuarantineEvidenceError(
            f"forensic marker must declare recovery: {FORENSIC_REQUIRED_RECOVERY}: {marker}"
        )
    return {
        "provenance": "forensic",
        "forensicMarkerPath": FORENSIC_MARKER_NAME,
        "forensicMarkerSha256": _sha256_bytes(body),
        "forensicDecision": decision,
        "forensicConsumption": consumption,
        "forensicRecovery": recovery,
    }


def _safe_symlink_entry(path: Path, *, root: Path) -> dict[str, str]:
    target = os.readlink(path)
    if not target:
        raise ProtectedQuarantineEvidenceError(f"empty symlink target: {path}")
    try:
        resolved_target = path.resolve(strict=True)
        resolved_target.relative_to(root)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise ProtectedQuarantineEvidenceError(
            f"quarantine symlink is broken or escapes its root: {path} -> {target}"
        ) from exc
    return {
        "path": path.relative_to(root).as_posix(),
        "target": target,
        "targetSha256": _sha256_bytes(os.fsencode(target)),
    }


def _tree_inventory(root: Path) -> dict[str, object]:
    directories: list[str] = []
    files: list[dict[str, object]] = []
    symlinks: list[dict[str, str]] = []
    byte_count = 0
    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        retained: list[str] = []
        for name in sorted(dirnames):
            child = current_path / name
            if child.is_symlink():
                symlinks.append(_safe_symlink_entry(child, root=root))
            else:
                mode = child.lstat().st_mode
                if not stat.S_ISDIR(mode):
                    raise ProtectedQuarantineEvidenceError(
                        f"unsupported quarantine entry: {child}"
                    )
                directories.append(child.relative_to(root).as_posix())
                retained.append(name)
        dirnames[:] = retained
        for name in sorted(filenames):
            child = current_path / name
            if child.is_symlink():
                symlinks.append(_safe_symlink_entry(child, root=root))
                continue
            mode = child.lstat().st_mode
            if not stat.S_ISREG(mode):
                raise ProtectedQuarantineEvidenceError(
                    f"unsupported quarantine entry: {child}"
                )
            body = child.read_bytes()
            byte_count += len(body)
            files.append(
                {
                    "path": child.relative_to(root).as_posix(),
                    "byteCount": len(body),
                    "sha256": _sha256_bytes(body),
                }
            )
    if not files:
        raise ProtectedQuarantineEvidenceError("protected quarantine must contain files")
    tree = {
        "directories": sorted(directories),
        "files": sorted(files, key=lambda item: str(item["path"])),
        "symlinks": sorted(symlinks, key=lambda item: item["path"]),
    }
    return {
        **tree,
        "directoryCount": len(tree["directories"]),
        "fileCount": len(tree["files"]),
        "symlinkCount": len(tree["symlinks"]),
        "byteCount": byte_count,
        "treeDigest": _canonical_digest(tree),
    }


def _validate_migration_receipt(
    path: Path,
    *,
    data_output_root: Path,
) -> dict[str, str]:
    if not path.is_file() or path.is_symlink():
        raise ProtectedQuarantineEvidenceError(
            f"migration apply receipt is missing or not a regular file: {path}"
        )
    relative = _relative_to_output(path, data_output_root=data_output_root)
    parts = Path(relative).parts
    expected_prefix = ("local", "cache", "output-layout-migrations")
    if (
        len(parts) != 5
        or parts[:3] != expected_prefix
        or len(parts[3]) != 64
        or any(character not in "0123456789abcdef" for character in parts[3])
        or parts[4] != "apply.json"
    ):
        raise ProtectedQuarantineEvidenceError(
            "migration receipt must use the canonical output-layout-migrations path"
        )
    body = path.read_bytes()
    try:
        payload = json.loads(body)
        assert_valid(
            payload,
            "governance",
            "data_output_layout_migration",
            label="quwoquan_data.data_output_layout_migration",
        )
    except (ValueError, json.JSONDecodeError) as exc:
        raise ProtectedQuarantineEvidenceError(
            f"migration apply receipt is invalid: {path}: {exc}"
        ) from exc
    plan_digest = "sha256:" + parts[3]
    if (
        payload.get("documentKind") != "apply_receipt"
        or payload.get("status") != "applied"
        or payload.get("planDigest") != plan_digest
    ):
        raise ProtectedQuarantineEvidenceError(
            "migration provenance is not an applied receipt bound to its path"
        )
    if Path(str(payload.get("dataOutputRoot", ""))).expanduser().resolve() != data_output_root:
        raise ProtectedQuarantineEvidenceError(
            "migration apply receipt belongs to a different Data output root"
        )
    quarantine_entries = [
        entry
        for entry in payload.get("entries", [])
        if isinstance(entry, Mapping)
        and entry.get("sourceRef") == "quarantine"
        and entry.get("destinationRef") == "local/workspace/quarantine"
    ]
    if len(quarantine_entries) != 1:
        raise ProtectedQuarantineEvidenceError(
            "migration apply receipt does not bind quarantine -> local/workspace/quarantine"
        )
    migration_entry = quarantine_entries[0]
    return {
        "migrationApplyReceiptRef": relative,
        "migrationApplyReceiptSha256": _sha256_bytes(body),
        "migrationPlanDigest": plan_digest,
        "migrationSourceRef": "quarantine",
        "migrationDestinationRef": "local/workspace/quarantine",
        "migrationEntryFileCount": int(migration_entry["fileCount"]),
        "migrationEntryByteCount": int(migration_entry["byteCount"]),
        "migrationEntryDigest": str(migration_entry["digest"]),
    }


#: migration 变体的冻结字段集不可变动:变动会改变既有 receipt 的 manifestDigest。
_MIGRATION_MANIFEST_KEYS = (
    "schema",
    "status",
    "quarantineRef",
    "reason",
    "reusableSourceTruthAllowed",
    "migrationApplyReceiptRef",
    "migrationApplyReceiptSha256",
    "migrationPlanDigest",
    "migrationSourceRef",
    "migrationDestinationRef",
    "migrationEntryFileCount",
    "migrationEntryByteCount",
    "migrationEntryDigest",
    "directories",
    "files",
    "symlinks",
    "directoryCount",
    "fileCount",
    "symlinkCount",
    "byteCount",
    "treeDigest",
)
_FORENSIC_MANIFEST_KEYS = (
    "schema",
    "status",
    "provenance",
    "quarantineRef",
    "reason",
    "reusableSourceTruthAllowed",
    "forensicMarkerPath",
    "forensicMarkerSha256",
    "forensicDecision",
    "forensicConsumption",
    "forensicRecovery",
    "directories",
    "files",
    "symlinks",
    "directoryCount",
    "fileCount",
    "symlinkCount",
    "byteCount",
    "treeDigest",
)


def _stable_manifest(payload: Mapping[str, object]) -> dict[str, object]:
    keys = (
        _FORENSIC_MANIFEST_KEYS
        if payload.get("provenance") == "forensic"
        else _MIGRATION_MANIFEST_KEYS
    )
    return {key: payload[key] for key in keys}


def validate_protected_quarantine_receipt(
    receipt_path: Path,
    *,
    data_output_root: Path = DATA_OUTPUT_ROOT,
) -> tuple[dict[str, object], Path]:
    root = data_output_root.expanduser().resolve()
    path = receipt_path.expanduser().resolve()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert_valid(
            payload,
            "governance",
            "protected_quarantine_evidence",
            label=SCHEMA,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ProtectedQuarantineEvidenceError(
            f"protected quarantine receipt is invalid: {path}: {exc}"
        ) from exc
    manifest_digest = str(payload["manifestDigest"])
    expected_path = (
        root
        / RECEIPT_DIRECTORY
        / manifest_digest.removeprefix("sha256:")
        / "receipt.json"
    )
    if path != expected_path:
        raise ProtectedQuarantineEvidenceError(
            "protected quarantine receipt path does not match manifestDigest"
        )
    quarantine_root = root / str(payload["quarantineRef"])
    if payload.get("provenance") == "forensic":
        if (
            _forensic_quarantine_ref(quarantine_root, data_output_root=root)
            != payload["quarantineRef"]
        ):
            raise ProtectedQuarantineEvidenceError(
                "quarantine reference is not canonical"
            )
        provenance = _validate_forensic_marker(quarantine_root)
    else:
        if (
            _quarantine_ref(quarantine_root, data_output_root=root)
            != payload["quarantineRef"]
        ):
            raise ProtectedQuarantineEvidenceError(
                "quarantine reference is not canonical"
            )
        provenance = _validate_migration_receipt(
            root / str(payload["migrationApplyReceiptRef"]),
            data_output_root=root,
        )
    for key, value in provenance.items():
        if payload.get(key) != value:
            raise ProtectedQuarantineEvidenceError(
                f"protected quarantine provenance drift: {key}"
            )
    current_tree = _tree_inventory(quarantine_root)
    for key, value in current_tree.items():
        if payload.get(key) != value:
            raise ProtectedQuarantineEvidenceError(
                f"protected quarantine tree drift: {key}"
            )
    if _canonical_digest(_stable_manifest(payload)) != manifest_digest:
        raise ProtectedQuarantineEvidenceError(
            "protected quarantine manifest digest mismatch"
        )
    return payload, quarantine_root


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


def protect_historical_quarantine(
    *,
    quarantine_root: Path,
    migration_apply_receipt: Path,
    data_output_root: Path = DATA_OUTPUT_ROOT,
    reason: str = DEFAULT_REASON,
) -> tuple[dict[str, object], Path]:
    root = data_output_root.expanduser().resolve()
    normalized_reason = str(reason).strip()
    if not normalized_reason:
        raise ProtectedQuarantineEvidenceError("protection reason must not be empty")
    quarantine_candidate = quarantine_root.expanduser()
    quarantine_ref = _quarantine_ref(quarantine_candidate, data_output_root=root)
    quarantine_path = quarantine_candidate.resolve()
    tree = _tree_inventory(quarantine_path)
    migration_receipt_path = migration_apply_receipt.expanduser()
    provenance = _validate_migration_receipt(
        migration_receipt_path,
        data_output_root=root,
    )
    return _issue_protection_receipt(
        root=root,
        quarantine_path=quarantine_path,
        quarantine_ref=quarantine_ref,
        provenance=provenance,
        tree=tree,
        reason=normalized_reason,
        recheck_provenance=lambda: _validate_migration_receipt(
            migration_receipt_path,
            data_output_root=root,
        ),
        provenance_drift_message=(
            "migration provenance drifted while the receipt was being created"
        ),
    )


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
    "DEFAULT_REASON",
    "FORENSIC_DEFAULT_REASON",
    "FORENSIC_MARKER_NAME",
    "FORENSIC_REQUIRED_CONSUMPTION",
    "FORENSIC_REQUIRED_RECOVERY",
    "ProtectedQuarantineEvidenceError",
    "load_protected_quarantine_receipts",
    "protect_forensic_quarantine",
    "protect_historical_quarantine",
    "validate_protected_quarantine_receipt",
]
