"""Freeze one proven capacity calibration receipt into an execution policy.

`DEC-006` makes a create-once receipt the only legal source of the two
concurrency ceilings, the per-object wall clock and the completion grace. This
module is the projection side of that decision: it refuses a receipt whose
applicability does not cover the requesting host and Provider tier, and
projects the immutable `executionPolicy` binding that carries the values plus
their provenance. Proving the receipt itself belongs to
`capacity_calibration_receipt`.

Runtime never re-reads the receipt. Once `freeze_capacity_calibration_binding`
returns, the binding alone decides the ceilings and the absolute batch
deadline, so replacing the receipt cannot move the deadline of a batch that is
already running.
"""
from __future__ import annotations

import math
import platform
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.schema import load_schema, validate_strict

from content.execution.planning.capacity_calibration_receipt import (
    CapacityCalibrationError,
    load_capacity_calibration_receipt,
    resolve_capacity_calibration_ref,
    safe_calibration_ref,
)

RECEIPT_SCHEMA_ID = "quwoquan_data.governed_capacity_calibration_receipt"
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_FROZEN_CAPACITY_FIELDS = (
    "autoResearchMaxConcurrentWorkers",
    "fleetMaxConcurrentWorkers",
    "objectWallClockSeconds",
    "completionGraceSeconds",
)
# 存活阈值与容量上限分块冻结：两块各有自己的观测基础，任一块缺失都不得由另一块补齐。
_FROZEN_LIVENESS_FIELDS = (
    "sourceDiscoveryHeartbeatIntervalSeconds",
    "sourceDiscoveryHeartbeatStaleAfterSeconds",
)


def _frozen_liveness_values(
    payload: Mapping[str, Any],
    *,
    label: str,
) -> dict[str, int]:
    """Read the frozen liveness block, which never falls back to capacity values."""
    block = payload.get("frozenLiveness")
    if not isinstance(block, Mapping):
        raise CapacityCalibrationError(f"{label} frozenLiveness is missing")
    values: dict[str, int] = {}
    for field in _FROZEN_LIVENESS_FIELDS:
        value = block.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise CapacityCalibrationError(f"{label} frozenLiveness.{field} is invalid")
        values[field] = value
    if (
        values["sourceDiscoveryHeartbeatStaleAfterSeconds"]
        <= values["sourceDiscoveryHeartbeatIntervalSeconds"]
    ):
        raise CapacityCalibrationError(
            f"{label} frozenLiveness staleAfter must exceed the heartbeat interval"
        )
    return values


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


def assert_execution_policy_capacity_binding(binding: Mapping[str, Any]) -> None:
    """Admit one frozen executionPolicy binding: values plus freeze instant."""
    schema = load_schema(
        "execution",
        "governed_capacity_calibration_receipt",
    )["$defs"]["executionPolicyBinding"]
    issues = validate_strict(dict(binding), schema)
    if issues:
        raise CapacityCalibrationError(
            "execution policy capacity binding is invalid:\n  - "
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
    normalized_ref = safe_calibration_ref(receipt_ref)
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
        "frozenLiveness": _frozen_liveness_values(
            receipt,
            label="calibration receipt",
        ),
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
        "calibrationReceiptRef": safe_calibration_ref(receipt_ref),
        "calibrationReceiptDigest": receipt_digest,
        "applicability": {
            "hostClass": str(receipt["applicability"]["hostClass"]).strip(),
            "providerTier": str(receipt["applicability"]["providerTier"]).strip(),
        },
        "frozenCapacity": dict(values),
        "frozenLiveness": _frozen_liveness_values(
            receipt,
            label="calibration receipt",
        ),
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
    receipt_ref = safe_calibration_ref(
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
        "frozenLiveness": _frozen_liveness_values(
            source_binding,
            label="capacity calibration source binding",
        ),
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
    "assert_execution_policy_capacity_binding",
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
