"""Pure governed capacity projection for one immutable execution policy."""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from core.schema import assert_valid


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


__all__ = ["execution_capacity_policy_fields"]
