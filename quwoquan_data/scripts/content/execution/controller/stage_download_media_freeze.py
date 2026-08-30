"""`1.download` 收尾的 homepage 逐图处置冻结（DEC-029）。"""
from __future__ import annotations

from core.control_types import ExecutionStage, StageStatus

from content.execution.support import (
    AUTO,
    DataIssueCode,
    DataIssueStage,
    DataRecoveryAction,
    ExecutionContext,
    StageResult,
    _entity_homepages_per_target,
    data_issue,
)


def freeze_homepage_media_dispositions_for_stage(
    ctx: ExecutionContext,
) -> StageResult | None:
    """在 `1.download` 收尾一次冻结 homepage 逐图处置与 `assetId`（DEC-029）。

    挂在 stage 的成功出口而不是 fetch handler 内部：来源字节已就位、fetch 被短路时
    handler 根本不会被调用，而阶段仍要交付这份处置，否则完成判据在那条路径上永远
    不可满足。写入是 create-once，重跑同一结论幂等，结论不同则失败。

    返回 `None` 表示无需冻结或已冻结完成；返回 StageResult 表示阶段失败。
    """
    if _entity_homepages_per_target(ctx) <= 0:
        return None
    from content.execution.agent.auto_research import _entity_ids_grouped_by_type
    from content.homepage.homepage_media_freeze import (
        freeze_homepage_media_dispositions,
    )
    from governance.coverage.entity_extract import require_domain_etype

    fallback_entity_type = (
        ctx.spec.scope.entity_types[0] if ctx.spec.scope.entity_types else ""
    )
    grouped = _entity_ids_grouped_by_type(
        ctx,
        list(ctx.entity_ids),
        fallback_type=fallback_entity_type,
    )
    for entity_type, entity_ids in grouped.items():
        if not entity_ids:
            continue
        domain, etype = require_domain_etype(
            entity_type,
            context=f"homepage media freeze for execution={ctx.execution_id}",
        )
        for entity_id in entity_ids:
            try:
                freeze_homepage_media_dispositions(
                    ctx.execution_id, domain, etype, entity_id
                )
            except (OSError, ValueError) as exc:
                issue = data_issue(
                    DataIssueCode.CONTRACT_INVALID,
                    stage=DataIssueStage.DOWNLOAD_FETCH,
                    ref=entity_id,
                    recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
                    message=f"homepage media disposition freeze failed: {exc}",
                )
                return StageResult(
                    ExecutionStage.DOWNLOAD_FETCH,
                    AUTO,
                    StageStatus.FAILED,
                    f"homepage media disposition freeze failed for {entity_id}",
                    fallback_stage=ExecutionStage.DOWNLOAD_PLAN,
                    issue_records=[issue],
                )
    return None
