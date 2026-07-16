"""Workflow service extracted from the retired monolithic runner."""
from __future__ import annotations
from core.control_types import ExecutionStage
from content.execution.coverage import coverage_entity_type, coverage_entity_type_for_entity
from content.execution.support import Any, DataIssue, DataIssueCode, DataIssueLane, DataIssueStage, DataRecoveryAction, ExecutionContext, MANAGED_LOCAL_CURSOR_MAX_WORKERS, Mapping, Sequence, _context_managed_local_cursor_worker_cap, _normalize_managed_agent_provider, _planned_pixel_issue, data_issue, execution_root, image_count_is_hard_quota, image_strategy_allows_ai_generated, image_strategy_requires_publishable_images, issue_messages, load_workflow_state, minimum_publishable_images_per_target, read_json, save_workflow_state, store

def _managed_local_cursor_worker_cap(ctx: ExecutionContext) -> int:
    return _context_managed_local_cursor_worker_cap(
        ctx,
        local_cursor_max_workers=MANAGED_LOCAL_CURSOR_MAX_WORKERS,
    )

def _managed_uses_serial_local_cursor(ctx: ExecutionContext) -> bool:
    return (
        _normalize_managed_agent_provider(ctx.agent_provider) == "cursor_sdk"
        and str(ctx.runtime) == "local"
        and _managed_local_cursor_worker_cap(ctx) == 1
    )

def reset_stage_retries(
    execution_id: str,
    *,
    stage: str,
    reason: str,
    reset_react_rewinds: bool = False,
) -> dict[str, Any]:
    """Clear retry ledgers for an audited operator-confirmed recovery."""
    from content.execution.pipeline.dag import STAGE_NAMES
    from content.execution.pipeline.pipeline_control import _rewind_to
    from content.execution.recovery.post_recovery import _invalidate_ref_for_retry, _purge_author_queue_for_stale_workflow
    stage_name = str(stage or "").strip()
    if stage_name not in STAGE_NAMES:
        raise ValueError(f"unknown workflow stage: {stage_name}")
    state = load_workflow_state(execution_id)
    retry_counts = dict(state.get("retryCounts") or {})
    infra_counts = dict(state.get("infrastructureRetryCounts") or {})
    react_rewinds = dict(state.get("reactRewinds") or {})
    completed_before = set(state.get("completed") or [])
    tail_stages = set(STAGE_NAMES[STAGE_NAMES.index(stage_name):])
    was_waiting_for_stage = str(state.get("waitingCheckpoint") or "") == stage_name
    previous = {
        "retryCount": retry_counts.pop(stage_name, None),
        "infrastructureRetryCount": infra_counts.pop(stage_name, None),
        "reactRewindCount": react_rewinds.get(stage_name),
        "completed": sorted(completed_before),
        "status": state.get("status"),
        "failedObjects": list(state.get("failedObjects") or []),
        "activeAutoResearch": dict(state.get("activeAutoResearch") or {})
        if isinstance(state.get("activeAutoResearch"), Mapping)
        else None,
    }
    for name in list(retry_counts):
        if name in tail_stages:
            retry_counts.pop(name, None)
    for name in list(infra_counts):
        if name in tail_stages:
            infra_counts.pop(name, None)
    state["retryCounts"] = retry_counts
    state["infrastructureRetryCounts"] = infra_counts
    recovered_at = store.now_iso()
    recovery_cutoffs = dict(state.get("managedInfraRecoveryCutoffs") or {})
    for name in tail_stages:
        recovery_cutoffs[name] = recovered_at
    state["managedInfraRecoveryCutoffs"] = recovery_cutoffs
    reset_react_keys: list[str] = []
    if reset_react_rewinds:
        for name in list(react_rewinds):
            if name in tail_stages:
                react_rewinds.pop(name, None)
                reset_react_keys.append(name)
    # retry-stage is primarily an infrastructure recovery tool.  ReAct rewind
    # counters survive by default; a quality-contract code repair must opt in to
    # clearing them so the recovery record stays auditable.
    state["reactRewinds"] = react_rewinds
    rewound_completed = _rewind_to(completed_before, stage_name)
    state["completed"] = [name for name in STAGE_NAMES if name in rewound_completed]
    invalidated_content_refs: list[str] = []
    if stage_name in {"download_plan", "download_fetch", "build_prepare", "build_homepage", "build_validate", "content_plan", "post_plan", "post_compose"}:
        try:
            from content.post import object_index as content_object
            ctx = ExecutionContext(
                execution_id=execution_id,
                entity_ids=[],
                spec=store.load_spec(execution_id),
            )
            candidate_refs = content_object.iter_content_refs(execution_id)
            _purge_author_queue_for_stale_workflow(ctx, refs=candidate_refs, reason=f"retry-stage->{stage_name}")
            invalidated_content_refs = [
                ref for ref in candidate_refs
                if _invalidate_ref_for_retry(ctx, ref)
            ]
        except Exception as exc:  # noqa: BLE001
            state["failedObjects"] = [f"{stage_name}: retry invalidation failed: {exc}"]
            state["status"] = "manual_required"
            state["nextAction"] = f"retry {stage_name}: content invalidation failed"
            save_workflow_state(state)
            raise
    state["waitingCheckpoint"] = None
    state["failedObjects"] = []
    active_auto = state.get("activeAutoResearch")
    if isinstance(active_auto, Mapping):
        active_stage = str(active_auto.get("stage") or "").strip()
        active_status = str(active_auto.get("status") or "").strip()
        if (
            active_stage in STAGE_NAMES
            and STAGE_NAMES.index(active_stage) <= STAGE_NAMES.index(stage_name)
            and active_status in {"interrupted", "succeeded"}
        ):
            state.pop("activeAutoResearch", None)
    if was_waiting_for_stage:
        state["status"] = "waiting_agent"
        state["waitingCheckpoint"] = stage_name
        state["nextAction"] = f"retry {stage_name}: {reason or 'operator requested retry'}"
    else:
        state["status"] = "repairing"
        state["nextAction"] = f"rewind to {stage_name}: {reason or 'operator requested retry'}"
    recoveries = list(state.get("recoveryActions") or [])
    recoveries.append(
        {
            "stage": stage_name,
            "reason": str(reason or "operator requested retry"),
            "previous": previous,
            "invalidatedContentRefs": sorted(invalidated_content_refs),
            "resetReactRewinds": sorted(reset_react_keys),
            "recoveredAt": recovered_at,
        }
    )
    state["recoveryActions"] = recoveries
    save_workflow_state(state)
    return {
        "stage": stage_name,
        "previous": previous,
        "invalidatedContentRefs": sorted(invalidated_content_refs),
        "resetReactRewinds": sorted(reset_react_keys),
        "retryCounts": state.get("retryCounts") or {},
        "infrastructureRetryCounts": state.get("infrastructureRetryCounts") or {},
        "reactRewinds": state.get("reactRewinds") or {},
        "completed": state.get("completed") or [],
        "status": state.get("status"),
        "nextAction": state.get("nextAction"),
    }

def _compose_brief_gate_failures(
    ctx: ExecutionContext,
    refs: Sequence[str],
) -> tuple[list[DataIssue], ExecutionStage | None]:
    from content.post.object_index import content_object_stage_dir
    from core.io import read_json
    from core.paths import STAGE_COMPOSE
    failures: list[DataIssue] = []
    fallback_stage: ExecutionStage | None = None
    for ref in refs:
        try:
            gate_path = content_object_stage_dir(ctx.execution_id, ref, STAGE_COMPOSE) / "compose_brief_gate.json"
        except KeyError:
            failures.append(data_issue(
                DataIssueCode.CONTRACT_INVALID,
                stage=DataIssueStage.COMPOSE_BRIEF,
                ref=ref,
                recovery=DataRecoveryAction.REWIND_COMPOSE,
                message="compose object route missing",
            ))
            fallback_stage = fallback_stage or ExecutionStage.POST_COMPOSE
            continue
        if not gate_path.is_file():
            failures.append(data_issue(
                DataIssueCode.CONTRACT_INVALID,
                stage=DataIssueStage.COMPOSE_BRIEF,
                ref=ref,
                recovery=DataRecoveryAction.REWIND_COMPOSE,
                message="missing compose_brief_gate.json",
            ))
            fallback_stage = fallback_stage or ExecutionStage.POST_COMPOSE
            continue
        try:
            envelope = read_json(gate_path)
        except (OSError, ValueError, TypeError):
            failures.append(data_issue(
                DataIssueCode.CONTRACT_INVALID,
                stage=DataIssueStage.COMPOSE_BRIEF,
                ref=ref,
                recovery=DataRecoveryAction.REWIND_COMPOSE,
                message="unreadable compose_brief_gate.json",
            ))
            fallback_stage = fallback_stage or ExecutionStage.POST_COMPOSE
            continue
        payload = envelope.get("payload") if isinstance(envelope.get("payload"), Mapping) else envelope
        if not isinstance(payload, Mapping) or payload.get("passed") is not False:
            continue
        issues = [
            DataIssue.from_dict(issue)
            for issue in (payload.get("issues") or [])
            if isinstance(issue, Mapping)
        ]
        if issues:
            failures.extend(issues)
        else:
            failures.append(data_issue(
                DataIssueCode.QUALITY_FAILED,
                stage=DataIssueStage.COMPOSE_BRIEF,
                ref=ref,
                recovery=DataRecoveryAction.REWIND_COMPOSE,
                message="compose_brief gate failed",
            ))
        if any(issue.recovery is DataRecoveryAction.REWIND_DOWNLOAD for issue in issues):
            fallback_stage = ExecutionStage.DOWNLOAD_PLAN
        elif fallback_stage is None:
            fallback_stage = ExecutionStage.POST_COMPOSE
    return failures, fallback_stage

def _clear_manual_repair_rewind_if_resuming(execution_id: str) -> None:
    """Allow a manually repaired failed stage to be re-evaluated with fresh budgets."""
    state = load_workflow_state(execution_id)
    if str(state.get("status") or "") != "manual_required":
        return
    stage = str(state.get("lastFailedStage") or state.get("waitingCheckpoint") or "").strip()
    if not stage:
        return
    rewinds = dict(state.get("reactRewinds") or {})
    retry_counts = dict(state.get("retryCounts") or {})
    if stage not in rewinds and stage not in retry_counts:
        return
    previous = int(rewinds.pop(stage, 0) or 0)
    previous_retries = int(retry_counts.pop(stage, 0) or 0)
    state["reactRewinds"] = rewinds
    state["retryCounts"] = retry_counts
    resumes = list(state.get("manualRepairResumes") or [])
    resumes.append(
        {
            "stage": stage,
            "clearedReactRewinds": previous,
            "clearedRetryCount": previous_retries,
            "resumedAt": store.now_iso(),
        }
    )
    state["manualRepairResumes"] = resumes[-20:]
    state["nextAction"] = f"manual repair resume: revalidate {stage}"
    state["heartbeatAt"] = store.now_iso()
    save_workflow_state(state)
    print(
        f"[geo-homepages] manual repair resume: cleared react rewind budget for {stage} "
        f"(reactRewinds={previous}, retries={previous_retries})",
        flush=True,
    )

def _source_plan_issue_records(
    ctx: ExecutionContext,
    *,
    include_download_repair: bool = True,
) -> list[DataIssue]:
    """Return machine-actionable readiness issues for all source-plan lanes."""
    from content.execution.agent.auto_research import _download_auto_research_lanes
    from content.execution.recovery.download_gate import _article_source_identity_issues
    from content.execution.recovery.download_unresolved import _pending_download_repair_unresolved
    from content.source.gate import download_requirements
    from content.source.source_inputs import (
        curated_images_for_entity,
        curated_sources_for_entity,
        source_plan_rights_issues,
    )
    from core.image_rules import relevance_issue
    from governance.coverage.license import validate_image_rights
    etype = coverage_entity_type(ctx.spec)
    from core.source_catalog import platform_category
    from content.source.source_unit import resolve_entity_object_dir
    requirements = download_requirements(ctx.execution_id)
    separated_research = str((ctx.spec.get("content") or {}).get("modalityContract") or "") == "separated_research"
    missing: list[DataIssue] = []
    for eid in ctx.entity_ids:
        entity_type = coverage_entity_type_for_entity(ctx.spec, eid) or etype
        obj = resolve_entity_object_dir(ctx.execution_id, eid, etype_hint=entity_type)
        lane_files = {
            lane: obj / "1.download" / f"{lane}_source_plan.json"
            for lane in ("homepage", "article", "image")
        }
        has_lane_contract = separated_research or any(path.is_file() for path in lane_files.values())
        if has_lane_contract:
            lane_issues: list[str] = []
            homepage_sources = curated_sources_for_entity(
                ctx.execution_id, eid, entity_type, research_lane="homepage"
            )
            article_sources = curated_sources_for_entity(
                ctx.execution_id, eid, entity_type, research_lane="article"
            )
            images = curated_images_for_entity(ctx.execution_id, eid, entity_type)
            work_images = [
                image for image in images
                if str(image.get("researchLane") or "image") == "image"
            ]
            quotas = ((ctx.spec.get("content") or {}).get("quotas") or {})
            active_lanes = _download_auto_research_lanes(ctx) or {"homepage", "article", "image"}
            article_quota = int(quotas.get("entityArticlesPerTarget") or 0)
            if "homepage" in active_lanes:
                min_homepage_sources = max(1, int(requirements.get("minHomepageSources") or 0))
                if len(homepage_sources) < min_homepage_sources:
                    lane_issues.append(
                        f"homepage sources={len(homepage_sources)} need>={min_homepage_sources}"
                    )
                from core.content_source_registry import homepage_source_can_seed_base_draft
                if not any(homepage_source_can_seed_base_draft(source) for source in homepage_sources):
                    lane_issues.append("homepage research needs primary authority encyclopedia evidence")
                for source in homepage_sources:
                    category = str(source.get("category") or "") or platform_category(str(source.get("platform") or ""))
                    if category in {"travelogue", "guidebook", "review"}:
                        lane_issues.append(
                            f"homepage source {source.get('source_id')}: "
                            f"entity homepage cannot use author/guide/review source category {category}"
                        )
            if "article" in active_lanes and article_quota > 0:
                min_article_sources = int(requirements.get("minArticleBaseSources") or requirements["minSources"])
                if len(article_sources) < min_article_sources:
                    lane_issues.append(
                        f"article sources={len(article_sources)} need>={min_article_sources}"
                    )
                for source in article_sources:
                    for img_index, image in enumerate(source.get("imageUrls") or [], start=1):
                        lane_issues.extend(
                            f"article source {source.get('source_id')} image[{img_index}]: {issue}"
                            for issue in validate_image_rights(
                                image, vertical=str(ctx.spec.get("vertical") or "travel")
                            )
                        )
                        relevance = str(image.get("relevance") or image.get("caption") or "")
                        rel_issue = relevance_issue(
                            relevance,
                            entity_id=eid,
                            asset_id=f"{eid}#{source.get('source_id')}#{img_index}",
                        )
                        if rel_issue:
                            lane_issues.append(
                                f"article source {source.get('source_id')} image[{img_index}]: {rel_issue}"
                            )
                        px_issue = _planned_pixel_issue(
                            image,
                            asset_id=f"{eid}/{source.get('source_id')}#{img_index}",
                        )
                        if px_issue:
                            lane_issues.append(
                                f"article source {source.get('source_id')} image[{img_index}]: {px_issue}"
                            )
                for source in article_sources:
                    lane_issues.extend(
                        _article_source_identity_issues(
                            source,
                            platform_category(str(source.get("platform") or "")),
                        )
                    )
            duplicate_urls: set[str] = set()
            if {"homepage", "article"} <= active_lanes:
                duplicate_urls = {
                    str(source.get("url") or "")
                    for source in homepage_sources
                } & {
                    str(source.get("url") or "")
                    for source in article_sources
                }
                duplicate_urls.discard("")
            collections: dict[str, list[dict[str, Any]]] = {}
            require_publishable_images = image_strategy_requires_publishable_images(ctx.spec)
            allow_generated_images = image_strategy_allows_ai_generated(ctx.spec)
            for image in work_images:
                if "image" not in active_lanes or not require_publishable_images:
                    continue
                collection_id = str(image.get("sourceCollectionId") or "").strip()
                if collection_id:
                    collections.setdefault(collection_id, []).append(image)
                missing_fields = [
                    field
                    for field in (
                        "sourceCollectionId",
                        "creator",
                        "collectionPageUrl",
                        "license",
                        "termsUrl",
                        "authorizationProof",
                    )
                    if not str(image.get(field) or "").strip()
                ]
                if missing_fields:
                    lane_issues.append(
                        f"image {image.get('url') or '?'} missing collection rights {missing_fields}"
                    )
                if str(image.get("generationModel") or "").strip() and not allow_generated_images:
                    lane_issues.append(f"image {image.get('url') or '?'} is AI-generated")
            desired_image_works = int(quotas.get("imageWorksPerTarget") or 0) if "image" in active_lanes else 0
            required_image_works = (
                max(1, desired_image_works)
                if image_count_is_hard_quota(ctx.spec)
                else minimum_publishable_images_per_target(ctx.spec)
            )
            # One source collection can form one image work. A multi-image
            # post may use 1..20 images from that collection, but the same
            # collection must not be counted as multiple works by default.
            work_capacity = sum(1 for rows in collections.values() if rows)
            if require_publishable_images and required_image_works and work_capacity < required_image_works:
                lane_issues.append(
                    "image research needs enough rights-cleared source collections "
                    f"for {required_image_works} image work(s)"
                )
            source_rights_lanes = [
                lane for lane in ("homepage", "article")
                if lane in active_lanes and (lane != "article" or article_quota > 0)
            ]
            for lane in source_rights_lanes:
                lane_issues.extend(
                    f"{lane}: {issue}"
                    for issue in source_plan_rights_issues(
                        ctx.execution_id,
                        eid,
                        entity_type,
                        require_explicit=True,
                        research_lane=lane,
                    )
                )
            for index, image in enumerate(work_images, start=1):
                if "image" not in active_lanes or not require_publishable_images:
                    continue
                lane_issues.extend(
                    f"image[{index}]: {issue}"
                    for issue in validate_image_rights(
                        image, vertical=str(ctx.spec.get("vertical") or "travel")
                    )
                )
                relevance = str(image.get("relevance") or image.get("caption") or "")
                rel_issue = relevance_issue(
                    relevance,
                    entity_id=eid,
                    asset_id=f"{eid}#{index}",
                )
                if rel_issue:
                    lane_issues.append(f"image[{index}]: {rel_issue}")
                px_issue = _planned_pixel_issue(image, asset_id=f"{eid}#image#{index}")
                if px_issue:
                    lane_issues.append(f"image[{index}]: {px_issue}")
            if lane_issues:
                missing.append(
                    data_issue(
                        DataIssueCode.SOURCE_PLAN_INVALID,
                        stage=DataIssueStage.DOWNLOAD_PLAN,
                        ref=eid,
                        lane=DataIssueLane.ALL,
                        recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
                        message="; ".join(lane_issues[:12]),
                    )
                )
            continue
        sources = curated_sources_for_entity(ctx.execution_id, eid, entity_type)
        images = curated_images_for_entity(ctx.execution_id, eid, entity_type)
        issues = source_plan_rights_issues(
            ctx.execution_id,
            eid,
            entity_type,
            require_explicit=requirements["minSources"] >= 4,
        )
        for index, image in enumerate(images, start=1):
            issues.extend(
                f"image[{index}]: {issue}"
                for issue in validate_image_rights(image, vertical=str(ctx.spec.get("vertical") or "travel"))
            )
            relevance = str(image.get("relevance") or image.get("caption") or "")
            rel_issue = relevance_issue(
                relevance,
                entity_id=eid,
                asset_id=f"{eid}#{index}",
            )
            if rel_issue:
                issues.append(f"image[{index}]: {rel_issue}")
        if len(sources) < requirements["minSources"]:
            issues.append(f"sources={len(sources)} need>={requirements['minSources']}")
        if len(images) < requirements["minImages"]:
            issues.append(f"imageUrls={len(images)} need>={requirements['minImages']}")
        if issues:
            missing.append(
                data_issue(
                    DataIssueCode.SOURCE_PLAN_INVALID,
                    stage=DataIssueStage.DOWNLOAD_PLAN,
                    ref=eid,
                    lane=DataIssueLane.ALL,
                    recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
                    message="; ".join(issues[:8]),
                )
            )
    repair_path = execution_root(ctx.execution_id) / "_shared" / "download_repair.json"
    if include_download_repair and repair_path.is_file():
        pending_unresolved = _pending_download_repair_unresolved(ctx)
        if pending_unresolved:
            pending_repairs: list[DataIssue] = []
            for eid, lanes in pending_unresolved.items():
                details = "; ".join(
                    issue
                    for lane_issues in lanes.values()
                    for issue in lane_issues[:4]
                )
                if details:
                    pending_repairs.append(
                        data_issue(
                            DataIssueCode.SOURCE_PLAN_INVALID,
                            stage=DataIssueStage.DOWNLOAD_PLAN,
                            ref=eid,
                            lane=DataIssueLane.ALL,
                            recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
                            message=details,
                        )
                    )
            if pending_repairs:
                missing.extend(pending_repairs)
    return missing


def _source_plan_filled(
    ctx: ExecutionContext,
    *,
    include_download_repair: bool = True,
) -> tuple[bool, list[str]]:
    """Render source-plan readiness for prompt and CLI presentation boundaries."""
    issues = _source_plan_issue_records(
        ctx,
        include_download_repair=include_download_repair,
    )
    return (not issues), issue_messages(issues)
