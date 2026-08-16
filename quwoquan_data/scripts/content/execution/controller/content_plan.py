from __future__ import annotations

from core.entity_focus import classify_entity_focus as _classify_entity_focus
from core.entity_focus import (
    coverage_targets_mentioned as _coverage_targets_mentioned,
)

from content.execution import support as _support
from content.execution.controller import content_plan_assets as _plan_assets
from content.execution.controller.content_plan_asset_semantics import (
    admitted_article_asset_rows as _admitted_article_asset_rows,
)
from content.execution.controller.content_plan_asset_semantics import (
    article_target_scope as _article_target_scope,
)
from content.execution.controller.content_plan_decisions import (
    ContentPlanRejectLedger,
    missing_source_diagnostic,
)
from content.execution.coverage import (
    coverage_entity_type,
    coverage_entity_type_for_entity,
)
from content.execution.support import Any, Mapping

_EXTRACTED_DEPENDENCIES = (
    ContentPlanRejectLedger,
    _admitted_article_asset_rows,
    _article_target_scope,
    _classify_entity_focus,
    _coverage_targets_mentioned,
    _plan_assets,
    coverage_entity_type,
    coverage_entity_type_for_entity,
    missing_source_diagnostic,
)


def _auto_content_plan(
    ctx: _support.ExecutionContext, active_spec: Mapping[str, Any]
) -> list[_support.DataIssue]:
    from content.execution.controller.planning.auto_content_plan import (
        auto_content_plan,
    )

    return auto_content_plan(ctx, active_spec)
