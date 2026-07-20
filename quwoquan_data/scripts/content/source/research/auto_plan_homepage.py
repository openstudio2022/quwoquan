"""Build the homepage source plan for one entity."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from core.data_issue import DataIssueCode, DataRecoveryAction
from content.source.research.auto_plan_lanes import _independent_homepage_media_collections
from content.source.research.baidu_baike import BaiduBaikeResolution
from content.source.research.baike_com import BaikePageResolution
from content.source.research.homepage_source_policy import (
    _homepage_can_seed_base_draft,
    _homepage_core_sources,
)
from core.content_source_registry import homepage_core_source_limit
from content.source.research.plan_state import (
    _accept_source_with_reject_memory,
    _hydrate_mediawiki_same_source_images,
    _image_window,
    _record_unavailable,
    _source,
    _write_lane,
)
from content.source.research.source_quality import _evidence_reason
from content.source.research.wiki_core import _wiki_url


@dataclass(frozen=True)
class HomepageResearchInput:
    execution_id: str
    entity_id: str
    entity_aliases: tuple[str, ...]
    vertical: str
    plan_dir: Path
    report: dict[str, Any]
    updated: list[dict[str, Any]]
    prior_homepage_sources: tuple[Mapping[str, Any], ...]
    wiki_url: str
    wiki_title: str
    wiki_page_images: tuple[dict[str, Any], ...]
    related_wiki_titles: tuple[str, ...]
    baidu_baike: BaiduBaikeResolution | None
    toutiao_baike: BaikePageResolution | None
    prior_image_pool: tuple[dict[str, Any], ...]
    voyage_page_images: tuple[dict[str, Any], ...]
    commons: tuple[dict[str, Any], ...]
    hint_commons: tuple[dict[str, Any], ...]
    wikidata_commons: tuple[dict[str, Any], ...]
    openverse: tuple[dict[str, Any], ...]
    rejected_source_urls: frozenset[str]
    force: bool
    related_page_images: Callable[..., list[dict[str, Any]]]


def _candidate_sources(spec: HomepageResearchInput) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    source_limit = homepage_core_source_limit()

    def accept(source: dict[str, Any]) -> dict[str, Any] | None:
        return _accept_source_with_reject_memory(
            spec.report,
            _hydrate_mediawiki_same_source_images(source, entity_id=spec.entity_id),
            entity_id=spec.entity_id,
            lane="homepage",
            entity_aliases=list(spec.entity_aliases),
            rejected_source_urls=set(spec.rejected_source_urls),
        )

    for prior_source in spec.prior_homepage_sources:
        if len(sources) >= source_limit:
            break
        accepted = accept(dict(prior_source))
        if accepted:
            sources.append(accepted)
    if spec.wiki_url:
        accepted = accept(_source(
            source_id="home_wikipedia",
            platform="维基百科",
            url=spec.wiki_url,
            source_kind="wikipedia",
            source_title=spec.wiki_title or spec.entity_id,
            category="encyclopedia",
            discovery_provider="mediawiki_exact_title",
            match_confidence=0.99,
            evidence_reason=_evidence_reason(
                spec.entity_id, "homepage", "Chinese Wikipedia", "encyclopedia"
            ),
            source_role="supporting",
            images=list(spec.wiki_page_images),
            image_evidence_mode="same_source" if spec.wiki_page_images else "",
        ))
        if accepted:
            sources.append(accepted)
    if spec.baidu_baike is not None:
        resolved = spec.baidu_baike
        accepted = accept(_source(
            source_id="home_baidu_baike",
            platform="百度百科",
            url=resolved.url,
            source_kind="baidu_baike",
            source_title=resolved.title,
            category="encyclopedia",
            discovery_provider="baidu_baike_html_resolution",
            match_confidence=resolved.match_confidence,
            evidence_reason=_evidence_reason(
                spec.entity_id,
                "homepage",
                f"verified Baidu Baike card API via {resolved.matched_term}",
                "encyclopedia",
            ),
            source_role="supporting",
            images=[],
            image_evidence_mode="",
        ))
        if accepted:
            sources.append(accepted)
    for related_index, related_title in enumerate(spec.related_wiki_titles[:2], start=1):
        if len(sources) >= source_limit:
            break
        related_url = _wiki_url("zh.wikipedia.org", related_title)
        if not related_url:
            continue
        related_images = spec.related_page_images(
            "zh.wikipedia.org", related_title, entity_id=spec.entity_id, limit=3
        )
        accepted = accept(_source(
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
                f"entity context and rights-compatible media for {spec.entity_id}"
            ),
            source_role="supporting",
            images=_image_window(related_images, 0, count=3),
            image_evidence_mode="same_source" if related_images else "",
        ))
        if accepted:
            sources.append(accepted)
    if len(sources) < source_limit and spec.toutiao_baike is not None:
        resolved = spec.toutiao_baike
        accepted = accept(_source(
            source_id="home_toutiao_baike",
            platform="快懂百科",
            url=resolved.url,
            source_kind="toutiao_baike",
            source_title=resolved.title,
            category="encyclopedia",
            discovery_provider="toutiao_baike_canonical_resolution",
            match_confidence=resolved.match_confidence,
            evidence_reason=_evidence_reason(
                spec.entity_id,
                "homepage",
                f"verified baike.com wikiid via {resolved.matched_term}",
                "encyclopedia",
            ),
            source_role="supporting",
            images=[],
            image_evidence_mode="",
        ))
        if accepted:
            sources.append(accepted)
    return sources


def write_homepage_lane(spec: HomepageResearchInput) -> list[dict[str, Any]]:
    homepage_sources = _candidate_sources(spec)
    core_sources = _homepage_core_sources(homepage_sources)
    primary_assigned = False
    for source in core_sources:
        if not primary_assigned and _homepage_can_seed_base_draft(source):
            source["sourceRole"] = "primary"
            primary_assigned = True
        elif str(source.get("sourceRole") or "") == "primary":
            source["sourceRole"] = "supporting"
    seed_sources = [source for source in core_sources if _homepage_can_seed_base_draft(source)]
    same_source_seeds = [
        source for source in seed_sources
        if str(source.get("imageEvidenceMode") or "").strip() == "same_source"
        and any(
            isinstance(item, dict) and str(item.get("url") or "").strip()
            for item in (source.get("imageUrls") or [])
        )
    ]
    media_collections: list[dict[str, Any]] = []
    if seed_sources and not same_source_seeds:
        media_collections = _independent_homepage_media_collections(
            [
                *spec.prior_image_pool,
                *spec.wiki_page_images,
                *spec.voyage_page_images,
                *spec.commons,
                *spec.hint_commons,
                *spec.wikidata_commons,
                *spec.openverse,
            ],
            entity_id=spec.entity_id,
            entity_aliases=list(spec.entity_aliases),
            vertical=spec.vertical,
            report=spec.report,
            limit=1,
        )
    if _write_lane(
        spec.plan_dir / "homepage_source_plan.json",
        "homepage",
        {
            "policyRevision": "encyclopedia-primary",
            "primaryEvidenceRef": core_sources[0]["source_id"] if core_sources else "",
            "sources": core_sources,
            "homepageMediaCollections": media_collections,
        },
        force=spec.force,
    ):
        spec.updated.append({
            "entityId": spec.entity_id,
            "lane": "homepage",
            "sources": len(core_sources),
        })
    if not seed_sources:
        _record_unavailable(
            spec.report,
            entity_id=spec.entity_id,
            lane="homepage",
            reason=(
                "homepage has no explicit encyclopedia-primary "
                "Wikipedia/Baidu/Toutiao source for baseDraft"
            ),
            code=DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING,
            recovery=DataRecoveryAction.STOP,
        )
    elif not same_source_seeds and not media_collections:
        _record_unavailable(
            spec.report,
            entity_id=spec.entity_id,
            lane="homepage",
            reason=(
                "homepage has neither same-source imagery nor an independent "
                "rights-cleared entity-matched media collection"
            ),
            code=DataIssueCode.MEDIA_RIGHTS_UNAVAILABLE,
            recovery=DataRecoveryAction.STOP,
        )
    return core_sources
