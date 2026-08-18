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


def workload_plan_document(
    *,
    target_scale: str,
    carrier: str,
    work_unit_count: int,
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
) -> dict[str, Any]:
    """Derive the governed capacity triple from the exact frozen work-unit count.

    These wire keys carry workload topology, not a resource ceiling: every
    candidate work unit may start, and partitions only isolate durable job
    identity and fencing. Deriving them keeps the single execution facade and
    the campaign envelope on one capacity truth source.
    """
    plan = workload_plan_document(
        target_scale=target_scale,
        carrier=carrier,
        work_unit_count=work_unit_count,
    )
    return {
        "requiredWorkers": work_unit_count,
        "partitionCount": workload_partition_count(work_unit_count),
        "capacityPlanDigest": workload_plan_digest(plan),
        "workerHostSetBinding": None,
    }


def execution_capacity_policy_fields(
    *,
    required_workers: int,
    partition_count: int,
    capacity_plan_digest: str,
    worker_host_set_binding: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if (
        isinstance(required_workers, bool)
        or not isinstance(required_workers, int)
        or required_workers < 1
    ):
        raise ValueError("requiredWorkers must be a positive integer")
    if partition_count not in {16, 32, 64, 128, 256}:
        raise ValueError("partitionCount must be a governed partition count")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", capacity_plan_digest):
        raise ValueError("capacityPlanDigest must be a canonical sha256 digest")
    binding = None
    if worker_host_set_binding is not None:
        binding = dict(worker_host_set_binding)
        assert_valid(
            binding,
            "execution",
            "governed_worker_host_binding",
            label="execution worker host-set binding",
        )
    return {
        "requiredWorkers": required_workers,
        "partitionCount": partition_count,
        "capacityPlanDigest": capacity_plan_digest,
        "workerHostSetBinding": binding,
    }


__all__ = [
    "WORKLOAD_PLAN_SCHEMA",
    "derive_workload_capacity_fields",
    "execution_capacity_policy_fields",
    "workload_plan_digest",
    "workload_plan_document",
]
