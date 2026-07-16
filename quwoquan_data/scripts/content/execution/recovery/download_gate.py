"""Workflow service extracted from the retired monolithic runner."""
from __future__ import annotations
from content.execution.coverage import coverage_entity_type, coverage_entity_type_for_entity
from content.execution.support import Any, DOWNLOAD_FETCH_ONLY_RETRY_LIMIT, DataIssue, DataIssueCode, DataIssueLane, DataIssueStage, DataRecoveryAction, ExecutionContext, Iterable, Mapping, Path, _active_spec, _planned_pixel_issue, data_issue, execution_command_root, execution_root, hashlib, image_count_is_hard_quota, image_strategy_allows_ai_generated, image_strategy_requires_publishable_images, json, minimum_publishable_images_per_target, read_json, source_plan_rule_signature
from core.data_issue import issue_messages

_MAX_IMAGES_PER_SOURCE_COLLECTION = 20


def _research_lane_issue(
    *,
    code: DataIssueCode,
    stage: DataIssueStage,
    entity_id: str,
    lane: DataIssueLane,
    message: str,
    recovery: DataRecoveryAction = DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
) -> DataIssue:
    return data_issue(
        code,
        stage=stage,
        ref=entity_id,
        lane=lane,
        recovery=recovery,
        message=message,
    )

def _download_research_lane_issues(
    ctx: ExecutionContext,
    eid: str,
    etype: str,
    lane: str,
) -> list[DataIssue]:
    """Validate one separated-current research lane for targeted managed repair."""
    from content.execution.agent.auto_research import _download_auto_research_lanes
    etype = coverage_entity_type_for_entity(ctx.spec, eid) or etype
    active_lanes = _download_auto_research_lanes(ctx)
    if active_lanes is not None and lane not in active_lanes:
        return []
    from content.source.gate import download_requirements
    from content.source.source_inputs import (
        curated_images_for_entity,
        curated_sources_for_entity,
        source_plan_rights_issues,
    )
    from core.image_rules import relevance_issue
    from core.source_catalog import platform_category
    from governance.coverage.license import validate_image_rights
    requirements = download_requirements(ctx.execution_id)
    try:
        issue_lane = DataIssueLane(lane)
    except ValueError:
        return [
            _research_lane_issue(
                code=DataIssueCode.CONTRACT_INVALID,
                stage=DataIssueStage.SOURCE_GATE,
                entity_id=eid,
                lane=DataIssueLane.ALL,
                recovery=DataRecoveryAction.STOP,
                message=f"unknown research lane: {lane}",
            )
        ]
    issues: list[DataIssue] = []

    def add(
        code: DataIssueCode,
        message: str,
        *,
        stage: DataIssueStage = DataIssueStage.SOURCE_GATE,
        recovery: DataRecoveryAction = DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
    ) -> None:
        issues.append(
            _research_lane_issue(
                code=code,
                stage=stage,
                entity_id=eid,
                lane=issue_lane,
                recovery=recovery,
                message=message,
            )
        )
    if lane == "homepage":
        sources = curated_sources_for_entity(
            ctx.execution_id, eid, etype, research_lane="homepage"
        )
        images = [
            image for image in curated_images_for_entity(ctx.execution_id, eid, etype)
            if str(image.get("researchLane") or "") == "homepage"
        ]
        min_homepage_sources = max(1, int(requirements.get("minHomepageSources") or 0))
        if len(sources) < min_homepage_sources:
            add(
                DataIssueCode.SOURCE_RETAINED_SHORTFALL,
                f"homepage sources={len(sources)} need>={min_homepage_sources}",
            )
        from core.content_source_registry import homepage_source_can_seed_base_draft
        if not any(homepage_source_can_seed_base_draft(source) for source in sources):
            add(
                DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING,
                "homepage research needs primary authority encyclopedia evidence",
            )
        for source in sources:
            category = str(source.get("category") or "") or platform_category(str(source.get("platform") or ""))
            if category in {"travelogue", "guidebook", "review"}:
                add(
                    DataIssueCode.SOURCE_CATEGORY_SHORTFALL,
                    f"homepage source {source.get('source_id')}: "
                    f"entity homepage cannot use author/guide/review source category {category}"
                )
        for issue in source_plan_rights_issues(
                ctx.execution_id,
                eid,
                etype,
                require_explicit=True,
                research_lane="homepage",
        ):
            add(
                DataIssueCode.MEDIA_RIGHTS_UNAVAILABLE,
                f"homepage: {issue}",
                stage=DataIssueStage.IMAGE_RIGHTS,
                recovery=DataRecoveryAction.REPLACE_MEDIA,
            )
        for index, image in enumerate(images, start=1):
            for issue in validate_image_rights(
                    image, vertical=str(ctx.spec.get("vertical") or "travel")
            ):
                add(
                    DataIssueCode.MEDIA_RIGHTS_UNAVAILABLE,
                    f"homepage image[{index}]: {issue}",
                    stage=DataIssueStage.IMAGE_RIGHTS,
                    recovery=DataRecoveryAction.REPLACE_MEDIA,
                )
            relevance = str(image.get("relevance") or image.get("caption") or "")
            rel_issue = relevance_issue(
                relevance,
                entity_id=eid,
                asset_id=f"{eid}#homepage#{index}",
            )
            if rel_issue:
                add(
                    DataIssueCode.SOURCE_ENTITY_MISMATCH,
                    f"homepage image[{index}]: {rel_issue}",
                    stage=DataIssueStage.IMAGE_RIGHTS,
                    recovery=DataRecoveryAction.REPLACE_MEDIA,
                )
            px_issue = _planned_pixel_issue(image, asset_id=f"{eid}#homepage#{index}")
            if px_issue:
                add(
                    DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
                    f"homepage image[{index}]: {px_issue}",
                    stage=DataIssueStage.IMAGE_RIGHTS,
                    recovery=DataRecoveryAction.REPLACE_MEDIA,
                )
        return issues
    if lane == "article":
        sources = curated_sources_for_entity(
            ctx.execution_id, eid, etype, research_lane="article"
        )
        min_article_sources = int(requirements.get("minArticleBaseSources") or requirements["minSources"])
        if len(sources) < min_article_sources:
            add(
                DataIssueCode.SOURCE_RETAINED_SHORTFALL,
                f"article sources={len(sources)} need>={min_article_sources}",
            )
        quotas = ((ctx.spec.get("content") or {}).get("quotas") or {})
        required_article_base_sources = min_article_sources if int(quotas.get("entityArticlesPerTarget") or 0) else 0
        article_base_sources = [
            source for source in sources
            if str(source.get("sourceRole") or "") == "base"
        ]
        if (
            required_article_base_sources
            and len(article_base_sources) < required_article_base_sources
        ):
            add(
                DataIssueCode.SOURCE_RETAINED_SHORTFALL,
                f"article research needs >= {required_article_base_sources} "
                "text-qualified base sources"
            )
        for source in sources:
            gate = source.get("candidateGate") if isinstance(source.get("candidateGate"), dict) else {}
            if gate and not gate.get("passed"):
                add(
                    DataIssueCode.SOURCE_PLAN_INVALID,
                    f"article source {source.get('source_id')}: candidate gate failed "
                    f"{gate.get('issues') or []}"
                )
            if str(source.get("entityMatch") or "") == "weak":
                add(
                    DataIssueCode.SOURCE_ENTITY_MISMATCH,
                    f"article source {source.get('source_id')}: weak entity match",
                )
            source_category = str(source.get("category") or "") or platform_category(str(source.get("platform") or ""))
            if str(source.get("sourceRole") or "") == "base":
                from core.qunar_template import QUNAR_PAGE_SEARCH_RESULT, qunar_page_type
                if qunar_page_type(str(source.get("url") or "")) == QUNAR_PAGE_SEARCH_RESULT:
                    add(
                        DataIssueCode.SOURCE_PAGE_TYPE_INVALID,
                        f"article source {source.get('source_id')}: "
                        "Qunar search result directory cannot be article base"
                    )
                if source_category not in {
                    "travelogue",
                    "guidebook",
                    "travel_guide",
                    "wikivoyage",
                    "official_article",
                    "vertical_professional",
                    "ugc_longform",
                    "community_post",
                    "media_article",
                    "platform_article",
                    "forum_thread",
                    "review_note",
                }:
                    add(
                        DataIssueCode.SOURCE_CATEGORY_SHORTFALL,
                        f"article source {source.get('source_id')}: base source category "
                        f"must be article-quality, got {source_category or 'unknown'}"
                    )
            for img_index, image in enumerate(source.get("imageUrls") or [], start=1):
                for issue in validate_image_rights(
                        image, vertical=str(ctx.spec.get("vertical") or "travel")
                ):
                    add(
                        DataIssueCode.MEDIA_RIGHTS_UNAVAILABLE,
                        f"article source {source.get('source_id')} image[{img_index}]: {issue}",
                        stage=DataIssueStage.IMAGE_RIGHTS,
                        recovery=DataRecoveryAction.REPLACE_MEDIA,
                    )
                relevance = str(image.get("relevance") or image.get("caption") or "")
                rel_issue = relevance_issue(
                    relevance,
                    entity_id=eid,
                    asset_id=f"{eid}#{source.get('source_id')}#{img_index}",
                )
                if rel_issue:
                    add(
                        DataIssueCode.SOURCE_ENTITY_MISMATCH,
                        f"article source {source.get('source_id')} image[{img_index}]: {rel_issue}"
                    )
                px_issue = _planned_pixel_issue(
                    image,
                    asset_id=f"{eid}/{source.get('source_id')}#{img_index}",
                )
                if px_issue:
                    add(
                        DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
                        f"article source {source.get('source_id')} image[{img_index}]: {px_issue}"
                    )
        for source in sources:
            for code, message in _article_source_identity_issues(
                source,
                str(source.get("category") or "")
                or platform_category(str(source.get("platform") or "")),
            ):
                add(code, message)
        homepage_urls = {
            str(source.get("url") or "")
            for source in curated_sources_for_entity(
                ctx.execution_id, eid, etype, research_lane="homepage"
            )
        }
        article_urls = {str(source.get("url") or "") for source in sources}
        duplicate_urls = homepage_urls & article_urls
        duplicate_urls.discard("")
        if duplicate_urls:
            add(
                DataIssueCode.SOURCE_PLAN_INVALID,
                "article sources must be independent from homepage lane; duplicate urls="
                + ", ".join(sorted(duplicate_urls)[:3])
            )
        for issue in source_plan_rights_issues(
                ctx.execution_id,
                eid,
                etype,
                require_explicit=True,
                research_lane="article",
        ):
            add(
                DataIssueCode.MEDIA_RIGHTS_UNAVAILABLE,
                f"article: {issue}",
                stage=DataIssueStage.IMAGE_RIGHTS,
                recovery=DataRecoveryAction.REPLACE_MEDIA,
            )
        return issues
    if lane == "image":
        images = [
            image for image in curated_images_for_entity(ctx.execution_id, eid, etype)
            if str(image.get("researchLane") or "image") == "image"
        ]
        require_publishable_images = image_strategy_requires_publishable_images(ctx.spec)
        allow_generated_images = image_strategy_allows_ai_generated(ctx.spec)
        collections: dict[str, list[dict[str, Any]]] = {}
        for image in images:
            if not require_publishable_images:
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
                add(
                    DataIssueCode.MEDIA_RIGHTS_UNAVAILABLE,
                    f"image {image.get('url') or '?'} missing collection rights {missing_fields}"
                )
            if str(image.get("generationModel") or "").strip() and not allow_generated_images:
                add(
                    DataIssueCode.MEDIA_RIGHTS_UNAVAILABLE,
                    f"image {image.get('url') or '?'} is AI-generated",
                )
        quotas = ((ctx.spec.get("content") or {}).get("quotas") or {})
        desired_image_works = int(quotas.get("imageWorksPerTarget") or 0)
        required_image_works = (
            max(1, desired_image_works)
            if image_count_is_hard_quota(ctx.spec)
            else minimum_publishable_images_per_target(ctx.spec)
        )
        work_capacity = sum(1 for rows in collections.values() if rows)
        if require_publishable_images and required_image_works and work_capacity < required_image_works:
            add(
                DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
                "image research needs enough rights-cleared source collections "
                f"for {required_image_works} image work(s)"
            )
        for collection_id, rows in sorted(collections.items()):
            creators = {
                str(row.get("creator") or row.get("credit") or "").strip()
                for row in rows
                if str(row.get("creator") or row.get("credit") or "").strip()
            }
            platforms = {
                str(row.get("platform") or "").strip()
                for row in rows
                if str(row.get("platform") or "").strip()
            }
            if len(rows) > _MAX_IMAGES_PER_SOURCE_COLLECTION:
                add(
                    DataIssueCode.CONTRACT_INVALID,
                    f"image collection {collection_id}: images={len(rows)} exceeds "
                    f"{_MAX_IMAGES_PER_SOURCE_COLLECTION}",
                    recovery=DataRecoveryAction.STOP,
                )
            if len(creators) > 1:
                add(
                    DataIssueCode.MEDIA_RIGHTS_UNAVAILABLE,
                    f"image collection {collection_id}: mixed creators are not allowed",
                )
            if len(platforms) > 1:
                add(
                    DataIssueCode.MEDIA_RIGHTS_UNAVAILABLE,
                    f"image collection {collection_id}: mixed platforms are not allowed",
                )
        for index, image in enumerate(images, start=1):
            if not require_publishable_images:
                continue
            for issue in validate_image_rights(
                    image, vertical=str(ctx.spec.get("vertical") or "travel")
            ):
                add(
                    DataIssueCode.MEDIA_RIGHTS_UNAVAILABLE,
                    f"image[{index}]: {issue}",
                    stage=DataIssueStage.IMAGE_RIGHTS,
                    recovery=DataRecoveryAction.REPLACE_MEDIA,
                )
            relevance = str(image.get("relevance") or image.get("caption") or "")
            rel_issue = relevance_issue(relevance, entity_id=eid, asset_id=f"{eid}#{index}")
            if rel_issue:
                add(
                    DataIssueCode.SOURCE_ENTITY_MISMATCH,
                    f"image[{index}]: {rel_issue}",
                    stage=DataIssueStage.IMAGE_RIGHTS,
                    recovery=DataRecoveryAction.REPLACE_MEDIA,
                )
            px_issue = _planned_pixel_issue(image, asset_id=f"{eid}#image#{index}")
            if px_issue:
                add(
                    DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
                    f"image[{index}]: {px_issue}",
                    stage=DataIssueStage.IMAGE_RIGHTS,
                    recovery=DataRecoveryAction.REPLACE_MEDIA,
                )
        return issues
    return []

def _article_source_identity_issues(
    source: dict[str, Any],
    category: str | None,
) -> list[tuple[DataIssueCode, str]]:
    source_id = str(source.get("source_id") or "").strip().lower()
    platform = str(source.get("platform") or "").strip()
    issues: list[tuple[DataIssueCode, str]] = []
    if "official" in source_id and category not in {"official", "official_article"}:
        issues.append(
            (
                DataIssueCode.SOURCE_CATEGORY_SHORTFALL,
                f"article source {source.get('source_id')}: source_id implies official, "
                f"but platform {platform!r} maps to {category or 'unknown'}",
            )
        )
    if (
        ("wiki" in source_id or "baike" in source_id or "百科" in source_id)
        and "wikivoyage" not in source_id
        and category != "encyclopedia"
    ):
        issues.append(
            (
                DataIssueCode.SOURCE_CATEGORY_SHORTFALL,
                f"article source {source.get('source_id')}: source_id implies encyclopedia, "
                f"but platform {platform!r} maps to {category or 'unknown'}",
            )
        )
    return issues

def _download_repair_path(ctx: ExecutionContext) -> Path:
    return execution_root(ctx.execution_id) / "_shared" / "download_repair.json"

def _download_repair_active_issues(
    ctx: ExecutionContext,
    repair: dict[str, Any],
) -> list[str]:
    """Render one repair row's typed issues for prompts and operator reports.

    Whether a repair remains pending is decided by source-plan signatures and
    typed gate results. Human-readable messages are never parsed here.
    """
    entity_id = str(repair.get("entityId") or "").strip()
    if not entity_id or entity_id not in ctx.entity_ids:
        return []
    records = repair.get("issueRecords")
    if not isinstance(records, list):
        raise ValueError(f"download repair {entity_id} missing typed issueRecords")
    issues: list[DataIssue] = []
    for raw in records:
        if not isinstance(raw, Mapping):
            raise ValueError(f"download repair {entity_id} contains an invalid issue record")
        issues.append(DataIssue.from_dict(raw))
    return issue_messages(issues)

def _source_plan_revision(paths: Iterable[Path]) -> str:
    rows: list[dict[str, str]] = []
    for path in paths:
        if not path.is_file():
            continue
        rows.append(
            {
                "name": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    if not rows:
        return ""
    encoded = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()

def _download_repair_entry_pending(repair: dict[str, Any]) -> bool:
    if not _download_repair_entry_actionable(repair):
        return False
    if _download_repair_fetch_only_retryable(repair):
        return False
    plan_paths = [
        Path(str(path))
        for path in (repair.get("sourcePlanPaths") or [])
        if str(path).strip()
    ]
    if not plan_paths and str(repair.get("sourcePlanPath") or "").strip():
        plan_paths = [Path(str(repair.get("sourcePlanPath")))]
    failed_revision = str(repair.get("sourcePlanRevision") or "")
    current_revision = _source_plan_revision(plan_paths)
    return bool(failed_revision and current_revision == failed_revision)

def _download_repair_entry_actionable(repair: dict[str, Any]) -> bool:
    records = repair.get("issueRecords")
    if isinstance(records, list) and any(isinstance(item, Mapping) for item in records):
        return True
    return any(isinstance(hint, dict) for hint in (repair.get("imageRepairHints") or []))

def _download_repair_fetch_only_retryable(repair: dict[str, Any]) -> bool:
    """Fetch-only image repair gets one deterministic retry before Agent work.
    A source plan with enough rights-cleared image candidates should not be
    sent back to Cursor agents just because the previous network budget was too
    tight or a CDN was transiently unavailable. Repeated failures of the same
    plan still escalate to source-plan repair.
    """
    if DOWNLOAD_FETCH_ONLY_RETRY_LIMIT <= 0:
        return False
    try:
        retry_count = int(repair.get("fetchRetryCount") or 0)
    except (TypeError, ValueError):
        retry_count = 0
    if retry_count >= DOWNLOAD_FETCH_ONLY_RETRY_LIMIT:
        return False
    records = repair.get("issueRecords")
    typed_issues: list[DataIssue] = []
    for raw in records if isinstance(records, list) else []:
        if not isinstance(raw, Mapping):
            continue
        try:
            typed_issues.append(DataIssue.from_dict(raw))
        except (TypeError, ValueError):
            return False
    if not typed_issues or not any(
        issue.code in {
            DataIssueCode.MEDIA_FETCH_FAILED,
            DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
            DataIssueCode.MEDIA_DOWNLOAD_INCOMPLETE,
        }
        for issue in typed_issues
    ):
        return False
    if any(issue.code is DataIssueCode.MEDIA_RIGHTS_UNAVAILABLE for issue in typed_issues):
        return False
    diagnostics = repair.get("downloadDiagnostics") or {}
    if not isinstance(diagnostics, dict):
        return False
    rejected_by = diagnostics.get("rejectedByCategory") if isinstance(diagnostics, dict) else {}
    rejected_by = rejected_by if isinstance(rejected_by, dict) else {}
    if int(rejected_by.get("rights") or 0) or int(rejected_by.get("safety_or_watermark") or 0):
        return False
    fetch_rejects = int(rejected_by.get("fetch_or_non_image") or 0)
    planned = int(diagnostics.get("plannedImages") or 0)
    return fetch_rejects > 0 and planned > 0

def _source_plan_signature_state(
    ctx: ExecutionContext,
    *,
    entity_id: str,
    paths: list[Path],
) -> str:
    """Return current/stale/missing_signature for lane source-plan rules."""
    expected = source_plan_rule_signature(str(ctx.spec.get("vertical") or "travel"), entity_id)
    saw_signature = False
    for path in paths:
        if not path.is_file():
            continue
        try:
            plan = read_json(path)
        except Exception:  # noqa: BLE001
            return "missing_signature"
        signature = plan.get("sourceRuleSignature")
        if not isinstance(signature, Mapping):
            return "missing_signature"
        saw_signature = True
        if str(signature.get("hash") or "") != str(expected.get("hash") or ""):
            return "stale"
    return "current" if saw_signature else "missing_signature"

def _source_plan_lane_paths(
    ctx: ExecutionContext,
    entity_id: str,
    etype: str,
) -> list[Path]:
    from content.source.source_unit import resolve_entity_object_dir
    plan_dir = resolve_entity_object_dir(
        ctx.execution_id,
        entity_id,
        etype_hint=etype,
    ) / "1.download"
    active_spec = _active_spec(ctx)
    quotas = ((active_spec.get("content") or {}).get("quotas") or {})
    enabled_lanes: set[str] = set()
    if int(quotas.get("entityHomepagesPerTarget") or 0) > 0:
        enabled_lanes.add("homepage")
    if (
        int(quotas.get("entityArticlesPerTarget") or 0) > 0
        or int(quotas.get("routeArticles") or 0) > 0
    ):
        enabled_lanes.add("article")
    if int(quotas.get("imageWorksPerTarget") or 0) > 0:
        enabled_lanes.add("image")
    if not enabled_lanes:
        enabled_lanes = {"homepage", "article", "image"}
    lane_paths = [
        plan_dir / f"{lane}_source_plan.json"
        for lane in ("homepage", "article", "image")
        if lane in enabled_lanes
    ]
    existing_lane_paths = [path for path in lane_paths if path.is_file()]
    return existing_lane_paths

def _stale_source_plan_entities(
    ctx: ExecutionContext,
    *,
    entity_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return entities whose generated source plans predate source/rights rules."""
    batch_etype = coverage_entity_type(ctx.spec)
    scoped_ids = entity_ids if entity_ids is not None else ctx.entity_ids
    stale: list[dict[str, Any]] = []
    for entity_id in scoped_ids:
        etype = coverage_entity_type_for_entity(ctx.spec, entity_id) or batch_etype
        paths = _source_plan_lane_paths(ctx, entity_id, etype)
        if not paths:
            continue
        signature_state = _source_plan_signature_state(ctx, entity_id=entity_id, paths=paths)
        if signature_state == "current":
            continue
        stale.append(
            {
                "entityId": entity_id,
                "sourcePlanRuleState": (
                    "signature_stale"
                    if signature_state == "stale"
                    else "signature_missing"
                ),
            }
        )
    return stale

def _download_retry_entity_ids(ctx: ExecutionContext) -> list[str]:
    """Return failed entities for an object-scoped download repair.
    The repair packet is retained until the next successful fetch. For an
    interrupted older run, derive scope from the current persisted final gate;
    stale per-stage red reports must never widen the repair.
    """
    selected: set[str] = set()
    repair_path = _download_repair_path(ctx)
    if not repair_path.is_file():
        return []
    from content.source.gate import gate_download
    current_issues = gate_download(ctx.execution_id, target_entities=set(ctx.entity_ids))
    if not current_issues:
        repair_path.unlink()
        return []
    current_scope = {
        entity_id
        for entity_id in ctx.entity_ids
        if any(issue.ref == entity_id for issue in current_issues)
    }
    if current_scope:
        return [entity_id for entity_id in ctx.entity_ids if entity_id in current_scope]
    try:
        repair = read_json(repair_path)
    except (OSError, ValueError, TypeError):
        repair = {}
    selected.update(
        str(entity.get("entityId") or "")
        for entity in repair.get("entities") or []
        if isinstance(entity, dict) and _download_repair_entry_actionable(entity)
    )
    return [entity_id for entity_id in ctx.entity_ids if entity_id in selected]

def _download_retry_lane(
    ctx: ExecutionContext,
    entity_ids: list[str],
) -> str:
    """Return a safe lane scope for deterministic download retry.
    Narrow the expensive fetch/prune cycle only when every pending repair in
    this retry batch points at the same concrete lane. Mixed or unknown repair
    remains full-lane so the workflow cannot accidentally skip required
    evidence.
    """
    from content.execution.recovery.download_unresolved import _pending_download_repair_unresolved
    unresolved = _pending_download_repair_unresolved(ctx)
    lanes: set[str] = set()
    for entity_id in entity_ids:
        lanes.update(
            lane
            for lane in (unresolved.get(entity_id) or {})
            if lane in {"homepage", "article", "image"}
        )
    return next(iter(lanes)) if len(lanes) == 1 else "all"

def _build_prepare_homepage_retry_entity_ids(ctx: ExecutionContext) -> list[str]:
    from content.execution.recovery.download_unresolved import _build_prepare_homepage_unresolved_entities
    unresolved = _build_prepare_homepage_unresolved_entities(ctx)
    if not unresolved:
        return []
    return [entity_id for entity_id in ctx.entity_ids if entity_id in unresolved]

def _workflow_repair_report_issues(ctx: ExecutionContext, stage: str) -> list[DataIssue]:
    from content.execution.stage_reports import stage_result_path
    try:
        path = stage_result_path(
            ctx.execution_id,
            "execution",
            "repair_report",
            stage,
        )
        if not path.is_file():
            return []
        envelope = read_json(path)
    except (KeyError, OSError, ValueError, TypeError):
        return []
    payload = envelope.get("payload") if isinstance(envelope, Mapping) else {}
    if not isinstance(payload, Mapping):
        return []
    return [
        DataIssue.from_dict(issue)
        for issue in (payload.get("issues") or [])
        if isinstance(issue, Mapping)
    ]

def _download_stage_gate_issues(
    ctx: ExecutionContext,
    *,
    entity_ids: Iterable[str] | None = None,
) -> list[DataIssue]:
    result_root = execution_command_root(ctx.execution_id, "source") / "results"
    scoped_entities = {str(entity_id) for entity_id in (entity_ids or []) if str(entity_id).strip()}
    issues: list[DataIssue] = []
    for step in (
        "source_plan_gate",
        "image_rights_gate",
        "image_fetch_gate",
        "source_screen_gate",
        "entity_source_bundle_gate",
    ):
        step_dir = result_root / step
        if not step_dir.is_dir():
            continue
        for path in sorted(step_dir.glob("*.json")):
            try:
                data = read_json(path)
            except (OSError, ValueError, TypeError):
                continue
            payload = data.get("payload") if isinstance(data.get("payload"), dict) else data
            if not isinstance(payload, dict) or payload.get("passed") is not False:
                continue
            evidence = payload.get("evidenceSummary") if isinstance(payload.get("evidenceSummary"), dict) else {}
            entity_ref = (
                str(evidence.get("entityId") or "")
                if step == "source_screen_gate"
                else str(payload.get("ref") or path.stem)
            )
            if scoped_entities and entity_ref not in scoped_entities:
                continue
            ref = str(payload.get("ref") or path.stem)
            raw_issues = payload.get("issues") if isinstance(payload.get("issues"), list) else []
            if raw_issues:
                for raw_issue in raw_issues:
                    if not isinstance(raw_issue, Mapping):
                        raise ValueError(
                            f"retired untyped download gate report: {path}; rerun download to regenerate"
                        )
                    issues.append(DataIssue.from_dict(raw_issue))
            else:
                issues.append(data_issue(
                    DataIssueCode.CONTRACT_INVALID,
                    stage={
                        "image_rights_gate": DataIssueStage.IMAGE_RIGHTS,
                        "image_fetch_gate": DataIssueStage.IMAGE_FETCH,
                        "source_screen_gate": DataIssueStage.SOURCE_SCREEN,
                        "entity_source_bundle_gate": DataIssueStage.ENTITY_SOURCE_BUNDLE,
                    }[step],
                    ref=ref,
                    message=f"{step} failed without issue detail",
                ))
    return issues
