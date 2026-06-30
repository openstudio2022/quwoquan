"""Per-entity auto research plan implementation."""
from __future__ import annotations

import urllib.parse
from typing import Any

from _common.image_asset_strategy import (
    image_count_is_hard_quota,
    image_count_policy,
    image_asset_strategy,
    image_strategy_requires_publishable_images,
    minimum_publishable_images_per_target,
)
from _common.paths import STAGE_DOWNLOAD
from _common.source_catalog import vertical_from_task_id
from _common.source_unit import resolve_entity_object_dir
from download.prepare import prepare_source_plan

from download.research.auto_plan_facade import (
    _discover_open_license_image_pools,
    _external_article_category,
    _external_platform,
    _known_article_sources,
    _known_entity_aliases,
    _known_homepage_support_websites,
    _known_official_website,
    _mediawiki_page_images,
    _official_website,
    _qunar_review_support_source,
    _qunar_travelogue_sources,
    _task_content_quotas,
    _trusted_external_links,
    _wikidata_entity_aliases,
    _wikidata_item_for_entity_search,
    _wikidata_item_for_zhwiki,
)
from download.research.image_provider_compliance import (
    professional_library_compliance_summary,
)
from download.research.auto_plan_report import (
    _source_availability_summary,
    _write_auto_report_artifacts,
)
from download.research.plan_state import (
    _accept_source,
    _accept_source_with_reject_memory,
    _download_reject_memory,
    _homepage_urls_from_current_plan,
    _image_at,
    _image_window,
    _images_from_collections,
    _record_unavailable,
    _safe_collection_id,
    _source,
    _source_unavailable_for_entity,
    _task_spec,
    _url_in_memory,
    _verified_article_sources_from_prior_plans,
    _verified_homepage_sources_from_source_units,
    _verified_image_collections_from_prior_plans,
    _write_lane,
)
from download.research.source_quality import (
    _ARTICLE_BASE_CATEGORIES,
    _HOMEPAGE_CORE_SOURCE_LIMIT,
    _article_base_candidate_limit,
    _collection_gate,
    _collection_publishable_image_urls,
    _evidence_reason,
    _homepage_can_seed_base_draft,
    _homepage_core_sources,
    _select_article_plan_sources,
)
from download.research.text_match import _entity_name_variants, _expanded_entity_aliases
from download.research.wiki_discovery import (
    _BASE_DRAFT_IMAGE_CANDIDATES,
    _wiki_related_titles_for_entity,
    _wiki_title_for_entity,
    _wiki_url,
)

def _write_auto_research_plans_impl(
    task_id: str,
    batch_id: str,
    entity_ids: list[str],
    *,
    entity_type: str,
    force: bool = False,
    lanes: set[str] | None = None,
    write_shared_report: bool = True,
) -> dict[str, Any]:
    selected_lanes = lanes or {"homepage", "article", "image"}
    vertical = vertical_from_task_id(task_id)
    entities = [
        {"entityId": entity_id, "canonicalName": entity_id, "entityType": entity_type}
        for entity_id in entity_ids
    ]
    prepare_source_plan(task_id, batch_id, entities)
    updated: list[dict[str, Any]] = []
    issues: list[str] = []
    report: dict[str, Any] = {
        "schemaVersion": "quwoquan.download.auto_research_plan",
        "taskId": task_id,
        "batchId": batch_id,
        "vertical": vertical,
        "selectedLanes": sorted(selected_lanes),
        "updated": updated,
        "issues": issues,
        "candidates": [],
        "imageCollections": [],
        "sourceUnavailable": [],
        "rescueEvents": [],
    }
    quotas = _task_content_quotas(task_id)
    strategy_spec = _task_spec(task_id)
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
    try:
        from download.gate import download_requirements

        required_publishable_images = max(
            hard_image_works,
            int(download_requirements(task_id).get("minImages") or 0),
        )
    except Exception:  # noqa: BLE001
        required_publishable_images = hard_image_works
    from _common.base_draft import ARTICLE_MIN_BASE_DRAFT_CHARS

    report["scoringPolicy"] = {
        "imageCountPolicy": image_policy,
        "imageBonusSaturationCount": image_bonus_saturation_count,
        "minimumPublishableImagesPerTarget": hard_image_works,
        # RC6：长文字数门唯一真相源（图文混排走 base_draft_readiness 自适应，不在此体现固定门）。
        "articleLengthPassChars": ARTICLE_MIN_BASE_DRAFT_CHARS,
    }
    for entity_id in entity_ids:
        obj = resolve_entity_object_dir(task_id, batch_id, entity_id, etype_hint=entity_type)
        dl = obj / STAGE_DOWNLOAD
        initial_aliases = _entity_name_variants(entity_id)
        wiki_title = _wiki_title_for_entity(
            "zh.wikipedia.org",
            entity_id,
            entity_aliases=initial_aliases,
        )
        qid = _wikidata_item_for_zhwiki(wiki_title) or _wikidata_item_for_entity_search(entity_id)
        entity_aliases = _expanded_entity_aliases(
            [
                *_entity_name_variants(entity_id),
                *_known_entity_aliases(entity_id),
                wiki_title,
                *_wikidata_entity_aliases(qid),
            ],
            limit=24,
        )
        if not wiki_title:
            wiki_title = _wiki_title_for_entity(
                "zh.wikipedia.org",
                entity_id,
                entity_aliases=entity_aliases,
            )
        related_wiki_titles = [
            title for title in _wiki_related_titles_for_entity(
                "zh.wikipedia.org",
                entity_id,
                entity_aliases=entity_aliases,
            )
            if title and title != wiki_title
        ]
        needs_visual_pool = bool(selected_lanes & {"article", "image"})
        voyage_title = (
            _wiki_title_for_entity(
                "zh.wikivoyage.org",
                entity_id,
                entity_aliases=entity_aliases,
            )
            if needs_visual_pool
            else ""
        )
        wiki_url = _wiki_url("zh.wikipedia.org", wiki_title)
        voyage_url = _wiki_url("zh.wikivoyage.org", voyage_title)
        registry_official_url = _known_official_website(entity_id)
        official_url = registry_official_url or _official_website(qid)
        official_provider = (
            "travel_source_registry"
            if registry_official_url
            else "wikidata_official_website"
        )
        official_reason_provider = (
            "Travel source registry official website"
            if registry_official_url
            else "Wikidata official website"
        )
        reject_memory = _download_reject_memory(
            task_id,
            batch_id,
            entity_id,
            entity_type=entity_type,
        )
        rejected_source_urls = reject_memory["sourceUrls"]
        rejected_image_urls = reject_memory["imageUrls"]
        prior_image_collections = (
            _verified_image_collections_from_prior_plans(
                task_id,
                batch_id,
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
                task_id,
                batch_id,
                entity_id,
                entity_type=entity_type,
                rejected_source_urls=rejected_source_urls,
                limit=_article_base_candidate_limit(required_article_bases),
            )
            if "article" in selected_lanes
            else []
        )
        prior_homepage_sources = (
            _verified_homepage_sources_from_source_units(
                task_id,
                batch_id,
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
        # 实体百科底稿(homepage)图位绝不混入 commons/openverse 等搜索池——那些只能用于
        # P4 独立"图片作品"lane。同源隔离：homepage 图只来自页面自身 wikitext 真实图位
        # (wiki/voyage)，宁可受限标注，也不混入页面外图。
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
        if needs_visual_pool and requires_publishable_images and not open_license_image_pool:
            issues.append(f"{entity_id}: no rights-compatible open-license images discovered")
            if "image" in selected_lanes:
                _record_unavailable(
                    report,
                    entity_id=entity_id,
                    lane="image",
                    reason="no rights-compatible Openverse/Wikimedia images discovered",
                    next_action="manual_authorized_gallery_or_target_replacement",
                )

        homepage_sources: list[dict[str, Any]] = []
        baidu_url = f"https://baike.baidu.com/item/{urllib.parse.quote(entity_id)}"
        if "homepage" in selected_lanes:
            def _accept_homepage_source(source: dict[str, Any]) -> dict[str, Any] | None:
                return _accept_source_with_reject_memory(
                    report,
                    source,
                    entity_id=entity_id,
                    lane="homepage",
                    entity_aliases=entity_aliases,
                    rejected_source_urls=rejected_source_urls,
                )

            def _encyclopedia_role() -> str:
                # P3 三类解耦：实体主页主源【只限百科】。首个被接受的百科作 primary，
                # 其余百科与官网/补充源一律 supporting，使 plan 的 sourceRole 与消费侧择优一致（消除第二真相源）。
                for existing in homepage_sources:
                    if (
                        str(existing.get("category") or "").casefold() == "encyclopedia"
                        and str(existing.get("sourceRole") or "") == "primary"
                    ):
                        return "supporting"
                return "primary"

            for prior_source in prior_homepage_sources:
                if len(homepage_sources) >= _HOMEPAGE_CORE_SOURCE_LIMIT:
                    break
                accepted = _accept_homepage_source(dict(prior_source))
                if accepted:
                    homepage_sources.append(accepted)
            if official_url:
                accepted = _accept_homepage_source(
                    _source(
                        source_id="home_official",
                        platform="景区官网",
                        url=official_url,
                        category="official",
                        discovery_provider=official_provider,
                        match_confidence=0.94,
                        evidence_reason=_evidence_reason(
                            entity_id, "homepage", official_reason_provider, "official"
                        ),
                        # P3: 官网降为 supporting（只补事实，不得作 base draft 主源）。
                        source_role="supporting",
                    )
                )
                if accepted:
                    homepage_sources.append(accepted)
            if wiki_url:
                accepted = _accept_homepage_source(
                    _source(
                        source_id="home_wikipedia",
                        platform="维基百科",
                        url=wiki_url,
                        category="encyclopedia",
                        discovery_provider="mediawiki_exact_title",
                        match_confidence=0.99,
                        evidence_reason=_evidence_reason(
                            entity_id, "homepage", "Chinese Wikipedia", "encyclopedia"
                        ),
                        source_role=_encyclopedia_role(),
                        images=_image_window(wiki_page_images, 0, count=_BASE_DRAFT_IMAGE_CANDIDATES),
                        image_evidence_mode="same_source" if wiki_page_images else "",
                    )
                )
                if accepted:
                    homepage_sources.append(accepted)
            for support_index, support in enumerate(_known_homepage_support_websites(entity_id), start=1):
                if len(homepage_sources) >= _HOMEPAGE_CORE_SOURCE_LIMIT:
                    break
                accepted = _accept_homepage_source(
                    _source(
                        source_id=support["source_id"] or f"home_official_support_{support_index}",
                        platform=support["platform"] or "景区官网",
                        url=support["url"],
                        category=support["category"] or "official",
                        discovery_provider="travel_source_registry",
                        match_confidence=0.90,
                        evidence_reason=_evidence_reason(
                            entity_id,
                            "homepage",
                            "Travel source registry official detail page",
                            support["category"] or "official",
                        ),
                        source_role="supporting",
                        images=[],
                        image_evidence_mode="",
                    )
                )
                if accepted:
                    homepage_sources.append(accepted)
            accepted = _accept_homepage_source(
                _source(
                    source_id="home_baidu_baike",
                    platform="百度百科",
                    url=baidu_url,
                    category="encyclopedia",
                    discovery_provider="baidu_baike_exact_item_url",
                    match_confidence=0.86,
                    evidence_reason=_evidence_reason(
                        entity_id, "homepage", "Baidu Baike item URL", "encyclopedia"
                    ),
                    # P3 多源择优：百度百科作百科候选，若 wiki 缺失则升为 primary。
                    source_role=_encyclopedia_role(),
                    images=[],
                    image_evidence_mode="",
                )
            )
            if accepted:
                homepage_sources.append(accepted)
            for related_index, related_title in enumerate(related_wiki_titles[:2], start=1):
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
            if len(homepage_sources) < 2:
                accepted = _accept_homepage_source(
                    _source(
                        source_id="home_sogou_baike",
                        platform="搜狗百科",
                        url=f"https://baike.sogou.com/v?query={urllib.parse.quote(entity_id)}",
                        category="encyclopedia",
                        discovery_provider="sogou_baike_exact_query_url",
                        match_confidence=0.78,
                        evidence_reason=_evidence_reason(
                            entity_id, "homepage", "Sogou Baike query URL", "encyclopedia"
                        ),
                        # P3 多源择优：搜狗百科作百科候选，若 wiki/百度均缺失则升为 primary。
                        source_role=_encyclopedia_role(),
                        images=[],
                        image_evidence_mode="",
                    )
                )
                if accepted:
                    homepage_sources.append(accepted)
            homepage_core_sources = _homepage_core_sources(homepage_sources)
            if _write_lane(
                dl / "homepage_source_plan.json",
                "homepage",
                {
                    "primaryEvidenceRef": (
                        homepage_core_sources[0]["source_id"]
                        if homepage_core_sources
                        else ""
                    ),
                    "sources": homepage_core_sources,
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
            homepage_seed_sources = [
                source for source in homepage_core_sources if _homepage_can_seed_base_draft(source)
            ]
            if not homepage_seed_sources:
                _record_unavailable(
                    report,
                    entity_id=entity_id,
                    lane="homepage",
                    reason="homepage has no encyclopedia (wiki/baidu/sogou) seed source for baseDraft",
                    next_action="manual_homepage_seed_source_or_target_replacement",
                )

        article_sources: list[dict[str, Any]] = []
        if "article" in selected_lanes:
            for source in _qunar_travelogue_sources(
                entity_id,
                entity_aliases=entity_aliases,
                limit=_article_base_candidate_limit(required_article_bases),
            ):
                accepted = _accept_source(
                    report,
                    source,
                    entity_id=entity_id,
                    lane="article",
                    entity_aliases=entity_aliases,
                )
                if accepted:
                    article_sources.append(accepted)
            accepted = _accept_source(
                report,
                _qunar_review_support_source(entity_id),
                entity_id=entity_id,
                lane="article",
                entity_aliases=entity_aliases,
            )
            if accepted:
                article_sources.append(accepted)
            for related_index, related_title in enumerate(related_wiki_titles, start=1):
                related_url = _wiki_url("zh.wikipedia.org", related_title)
                if not related_url:
                    continue
                related_images = _mediawiki_page_images(
                    "zh.wikipedia.org",
                    related_title,
                    entity_id=entity_id,
                    limit=2,
                )
                accepted = _accept_source(
                    report,
                    _source(
                        source_id=f"article_related_encyclopedia_support_{related_index}",
                        platform="维基百科",
                        url=related_url,
                        category="encyclopedia",
                        discovery_provider="mediawiki_related_title",
                        match_confidence=0.82,
                        evidence_reason=(
                            f"Chinese Wikipedia related page {related_title} provides factual "
                            f"context for {entity_id}; supporting only, not an article base"
                        ),
                        source_role="supporting",
                        images=_image_window(related_images, 0, count=2),
                        image_evidence_mode="same_source" if related_images else "",
                    ),
                    entity_id=entity_id,
                    lane="article",
                    entity_aliases=entity_aliases,
                )
                if accepted:
                    article_sources.append(accepted)
            if voyage_url:
                voyage_images = voyage_page_images
                accepted = _accept_source(
                    report,
                    _source(
                        source_id="article_wikivoyage_base",
                        platform="维基导游",
                        url=voyage_url,
                        category="travelogue",
                        discovery_provider="wikivoyage_exact_title",
                        match_confidence=0.99,
                        evidence_reason=_evidence_reason(
                            entity_id, "article", "Chinese Wikivoyage", "travelogue"
                        ),
                        source_role="base",
                        images=_image_window(voyage_images, 0, count=_BASE_DRAFT_IMAGE_CANDIDATES),
                        image_evidence_mode=(
                            "same_source" if voyage_page_images else ""
                        ) if voyage_images else "",
                    ),
                    entity_id=entity_id,
                    lane="article",
                    entity_aliases=entity_aliases,
                )
                if accepted:
                    article_sources.append(accepted)
            for index, link in enumerate(external_links, start=1):
                if _url_in_memory(link, rejected_source_urls):
                    continue
                platform = _external_platform(link)
                category = _external_article_category(link, platform)
                source_role = "base" if category in _ARTICLE_BASE_CATEGORIES else "supporting"
                accepted = _accept_source(
                    report,
                    _source(
                        source_id=(
                            f"article_external_base_{index}"
                            if source_role == "base"
                            else f"article_authoritative_support_{index}"
                        ),
                        platform=platform,
                        url=link,
                        category=category,
                        discovery_provider="wikipedia_trusted_extlinks",
                        match_confidence=0.80,
                        evidence_reason=_evidence_reason(
                            entity_id, "article", "Wikipedia trusted external links", category
                        ),
                        source_role=source_role,
                        images=[],
                        image_evidence_mode="",
                    ),
                    entity_id=entity_id,
                    lane="article",
                    entity_aliases=entity_aliases,
                )
                if accepted:
                    article_sources.append(accepted)
            for index, known in enumerate(_known_article_sources(entity_id), start=1):
                if _url_in_memory(str(known.get("url") or ""), rejected_source_urls):
                    continue
                category = str(known.get("category") or "travelogue").strip()
                source_role = "base" if category in _ARTICLE_BASE_CATEGORIES else "supporting"
                accepted = _accept_source(
                    report,
                    _source(
                        source_id=known["source_id"] or f"article_registry_base_{index}",
                        platform=known["platform"] or "垂类专业站",
                        url=known["url"],
                        category=category,
                        discovery_provider="travel_source_registry",
                        match_confidence=0.88,
                        evidence_reason=_evidence_reason(
                            entity_id,
                            "article",
                            "Travel source registry known article source",
                            category,
                        ),
                        source_role=source_role,
                        images=[],
                        image_evidence_mode="",
                        fetchable_override=bool(known.get("fetchable")),
                    ),
                    entity_id=entity_id,
                    lane="article",
                    entity_aliases=entity_aliases,
                )
                if accepted:
                    if known.get("title"):
                        accepted["title"] = known["title"]
                    article_sources.append(accepted)
            commons_visual = _image_at(commons, 5)
            open_visual = _image_at(openverse, 0)
            if commons_visual or open_visual:
                visual = commons_visual or open_visual or {}
                accepted = _accept_source(
                    report,
                    _source(
                        source_id="article_open_visual_support",
                        platform=str(visual.get("platform") or "Openverse"),
                        url=str(visual.get("sourceUrl") or visual.get("url") or ""),
                        category="open_license",
                        discovery_provider="open_license_image_search",
                        match_confidence=0.82,
                        evidence_reason=_evidence_reason(
                            entity_id, "article", "Open license image search", "open_license"
                        ),
                        source_role="supporting",
                        images=[],
                        image_evidence_mode="",
                    ),
                    entity_id=entity_id,
                    lane="article",
                    entity_aliases=entity_aliases,
                )
                if accepted:
                    article_sources.append(accepted)
            seen_article_urls = {
                str(source.get("url") or "").strip()
                for source in article_sources
                if str(source.get("url") or "").strip()
            }
            homepage_urls = {
                str(source.get("url") or "").strip()
                for source in homepage_sources
                if str(source.get("url") or "").strip()
            }
            homepage_urls.update(
                _homepage_urls_from_current_plan(
                    task_id,
                    batch_id,
                    entity_id,
                    entity_type=entity_type,
                )
            )
            for source in prior_article_sources:
                url = str(source.get("url") or "").strip()
                if not url or url in seen_article_urls or url in homepage_urls:
                    continue
                if _url_in_memory(url, rejected_source_urls):
                    continue
                accepted = _accept_source(
                    report,
                    source,
                    entity_id=entity_id,
                    lane="article",
                    entity_aliases=entity_aliases,
                )
                if accepted:
                    article_sources.append(accepted)
                    seen_article_urls.add(url)
            base_count = sum(1 for source in article_sources if source.get("sourceRole") == "base")
            if base_count < required_article_bases:
                issues.append(
                    f"{entity_id}: article base sources={base_count} need>={required_article_bases}"
                )
                _record_unavailable(
                    report,
                    entity_id=entity_id,
                    lane="article",
                    reason=f"article base sources={base_count} need>={required_article_bases}",
                    next_action="agent_repair_or_manual_fetchable_article_provider",
                )
            if len(article_sources) < required_article_bases:
                issues.append(
                    f"{entity_id}: article auto plan has {len(article_sources)} "
                    f"source(s), need >={required_article_bases}"
                )
            article_plan_sources = _select_article_plan_sources(
                article_sources,
                required_article_bases=required_article_bases,
            )
            if _write_lane(
                dl / "article_source_plan.json",
                "article",
                {"sources": article_plan_sources},
                force=force,
            ):
                updated.append(
                    {
                        "entityId": entity_id,
                        "lane": "article",
                        "sources": len(article_plan_sources),
                    }
                )

        if "image" in selected_lanes:
            collections: list[dict[str, Any]] = []
            desired_image_collections = max(
                required_publishable_images + 3,
                min(12, required_publishable_images + required_article_bases + 3),
            )
            used_collection_ids: set[str] = set()
            for collection in prior_image_collections:
                collection_id = str(collection.get("sourceCollectionId") or "").strip()
                if not collection_id or collection_id in used_collection_ids:
                    continue
                collection_verdict = _collection_gate(
                    collection,
                    entity_id=entity_id,
                    entity_aliases=entity_aliases,
                    vertical=vertical,
                )
                report.setdefault("imageCollections", []).append(
                    {
                        "entityId": entity_id,
                        "sourceCollectionId": collection_id,
                        "platform": collection.get("platform") or "",
                        "imageCount": len(collection.get("images") or []),
                        "passed": bool(collection_verdict.get("passed")),
                        "issues": list(collection_verdict.get("issues") or []),
                        "discoveryProvider": "verified_source_pool_reuse",
                    }
                )
                if not collection_verdict["passed"]:
                    continue
                used_collection_ids.add(collection_id)
                collections.append(collection)
                if len(collections) >= desired_image_collections:
                    break
            first_image = (
                _image_at(prior_image_pool, 0)
                or _image_at(openverse, 0)
                or _image_at(commons, 0)
                or _image_at(wikidata_commons, 0)
                or _image_at(wiki_page_images, 0)
                or _image_at(voyage_page_images, 0)
            )
            if first_image and len(collections) < desired_image_collections:
                collection_candidates = (
                    openverse
                    + commons
                    + hint_commons
                    + wikidata_commons
                    + wiki_page_images
                    + voyage_page_images
                )
                collection_candidates = sorted(
                    collection_candidates,
                    key=lambda item: str(item.get("url") or "") in homepage_image_urls,
                )
                for raw_item in collection_candidates:
                    item = dict(raw_item)
                    collection_id = _safe_collection_id(
                        "open_license_file",
                        entity_id,
                        str(item.get("sourceCollectionId") or item.get("sourceUrl") or item.get("url") or ""),
                    )
                    if collection_id in used_collection_ids:
                        continue
                    used_collection_ids.add(collection_id)
                    item["sourceCollectionId"] = collection_id
                    item["creator"] = item.get("creator") or item.get("credit") or "Wikimedia Commons contributor"
                    item["collectionPageUrl"] = item.get("collectionPageUrl") or item.get("sourceUrl") or item.get("url") or ""
                    item["researchLane"] = "image"
                    collection = {
                        "sourceCollectionId": collection_id,
                        "creator": item["creator"],
                        "credit": item.get("credit") or item["creator"],
                        "collectionPageUrl": item["collectionPageUrl"],
                        "platform": item.get("platform") or "Openverse",
                        "license": item.get("license") or "",
                        "termsUrl": item.get("termsUrl") or "",
                        "licenseSnapshot": item.get("licenseSnapshot") or "",
                        "authorizationProof": item.get("authorizationProof") or item["collectionPageUrl"],
                        "usageScope": "app_publish",
                        "discoveryProvider": "open_license_image_search",
                        "evidenceReason": _evidence_reason(
                            entity_id, "image", "Open license image search", "open_license"
                        ),
                        "images": [item],
                    }
                    collection_verdict = _collection_gate(
                        collection,
                        entity_id=entity_id,
                        entity_aliases=entity_aliases,
                        vertical=vertical,
                    )
                    report.setdefault("imageCollections", []).append(
                        {
                            "entityId": entity_id,
                            "sourceCollectionId": collection_id,
                            "platform": collection.get("platform") or "",
                            "imageCount": len(collection.get("images") or []),
                            "passed": bool(collection_verdict.get("passed")),
                            "issues": list(collection_verdict.get("issues") or []),
                        }
                    )
                    if collection_verdict["passed"]:
                        collections.append(collection)
                    if len(collections) >= desired_image_collections:
                        break
            if not requires_publishable_images:
                report.setdefault("imageCollections", []).append(
                    {
                        "entityId": entity_id,
                        "sourceCollectionId": "",
                        "platform": "",
                        "imageCount": len(open_license_image_pool),
                        "passed": True,
                        "issues": [],
                        "discoveryProvider": "reference_only_image_strategy",
                        "imageAssetStrategy": image_strategy,
                    }
                )
            elif hard_image_works and not collections:
                _record_unavailable(
                    report,
                    entity_id=entity_id,
                    lane="image",
                    reason="no single-author/single-file rights-cleared image collection",
                    next_action="manual_authorized_gallery_or_target_replacement",
                )
            elif hard_image_works and len(collections) < hard_image_works:
                _record_unavailable(
                    report,
                    entity_id=entity_id,
                    lane="image",
                    reason=f"image collections={len(collections)} need>={hard_image_works}",
                    next_action="manual_authorized_gallery_or_target_replacement",
                )
            else:
                unique_publishable_images = len(
                    _collection_publishable_image_urls(
                        collections,
                        entity_id=entity_id,
                        entity_aliases=entity_aliases,
                        vertical=vertical,
                    )
                )
                if required_publishable_images and unique_publishable_images < required_publishable_images:
                    _record_unavailable(
                        report,
                        entity_id=entity_id,
                        lane="image",
                        reason=(
                            f"unique publishable images={unique_publishable_images} "
                            f"need>={required_publishable_images}"
                        ),
                        next_action="manual_authorized_gallery_or_target_replacement",
                    )
            if _write_lane(
                dl / "image_source_plan.json",
                "image",
                {
                    "collections": collections,
                    "imageDiscoveryDiagnostics": {
                        "imageAssetStrategy": image_strategy,
                        "imageCountPolicy": image_policy,
                        "requiresPublishableImages": requires_publishable_images,
                        "desiredImageWorks": desired_image_works,
                        "imageBonusSaturationCount": image_bonus_saturation_count,
                        "requiredImageWorks": hard_image_works,
                        "requiredPublishableImages": required_publishable_images,
                        "qid": qid,
                        "wikiTitle": wiki_title,
                        "voyageTitle": voyage_title,
                        "entityAliases": entity_aliases[:24],
                        "poolCounts": {
                            "priorImageCollections": len(prior_image_collections),
                            "priorImagePool": len(prior_image_pool),
                            "commons": len(commons),
                            "hintCommons": len(hint_commons),
                            "wikidataCommons": len(wikidata_commons),
                            "openverse": len(openverse),
                            "wikiPageImages": len(wiki_page_images),
                            "voyagePageImages": len(voyage_page_images),
                            "openLicenseImagePool": len(open_license_image_pool),
                            "acceptedCollections": len(collections),
                        },
                        "sourceUnavailable": _source_unavailable_for_entity(
                            report,
                            entity_id=entity_id,
                            lane="image",
                        ),
                    },
                    "sourceUnavailable": _source_unavailable_for_entity(
                        report,
                        entity_id=entity_id,
                        lane="image",
                    ),
                },
                force=force,
            ):
                updated.append(
                    {
                        "entityId": entity_id,
                        "lane": "image",
                        "collections": len(collections),
                        "images": sum(len(c.get("images") or []) for c in collections),
                    }
                )
    report["sourceAvailability"] = _source_availability_summary(report, entity_ids)
    if write_shared_report:
        _write_auto_report_artifacts(task_id, batch_id, report)
    return report
