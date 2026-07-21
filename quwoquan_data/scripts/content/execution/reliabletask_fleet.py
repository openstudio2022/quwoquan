"""通过唯一 Data CLI 驱动 Mongo+Redis ReliableTask 内容 worker。"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Mapping

from core.control_types import QueueBackend, QueueJobStage, QueueJobState
from core.io import read_json, write_json
from core.paths import OUTPUT_ROOT, PUBLISH_ROOT, REPO_ROOT, execution_root
from core.python_environment import resolve_data_agent_python
from core.schema import assert_valid
from content.execution.queue.core import _load_jobs


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

    state = load_execution_state(execution_id)
    for action in reversed(tuple(state.recovery_actions or ())):
        if not isinstance(action, Mapping):
            continue
        if str(action.get("stage") or "").strip() != stage.value:
            continue
        if str(action.get("recoveredAt") or "").strip():
            return True
    return False


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
    payload: dict[str, object] = {
        "schema": "quwoquan.data_content_fleet_request",
        "executionId": execution_id,
        "requireCommercial": stage is QueueJobStage.PUBLISH,
        "recoverDeadTasks": _has_audited_remote_recovery(execution_id, stage),
        "jobs": [_fleet_job_document(job) for job in sorted(jobs, key=lambda item: item.job_id)],
    }
    assert_valid(
        payload,
        "execution",
        "data_content_fleet_request",
        label="data_content_fleet_request",
    )
    return payload


def _required_environment(name: str) -> str:
    value = str(os.environ.get(name) or "").strip()
    if not value:
        raise ValueError(f"ReliableTask fleet 缺运行配置：{name}")
    return value


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


def run_reliabletask_fleet(
    execution_id: str,
    stage: QueueJobStage,
    *,
    workers: int,
    timeout_seconds: int,
) -> dict[str, object]:
    if workers < 1:
        raise ValueError("ReliableTask workers 必须为正整数")
    if timeout_seconds < 1:
        raise ValueError("ReliableTask timeout 必须为正整数")
    _required_environment("QWQ_DATA_FLEET_MONGO_URI")
    _required_environment("QWQ_DATA_FLEET_REDIS_ADDR")
    request = build_fleet_request(execution_id, stage)
    evidence_dir = execution_root(execution_id) / "evidence/reliabletask"
    request_path = evidence_dir / f"{stage.value}_fleet_request.json"
    report_path = evidence_dir / f"{stage.value}_fleet_report.json"
    write_json(request_path, request)
    command, cwd = _fleet_command()
    environment = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "QWQ_DATA_FLEET_PYTHON": str(_fleet_agent_python()),
        "QWQ_DATA_FLEET_SCRIPTS_ROOT": str(REPO_ROOT / "quwoquan_data/scripts"),
        "QWQ_DATA_FLEET_WORK_DIR": str(REPO_ROOT / "quwoquan_data"),
        "QWQ_DATA_FLEET_PUBLISH_ROOT": str(PUBLISH_ROOT),
        "QWQ_DATA_FLEET_EVIDENCE_ROOT": str(OUTPUT_ROOT),
        "QWQ_DATA_FLEET_WORKERS": str(workers),
        "QWQ_DATA_FLEET_TIMEOUT_MS": str(timeout_seconds * 1000),
    }
    completed = subprocess.run(
        [
            *command,
            "--request",
            str(request_path),
            "--report",
            str(report_path),
        ],
        cwd=cwd,
        env=environment,
        check=False,
    )
    if not report_path.is_file():
        raise RuntimeError(
            "ReliableTask fleet 未产出报告"
            f"（exit={completed.returncode}, executionId={execution_id}）"
        )
    report = read_json(report_path)
    assert_valid(
        report,
        "release",
        "reliabletask_fleet_report",
        label="reliabletask_fleet_report",
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "ReliableTask fleet 执行失败"
            f"（exit={completed.returncode}, report={report_path}）"
        )
    if stage is QueueJobStage.PUBLISH and report.get("passed") is not True:
        raise RuntimeError(
            "ReliableTask publish 未形成 accepted commercial throughput："
            f"{report.get('acceptedContentThroughputStatus')}"
        )
    return report


__all__ = [
    "build_fleet_request",
    "run_reliabletask_fleet",
]
