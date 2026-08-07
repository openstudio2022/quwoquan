"""Small checkpoint decisions shared by the execution controller facade."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from content.execution.support import (
    CHECKPOINT,
    DataIssue,
    DataIssueCode,
    DataIssueStage,
    DataRecoveryAction,
    ExecutionContext,
    StageResult,
    _is_homepage_only_execution,
    data_issue,
)
from core.control_types import ExecutionStage, StageStatus


def download_plan_network_outage_result(
    ctx: ExecutionContext,
    auto_report: Mapping[str, Any],
) -> StageResult | None:
    """Turn a zero-progress network outage into a typed retryable failure."""

    outage = auto_report.get("networkOutage")
    if not isinstance(outage, Mapping):
        return None
    updated = [item for item in (auto_report.get("updated") or []) if item]
    if updated:
        return None
    open_hosts = [str(host) for host in (outage.get("openHosts") or [])]
    no_progress = bool(outage.get("noProgress"))
    detail = (
        f"openHosts={','.join(open_hosts) or 'none'}; "
        f"noProgress={str(no_progress).lower()}"
    )
    return StageResult(
        ExecutionStage.DOWNLOAD_PLAN,
        CHECKPOINT,
        StageStatus.FAILED,
        "download_plan network outage: network_unreachable with zero research progress",
        issue_records=[data_issue(
            DataIssueCode.NETWORK_UNREACHABLE,
            stage=DataIssueStage.DOWNLOAD_PLAN,
            recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
            message="auto research network outage with zero progress",
            attributes={"detail": detail},
        )],
    )


def strict_source_unavailable_issues(
    _ctx: ExecutionContext,
    issues: Sequence[DataIssue],
) -> bool:
    """Return whether every issue is a deterministic source shortfall."""

    deterministic_codes = {
        DataIssueCode.SOURCE_MISSING,
        DataIssueCode.SOURCE_RETAINED_SHORTFALL,
        DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
    }
    return bool(issues) and all(issue.code in deterministic_codes for issue in issues)


def checkpoint_post_author(ctx: ExecutionContext) -> StageResult:
    """Resolve the post-author checkpoint without owning orchestration state."""

    from content.execution.controller.homepage_authoring import _drafts_authored

    if _is_homepage_only_execution(ctx):
        return StageResult(
            ExecutionStage.POST_AUTHOR,
            CHECKPOINT,
            StageStatus.DONE,
            "homepage-only 批次主页正文已在 build_homepage 由 Agent 创作，post_author 确定性跳过",
        )
    ok, pending = _drafts_authored(ctx)
    if ok:
        return StageResult(
            ExecutionStage.POST_AUTHOR,
            CHECKPOINT,
            StageStatus.DONE,
            "文章/主页正文已由 Agent 创作，图片作品采用结构化证据包",
        )
    from content.execution.queue.reliabletask.jobs import prepare_reliable_author_jobs

    prepare_reliable_author_jobs(ctx, "post_author")
    hint = (
        "[CHECKPOINT post_author] Agent 逐篇创作文章/主页正文(generator=agent)：\n"
        "  草稿目录: posts/<type>/<angle>/<title>/<seq>/4.draft/\n"
        "  读 <ref>/prompt.md + <ref>/writing_pack.json，文章/主页写回 <ref>/draft.article.md\n"
        "  图片作品不得生成 draft.article.md，只能使用 sourceCollection/assets/caption 结构化证据包\n"
        "  draft_meta 记 model/styleFamily/openingStrategy/extractedEntities\n"
        f"  待创作: {pending}\n"
        "  完成后: 由当前 task execute 调度器继续执行，不得调用其它工作流入口"
    )
    return StageResult(
        ExecutionStage.POST_AUTHOR,
        CHECKPOINT,
        StageStatus.WAITING,
        "等待 Agent 创作正文",
        hint,
    )
