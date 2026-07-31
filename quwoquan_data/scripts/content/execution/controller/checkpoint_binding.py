"""Frozen research-output binding check for the download-plan checkpoint."""
from __future__ import annotations

from core.control_types import ExecutionStage, StageStatus
from content.execution.support import (
    CHECKPOINT,
    DataIssueCode,
    DataIssueStage,
    DataRecoveryAction,
    ExecutionContext,
    StageResult,
    data_issue,
)
from content.source.prepare import research_entity_type_binding_error


def source_plan_binding_failure(ctx: ExecutionContext) -> StageResult | None:
    """Convert a canonical entity-type drift into a fail-closed stage result."""
    binding_error = research_entity_type_binding_error(ctx.execution_id)
    if not binding_error:
        return None
    issue = data_issue(
        DataIssueCode.SOURCE_PLAN_INVALID,
        stage=DataIssueStage.DOWNLOAD_PLAN,
        ref=ctx.execution_id,
        recovery=DataRecoveryAction.STOP,
        message=binding_error,
    )
    return StageResult(
        ExecutionStage.DOWNLOAD_PLAN,
        CHECKPOINT,
        StageStatus.FAILED,
        "download_plan detected source output outside frozen entity type binding",
        issue_records=(issue,),
    )


__all__ = ["source_plan_binding_failure"]
