"""Pure host/partition slicing for one ReliableTask fleet request."""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from content.execution.identity import parse_execution_id


def fleet_job_document(job: object) -> dict[str, object]:
    from content.execution.queue.model import QueueJob

    if not isinstance(job, QueueJob):
        raise TypeError("ReliableTask fleet job 必须为 QueueJob")
    reliable_ref = job.reliable_task_ref_document()
    payload = reliable_ref.get("payload") if isinstance(reliable_ref, Mapping) else None
    if not isinstance(payload, Mapping):
        raise TypeError(f"ReliableTask job 缺 typed payload：{job.job_id}")
    fields = (
        "entityRef", "carrier", "sourceRevision", "idempotencyKey", "jobId",
        "executionId", "ref", "stage", "partitionKey",
    )
    document: dict[str, object] = {
        field: str(payload.get(field) or "").strip() for field in fields
    }
    missing = [field for field, value in document.items() if not value]
    if missing:
        raise ValueError(
            f"ReliableTask job payload 不完整：{job.job_id}: {', '.join(missing)}"
        )
    if isinstance(job.max_attempts, bool) or job.max_attempts < 1:
        raise ValueError(
            f"ReliableTask job maxAttempts 必须为正整数：{job.job_id}"
        )
    document["maxAttempts"] = job.max_attempts
    return document


def select_worker_host_slice(
    frozen_tasks: Sequence[Mapping[str, Any]],
    host_set_binding: object,
    *,
    host_scope_id: str | None,
    default_workers: int,
) -> tuple[list[Mapping[str, Any]], dict[str, Any] | None, int]:
    if host_set_binding is None:
        return list(frozen_tasks), None, default_workers
    if not isinstance(host_set_binding, Mapping):
        raise TypeError("ReliableTask worker host-set binding is invalid")
    requested_host = str(host_scope_id or "").strip()
    if not requested_host:
        raise ValueError(
            "DATA.AGENT.CAPACITY_SHORTFALL: governed fleet requires hostScopeId"
        )
    assignments = host_set_binding.get("hosts")
    matching = [
        row for row in assignments
        if isinstance(row, Mapping) and row.get("hostScopeId") == requested_host
    ] if isinstance(assignments, list) else []
    if len(matching) != 1:
        raise ValueError("governed fleet hostScopeId is not assigned to this lane")
    assignment = dict(matching[0])
    partitions = {str(value) for value in assignment["partitionKeys"]}
    jobs = [row for row in frozen_tasks if str(row.get("partitionKey")) in partitions]
    if not jobs:
        raise ValueError("governed fleet host assignment contains no executable jobs")
    binding = {
        "hostSetId": host_set_binding["hostSetId"],
        "generation": host_set_binding["generation"],
        "fencingToken": host_set_binding["fencingToken"],
        "hostSetDigest": host_set_binding["hostSetDigest"],
        "transportBinding": host_set_binding["transportBinding"],
        **assignment,
    }
    return jobs, binding, int(assignment["workerCount"])


def allocate_worker_host_quotas(
    frozen_tasks: Sequence[Mapping[str, Any]],
    host_set_binding: Mapping[str, Any],
    *,
    global_required_quota: int,
) -> dict[str, int]:
    """Allocate one global quota across host slices without duplication."""
    if global_required_quota < 1:
        raise ValueError("ReliableTask global required quota must be positive")
    assignments = host_set_binding.get("hosts")
    if not isinstance(assignments, list) or not assignments:
        raise ValueError("governed fleet has no assigned hosts")
    partition_owners: dict[str, str] = {}
    for raw in sorted(assignments, key=lambda row: str(row.get("hostScopeId") or "")):
        if not isinstance(raw, Mapping):
            raise TypeError("governed fleet host assignment is invalid")
        host_id = str(raw.get("hostScopeId") or "").strip()
        partitions = raw.get("partitionKeys")
        if not host_id or not isinstance(partitions, list) or not partitions:
            raise ValueError("governed fleet host assignment is incomplete")
        for value in partitions:
            partition = str(value)
            if partition in partition_owners:
                raise ValueError("governed fleet partition is assigned more than once")
            partition_owners[partition] = host_id
    task_counts: Counter[str] = Counter()
    for task in frozen_tasks:
        partition = str(task.get("partitionKey") or "")
        host_id = partition_owners.get(partition)
        if host_id is None:
            raise ValueError("governed fleet task partition has no assigned host")
        task_counts[host_id] += 1
    host_ids = tuple(sorted(set(partition_owners.values())))
    if any(task_counts[host_id] < 1 for host_id in host_ids):
        raise ValueError(
            "DATA.AGENT.CAPACITY_SHORTFALL: assigned host has no candidate task"
        )
    if global_required_quota < len(host_ids):
        raise ValueError(
            "DATA.AGENT.CAPACITY_SHORTFALL: remaining quota cannot admit every "
            "assigned host"
        )
    if global_required_quota > sum(task_counts.values()):
        raise ValueError(
            "DATA.AGENT.CAPACITY_SHORTFALL: global quota exceeds assigned tasks"
        )
    quotas = {host_id: 1 for host_id in host_ids}
    unallocated = global_required_quota - len(host_ids)
    for host_id in host_ids:
        added = min(unallocated, task_counts[host_id] - 1)
        quotas[host_id] += added
        unallocated -= added
    if unallocated:
        raise ValueError("governed fleet quota allocation is incomplete")
    return quotas


def require_fleet_carrier(execution_id: str, jobs: list[object]) -> str:
    from content.execution.queue.model import QueueJob

    expected = parse_execution_id(execution_id).content_type.value
    carriers = {
        job.carrier.value
        for job in jobs
        if isinstance(job, QueueJob) and job.carrier is not None
    }
    if len(carriers) != 1 or carriers != {expected} or not jobs:
        raise ValueError(
            f"ReliableTask fleet carrier 必须与 executionId 一致："
            f"expected={expected}, jobs={sorted(carriers)}"
        )
    return expected


__all__ = [
    "allocate_worker_host_quotas",
    "fleet_job_document",
    "require_fleet_carrier",
    "select_worker_host_slice",
]
