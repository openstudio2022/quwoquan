"""Finalize deterministic content-plan controller outputs."""
from __future__ import annotations

from content.execution.controller.content_plan_decisions import (
    absorb_content_plan_shortfalls,
    persist_content_plan_shortfall_absorb,
)
from content.execution.controller.content_plan_output import (
    write_content_plan_diagnostics,
    write_content_plan_packet,
)
from content.execution.controller.content_plan_prep import _clean_content_plan_outputs
from content.execution.support import (
    Any,
    DataIssue,
    DataIssueCode,
    DataIssueStage,
    DataRecoveryAction,
    ExecutionContext,
    Mapping,
    data_issue,
    data_issues,
)


def finalize_content_plan(
    *,
    ctx: ExecutionContext,
    active_spec: Mapping[str, Any],
    items: list[dict[str, Any]],
    issues: list[DataIssue],
    source_diagnostics: dict[str, dict[str, Any]],
    existing_source_site: dict[str, Any] | None,
) -> list[DataIssue]:
    """Persist a valid plan or return the existing typed blocking issue."""
    from content.execution.identity import parse_execution_id
    from content.post.content_plan_validation import validate_content_plan

    write_content_plan_diagnostics(
        ctx.execution_id,
        source_diagnostics=source_diagnostics,
    )
    if issues:
        # Source/media shortfalls are object dispositions. Any real planned
        # object continues through materialization/review; only a zero-object
        # closure remains blocking.
        absorbed = absorb_content_plan_shortfalls(
            ctx=ctx,
            active_spec=active_spec,
            items=items,
            issues=issues,
            carrier=parse_execution_id(ctx.execution_id).content_type.value,
            persist_absorb=persist_content_plan_shortfall_absorb,
        )
        if not absorbed:
            _clean_content_plan_outputs(ctx)
            return issues
    if not items:
        _clean_content_plan_outputs(ctx)
        return [
            data_issue(
                DataIssueCode.SOURCE_RETAINED_SHORTFALL,
                stage=DataIssueStage.CONTENT_PLAN,
                ref=ctx.execution_id,
                recovery=DataRecoveryAction.REPLACE_SOURCE,
                message="auto content_plan produced no items",
            )
        ]
    write_content_plan_packet(
        ctx.execution_id,
        items=items,
        source_site=existing_source_site,
    )
    return data_issues(
        DataIssueCode.CONTRACT_INVALID,
        stage=DataIssueStage.CONTENT_PLAN,
        messages=validate_content_plan(ctx.execution_id, active_spec),
        recovery=DataRecoveryAction.REWIND_COMPOSE,
    )


__all__ = ["finalize_content_plan"]
