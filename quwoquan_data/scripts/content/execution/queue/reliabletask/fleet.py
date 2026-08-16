"""通过唯一 Data CLI 驱动 Mongo+Redis ReliableTask 内容 worker。"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path

from core.control_types import QueueBackend, QueueJobStage, QueueJobState
from core.io import read_json, write_json
from core.paths import OUTPUT_ROOT, PUBLISH_ROOT, REPO_ROOT
from core.python_environment import resolve_data_agent_python
from core.schema import assert_valid
from governance.coverage.distribution import (
    ProductLifecycleState,
    load_content_distribution_policy,
)

from content.execution.queue.backend import load_execution_queue_backend
from content.execution.queue.core import _load_jobs
from content.execution.queue.reliabletask.attempt import (
    attempt_evidence_dir,
    select_or_freeze_job_set_attempt,
    write_attempt_document_create_once,
)
from content.execution.queue.reliabletask.fleet_host_binding import (
    allocate_worker_host_quotas,
    fleet_job_document,
    require_fleet_carrier,
    select_worker_host_slice,
)
from content.execution.queue.reliabletask.report import ReliableTaskFleetReport
from content.execution.queue.reliabletask.transport import (
    ReliableTaskFleetTransport,
    _wait_for_fleet_transport,
    reliabletask_fleet_preflight,
    resolve_reliabletask_fleet_transport,
)
from content.execution.runtime_contract import canonical_sha256
from content.execution.runtime_evidence.reliabletask_process import (
    OBSERVER_BINARY_REF_ENV,
    OBSERVER_BINARY_SHA256_ENV,
    load_frozen_campaign_worker_binary_binding,
    load_frozen_observer_binary_binding,
)

_EXTRACTED_DEPENDENCIES = (signal,)

_RECOVERY_EXECUTION_STAGES_BY_QUEUE_STAGE = {
    QueueJobStage.AUTHOR: frozenset({"build_homepage", "post_author"}),
    QueueJobStage.PUBLISH: frozenset({"publish"}),
}


def _has_audited_remote_recovery(
    execution_id: str,
    stage: QueueJobStage,
) -> bool:
    """Permit DLQ revival only after the controller recorded recovery evidence."""
    from content.execution.support import load_execution_state

    accepted_stages = _RECOVERY_EXECUTION_STAGES_BY_QUEUE_STAGE.get(
        stage,
        frozenset({stage.value}),
    )
    state = load_execution_state(execution_id)
    for action in reversed(tuple(state.recovery_actions or ())):
        if not isinstance(action, Mapping):
            continue
        if str(action.get("stage") or "").strip() not in accepted_stages:
            continue
        if str(action.get("recoveredAt") or "").strip():
            return True
    return False


def _object_timeout_seconds(jobs: list[object]) -> int:
    from content.execution.queue.model import QueueJob

    if not jobs or not all(isinstance(job, QueueJob) for job in jobs):
        raise ValueError("ReliableTask fleet requires declared QueueJob values")
    values = {job.max_wall_clock_seconds for job in jobs}
    if len(values) != 1:
        raise ValueError("ReliableTask fleet jobs must share one object timeout")
    timeout_seconds = next(iter(values))
    if timeout_seconds < 1:
        raise ValueError("ReliableTask object timeout must be positive")
    return timeout_seconds


def _attempt_request_name(*, recover_dead_tasks: bool) -> str:
    """Keep audited recovery input separate from the immutable first attempt."""

    return "recovery-request.json" if recover_dead_tasks else "request.json"


def _remaining_quota(
    execution_id: str,
    stage: QueueJobStage,
    active_job_count: int,
) -> int:
    """Remaining approved quota this fleet invocation must still deliver.

    The batch gate admits on quota, never on全量成功, so the request carries the
    quota that is still outstanding for this stage.  Objects already accepted in
    an earlier invocation are subtracted; the oversampled surplus is free to fail.
    """
    from content.execution import store

    policy = store.load_spec(execution_id).get("executionPolicy") or {}
    approved = policy.get("approvedQuota")
    if isinstance(approved, bool) or not isinstance(approved, int) or approved < 1:
        raise ValueError(
            f"execution {execution_id} executionPolicy.approvedQuota is required"
        )
    already_accepted = sum(
        1
        for job in _load_jobs(execution_id)
        if job.backend is QueueBackend.RELIABLE_TASK
        and job.stage is stage
        and job.state is QueueJobState.SUCCEEDED
    )
    remaining = approved - already_accepted
    if remaining < 1:
        raise ValueError(
            f"execution {execution_id} 已达 {stage.value} 准出配额 "
            f"{approved}（已接受 {already_accepted}），无需再派发 fleet"
        )
    if remaining > active_job_count and stage is not QueueJobStage.PUBLISH:
        raise ValueError(
            f"候选池耗尽，区域实体供给不足：{stage.value} 剩余配额 {remaining} "
            f"超过待执行 job 数 {active_job_count}"
        )
    # Publication consumes the immutable review-qualified closure.  The
    # semantic approvedQuota is a milestone target, not authority to suppress
    # already qualified objects when the reviewed closure is partial.  Deliver
    # every frozen publish job and leave the remaining milestone gap to a new
    # source/semantic wave; author acquisition remains strict above.
    return min(remaining, active_job_count)


def build_fleet_request(
    execution_id: str,
    stage: QueueJobStage,
    *,
    required_workers: int,
    host_scope_id: str | None = None,
) -> dict[str, object]:
    recover_dead_tasks = _has_audited_remote_recovery(execution_id, stage)
    stage_jobs = [
        job
        for job in _load_jobs(execution_id)
        if job.backend is QueueBackend.RELIABLE_TASK and job.stage is stage
    ]
    jobs = [
        job
        for job in stage_jobs
        if job.state is not QueueJobState.SUCCEEDED
        and (recover_dead_tasks or job.state is not QueueJobState.DEAD)
    ]
    if not jobs:
        raise ValueError(
            f"execution 无待执行 ReliableTask {stage.value} jobs：{execution_id}"
        )
    require_fleet_carrier(execution_id, jobs)
    object_timeout_seconds = _object_timeout_seconds(jobs)
    backend_envelope = load_execution_queue_backend(execution_id)
    active_documents = [
        fleet_job_document(job) for job in sorted(jobs, key=lambda item: item.job_id)
    ]
    job_set_envelope = select_or_freeze_job_set_attempt(
        execution_id,
        stage.value,
        required_workers=required_workers,
        active_tasks=active_documents,
    )
    frozen_tasks = job_set_envelope.get("expectedTasks")
    if not isinstance(frozen_tasks, list):
        raise TypeError("ReliableTask frozen expectedTasks is invalid")
    request_jobs, worker_host_binding, request_workers = select_worker_host_slice(
        frozen_tasks,
        job_set_envelope.get("workerHostSetBinding"),
        host_scope_id=host_scope_id,
        default_workers=int(job_set_envelope["requiredWorkers"]),
    )
    global_required_quota = _remaining_quota(
        execution_id,
        stage,
        len(jobs),
    )
    required_quota = global_required_quota
    if worker_host_binding is not None:
        host_quotas = allocate_worker_host_quotas(
            frozen_tasks,
            job_set_envelope["workerHostSetBinding"],
            global_required_quota=global_required_quota,
        )
        required_quota = host_quotas[str(worker_host_binding["hostScopeId"])]
    actual_task_digest = canonical_sha256(request_jobs)
    request_name = _attempt_request_name(
        recover_dead_tasks=recover_dead_tasks,
    )
    request_path = attempt_evidence_dir(
        execution_id,
        job_set_envelope,
    ) / (
        f"hosts/{host_scope_id}/{request_name}" if worker_host_binding else request_name
    )
    if request_path.is_file():
        existing = read_json(request_path)
        assert_valid(
            existing,
            "execution",
            "data_content_fleet_request",
            label="data_content_fleet_request",
        )
        if (
            existing.get("jobSetEnvelopeDigest")
            != job_set_envelope.get("envelopeDigest")
            or existing.get("jobSetDigest") != job_set_envelope.get("jobSetDigest")
            or existing.get("actualTaskDigest") != actual_task_digest
            or existing.get("workerHostBinding") != worker_host_binding
            or existing.get("globalRequiredQuota") != global_required_quota
            or existing.get("requiredQuota") != required_quota
            or existing.get("jobs") != request_jobs
            or existing.get("recoverDeadTasks") is not recover_dead_tasks
        ):
            raise ValueError("ReliableTask attempt request identity drift")
        return existing
    payload: dict[str, object] = {
        "schema": "quwoquan.data_content_fleet_request",
        "executionId": execution_id,
        "campaignScale": backend_envelope["campaignScale"],
        "scaleClass": backend_envelope["scaleClass"],
        "executionEnvelopeDigest": backend_envelope["envelopeDigest"],
        "jobSetEnvelopeDigest": job_set_envelope["envelopeDigest"],
        "jobSetDigest": job_set_envelope["jobSetDigest"],
        "actualTaskDigest": actual_task_digest,
        "requiredWorkers": request_workers,
        "partitionCount": job_set_envelope["partitionCount"],
        "partitionAlgorithm": job_set_envelope["partitionAlgorithm"],
        "checkpointPolicy": job_set_envelope["checkpointPolicy"],
        "requireCommercial": (
            stage is QueueJobStage.PUBLISH
            and load_content_distribution_policy().product_lifecycle_state
            is ProductLifecycleState.COMMERCIAL
        ),
        "recoverDeadTasks": recover_dead_tasks,
        "objectTimeoutMilliseconds": object_timeout_seconds * 1000,
        "globalRequiredQuota": global_required_quota,
        "requiredQuota": required_quota,
        "jobs": request_jobs,
    }
    if worker_host_binding is not None:
        payload["workerHostBinding"] = worker_host_binding
    campaign_binding = job_set_envelope.get("campaignBinding")
    if campaign_binding is not None:
        if not isinstance(campaign_binding, Mapping):
            raise TypeError("ReliableTask campaign pool delivery binding is invalid")
        payload["campaignBinding"] = dict(campaign_binding)
    assert_valid(
        payload,
        "execution",
        "data_content_fleet_request",
        label="data_content_fleet_request",
    )
    return payload


def _fleet_command(
    execution_id: str,
    *,
    stage: QueueJobStage | None = None,
) -> tuple[list[str], Path]:
    # A campaign capsule deliberately excludes Service implementation source.
    # The controller already freezes the exact data-content-worker executable
    # (the same command exposes both the read-only observer and fleet modes),
    # so a lane must consume that attested binary instead of falling back to
    # ``go run`` against an incomplete capsule tree.  A partial binding fails
    # closed through ``load_frozen_observer_binary_binding``.
    if stage is QueueJobStage.PUBLISH:
        from content.execution.preflight.pool_delivery import (
            load_current_pool_delivery_preflight_receipt,
        )
        from content.execution.runtime_evidence.reliabletask_process import (
            ReliableTaskObserverBinaryBinding,
            validate_frozen_observer_binary,
        )

        receipt, _path = load_current_pool_delivery_preflight_receipt(execution_id)
        binding = ReliableTaskObserverBinaryBinding(
            ref=str(receipt["workerRef"]),
            sha256=str(receipt["workerSha256"]),
        )
        return [str(validate_frozen_observer_binary(binding))], REPO_ROOT
    if any(
        str(os.environ.get(name) or "").strip()
        for name in (OBSERVER_BINARY_REF_ENV, OBSERVER_BINARY_SHA256_ENV)
    ):
        backend_envelope = load_execution_queue_backend(execution_id)
        binding = (
            load_frozen_observer_binary_binding()
            if backend_envelope.get("scaleClass") in {"M100_PLUS", "M10000_PLUS"}
            else load_frozen_campaign_worker_binary_binding()
        )
        return [str(validate_frozen_observer_binary(binding))], REPO_ROOT
    binary = str(os.environ.get("QWQ_DATA_FLEET_BINARY") or "").strip()
    service_root = REPO_ROOT / "quwoquan_service"
    if binary:
        return [binary], service_root
    return [
        "go",
        "run",
        "./services/content-service/cmd/data-content-worker",
    ], service_root


def _fleet_agent_python() -> Path:
    """Resolve the verified Data runtime instead of inheriting caller Python."""
    python = resolve_data_agent_python(include_current=False)
    if python is None:
        raise RuntimeError(
            "ReliableTask fleet 找不到包含 Agent 依赖的 Data Python；"
            "先运行 `qwq-data task preflight` 重建仓外工具缓存"
        )
    return python


def fleet_batch_timeout_seconds(
    *,
    job_count: int,
    workers: int,
    object_timeout_seconds: int,
    completion_grace_seconds: int,
) -> int:
    """Derive one bounded fleet deadline from immutable object budgets."""
    if job_count < 1 or workers < 1:
        raise ValueError("ReliableTask fleet job_count and workers must be positive")
    if object_timeout_seconds < 1 or completion_grace_seconds < 1:
        raise ValueError("ReliableTask fleet time budgets must be positive")
    waves = (job_count + workers - 1) // workers
    return waves * object_timeout_seconds + completion_grace_seconds


def _terminate_fleet_process(process: subprocess.Popen[object]) -> None:
    from content.execution.queue.reliabletask.fleet_process import (
        _terminate_fleet_process as implementation,
    )

    return implementation(process)


def _run_fleet_process(
    command: list[str], *, cwd: Path, environment: Mapping[str, str]
) -> int:
    from content.execution.queue.reliabletask.fleet_process import (
        _run_fleet_process as implementation,
    )

    return implementation(command, cwd=cwd, environment=environment)


def discard_reliabletask_execution(execution_id: str) -> None:
    """Delete the service-owned task state of one already stopped execution."""
    transport = resolve_reliabletask_fleet_transport()
    command, cwd = _fleet_command(execution_id)
    environment = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "QWQ_DATA_FLEET_MONGO_URI": transport.mongo_uri,
        "QWQ_DATA_FLEET_REDIS_ADDR": transport.redis_addr,
    }
    returncode = _run_fleet_process(
        [
            *command,
            "--discard-execution",
            execution_id,
            "--confirm-discard",
        ],
        cwd=cwd,
        environment=environment,
    )
    if returncode != 0:
        raise RuntimeError(
            f"ReliableTask remote discard failed for executionId={execution_id}"
        )


def _run_reliabletask_host(
    execution_id: str,
    stage: QueueJobStage,
    *,
    workers: int,
    completion_grace_seconds: int,
    host_scope_id: str | None = None,
) -> ReliableTaskFleetReport:
    if workers < 1:
        raise ValueError("ReliableTask workers 必须为正整数")
    if completion_grace_seconds < 1:
        raise ValueError("ReliableTask completion grace 必须为正整数")
    transport = resolve_reliabletask_fleet_transport()
    request = build_fleet_request(
        execution_id,
        stage,
        required_workers=workers,
        host_scope_id=host_scope_id,
    )
    object_timeout_milliseconds = request["objectTimeoutMilliseconds"]
    if not isinstance(object_timeout_milliseconds, int):
        raise TypeError("ReliableTask fleet request object timeout is invalid")
    batch_timeout_seconds = fleet_batch_timeout_seconds(
        job_count=len(request["jobs"]),
        workers=int(request["requiredWorkers"]),
        object_timeout_seconds=object_timeout_milliseconds // 1000,
        completion_grace_seconds=completion_grace_seconds,
    )
    evidence_dir = attempt_evidence_dir(
        execution_id,
        {
            "stage": stage.value,
            "jobSetDigest": request["jobSetDigest"],
        },
    )
    worker_binding = request.get("workerHostBinding")
    if isinstance(worker_binding, Mapping):
        evidence_dir = evidence_dir / "hosts" / str(worker_binding["hostScopeId"])
    request_path = evidence_dir / _attempt_request_name(
        recover_dead_tasks=bool(request.get("recoverDeadTasks")),
    )
    report_path = evidence_dir / "report.json"
    write_attempt_document_create_once(request_path, request)
    if report_path.is_file():
        existing_report = read_json(report_path)
        assert_valid(
            existing_report,
            "release",
            "reliabletask_fleet_report",
            label="reliabletask_fleet_report",
        )
        existing = ReliableTaskFleetReport.from_document(existing_report)
        exact_attempt = (
            existing.execution_id == execution_id
            and existing.stage == stage.value
            and existing.job_set_envelope_digest == request["jobSetEnvelopeDigest"]
            and existing.job_set_digest == request["jobSetDigest"]
            and existing.actual_task_digest == request["actualTaskDigest"]
        )
        if not exact_attempt:
            raise ValueError("ReliableTask fleet report attempt identity drift")
        if existing.passed or (
            not bool(request.get("recoverDeadTasks"))
            and all(
                outcome.status in {"succeeded", "dead"} for outcome in existing.outcomes
            )
        ):
            return existing
        write_attempt_document_create_once(
            evidence_dir / "runtime-report-000.json",
            existing_report,
        )
    command, cwd = _fleet_command(execution_id, stage=stage)
    environment = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "QWQ_DATA_FLEET_MONGO_URI": transport.mongo_uri,
        "QWQ_DATA_FLEET_REDIS_ADDR": transport.redis_addr,
        "QWQ_DATA_FLEET_PYTHON": str(_fleet_agent_python()),
        "QWQ_DATA_FLEET_SCRIPTS_ROOT": str(REPO_ROOT / "quwoquan_data/scripts"),
        "QWQ_DATA_FLEET_WORK_DIR": str(REPO_ROOT / "quwoquan_data"),
        "QWQ_DATA_FLEET_PUBLISH_ROOT": str(PUBLISH_ROOT),
        "QWQ_DATA_FLEET_EVIDENCE_ROOT": str(OUTPUT_ROOT),
        "QWQ_DATA_FLEET_WORKERS": str(request["requiredWorkers"]),
        "QWQ_DATA_FLEET_BATCH_TIMEOUT_MS": str(batch_timeout_seconds * 1000),
    }
    from core.runtime_policy import active_runtime_policy

    policy = active_runtime_policy()
    startup_failure_limit = policy.queue_max_startup_failures
    restart_deadline = time.monotonic() + min(
        batch_timeout_seconds,
        policy.campaign_lane_timeout_seconds_for_scale(str(request["campaignScale"])),
    )

    def wait_for_backend(startup_failures: int) -> None:
        print(
            "[data fleet] waiting for Mongo/Redis recovery before worker restart; "
            f"consecutive startup failures {startup_failures}/"
            f"{startup_failure_limit} for {execution_id}"
        )
        recovered = _wait_for_fleet_transport(
            transport,
            timeout_seconds=policy.startup_timeout_seconds,
            retry_delay_seconds=policy.preflight_retry_delay_seconds,
            socket_timeout_seconds=policy.preflight_network_timeout_seconds,
            required_ready_probes=policy.preflight_startup_attempts,
        )
        if not recovered:
            print(
                "[data fleet] Mongo/Redis recovery window elapsed; "
                f"continuing deadline-bounded recovery for {execution_id}"
            )

    run_attempt = 0
    consecutive_startup_failures = 0
    while time.monotonic() < restart_deadline:
        run_attempt += 1
        # A previous process may have left a valid nonterminal receipt.  Never
        # mistake it for the receipt of the new invocation.
        report_path.unlink(missing_ok=True)
        returncode = _run_fleet_process(
            [*command, "--request", str(request_path), "--report", str(report_path)],
            cwd=cwd,
            environment=environment,
        )
        if not report_path.is_file():
            consecutive_startup_failures += 1
            if consecutive_startup_failures >= startup_failure_limit:
                raise RuntimeError(
                    "ReliableTask fleet 未产出报告"
                    "（exit="
                    f"{returncode}, consecutiveStartupFailures="
                    f"{consecutive_startup_failures}, executionId={execution_id}）"
                )
            print(
                "[data fleet] worker exited without a receipt; "
                f"consecutive startup failures {consecutive_startup_failures}/"
                f"{startup_failure_limit} for {execution_id}"
            )
            wait_for_backend(consecutive_startup_failures)
            continue
        report = read_json(report_path)
        assert_valid(
            report,
            "release",
            "reliabletask_fleet_report",
            label="reliabletask_fleet_report",
        )
        decoded = ReliableTaskFleetReport.from_document(report)
        if (
            decoded.execution_id != execution_id
            or decoded.stage != stage.value
            or decoded.job_set_envelope_digest != request["jobSetEnvelopeDigest"]
            or decoded.job_set_digest != request["jobSetDigest"]
            or decoded.actual_task_digest != request["actualTaskDigest"]
        ):
            raise ValueError("ReliableTask fleet report attempt identity drift")
        all_terminal = all(
            outcome.status in {"succeeded", "dead"} for outcome in decoded.outcomes
        )
        if decoded.passed or all_terminal:
            return decoded
        attempt_report_path = evidence_dir / f"runtime-report-{run_attempt:03d}.json"
        write_json(attempt_report_path, report)
        # A worker that lived long enough to produce a valid durable-queue
        # receipt was not a startup failure.  Runtime interruptions may recur
        # during a long Auto batch, so only the campaign deadline bounds them.
        consecutive_startup_failures = 0
        print(
            "[data fleet] nonterminal receipt after worker interruption; "
            f"runtime restart {run_attempt} for {execution_id}"
        )
        wait_for_backend(consecutive_startup_failures)
    raise RuntimeError(
        "ReliableTask fleet recovery exceeded campaign deadline"
        f"（executionId={execution_id}）"
    )


def run_reliabletask_fleet(
    execution_id: str,
    stage: QueueJobStage,
    *,
    workers: int,
    completion_grace_seconds: int,
) -> ReliableTaskFleetReport:
    from content.execution.queue.reliabletask.fleet_multi_host import (
        run_multi_host_fleet,
    )

    return run_multi_host_fleet(
        execution_id,
        stage,
        workers=workers,
        completion_grace_seconds=completion_grace_seconds,
    )


__all__ = [
    "ReliableTaskFleetTransport",
    "build_fleet_request",
    "discard_reliabletask_execution",
    "fleet_batch_timeout_seconds",
    "reliabletask_fleet_preflight",
    "resolve_reliabletask_fleet_transport",
    "run_reliabletask_fleet",
]
