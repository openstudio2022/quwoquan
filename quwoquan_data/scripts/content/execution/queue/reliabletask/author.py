"""ReliableTask author-stage execution and durable evidence recovery."""
from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path

from core.io import read_json
from core.paths import OUTPUT_ROOT, execution_root

from content.execution import store
from content.execution.agent.outcome import (
    AgentRunOutcome,
    ManagedAgentJobOutcome,
    coerce_agent_outcome,
)
from content.execution.context import ExecutionContext
from content.execution.coverage import coverage_entity_ids
from content.execution.model_contract import semantic_execution_binding_for_execution
from content.execution.production_contracts import (
    assert_envelope_matches_job,
    sha256_file,
    validate_agent_result_envelope,
)
from content.execution.queue.completion import author_completion_issues
from content.execution.queue.model import QueueJob
from content.execution.queue.reliabletask.author_retry_feedback import article_retry_review_feedback_addendum as _render_retry_review_feedback

WorkerAgentRunner = Callable[[ExecutionContext, str], AgentRunOutcome]
_DURABLE_OUTPUT_SETTLE_SECONDS = 1.5
_DURABLE_OUTPUT_SETTLE_SAMPLES = 8


def _execution_context(
    execution_id: str, *, semantic_max_attempts: int
) -> ExecutionContext:
    spec = store.load_spec(execution_id)
    semantic_binding = semantic_execution_binding_for_execution(execution_id)
    model = semantic_binding.pair.author
    return ExecutionContext(
        execution_id=execution_id,
        entity_ids=tuple(coverage_entity_ids(spec)),
        spec=spec,
        managed=True,
        runtime=semantic_binding.runtime,
        model=model.model_id,
        model_parameters=model.parameters,
        agent_provider=model.provider,
        semantic_max_attempts=semantic_max_attempts,
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
    repair_strategies = {
        dict(issue.attributes).get("repairStrategy", "") for issue in issues
    }
    if repair_strategies not in (
        {"local_edit"},
        {"rebuild_from_frozen_base"},
    ):
        raise ValueError(f"ReliableTask homepage repair report issue contract invalid: {job.ref}")
    rendered_issues = "\n".join(f"- [{issue.code.value}] {issue.message}" for issue in issues)
    rebuild_from_base = repair_strategies == {"rebuild_from_frozen_base"}
    repair_strategy = (
        "本次必须整份重建。不得在旧 page.md 上继续扩写；必须以 prompt.md 中完整的"
        "『底稿材料』重新构建 page.md：按原顺序覆盖全部必需标题与每个图片占位符，"
        "正文沿用底稿原文的尺度只按 prompt.md 里 sourceUseMode 那一条指令执行，"
        "不得丢失该指令要求保留的事实。"
        if rebuild_from_base
        else (
            "请在现有 page.md 基础上逐项修订，保留已通过的底稿和图片占位符，"
            "不得从零重写或再次覆盖整份文件；若正文已经包含合格章节，必须用局部"
            "编辑补回缺失标题及其对应底稿段落，避免因整文件输出长度限制再次截断后半部分。"
        )
    )
    return (
        "\n\n## 确定性质量门修复反馈\n"
        "上一次正文未通过确定性质量门。"
        f"{repair_strategy}若当前 page.md 仍为"
        "等待创作占位，必须先用符合冻结正文合同的完整主页正文替换该占位：\n"
        f"{rendered_issues}\n"
        "逐项修复后必须重新读取每个问题涉及的章节与图片标记：时间锚点错误时"
        "移动整条图片标记到匹配年代的章节；图注遗漏共现主体时直接补回来源"
        "已声明的全部主体；问题若指出图片含日期戳、水印、页码、扫描编号或其他"
        "未清理的画面文字，必须从 page.md 删除该图片标记，不得只改图注，也不"
        "得猜测或裁切原始字节。仅可换用冻结素材中通过同一质量门的干净图片；"
        "没有替代图时直接省略。确认旧的错误位置、错误图注及污染 assetId 已不"
        "再出现后才能结束。"
    )


def _article_repair_addendum(job: QueueJob, object_dir: Path) -> str:
    """Render a validated article review repair as immutable retry input."""
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
    envelope = read_json(report_path)
    if not isinstance(envelope, Mapping):
        raise ValueError(f"ReliableTask article repair envelope must be object: {job.ref}")
    expected_envelope = {
        "schema": "quwoquan_data.stage_envelope",
        "executionId": job.execution_id,
        "step": "repair_report",
        "ref": job.ref,
    }
    envelope_mismatches = [
        field
        for field, expected_value in expected_envelope.items()
        if str(envelope.get(field) or "").strip() != expected_value
    ]
    report = envelope.get("payload")
    if not isinstance(report, Mapping):
        envelope_mismatches.append("payload")
    if envelope_mismatches:
        raise ValueError(
            "ReliableTask article repair envelope binding mismatch: "
            + ", ".join(sorted(envelope_mismatches))
        )
    assert isinstance(report, Mapping)
    expected = {
        "schema": "quwoquan_data.repair_report",
        "executionId": job.execution_id,
        "command": "post",
        "ref": job.ref,
        "failedStage": DataIssueStage.REVIEW.value,
        "fallbackStage": DataIssueStage.AGENT_COMPOSE.value,
    }
    mismatches = [
        field
        for field, expected_value in expected.items()
        if str(report.get(field) or "").strip() != expected_value
    ]
    if str(report.get("failedGate") or "").strip() not in {
        "contentReview",
        "post_verify",
    }:
        mismatches.append("failedGate")
    if report.get("rerunChain") != ["agent_compose", "review", "materialize"]:
        mismatches.append("rerunChain")
    if mismatches:
        raise ValueError(
            "ReliableTask article repair report binding mismatch: "
            + ", ".join(sorted(mismatches))
        )
    raw_issues = report.get("issues")
    if not isinstance(raw_issues, list) or not raw_issues:
        raise ValueError(f"ReliableTask article repair report issues invalid: {job.ref}")
    issues = tuple(DataIssue.from_dict(item) for item in raw_issues)
    allowed_lanes = {DataIssueLane.ALL, DataIssueLane.ARTICLE}
    if any(
        issue.code is not DataIssueCode.QUALITY_FAILED
        or issue.stage is not DataIssueStage.REVIEW
        or issue.lane not in allowed_lanes
        or issue.recovery is not DataRecoveryAction.REWIND_COMPOSE
        or issue.ref != job.ref
        for issue in issues
    ):
        raise ValueError(f"ReliableTask article repair report issue contract invalid: {job.ref}")
    rendered_issues = "\n".join(
        f"- [{issue.code.value}] {issue.message}" for issue in issues
    )
    return (
        "\n\n## 已绑定的确定性 review 修复反馈\n"
        "只修复以下 typed review 问题，不得改变冻结来源、事实边界或素材权利。"
        "若问题指出正文 figure 与实体、相邻段落或图注不一致，先删除该错误 "
        "figure 块；仅可用 writing_pack.json 已冻结且与正文事实可直接锚定的另一 "
        "assetId 替换。没有合格替代图时必须移除正文 figure，不得保留错图、虚构"
        "图注、改写素材身份，或按文件名猜测画面：\n"
        f"{rendered_issues}\n"
        "完成后重新读取修改处上下文，确认旧 assetId 已不在错误位置、替代图的"
        " caption 与附近正文事实一致；未满足时继续局部修订。"
    )


def _article_retry_review_feedback_addendum(job: QueueJob, object_dir: Path) -> str:
    return _render_retry_review_feedback(job, object_dir, execution_root(job.execution_id))


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
    elif checkpoint == "post_author":
        prompt += _article_retry_review_feedback_addendum(job, object_dir)
        prompt += _article_repair_addendum(job, object_dir)
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


def author_envelope_requires_reauthoring(
    job: QueueJob,
    envelope_path: Path,
) -> bool:
    """A newer typed repair invalidates a previous author completion."""
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
        return (
            repair_report.is_file()
            and repair_report.stat().st_mtime >= envelope_path.stat().st_mtime
        )
    except OSError as exc:
        raise RuntimeError(
            f"ReliableTask author repair evidence unreadable: {exc}"
        ) from exc


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
    # A repair report is part of the next author job identity.  Discard the
    # superseded envelope before validating it against that newer job; doing
    # the validation first turns the expected sourceRevision/hash change into
    # an unrecoverable mismatch and the repair can never run.
    if author_envelope_requires_reauthoring(job, envelope_path):
        envelope_path.unlink(missing_ok=True)
        return False
    _validate_author_envelope(job, envelope_path)
    if not job.carrier or job.carrier.value != "homepage":
        return True
    parts = str(job.ref or "").strip().strip("/").split("/", 3)
    if len(parts) != 4 or parts[0] != "entity" or not all(parts[1:]):
        raise ValueError(f"ReliableTask homepage ref 不合法：{job.ref!r}")
    from core.homepage_source_failure import (
        SOURCE_RECOVERY_FAILURE_KINDS,
        entity_page_failure_issues,
        entity_page_failure_kind,
        read_entity_page_failure,
    )

    draft_dir = (
        execution_root(job.execution_id) / job.content_object_dir / "4.draft"
    )
    source_failure = read_entity_page_failure(draft_dir)
    if source_failure is not None:
        failure_problems = entity_page_failure_issues(
            source_failure,
            entity_name=parts[3],
        )
        kind = entity_page_failure_kind(source_failure)
        if not failure_problems and kind in SOURCE_RECOVERY_FAILURE_KINDS:
            # Author already applied typed failure protocol; reuse evidence and
            # let build_homepage checkpoint rewind source discovery.
            return True
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


def _recover_completed_author_outcome(
    ctx: ExecutionContext,
    job: QueueJob,
    *,
    checkpoint: str,
    prompt: str,
    outcome: AgentRunOutcome,
) -> AgentRunOutcome | None:
    """Admit a timed-out run only when its durable output is fully provenance-bound."""
    if checkpoint != "post_author" or not outcome.started:
        return None
    from content.execution.agent.agent_checkpoint import (
        _managed_checkpoint_job_issues,
    )
    from content.post.article.draft_io import read_draft_meta

    meta = read_draft_meta(ctx.execution_id, job.ref) or {}
    if _managed_checkpoint_job_issues(
        ctx,
        stage=checkpoint,
        prompt=prompt,
    ):
        return None
    provenance_hashes = (
        "promptSha256",
        "writingPackSha256",
        "sourceBundleSha256",
        "draftSha256",
    )
    if not (
        str(meta.get("executionId") or "") == ctx.execution_id
        and str(meta.get("objectRef") or meta.get("ref") or "") == job.ref
        and str(meta.get("status") or "") == "completed"
        and str(meta.get("provider") or "") == outcome.provider.value
        and str(meta.get("model") or "") == ctx.model
        and bool(str(meta.get("agentRunId") or "").strip())
        and all(
            str(meta.get(field) or "").startswith("sha256:")
            for field in provenance_hashes
        )
    ):
        return None
    if not _durable_author_output_is_quiescent(
        job,
        expected_sha256=str(meta["draftSha256"]),
    ):
        return None
    return AgentRunOutcome.finished(
        provider=outcome.provider,
        run_id=str(meta["agentRunId"]),
        agent_id=str(meta.get("agentId") or ""),
        attempts=outcome.attempts,
        warm_attempts=outcome.warm_attempts,
        duration_ms=outcome.duration_ms,
        completion_mode="durable_output_recovery",
        stdout_tail=outcome.stdout_tail,
        stderr_tail=outcome.stderr_tail,
        request_id=outcome.request_id,
    )


def _durable_author_output_is_quiescent(
    job: QueueJob,
    *,
    expected_sha256: str,
) -> bool:
    content_object_dir = str(job.content_object_dir or "").strip()
    if not content_object_dir:
        return False
    carrier = job.carrier.value if job.carrier else ""
    output_name = "video_script.json" if carrier == "video" else "draft.article.md"
    output_path = (
        execution_root(job.execution_id)
        / content_object_dir
        / "4.draft"
        / output_name
    )
    try:
        baseline = output_path.stat()
        if sha256_file(output_path) != expected_sha256:
            return False
        signature = (baseline.st_mtime_ns, baseline.st_size, expected_sha256)
        for _ in range(_DURABLE_OUTPUT_SETTLE_SAMPLES):
            time.sleep(_DURABLE_OUTPUT_SETTLE_SECONDS)
            observed = output_path.stat()
            current = (
                observed.st_mtime_ns,
                observed.st_size,
                sha256_file(output_path),
            )
            if current != signature:
                return False
        return True
    except OSError:
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
        from content.execution.queue.reliabletask.projection import (
            record_reliabletask_completion,
        )

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
    ctx = _execution_context(job.execution_id, semantic_max_attempts=job.max_attempts)
    checkpoint, prompt = _author_prompt(ctx, job)
    runner = agent_runner or _default_agent_runner
    outcome = coerce_agent_outcome(
        runner(ctx, prompt),
        label=f"ReliableTask author {job.job_id}",
    )
    if not outcome.succeeded:
        recovered = _recover_completed_author_outcome(
            ctx,
            job,
            checkpoint=checkpoint,
            prompt=prompt,
            outcome=outcome,
        )
        if recovered is None:
            failure_kind = outcome.failure_kind.value if outcome.failure_kind else "unknown"
            raise RuntimeError(
                f"ReliableTask author Agent 失败：{failure_kind}: {outcome.message}"
            )
        outcome = recovered
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
    from content.execution.queue.reliabletask.projection import (
        record_reliabletask_completion,
    )

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
