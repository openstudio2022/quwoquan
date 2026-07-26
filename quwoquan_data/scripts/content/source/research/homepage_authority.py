"""Canonical encyclopedia authority discovery for homepage planning and selection."""
from __future__ import annotations

from dataclasses import dataclass

from core.baike_source_contract import HOMEPAGE_SOURCE_POLICY_REVISION, SOURCE_EXTRACTORS
from core.data_issue import DataIssueCode, DataIssueError
from content.homepage.homepage_text import homepage_base_draft_readiness
from content.source.research.homepage_text_quality import (
    HomepageTextQualityIssue,
    assess_homepage_text_quality,
)
from content.source.research.baidu_baike import (
    BaiduBaikeResolution,
    resolve_baidu_baike_page,
)
from content.source.research.baike_com import (
    BaikePageResolution,
    resolve_toutiao_baike_page,
)
from content.source.research.wiki_core import _wiki_title_for_entity, _wiki_url
from content.source.fetch_payload import fetch_source_payload
from content.source.contracts import (
    HomepageAuthorityProvider,
    QualifiedHomepageSource,
)


@dataclass(frozen=True, slots=True)
class HomepageAuthorityCandidate:
    provider: HomepageAuthorityProvider
    title: str
    url: str

    @property
    def qualified_source(self) -> QualifiedHomepageSource:
        return QualifiedHomepageSource(
            provider=self.provider,
            title=self.title,
            url=self.url,
        )

    def source_metadata(self) -> dict[str, str]:
        source = self.qualified_source
        return {
            "source_id": source.source_id,
            "sourceKind": source.source_kind,
            "sourceTitle": self.title,
            # The resolved provider title is the only title evidence available
            # before the source unit exists.  Preserve it explicitly so the
            # shared homepage judge can make the same exact/alias decision for
            # all admitted encyclopedia providers, not only MediaWiki URLs.
            "resolvedTitle": self.title,
            "sourceRole": "primary",
            "researchLane": "homepage",
            "url": self.url,
            "canonicalUrl": self.url,
            "extractor": SOURCE_EXTRACTORS[source.source_kind],
            "policyRevision": HOMEPAGE_SOURCE_POLICY_REVISION,
        }


@dataclass(frozen=True, slots=True)
class HomepageAuthorityQualification:
    accepted: bool
    qualified_source: QualifiedHomepageSource | None
    rejection_code: DataIssueCode | None

    def __post_init__(self) -> None:
        if self.accepted != (self.qualified_source is not None):
            raise ValueError("qualification acceptance and qualified source disagree")
        if self.accepted != (self.rejection_code is None):
            raise ValueError("qualification acceptance and rejection code disagree")


@dataclass(frozen=True, slots=True)
class HomepageAuthorityDiscovery:
    """Resolved primary-authority candidates for one canonical entity."""

    wikipedia_title: str
    wikipedia_url: str
    baidu_baike: BaiduBaikeResolution | None
    toutiao_baike: BaikePageResolution | None

    @property
    def available(self) -> bool:
        return bool(
            self.wikipedia_url or self.baidu_baike is not None or self.toutiao_baike is not None
        )

    @property
    def candidates(self) -> tuple[HomepageAuthorityCandidate, ...]:
        candidates: list[HomepageAuthorityCandidate] = []
        if self.wikipedia_url:
            candidates.append(
                HomepageAuthorityCandidate(
                    provider=HomepageAuthorityProvider.WIKIPEDIA,
                    title=self.wikipedia_title,
                    url=self.wikipedia_url,
                )
            )
        if self.baidu_baike is not None:
            candidates.append(
                HomepageAuthorityCandidate(
                    provider=HomepageAuthorityProvider.BAIDU_BAIKE,
                    title=self.baidu_baike.title,
                    url=self.baidu_baike.url,
                )
            )
        if self.toutiao_baike is not None:
            candidates.append(
                HomepageAuthorityCandidate(
                    provider=HomepageAuthorityProvider.TOUTIAO_BAIKE,
                    title=self.toutiao_baike.title,
                    url=self.toutiao_baike.url,
                )
            )
        return tuple(candidates)


def discover_homepage_authority(
    entity_id: str,
    *,
    entity_aliases: tuple[str, ...] = (),
    geo_context_terms: tuple[str, ...] = (),
    wikipedia_title: str | None = None,
    include_external: bool = True,
) -> HomepageAuthorityDiscovery:
    """Resolve only authority candidates; source fetching remains a later stage."""
    canonical_name = str(entity_id).strip()
    if not canonical_name:
        raise ValueError("entity_id must be non-empty")
    aliases = tuple(str(alias).strip() for alias in entity_aliases if str(alias).strip())
    resolved_title = (
        str(wikipedia_title).strip()
        if wikipedia_title is not None
        else _wiki_title_for_entity(
            "zh.wikipedia.org",
            canonical_name,
            entity_aliases=aliases,
        )
    )
    baidu_baike = None
    toutiao_baike = None
    if include_external:
        baidu_baike = resolve_baidu_baike_page(
            canonical_name,
            entity_aliases=aliases,
            geo_context_terms=geo_context_terms,
        )
        toutiao_baike = resolve_toutiao_baike_page(
            canonical_name,
            entity_aliases=aliases,
            geo_context_terms=geo_context_terms,
        )
    return HomepageAuthorityDiscovery(
        wikipedia_title=resolved_title,
        wikipedia_url=_wiki_url("zh.wikipedia.org", resolved_title),
        baidu_baike=baidu_baike,
        toutiao_baike=toutiao_baike,
    )


def qualify_homepage_authority_content(
    entity_id: str,
    *,
    entity_aliases: tuple[str, ...] = (),
    geo_context_terms: tuple[str, ...] = (),
) -> HomepageAuthorityQualification:
    """Prove that a primary encyclopedia candidate can seed a homepage draft."""
    wikipedia_discovery = discover_homepage_authority(
        entity_id,
        entity_aliases=entity_aliases,
        geo_context_terms=geo_context_terms,
        include_external=False,
    )
    candidates = list(wikipedia_discovery.candidates)
    seen_urls = {candidate.url for candidate in candidates}
    readable_candidate_seen = False
    quality_issues_seen: set[HomepageTextQualityIssue] = set()

    def attempt(candidates_to_check: tuple[HomepageAuthorityCandidate, ...]) -> QualifiedHomepageSource | None:
        nonlocal readable_candidate_seen
        for candidate in candidates_to_check:
            try:
                payload = fetch_source_payload(
                    candidate.url,
                    source=candidate.source_metadata(),
                    include_page_images=False,
                )
            except (DataIssueError, RuntimeError, OSError):
                continue
            readable_candidate_seen = True
            readiness = homepage_base_draft_readiness(
                candidate.source_metadata(),
                str(payload.get("text") or ""),
                entity_name=entity_id,
                aliases=entity_aliases,
            )
            quality_verdict = assess_homepage_text_quality(
                str(payload.get("text") or ""),
                entity_id,
                # ``homepage_base_draft_readiness`` owns factual sufficiency.
                # This companion guard only rejects malformed, redirect, or
                # disambiguation payloads; applying its independent sentence
                # count here would create two conflicting admission contracts.
                require_fact_ready=False,
            )
            if quality_verdict.issue is not None:
                quality_issues_seen.add(quality_verdict.issue)
            if bool(readiness.get("ready")) and quality_verdict.accepted:
                return candidate.qualified_source
        return None

    qualified = attempt(tuple(candidates))
    if qualified is not None:
        return HomepageAuthorityQualification(
            accepted=True,
            qualified_source=qualified,
            rejection_code=None,
        )

    external_discovery = discover_homepage_authority(
        entity_id,
        entity_aliases=entity_aliases,
        geo_context_terms=geo_context_terms,
        wikipedia_title=wikipedia_discovery.wikipedia_title,
        include_external=True,
    )
    external_candidates = tuple(
        candidate
        for candidate in external_discovery.candidates
        if candidate.url not in seen_urls
    )
    candidates.extend(external_candidates)
    qualified = attempt(external_candidates)
    if qualified is not None:
        return HomepageAuthorityQualification(
            accepted=True,
            qualified_source=qualified,
            rejection_code=None,
        )
    if not candidates:
        return HomepageAuthorityQualification(
            accepted=False,
            qualified_source=None,
            rejection_code=DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING,
        )
    if quality_issues_seen.intersection(
        {
            HomepageTextQualityIssue.REDIRECT,
            HomepageTextQualityIssue.DISAMBIGUATION,
        }
    ):
        return HomepageAuthorityQualification(
            accepted=False,
            qualified_source=None,
            rejection_code=DataIssueCode.SOURCE_PAGE_TYPE_INVALID,
        )
    return HomepageAuthorityQualification(
        accepted=False,
        qualified_source=None,
        rejection_code=(
            DataIssueCode.SOURCE_CONTENT_INCOMPLETE
            if readable_candidate_seen
            else DataIssueCode.SOURCE_UNREADABLE
        ),
    )


__all__ = [
    "HomepageAuthorityCandidate",
    "HomepageAuthorityDiscovery",
    "HomepageAuthorityQualification",
    "discover_homepage_authority",
    "qualify_homepage_authority_content",
]
