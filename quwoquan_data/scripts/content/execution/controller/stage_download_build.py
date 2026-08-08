"""Execution service extracted from the retired monolithic runner."""
from __future__ import annotations
from core.control_types import ExecutionStage, StageStatus
from core.data_issue import DataIssue
from content.execution.diagnostics import unexpected_stage_issue
from content.execution.workspace import ExecutionSourceDigestDriftError
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


def _source_digest_drift_issue(
    error: ExecutionSourceDigestDriftError,
) -> DataIssue:
    """Render immutable input drift without treating it as a source retry."""
    return data_issue(
        DataIssueCode.CONTRACT_INVALID,
        stage=DataIssueStage.DOWNLOAD_FETCH,
        recovery=DataRecoveryAction.STOP,
        message="execution source digest drift; execution must be recreated",
        attributes={"contract": "sourceDigest", "reason": str(error)},
    )


def _run_download_fetch(ctx: ExecutionContext) -> StageResult:
    from content.execution.agent.auto_research import _download_auto_research_lanes, _entity_ids_grouped_by_type, _refresh_stale_source_plans_for_fetch
    from content.execution.recovery.download_freshness import _content_plan_source_shortfall_entity_ids, _download_content_capacity_preflight, _download_fetch_stale_entity_ids, _resolve_download_content_capacity_shortfall
    from content.execution.recovery.download_gate import _build_prepare_homepage_retry_entity_ids, _download_repair_path, _download_retry_entity_ids, _download_retry_lane, _download_stage_gate_issues
    from content.execution.recovery.download_repair import _record_download_repair
    from content.execution.recovery.download_unresolved import (
        absorb_download_shortfall_if_any_ready,
        _write_download_availability,
    )
    from content.source.handler import handle_download
    from content.source.gate import gate_download

    # A prior fetch pass may have already produced an auditable frozen-pool
    # partition with enough homepage-ready targets. Do not requeue its
    # ineligible oversample tail: doing so reopens a settled discard decision
    # and burns the ReAct budget before build_prepare can consume that scope.
    persisted_availability = _write_download_availability(
        ctx,
        {},
        source="download_fetch_resume",
    )
    persisted_absorbed = absorb_download_shortfall_if_any_ready(
        ctx,
        persisted_availability,
        stage=DataIssueStage.DOWNLOAD_FETCH,
        stage_enum=ExecutionStage.DOWNLOAD_FETCH,
        auto_mode=AUTO,
        done_status=StageStatus.DONE,
    )
    if persisted_absorbed is not None:
        return persisted_absorbed

    def current_gate_issues(entity_ids: list[str]) -> list[DataIssue]:
        issues = gate_download(ctx.execution_id, target_entities=set(ctx.entity_ids))
        seen = set(issues)
        for issue in _download_stage_gate_issues(ctx, entity_ids=entity_ids):
            if issue not in seen:
                issues.append(issue)
                seen.add(issue)
        return issues

    def _fail_or_absorb(
        *,
        issues: list[DataIssue],
        message: str,
        source: str,
    ) -> StageResult:
        _record_download_repair(ctx, issues)
        availability = _write_download_availability(ctx, {}, source=source)
        absorbed = absorb_download_shortfall_if_any_ready(
            ctx,
            availability,
            stage=DataIssueStage.DOWNLOAD_FETCH,
            stage_enum=ExecutionStage.DOWNLOAD_FETCH,
            auto_mode=AUTO,
            done_status=StageStatus.DONE,
        )
        if absorbed is not None:
            return absorbed
        return StageResult(
            ExecutionStage.DOWNLOAD_FETCH,
            AUTO,
            StageStatus.FAILED,
            message,
            fallback_stage=ExecutionStage.DOWNLOAD_PLAN,
            issue_records=issues,
        )

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
            return _fail_or_absorb(
                issues=issues,
                message=(
                    "persisted download artifacts do not satisfy the frozen target set:\n  - "
                    + "\n  - ".join(issue_messages(issues[:10]))
                ),
                source="download_fetch_failed",
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
            message = f"download gate failed with exit code {code}"
            if issues:
                message += ": " + "; ".join(rendered_issues[:5])
            return _fail_or_absorb(
                issues=issues,
                message=message,
                source="download_fetch_failed",
            )
    except ExecutionSourceDigestDriftError as exc:
        issue = _source_digest_drift_issue(exc)
        _record_download_repair(ctx, [issue])
        _write_download_availability(ctx, {}, source="download_fetch_contract_invalid")
        return StageResult(
            ExecutionStage.DOWNLOAD_FETCH,
            AUTO,
            StageStatus.FAILED,
            "download fetch blocked by immutable execution contract drift",
            issue_records=[issue],
        )
    except Exception as exc:  # noqa: BLE001
        issue = unexpected_stage_issue(
            DataIssueStage.DOWNLOAD_FETCH,
            exc,
            recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
            message="download handler raised an unexpected exception",
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
        return _fail_or_absorb(
            issues=issues,
            message="download gate failed:\n  - " + "\n  - ".join(rendered_issues[:10]),
            source="download_fetch_failed",
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

def _qualified_entity_names(verdict: Any) -> tuple[str, ...]:
    """从采纳门的 ``<domain>/<etype>/<name>`` 标签取回实体名。

    准出集合是图片完整性门与来源资格门共同的裁剪口径：两者都只对本批次真正要发布的
    对象负责，过采丢弃对象的素材缺口不参与准出判定。
    """
    names: list[str] = []
    for label in verdict.qualified_refs:
        parts = str(label).split("/")
        if len(parts) >= 3 and parts[2].strip():
            names.append("/".join(parts[2:]).strip())
    return tuple(names)


def _write_homepage_independent_review_repairs(ctx: ExecutionContext) -> None:
    """Turn failed independent reviews into object-bound author retry input."""
    from governance.coverage.entity_extract import entity_ref, require_domain_etype

    from content.execution.controller.homepage_author_finalization import (
        _write_homepage_repair_report,
    )
    from content.homepage.homepage_review import _entity_draft_dir
    from core.io import read_json

    for target in ctx.spec.scope.coverage_targets:
        domain, entity_type = require_domain_etype(
            target.entity_type,
            context=target.name,
        )
        draft_dir = _entity_draft_dir(
            ctx.execution_id,
            domain,
            entity_type,
            target.name,
        )
        result_path = draft_dir.parent / "5.review" / "reviewer_result.json"
        if not result_path.is_file():
            continue
        result = read_json(result_path)
        if not isinstance(result, Mapping) or result.get("verdict") != "failed":
            continue
        issues = tuple(
            str(item).strip()
            for item in (result.get("issues") or [])
            if str(item).strip()
        )
        if not issues:
            continue
        _write_homepage_repair_report(
            ctx,
            object_dir=draft_dir.parent,
            ref=entity_ref(domain, entity_type, target.name),
            materialization_messages=issues,
        )


def _run_build_validate(ctx: ExecutionContext) -> StageResult:
    from content.execution.controller.homepage_review_stage import (
        independent_reviewer_precondition_issues,
        run_homepage_independent_reviews,
    )
    from content.execution.controller.homepage_authoring import homepage_quota_verdict
    from content.homepage.homepage import homepage_runtime_spec
    from verify.verify_homepage_media_completeness import homepage_media_completeness_report
    if _entity_homepages_per_target(ctx) <= 0:
        return StageResult(
            ExecutionStage.BUILD_VALIDATE,
            AUTO,
            StageStatus.DONE,
            "entityHomepagesPerTarget=0；非主页载体跳过主页采纳门",
        )
    verdict = homepage_quota_verdict(ctx)
    if verdict.qualified_count <= 0:
        issues = verdict.blocking_issues() or [
            "homepage validate has no qualified objects"
        ]
        return StageResult(
            ExecutionStage.BUILD_VALIDATE,
            AUTO,
            StageStatus.FAILED,
            f"主页采纳门无合格对象（达标 {verdict.qualified_count}/{verdict.approved_quota}）:\n  - "
            + "\n  - ".join(issues[:10]),
            fallback_stage=ExecutionStage.BUILD_HOMEPAGE,
            issue_records=stage_issues(
                ExecutionStage.BUILD_VALIDATE,
                issues,
                code=DataIssueCode.QUALITY_FAILED,
                recovery=DataRecoveryAction.REWIND_COMPOSE,
            ),
        )
    if not verdict.passed:
        print(
            "[build_validate] quota milestone partial "
            f"{verdict.qualified_count}/{verdict.approved_quota}; "
            "qualified objects continue"
        )
    for line in verdict.discard_summary():
        print(f"[build_validate] {line}")
    media_report = homepage_media_completeness_report(
        ctx.execution_id,
        publishable_names=_qualified_entity_names(verdict),
    )
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
    precondition = independent_reviewer_precondition_issues(ctx.execution_id)
    if precondition:
        return StageResult(
            ExecutionStage.BUILD_VALIDATE,
            AUTO,
            StageStatus.FAILED,
            "主页独立审阅装配未就绪:\n  - " + "\n  - ".join(precondition),
            fallback_stage=ExecutionStage.BUILD_HOMEPAGE,
            issue_records=stage_issues(
                ExecutionStage.BUILD_VALIDATE,
                precondition,
                code=DataIssueCode.AGENT_REVIEW_UNAVAILABLE,
                recovery=DataRecoveryAction.STOP,
            ),
        )
    run_homepage_independent_reviews(
        ctx, homepage_runtime_spec(ctx.execution_id, _active_spec(ctx))
    )
    # 审阅结论逐对象写回 5.review/review.json。审阅未过的对象按丢弃处理；
    # 只要仍有合格对象就 partial 准出，approvedQuota 只保留为规模里程碑。
    reviewed = homepage_quota_verdict(ctx)
    if reviewed.qualified_count <= 0:
        issues = reviewed.blocking_issues() or [
            "homepage independent review produced no qualified objects"
        ]
        _write_homepage_independent_review_repairs(ctx)
        return StageResult(
            ExecutionStage.BUILD_VALIDATE,
            AUTO,
            StageStatus.FAILED,
            f"主页独立审阅后无合格对象（达标 {reviewed.qualified_count}/{reviewed.approved_quota}）:\n  - "
            + "\n  - ".join(issues[:10]),
            fallback_stage=ExecutionStage.BUILD_HOMEPAGE,
            issue_records=stage_issues(
                ExecutionStage.BUILD_VALIDATE,
                issues,
                code=DataIssueCode.AGENT_REVIEW_INVALID,
                recovery=DataRecoveryAction.REWIND_COMPOSE,
            ),
        )
    if not reviewed.passed:
        print(
            "[build_validate] independent review partial "
            f"{reviewed.qualified_count}/{reviewed.approved_quota}; "
            "qualified objects continue"
        )
    for line in reviewed.discard_summary():
        print(f"[build_validate] 审阅丢弃 {line}")
    return StageResult(
        ExecutionStage.BUILD_VALIDATE,
        AUTO,
        StageStatus.DONE,
        "主页采纳门与独立审阅部分通过（合格 "
        f"{reviewed.qualified_count}/{reviewed.approved_quota}）",
    )
