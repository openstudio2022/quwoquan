"""Execution service extracted from the retired monolithic runner."""
from __future__ import annotations
from content.execution.coverage import coverage_entity_type, coverage_entity_type_for_entity
from content.execution.support import Any, DOWNLOAD_FETCH_ONLY_RETRY_LIMIT, DataIssue, DataIssueCode, DataIssueLane, DataIssueStage, DataRecoveryAction, ExecutionContext, Iterable, Mapping, Path, _active_spec, _planned_pixel_issue, data_issue, execution_command_root, execution_root, hashlib, image_count_is_hard_quota, image_strategy_allows_ai_generated, image_strategy_requires_publishable_images, json, minimum_publishable_images_per_target, read_json, source_plan_rule_signature
from core.data_issue import issue_messages

_MAX_IMAGES_PER_SOURCE_COLLECTION = 20


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
    if lane not in active_lanes:
        return []
    from content.source.gate import download_requirements
    from content.source.source_inputs import (
        curated_images_for_entity,
        curated_sourced_videos_for_entity,
        curated_sources_for_entity,
    )
    from core.image_rules import relevance_issue
    from core.source_catalog import platform_category
    from governance.coverage.license import rights_proof_required, validate_image_rights
    requirements = download_requirements(ctx.execution_id)
    enforce_rights = rights_proof_required(ctx.spec.vertical)
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
        min_homepage_sources = requirements.min_homepage_sources
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
        if len(images) < requirements.min_homepage_media:
            add(
                DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
                "homepage research needs enough rights-cleared media "
                f"({len(images)}<{requirements.min_homepage_media})",
                stage=DataIssueStage.IMAGE_RIGHTS,
                recovery=DataRecoveryAction.REPLACE_MEDIA,
            )
        for source in sources:
            category = str(source.get("category") or "") or platform_category(str(source.get("platform") or ""))
            if category in {"travelogue", "guidebook", "review"}:
                add(
                    DataIssueCode.SOURCE_CATEGORY_SHORTFALL,
                    f"homepage source {source.get('source_id')}: "
                    f"entity homepage cannot use author/guide/review source category {category}"
                )
        if enforce_rights and requirements.min_homepage_media > 0:
            for image in images:
                for issue in validate_image_rights(
                    image,
                    vertical=ctx.spec.vertical,
                ):
                    add(
                        DataIssueCode.MEDIA_RIGHTS_UNAVAILABLE,
                        f"homepage image {image.get('url') or '?'}: {issue}",
                        stage=DataIssueStage.IMAGE_RIGHTS,
                        recovery=DataRecoveryAction.REPLACE_MEDIA,
                    )
        # Page-owned media is enumerated here, then every candidate receives a
        # typed disposition in the download funnel. One excluded image must not
        # invalidate an otherwise readable primary encyclopedia source.
        return issues
    if lane == "article":
        sources = curated_sources_for_entity(
            ctx.execution_id, eid, etype, research_lane="article"
        )
        min_article_sources = (
            requirements.min_article_base_sources or requirements.min_sources
        )
        if len(sources) < min_article_sources:
            add(
                DataIssueCode.SOURCE_RETAINED_SHORTFALL,
                f"article sources={len(sources)} need>={min_article_sources}",
            )
        quotas = ctx.spec.content.quotas
        required_article_base_sources = min_article_sources if quotas.entity_articles_per_target else 0
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
        return issues
    if lane == "image":
        images = [
            image for image in curated_images_for_entity(ctx.execution_id, eid, etype)
            if str(image.get("researchLane") or "image") == "image"
        ]
        require_publishable_images = image_strategy_requires_publishable_images(ctx.spec.to_dict())
        allow_generated_images = image_strategy_allows_ai_generated(ctx.spec.to_dict())
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
                )
                if not str(image.get(field) or "").strip()
            ]
            if missing_fields:
                add(
                    DataIssueCode.MEDIA_RIGHTS_UNAVAILABLE,
                    f"image {image.get('url') or '?'} missing collection rights {missing_fields}"
                )
            if enforce_rights:
                for issue in validate_image_rights(
                    image,
                    vertical=ctx.spec.vertical,
                ):
                    add(
                        DataIssueCode.MEDIA_RIGHTS_UNAVAILABLE,
                        f"image {image.get('url') or '?'}: {issue}",
                    )
            if str(image.get("generationModel") or "").strip() and not allow_generated_images:
                add(
                    DataIssueCode.MEDIA_RIGHTS_UNAVAILABLE,
                    f"image {image.get('url') or '?'} is AI-generated",
                )
        quotas = ctx.spec.content.quotas
        desired_image_works = quotas.image_works_per_target
        required_image_works = (
            max(1, desired_image_works)
            if image_count_is_hard_quota(ctx.spec.to_dict())
            else minimum_publishable_images_per_target(ctx.spec.to_dict())
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
    if lane == "video":
        videos = curated_sourced_videos_for_entity(
            ctx.execution_id,
            eid,
            etype,
        )
        frames = [
            image
            for image in curated_images_for_entity(ctx.execution_id, eid, etype)
            if str(image.get("researchLane") or "") == "video"
        ]
        if not videos and len(frames) < requirements.min_video_frames:
            add(
                DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
                "video research needs an admitted direct-video candidate or "
                f"{requirements.min_video_frames} rights-cleared frame(s) "
                f"({len(frames)} retained)",
                stage=DataIssueStage.IMAGE_RIGHTS,
                recovery=DataRecoveryAction.REPLACE_MEDIA,
            )
        for index, frame in enumerate(frames, start=1):
            if enforce_rights:
                for issue in validate_image_rights(
                    frame,
                    vertical=ctx.spec.vertical,
                ):
                    add(
                        DataIssueCode.MEDIA_RIGHTS_UNAVAILABLE,
                        f"video frame[{index}] {frame.get('url') or '?'}: {issue}",
                        stage=DataIssueStage.IMAGE_RIGHTS,
                        recovery=DataRecoveryAction.REPLACE_MEDIA,
                    )
            relevance = str(frame.get("relevance") or frame.get("caption") or "")
            rel_issue = relevance_issue(
                relevance,
                entity_id=eid,
                asset_id=f"{eid}#video#{index}",
            )
            if rel_issue:
                add(
                    DataIssueCode.SOURCE_ENTITY_MISMATCH,
                    f"video frame[{index}]: {rel_issue}",
                    stage=DataIssueStage.IMAGE_RIGHTS,
                    recovery=DataRecoveryAction.REPLACE_MEDIA,
                )
            px_issue = _planned_pixel_issue(
                frame,
                asset_id=f"{eid}#video#{index}",
            )
            if px_issue:
                add(
                    DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
                    f"video frame[{index}]: {px_issue}",
                    stage=DataIssueStage.IMAGE_RIGHTS,
                    recovery=DataRecoveryAction.REPLACE_MEDIA,
                )
        return issues
    return []
