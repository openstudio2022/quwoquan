"""通过唯一 Data CLI 驱动 Mongo+Redis ReliableTask 内容 worker。"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

from core.control_types import QueueBackend, QueueJobStage, QueueJobState
from core.io import read_json, write_json
from core.paths import OUTPUT_ROOT, PUBLISH_ROOT, REPO_ROOT, execution_root
from core.python_environment import resolve_data_agent_python
from core.schema import assert_valid
from content.execution.identity import parse_execution_id
from content.execution.queue.core import _load_jobs


_FLEET_TASK_STATUSES = frozenset(
    {"ready", "processing", "retry_wait", "succeeded", "dead"}
)
_FLEET_ACCEPTED_CONTENT_STATUSES = frozenset(
    {
        "MEASURED",
        "GATE_BLOCK_NO_COMMERCIAL_BATCH",
        "GATE_BLOCK_INCOMPLETE_COMMERCIAL_BATCH",
    }
)
_STACKCTL_PATH = REPO_ROOT / "quwoquan_ops" / "cli" / "stackctl.py"
_RECOVERY_EXECUTION_STAGES_BY_QUEUE_STAGE = {
    QueueJobStage.AUTHOR: frozenset({"build_homepage", "post_author"}),
    QueueJobStage.PUBLISH: frozenset({"publish"}),
}


@dataclass(frozen=True, slots=True)
class ReliableTaskFleetOutcome:
    job_id: str
    status: str
    attempts: int
    failure_code: str = ""

    @classmethod
    def from_document(cls, value: object) -> "ReliableTaskFleetOutcome":
        if not isinstance(value, Mapping):
            raise ValueError("ReliableTask fleet task outcome must be an object")
        job_id = str(value.get("jobId") or "").strip()
        status = str(value.get("status") or "").strip()
        failure_code = str(value.get("failureCode") or "").strip()
        try:
            attempts = int(value.get("attempts"))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "ReliableTask fleet task outcome attempts must be an integer"
            ) from exc
        if not job_id or status not in _FLEET_TASK_STATUSES or attempts < 0:
            raise ValueError("ReliableTask fleet task outcome is invalid")
        return cls(job_id, status, attempts, failure_code)


@dataclass(frozen=True, slots=True)
class ReliableTaskFleetReport:
    total: int
    succeeded: int
    outcomes: tuple[ReliableTaskFleetOutcome, ...]
    passed: bool = True
    accepted_content_throughput_status: str = "MEASURED"

    @classmethod
    def from_document(cls, value: object) -> "ReliableTaskFleetReport":
        if not isinstance(value, Mapping):
            raise ValueError("ReliableTask fleet report must be an object")
        try:
            total = int(value.get("total"))
            succeeded = int(value.get("succeeded"))
        except (TypeError, ValueError) as exc:
            raise ValueError("ReliableTask fleet report counts must be integers") from exc
        raw_outcomes = value.get("taskOutcomes")
        if not isinstance(raw_outcomes, list):
            raise ValueError("ReliableTask fleet report taskOutcomes must be an array")
        passed = value.get("passed")
        accepted_status = str(
            value.get("acceptedContentThroughputStatus") or ""
        ).strip()
        if not isinstance(passed, bool):
            raise ValueError("ReliableTask fleet report passed must be a boolean")
        if accepted_status not in _FLEET_ACCEPTED_CONTENT_STATUSES:
            raise ValueError(
                "ReliableTask fleet report accepted throughput status is invalid"
            )
        outcomes = tuple(ReliableTaskFleetOutcome.from_document(item) for item in raw_outcomes)
        if total < 1 or succeeded < 0 or len(outcomes) != total:
            raise ValueError("ReliableTask fleet report outcome count is invalid")
        if len({outcome.job_id for outcome in outcomes}) != len(outcomes):
            raise ValueError("ReliableTask fleet report contains duplicate job outcomes")
        return cls(
            total=total,
            succeeded=succeeded,
            outcomes=outcomes,
            passed=passed,
            accepted_content_throughput_status=accepted_status,
        )


@dataclass(frozen=True, slots=True)
class ReliableTaskFleetTransport:
    target: str
    mongo_uri: str
    redis_addr: str

    @classmethod
    def from_document(cls, value: object) -> "ReliableTaskFleetTransport":
        if not isinstance(value, Mapping):
            raise ValueError("ReliableTask fleet transport must be an object")
        expected_fields = {"target", "mongoUri", "redisAddr"}
        if set(value) != expected_fields:
            raise ValueError("ReliableTask fleet transport fields are invalid")
        target = str(value.get("target") or "").strip()
        mongo_uri = str(value.get("mongoUri") or "").strip()
        redis_addr = str(value.get("redisAddr") or "").strip()
        parsed = urlparse(mongo_uri)
        host, separator, port = redis_addr.rpartition(":")
        if (
            not target
            or parsed.scheme != "mongodb"
            or not parsed.hostname
            or parsed.port is None
            or not host
            or not separator
            or not port.isdecimal()
        ):
            raise ValueError("ReliableTask fleet transport values are invalid")
        return cls(target=target, mongo_uri=mongo_uri, redis_addr=redis_addr)


def _fleet_job_document(job: object) -> dict[str, str]:
    from content.execution.queue.model import QueueJob

    if not isinstance(job, QueueJob):
        raise TypeError("ReliableTask fleet job 必须为 QueueJob")
    reliable_ref = job.reliable_task_ref_document()
    payload = reliable_ref.get("payload") if isinstance(reliable_ref, Mapping) else None
    if not isinstance(payload, Mapping):
        raise ValueError(f"ReliableTask job 缺 typed payload：{job.job_id}")
    fields = (
        "entityRef",
        "carrier",
        "sourceRevision",
        "idempotencyKey",
        "jobId",
        "executionId",
        "ref",
        "stage",
        "partitionKey",
    )
    document = {field: str(payload.get(field) or "").strip() for field in fields}
    missing = [field for field, value in document.items() if not value]
    if missing:
        raise ValueError(
            f"ReliableTask job payload 不完整：{job.job_id}: {', '.join(missing)}"
        )
    return document


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


def _fleet_carrier(execution_id: str, jobs: list[object]) -> str:
    """Bind every request job to the carrier frozen into executionId."""
    from content.execution.queue.model import QueueJob

    expected = parse_execution_id(execution_id).content_type.value
    carriers = {
        job.carrier.value
        for job in jobs
        if isinstance(job, QueueJob) and job.carrier is not None
    }
    if len(carriers) != 1 or carriers != {expected} or len(jobs) < 1:
        raise ValueError(
            f"ReliableTask fleet carrier 必须与 executionId 一致："
            f"expected={expected}, jobs={sorted(carriers)}"
        )
    return expected


def _required_quota(
    execution_id: str,
    stage: QueueJobStage,
    pending_job_count: int,
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
    if remaining > pending_job_count:
        raise ValueError(
            f"候选池耗尽，区域实体供给不足：{stage.value} 剩余配额 {remaining} "
            f"超过待执行 job 数 {pending_job_count}"
        )
    return remaining


def build_fleet_request(
    execution_id: str,
    stage: QueueJobStage,
) -> dict[str, object]:
    jobs = [
        job
        for job in _load_jobs(execution_id)
        if job.backend is QueueBackend.RELIABLE_TASK
        and job.stage is stage
        and job.state not in {QueueJobState.SUCCEEDED, QueueJobState.DEAD}
    ]
    if not jobs:
        raise ValueError(
            f"execution 无待执行 ReliableTask {stage.value} jobs：{execution_id}"
        )
    _fleet_carrier(execution_id, jobs)
    object_timeout_seconds = _object_timeout_seconds(jobs)
    payload: dict[str, object] = {
        "schema": "quwoquan.data_content_fleet_request",
        "executionId": execution_id,
        "requireCommercial": stage is QueueJobStage.PUBLISH,
        "recoverDeadTasks": _has_audited_remote_recovery(execution_id, stage),
        "objectTimeoutMilliseconds": object_timeout_seconds * 1000,
        "requiredQuota": _required_quota(execution_id, stage, len(jobs)),
        "jobs": [_fleet_job_document(job) for job in sorted(jobs, key=lambda item: item.job_id)],
    }
    assert_valid(
        payload,
        "execution",
        "data_content_fleet_request",
        label="data_content_fleet_request",
    )
    return payload


def resolve_reliabletask_fleet_transport() -> ReliableTaskFleetTransport:
    """Resolve runtime endpoints only through the Ops-owned topology facade."""
    completed = subprocess.run(
        [
            sys.executable,
            str(_STACKCTL_PATH),
            "--output-format",
            "json",
            "data-execution-fleet",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip() or "no diagnostic output"
        raise RuntimeError(f"ReliableTask fleet topology is unavailable: {detail}")
    try:
        document = read_json_text(completed.stdout)
    except ValueError as exc:
        raise RuntimeError("ReliableTask fleet topology returned invalid JSON") from exc
    if not isinstance(document, Mapping):
        raise RuntimeError("ReliableTask fleet topology result must be an object")
    exit_code = document.get("exitCode")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int) or exit_code != 0:
        raise RuntimeError("ReliableTask fleet topology reported failure")
    return ReliableTaskFleetTransport.from_document(document.get("fleet"))


def _transport_socket_parts(transport: ReliableTaskFleetTransport) -> tuple[tuple[str, int], tuple[str, int]]:
    mongo = urlparse(transport.mongo_uri)
    redis_host, _, redis_port = transport.redis_addr.rpartition(":")
    if mongo.hostname is None or mongo.port is None:
        raise ValueError("ReliableTask fleet Mongo endpoint is invalid")
    return (mongo.hostname, mongo.port), (redis_host, int(redis_port))


def reliabletask_fleet_preflight() -> dict[str, object]:
    """Probe the resolved fleet control plane before expensive source work starts."""
    transport = resolve_reliabletask_fleet_transport()
    from core.runtime_policy import active_runtime_policy

    timeout = float(active_runtime_policy().preflight_network_timeout_seconds)
    mongo, redis = _transport_socket_parts(transport)
    checks: list[tuple[str, tuple[str, int]]] = [("mongo", mongo), ("redis", redis)]
    outcomes: dict[str, bool] = {}
    issues: list[str] = []
    for name, address in checks:
        try:
            with socket.create_connection(address, timeout=timeout):
                outcomes[name] = True
        except OSError as exc:
            outcomes[name] = False
            issues.append(f"{name} endpoint unavailable: {type(exc).__name__}")
    return {
        "ready": not issues,
        "target": transport.target,
        "mongo": outcomes["mongo"],
        "redis": outcomes["redis"],
        "issues": issues,
    }


def read_json_text(text: str) -> object:
    import json

    return json.loads(text)


def _fleet_command() -> tuple[list[str], Path]:
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
    """Stop the service worker and all of its children after controller cancellation."""
    if process.poll() is not None:
        return
    from core.runtime_policy import active_runtime_policy

    grace_seconds = active_runtime_policy().process_termination_timeout_seconds
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except OSError:
        return
    try:
        process.wait(timeout=grace_seconds)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except OSError:
        return
    process.wait()


def _run_fleet_process(
    command: list[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
) -> int:
    """Run one owned worker process group so an interrupted execution cannot leak it."""
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=dict(environment),
        start_new_session=True,
    )
    try:
        return process.wait()
    except BaseException:
        _terminate_fleet_process(process)
        raise


def discard_reliabletask_execution(execution_id: str) -> None:
    """Delete the service-owned task state of one already stopped execution."""
    transport = resolve_reliabletask_fleet_transport()
    command, cwd = _fleet_command()
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


def run_reliabletask_fleet(
    execution_id: str,
    stage: QueueJobStage,
    *,
    workers: int,
    completion_grace_seconds: int,
) -> ReliableTaskFleetReport:
    if workers < 1:
        raise ValueError("ReliableTask workers 必须为正整数")
    if completion_grace_seconds < 1:
        raise ValueError("ReliableTask completion grace 必须为正整数")
    transport = resolve_reliabletask_fleet_transport()
    request = build_fleet_request(execution_id, stage)
    object_timeout_milliseconds = request["objectTimeoutMilliseconds"]
    if not isinstance(object_timeout_milliseconds, int):
        raise ValueError("ReliableTask fleet request object timeout is invalid")
    batch_timeout_seconds = fleet_batch_timeout_seconds(
        job_count=len(request["jobs"]),
        workers=workers,
        object_timeout_seconds=object_timeout_milliseconds // 1000,
        completion_grace_seconds=completion_grace_seconds,
    )
    evidence_dir = execution_root(execution_id) / "evidence/reliabletask"
    request_path = evidence_dir / f"{stage.value}_fleet_request.json"
    report_path = evidence_dir / f"{stage.value}_fleet_report.json"
    write_json(request_path, request)
    command, cwd = _fleet_command()
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
        "QWQ_DATA_FLEET_WORKERS": str(workers),
        "QWQ_DATA_FLEET_BATCH_TIMEOUT_MS": str(batch_timeout_seconds * 1000),
    }
    from core.runtime_policy import active_runtime_policy

    environment["QWQ_DATA_FLEET_MAX_ATTEMPTS"] = str(
        active_runtime_policy().queue_max_attempts
    )
    returncode = _run_fleet_process(
        [*command, "--request", str(request_path), "--report", str(report_path)],
        cwd=cwd,
        environment=environment,
    )
    if not report_path.is_file():
        raise RuntimeError(
            "ReliableTask fleet 未产出报告"
            f"（exit={returncode}, executionId={execution_id}）"
        )
    report = read_json(report_path)
    assert_valid(
        report,
        "release",
        "reliabletask_fleet_report",
        label="reliabletask_fleet_report",
    )
    decoded = ReliableTaskFleetReport.from_document(report)
    return decoded


__all__ = [
    "build_fleet_request",
    "ReliableTaskFleetOutcome",
    "ReliableTaskFleetReport",
    "ReliableTaskFleetTransport",
    "fleet_batch_timeout_seconds",
    "discard_reliabletask_execution",
    "reliabletask_fleet_preflight",
    "resolve_reliabletask_fleet_transport",
    "run_reliabletask_fleet",
]
