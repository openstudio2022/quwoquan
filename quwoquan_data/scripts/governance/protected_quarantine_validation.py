"""Canonical validation for protected quarantine evidence."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

from core.paths import DATA_OUTPUT_ROOT
from core.schema import assert_valid

SCHEMA = "quwoquan_data.protected_quarantine_evidence"
RECEIPT_DIRECTORY = Path("local/cache/protected-quarantines")
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
    return {key: payload[key] for key in _FORENSIC_MANIFEST_KEYS}


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
    if (
        _forensic_quarantine_ref(quarantine_root, data_output_root=root)
        != payload["quarantineRef"]
    ):
        raise ProtectedQuarantineEvidenceError(
            "quarantine reference is not canonical"
        )
    provenance = _validate_forensic_marker(quarantine_root)
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


