"""Article source-plan construction for one execution entity."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core.data_issue import DataIssueCode, DataRecoveryAction
from core.paths import now_iso
from core.source_catalog import ARTICLE_BASE_SOURCE_CATEGORIES
from content.source.research.plan_state import (
    _accept_source,
    _hydrate_mediawiki_same_source_images,
    _image_window,
    _record_unavailable,
    _source,
    _write_lane,
)
from content.source.research.reject_memory import _url_in_memory
from content.source.research.plan_reuse import _homepage_urls_from_current_plan
from content.source.research.article_frontier_contract import (
    public_article_source_attribution,
)
from content.source.research.article_frontier_profile import (
    article_profile_digest,
    article_search_sites,
    article_url_allowed,
    resolve_article_source_binding,
)
from content.source.research.article_source_unit_catalog import (
    ARTICLE_SOURCE_POLICY_REVISION,
)
from content.source.research.source_quality import (
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
from content.source.research.public_search import discover_article_source_frontier


def _bind_article_source_identity(source: dict[str, Any]) -> dict[str, Any]:
    """Project the frozen registry binding into the source-unit wire identity."""
    projected = dict(source)
    site = resolve_article_source_binding(
        str(projected.get("url") or ""),
        site_id=str(projected.get("articleSiteId") or ""),
        profile_digest=str(projected.get("sourceDiscoveryProfileDigest") or ""),
    )
    profile = site.get("siteCrawlProfile")
    profile = profile if isinstance(profile, dict) else {}
    source_kind = str(site.get("category") or "").strip()
    extractor = str(profile.get("extractor") or site.get("extractor") or "").strip()
    if not source_kind or not extractor:
        raise ValueError("article source registry binding lacks sourceKind/extractor")
    projected.update(
        {
            "sourceKind": source_kind,
            "extractor": extractor,
            "policyRevision": ARTICLE_SOURCE_POLICY_REVISION,
        }
    )
    return projected


def _bind_external_article_source_identity(
    source: dict[str, Any],
) -> dict[str, Any] | None:
    """Admit a discovered external URL only through one current crawl profile."""
    url = str(source.get("url") or "").strip()
    matches = [
        site for site in article_search_sites() if article_url_allowed(url, site)
    ]
    if len(matches) != 1:
        return None
    site = matches[0]
    profile = site.get("siteCrawlProfile")
    profile = profile if isinstance(profile, dict) else {}
    projected = dict(source)
    projected.update(
        {
            "articleSiteId": str(site.get("siteId") or "").strip(),
            "sourceDiscoveryProfileDigest": article_profile_digest(site),
            "articleCommercialAdmission": str(
                profile.get("articleCommercialAdmission") or ""
            ).strip(),
            "sourceUseMode": "factual_reference_only",
        }
    )
    return _bind_article_source_identity(projected)


def _registry_bound_article_base_source(
    source: dict[str, Any],
) -> dict[str, Any] | None:
    """Bind a bespoke article base source to its registry admission and attribution.

    Sources minted outside ``discover_article_source_frontier`` used to reach the
    source unit with no ``articleSiteId``, ``sourceKind`` or ``sourceAttribution``.
    The article carrier inherits attribution from its source unit, so such a
    source cannot be delivered — and before per-source isolation existed it took
    its whole entity down at write time. Admission, identity and attribution now
    come from the same registry entry the frontier uses, and a URL the registry
    does not admit for the article lane is not planned at all.
    """
    bound = _bind_external_article_source_identity(source)
    if bound is None:
        return None
    url = str(bound.get("url") or "").strip()
    site = resolve_article_source_binding(
        url,
        site_id=str(bound.get("articleSiteId") or ""),
        profile_digest=str(bound.get("sourceDiscoveryProfileDigest") or ""),
    )
    profile = site.get("siteCrawlProfile")
    profile = profile if isinstance(profile, dict) else {}
    bound["sourceAttribution"] = public_article_source_attribution(
        platform=str(bound.get("platform") or site.get("platform") or ""),
        canonical_url=url,
        terms_url=str(profile.get("termsUrl") or site.get("termsUrl") or ""),
        captured_at=now_iso(),
    )
    return bound


def write_article_lane(
    *,
    execution_id: str,
    entity_id: str,
    entity_type: str,
    vertical: str,
    selected_lanes: set[str],
    report: dict[str, Any],
    issues: list[str],
    updated: list[dict[str, Any]],
    plan_dir: Path,
    entity_aliases: list[str],
    topic_terms: list[str],
    related_wiki_titles: list[str],
    voyage_url: str,
    voyage_page_images: list[dict[str, Any]],
    external_links: list[str],
    rejected_source_urls: set[str],
    prior_article_sources: list[dict[str, Any]],
    homepage_sources: list[dict[str, Any]],
    required_article_bases: int,
    force: bool,
) -> None:
    article_sources: list[dict[str, Any]] = []
    if "article" in selected_lanes:
        frontier_outcome = discover_article_source_frontier(
            entity_id,
            entity_aliases=entity_aliases,
            topics=topic_terms,
            limit=_article_base_candidate_limit(required_article_bases),
        )
        report.setdefault("articleSourceDiscovery", []).append(
            frontier_outcome.as_evidence()
        )
        for source in frontier_outcome.source_documents():
            source = _bind_article_source_identity(source)
            source = _hydrate_mediawiki_same_source_images(
                source,
                entity_id=entity_id,
                publish_media_mode="illustrated",
            )
            accepted = _accept_source(
                report,
                source,
                entity_id=entity_id,
                lane="article",
                vertical=vertical,
                entity_aliases=entity_aliases,
            )
            if accepted:
                article_sources.append(accepted)
        frontier_base_count = sum(
            1 for source in article_sources if source.get("sourceRole") == "base"
        )
        if frontier_base_count < required_article_bases:
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
                    vertical=vertical,
                    entity_aliases=entity_aliases,
                )
                if accepted:
                    article_sources.append(accepted)
            accepted = _accept_source(
                report,
                _qunar_review_support_source(entity_id),
                entity_id=entity_id,
                lane="article",
                vertical=vertical,
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
                vertical=vertical,
                entity_aliases=entity_aliases,
            )
            if accepted:
                article_sources.append(accepted)
        if voyage_url:
            voyage_images = voyage_page_images
            voyage_source = _registry_bound_article_base_source(
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
                )
            )
            if voyage_source is not None:
                accepted = _accept_source(
                    report,
                    voyage_source,
                    entity_id=entity_id,
                    lane="article",
                    vertical=vertical,
                    entity_aliases=entity_aliases,
                )
                if accepted:
                    article_sources.append(accepted)
        for index, link in enumerate(external_links, start=1):
            if _url_in_memory(link, rejected_source_urls):
                continue
            platform = _external_platform(link)
            category = _external_article_category(link, platform)
            source_role = "base" if category in ARTICLE_BASE_SOURCE_CATEGORIES else "supporting"
            external_source = _bind_external_article_source_identity(
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
                )
            )
            if external_source is None:
                continue
            accepted = _accept_source(
                report,
                external_source,
                entity_id=entity_id,
                lane="article",
                vertical=vertical,
                entity_aliases=entity_aliases,
            )
            if accepted:
                article_sources.append(accepted)
        for index, known in enumerate(_known_article_sources(entity_id), start=1):
            if _url_in_memory(str(known.get("url") or ""), rejected_source_urls):
                continue
            category = str(known.get("category") or "travelogue").strip()
            source_role = "base" if category in ARTICLE_BASE_SOURCE_CATEGORIES else "supporting"
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
                vertical=vertical,
                entity_aliases=entity_aliases,
            )
            if accepted:
                if known.get("title"):
                    accepted["title"] = known["title"]
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
                vertical=vertical,
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
