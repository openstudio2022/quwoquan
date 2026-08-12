"""Fail-closed aggregation of every host slice in one immutable job set."""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from content.execution.queue.reliabletask.report import ReliableTaskFleetReport
from content.execution.runtime_contract import canonical_sha256


def aggregate_host_fleet_reports(
    job_set: Mapping[str, Any],
    requests: Mapping[str, Mapping[str, Any]],
    reports: Mapping[str, ReliableTaskFleetReport],
) -> ReliableTaskFleetReport:
    binding = job_set.get("workerHostSetBinding")
    if not isinstance(binding, Mapping):
        raise TypeError("ReliableTask host aggregate requires workerHostSetBinding")
    assigned = binding.get("hosts")
    expected_hosts = {
        str(row.get("hostScopeId") or "")
        for row in assigned if isinstance(row, Mapping)
    } if isinstance(assigned, list) else set()
    if not expected_hosts or set(requests) != expected_hosts or set(reports) != expected_hosts:
        raise ValueError("ReliableTask host aggregate is missing an assigned host")
    expected_tasks = job_set.get("expectedTasks")
    if not isinstance(expected_tasks, list):
        raise TypeError("ReliableTask host aggregate expectedTasks is invalid")
    expected_job_ids = {str(row.get("jobId") or "") for row in expected_tasks}
    request_job_ids: list[str] = []
    report_outcomes = []
    decoded = []
    request_quotas: list[int] = []
    global_quotas: set[int] = set()
    for host_id in sorted(expected_hosts):
        request = requests[host_id]
        report = reports[host_id]
        worker = request.get("workerHostBinding")
        if (
            not isinstance(worker, Mapping)
            or worker.get("hostScopeId") != host_id
            or worker.get("hostSetDigest") != binding.get("hostSetDigest")
            or worker.get("generation") != binding.get("generation")
            or worker.get("fencingToken") != binding.get("fencingToken")
        ):
            raise ValueError("ReliableTask host aggregate worker identity drift")
        jobs = request.get("jobs")
        if not isinstance(jobs, list):
            raise TypeError("ReliableTask host request jobs are invalid")
        job_ids = [str(row.get("jobId") or "") for row in jobs]
        if canonical_sha256(jobs) != request.get("actualTaskDigest"):
            raise ValueError("ReliableTask host request actualTaskDigest drift")
        required_quota = request.get("requiredQuota")
        global_required_quota = request.get("globalRequiredQuota")
        if (
            isinstance(required_quota, bool)
            or not isinstance(required_quota, int)
            or not 1 <= required_quota <= len(jobs)
            or isinstance(global_required_quota, bool)
            or not isinstance(global_required_quota, int)
            or global_required_quota < 1
        ):
            raise ValueError("ReliableTask host request quota is invalid")
        if (
            report.job_set_envelope_digest != job_set.get("envelopeDigest")
            or report.job_set_digest != job_set.get("jobSetDigest")
            or report.actual_task_digest != request.get("actualTaskDigest")
            or report.required_quota != required_quota
            or {outcome.job_id for outcome in report.outcomes} != set(job_ids)
        ):
            raise ValueError("ReliableTask host report does not cover its exact request")
        request_job_ids.extend(job_ids)
        request_quotas.append(required_quota)
        global_quotas.add(global_required_quota)
        report_outcomes.extend(report.outcomes)
        decoded.append(report)
    counts = Counter(request_job_ids)
    if set(counts) != expected_job_ids or any(count != 1 for count in counts.values()):
        raise ValueError("ReliableTask host requests have missing or overlapping tasks")
    if len(global_quotas) != 1 or sum(request_quotas) != next(iter(global_quotas)):
        raise ValueError("ReliableTask host request quotas do not cover global quota")
    return ReliableTaskFleetReport(
        total=sum(row.total for row in decoded),
        succeeded=sum(row.succeeded for row in decoded),
        outcomes=tuple(report_outcomes),
        execution_id=str(job_set["executionId"]),
        stage=str(job_set["stage"]),
        job_set_envelope_digest=str(job_set["envelopeDigest"]),
        job_set_digest=str(job_set["jobSetDigest"]),
        actual_task_digest=canonical_sha256(expected_tasks),
        passed=all(row.passed for row in decoded),
        finalized_object_count=sum(row.finalized_object_count for row in decoded),
        required_quota=next(iter(global_quotas)),
        publish_task_count=sum(row.publish_task_count for row in decoded),
        object_transaction_result_count=sum(row.object_transaction_result_count for row in decoded),
        research_accepted_count=sum(row.research_accepted_count for row in decoded),
        commercial_accepted_count=sum(row.commercial_accepted_count for row in decoded),
        recovery_eligible_count=sum(row.recovery_eligible_count for row in decoded),
        automatic_recovered_count=sum(row.automatic_recovered_count for row in decoded),
        manual_recovered_count=sum(row.manual_recovered_count for row in decoded),
    )


__all__ = ["aggregate_host_fleet_reports"]
