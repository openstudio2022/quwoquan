"""Audited remote-ledger reconciliation for idempotent publish completion."""
from __future__ import annotations

import os
from collections.abc import Mapping

from core.control_types import QueueBackend, QueueJobStage, QueueJobState
from core.io import read_json
from core.paths import OUTPUT_ROOT, PUBLISH_ROOT, REPO_ROOT
from core.schema import assert_valid

from content.execution.queue.core import _load_jobs
from content.execution.queue.reliabletask.attempt import (
    attempt_evidence_dir,
    select_or_freeze_job_set_attempt,
)
from content.execution.queue.reliabletask.fleet_host_binding import (
    fleet_job_document,
    require_fleet_carrier,
)
from content.execution.queue.reliabletask.report import ReliableTaskFleetReport


def reconcile_frozen_publish_recovery(
    execution_id: str,
    *,
    workers: int,
    completion_grace_seconds: int,
) -> ReliableTaskFleetReport | None:
    """Reconcile remote dead tasks after every local publish job succeeded."""

    from content.execution.queue.reliabletask import fleet as runtime

    if workers < 1 or completion_grace_seconds < 1:
        raise ValueError("ReliableTask reconciliation budgets must be positive")
    stage = QueueJobStage.PUBLISH
    jobs = [
        job
        for job in _load_jobs(execution_id)
        if job.backend is QueueBackend.RELIABLE_TASK and job.stage is stage
    ]
    if not jobs or any(job.state is not QueueJobState.SUCCEEDED for job in jobs):
        return None
    if not runtime._has_audited_remote_recovery(execution_id, stage):
        return None
    require_fleet_carrier(execution_id, jobs)
    active_documents = [
        fleet_job_document(job) for job in sorted(jobs, key=lambda item: item.job_id)
    ]
    job_set_envelope = select_or_freeze_job_set_attempt(
        execution_id,
        stage.value,
        required_workers=workers,
        active_tasks=active_documents,
    )
    frozen_tasks = job_set_envelope.get("expectedTasks")
    if not isinstance(frozen_tasks, list) or not frozen_tasks:
        raise ValueError("ReliableTask frozen reconciliation tasks are invalid")
    evidence_dir = attempt_evidence_dir(execution_id, job_set_envelope)
    request_path = evidence_dir / "recovery-request.json"
    prior_report_path = evidence_dir / "report.json"
    if not request_path.is_file() or not prior_report_path.is_file():
        return None
    request = read_json(request_path)
    assert_valid(
        request,
        "execution",
        "data_content_fleet_request",
        label="data_content_fleet_reconciliation_request",
    )
    if (
        request.get("executionId") != execution_id
        or request.get("recoverDeadTasks") is not True
        or request.get("jobs") != frozen_tasks
        or request.get("jobSetEnvelopeDigest")
        != job_set_envelope.get("envelopeDigest")
        or request.get("jobSetDigest") != job_set_envelope.get("jobSetDigest")
    ):
        raise ValueError("ReliableTask frozen reconciliation request identity drift")
    prior_report = _read_bound_report(
        prior_report_path,
        execution_id=execution_id,
        request=request,
        label="reliabletask_fleet_reconciliation_prior_report",
    )
    if prior_report.passed:
        return prior_report
    if not prior_report.outcomes or any(
        outcome.status != "dead" for outcome in prior_report.outcomes
    ):
        raise ValueError("ReliableTask reconciliation requires an exact dead receipt")

    report_path = evidence_dir / "reconciliation-report-001.json"
    if report_path.is_file():
        report = _read_bound_report(
            report_path,
            execution_id=execution_id,
            request=request,
            label="reliabletask_fleet_reconciliation_report",
        )
        if report.passed:
            return report
        raise ValueError("ReliableTask frozen reconciliation remains below quota")

    object_timeout_milliseconds = request.get("objectTimeoutMilliseconds")
    if not isinstance(object_timeout_milliseconds, int):
        raise TypeError("ReliableTask reconciliation object timeout is invalid")
    batch_timeout_seconds = runtime.fleet_batch_timeout_seconds(
        job_count=len(active_documents),
        workers=int(request["requiredWorkers"]),
        object_timeout_seconds=object_timeout_milliseconds // 1000,
        completion_grace_seconds=completion_grace_seconds,
    )
    transport = runtime.resolve_reliabletask_fleet_transport()
    command, cwd = runtime._fleet_command(execution_id, stage=stage)
    environment = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "QWQ_DATA_FLEET_MONGO_URI": transport.mongo_uri,
        "QWQ_DATA_FLEET_REDIS_ADDR": transport.redis_addr,
        "QWQ_DATA_FLEET_PYTHON": str(runtime._fleet_agent_python()),
        "QWQ_DATA_FLEET_SCRIPTS_ROOT": str(REPO_ROOT / "quwoquan_data/scripts"),
        "QWQ_DATA_FLEET_WORK_DIR": str(REPO_ROOT / "quwoquan_data"),
        "QWQ_DATA_FLEET_PUBLISH_ROOT": str(PUBLISH_ROOT),
        "QWQ_DATA_FLEET_EVIDENCE_ROOT": str(OUTPUT_ROOT),
        "QWQ_DATA_FLEET_WORKERS": str(request["requiredWorkers"]),
        "QWQ_DATA_FLEET_BATCH_TIMEOUT_MS": str(batch_timeout_seconds * 1000),
    }
    returncode = runtime._run_fleet_process(
        [*command, "--request", str(request_path), "--report", str(report_path)],
        cwd=cwd,
        environment=environment,
    )
    if not report_path.is_file():
        raise RuntimeError(
            "ReliableTask reconciliation did not produce a report "
            f"(exit={returncode})"
        )
    report = _read_bound_report(
        report_path,
        execution_id=execution_id,
        request=request,
        label="reliabletask_fleet_reconciliation_report",
    )
    if not report.passed:
        raise ValueError("ReliableTask frozen reconciliation did not reach quota")
    return report


def _read_bound_report(
    path: object,
    *,
    execution_id: str,
    request: Mapping[str, object],
    label: str,
) -> ReliableTaskFleetReport:
    document = read_json(path)
    assert_valid(document, "release", "reliabletask_fleet_report", label=label)
    report = ReliableTaskFleetReport.from_document(document)
    if (
        report.execution_id != execution_id
        or report.job_set_envelope_digest != request["jobSetEnvelopeDigest"]
        or report.job_set_digest != request["jobSetDigest"]
        or report.actual_task_digest != request["actualTaskDigest"]
    ):
        raise ValueError("ReliableTask reconciliation report identity drift")
    return report


__all__ = ["reconcile_frozen_publish_recovery"]
