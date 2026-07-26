"""Execution service extracted from the retired monolithic runner."""
from __future__ import annotations
from core.control_types import ExecutionStage, StageStatus
from core.data_issue import DataIssue
from content.execution.support import AUTO, Any, DataIssueCode, DataIssueStage, DataRecoveryAction, ExecutionContext, Mapping, StageResult, _active_spec, _entity_homepages_per_target, _prune_inactive_entity_homepage_artifacts, data_issue, issue_messages, stage_issues

_MEDIA_RECOVERY_BY_CODE = {
    DataIssueCode.MEDIA_ENUMERATION_INCOMPLETE: DataRecoveryAction.REWIND_DOWNLOAD,
    DataIssueCode.MEDIA_DOWNLOAD_INCOMPLETE: DataRecoveryAction.REWIND_DOWNLOAD,
    DataIssueCode.MEDIA_CAPTION_INVALID: DataRecoveryAction.REWIND_COMPOSE,
    DataIssueCode.MEDIA_COVER_CONFLICT: DataRecoveryAction.REWIND_COMPOSE,
}


def _typed_media_validation_issues(
    media_report: Mapping[str, Any],
) -> tuple[DataIssue, ...]:
    return tuple(
        DataIssue(
            code=issue.code,
            stage=DataIssueStage.BUILD_VALIDATE,
            message=issue.message,
            ref=issue.ref,
            lane=issue.lane,
            recovery=_MEDIA_RECOVERY_BY_CODE.get(issue.code, DataRecoveryAction.STOP),
            attributes=issue.attributes,
        )
        for issue in (
            DataIssue.from_dict(row)
            for row in (media_report.get("issues") or [])
            if isinstance(row, Mapping)
        )
    )


def _media_validation_fallback(issues: tuple[DataIssue, ...]) -> ExecutionStage:
    codes = {issue.code for issue in issues}
    if DataIssueCode.MEDIA_ENUMERATION_INCOMPLETE in codes:
        return ExecutionStage.DOWNLOAD_PLAN
    if DataIssueCode.MEDIA_DOWNLOAD_INCOMPLETE in codes:
        return ExecutionStage.DOWNLOAD_FETCH
    return ExecutionStage.BUILD_HOMEPAGE

def _run_download_fetch(ctx: ExecutionContext) -> StageResult:
    from content.execution.agent.auto_research import _download_auto_research_lanes, _entity_ids_grouped_by_type, _refresh_stale_source_plans_for_fetch
    from content.execution.recovery.download_freshness import _content_plan_source_shortfall_entity_ids, _download_content_capacity_preflight, _download_fetch_stale_entity_ids, _resolve_download_content_capacity_shortfall
    from content.execution.recovery.download_gate import _build_prepare_homepage_retry_entity_ids, _download_repair_path, _download_retry_entity_ids, _download_retry_lane, _download_stage_gate_issues
    from content.execution.recovery.download_repair import _record_download_repair
    from content.execution.recovery.download_unresolved import _write_download_availability
    from content.source.handler import handle_download
    from content.source.gate import gate_download

    def current_gate_issues(entity_ids: list[str]) -> list[DataIssue]:
        issues = gate_download(ctx.execution_id, target_entities=set(ctx.entity_ids))
        seen = set(issues)
        for issue in _download_stage_gate_issues(ctx, entity_ids=entity_ids):
            if issue not in seen:
                issues.append(issue)
                seen.add(issue)
        return issues

    retry_entity_ids = _download_retry_entity_ids(ctx)
    build_prepare_retry_entity_ids = _build_prepare_homepage_retry_entity_ids(ctx)
    refresh_before_fetch_ids: list[str] = []
    download_lane_override = ""
    if retry_entity_ids:
        target_entity_ids = retry_entity_ids
        refresh_before_fetch_ids = retry_entity_ids
    elif build_prepare_retry_entity_ids:
        target_entity_ids = build_prepare_retry_entity_ids
        download_lane_override = "homepage"
    else:
        fetch_stale_ids = set(_download_fetch_stale_entity_ids(ctx))
        shortfall_ids = set(_content_plan_source_shortfall_entity_ids(ctx))
        target_ids = fetch_stale_ids | shortfall_ids
        target_entity_ids = [entity_id for entity_id in ctx.entity_ids if entity_id in target_ids]
        refresh_before_fetch_ids = [entity_id for entity_id in ctx.entity_ids if entity_id in shortfall_ids]
    if not target_entity_ids:
        issues = current_gate_issues(ctx.entity_ids)
        if issues:
            _record_download_repair(ctx, issues)
            _write_download_availability(ctx, {}, source="download_fetch_failed")
            return StageResult(
                ExecutionStage.DOWNLOAD_FETCH,
                AUTO,
                StageStatus.FAILED,
                "persisted download artifacts do not satisfy the frozen target set:\n  - "
                + "\n  - ".join(issue_messages(issues[:10])),
                fallback_stage=ExecutionStage.DOWNLOAD_PLAN,
                issue_records=issues,
            )
        capacity_result = _resolve_download_content_capacity_shortfall(
            ctx,
            _download_content_capacity_preflight(ctx),
        )
        if capacity_result is not None:
            return capacity_result
        _write_download_availability(ctx, {}, source="download_fetch_passed")
        return StageResult(
            ExecutionStage.DOWNLOAD_FETCH,
            AUTO,
            StageStatus.DONE,
            "current persisted download gate already passes",
        )
    if refresh_before_fetch_ids:
        _refresh_stale_source_plans_for_fetch(ctx, refresh_before_fetch_ids)
    if target_entity_ids != ctx.entity_ids:
        print(
            "[task execute] download object repair/refresh: "
            + ", ".join(target_entity_ids)
        )
    download_lane = download_lane_override or _download_retry_lane(ctx, target_entity_ids)
    active_download_lanes = _download_auto_research_lanes(ctx)
    if download_lane == "all" and active_download_lanes and len(active_download_lanes) == 1:
        download_lane = next(iter(active_download_lanes))
    if download_lane != "all":
        print(f"[task execute] download lane-scoped repair: lane={download_lane}")
    fallback_entity_type = (
        ctx.spec.scope.entity_types[0] if ctx.spec.scope.entity_types else ""
    )
    grouped_targets = _entity_ids_grouped_by_type(
        ctx,
        target_entity_ids,
        fallback_type=fallback_entity_type,
    )
    try:
        grouped_items = list(grouped_targets.items())
        for group_index, (group_type, group_ids) in enumerate(grouped_items):
            if not group_ids:
                continue
            handle_download(
                execution_id=ctx.execution_id,
                entity_ids=group_ids,
                entity_type=group_type,
                lane=download_lane,
                max_workers=max(1, int(ctx.max_workers or 1)),
                defer_gate=group_index < len(grouped_items) - 1,
            )
    except SystemExit as exc:
        code = int(getattr(exc, "code", 1) or 0)
        if code not in (0,):
            issues = current_gate_issues(target_entity_ids)
            if not issues:
                issues = [data_issue(
                    DataIssueCode.INTERNAL_UNEXPECTED,
                    stage=DataIssueStage.DOWNLOAD_FETCH,
                    recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
                    message="download handler exited non-zero without persisted gate issues",
                    attributes={"exitCode": code},
                )]
            rendered_issues = issue_messages(issues)
            _record_download_repair(ctx, issues)
            _write_download_availability(ctx, {}, source="download_fetch_failed")
            message = f"download gate failed with exit code {code}"
            if issues:
                message += ": " + "; ".join(rendered_issues[:5])
            return StageResult(
                ExecutionStage.DOWNLOAD_FETCH,
                AUTO,
                StageStatus.FAILED,
                message,
                fallback_stage=ExecutionStage.DOWNLOAD_PLAN,
                issue_records=issues,
            )
    except Exception as exc:  # noqa: BLE001
        issue = data_issue(
            DataIssueCode.INTERNAL_UNEXPECTED,
            stage=DataIssueStage.DOWNLOAD_FETCH,
            recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
            message="download handler raised an unexpected exception",
            attributes={"errorType": type(exc).__name__},
        )
        _record_download_repair(ctx, [issue])
        _write_download_availability(ctx, {}, source="download_fetch_failed")
        return StageResult(
            ExecutionStage.DOWNLOAD_FETCH,
            AUTO,
            StageStatus.FAILED,
            f"download handler failed: {type(exc).__name__}",
            fallback_stage=ExecutionStage.DOWNLOAD_PLAN,
            issue_records=[issue],
        )
    issues = current_gate_issues(target_entity_ids)
    if issues:
        rendered_issues = issue_messages(issues)
        _record_download_repair(ctx, issues)
        _write_download_availability(ctx, {}, source="download_fetch_failed")
        return StageResult(
            ExecutionStage.DOWNLOAD_FETCH,
            AUTO,
            StageStatus.FAILED,
            "download gate failed:\n  - " + "\n  - ".join(rendered_issues[:10]),
            fallback_stage=ExecutionStage.DOWNLOAD_PLAN,
            issue_records=issues,
        )
    repair_path = _download_repair_path(ctx)
    if repair_path.is_file():
        repair_path.unlink()
    _write_download_availability(ctx, {}, source="download_fetch_passed")
    capacity_result = _resolve_download_content_capacity_shortfall(
        ctx,
        _download_content_capacity_preflight(ctx),
    )
    if capacity_result is not None:
        return capacity_result
    return StageResult(
        ExecutionStage.DOWNLOAD_FETCH,
        AUTO,
        StageStatus.DONE,
        "fetched sources for " + ", ".join(target_entity_ids),
    )

def _run_build_prepare(ctx: ExecutionContext) -> StageResult:
    from content.homepage.homepage import homepage_runtime_spec, validate_entity_page_inputs
    from content.homepage.homepage_prepare import prepare_entity_pages
    if _entity_homepages_per_target(ctx) <= 0:
        return StageResult(
            ExecutionStage.BUILD_PREPARE,
            AUTO,
            StageStatus.DONE,
            "entityHomepagesPerTarget=0；非主页载体跳过主页输入准备",
        )
    active_spec = homepage_runtime_spec(ctx.execution_id, _active_spec(ctx))
    _prune_inactive_entity_homepage_artifacts(ctx, reason="build_prepare active target sync")
    inputs_dir, refs = prepare_entity_pages(ctx.execution_id, active_spec)
    issues = validate_entity_page_inputs(ctx.execution_id, active_spec)
    if issues:
        return StageResult(
            ExecutionStage.BUILD_PREPARE,
            AUTO,
            StageStatus.FAILED,
            "主页输入未就绪，需回到 download_plan/download_fetch 修复上游来源:\n  - "
            + "\n  - ".join(issue_messages(issues[:10])),
            fallback_stage=ExecutionStage.DOWNLOAD_PLAN,
            issue_records=issues,
        )
    return StageResult(ExecutionStage.BUILD_PREPARE, AUTO, StageStatus.DONE, f"下发 {len(refs)} 个主页产出契约 -> {inputs_dir}")

def _run_build_validate(ctx: ExecutionContext) -> StageResult:
    from content.execution.controller.homepage_review_stage import run_homepage_independent_reviews
    from content.homepage.homepage import homepage_runtime_spec
    from content.homepage.homepage_release_validation import validate_entity_pages
    from verify.verify_homepage_media_completeness import homepage_media_completeness_report
    if _entity_homepages_per_target(ctx) <= 0:
        return StageResult(
            ExecutionStage.BUILD_VALIDATE,
            AUTO,
            StageStatus.DONE,
            "entityHomepagesPerTarget=0；非主页载体跳过主页采纳门",
        )
    runtime_spec = homepage_runtime_spec(ctx.execution_id, _active_spec(ctx))
    issues = validate_entity_pages(ctx.execution_id, runtime_spec)
    if issues:
        return StageResult(
            ExecutionStage.BUILD_VALIDATE,
            AUTO,
            StageStatus.FAILED,
            "主页采纳门未过:\n  - " + "\n  - ".join(issues[:10]),
            fallback_stage=ExecutionStage.BUILD_HOMEPAGE,
            issue_records=stage_issues(
                ExecutionStage.BUILD_VALIDATE,
                issues,
                code=DataIssueCode.QUALITY_FAILED,
                recovery=DataRecoveryAction.REWIND_COMPOSE,
            ),
        )
    media_report = homepage_media_completeness_report(ctx.execution_id)
    if not bool(media_report.get("passed")):
        typed_issues = _typed_media_validation_issues(media_report)
        media_issues = issue_messages(typed_issues)
        return StageResult(
            ExecutionStage.BUILD_VALIDATE,
            AUTO,
            StageStatus.FAILED,
            "主页图片完整性门未过:\n  - " + "\n  - ".join(media_issues[:10]),
            fallback_stage=_media_validation_fallback(typed_issues),
            issue_records=typed_issues or stage_issues(
                ExecutionStage.BUILD_VALIDATE,
                ["homepage media completeness report did not pass"],
                code=DataIssueCode.CONTRACT_INVALID,
            ),
        )
    review_issues = run_homepage_independent_reviews(ctx, runtime_spec)
    if review_issues:
        return StageResult(
            ExecutionStage.BUILD_VALIDATE,
            AUTO,
            StageStatus.FAILED,
            "主页独立审阅未过:\n  - " + "\n  - ".join(review_issues[:10]),
            fallback_stage=ExecutionStage.BUILD_HOMEPAGE,
            issue_records=stage_issues(
                ExecutionStage.BUILD_VALIDATE,
                review_issues,
                code=DataIssueCode.AGENT_REVIEW_INVALID,
                recovery=DataRecoveryAction.REWIND_COMPOSE,
            ),
        )
    return StageResult(ExecutionStage.BUILD_VALIDATE, AUTO, StageStatus.DONE, "所有 coverage 实体主页及独立审阅达标")
