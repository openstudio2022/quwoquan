"""Article source-plan construction for one execution entity."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core.data_issue import DataIssueCode, DataRecoveryAction
from content.source.research.plan_state import (
    _accept_source,
    _image_at,
    _image_window,
    _record_unavailable,
    _source,
    _write_lane,
)
from content.source.research.reject_memory import _url_in_memory
from content.source.research.plan_reuse import _homepage_urls_from_current_plan
from content.source.research.source_quality import (
    _ARTICLE_BASE_CATEGORIES,
    _article_base_candidate_limit,
    _evidence_reason,
    _select_article_plan_sources,
)
from content.source.research.source_registry import _known_article_sources
from content.source.research.wiki_common import _BASE_DRAFT_IMAGE_CANDIDATES
from content.source.research.wiki_core import (
    _external_article_category,
    _external_platform,
    _wiki_url,
)
from content.source.research.wiki_media import _mediawiki_page_images
from content.source.research.qunar_sources import (
    _qunar_review_support_source,
    _qunar_travelogue_sources,
)


def write_article_lane(
    *,
    execution_id: str,
    entity_id: str,
    entity_type: str,
    selected_lanes: set[str],
    report: dict[str, Any],
    issues: list[str],
    updated: list[dict[str, Any]],
    plan_dir: Path,
    entity_aliases: list[str],
    related_wiki_titles: list[str],
    voyage_url: str,
    voyage_page_images: list[dict[str, Any]],
    external_links: list[str],
    rejected_source_urls: set[str],
    prior_article_sources: list[dict[str, Any]],
    homepage_sources: list[dict[str, Any]],
    required_article_bases: int,
    article_commercial_mode: bool,
    commons: list[dict[str, Any]],
    openverse: list[dict[str, Any]],
    force: bool,
) -> None:
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
        if not article_commercial_mode:
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
                execution_id,
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
                code=DataIssueCode.SOURCE_RETAINED_SHORTFALL,
                recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
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
            plan_dir / "article_source_plan.json",
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
