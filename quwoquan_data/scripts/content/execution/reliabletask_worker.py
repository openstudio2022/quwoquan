"""Typed Python worker boundary for Mongo+Redis ReliableTask content jobs."""
from __future__ import annotations

import json
import signal
import sys
from dataclasses import dataclass
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
    model = execution_model_pair_for_execution(execution_id).author
    return ExecutionContext(
        execution_id=execution_id,
        entity_ids=tuple(coverage_entity_ids(spec)),
        spec=spec,
        managed=True,
        runtime=policy.cursor_runtime,
        max_workers=policy.author_workers,
        model=model.model_id,
        model_parameters=model.parameters,
        agent_provider=AgentProvider(policy.cursor_provider.value),
    )


def _homepage_repair_addendum(job: QueueJob, object_dir: Path) -> str:
    """Render only a validated typed homepage repair report for an author retry."""
    from core.data_issue import (
        DataIssue,
        DataIssueCode,
        DataIssueLane,
        DataIssueStage,
        DataRecoveryAction,
    )

    report_path = object_dir / "5.review" / "repair_report.json"
    if not report_path.is_file():
        return ""
    report = read_json(report_path)
    if not isinstance(report, Mapping):
        raise ValueError(f"ReliableTask homepage repair report must be object: {job.ref}")
    expected = {
        "schema": "quwoquan_data.repair_report",
        "executionId": job.execution_id,
        "command": "homepage",
        "ref": job.ref,
        "failedStage": DataIssueStage.BUILD_HOMEPAGE.value,
        "failedGate": "homepage_materialization",
        "fallbackStage": DataIssueStage.BUILD_HOMEPAGE.value,
    }
    mismatches = [
        field
        for field, expected_value in expected.items()
        if str(report.get(field) or "").strip() != expected_value
    ]
    if report.get("rerunChain") != ["author", "materialize"]:
        mismatches.append("rerunChain")
    if mismatches:
        raise ValueError(
            "ReliableTask homepage repair report binding mismatch: "
            + ", ".join(sorted(mismatches))
        )
    raw_issues = report.get("issues")
    if not isinstance(raw_issues, list) or not raw_issues:
        raise ValueError(f"ReliableTask homepage repair report issues invalid: {job.ref}")
    issues = tuple(DataIssue.from_dict(item) for item in raw_issues)
    expected_issue_values = (
        DataIssueCode.QUALITY_FAILED,
        DataIssueStage.BUILD_HOMEPAGE,
        DataIssueLane.HOMEPAGE,
        DataRecoveryAction.RETRY_AGENT,
    )
    if any(
        (issue.code, issue.stage, issue.lane, issue.recovery) != expected_issue_values
        for issue in issues
    ):
        raise ValueError(f"ReliableTask homepage repair report issue contract invalid: {job.ref}")
    rendered_issues = "\n".join(f"- [{issue.code.value}] {issue.message}" for issue in issues)
    return (
        "\n\n## 确定性质量门修复反馈\n"
        "上一次正文未通过确定性质量门。请在现有 page.md 基础上逐项修订，"
        "保留已通过的底稿和图片占位符，不得从零重写：\n"
        f"{rendered_issues}\n"
    )


def _author_prompt(_ctx: ExecutionContext, job: QueueJob) -> tuple[str, str]:
    """Read the single frozen prompt bound to a ReliableTask author job.

    A deterministic review can require a second author attempt after the first
    draft has replaced its placeholder. Re-enumerating checkpoint prompts at
    that point is incorrect because that enumeration intentionally excludes
    non-placeholder drafts. The job packet is the frozen author input and
    remains the sole retry lookup source.
    """
    checkpoint = (
        "build_homepage"
        if job.carrier and job.carrier.value == "homepage"
        else "post_author"
    )
    content_object_dir = str(job.content_object_dir or "").strip()
    if not content_object_dir:
        raise ValueError(f"ReliableTask author job 缺 contentObjectDir：{job.job_id}")
    object_dir = execution_root(job.execution_id) / content_object_dir
    draft_dir = object_dir / "4.draft"
    packet_path = draft_dir / "author_job_packet.json"
    if not packet_path.is_file():
        raise ValueError(f"ReliableTask author packet missing: {job.ref}")
    packet = read_json(packet_path)
    if not isinstance(packet, Mapping):
        raise ValueError(f"ReliableTask author packet must be object: {job.ref}")
    if str(packet.get("executionId") or "").strip() != job.execution_id:
        raise ValueError(f"ReliableTask author packet executionId mismatch: {job.ref}")
    packet_ref = str(packet.get("objectRef") or packet.get("ref") or "").strip()
    if packet_ref != job.ref:
        raise ValueError(f"ReliableTask author packet objectRef mismatch: {job.ref}")
    prompt_ref = str(packet.get("promptRef") or "").strip()
    if prompt_ref != "4.draft/prompt.md":
        raise ValueError(f"ReliableTask author packet promptRef invalid: {job.ref}")
    prompt_path = draft_dir / "prompt.md"
    if not prompt_path.is_file():
        raise ValueError(f"ReliableTask author prompt missing: {job.ref}")
    prompt = prompt_path.read_text(encoding="utf-8").strip()
    if not prompt:
        raise ValueError(f"ReliableTask author prompt empty: {job.ref}")
    if checkpoint == "build_homepage":
        prompt += _homepage_repair_addendum(job, object_dir)
    return checkpoint, prompt


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


def _existing_author_envelope_is_reusable(
    job: QueueJob,
    envelope_path: Path,
) -> bool:
    """Reuse author evidence only when no newer review repair invalidates it.

    Homepage finalization writes the Agent evidence before the deterministic
    page gate runs.  A failed gate must therefore invalidate that evidence;
    otherwise a queue retry can mistake a valid draft envelope for a completed
    author repair. Post review uses the same rule: a repair report newer than
    the result envelope is a typed instruction to run the author again.
    """
    _validate_author_envelope(job, envelope_path)
    content_object_dir = str(job.content_object_dir or "").strip()
    if not content_object_dir:
        raise ValueError(f"ReliableTask author job 缺 contentObjectDir：{job.job_id}")
    repair_report = (
        execution_root(job.execution_id)
        / content_object_dir
        / "5.review"
        / "repair_report.json"
    )
    try:
        repair_requires_reauthoring = (
            repair_report.is_file()
            and repair_report.stat().st_mtime >= envelope_path.stat().st_mtime
        )
    except OSError as exc:
        raise RuntimeError(f"ReliableTask author repair evidence unreadable: {exc}") from exc
    if repair_requires_reauthoring:
        envelope_path.unlink(missing_ok=True)
        return False
    if not job.carrier or job.carrier.value != "homepage":
        return True
    parts = str(job.ref or "").strip().strip("/").split("/", 3)
    if len(parts) != 4 or parts[0] != "entity" or not all(parts[1:]):
        raise ValueError(f"ReliableTask homepage ref 不合法：{job.ref!r}")
    from content.homepage.homepage_release import materialize_entity_page

    materialize_issues = materialize_entity_page(
        job.execution_id,
        parts[1],
        parts[2],
        parts[3],
    )
    if not materialize_issues:
        return True
    envelope_path.unlink(missing_ok=True)
    return False


def _execute_author(
    job: QueueJob,
    *,
    agent_runner: WorkerAgentRunner | None,
) -> dict[str, object]:
    envelope_path = _author_envelope_path(job)
    if envelope_path.is_file() and _existing_author_envelope_is_reusable(
        job,
        envelope_path,
    ):
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
    runner = agent_runner or _default_agent_runner
    outcome = coerce_agent_outcome(
        runner(ctx, prompt),
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
            ctx,
            [prompt],
            [job_outcome],
        )
        if (
            not finalized
            or not finalized[0].succeeded
            or finalized[0].gate_issues
        ):
            issues = finalized[0].gate_issues if finalized else ("missing outcome",)
            raise ValueError(
                "ReliableTask homepage finalize failed: " + "; ".join(issues)
            )
    else:
        from content.execution.agent.agent_checkpoint import (
            _finalize_managed_author_outputs,
        )

        _finalize_managed_author_outputs(ctx, [prompt], [job_outcome])
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


def run_process_worker() -> None:
    """Private Go-to-Python process boundary; not a public Data CLI command."""
    from content.execution.agent.agent_worker import _terminate_managed_agent_subprocesses

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
