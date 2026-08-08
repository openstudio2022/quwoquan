"""Typed Python worker boundary for Mongo+Redis ReliableTask content jobs."""
from __future__ import annotations

import json
import signal
import sys
from collections.abc import Mapping
from contextlib import redirect_stdout
from dataclasses import dataclass

from core.control_types import QueueBackend, QueueJobStage
from core.schema import assert_valid

from content.execution.queue.reliabletask.author import (
    WorkerAgentRunner,
    _execute_author,
)
from content.execution.queue.backend import load_reliabletask_job_set_envelopes
from content.execution.queue.core import _read_job, stable_job_id
from content.execution.queue.model import QueueJob
from content.execution.queue.reliabletask.publish import _execute_publish
from content.execution.runtime_contract import canonical_sha256


@dataclass(frozen=True, slots=True)
class DataContentWorkItem:
    runtime_task_id: str
    job_id: str
    execution_id: str
    ref: str
    stage: QueueJobStage
    partition_key: str
    entity_ref: str
    carrier: str
    source_revision: str
    idempotency_key: str
    job_set_envelope_digest: str
    job_set_digest: str
    actual_task_digest: str

    @classmethod
    def from_document(cls, value: Mapping[str, object]) -> "DataContentWorkItem":
        return cls(
            runtime_task_id=str(value.get("runtimeTaskId") or "").strip(),
            job_id=str(value.get("jobId") or "").strip(),
            execution_id=str(value.get("executionId") or "").strip(),
            ref=str(value.get("ref") or "").strip(),
            stage=QueueJobStage(str(value.get("stage") or "").strip()),
            partition_key=str(value.get("partitionKey") or "").strip(),
            entity_ref=str(value.get("entityRef") or "").strip(),
            carrier=str(value.get("carrier") or "").strip(),
            source_revision=str(value.get("sourceRevision") or "").strip(),
            idempotency_key=str(value.get("idempotencyKey") or "").strip(),
            job_set_envelope_digest=str(
                value.get("jobSetEnvelopeDigest") or ""
            ).strip(),
            job_set_digest=str(value.get("jobSetDigest") or "").strip(),
            actual_task_digest=str(value.get("actualTaskDigest") or "").strip(),
        )


def _load_bound_job(item: DataContentWorkItem) -> QueueJob:
    expected_job_id = stable_job_id(item.execution_id, item.ref, item.stage.value)
    if item.job_id != expected_job_id:
        raise ValueError(
            f"ReliableTask jobId 绑定不匹配：{item.job_id!r} != {expected_job_id!r}"
        )
    job = _read_job(item.execution_id, item.job_id)
    if job.backend is not QueueBackend.RELIABLE_TASK:
        raise ValueError(f"ReliableTask worker 拒绝非 reliabletask job：{job.backend.value}")
    reliable_ref = job.reliable_task_ref_document() or {}
    payload = reliable_ref.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("ReliableTask job 缺少 typed payload")
    expected = {
        "jobId": item.job_id,
        "executionId": item.execution_id,
        "ref": item.ref,
        "stage": item.stage.value,
        "entityRef": item.entity_ref,
        "carrier": item.carrier,
        "sourceRevision": item.source_revision,
        "idempotencyKey": item.idempotency_key,
    }
    mismatches = [
        key
        for key, expected_value in expected.items()
        if str(payload.get(key) or "") != expected_value
    ]
    if mismatches:
        raise ValueError(
            "ReliableTask worker identity binding mismatch: "
            + ", ".join(sorted(mismatches))
        )
    envelopes = load_reliabletask_job_set_envelopes(item.execution_id)
    stage_envelopes = [
        envelope
        for envelope in envelopes
        if str(envelope.get("stage") or "").strip() == item.stage.value
        and envelope.get("envelopeDigest") == item.job_set_envelope_digest
        and envelope.get("jobSetDigest") == item.job_set_digest
    ]
    if len(stage_envelopes) != 1:
        raise ValueError(
            "ReliableTask worker requires one exact stage-attempt envelope"
        )
    frozen_tasks = stage_envelopes[0].get("expectedTasks")
    if not isinstance(frozen_tasks, list):
        raise TypeError("ReliableTask frozen expectedTasks must be an array")
    if (
        canonical_sha256(frozen_tasks) != item.actual_task_digest
        or item.actual_task_digest != item.job_set_digest
    ):
        raise ValueError("ReliableTask worker actual task digest mismatch")
    frozen_matches = [
        task
        for task in frozen_tasks
        if isinstance(task, Mapping)
        and str(task.get("idempotencyKey") or "").strip()
        == item.idempotency_key
    ]
    if len(frozen_matches) != 1:
        raise ValueError(
            "ReliableTask worker job is absent from frozen stage job-set envelope"
        )
    frozen = frozen_matches[0]
    frozen_expected = {**expected, "partitionKey": item.partition_key}
    frozen_mismatches = [
        key
        for key, expected_value in frozen_expected.items()
        if str(frozen.get(key) or "").strip() != expected_value
    ]
    if frozen_mismatches:
        raise ValueError(
            "ReliableTask worker frozen identity binding mismatch: "
            + ", ".join(sorted(frozen_mismatches))
        )
    return job


def execute_work_item(
    item: DataContentWorkItem,
    *,
    agent_runner: WorkerAgentRunner | None = None,
) -> dict[str, object]:
    job = _load_bound_job(item)
    if item.stage is QueueJobStage.AUTHOR:
        return _execute_author(job, agent_runner=agent_runner)
    if item.stage is QueueJobStage.PUBLISH:
        return _execute_publish(job)
    raise ValueError(
        "ReliableTask download 仍由 execution download lane 批量执行，"
        "不得伪报对象级完成"
    )


def run_process_worker() -> None:
    """Private Go-to-Python process boundary; not a public Data CLI command."""
    from content.execution.agent.agent_worker import (
        _terminate_managed_agent_subprocesses,
    )

    previous_handlers: dict[int, object] = {}

    def _interrupted(signum: int, _frame: object) -> None:
        _terminate_managed_agent_subprocesses()
        raise KeyboardInterrupt(f"ReliableTask worker interrupted by signal {signum}")

    for sig in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[sig] = signal.getsignal(sig)
        signal.signal(sig, _interrupted)
    try:
        request = json.load(sys.stdin)
        assert_valid(
            request,
            "execution",
            "data_content_worker_request",
            label="data_content_worker_request",
        )
        item_payload = request.get("item") if isinstance(request, Mapping) else None
        if not isinstance(item_payload, Mapping):
            raise ValueError("data content worker request.item 必须为 object")
        # stdout is the strict Go worker protocol. Agent/progress output from
        # the implementation belongs on stderr so it cannot precede the one
        # JSON response and make a completed task look externally failed.
        with redirect_stdout(sys.stderr):
            result = execute_work_item(DataContentWorkItem.from_document(item_payload))
        response = {
            "schema": "quwoquan.data_content_worker_response",
            "result": result,
        }
        assert_valid(
            response,
            "execution",
            "data_content_worker_response",
            label="data_content_worker_response",
        )
    except KeyboardInterrupt:
        raise
    except Exception as exc:  # noqa: BLE001
        print(
            f"[data-content-worker] {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    finally:
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)
    print(json.dumps(response, ensure_ascii=False, separators=(",", ":")))
__all__ = [
    "DataContentWorkItem",
    "execute_work_item",
    "run_process_worker",
]
