from dataclasses import replace

import pytest
from content.execution import store
from content.execution.queue.reliabletask.fleet_host_aggregate import (
    aggregate_host_fleet_reports,
)
from content.execution.queue.reliabletask.fleet_host_binding import (
    allocate_worker_host_quotas,
)
from content.execution.queue.reliabletask.fleet_multi_host import run_multi_host_fleet
from content.execution.queue.reliabletask.report import (
    ReliableTaskFleetOutcome,
    ReliableTaskFleetReport,
)
from content.execution.queue.reliabletask.worker import (
    DataContentWorkItem,
    _bound_actual_tasks,
)
from content.execution.runtime_contract import canonical_sha256
from core.control_types import QueueJobStage


def _fixture():
    tasks = [
        {"jobId": "job-a", "partitionKey": "0", "maxAttempts": 2},
        {"jobId": "job-b", "partitionKey": "1", "maxAttempts": 2},
    ]
    digest = "sha256:" + "1" * 64
    binding = {
        "hostSetId": "workers", "generation": 2,
        "fencingToken": "sha256:" + "2" * 64,
        "hostSetDigest": "sha256:" + "3" * 64,
        "hosts": [
            {"hostScopeId": "host-a"},
            {"hostScopeId": "host-b"},
        ],
    }
    job_set = {
        "executionId": "execution-1", "stage": "author",
        "envelopeDigest": digest, "jobSetDigest": "sha256:" + "4" * 64,
        "expectedTasks": tasks, "workerHostSetBinding": binding,
    }
    requests = {}
    reports = {}
    for index, host_id in enumerate(("host-a", "host-b")):
        host_tasks = [tasks[index]]
        actual = canonical_sha256(host_tasks)
        requests[host_id] = {
            "workerHostBinding": {
                "hostScopeId": host_id,
                "hostSetDigest": binding["hostSetDigest"],
                "generation": binding["generation"],
                "fencingToken": binding["fencingToken"],
            },
            "actualTaskDigest": actual,
            "globalRequiredQuota": 2,
            "requiredQuota": 1,
            "jobs": host_tasks,
        }
        reports[host_id] = ReliableTaskFleetReport(
            total=1,
            succeeded=1,
            outcomes=(ReliableTaskFleetOutcome(tasks[index]["jobId"], "succeeded", 1),),
            execution_id="execution-1",
            stage="author",
            job_set_envelope_digest=digest,
            job_set_digest=job_set["jobSetDigest"],
            actual_task_digest=actual,
            passed=True,
            required_quota=1,
        )
    return job_set, requests, reports


def _work_item(**overrides: object) -> DataContentWorkItem:
    payload: dict[str, object] = {
        "runtimeTaskId": "runtime-task-a",
        "jobId": "job-a",
        "executionId": "execution-1",
        "ref": "posts/homepage/a",
        "stage": "author",
        "partitionKey": "0",
        "entityRef": "entity/a",
        "carrier": "homepage",
        "sourceRevision": "sha256:" + "a" * 64,
        "idempotencyKey": "execution-1|entity/a|homepage|sha256:" + "a" * 64 + "|author",
        "jobSetEnvelopeDigest": "sha256:" + "b" * 64,
        "jobSetDigest": "sha256:" + "c" * 64,
        "actualTaskDigest": "sha256:" + "d" * 64,
        "maxAttempts": 2,
    }
    payload.update(overrides)
    return DataContentWorkItem.from_document(payload)


def test_host_aggregate_covers_each_job_exactly_once() -> None:
    job_set, requests, reports = _fixture()
    aggregate = aggregate_host_fleet_reports(job_set, requests, reports)
    assert aggregate.total == 2
    assert aggregate.succeeded == 2
    assert {row.job_id for row in aggregate.outcomes} == {"job-a", "job-b"}


def test_host_aggregate_rejects_missing_host_and_overlapping_jobs() -> None:
    job_set, requests, reports = _fixture()
    missing = dict(reports)
    missing.pop("host-b")
    with pytest.raises(ValueError, match="missing an assigned host"):
        aggregate_host_fleet_reports(job_set, requests, missing)

    requests["host-b"] = {
        **requests["host-b"],
        "jobs": requests["host-a"]["jobs"],
        "actualTaskDigest": requests["host-a"]["actualTaskDigest"],
    }
    reports["host-b"] = replace(
        reports["host-b"],
        outcomes=reports["host-a"].outcomes,
        actual_task_digest=reports["host-a"].actual_task_digest,
    )
    with pytest.raises(ValueError, match="missing or overlapping"):
        aggregate_host_fleet_reports(job_set, requests, reports)


def test_host_quota_is_allocated_once_across_sorted_assignments() -> None:
    tasks = [
        {
            "jobId": f"job-{index:03d}",
            "partitionKey": str(index // 90),
            "maxAttempts": 2,
        }
        for index in range(180)
    ]
    binding = {
        "hosts": [
            {"hostScopeId": "host-b", "partitionKeys": ["1"]},
            {"hostScopeId": "host-a", "partitionKeys": ["0"]},
        ]
    }
    assert allocate_worker_host_quotas(
        tasks,
        binding,
        global_required_quota=100,
    ) == {"host-a": 90, "host-b": 10}


def test_worker_actual_digest_uses_frozen_full_set_without_host_binding() -> None:
    tasks = [
        {"jobId": "job-a", "partitionKey": "0", "maxAttempts": 2},
        {"jobId": "job-b", "partitionKey": "1", "maxAttempts": 2},
    ]
    item = _work_item(actualTaskDigest=canonical_sha256(tasks))
    selected = _bound_actual_tasks(
        item,
        {"expectedTasks": tasks, "workerHostSetBinding": None},
    )
    assert selected == tasks
    assert canonical_sha256(selected) == item.actual_task_digest


def test_worker_actual_digest_uses_exact_host_partition_slice_and_fence() -> None:
    tasks = [
        {"jobId": "job-a", "partitionKey": "0", "maxAttempts": 2},
        {"jobId": "job-b", "partitionKey": "1", "maxAttempts": 2},
    ]
    binding = {
        "hostSetDigest": "sha256:" + "3" * 64,
        "generation": 2,
        "fencingToken": "sha256:" + "2" * 64,
        "hosts": [
            {"hostScopeId": "host-a", "partitionKeys": ["0"]},
            {"hostScopeId": "host-b", "partitionKeys": ["1"]},
        ],
    }
    item = _work_item(
        actualTaskDigest=canonical_sha256(tasks[:1]),
        workerHostSetDigest=binding["hostSetDigest"],
        workerHostGeneration=2,
        workerFencingToken=binding["fencingToken"],
        workerHostScopeId="host-a",
    )
    selected = _bound_actual_tasks(
        item,
        {"expectedTasks": tasks, "workerHostSetBinding": binding},
    )
    assert selected == tasks[:1]
    assert canonical_sha256(selected) == item.actual_task_digest
    with pytest.raises(ValueError, match="host-set fence mismatch"):
        _bound_actual_tasks(replace(item, worker_host_generation=3), {
            "expectedTasks": tasks,
            "workerHostSetBinding": binding,
        })


def test_multi_host_runtime_fails_without_audited_remote_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        store,
        "load_spec",
        lambda _execution_id: {
            "executionPolicy": {
                "workerHostSetBinding": {
                    "hosts": [
                        {"hostScopeId": "host-a"},
                        {"hostScopeId": "host-b"},
                    ]
                }
            }
        },
    )
    from core.data_issue import DataIssueCode, DataIssueError

    with pytest.raises(DataIssueError) as raised:
        run_multi_host_fleet(
            "20260810--travel-homepage-host-runtime--test-region--scale-001",
            QueueJobStage.AUTHOR,
            workers=2,
            completion_grace_seconds=1,
        )
    assert raised.value.issues[0].code is DataIssueCode.REMOTE_HOST_EXECUTOR_UNAVAILABLE
