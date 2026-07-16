"""Workflow service extracted from the retired monolithic runner."""
from __future__ import annotations
from core.control_types import ExecutionStage, StageStatus
from content.execution.coverage import coverage_entity_type, coverage_entity_type_for_entity
from content.execution.support import AUTO, Any, DataIssue, DataIssueCode, DataIssueStage, DataRecoveryAction, ExecutionContext, Mapping, Path, Sequence, StageResult, _active_spec, article_commercial_closure_enabled, data_issue, execution_command_root, execution_root, image_count_is_hard_quota, minimum_publishable_images_per_target, read_json, write_json

def _download_source_units_mtime_ns(ctx: ExecutionContext, entity_id: str, etype: str) -> int:
    from content.source.source_unit import iter_source_units, resolve_entity_object_dir
    object_dir = resolve_entity_object_dir(
        ctx.execution_id,
        entity_id,
        etype_hint=etype,
    )
    source_units = iter_source_units(object_dir)
    if not source_units:
        return 0
    mtimes: list[int] = []
    for unit in source_units:
        for path in unit.rglob("*"):
            if not path.is_file():
                continue
            try:
                mtimes.append(path.stat().st_mtime_ns)
            except OSError:
                continue
    return max(mtimes, default=0)

def _download_report_mtime_ns(ctx: ExecutionContext, entity_id: str) -> int:
    result_root = execution_command_root(ctx.execution_id, "source") / "results"
    bundle_gate = result_root / "entity_source_bundle_gate" / f"{entity_id}.json"
    if not bundle_gate.is_file():
        return 0
    candidates = [
        result_root / "source_plan_gate" / f"{entity_id}.json",
        result_root / "image_rights_gate" / f"{entity_id}.json",
        result_root / "image_fetch_gate" / f"{entity_id}.json",
        bundle_gate,
    ]
    mtimes: list[int] = []
    for path in candidates:
        if path.is_file():
            try:
                mtimes.append(path.stat().st_mtime_ns)
            except OSError:
                continue
    return min(mtimes) if mtimes else 0

def _download_fetch_rule_mtime_ns() -> int:
    scripts_root = Path(__file__).resolve().parents[3]
    candidates = [
        scripts_root / "content" / "source" / "handler_fetch.py",
        scripts_root / "content" / "source" / "handler.py",
        scripts_root / "content" / "source" / "source_unit.py",
        scripts_root / "content" / "source" / "research" / "image_provider_compliance.py",
        scripts_root.parent / "verticals" / "travel" / "rights" / "license_policy.yaml",
    ]
    return max((path.stat().st_mtime_ns for path in candidates if path.is_file()), default=0)

def _download_fetch_stale_entity_ids(ctx: ExecutionContext) -> list[str]:
    """Entities whose source plans are newer than fetched source units/reports."""
    from content.execution.recovery.download_gate import _source_plan_lane_paths
    etype = coverage_entity_type(ctx.spec)
    fetch_rule_mtime = _download_fetch_rule_mtime_ns()
    stale: list[str] = []
    for entity_id in ctx.entity_ids:
        entity_etype = coverage_entity_type_for_entity(ctx.spec, entity_id) or etype
        plan_mtime = max(
            (
                path.stat().st_mtime_ns
                for path in _source_plan_lane_paths(ctx, entity_id, entity_etype)
                if path.is_file()
            ),
            default=0,
        )
        if not plan_mtime:
            continue
        units_mtime = _download_source_units_mtime_ns(ctx, entity_id, entity_etype)
        report_mtime = _download_report_mtime_ns(ctx, entity_id)
        if (
            not units_mtime
            or not report_mtime
            or plan_mtime > units_mtime
            or plan_mtime > report_mtime
            or (fetch_rule_mtime and units_mtime < fetch_rule_mtime)
            or (fetch_rule_mtime and report_mtime < fetch_rule_mtime)
        ):
            stale.append(entity_id)
    return stale

def _content_plan_source_shortfall_entity_ids(ctx: ExecutionContext) -> list[str]:
    if article_commercial_closure_enabled(ctx.spec):
        return []
    diagnostics_path = execution_root(ctx.execution_id) / "_shared" / "content_plan_source_diagnostics.json"
    if not diagnostics_path.is_file():
        return []
    try:
        diagnostics = read_json(diagnostics_path)
    except (OSError, ValueError, TypeError):
        return []
    targets = diagnostics.get("targets") if isinstance(diagnostics.get("targets"), dict) else {}
    quotas = ((ctx.spec.get("content") or {}).get("quotas") or {})
    required_articles = int(quotas.get("entityArticlesPerTarget") or 0)
    required_images = (
        int(quotas.get("imageWorksPerTarget") or 0)
        if image_count_is_hard_quota(ctx.spec)
        else minimum_publishable_images_per_target(ctx.spec)
    )
    shortfall: set[str] = set()
    for entity_id, row in targets.items():
        if not isinstance(row, dict):
            continue
        if required_articles and int(row.get("pickedArticleBaseSources") or 0) < required_articles:
            shortfall.add(str(entity_id))
        if required_images and int(row.get("pickedImageSources") or 0) < required_images:
            shortfall.add(str(entity_id))
    return [entity_id for entity_id in ctx.entity_ids if entity_id in shortfall]

def _download_content_capacity_preflight(ctx: ExecutionContext) -> list[DataIssue]:
    """Run content-plan source capacity gate immediately after download_fetch."""
    from content.execution.pipeline.content_plan_prep import _content_capacity_gate_for_entity
    active_spec = _active_spec(ctx)
    quotas = (active_spec.get("content") or {}).get("quotas") or {}
    required_articles = int(quotas.get("entityArticlesPerTarget") or 0)
    required_images = int(quotas.get("imageWorksPerTarget") or 0)
    if required_articles <= 0 and required_images <= 0:
        return []
    diagnostics: dict[str, Any] = {
        "schemaVersion": "quwoquan_data.content_plan_source_diagnostics",
        "executionId": ctx.execution_id,
        "generatedBy": "download_fetch_content_capacity_preflight",
        "targets": {},
    }
    issues: list[DataIssue] = []
    for entity_id in ctx.entity_ids:
        ok, entity_issues, row = _content_capacity_gate_for_entity(
            ctx,
            entity_id,
            active_spec=active_spec,
        )
        if row:
            diagnostics["targets"][entity_id] = row
        if not ok:
            issues.append(data_issue(
                DataIssueCode.SOURCE_RETAINED_SHORTFALL,
                stage=DataIssueStage.DOWNLOAD_FETCH,
                ref=entity_id,
                recovery=DataRecoveryAction.STOP,
                message="; ".join(str(issue) for issue in entity_issues),
                attributes={
                    "requiredArticles": required_articles,
                    "requiredImages": required_images,
                },
            ))
    write_json(
        execution_root(ctx.execution_id) / "_shared" / "content_plan_source_diagnostics.json",
        diagnostics,
    )
    return issues

def _resolve_download_content_capacity_shortfall(
    ctx: ExecutionContext,
    issues: Sequence[DataIssue],
) -> StageResult | None:
    if not issues:
        return None
    return StageResult(
        ExecutionStage.DOWNLOAD_FETCH,
        AUTO,
        StageStatus.FAILED,
        "download_fetch content capacity preflight failed for frozen targets",
        fallback_stage=ExecutionStage.DOWNLOAD_PLAN,
        issue_records=list(issues),
    )
