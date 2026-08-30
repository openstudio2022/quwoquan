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


def partition_count(work_unit_count: int) -> int:
    """Return logical hash topology for the exact frozen work-unit count.

    Partitions isolate queue/checkpoint state; they are not worker capacity and
    therefore must not be multiplied by a configured per-worker resource ratio.

    The governed bands live in ``schema/execution/data_content_fleet_request``
    and are implemented on the Service side by ``data_fleet.go``'s
    ``dataContentPartitionCount``; both implementations are pinned to that
    single declaration by local_contract tests.
    """
    if isinstance(work_unit_count, bool) or not isinstance(work_unit_count, int):
        raise TypeError("work unit count must be an integer")
    if work_unit_count < 1:
        raise ValueError("work unit count must be positive")
    requested = max(MIN_PARTITION_COUNT, work_unit_count)
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
