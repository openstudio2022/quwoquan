"""Load one governed capacity calibration receipt and freeze it into a policy.

`DEC-006` makes a create-once receipt the only legal source of the two
concurrency ceilings, the per-object wall clock and the completion grace. This
module is the read side of that decision: it verifies a receipt against its own
digest, refuses a receipt whose applicability does not cover the requesting
host and Provider tier, and projects the immutable `executionPolicy` binding
that carries the values plus their provenance.

Runtime never re-reads the receipt. Once `freeze_capacity_calibration_binding`
returns, the binding alone decides the ceilings and the absolute batch
deadline, so replacing the receipt cannot move the deadline of a batch that is
already running.
"""
from __future__ import annotations

import hashlib
import json
import math
import platform
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core import paths
from core.schema import assert_valid, load_schema, validate_strict

RECEIPT_SCHEMA_ID = "quwoquan_data.governed_capacity_calibration_receipt"
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_FROZEN_CAPACITY_FIELDS = (
    "autoResearchMaxConcurrentWorkers",
    "fleetMaxConcurrentWorkers",
    "objectWallClockSeconds",
    "completionGraceSeconds",
)


class CapacityCalibrationError(RuntimeError):
    """A calibration receipt is absent, digest-drifted, or out of scope."""


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _canonical_digest(payload: Mapping[str, Any], *, excluded: str) -> str:
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


def _safe_relative_ref(ref: str) -> str:
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
    normalized = _safe_relative_ref(ref)
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
    expected_digest = _canonical_digest(evidence, excluded="evidenceDigest")
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
            or _file_digest(bound_path) != digest
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
    actual = _canonical_digest(payload, excluded="receiptDigest")
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


def current_host_class() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "darwin" and machine in {"arm64", "aarch64"}:
        return "local-apple-silicon"
    if system == "linux" and machine in {"x86_64", "amd64"}:
        return "linux-x86-64"
    if not system or not machine:
        raise CapacityCalibrationError("runtime host class is unavailable")
    return f"{system}-{machine}"


def assert_calibration_applies(
    receipt: Mapping[str, Any],
    *,
    host_class: str,
    provider_tier: str,
) -> None:
    """Refuse a receipt whose declared scope does not cover this execution."""
    applicability = receipt.get("applicability")
    if not isinstance(applicability, Mapping):
        raise CapacityCalibrationError(
            "calibration receipt applicability is missing"
        )
    requested = (str(host_class).strip(), str(provider_tier).strip())
    if not all(requested):
        raise CapacityCalibrationError(
            "capacity calibration requires hostClass and providerTier"
        )
    declared = (
        str(applicability.get("hostClass") or "").strip(),
        str(applicability.get("providerTier") or "").strip(),
    )
    if declared != requested:
        raise CapacityCalibrationError(
            "calibration receipt does not apply to "
            f"hostClass={requested[0]} providerTier={requested[1]}"
        )


def calibration_wave_count(
    *,
    work_unit_count: int,
    fleet_max_concurrent_workers: int,
) -> int:
    """Derive the wave count from job count and the frozen fleet ceiling.

    Scale only adds waves: the ceiling caps how many workers run at once, so
    growing the job count never widens concurrency. Quota is not an input.
    """
    if isinstance(work_unit_count, bool) or not isinstance(work_unit_count, int):
        raise CapacityCalibrationError("work unit count must be an integer")
    if work_unit_count < 1:
        raise CapacityCalibrationError("wave count requires at least one work unit")
    if (
        isinstance(fleet_max_concurrent_workers, bool)
        or not isinstance(fleet_max_concurrent_workers, int)
        or fleet_max_concurrent_workers < 1
    ):
        raise CapacityCalibrationError(
            "fleetMaxConcurrentWorkers must be a positive integer"
        )
    return math.ceil(work_unit_count / fleet_max_concurrent_workers)


def assert_capacity_source_binding(binding: Mapping[str, Any]) -> None:
    schema = load_schema(
        "execution",
        "governed_capacity_calibration_receipt",
    )["$defs"]["sourceBinding"]
    issues = validate_strict(dict(binding), schema)
    if issues:
        raise CapacityCalibrationError(
            "capacity calibration source binding is invalid:\n  - "
            + "\n  - ".join(issues[:20])
        )


def bind_capacity_calibration_source(
    *,
    receipt_path: Path,
    receipt_ref: str,
    host_class: str,
    provider_tier: str,
) -> dict[str, Any]:
    """Load one receipt and freeze only the facts known before target selection."""
    normalized_ref = _safe_relative_ref(receipt_ref)
    resolved_path = receipt_path.expanduser().resolve()
    owner_root = resolved_path
    for _part in Path(normalized_ref).parts:
        owner_root = owner_root.parent
    if (owner_root / normalized_ref).resolve() != resolved_path:
        raise CapacityCalibrationError(
            "capacity calibration receipt path and ref disagree"
        )
    receipt = load_capacity_calibration_receipt(
        resolved_path,
        evidence_owner_root=owner_root,
    )
    assert_calibration_applies(
        receipt,
        host_class=host_class,
        provider_tier=provider_tier,
    )
    frozen_capacity = receipt.get("frozenCapacity")
    if not isinstance(frozen_capacity, Mapping):
        raise CapacityCalibrationError(
            "calibration receipt frozenCapacity is missing"
        )
    values: dict[str, int] = {}
    for field in _FROZEN_CAPACITY_FIELDS:
        value = frozen_capacity.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise CapacityCalibrationError(
                f"calibration receipt frozenCapacity.{field} is invalid"
            )
        values[field] = value
    binding = {
        "calibrationId": str(receipt["calibrationId"]).strip(),
        "calibrationReceiptRef": normalized_ref,
        "calibrationReceiptDigest": str(receipt["receiptDigest"]).strip(),
        "applicability": {
            "hostClass": str(receipt["applicability"]["hostClass"]).strip(),
            "providerTier": str(receipt["applicability"]["providerTier"]).strip(),
        },
        "frozenCapacity": values,
    }
    assert_capacity_source_binding(binding)
    return binding


def freeze_capacity_calibration_binding(
    *,
    receipt: Mapping[str, Any],
    receipt_ref: str,
    host_class: str,
    provider_tier: str,
    work_unit_count: int,
    frozen_at_epoch_seconds: int,
) -> dict[str, Any]:
    """Project the immutable executionPolicy binding for one freeze instant.

    The absolute deadline is `DEC-003`'s single time authority: freeze instant
    plus wave count times the per-object wall clock plus the completion grace.
    Every term comes from the receipt, so no recovery path can extend a batch.
    """
    assert_calibration_applies(
        receipt,
        host_class=host_class,
        provider_tier=provider_tier,
    )
    if (
        isinstance(frozen_at_epoch_seconds, bool)
        or not isinstance(frozen_at_epoch_seconds, int)
        or frozen_at_epoch_seconds < 1
    ):
        raise CapacityCalibrationError(
            "freeze instant must be a positive epoch second"
        )
    receipt_digest = str(receipt.get("receiptDigest") or "").strip()
    if not _DIGEST.fullmatch(receipt_digest):
        raise CapacityCalibrationError(
            "calibration receipt digest must be a canonical sha256 digest"
        )
    frozen_capacity = receipt.get("frozenCapacity")
    if not isinstance(frozen_capacity, Mapping):
        raise CapacityCalibrationError(
            "calibration receipt frozenCapacity is missing"
        )
    values: dict[str, int] = {}
    for field in _FROZEN_CAPACITY_FIELDS:
        value = frozen_capacity.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise CapacityCalibrationError(
                f"calibration receipt frozenCapacity.{field} is invalid"
            )
        values[field] = value
    wave_count = calibration_wave_count(
        work_unit_count=work_unit_count,
        fleet_max_concurrent_workers=values["fleetMaxConcurrentWorkers"],
    )
    deadline = (
        frozen_at_epoch_seconds
        + wave_count * values["objectWallClockSeconds"]
        + values["completionGraceSeconds"]
    )
    calibration_id = str(receipt.get("calibrationId") or "").strip()
    if not calibration_id:
        raise CapacityCalibrationError("calibration receipt calibrationId is missing")
    return {
        "calibrationId": calibration_id,
        "calibrationReceiptRef": _safe_relative_ref(receipt_ref),
        "calibrationReceiptDigest": receipt_digest,
        "applicability": {
            "hostClass": str(receipt["applicability"]["hostClass"]).strip(),
            "providerTier": str(receipt["applicability"]["providerTier"]).strip(),
        },
        "frozenCapacity": dict(values),
        "frozenAtEpochSeconds": frozen_at_epoch_seconds,
        "waveCount": wave_count,
        "fleetBatchDeadlineEpochSeconds": deadline,
    }


def freeze_capacity_source_binding(
    source_binding: Mapping[str, Any],
    *,
    work_unit_count: int,
    frozen_at_epoch_seconds: int,
) -> dict[str, Any]:
    """Complete a pre-selection receipt binding at the execution freeze instant."""
    calibration_id = str(source_binding.get("calibrationId") or "").strip()
    receipt_ref = _safe_relative_ref(
        str(source_binding.get("calibrationReceiptRef") or "")
    )
    receipt_digest = str(
        source_binding.get("calibrationReceiptDigest") or ""
    ).strip()
    if not calibration_id or not _DIGEST.fullmatch(receipt_digest):
        raise CapacityCalibrationError(
            "capacity calibration source binding identity is invalid"
        )
    frozen_capacity = source_binding.get("frozenCapacity")
    applicability = source_binding.get("applicability")
    if not isinstance(frozen_capacity, Mapping) or not isinstance(
        applicability,
        Mapping,
    ):
        raise CapacityCalibrationError(
            "capacity calibration source binding is incomplete"
        )
    values: dict[str, int] = {}
    for field in _FROZEN_CAPACITY_FIELDS:
        value = frozen_capacity.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise CapacityCalibrationError(
                f"capacity calibration source binding {field} is invalid"
            )
        values[field] = value
    if (
        isinstance(frozen_at_epoch_seconds, bool)
        or not isinstance(frozen_at_epoch_seconds, int)
        or frozen_at_epoch_seconds < 1
    ):
        raise CapacityCalibrationError(
            "freeze instant must be a positive epoch second"
        )
    wave_count = calibration_wave_count(
        work_unit_count=work_unit_count,
        fleet_max_concurrent_workers=values["fleetMaxConcurrentWorkers"],
    )
    return {
        "calibrationId": calibration_id,
        "calibrationReceiptRef": receipt_ref,
        "calibrationReceiptDigest": receipt_digest,
        "applicability": dict(applicability),
        "frozenCapacity": values,
        "frozenAtEpochSeconds": frozen_at_epoch_seconds,
        "waveCount": wave_count,
        "fleetBatchDeadlineEpochSeconds": (
            frozen_at_epoch_seconds
            + wave_count * values["objectWallClockSeconds"]
            + values["completionGraceSeconds"]
        ),
    }


def remaining_batch_seconds(
    binding: Mapping[str, Any],
    *,
    now_epoch_seconds: int,
) -> int:
    """Project remaining batch time from the frozen absolute deadline.

    `DEC-003` makes this the only projection a lease, a restarted process or a
    rebuilt child may consume, which is why it clamps at zero instead of going
    negative.
    """
    deadline = binding.get("fleetBatchDeadlineEpochSeconds")
    if isinstance(deadline, bool) or not isinstance(deadline, int) or deadline < 1:
        raise CapacityCalibrationError(
            "execution policy binding is missing a frozen batch deadline"
        )
    if (
        isinstance(now_epoch_seconds, bool)
        or not isinstance(now_epoch_seconds, int)
        or now_epoch_seconds < 1
    ):
        raise CapacityCalibrationError("current time must be a positive epoch second")
    return max(0, deadline - now_epoch_seconds)


def lease_deadline_epoch_seconds(
    binding: Mapping[str, Any],
    *,
    now_epoch_seconds: int,
) -> int:
    """Take the smaller of the per-object window and the absolute deadline."""
    frozen_capacity = binding.get("frozenCapacity")
    if not isinstance(frozen_capacity, Mapping):
        raise CapacityCalibrationError(
            "execution policy binding is missing frozenCapacity"
        )
    wall_clock = frozen_capacity.get("objectWallClockSeconds")
    if (
        isinstance(wall_clock, bool)
        or not isinstance(wall_clock, int)
        or wall_clock < 1
    ):
        raise CapacityCalibrationError(
            "execution policy binding objectWallClockSeconds is invalid"
        )
    remaining = remaining_batch_seconds(
        binding,
        now_epoch_seconds=now_epoch_seconds,
    )
    return now_epoch_seconds + min(wall_clock, remaining)


__all__ = [
    "RECEIPT_SCHEMA_ID",
    "CapacityCalibrationError",
    "assert_calibration_applies",
    "assert_capacity_source_binding",
    "bind_capacity_calibration_source",
    "calibration_wave_count",
    "current_host_class",
    "freeze_capacity_calibration_binding",
    "freeze_capacity_source_binding",
    "lease_deadline_epoch_seconds",
    "load_capacity_calibration_receipt",
    "remaining_batch_seconds",
    "resolve_capacity_calibration_ref",
]
