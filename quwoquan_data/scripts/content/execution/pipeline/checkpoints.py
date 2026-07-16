"""Workflow service extracted from the retired monolithic runner."""
from __future__ import annotations
from core.control_types import ExecutionStage, StageStatus
from content.execution.coverage import coverage_entity_type, coverage_entity_type_for_entity
from content.execution.support import Any, CHECKPOINT, DataIssue, DataIssueCode, DataIssueStage, DataRecoveryAction, ExecutionContext, Mapping, Sequence, StageResult, _active_spec, _entity_homepages_per_target, _is_homepage_only_workflow, data_issue, execution_root, issue_messages, os, stage_issues, write_json

def _download_plan_network_outage_result(
    ctx: ExecutionContext,
    auto_report: Mapping[str, Any],
) -> StageResult | None:
    """auto research 判定为网络出口故障且零有效进展 → 网络类可自愈失败。
    failedObjects 文案携带 network_unreachable / retry_source_discovery 标记，
    与 recipe._NETWORK_FAILURE_MARKERS 同源：geo-homepages resume 循环据此分类为
    网络类 manual_required，等待出口自愈后自动 resume（实体无 plan payload，
    resume 会重新检索，不烧 Agent token）。
    """
    outage = auto_report.get("networkOutage") if isinstance(auto_report, Mapping) else None
    if not isinstance(outage, Mapping):
        return None
    updated = [item for item in (auto_report.get("updated") or []) if item]
    if updated:
        # 部分成功：网络退化但仍有进展，交由常规缺口修复通道处理。
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

def _checkpoint_download_plan(ctx: ExecutionContext) -> StageResult:
    from content.execution.agent.auto_research import _run_download_auto_research
    from content.execution.recovery.download_gate import _download_retry_entity_ids, _stale_source_plan_entities
    from content.execution.recovery.download_unresolved import _build_prepare_homepage_unresolved_entities, _download_plan_repair_exhausted_unresolved, _download_plan_unresolved_entities, _format_download_unresolved, _homepage_source_failure_entities, _write_download_plan_availability
    from content.execution.recovery.stage_reset import _source_plan_filled, _source_plan_issue_records
    ok, missing = _source_plan_filled(ctx)
    current_unresolved = _download_plan_unresolved_entities(ctx)
    build_prepare_unresolved = _build_prepare_homepage_unresolved_entities(ctx)
    homepage_source_failures = _homepage_source_failure_entities(ctx)
    unresolved_ids = [
        entity_id for entity_id in ctx.entity_ids
        if entity_id in current_unresolved
    ]
    build_prepare_ids = [
        entity_id for entity_id in ctx.entity_ids
        if entity_id in build_prepare_unresolved
    ]
    homepage_source_failure_ids = [
        entity_id for entity_id in ctx.entity_ids
        if entity_id in homepage_source_failures
    ]
    retry_ids = _download_retry_entity_ids(ctx)
    missing_records = _source_plan_issue_records(ctx)
    missing_ids = [
        entity_id
        for entity_id in ctx.entity_ids
        if any(issue.ref == entity_id for issue in missing_records)
    ]
    repair_scope = (
        homepage_source_failure_ids
        or unresolved_ids
        or retry_ids
        or missing_ids
        or build_prepare_ids
    )
    if not repair_scope and len(ctx.entity_ids) == 1:
        repair_scope = list(ctx.entity_ids)
    stale_entities = (
        _stale_source_plan_entities(ctx, entity_ids=repair_scope)
        if repair_scope
        else []
    )
    if ok and not stale_entities:
        if homepage_source_failures:
            missing = _format_download_unresolved(
                homepage_source_failures,
                prefix=ExecutionStage.BUILD_HOMEPAGE,
            )
        elif build_prepare_unresolved:
            missing = _format_download_unresolved(
                build_prepare_unresolved,
                prefix=ExecutionStage.BUILD_PREPARE,
            )
        else:
            _write_download_plan_availability(ctx, {})
            return StageResult(
                ExecutionStage.DOWNLOAD_PLAN,
                CHECKPOINT,
                StageStatus.DONE,
                "三路 research plan 已就绪",
            )
    if stale_entities:
        stale_ids = [str(item.get("entityId") or "") for item in stale_entities if item.get("entityId")]
        missing = [
            f"{entity_id}: source_plan predates source registry/rights policy; force auto research"
            for entity_id in stale_ids
        ]
    # 预置 homepage/article/image 三路计划骨架，由独立 Agent 填充。
    from content.source.prepare import prepare_source_plan
    etype = coverage_entity_type(ctx.spec)
    stale_ids = [
        str(item.get("entityId") or "") for item in stale_entities
        if item.get("entityId")
    ]
    auto_scope_ids = set(stale_ids)
    if not auto_scope_ids:
        auto_scope_ids.update(repair_scope)
    elif unresolved_ids:
        auto_scope_ids.update(unresolved_ids)
    elif build_prepare_ids:
        auto_scope_ids.update(build_prepare_ids)
    elif homepage_source_failure_ids:
        auto_scope_ids.update(homepage_source_failure_ids)
    if not auto_scope_ids and not ok:
        auto_scope_ids.update(ctx.entity_ids)
    auto_entity_ids = [entity_id for entity_id in ctx.entity_ids if entity_id in auto_scope_ids]
    entities = [
        {
            "entityId": e,
            "canonicalName": e,
            "entityType": coverage_entity_type_for_entity(ctx.spec, e) or etype,
        }
        for e in auto_entity_ids
    ]
    prepare_source_plan(ctx.execution_id, entities)
    if os.environ.get("QWQ_DOWNLOAD_AUTO_RESEARCH", "1") != "0":
        try:
            auto_report = _run_download_auto_research(
                ctx,
                auto_entity_ids,
                entity_type=etype,
                force=bool(
                    stale_entities
                    or unresolved_ids
                    or build_prepare_ids
                    or homepage_source_failure_ids
                ),
            )
        except Exception as exc:  # noqa: BLE001
            write_json(
                execution_root(ctx.execution_id) / "_shared" / "auto_research_plan.json",
                {
                    "schemaVersion": "quwoquan.content.source.auto_research_plan",
                    "executionId": ctx.execution_id,
                    "error": f"{type(exc).__name__}: {exc}",
                },
            )
        else:
            outage_result = _download_plan_network_outage_result(ctx, auto_report)
            if outage_result is not None:
                return outage_result
            if bool(auto_report.get("partialRun")):
                remaining_count = int(auto_report.get("remainingEntityCount") or 0)
                hint = (
                    "download_plan auto research paused after configured wave budget; "
                    f"remainingEntityCount={remaining_count}. Resume the same batch to continue."
                )
                return StageResult(
                    ExecutionStage.DOWNLOAD_PLAN,
                    CHECKPOINT,
                    StageStatus.WAITING,
                    "download_plan auto research partial wave completed",
                    checkpoint_hint=hint,
                    controller_yield=True,
                )
            ok_after_auto, missing_after_auto = _source_plan_filled(ctx)
            stale_after_auto = (
                _stale_source_plan_entities(ctx, entity_ids=auto_entity_ids)
                if ok_after_auto
                else []
            )
            if ok_after_auto and not stale_after_auto:
                _write_download_plan_availability(ctx, {})
                message = "三路 research plan 已由 CLI 自动检索就绪"
                if stale_entities:
                    message += "；过期 source_plan 已按 source registry/rights policy 重算: " + ", ".join(auto_entity_ids[:8])
                return StageResult(ExecutionStage.DOWNLOAD_PLAN, CHECKPOINT, StageStatus.DONE, message)
            if stale_after_auto:
                missing_after_auto = list(missing_after_auto) + [
                    f"{item.get('entityId')}: source_plan still predates source registry/rights policy"
                    for item in stale_after_auto
                    if item.get("entityId")
                ]
            missing = missing_after_auto
    unresolved = _download_plan_unresolved_entities(ctx)
    for entity_id, lanes in build_prepare_unresolved.items():
        entity_lanes = unresolved.setdefault(entity_id, {})
        for lane, issues in lanes.items():
            lane_rows = entity_lanes.setdefault(lane, [])
            for issue in issues:
                if issue not in lane_rows:
                    lane_rows.append(issue)
    _write_download_plan_availability(ctx, unresolved)
    full_missing = _format_download_unresolved(unresolved, prefix="source_plan")
    if full_missing:
        missing = full_missing
    deterministic = _download_plan_repair_exhausted_unresolved(ctx, unresolved)
    if deterministic:
        return StageResult(
            ExecutionStage.DOWNLOAD_PLAN,
            CHECKPOINT,
            StageStatus.FAILED,
            "download_plan frozen targets remain source-unavailable after recovery",
            issue_records=stage_issues(
                ExecutionStage.DOWNLOAD_PLAN,
                _format_download_unresolved(
                    deterministic,
                    prefix="deterministic_source_unavailable",
                ),
                code=DataIssueCode.SOURCE_RETAINED_SHORTFALL,
                recovery=DataRecoveryAction.STOP,
            ),
        )
    quotas = ((ctx.spec.get("content") or {}).get("quotas") or {})
    image_works = max(0, int(quotas.get("imageWorksPerTarget") or 0))
    hint = (
        f"[CHECKPOINT download_plan] 三类独立 Agent 检索真实素材，为以下实体写满足规模化门的 research plan：\n"
        f"  待补实体: {missing}\n"
        f"  写入: entities/<domain>/<type>/<entityId>/1.download/"
        "{homepage,article,image}_source_plan.json\n"
        f"  homepage/article/image 三路互不共用计划；图片按 sourceCollectionId 组织，"
        f"每组授权链完整；{image_works} 是图片评分饱和值，不是默认硬性淘汰门。\n"
        "  完成后: 由当前 task geo-homepages 调度器继续执行，不得调用其它工作流入口"
    )
    return StageResult(
        ExecutionStage.DOWNLOAD_PLAN,
        CHECKPOINT,
        StageStatus.WAITING,
        "等待三路 research Agent",
        hint,
        issue_records=stage_issues(
            ExecutionStage.DOWNLOAD_PLAN,
            list(missing),
            code=DataIssueCode.SOURCE_PLAN_INVALID,
            recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
        ),
    )

def _checkpoint_content_plan(ctx: ExecutionContext) -> StageResult:
    from content.execution.pipeline.content_plan import _auto_content_plan
    from content.execution.pipeline.content_plan_prep import _clean_content_plan_outputs
    from content.execution.pipeline.homepage_authoring import _content_plan_done
    if _is_homepage_only_workflow(ctx):
        _content_plan_done(ctx)
        return StageResult(
            ExecutionStage.CONTENT_PLAN,
            CHECKPOINT,
            StageStatus.DONE,
            "homepage-only 批次无 article/image/route 篇目合同；主页真相源在 build_homepage/build_validate，content_plan 确定性跳过",
        )
    ok, issues = _content_plan_done(ctx)
    if ok:
        return StageResult(ExecutionStage.CONTENT_PLAN, CHECKPOINT, StageStatus.DONE, "证据驱动篇目已就绪")
    from content.post.content_plan import content_plan_quotas_required
    active_spec = _active_spec(ctx)
    if content_plan_quotas_required(active_spec):
        _clean_content_plan_outputs(ctx)
        auto_issues = _auto_content_plan(ctx, active_spec)
        if not auto_issues:
            return StageResult(
                ExecutionStage.CONTENT_PLAN,
                CHECKPOINT,
                StageStatus.DONE,
                "证据驱动篇目已由 CLI 确定性规划就绪",
            )
        issues = auto_issues
        if _strict_source_unavailable_issues(ctx, issues):
            return StageResult(
                ExecutionStage.CONTENT_PLAN,
                CHECKPOINT,
                StageStatus.FAILED,
                "content_plan 存在确定性 source-unavailable；冻结目标不可替换，任务停止",
                issue_records=issues,
                fallback_stage=ExecutionStage.DOWNLOAD_PLAN,
            )
        issues = issue_messages(auto_issues)
    quotas = (active_spec.get("content") or {}).get("quotas") or {}
    acceptance = active_spec.get("acceptance") or {}
    required_angles = [str(a) for a in (acceptance.get("requiredAngles") or []) if str(a)]
    per_target_entity = int(quotas.get("entityArticlesPerTarget") or 0)
    per_target_image = int(quotas.get("imageWorksPerTarget") or 0)
    active_targets = [
        str(target.get("name") or "").strip()
        for target in (active_spec.get("scope") or {}).get("coverageTargets") or []
        if str(target.get("name") or "").strip()
    ]
    entity_q = (
        per_target_entity * len(active_targets)
        if per_target_entity
        else int(quotas.get("entityArticles") or 0)
    ) if content_plan_quotas_required(active_spec) else 0
    route_q = int(quotas.get("routeArticles") or 0) if content_plan_quotas_required(active_spec) else 0
    image_q = (
        per_target_image * len(active_targets)
        if per_target_image
        else 0
    ) if content_plan_quotas_required(active_spec) else 0
    hint = (
        f"[CHECKPOINT content_plan] Agent 通读已下载来源，证据驱动规划 "
        f"{entity_q} 篇文章 + {image_q} 个图片作品 + {route_q} 篇线路：\n"
        f"  产出: batches/{ctx.execution_id}/_shared/content_plan_packet.json\n"
        f"  每条: ref, kind(entity|route), title, entityRefs, evidenceRefs(相对batch路径), rationale, mustIncludeFacts,\n"
        f"        writingIntent(按 acceptance.requiredAngles，单篇唯一主线: {required_angles}),\n"
        f"        article 写 baseSourceRef；image 写 sourceCollectionId/assetRefs，可选 title/caption\n"
        f"  并 register_content_object + 写 posts/.../3.compose/brief.json（禁止预置营销 ref；brief 写入 writingIntent/baseSourceRef）\n"
        f"  未过项:\n    - " + "\n    - ".join(issues[:12]) + "\n"
        "  完成后: 由当前 task geo-homepages 调度器继续执行，不得调用其它工作流入口"
    )
    return StageResult(ExecutionStage.CONTENT_PLAN, CHECKPOINT, StageStatus.WAITING, "等待 Agent 证据驱动篇目规划", hint)

def _strict_source_unavailable_issues(ctx: ExecutionContext, issues: Sequence[DataIssue]) -> bool:
    """True when issues are deterministic source gaps that the stage Agent cannot fix."""
    if not issues:
        return False
    deterministic_codes = {
        DataIssueCode.SOURCE_MISSING,
        DataIssueCode.SOURCE_RETAINED_SHORTFALL,
        DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
    }
    return bool(issues) and all(issue.code in deterministic_codes for issue in issues)

def _checkpoint_build_homepage(ctx: ExecutionContext) -> StageResult:
    from content.execution.recovery.download_unresolved import _format_download_unresolved, _homepage_source_failure_entities
    from content.execution.pipeline.homepage_authoring import _homepages_done
    if _entity_homepages_per_target(ctx) <= 0:
        return StageResult(
            ExecutionStage.BUILD_HOMEPAGE,
            CHECKPOINT,
            StageStatus.DONE,
            "entityHomepagesPerTarget=0；图片作品-only 批次无需主页 Agent 创作",
        )
    ok, issues = _homepages_done(ctx)
    if ok:
        return StageResult(ExecutionStage.BUILD_HOMEPAGE, CHECKPOINT, StageStatus.DONE, "实体主页三件套已就绪")
    source_failures = _homepage_source_failure_entities(ctx)
    if source_failures:
        return StageResult(
            ExecutionStage.BUILD_HOMEPAGE,
            CHECKPOINT,
            StageStatus.FAILED,
            "Agent rejected one or more homepage base sources; rewind source discovery",
            fallback_stage=ExecutionStage.DOWNLOAD_PLAN,
            issue_records=stage_issues(
                ExecutionStage.BUILD_HOMEPAGE,
                _format_download_unresolved(source_failures, prefix=ExecutionStage.BUILD_HOMEPAGE),
                code=DataIssueCode.SOURCE_RETAINED_SHORTFALL,
                recovery=DataRecoveryAction.REWIND_DOWNLOAD,
            ),
        )
    finalize_issues: list[str] = []
    try:
        from content.homepage.homepage import homepage_runtime_spec
        from content.homepage.homepage_release import materialize_entity_pages
        finalize_issues = materialize_entity_pages(
            ctx.execution_id,
            homepage_runtime_spec(ctx.execution_id, _active_spec(ctx)),
        )
    except Exception as exc:  # noqa: BLE001
        finalize_issues = [f"homepage finalize failed: {type(exc).__name__}: {exc}"]
    ok, issues = _homepages_done(ctx)
    if ok:
        return StageResult(
            ExecutionStage.BUILD_HOMEPAGE,
            CHECKPOINT,
            StageStatus.DONE,
            "实体主页三件套已 finalize（Agent 正文 + 资产闭环）并通过采纳门",
        )
    combined_issues = list(finalize_issues or []) + list(issues)
    hint = (
        f"[CHECKPOINT build_homepage] Agent 在底稿基础上轻改创作实体主页正文（不脚本拼接）：\n"
        f"  人读指令: entities/<domain>/<type>/<name>/4.draft/prompt.md\n"
        f"  结构化契约: entities/<domain>/<type>/<name>/3.compose/entity_page_input.json\n"
        f"  写回正文: entities/<domain>/<type>/<name>/4.draft/page.md（覆盖占位，去空白≥350字，保留底稿原句最小改）\n"
        f"  来源判别: 来源目录若有 source.judge.request.json，先做门户/实体主页语义判别写回 source.judge.json\n"
        f"  失败协议: 底稿与实体不一致时按 prompt.md 在 4.draft/ 写 failure.json，不硬写正文\n"
        f"  finalize 自动补封面资产/manifest 并把关贴合度+模板指纹，无需手写 asset:// 或 manifest。\n"
        f"  采纳门未过项:\n    - " + "\n    - ".join(combined_issues[:10]) + "\n"
        "  完成后: 由当前 task geo-homepages 调度器继续执行，不得调用其它工作流入口"
    )
    return StageResult(
        ExecutionStage.BUILD_HOMEPAGE,
        CHECKPOINT,
        StageStatus.WAITING,
        "等待 Agent 写实体主页正文",
        hint,
        issue_records=stage_issues(ExecutionStage.BUILD_HOMEPAGE, combined_issues),
    )

def _checkpoint_post_author(ctx: ExecutionContext) -> StageResult:
    from content.execution.pipeline.homepage_authoring import _drafts_authored
    if _is_homepage_only_workflow(ctx):
        return StageResult(
            ExecutionStage.POST_AUTHOR,
            CHECKPOINT,
            StageStatus.DONE,
            "homepage-only 批次主页正文已在 build_homepage 由 Agent 创作，post_author 确定性跳过",
        )
    ok, pending = _drafts_authored(ctx)
    if ok:
        return StageResult(ExecutionStage.POST_AUTHOR, CHECKPOINT, StageStatus.DONE, "文章/主页正文已由 Agent 创作，图片作品采用结构化证据包")
    hint = (
        f"[CHECKPOINT post_author] Agent 逐篇创作文章/主页正文(generator=agent)：\n"
        f"  草稿目录: posts/<type>/<angle>/<title>/<seq>/4.draft/\n"
        f"  读 <ref>/prompt.md + <ref>/writing_pack.json，文章/主页写回 <ref>/draft.article.md\n"
        f"  图片作品不得生成 draft.article.md，只能使用 sourceCollection/assets/caption 结构化证据包\n"
        f"  draft_meta 记 model/styleFamily/openingStrategy/extractedEntities\n"
        f"  待创作: {pending}\n"
        "  完成后: 由当前 task geo-homepages 调度器继续执行，不得调用其它工作流入口"
    )
    return StageResult(ExecutionStage.POST_AUTHOR, CHECKPOINT, StageStatus.WAITING, "等待 Agent 创作正文", hint)
