"""Build the homepage source plan for one entity."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.data_issue import DataIssueCode, DataRecoveryAction

from content.source.contracts import (
    HomepageAuthorityProvider,
    QualifiedHomepageSource,
)
from content.source.research.auto_plan_lanes import (
    _independent_homepage_media_collections,
)
from content.source.research.homepage_source_policy import (
    _homepage_can_seed_base_draft,
    _homepage_core_sources,
)
from content.source.research.plan_state import (
    _accept_source_with_reject_memory,
    _hydrate_mediawiki_same_source_images,
    _record_unavailable,
    _source,
    _write_lane,
)
from content.source.research.source_quality import _evidence_reason


@dataclass(frozen=True)
class HomepageResearchInput:
    execution_id: str
    entity_id: str
    entity_aliases: tuple[str, ...]
    vertical: str
    plan_dir: Path
    report: dict[str, Any]
    updated: list[dict[str, Any]]
    qualified_homepage_source: QualifiedHomepageSource
    wiki_page_images: tuple[dict[str, Any], ...]
    prior_image_pool: tuple[dict[str, Any], ...]
    voyage_page_images: tuple[dict[str, Any], ...]
    commons: tuple[dict[str, Any], ...]
    hint_commons: tuple[dict[str, Any], ...]
    wikidata_commons: tuple[dict[str, Any], ...]
    openverse: tuple[dict[str, Any], ...]
    rejected_source_urls: frozenset[str]
    force: bool
    professional_image_specs: tuple[dict[str, Any], ...] = ()
    acquisition_receipt_refs: tuple[str, ...] = ()


def _candidate_sources(spec: HomepageResearchInput) -> list[dict[str, Any]]:
    qualified_source = spec.qualified_homepage_source

    def accept(source: dict[str, Any]) -> dict[str, Any] | None:
        return _accept_source_with_reject_memory(
            spec.report,
            _hydrate_mediawiki_same_source_images(source, entity_id=spec.entity_id),
            entity_id=spec.entity_id,
            lane="homepage",
            vertical=spec.vertical,
            entity_aliases=list(spec.entity_aliases),
            rejected_source_urls=set(spec.rejected_source_urls),
        )

    same_source_images = (
        list(spec.wiki_page_images)
        if qualified_source.provider is HomepageAuthorityProvider.WIKIPEDIA
        else []
    )
    accepted = accept(
        _source(
            source_id=qualified_source.source_id,
            platform=qualified_source.platform,
            url=qualified_source.url,
            source_kind=qualified_source.source_kind,
            source_title=qualified_source.title,
            qualified_authority_title=qualified_source.title,
            category="encyclopedia",
            discovery_provider=qualified_source.discovery_provider,
            match_confidence=1.0,
            evidence_reason=_evidence_reason(
                spec.entity_id,
                "homepage",
                f"frozen qualified {qualified_source.platform} authority",
                "encyclopedia",
            ),
            source_role="primary",
            images=same_source_images,
            image_evidence_mode="same_source" if same_source_images else "",
        )
    )
    return [accepted] if accepted else []


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
    professional_bound = bool(spec.acquisition_receipt_refs)
    if seed_sources and professional_bound:
        media_collections = _independent_homepage_media_collections(
            list(spec.professional_image_specs),
            entity_id=spec.entity_id,
            entity_aliases=list(spec.entity_aliases),
            vertical=spec.vertical,
            report=spec.report,
            limit=1,
        )
    elif seed_sources and not same_source_seeds:
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
            "acquisitionReceiptRefs": list(spec.acquisition_receipt_refs),
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
    elif professional_bound and not media_collections:
        _record_unavailable(
            spec.report,
            entity_id=spec.entity_id,
            lane="homepage",
            reason="frozen professional image assets accepted for entity=0 need>=1",
            code=DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
            recovery=DataRecoveryAction.STOP,
        )
    elif not same_source_seeds and not media_collections:
        # Cold-start policy audits media availability without making it a
        # publication prerequisite. Every downloaded asset still undergoes
        # source, match, and rights auditing in the media closure.
        spec.report.setdefault("homepageMediaAdvisories", []).append(
            {
                "entityId": spec.entity_id,
                "sameSourceImageCount": 0,
                "independentCollectionCount": 0,
            }
        )
    return core_sources
