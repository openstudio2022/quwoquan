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
from core.article_commercial_policy import article_commercial_closure_enabled
from core.image_asset_strategy import (
    image_count_is_hard_quota,
    image_count_policy,
    image_asset_strategy,
    image_strategy_requires_publishable_images,
    minimum_publishable_images_per_target,
)
from core.paths import STAGE_DOWNLOAD
from core.source_catalog import vertical_from_task_id
from content.source.source_unit import resolve_entity_object_dir
from content.source.prepare import prepare_source_plan
from content.source.research.auto_plan_lanes import (
    _independent_homepage_media_collections,
    write_image_lane,
)
from content.source.research.auto_plan_video import write_video_lane
from content.source.research.auto_plan_article import write_article_lane
from content.source.research.image_provider_compliance import (
    professional_library_compliance_summary,
)
from governance.coverage.license import rights_proof_required
from content.source.research.auto_plan_report import (
    _source_availability_summary,
    _write_auto_report_artifacts,
)
from content.source.research.plan_state import (
    _accept_source,
    _accept_source_with_reject_memory,
    _hydrate_mediawiki_same_source_images,
    _image_at,
    _image_window,
    _record_unavailable,
    _safe_collection_id,
    _source,
    _source_unavailable_for_entity,
    _task_content_quotas,
    _task_spec,
    _write_lane,
)
from content.source.research.reject_memory import (
    _download_reject_memory,
    _images_from_collections,
    _url_in_memory,
    _verified_image_collections_from_prior_plans,
)
from content.source.research.plan_reuse import (
    _homepage_urls_from_current_plan,
    _verified_article_sources_from_prior_plans,
)
from content.source.research.source_quality import (
    _ARTICLE_BASE_CATEGORIES,
    _article_base_candidate_limit,
    _collection_gate,
    _collection_admissible_image_urls,
    _evidence_reason,
    _select_article_plan_sources,
)
from content.source.research.homepage_source_policy import (
    _homepage_can_seed_base_draft,
    _homepage_core_sources,
)
from content.source.research.source_registry import (
    _known_article_sources,
    _known_entity_aliases,
    _known_official_website,
)
from content.source.research.text_match import _entity_name_variants, _expanded_entity_aliases
from content.source.research.wiki_common import _BASE_DRAFT_IMAGE_CANDIDATES
from content.source.research.wiki_core import (
    _external_article_category,
    _external_platform,
    _official_website,
    _trusted_external_links,
    _wikidata_entity_aliases,
    _wikidata_item_for_entity_search,
    _wikidata_item_for_zhwiki,
    _wiki_related_titles_for_entity,
    _wiki_title_for_entity,
    _wiki_url,
)
from content.source.research.wiki_media import (
    _discover_open_license_image_pools,
    _mediawiki_page_images,
)
from content.source.research.qunar_sources import (
    _qunar_review_support_source,
    _qunar_travelogue_sources,
)
from content.source.research.auto_plan_homepage import HomepageResearchInput, write_homepage_lane
from content.source.research.baike_com import geo_context_terms_from_ref
from content.source.research.homepage_authority import discover_homepage_authority
from content.source.contracts import (
    HomepageAuthorityProvider,
    QualifiedHomepageSource,
)
from content.execution.workspace import frozen_target_by_name




def _write_auto_research_plans_impl(
    execution_id: str,
    entity_ids: list[str],
    *,
    entity_type: str,
    force: bool = False,
    lanes: set[str] | None = None,
    write_shared_report: bool = True,
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
    report: dict[str, Any] = {
        "schema": "quwoquan.content.source.auto_research_plan",
        "executionId": execution_id,
        "vertical": vertical,
        "selectedLanes": sorted(selected_lanes),
        "updated": updated,
        "issues": issues,
        "candidates": [],
        "imageCollections": [],
        "videoFrames": [],
        "homepageMediaCollections": [],
        "sourceUnavailable": [],
        "rescueEvents": [],
    }
    quotas = _task_content_quotas(execution_id)
    target_by_name = {
        str(row.get("name") or "").strip(): row
        for row in ((strategy_spec.get("scope") or {}).get("coverageTargets") or [])
        if isinstance(row, dict) and str(row.get("name") or "").strip()
    }
    article_commercial_mode = article_commercial_closure_enabled(strategy_spec)
    image_strategy = image_asset_strategy(strategy_spec)
    image_policy = image_count_policy(strategy_spec)
    requires_publishable_images = image_strategy_requires_publishable_images(strategy_spec)
    report["articleCommercialClosure"] = article_commercial_mode
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
            selected_lanes & {"homepage", "article", "image", "video"}
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
        )
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
        registry_official_url = _known_official_website(entity_id) if needs_source_discovery_context else ""
        official_url = (
            registry_official_url or _official_website(qid)
            if needs_source_discovery_context
            else ""
        )
        official_provider = "travel_source_registry" if registry_official_url else "wikidata_official_website"
        official_reason_provider = "Travel source registry official website" if registry_official_url else "Wikidata official website"
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
            if "article" in selected_lanes and not article_commercial_mode
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
            # P4：图库可发布性以 registry rightsPolicy 为唯一真相源。图虫/Pinterest 等受限
            # 来源如实标注受限（bypassAttempted=false）+ 替代路径=开放许可图池，使"为什么专业
            # 图库不直接进发布面、合规替代是什么"在 research report 中可审计；不抓取、不绕过。
            report.setdefault(
                "professionalImageLibraryCompliance",
                professional_library_compliance_summary(),
            )
        if (
            "image" in selected_lanes
            and requires_publishable_images
            and rights_proof_required(vertical)
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
            related_wiki_titles=related_wiki_titles,
            voyage_url=voyage_url,
            voyage_page_images=voyage_page_images,
            external_links=external_links,
            rejected_source_urls=rejected_source_urls,
            prior_article_sources=prior_article_sources,
            homepage_sources=homepage_sources,
            required_article_bases=required_article_bases,
            article_commercial_mode=article_commercial_mode,
            commons=commons,
            openverse=openverse,
            force=force,
        )

        if "image" in selected_lanes:
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
                required_publishable_images=required_publishable_images,
                required_article_bases=required_article_bases,
                desired_image_works=desired_image_works,
                hard_image_works=hard_image_works,
                image_bonus_saturation_count=image_bonus_saturation_count,
                image_policy=image_policy,
                image_strategy=image_strategy,
                requires_publishable_images=requires_publishable_images,
                qid=qid,
                wiki_title=wiki_title,
                voyage_title=voyage_title,
            )
        if "video" in selected_lanes:
            write_video_lane(
                entity_id=entity_id,
                entity_aliases=entity_aliases,
                vertical=vertical,
                plan_dir=dl,
                force=force,
                report=report,
                updated=updated,
                open_license_image_pool=open_license_image_pool,
            )
    report["sourceAvailability"] = _source_availability_summary(report, entity_ids)
    if write_shared_report:
        _write_auto_report_artifacts(execution_id, report)
    return report
