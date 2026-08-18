"""Per-entity auto research plan implementation."""
from __future__ import annotations

from typing import Any

from core.data_issue import (
    DataIssueCode,
    DataIssueError,
    DataIssueStage,
    DataRecoveryAction,
    data_issue,
)
from core.image_asset_strategy import (
    image_asset_strategy,
    image_count_is_hard_quota,
    image_count_policy,
    image_strategy_requires_publishable_images,
    minimum_publishable_images_per_target,
)
from core.paths import STAGE_DOWNLOAD
from core.source_catalog import vertical_from_task_id

from content.execution.workspace import frozen_target_by_name
from content.source.contracts import (
    HomepageAuthorityProvider,
    QualifiedHomepageSource,
)
from content.source.external_acquisition_inputs import (
    professional_image_context_binding,
)
from content.source.prepare import prepare_source_plan
from content.source.research.auto_plan_article import write_article_lane
from content.source.research.auto_plan_homepage import (
    HomepageResearchInput,
    write_homepage_lane,
)
from content.source.research.auto_plan_lanes import write_image_lane
from content.source.research.auto_plan_report import (
    _source_availability_summary,
    _write_auto_report_artifacts,
)
from content.source.research.auto_plan_video import (
    discover_commons_sourced_videos,
    write_video_lane,
)
from content.source.research.baike_com import geo_context_terms_from_ref
from content.source.research.homepage_authority import discover_homepage_authority
from content.source.research.image_provider_compliance import (
    professional_library_compliance_summary,
)
from content.source.research.plan_reuse import (
    _verified_article_sources_from_prior_plans,
)
from content.source.research.plan_state import (
    _record_unavailable,
    _task_content_quotas,
    _task_spec,
)
from content.source.research.qunar_sources import (
    _qunar_travelogue_sources,  # noqa: F401 - retained test seam
)
from content.source.research.reject_memory import (
    _download_reject_memory,
    _images_from_collections,
    _verified_image_collections_from_prior_plans,
)
from content.source.research.source_quality import _article_base_candidate_limit
from content.source.research.source_registry import (
    _known_article_sources,  # noqa: F401 - retained test seam
    _known_entity_aliases,
    _known_official_website,  # noqa: F401 - retained test seam
)
from content.source.research.text_match import (
    _entity_name_variants,
    _expanded_entity_aliases,
)
from content.source.research.wiki_core import (
    _official_website,  # noqa: F401 - retained test seam
    _trusted_external_links,
    _wiki_related_titles_for_entity,
    _wiki_title_for_entity,
    _wiki_url,
    _wikidata_entity_aliases,
    _wikidata_item_for_entity_search,
    _wikidata_item_for_zhwiki,
)
from content.source.research.wiki_media import (
    _discover_open_license_image_pools,
    _mediawiki_page_images,  # noqa: F401 - retained test seam
)
from content.source.source_unit import resolve_entity_object_dir


def _write_auto_research_plans_impl(
    execution_id: str,
    entity_ids: list[str],
    *,
    entity_type: str,
    force: bool = False,
    lanes: set[str] | None = None,
    write_shared_report: bool = True,
    external_input_context: Any | None = None,
) -> dict[str, Any]:
    vertical = vertical_from_task_id(execution_id)
    # 单值 entity_type 只作 fallback；每个实体目录类型以 task spec coverageTargets 为准。
    from content.source.prepare import resolve_research_entity_types
    resolved_types = resolve_research_entity_types(execution_id, entity_ids, fallback_type=entity_type)
    entities = [
        {"entityId": entity_id, "canonicalName": entity_id, "entityType": resolved_types[entity_id]}
        for entity_id in entity_ids
    ]
    prepare_source_plan(execution_id, entities)
    updated: list[dict[str, Any]] = []
    issues: list[str] = []
    strategy_spec = _task_spec(execution_id)
    declared_lanes = {
        str(lane).strip()
        for lane in ((strategy_spec.get("content") or {}).get("research") or {}).get("lanes") or []
        if str(lane).strip()
    }
    selected_lanes = lanes or declared_lanes
    if not selected_lanes:
        raise ValueError("execution must declare at least one research lane")
    from content.source.research.auto_plan_context import (
        article_topic_terms,
        build_external_media_plan_context,
        coverage_targets_by_name,
        frozen_scale_source_pool_report,
        initialize_auto_plan_report,
    )

    frozen_report = frozen_scale_source_pool_report(
        execution_id,
        entity_ids,
        selected_lanes=selected_lanes,
        vertical=vertical,
        write_shared_report=write_shared_report,
    )
    if frozen_report is not None:
        return frozen_report
    media_context = build_external_media_plan_context(
        strategy_spec=strategy_spec,
        selected_lanes=selected_lanes,
        external_input_context=external_input_context,
    )
    professional_image_bound = media_context.professional_image_bound
    image_work_units = media_context.image_work_units
    video_work_units = media_context.video_work_units
    exact_media_work_units = media_context.exact_media_work_units
    professional_image_index = media_context.professional_image_index
    video_receipt_refs = media_context.video_receipt_refs
    video_acquisition_root = media_context.video_acquisition_root
    professional_video_index = media_context.professional_video_index
    report = initialize_auto_plan_report(
        execution_id=execution_id,
        vertical=vertical,
        selected_lanes=selected_lanes,
    )
    report["updated"] = updated
    report["issues"] = issues
    quotas = _task_content_quotas(execution_id)
    target_by_name = coverage_targets_by_name(strategy_spec)
    image_strategy = image_asset_strategy(strategy_spec)
    image_policy = image_count_policy(strategy_spec)
    requires_publishable_images = image_strategy_requires_publishable_images(strategy_spec)
    report["imageAssetStrategy"] = image_strategy
    report["imageCountPolicy"] = image_policy
    report["imagePublishableAssetsRequired"] = requires_publishable_images
    required_article_bases = max(1, quotas["entityArticlesPerTarget"] or 1)
    desired_image_works = max(0, quotas["imageWorksPerTarget"] or 0)
    image_bonus_saturation_count = max(1, desired_image_works)
    hard_image_works = (
        image_bonus_saturation_count
        if image_count_is_hard_quota(strategy_spec)
        else minimum_publishable_images_per_target(strategy_spec)
    )
    from content.source.gate import download_requirements
    required_publishable_images = max(
        hard_image_works,
        download_requirements(execution_id).min_images,
    )
    from content.post.article.base_draft import ARTICLE_MIN_BASE_DRAFT_CHARS
    report["scoringPolicy"] = {
        "imageCountPolicy": image_policy,
        "imageBonusSaturationCount": image_bonus_saturation_count,
        "minimumPublishableImagesPerTarget": hard_image_works,
        # RC6：长文字数门唯一真相源（图文混排走 base_draft_readiness 自适应，不在此体现固定门）。
        "articleLengthPassChars": ARTICLE_MIN_BASE_DRAFT_CHARS,
    }
    for entity_id in entity_ids:
        entity_type = resolved_types[entity_id]
        obj = resolve_entity_object_dir(execution_id, entity_id, etype_hint=entity_type)
        dl = obj / STAGE_DOWNLOAD
        target_source = target_by_name.get(entity_id) or {}
        entity_article_topic_terms = article_topic_terms(strategy_spec, target_source)
        needs_homepage_media = "homepage" in selected_lanes
        qualified_homepage_source: QualifiedHomepageSource | None = None
        if needs_homepage_media:
            frozen_target = frozen_target_by_name(execution_id, entity_id)
            qualified_homepage_source = (
                frozen_target.qualified_homepage_source
                if frozen_target is not None
                else None
            )
            if qualified_homepage_source is None:
                raise DataIssueError(
                    (
                        data_issue(
                            DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING,
                            stage=DataIssueStage.SOURCE_GATE,
                            ref=entity_id,
                            message="homepage target has no frozen qualified authority source",
                        ),
                    )
                )
        configured_aliases = [
            str(value).strip()
            for value in (target_source.get("aliases") or [])
            if str(value).strip()
        ]
        needs_source_discovery_context = bool(
            selected_lanes & {"homepage", "article", "video"}
            or ("image" in selected_lanes and not professional_image_bound)
        )
        initial_aliases = _expanded_entity_aliases(
            [*_entity_name_variants(entity_id), *configured_aliases],
            limit=24,
        )
        geo_context_terms = geo_context_terms_from_ref(
            str(target_source.get("geoTagRef") or "")
        )
        initial_authority = (
            discover_homepage_authority(
                entity_id,
                entity_aliases=tuple(initial_aliases),
                geo_context_terms=geo_context_terms,
                include_external=False,
            )
            if (
                needs_source_discovery_context
                and not (
                    qualified_homepage_source is not None
                    and qualified_homepage_source.provider is HomepageAuthorityProvider.WIKIPEDIA
                )
            )
            else None
        )
        wiki_title = (
            qualified_homepage_source.title
            if (
                qualified_homepage_source is not None
                and qualified_homepage_source.provider is HomepageAuthorityProvider.WIKIPEDIA
            )
            else (initial_authority.wikipedia_title if initial_authority else "")
        )
        qid = (
            _wikidata_item_for_zhwiki(wiki_title) or _wikidata_item_for_entity_search(entity_id)
            if needs_source_discovery_context
            else ""
        )
        entity_aliases = _expanded_entity_aliases(
            [
                *_entity_name_variants(entity_id),
                *configured_aliases,
                *_known_entity_aliases(entity_id),
                wiki_title,
                *(_wikidata_entity_aliases(qid) if needs_source_discovery_context else []),
            ],
            limit=24,
        )
        professional_image_receipt_refs, professional_image_specs = (
            professional_image_context_binding(
                execution_id=execution_id,
                entity_id=entity_id,
                carrier=str(external_input_context.envelope["carrier"]),
                external_input_context=external_input_context,
                entity_aliases=tuple(entity_aliases),
                verified_index=professional_image_index,
            )
            if professional_image_bound
            else ([], [])
        )
        authority = (
            discover_homepage_authority(
                entity_id,
                entity_aliases=tuple(entity_aliases),
                geo_context_terms=geo_context_terms,
                wikipedia_title=wiki_title,
                include_external=bool(selected_lanes & {"article", "image", "video"}),
            )
            if needs_source_discovery_context
            else None
        )
        wiki_title = authority.wikipedia_title if authority else ""
        related_wiki_titles = [
            title for title in _wiki_related_titles_for_entity(
                "zh.wikipedia.org",
                entity_id,
                entity_aliases=entity_aliases,
            )
            if title and title != wiki_title
        ] if needs_source_discovery_context else []
        needs_visual_pool = bool(
            selected_lanes & {"homepage", "article", "image", "video"}
        ) and not professional_image_bound
        voyage_title = (
            _wiki_title_for_entity(
                "zh.wikivoyage.org",
                entity_id,
                entity_aliases=configured_aliases,
            )
            if (needs_source_discovery_context or needs_homepage_media)
            and (needs_visual_pool or needs_homepage_media)
            else ""
        )
        voyage_url = _wiki_url("zh.wikivoyage.org", voyage_title)
        reject_memory = _download_reject_memory(
            execution_id,
            entity_id,
            entity_type=entity_type,
        )
        rejected_source_urls = reject_memory["sourceUrls"]
        rejected_image_urls = reject_memory["imageUrls"]
        prior_image_collections = (
            _verified_image_collections_from_prior_plans(
                execution_id,
                entity_id,
                entity_type=entity_type,
                vertical=vertical,
                entity_aliases=entity_aliases,
                rejected_image_urls=rejected_image_urls,
                limit=max(image_bonus_saturation_count, 8),
            )
            if needs_visual_pool
            else []
        )
        prior_image_pool = _images_from_collections(prior_image_collections)
        prior_article_sources = (
            _verified_article_sources_from_prior_plans(
                execution_id,
                entity_id,
                entity_type=entity_type,
                vertical=vertical,
                entity_aliases=entity_aliases,
                rejected_source_urls=rejected_source_urls,
                limit=_article_base_candidate_limit(required_article_bases),
            )
            if "article" in selected_lanes
            else []
        )
        image_pools = (
            _discover_open_license_image_pools(
                entity_id,
                entity_aliases=entity_aliases,
                qid=qid,
                wiki_title=wiki_title,
                voyage_title=voyage_title,
                rejected_image_urls=rejected_image_urls,
            )
            if needs_visual_pool
            else {
                "commons": [],
                "hint_commons": [],
                "wikidata_commons": [],
                "openverse": [],
                "wiki_page_images": [],
                "voyage_page_images": [],
            }
        )
        commons = image_pools["commons"]
        hint_commons = image_pools.get("hint_commons") or []
        wikidata_commons = image_pools["wikidata_commons"]
        openverse = image_pools["openverse"]
        wiki_page_images = image_pools["wiki_page_images"]
        voyage_page_images = image_pools["voyage_page_images"]
        open_license_image_pool = (
            prior_image_pool
            + openverse
            + commons
            + hint_commons
            + wikidata_commons
            + wiki_page_images
            + voyage_page_images
        )
        if needs_visual_pool and not open_license_image_pool:
            rescue_pools = _discover_open_license_image_pools(
                entity_id,
                entity_aliases=entity_aliases,
                qid=qid,
                wiki_title=wiki_title,
                voyage_title=voyage_title,
                rejected_image_urls=rejected_image_urls,
                commons_limit=20,
                wikidata_limit=20,
                openverse_limit=24,
                page_limit=14,
            )
            rescue_pool = (
                rescue_pools["openverse"]
                + rescue_pools["commons"]
                + (rescue_pools.get("hint_commons") or [])
                + rescue_pools["wikidata_commons"]
                + rescue_pools["wiki_page_images"]
                + rescue_pools["voyage_page_images"]
            )
            if rescue_pool:
                commons = rescue_pools["commons"]
                hint_commons = rescue_pools.get("hint_commons") or []
                wikidata_commons = rescue_pools["wikidata_commons"]
                openverse = rescue_pools["openverse"]
                wiki_page_images = rescue_pools["wiki_page_images"]
                voyage_page_images = rescue_pools["voyage_page_images"]
                open_license_image_pool = prior_image_pool + rescue_pool
                report.setdefault("rescueEvents", []).append(
                    {
                        "entityId": entity_id,
                        "lane": "image",
                        "reason": "open_license_image_discovery_empty_on_first_pass",
                        "images": len(rescue_pool),
                    }
                )
        # 正文来源的 imageUrls 仍只能来自该页面自身图位；开放许可检索结果进入独立
        # homepageMediaCollections，禁止伪装为正文同源图片。
        homepage_image_pool = wiki_page_images or voyage_page_images
        homepage_image_urls = {
            str(image.get("url") or "")
            for image in homepage_image_pool
            if str(image.get("url") or "").strip()
        }
        external_links = (
            _trusted_external_links(
                wiki_title,
                limit=max(4, min(12, required_article_bases * 2)),
            )
            if "article" in selected_lanes
            else []
        )
        if "image" in selected_lanes:
            # 图库 acquisition 与 distribution rights 分轨。Pinterest/图虫只有在公开直链、
            # 平台支持 API 或人工文件真实取得后才可形成 research 候选；未验证权利如实记录，
            # 不因缺商业授权丢弃，也绝不绕过登录、验证码、付费墙或访问控制。
            report.setdefault(
                "professionalImageLibraryCompliance",
                professional_library_compliance_summary(),
            )
        if (
            "image" in selected_lanes
            and requires_publishable_images
            and not professional_image_bound
            and not open_license_image_pool
        ):
            issues.append(f"{entity_id}: no rights-compatible open-license images discovered")
            if "image" in selected_lanes:
                _record_unavailable(
                    report,
                    entity_id=entity_id,
                    lane="image",
                    reason="no rights-compatible Openverse/Wikimedia images discovered",
                    code=DataIssueCode.MEDIA_RIGHTS_UNAVAILABLE,
                    recovery=DataRecoveryAction.STOP,
                )

        homepage_sources = (
            write_homepage_lane(HomepageResearchInput(
                execution_id=execution_id,
                entity_id=entity_id,
                entity_aliases=tuple(entity_aliases),
                vertical=vertical,
                plan_dir=dl,
                report=report,
                updated=updated,
                qualified_homepage_source=qualified_homepage_source,
                wiki_page_images=tuple(wiki_page_images),
                prior_image_pool=tuple(prior_image_pool),
                voyage_page_images=tuple(voyage_page_images),
                commons=tuple(commons),
                hint_commons=tuple(hint_commons),
                wikidata_commons=tuple(wikidata_commons),
                openverse=tuple(openverse),
                rejected_source_urls=frozenset(rejected_source_urls),
                force=force,
                professional_image_specs=tuple(professional_image_specs),
                acquisition_receipt_refs=tuple(
                    professional_image_receipt_refs
                ),
            ))
            if "homepage" in selected_lanes
            else []
        )

        write_article_lane(
            execution_id=execution_id,
            entity_id=entity_id,
            entity_type=entity_type,
            vertical=vertical,
            selected_lanes=selected_lanes,
            report=report,
            issues=issues,
            updated=updated,
            plan_dir=dl,
            entity_aliases=entity_aliases,
            topic_terms=entity_article_topic_terms,
            related_wiki_titles=related_wiki_titles,
            voyage_url=voyage_url,
            voyage_page_images=voyage_page_images,
            external_links=external_links,
            rejected_source_urls=rejected_source_urls,
            prior_article_sources=prior_article_sources,
            homepage_sources=homepage_sources,
            required_article_bases=required_article_bases,
            force=force,
        )

        if "image" in selected_lanes:
            entity_desired_image_works = (
                len(image_work_units.get(entity_id, ()))
                if exact_media_work_units
                else desired_image_works
            )
            entity_hard_image_works = (
                entity_desired_image_works
                if exact_media_work_units
                else hard_image_works
            )
            entity_required_publishable_images = (
                entity_desired_image_works
                if exact_media_work_units
                else required_publishable_images
            )
            write_image_lane(
                entity_id=entity_id,
                entity_aliases=entity_aliases,
                vertical=vertical,
                plan_dir=dl,
                force=force,
                report=report,
                updated=updated,
                prior_image_collections=prior_image_collections,
                prior_image_pool=prior_image_pool,
                openverse=openverse,
                commons=commons,
                hint_commons=hint_commons,
                wikidata_commons=wikidata_commons,
                wiki_page_images=wiki_page_images,
                voyage_page_images=voyage_page_images,
                open_license_image_pool=open_license_image_pool,
                homepage_image_urls=homepage_image_urls,
                required_publishable_images=entity_required_publishable_images,
                required_article_bases=required_article_bases,
                desired_image_works=entity_desired_image_works,
                hard_image_works=entity_hard_image_works,
                image_bonus_saturation_count=max(1, entity_desired_image_works),
                image_policy=image_policy,
                image_strategy=image_strategy,
                requires_publishable_images=requires_publishable_images,
                qid=qid,
                wiki_title=wiki_title,
                voyage_title=voyage_title,
                professional_image_specs=professional_image_specs,
                acquisition_receipt_refs=professional_image_receipt_refs,
            )
        if "video" in selected_lanes:
            video_provider_funnel: list[dict[str, Any]] = []
            sourced_video_pool = (
                []
                if video_receipt_refs
                else discover_commons_sourced_videos(
                    entity_id,
                    entity_aliases=entity_aliases,
                    diagnostics=video_provider_funnel,
                )
            )
            report.setdefault("videoProviderFunnels", []).extend(video_provider_funnel)
            write_video_lane(
                entity_id=entity_id,
                plan_dir=dl,
                force=force,
                report=report,
                updated=updated,
                sourced_video_pool=sourced_video_pool,
                acquisition_receipt_refs=video_receipt_refs,
                acquisition_root=video_acquisition_root,
                entity_aliases=tuple(entity_aliases),
                desired_video_works=(
                    len(video_work_units.get(entity_id, ()))
                    if exact_media_work_units
                    else max(1, int(quotas.get("videoWorksPerTarget") or 1))
                ),
                verified_index=professional_video_index,
            )
    report["sourceAvailability"] = _source_availability_summary(report, entity_ids)
    if write_shared_report:
        _write_auto_report_artifacts(execution_id, report)
    return report
