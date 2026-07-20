"""Typed Python worker boundary for Mongo+Redis ReliableTask content jobs."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from core.control_types import AgentProvider, QueueBackend, QueueJobStage
from core.io import read_json
from core.paths import OUTPUT_ROOT, execution_root
from core.schema import assert_valid
from content.execution import store
from content.execution.agent.outcome import (
    AgentRunOutcome,
    ManagedAgentJobOutcome,
    coerce_agent_outcome,
)
from content.execution.context import ExecutionContext
from content.execution.coverage import coverage_entity_ids
from content.execution.model_contract import execution_model_pair_for_execution
from content.execution.production_contracts import (
    assert_envelope_matches_job,
    validate_agent_result_envelope,
)
from content.execution.queue.completion import author_completion_issues
from content.execution.queue.core import _read_job, stable_job_id
from content.execution.queue.model import QueueJob

WorkerAgentRunner = Callable[[ExecutionContext, str], AgentRunOutcome]


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
        "partitionKey": item.partition_key,
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
    return job


def _execution_context(execution_id: str) -> ExecutionContext:
    from core.runtime_policy import active_runtime_policy

    spec = store.load_spec(execution_id)
    policy = active_runtime_policy()
    model = execution_model_pair_for_execution(execution_id).author.model_id
    return ExecutionContext(
        execution_id=execution_id,
        entity_ids=tuple(coverage_entity_ids(spec)),
        spec=spec,
        managed=True,
        runtime=policy.cursor_runtime,
        max_workers=policy.author_workers,
        model=model,
        agent_provider=AgentProvider(policy.cursor_provider.value),
    )


def _normalized_ref(value: str) -> str:
    text = str(value or "").strip().strip("/")
    if text.startswith("entity/"):
        return "entities/" + text.removeprefix("entity/")
    return text


def _author_prompt(ctx: ExecutionContext, job: QueueJob) -> tuple[str, str]:
    from content.execution.agent.checkpoint_prompts import _checkpoint_prompts
    from content.execution.agent.managed_checkpoint import _managed_checkpoint_ref

    checkpoint = "build_homepage" if job.carrier and job.carrier.value == "homepage" else "post_author"
    prompts = _checkpoint_prompts(ctx, checkpoint)
    expected_ref = _normalized_ref(job.ref)
    for prompt in prompts:
        prompt_ref = _normalized_ref(_managed_checkpoint_ref(ctx, checkpoint, prompt))
        if prompt_ref == expected_ref:
            return checkpoint, prompt
    raise ValueError(
        f"ReliableTask author job 未找到唯一待执行 prompt：{job.ref} ({checkpoint})"
    )


def _default_agent_runner(ctx: ExecutionContext, prompt: str) -> AgentRunOutcome:
    from content.execution.agent.agent_worker import (
        _default_managed_agent_runner_isolated,
    )

    return _default_managed_agent_runner_isolated(ctx, prompt)


def _author_envelope_path(job: QueueJob) -> Path:
    if not job.content_object_dir:
        raise ValueError(f"ReliableTask author job 缺 contentObjectDir：{job.job_id}")
    return (
        execution_root(job.execution_id)
        / job.content_object_dir
        / "4.draft"
        / "agent_result_envelope.json"
    )


def _validate_author_envelope(job: QueueJob, envelope_path: Path) -> None:
    envelope = read_json(envelope_path)
    if not isinstance(envelope, Mapping):
        raise ValueError("AgentResultEnvelope 必须为 object")
    issues = validate_agent_result_envelope(
        envelope,
        workspace_root=envelope_path.parent,
    )
    issues.extend(assert_envelope_matches_job(envelope, job.to_document()))
    issues.extend(issue.message for issue in author_completion_issues(job))
    if issues:
        raise ValueError("ReliableTask author evidence invalid: " + "; ".join(issues))


def _execute_author(
    job: QueueJob,
    *,
    agent_runner: WorkerAgentRunner | None,
) -> dict[str, object]:
    envelope_path = _author_envelope_path(job)
    if envelope_path.is_file():
        _validate_author_envelope(job, envelope_path)
        from content.execution.queue.runtime import record_reliabletask_completion

        record_reliabletask_completion(
            job.execution_id,
            job.job_id,
            evidence_path=envelope_path,
            evidence_root=OUTPUT_ROOT,
            envelope_workspace_root=envelope_path.parent,
        )
        return {
            "executionId": job.execution_id,
            "jobId": job.job_id,
            "resultEnvelopeRef": envelope_path.relative_to(OUTPUT_ROOT).as_posix(),
            "acceptanceClass": "stage_completed",
            "completedAt": datetime.now(timezone.utc).isoformat(),
        }
    ctx = _execution_context(job.execution_id)
    checkpoint, prompt = _author_prompt(ctx, job)
    scoped_ctx = replace(
        ctx,
        agent_usage_scope="content_object",
        agent_content_object_ref=job.ref,
        agent_execution_stage=checkpoint,
    )
    runner = agent_runner or _default_agent_runner
    outcome = coerce_agent_outcome(
        runner(scoped_ctx, prompt),
        label=f"ReliableTask author {job.job_id}",
    )
    if not outcome.succeeded:
        raise RuntimeError(
            f"ReliableTask author Agent 失败：{outcome.failure_kind.value}: {outcome.message}"
        )
    job_outcome = ManagedAgentJobOutcome(
        outcome=outcome,
        job_index=0,
        lane="homepage" if checkpoint == "build_homepage" else "article",
        ref=job.ref,
    )
    if checkpoint == "build_homepage":
        from content.execution.controller.homepage_author_finalization import (
            _finalize_managed_homepage_outputs,
        )

        finalized = _finalize_managed_homepage_outputs(
            scoped_ctx,
            [prompt],
            [job_outcome],
        )
        if not finalized or not finalized[0].succeeded:
            issues = finalized[0].gate_issues if finalized else ("missing outcome",)
            raise ValueError(
                "ReliableTask homepage finalize failed: " + "; ".join(issues)
            )
    else:
        from content.execution.agent.agent_checkpoint import (
            _finalize_managed_author_outputs,
        )

        _finalize_managed_author_outputs(scoped_ctx, [prompt], [job_outcome])
    _validate_author_envelope(job, envelope_path)
    from content.execution.queue.runtime import record_reliabletask_completion

    record_reliabletask_completion(
        job.execution_id,
        job.job_id,
        evidence_path=envelope_path,
        evidence_root=OUTPUT_ROOT,
        envelope_workspace_root=envelope_path.parent,
    )
    return {
        "executionId": job.execution_id,
        "jobId": job.job_id,
        "resultEnvelopeRef": envelope_path.relative_to(OUTPUT_ROOT).as_posix(),
        "acceptanceClass": "stage_completed",
        "completedAt": datetime.now(timezone.utc).isoformat(),
    }


def _execute_publish(job: QueueJob) -> dict[str, object]:
    carrier = job.carrier.value if job.carrier else ""
    if carrier == "homepage":
        from content.execution.controller.publish import publish_homepage_object

        transaction = publish_homepage_object(job.execution_id, job.ref)
    else:
        from content.release.canonical.post_promotion import promote_post_object

        if not job.content_object_dir:
            raise ValueError(f"ReliableTask publish job 缺 contentObjectDir：{job.job_id}")
        transaction = promote_post_object(
            job.execution_id,
            job.content_object_dir,
        )
    from content.execution.queue.runtime import record_reliabletask_completion

    record_reliabletask_completion(
        job.execution_id,
        job.job_id,
        evidence_path=OUTPUT_ROOT / transaction["applyReportRef"],
        evidence_root=OUTPUT_ROOT,
    )
    return {
        "executionId": job.execution_id,
        "jobId": job.job_id,
        "canonicalObjectRef": transaction["canonicalObjectRef"],
        "canonicalObjectSha256": transaction["canonicalObjectSha256"],
        "objectTransactionId": transaction["transactionId"],
        "resultEnvelopeRef": transaction["applyReportRef"],
        "acceptanceClass": "commercial_canonical",
        "completedAt": datetime.now(timezone.utc).isoformat(),
    }


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


def handle_execute_object_worker(_args: argparse.Namespace) -> None:
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
    except Exception as exc:  # noqa: BLE001
        print(
            f"[task execute-object-worker] {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    print(json.dumps(response, ensure_ascii=False, separators=(",", ":")))


def register_execute_object_worker_parser(
    subparsers: argparse._SubParsersAction,
) -> None:
    parser = subparsers.add_parser(
        "execute-object-worker",
        help="ReliableTask 内部强类型对象 worker（stdin/stdout JSON）",
    )
    parser.set_defaults(handler=handle_execute_object_worker)


__all__ = [
    "DataContentWorkItem",
    "execute_work_item",
    "handle_execute_object_worker",
    "register_execute_object_worker_parser",
]
