from __future__ import annotations
from content.execution.coverage import coverage_entity_type, coverage_entity_type_for_entity
from content.execution.support import Any, DataIssue, DataIssueCode, DataIssueStage, DataIssueLane, DataRecoveryAction, ExecutionContext, Mapping, Path, article_commercial_closure_enabled, data_issue, data_issues, execution_content_plan_packet_path, execution_root, image_count_is_hard_quota, minimum_publishable_images_per_target, read_json, relative_execution_ref, write_json
from content.execution.controller.content_plan_assets import (
    article_asset_claims as _article_asset_claims,
    asset_ref as _asset_ref, asset_rows as _asset_rows, asset_sha as _asset_sha,
    claim as _claim, claims_conflict as _claims_conflict,
    image_claims as _image_claims,
    source_ref as _source_ref,
)
from content.execution.controller.content_plan_output import write_content_plan_diagnostics, write_content_plan_packet
from content.execution.controller.content_plan_decisions import (
    ContentPlanRejectLedger,
    absorb_content_plan_shortfalls,
    missing_source_diagnostic,
    persist_content_plan_shortfall_absorb as _persist_content_plan_shortfall_absorb,
)
from core.entity_focus import (
    VERDICT_STRONG as _VERDICT_STRONG,
    classify_entity_focus as _classify_entity_focus,
    coverage_targets_mentioned as _coverage_targets_mentioned,
)

def _auto_content_plan(ctx: ExecutionContext, active_spec: Mapping[str, Any]) -> list[DataIssue]:
    """Build exact per-entity content plans from validated source units."""
    from content.execution.controller.content_plan_prep import _article_source_quality_sort_key, _assess_content_plan_publish_image, _clean_content_plan_outputs
    from content.execution.planning.source_ready_scope import source_ready_runtime_spec
    from content.post.article.base_draft import load_base_draft_text
    from content.post.article.base_draft_source import extract_source_title
    from core.quality_gates import derive_writing_intent
    from content.post.content_plan import (
        ARTICLE_MIN_BASE_DRAFT_CHARS,
    )
    from content.post.content_plan_validation import validate_content_plan
    from content.post.content_plan_state import load_content_plan_packet
    from content.source.source_unit import resolve_entity_object_dir
    from content.execution.controller.content_plan_contract import (
        resolve_content_plan_contract,
    )
    active_spec = source_ready_runtime_spec(ctx.execution_id, active_spec)
    contract, contract_issues = resolve_content_plan_contract(ctx, active_spec)
    if contract is None:
        return list(contract_issues)
    per_target_articles = contract.articles_per_target
    per_target_images = contract.images_per_target
    per_target_videos = contract.videos_per_target
    minimum_required_articles = contract.minimum_articles
    minimum_required_images = contract.minimum_images
    article_lane_enabled = contract.article_lane_enabled
    image_lane_enabled = contract.image_lane_enabled
    video_lane_enabled = contract.video_lane_enabled
    commercial_closure = contract.commercial_closure
    existing_packet = load_content_plan_packet(ctx.execution_id) or {}
    existing_source_site = (
        dict(existing_packet.get("sourceSite"))
        if isinstance(existing_packet.get("sourceSite"), Mapping)
        else None
    )
    _clean_content_plan_outputs(ctx)
    root = execution_root(ctx.execution_id)
    etype = coverage_entity_type(active_spec)
    targets = [
        str(target.get("name") or "").strip()
        for target in ((active_spec.get("scope") or {}).get("coverageTargets") or [])
        if str(target.get("name") or "").strip()
    ]
    task_region = str(((active_spec.get("scope") or {}).get("region") or "")).strip()
    execution_policy = active_spec.get("executionPolicy") if isinstance(active_spec.get("executionPolicy"), Mapping) else {}
    daily_object_target = int(execution_policy.get("targetObjectCount") or 0)
    if daily_object_target < 1:
        return [data_issue(
            DataIssueCode.CONTRACT_INVALID,
            stage=DataIssueStage.CONTENT_PLAN,
            ref=ctx.execution_id,
            recovery=DataRecoveryAction.STOP,
            message="executionPolicy.targetObjectCount must be a positive frozen execution value",
        )]
    from content.execution.controller.content_plan_schedule import ContentPlanScheduler
    try:
        scheduler = ContentPlanScheduler.load(
            execution_id=ctx.execution_id,
            region=task_region,
            daily_object_target=daily_object_target,
        )
    except (OSError, TypeError, ValueError) as exc:
        return [data_issue(
            DataIssueCode.CONTRACT_INVALID,
            stage=DataIssueStage.CONTENT_PLAN,
            ref=ctx.execution_id,
            recovery=DataRecoveryAction.STOP,
            message=f"creator scheduling contract is invalid: {exc}",
        )]
    used_asset_refs: set[str] = set()
    used_asset_shas: set[str] = set()
    used_collection_ids: set[str] = set()
    used_article_source_refs: set[str] = set()
    items: list[dict[str, Any]] = []
    issues: list[DataIssue] = []
    source_diagnostics: dict[str, dict[str, Any]] = {}
    for target in targets:
        # 目标集可以跨实体类型（如金丝雀 景区+自然景观），必须按冻结目标逐一解析类型，
        # 不能用批级同质 etype（异构集合时为空串，会把对象目录解析到错误类型）。
        target_etype = coverage_entity_type_for_entity(active_spec, target) or etype
        object_dir = resolve_entity_object_dir(ctx.execution_id, target, etype_hint=target_etype)
        from content.source.source_unit import iter_source_units
        source_units = iter_source_units(object_dir)
        if video_lane_enabled:
            from content.execution.controller.content_plan_video import (
                build_video_plan_for_target,
            )
            video_outcome = build_video_plan_for_target(
                ctx=ctx,
                scheduler=scheduler,
                entity_type=target_etype,
                target=target,
                object_dir=object_dir,
                videos_per_target=per_target_videos,
            )
            items.extend(video_outcome.items)
            issues.extend(video_outcome.issues)
            source_diagnostics[target] = video_outcome.diagnostic
            continue
        if not source_units:
            reason = f"{target}: sources directory missing"
            source_diagnostics[target] = missing_source_diagnostic(
                target=target,
                per_target_articles=per_target_articles,
                minimum_articles=minimum_required_articles,
                per_target_images=per_target_images,
                minimum_images=minimum_required_images,
                article_lane_enabled=article_lane_enabled,
                image_lane_enabled=image_lane_enabled,
            )
            if commercial_closure:
                continue
            issues.append(data_issue(
                DataIssueCode.SOURCE_MISSING,
                stage=DataIssueStage.CONTENT_PLAN,
                ref=target,
                lane=(
                    DataIssueLane.IMAGE
                    if image_lane_enabled and not article_lane_enabled
                    else DataIssueLane.ARTICLE
                    if article_lane_enabled and not image_lane_enabled
                    else DataIssueLane.ALL
                ),
                recovery=DataRecoveryAction.REPLACE_SOURCE,
                message=reason,
            ))
            continue
        article_candidates: list[dict[str, Any]] = []
        image_candidates: list[dict[str, Any]] = []
        article_raw_count = 0
        image_raw_count = 0
        rejects = ContentPlanRejectLedger()
        for source_dir in source_units:
            meta_path = source_dir / "meta.json"
            if not meta_path.is_file() or not (source_dir / "source.md").is_file():
                continue
            try:
                meta = read_json(meta_path)
            except (OSError, ValueError, TypeError):
                meta = {}
            source_id = str(meta.get("sourceId") or source_dir.name).strip()
            lane = str(meta.get("researchLane") or "").strip()
            rows = _asset_rows(source_dir)
            if lane == "article":
                if str(meta.get("sourceRole") or "") != "base":
                    continue
                if "support" in source_id.lower() or "support" in source_dir.name.lower():
                    continue
                article_raw_count += 1
                if bool(meta.get("hasVideo")):
                    # P3 文章判据：含视频则放弃——不把视频内容强行图文化为攻略文章。
                    rejects.reject_article("contains_video", source_id, "来源含内联视频，文章类放弃")
                    continue
                source_ref = _source_ref(ctx, source_dir)
                base_body = load_base_draft_text(ctx.execution_id, source_ref)
                from content.post.article.base_draft import base_draft_readiness
                readiness = base_draft_readiness(
                    base_body,
                    publish_media_mode=str(meta.get("publishMediaMode") or ""),
                )
                text_len = int(readiness["effectiveChars"])
                if not readiness["ready"]:
                    rejects.reject_article(
                        "text_too_short",
                        source_id,
                        f"{text_len}<{ARTICLE_MIN_BASE_DRAFT_CHARS}; "
                        f"figures={readiness['inlineFigureCount']} captions={readiness['captionChars']}",
                    )
                    continue
                focus_score, focus_verdict = _classify_entity_focus(
                    base_body,
                    target,
                    title=str(meta.get("title") or ""),
                    sibling_names=targets,
                )
                from core.qunar_template import qunar_article_base_block_reason
                # 与 validate_content_plan 同口径：优先尊重 source unit meta
                # 中的实体锚点判定，避免 Qunar off_entity 游记进入 packet。
                qunar_focus_verdict = str(meta.get("entityFocusVerdict") or "").strip() or focus_verdict
                qunar_block = qunar_article_base_block_reason(meta, qunar_focus_verdict)
                if qunar_block:
                    rejects.reject_article(qunar_block, source_id, "Qunar 模板底稿不可作为当前实体 article base")
                    continue
                # 底稿中心 1:1：实体退化为多标签，文章不再因"未整体指代单一实体"弃稿
                # （多目的地游记照样按单一底稿成稿，实体作为标签集合）；focus 仅留作诊断信号。
                draft_title = extract_source_title(ctx.execution_id, source_ref)
                if not draft_title:
                    # 标题取自底稿：文章源无法提取可用发布标题 → 上游诚实弃稿（不成稿）。
                    rejects.reject_article("no_source_title", source_id, "底稿无法提取发布标题")
                    continue
                entity_tags = sorted(
                    {
                        *_coverage_targets_mentioned(base_body, str(meta.get("title") or ""), targets),
                        target,
                    }
                )
                if not rows:
                    rejects.warn_article_image("no_source_assets", source_id)
                article_candidates.append(
                    {
                        "sourceDir": source_dir,
                        "sourceRef": source_ref,
                        "sourceId": source_id,
                        "title": str(meta.get("title") or source_id),
                        "draftTitle": draft_title,
                        "writingIntent": derive_writing_intent(base_body),
                        "entityTags": entity_tags,
                        "sourceUseMode": str(meta.get("sourceUseMode") or "factual_reference_only"),
                        "sourceClass": str(meta.get("sourceClass") or meta.get("category") or ""),
                        "sourceQualityScore": float(
                            meta.get("sourceQualityScore")
                            or meta.get("qualityScore")
                            or meta.get("score")
                            or 0
                        ),
                        "textLen": text_len,
                        "entityFocusScore": focus_score,
                        "entityFocusVerdict": focus_verdict,
                        "sourceFreshnessTier": str(
                            meta.get("sourceFreshnessTier")
                            or ((meta.get("siteTemplate") or {}).get("freshnessTier") if isinstance(meta.get("siteTemplate"), Mapping) else "")
                            or ""
                        ),
                        "rows": rows,
                    }
                )
            elif lane == "image":
                for row in rows:
                    image_raw_count += 1
                    asset_ref = _asset_ref(ctx, source_dir, row)
                    collection_id = str(row.get("sourceCollectionId") or "").strip()
                    if not asset_ref:
                        rejects.reject_image("missing_asset_ref", source_id)
                        continue
                    if not collection_id:
                        rejects.reject_image("missing_source_collection_id", source_id, asset_ref)
                        continue
                    asset_path = root / asset_ref
                    if not asset_path.is_file():
                        rejects.reject_image("asset_file_missing", source_id, asset_ref)
                        continue
                    verdict = _assess_content_plan_publish_image(asset_path, ctx)
                    if verdict.blocks_image_publish:
                        rejects.reject_image(
                            "image_safety_blocked",
                            source_id,
                            f"{asset_ref}:{'/'.join(verdict.reasons) or verdict.status}",
                        )
                        continue
                    image_candidates.append(
                        {
                            "sourceDir": source_dir,
                            "sourceRef": _source_ref(ctx, source_dir),
                            "sourceId": source_id,
                            "assetRef": asset_ref,
                            "assetSha": _asset_sha(row),
                            "collectionId": collection_id,
                            "caption": str(row.get("caption") or "").strip(),
                            "title": str(meta.get("title") or "").strip(),
                        }
                    )
        article_candidates.sort(key=_article_source_quality_sort_key)
        image_candidates.sort(key=lambda row: (str(row["collectionId"]), str(row["assetRef"])))
        protected_article_refs: set[str] = set()
        protected_article_shas: set[str] = set()
        protected_article_collections: set[str] = set()
        for candidate in article_candidates:
            refs, shas, collections, _asset_refs = _article_asset_claims(ctx, root, candidate)
            _claim(
                refs,
                shas,
                collections,
                claimed_refs=protected_article_refs,
                claimed_shas=protected_article_shas,
                claimed_collections=protected_article_collections,
            )
        picked_images: list[dict[str, Any]] = []
        for candidate in (image_candidates if image_lane_enabled else []):
            if per_target_images and len(picked_images) >= per_target_images:
                break
            refs, shas, collections = _image_claims(candidate)
            if _claims_conflict(
                refs,
                shas,
                collections,
                claimed_refs=protected_article_refs,
                claimed_shas=protected_article_shas,
                claimed_collections=protected_article_collections,
            ) or _claims_conflict(
                refs,
                shas,
                collections,
                claimed_refs=used_asset_refs,
                claimed_shas=used_asset_shas,
                claimed_collections=used_collection_ids,
            ):
                rejects.reject_image(
                    "source_asset_reused",
                    str(candidate.get("sourceId") or candidate.get("sourceRef") or ""),
                    str(candidate.get("assetRef") or ""),
                )
                continue
            picked_images.append(candidate)
            _claim(
                refs,
                shas,
                collections,
                claimed_refs=used_asset_refs,
                claimed_shas=used_asset_shas,
                claimed_collections=used_collection_ids,
            )
        picked_articles: list[dict[str, Any]] = []
        for candidate in (article_candidates if article_lane_enabled else []):
            if per_target_articles and len(picked_articles) >= per_target_articles:
                break
            source_ref = str(candidate.get("sourceRef") or "").strip()
            if source_ref in used_article_source_refs:
                rejects.reject_article("source_ref_reused", str(candidate["sourceId"]))
                continue
            refs, shas, collections, asset_refs = _article_asset_claims(ctx, root, candidate)
            if len(asset_refs) < 2:
                rejects.reject_article(
                    "same_source_cover_body_missing",
                    str(candidate["sourceId"]),
                    "article requires at least two publishable images from its base source unit",
                )
                continue
            if _claims_conflict(
                refs,
                shas,
                collections,
                claimed_refs=used_asset_refs,
                claimed_shas=used_asset_shas,
                claimed_collections=used_collection_ids,
            ):
                rejects.reject_article(
                    "source_asset_reused",
                    str(candidate["sourceId"]),
                )
                continue
            claimed_candidate = dict(candidate)
            claimed_candidate["assetRefs"] = asset_refs
            picked_articles.append(claimed_candidate)
            if source_ref:
                used_article_source_refs.add(source_ref)
            if asset_refs:
                _claim(
                    refs,
                    shas,
                    collections,
                    claimed_refs=used_asset_refs,
                    claimed_shas=used_asset_shas,
                    claimed_collections=used_collection_ids,
                )
        if article_lane_enabled and len(picked_articles) < per_target_articles:
            reason = (
                f"{target}: entityArticlesPerTarget quota {per_target_articles} "
                f"but only picked {len(picked_articles)} qualified article source(s)"
            )
            if commercial_closure:
                pass
            else:
                issues.append(data_issue(
                    DataIssueCode.SOURCE_RETAINED_SHORTFALL,
                    stage=DataIssueStage.CONTENT_PLAN,
                    ref=target,
                    lane=DataIssueLane.ARTICLE,
                    recovery=DataRecoveryAction.REPLACE_SOURCE,
                    message=reason,
                    attributes={
                        "carrier": "article",
                        "required": per_target_articles,
                        "retained": len(picked_articles),
                    },
                ))
        if image_lane_enabled and len(picked_images) < per_target_images:
            reason = (
                f"{target}: imageWorksPerTarget quota {per_target_images} "
                f"but only picked {len(picked_images)} qualified image source(s)"
            )
            if commercial_closure:
                pass
            else:
                issues.append(data_issue(
                    DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
                    stage=DataIssueStage.CONTENT_PLAN,
                    ref=target,
                    lane=DataIssueLane.IMAGE,
                    recovery=DataRecoveryAction.REPLACE_MEDIA,
                    message=reason,
                    attributes={
                        "carrier": "image",
                        "required": per_target_images,
                        "retained": len(picked_images),
                    },
                ))
        from content.execution.controller.content_plan_diagnostics import (
            SourceDiagnosticInput,
            build_source_diagnostic,
        )
        source_diagnostics[target] = build_source_diagnostic(
            SourceDiagnosticInput(
                desired_articles=per_target_articles,
                minimum_articles=minimum_required_articles,
                article_raw_count=article_raw_count,
                article_candidates=tuple(article_candidates),
                picked_articles=tuple(picked_articles),
                desired_images=per_target_images,
                minimum_images=minimum_required_images,
                image_raw_count=image_raw_count,
                image_candidates=tuple(image_candidates),
                picked_images=tuple(picked_images),
                article_lane_enabled=article_lane_enabled,
                image_lane_enabled=image_lane_enabled,
                article_rejects=dict(rejects.article_rejects),
                article_reject_examples=dict(rejects.article_reject_examples),
                article_image_warnings=dict(rejects.article_image_warnings),
                article_image_warning_examples=dict(rejects.article_image_warning_examples),
                image_rejects=dict(rejects.image_rejects),
                image_reject_examples=dict(rejects.image_reject_examples),
            )
        )
        from content.execution.controller.content_plan_items import (
            append_article_plan_items,
            append_image_plan_items,
        )
        append_article_plan_items(
            ctx=ctx,
            scheduler=scheduler,
            entity_type=target_etype,
            target=target,
            candidates=picked_articles,
            items=items,
        )
        append_image_plan_items(
            ctx=ctx,
            scheduler=scheduler,
            entity_type=target_etype,
            target=target,
            candidates=picked_images,
            items=items,
        )
    write_content_plan_diagnostics(ctx.execution_id, source_diagnostics=source_diagnostics)
    if issues:
        from content.execution.identity import parse_execution_id

        # Source/media shortfalls are object dispositions. Any real planned
        # object continues through materialization/review; only a zero-object
        # closure remains blocking.
        absorbed = absorb_content_plan_shortfalls(
            ctx=ctx,
            active_spec=active_spec,
            items=items,
            issues=issues,
            carrier=parse_execution_id(ctx.execution_id).content_type.value,
            persist_absorb=_persist_content_plan_shortfall_absorb,
        )
        if not absorbed:
            _clean_content_plan_outputs(ctx)
            return issues
    if not items:
        _clean_content_plan_outputs(ctx)
        return [data_issue(
            DataIssueCode.SOURCE_RETAINED_SHORTFALL,
            stage=DataIssueStage.CONTENT_PLAN,
            ref=ctx.execution_id,
            recovery=DataRecoveryAction.REPLACE_SOURCE,
            message="auto content_plan produced no items",
        )]
    write_content_plan_packet(ctx.execution_id, items=items, source_site=existing_source_site)
    return data_issues(
        DataIssueCode.CONTRACT_INVALID,
        stage=DataIssueStage.CONTENT_PLAN,
        messages=validate_content_plan(ctx.execution_id, active_spec),
        recovery=DataRecoveryAction.REWIND_COMPOSE,
    )
