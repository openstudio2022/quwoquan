"""Per-entity auto research plan implementation."""
from __future__ import annotations
import urllib.parse
from typing import Any
from core.data_issue import DataIssueCode, DataRecoveryAction
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
from content.source.research.auto_plan_article import write_article_lane
from content.source.research.image_provider_compliance import (
    professional_library_compliance_summary,
)
from content.source.research.auto_plan_report import (
    _source_availability_summary,
    _write_auto_report_artifacts,
)
from content.source.research.plan_state import (
    _accept_source,
    _accept_source_with_reject_memory,
    _download_reject_memory,
    _hydrate_mediawiki_same_source_images,
    _image_at,
    _image_window,
    _images_from_collections,
    _record_unavailable,
    _safe_collection_id,
    _source,
    _source_unavailable_for_entity,
    _task_content_quotas,
    _task_spec,
    _url_in_memory,
    _verified_image_collections_from_prior_plans,
    _write_lane,
)
from content.source.research.plan_reuse import (
    _homepage_urls_from_current_plan,
    _verified_article_sources_from_prior_plans,
    _verified_homepage_sources_from_source_units,
)
from content.source.research.source_quality import (
    _ARTICLE_BASE_CATEGORIES,
    _article_base_candidate_limit,
    _collection_gate,
    _collection_publishable_image_urls,
    _evidence_reason,
    _select_article_plan_sources,
)
from content.source.research.homepage_source_policy import (
    _HOMEPAGE_CORE_SOURCE_LIMIT,
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




def _write_auto_research_plans_impl(
    execution_id: str,
    entity_ids: list[str],
    *,
    entity_type: str,
    force: bool = False,
    lanes: set[str] | None = None,
    write_shared_report: bool = True,
) -> dict[str, Any]:
    selected_lanes = lanes or {"homepage", "article", "image"}
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
    report: dict[str, Any] = {
        "schemaVersion": "quwoquan.content.source.auto_research_plan",
        "executionId": execution_id,
        "vertical": vertical,
        "selectedLanes": sorted(selected_lanes),
        "updated": updated,
        "issues": issues,
        "candidates": [],
        "imageCollections": [],
        "homepageMediaCollections": [],
        "sourceUnavailable": [],
        "rescueEvents": [],
    }
    quotas = _task_content_quotas(execution_id)
    strategy_spec = _task_spec(execution_id)
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
    try:
        from content.source.gate import download_requirements
        required_publishable_images = max(
            hard_image_works,
            int(download_requirements(execution_id).get("minImages") or 0),
        )
    except Exception:  # noqa: BLE001
        required_publishable_images = hard_image_works
    from content.post.base_draft import ARTICLE_MIN_BASE_DRAFT_CHARS
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
        configured_aliases = [
            str(value).strip()
            for value in (target_source.get("aliases") or [])
            if str(value).strip()
        ]
        needs_source_discovery_context = bool(selected_lanes & {"homepage", "article", "image"})
        initial_aliases = _expanded_entity_aliases(
            [*_entity_name_variants(entity_id), *configured_aliases],
            limit=24,
        )
        wiki_title = (
            _wiki_title_for_entity(
                "zh.wikipedia.org",
                entity_id,
                entity_aliases=configured_aliases,
            )
            if needs_source_discovery_context
            else ""
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
        if needs_source_discovery_context and not wiki_title:
            wiki_title = _wiki_title_for_entity(
                "zh.wikipedia.org",
                entity_id,
                entity_aliases=configured_aliases,
            )
        related_wiki_titles = [
            title for title in _wiki_related_titles_for_entity(
                "zh.wikipedia.org",
                entity_id,
                entity_aliases=entity_aliases,
            )
            if title and title != wiki_title
        ] if needs_source_discovery_context else []
        needs_visual_pool = bool(selected_lanes & {"homepage", "article", "image"})
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
        wiki_url = _wiki_url("zh.wikipedia.org", wiki_title)
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
                entity_aliases=entity_aliases,
                rejected_source_urls=rejected_source_urls,
                limit=_article_base_candidate_limit(required_article_bases),
            )
            if "article" in selected_lanes and not article_commercial_mode
            else []
        )
        prior_homepage_sources = (
            _verified_homepage_sources_from_source_units(
                execution_id,
                entity_id,
                entity_type=entity_type,
                rejected_source_urls=rejected_source_urls,
            )
            if "homepage" in selected_lanes
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
        if "image" in selected_lanes and requires_publishable_images and not open_license_image_pool:
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

        homepage_sources: list[dict[str, Any]] = []
        baidu_url = f"https://baike.baidu.com/item/{urllib.parse.quote(entity_id)}"
        if "homepage" in selected_lanes:
            def _accept_homepage_source(source: dict[str, Any]) -> dict[str, Any] | None:
                return _accept_source_with_reject_memory(
                    report,
                    _hydrate_mediawiki_same_source_images(source, entity_id=entity_id),
                    entity_id=entity_id,
                    lane="homepage",
                    entity_aliases=entity_aliases,
                    rejected_source_urls=rejected_source_urls,
                )

            for prior_source in prior_homepage_sources:
                if len(homepage_sources) >= _HOMEPAGE_CORE_SOURCE_LIMIT:
                    break
                accepted = _accept_homepage_source(dict(prior_source))
                if accepted:
                    homepage_sources.append(accepted)
            if wiki_url:
                accepted = _accept_homepage_source(
                    _source(
                        source_id="home_wikipedia",
                        platform="维基百科",
                        url=wiki_url,
                        source_kind="wikipedia",
                        source_title=wiki_title or entity_id,
                        category="encyclopedia",
                        discovery_provider="mediawiki_exact_title",
                        match_confidence=0.99,
                        evidence_reason=_evidence_reason(
                            entity_id, "homepage", "Chinese Wikipedia", "encyclopedia"
                        ),
                        # 主权威百科候选；最终 primary 由排序后统一仲裁（消除插入序第二真相源）。
                        source_role="supporting",
                        # 主页同源图片是页面内容的一部分，必须完整进入下载计划；
                        # `_image_window` 只适用于 supporting/article 候选，不适用于主页真相源。
                        images=list(wiki_page_images),
                        image_evidence_mode="same_source" if wiki_page_images else "",
                    )
                )
                if accepted:
                    homepage_sources.append(accepted)
            accepted = _accept_homepage_source(
                _source(
                    source_id="home_baidu_baike",
                    platform="百度百科",
                    url=baidu_url,
                    source_kind="baidu_baike",
                    source_title=entity_id,
                    category="encyclopedia",
                    discovery_provider="baidu_baike_exact_item_url",
                    match_confidence=0.86,
                    evidence_reason=_evidence_reason(
                        entity_id, "homepage", "Baidu Baike item URL", "encyclopedia"
                    ),
                    # 主权威百科候选；最终 primary 由排序后统一仲裁（消除插入序第二真相源）。
                    source_role="supporting",
                    images=[],
                    image_evidence_mode="",
                )
            )
            if accepted:
                homepage_sources.append(accepted)
            for related_index, related_title in enumerate(
                related_wiki_titles[:2], start=1
            ):
                if len(homepage_sources) >= _HOMEPAGE_CORE_SOURCE_LIMIT:
                    break
                related_url = _wiki_url("zh.wikipedia.org", related_title)
                if not related_url:
                    continue
                related_images = _mediawiki_page_images(
                    "zh.wikipedia.org",
                    related_title,
                    entity_id=entity_id,
                    limit=3,
                )
                related_pool = related_images
                accepted = _accept_homepage_source(
                    _source(
                        source_id=f"home_related_encyclopedia_support_{related_index}",
                        platform="维基百科",
                        url=related_url,
                        source_kind="wikipedia",
                        source_title=related_title,
                        category="encyclopedia",
                        discovery_provider="mediawiki_related_title",
                        match_confidence=0.82,
                        evidence_reason=(
                            f"Chinese Wikipedia related page {related_title} provides "
                            f"entity context and rights-compatible media for {entity_id}"
                        ),
                        source_role="supporting",
                        images=_image_window(related_pool, 0, count=3),
                        image_evidence_mode=(
                            "same_source" if related_images else ""
                        ) if related_pool else "",
                    )
                )
                if accepted:
                    homepage_sources.append(accepted)
            if len(homepage_sources) < _HOMEPAGE_CORE_SOURCE_LIMIT:
                accepted = _accept_homepage_source(
                    _source(
                        source_id="home_sogou_baike",
                        platform="搜狗百科",
                        url=f"https://baike.sogou.com/v?query={urllib.parse.quote(entity_id)}",
                        source_kind="sogou_baike",
                        source_title=entity_id,
                        category="encyclopedia",
                        discovery_provider="sogou_baike_exact_query_url",
                        match_confidence=0.78,
                        evidence_reason=_evidence_reason(
                            entity_id, "homepage", "Sogou Baike query URL", "encyclopedia"
                        ),
                        # 主权威百科候选；最终 primary 由排序后统一仲裁（消除插入序第二真相源）。
                        source_role="supporting",
                        images=[],
                        image_evidence_mode="",
                    )
                )
                if accepted:
                    homepage_sources.append(accepted)
            if len(homepage_sources) < _HOMEPAGE_CORE_SOURCE_LIMIT:
                accepted = _accept_homepage_source(
                    _source(
                        source_id="home_toutiao_baike",
                        platform="今日头条百科",
                        url=f"https://www.baike.com/wiki/{urllib.parse.quote(entity_id)}",
                        source_kind="toutiao_baike",
                        source_title=entity_id,
                        category="encyclopedia",
                        discovery_provider="toutiao_baike_exact_item_url",
                        match_confidence=0.78,
                        evidence_reason=_evidence_reason(
                            entity_id, "homepage", "Toutiao Baike item URL", "encyclopedia"
                        ),
                        source_role="supporting",
                        images=[],
                        image_evidence_mode="",
                    )
                )
                if accepted:
                    homepage_sources.append(accepted)
            homepage_core_sources = _homepage_core_sources(homepage_sources)
            # 主源统一仲裁：只在四百科闭集内按 authority rank 选择 primary。
            primary_assigned = False
            for core_source in homepage_core_sources:
                if not primary_assigned and _homepage_can_seed_base_draft(core_source):
                    core_source["sourceRole"] = "primary"
                    primary_assigned = True
                elif str(core_source.get("sourceRole") or "") == "primary":
                    core_source["sourceRole"] = "supporting"
            homepage_seed_sources = [
                source for source in homepage_core_sources if _homepage_can_seed_base_draft(source)
            ]
            homepage_same_source_seed_sources = [
                source
                for source in homepage_seed_sources
                if str(source.get("imageEvidenceMode") or "").strip() == "same_source"
                and any(
                    isinstance(item, dict) and str(item.get("url") or "").strip()
                    for item in (source.get("imageUrls") or [])
                )
            ]
            homepage_media_collections: list[dict[str, Any]] = []
            if homepage_seed_sources and not homepage_same_source_seed_sources:
                homepage_media_collections = _independent_homepage_media_collections(
                    [
                        *prior_image_pool,
                        *wiki_page_images,
                        *voyage_page_images,
                        *commons,
                        *hint_commons,
                        *wikidata_commons,
                        *openverse,
                    ],
                    entity_id=entity_id,
                    entity_aliases=list(entity_aliases),
                    vertical=vertical,
                    report=report,
                    limit=1,
                )
            if _write_lane(
                dl / "homepage_source_plan.json",
                "homepage",
                {
                    "policyRevision": "encyclopedia-primary-v2",
                    "primaryEvidenceRef": (
                        homepage_core_sources[0]["source_id"]
                        if homepage_core_sources
                        else ""
                    ),
                    "sources": homepage_core_sources,
                    "homepageMediaCollections": homepage_media_collections,
                },
                force=force,
            ):
                updated.append(
                    {
                        "entityId": entity_id,
                        "lane": "homepage",
                        "sources": len(homepage_core_sources),
                    }
                )
            if not homepage_seed_sources:
                _record_unavailable(
                    report,
                    entity_id=entity_id,
                    lane="homepage",
                    reason=(
                        "homepage has no explicit encyclopedia-primary-v2 "
                        "Wikipedia/Baidu/Sogou/Toutiao source for baseDraft"
                    ),
                    code=DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING,
                    recovery=DataRecoveryAction.STOP,
                )
            elif not homepage_same_source_seed_sources and not homepage_media_collections:
                _record_unavailable(
                    report,
                    entity_id=entity_id,
                    lane="homepage",
                    reason=(
                        "homepage has neither same-source imagery nor an independent "
                        "rights-cleared entity-matched media collection"
                    ),
                    code=DataIssueCode.MEDIA_RIGHTS_UNAVAILABLE,
                    recovery=DataRecoveryAction.STOP,
                )

        write_article_lane(
            execution_id=execution_id,
            entity_id=entity_id,
            entity_type=entity_type,
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
    report["sourceAvailability"] = _source_availability_summary(report, entity_ids)
    if write_shared_report:
        _write_auto_report_artifacts(execution_id, report)
    return report
