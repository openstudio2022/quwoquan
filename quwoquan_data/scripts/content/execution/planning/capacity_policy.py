"""Pure governed capacity projection for one immutable execution policy."""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from content.execution.queue.partition import partition_count as workload_partition_count
from core.schema import assert_valid

WORKLOAD_PLAN_SCHEMA = "quwoquan_data.campaign_workload_plan"


def _calibration_plan_terms(capacity_calibration: Mapping[str, Any]) -> dict[str, Any]:
    """Project the calibration terms one workload plan digest commits to.

    `DEC-002` puts both concurrency ceilings and the receipt digest inside the
    plan so a ceiling that drifts between submission, claim and execution
    policy is caught by comparing digests. The freeze instant and its derived
    deadline stay out, which is what lets the same plan be re-derived from an
    already frozen payload.
    """
    if not isinstance(capacity_calibration, Mapping):
        raise TypeError("capacity calibration binding must be a mapping")
    digest = str(capacity_calibration.get("calibrationReceiptDigest") or "").strip()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError(
            "capacity calibration receipt digest must be a canonical sha256 digest"
        )
    frozen_capacity = capacity_calibration.get("frozenCapacity")
    if not isinstance(frozen_capacity, Mapping):
        raise ValueError("capacity calibration frozenCapacity is missing")
    ceilings: dict[str, int] = {}
    for field in ("autoResearchMaxConcurrentWorkers", "fleetMaxConcurrentWorkers"):
        value = frozen_capacity.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(
                f"capacity calibration frozenCapacity.{field} is invalid"
            )
        ceilings[field] = value
    return {"calibrationReceiptDigest": digest, **ceilings}


def workload_plan_document(
    *,
    target_scale: str,
    carrier: str,
    work_unit_count: int,
    capacity_calibration: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the stable workload-topology document a capacity digest commits to."""
    if isinstance(work_unit_count, bool) or not isinstance(work_unit_count, int):
        raise TypeError("work unit count must be an integer")
    if work_unit_count < 1:
        raise ValueError("workload requires at least one work unit")
    scale = str(target_scale or "").strip()
    normalized_carrier = str(carrier or "").strip()
    if not scale or not normalized_carrier:
        raise ValueError("workload plan requires targetScale and carrier")
    return {
        "schema": WORKLOAD_PLAN_SCHEMA,
        "targetScale": scale,
        "carrier": normalized_carrier,
        "workUnitCount": work_unit_count,
        **_calibration_plan_terms(capacity_calibration),
    }


def workload_plan_digest(plan: Mapping[str, Any]) -> str:
    """Digest one workload plan with the canonical envelope encoding."""
    encoded = json.dumps(
        dict(plan),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def derive_workload_capacity_fields(
    *,
    target_scale: str,
    carrier: str,
    work_unit_count: int,
    capacity_calibration: Mapping[str, Any],
    frozen_at_epoch_seconds: int,
) -> dict[str, Any]:
    """Derive the governed capacity fields from the exact frozen work-unit count.

    `requiredWorkers` is retired by `DEC-002`: the work-unit count already lives
    in `targetObjectCount`, and how many workers may run at once comes only from
    the calibration receipt. `partitionCount` still derives from the work-unit
    count because partitions isolate durable job identity and fencing rather
    than expressing concurrency. Deriving all of it here keeps the single
    execution facade and the campaign envelope on one capacity truth source.
    """
    from content.execution.planning.capacity_calibration import (
        freeze_capacity_source_binding,
    )

    plan = workload_plan_document(
        target_scale=target_scale,
        carrier=carrier,
        work_unit_count=work_unit_count,
        capacity_calibration=capacity_calibration,
    )
    return {
        "partitionCount": workload_partition_count(work_unit_count),
        "capacityPlanDigest": workload_plan_digest(plan),
        "capacityCalibration": freeze_capacity_source_binding(
            capacity_calibration,
            work_unit_count=work_unit_count,
            frozen_at_epoch_seconds=frozen_at_epoch_seconds,
        ),
        "workerHostSetBinding": None,
    }


def execution_capacity_policy_fields(
    *,
    target_scale: str,
    carrier: str,
    work_unit_count: int,
    capacity_calibration: Mapping[str, Any],
    frozen_at_epoch_seconds: int,
    worker_host_set_binding: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Freeze one executionPolicy capacity block at the execution freeze instant.

    The caller hands over the selected receipt binding, never a partition count
    or a plan digest: both are derived here so a spec cannot carry a digest that
    disagrees with its own work-unit count and calibration.
    """
    fields = derive_workload_capacity_fields(
        target_scale=target_scale,
        carrier=carrier,
        work_unit_count=work_unit_count,
        capacity_calibration=capacity_calibration,
        frozen_at_epoch_seconds=frozen_at_epoch_seconds,
    )
    binding = None
    if worker_host_set_binding is not None:
        binding = dict(worker_host_set_binding)
        assert_valid(
            binding,
            "execution",
            "governed_worker_host_binding",
            label="execution worker host-set binding",
        )
    return {**fields, "workerHostSetBinding": binding}


def frozen_capacity_calibration(
    capacity_calibration: Mapping[str, Any],
) -> dict[str, Any]:
    """Admit one already frozen executionPolicy capacity binding."""
    from content.execution.planning.capacity_calibration import (
        assert_execution_policy_capacity_binding,
    )

    binding = dict(capacity_calibration or {})
    assert_execution_policy_capacity_binding(binding)
    return binding


__all__ = [
    "WORKLOAD_PLAN_SCHEMA",
    "derive_workload_capacity_fields",
    "frozen_capacity_calibration",
    "execution_capacity_policy_fields",
    "workload_plan_digest",
    "workload_plan_document",
]
