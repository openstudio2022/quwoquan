"""Deterministic ReliableTask partition and checkpoint contracts."""
from __future__ import annotations

import hashlib
from collections.abc import Mapping

MIN_PARTITION_COUNT = 16
MAX_PARTITION_COUNT = 256
PARTITION_ALGORITHM = "sha256_carrier_object_ref_mod_v1"
CHECKPOINT_POLICY: Mapping[str, object] = {
    "mode": "partition_watermark",
    "scope": "execution_stage_partition",
    "cursor": "last_succeeded_job_id",
    "resume": "strictly_after_cursor",
    "store": "MongoStore",
    "fencing": "execution_job_set_digest",
    "everyFinalizedObjects": 100,
    "everySeconds": 900,
    "triggerMode": "first_reached",
}


def partition_count(required_workers: int) -> int:
    """Return the governed power-of-two partition count for one fleet."""
    from core.runtime_policy import active_runtime_policy

    if isinstance(required_workers, bool) or not isinstance(required_workers, int):
        raise TypeError("requiredWorkers must be an integer")
    if required_workers < 1:
        raise ValueError("requiredWorkers must be positive")
    requested = max(
        MIN_PARTITION_COUNT,
        active_runtime_policy().partitions_per_worker * required_workers,
    )
    if requested >= MAX_PARTITION_COUNT:
        return MAX_PARTITION_COUNT
    return 1 << (requested - 1).bit_length()


def partition_key(carrier: str, object_ref: str, count: int) -> str:
    """Project a content object into its immutable decimal partition key."""
    normalized_carrier = str(carrier or "").strip()
    normalized_ref = str(object_ref or "").strip()
    if not normalized_carrier or not normalized_ref:
        raise ValueError("carrier and objectRef are required for partitioning")
    if count not in {16, 32, 64, 128, 256}:
        raise ValueError("partitionCount must be a governed power of two")
    digest = hashlib.sha256(
        f"{normalized_carrier}{normalized_ref}".encode("utf-8")
    ).digest()
    return str(int.from_bytes(digest, byteorder="big", signed=False) % count)


def checkpoint_policy_document() -> dict[str, object]:
    """Return a copy so callers cannot mutate the governed constant."""
    return dict(CHECKPOINT_POLICY)


__all__ = [
    "CHECKPOINT_POLICY",
    "MAX_PARTITION_COUNT",
    "MIN_PARTITION_COUNT",
    "PARTITION_ALGORITHM",
    "checkpoint_policy_document",
    "partition_count",
    "partition_key",
]
