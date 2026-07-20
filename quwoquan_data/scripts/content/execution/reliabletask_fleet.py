"""通过唯一 Data CLI 驱动 Mongo+Redis ReliableTask 内容 worker。"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Mapping

from core.control_types import QueueBackend, QueueJobStage, QueueJobState
from core.io import read_json, write_json
from core.paths import OUTPUT_ROOT, PUBLISH_ROOT, REPO_ROOT, execution_root
from core.runtime_policy import active_runtime_policy
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
        "QWQ_DATA_FLEET_PYTHON": sys.executable,
        "QWQ_DATA_FLEET_CLI": str(REPO_ROOT / "quwoquan_data/scripts/cli.py"),
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


def handle_reliabletask_fleet(args: argparse.Namespace) -> None:
    report = run_reliabletask_fleet(
        str(args.execution_id),
        QueueJobStage(str(args.stage)),
        workers=int(args.workers),
        timeout_seconds=int(args.timeout_seconds),
    )
    print(
        "[task reliabletask-fleet] "
        f"stage={args.stage} total={report['total']} "
        f"succeeded={report['succeeded']} "
        f"accepted={report['commercialAcceptedCount']} "
        f"acceptedObjectsPerHour={report['acceptedContentThroughputPerHour']:.3f}"
    )


def register_reliabletask_fleet_parser(
    commands: argparse._SubParsersAction,
) -> None:
    policy = active_runtime_policy()
    parser = commands.add_parser(
        "reliabletask-fleet",
        help="通过 Mongo+Redis worker 池执行已冻结的对象 author/publish jobs",
    )
    parser.add_argument("--execution-id", required=True)
    parser.add_argument(
        "--stage",
        required=True,
        choices=(QueueJobStage.AUTHOR.value, QueueJobStage.PUBLISH.value),
    )
    parser.add_argument("--workers", type=int, default=policy.author_workers)
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=policy.queue_max_wall_clock_seconds,
    )
    parser.set_defaults(handler=handle_reliabletask_fleet)


__all__ = [
    "build_fleet_request",
    "register_reliabletask_fleet_parser",
    "run_reliabletask_fleet",
]
