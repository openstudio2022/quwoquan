"""Read one create-once capacity calibration receipt and prove its provenance.

`DEC-006` makes the receipt the only legal source of the concurrency ceilings,
the per-object wall clock, the completion grace and the source-discovery
liveness thresholds. This module owns the read-and-prove half of that
decision: resolving a governed receipt reference, refusing bytes that disagree
with the digest they carry, and walking the soak evidence closure so a receipt
cannot cite observations that have since moved.

The projection half — turning a proven receipt into an immutable
`executionPolicy` binding — lives in `capacity_calibration`.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core import paths
from core.schema import assert_valid


class CapacityCalibrationError(ValueError):
    """A calibration receipt is absent, digest-drifted, or out of scope."""


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def canonical_digest(payload: Mapping[str, Any], *, excluded: str) -> str:
    document = {
        key: value for key, value in payload.items() if key != excluded
    }
    encoded = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def safe_calibration_ref(ref: str) -> str:
    candidate = str(ref or "").strip()
    path = Path(candidate)
    if not candidate or path.is_absolute() or ".." in path.parts:
        raise CapacityCalibrationError(
            "calibration receipt reference must be a safe relative path"
        )
    return path.as_posix()


def resolve_capacity_calibration_ref(
    ref: str,
    *,
    owner_root: Path | None = None,
) -> Path:
    normalized = safe_calibration_ref(ref)
    allowed_prefixes = (
        "data/",
        "quwoquan_data/control_plane/_shared/capacity_calibration/",
    )
    if not normalized.startswith(allowed_prefixes):
        raise CapacityCalibrationError(
            "calibration receipt reference has no governed owner"
        )
    root = (
        owner_root
        if owner_root is not None
        else paths.REPO_ROOT
        if normalized.startswith("quwoquan_data/")
        else paths.OUTPUT_ROOT
    )
    path = (root / normalized).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise CapacityCalibrationError(
            "calibration receipt reference escapes its owner root"
        ) from exc
    return path


def _assert_calibration_evidence_closure(
    receipt: Mapping[str, Any],
    *,
    owner_root: Path | None = None,
) -> None:
    evidence_ref = str(receipt.get("soakEvidenceRef") or "").strip()
    evidence_path = resolve_capacity_calibration_ref(
        evidence_ref,
        owner_root=owner_root,
    )
    if evidence_path.is_symlink() or not evidence_path.is_file():
        raise CapacityCalibrationError(
            "capacity calibration evidence is missing"
        )
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert_valid(
            evidence,
            "execution",
            "governed_capacity_calibration_evidence",
            label="governed capacity calibration evidence",
        )
    except (OSError, TypeError, ValueError) as exc:
        raise CapacityCalibrationError(str(exc)) from exc
    expected_digest = canonical_digest(evidence, excluded="evidenceDigest")
    if (
        evidence.get("evidenceDigest") != expected_digest
        or receipt.get("soakEvidenceDigest") != expected_digest
    ):
        raise CapacityCalibrationError(
            "capacity calibration evidence digest drifted"
        )
    bindings: list[tuple[str, str]] = []
    for row in evidence.get("providerCandidates") or []:
        bindings.extend(
            (
                (str(row.get("reportRef") or ""), str(row.get("reportDigest") or "")),
                (
                    str(row.get("resourceSamplesRef") or ""),
                    str(row.get("resourceSamplesDigest") or ""),
                ),
            )
        )
    for row in evidence.get("fleetObservations") or []:
        bindings.append(
            (str(row.get("reportRef") or ""), str(row.get("reportDigest") or ""))
        )
    for row in evidence.get("objectTimingObservations") or []:
        bindings.append(
            (str(row.get("stateRef") or ""), str(row.get("stateDigest") or ""))
        )
    for ref, digest in bindings:
        bound_path = resolve_capacity_calibration_ref(
            ref,
            owner_root=owner_root,
        )
        if (
            bound_path.is_symlink()
            or not bound_path.is_file()
            or file_digest(bound_path) != digest
        ):
            raise CapacityCalibrationError(
                f"capacity calibration evidence binding drifted: {ref}"
            )


def load_capacity_calibration_receipt(
    path: Path,
    *,
    verify_evidence: bool = True,
    evidence_owner_root: Path | None = None,
) -> dict[str, Any]:
    """Read and self-verify one create-once calibration receipt.

    Fails closed on the two provenance failures `DEC-006` names: an absent
    receipt, and receipt bytes that disagree with the digest they carry.
    """
    receipt_path = Path(path)
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise CapacityCalibrationError(
            f"calibration receipt is missing: {receipt_path}"
        )
    try:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CapacityCalibrationError(
            f"calibration receipt is unreadable: {receipt_path}"
        ) from exc
    if not isinstance(payload, dict):
        raise CapacityCalibrationError(
            f"calibration receipt must be one JSON object: {receipt_path}"
        )
    try:
        assert_valid(
            payload,
            "execution",
            "governed_capacity_calibration_receipt",
            label="governed capacity calibration receipt",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise CapacityCalibrationError(str(exc)) from exc
    actual = canonical_digest(payload, excluded="receiptDigest")
    if payload.get("receiptDigest") != actual:
        raise CapacityCalibrationError(
            "calibration receipt digest drifted from its own bytes"
        )
    if verify_evidence:
        _assert_calibration_evidence_closure(
            payload,
            owner_root=evidence_owner_root,
        )
    return payload


__all__ = [
    "CapacityCalibrationError",
    "canonical_digest",
    "file_digest",
    "load_capacity_calibration_receipt",
    "resolve_capacity_calibration_ref",
    "safe_calibration_ref",
]
