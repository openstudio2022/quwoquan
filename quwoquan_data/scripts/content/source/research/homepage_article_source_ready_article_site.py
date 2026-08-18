"""Acquire one immutable Article source unit from the governed site frontier."""
from __future__ import annotations

import base64
import json
import re
import urllib.parse
from collections.abc import Mapping
from typing import Any

from core.runtime_policy import active_runtime_policy
from core.source_attribution import canonical_source_attribution

from content.post.article.base_draft import base_draft_readiness
from content.post.article.evidence_text import score_source_markdown
from content.source.fetch_payload import fetch_source_payload
from content.source.research.article_frontier_profile import (
    article_profile_digest,
    article_search_sites,
    resolve_article_source_binding,
)
from content.source.research.article_frontier_contract import ArticleSourceCandidate
from content.source.research.article_source_classification import (
    ArticleSourceClassificationRejected,
    photography_classification,
)
from content.source.research.homepage_article_source_ready_mediawiki import (
    PUBLIC_ACCESS,
    AcquiredSourceReadyCandidate,
    MediaWikiSourceReadyRejected,
    source_ready_sha256,
    source_ready_stable_id,
)
from content.source.research.public_search import discover_article_source_frontier
from content.source.research.qunar_sources import _qunar_travelogue_sources
from content.source.research import network_io
from content.source.research.text_match import (
    _entity_name_variants,
    _title_matches_entity,
)


_SEARCH_FALLBACK_PRIORITY = ("wikivoyage_zh", "ctrip_sight_guide")
_TOPICS = ("旅游攻略", "游记", "玩法", "避坑", "摄影")
_QUNAR_POI_LINK = re.compile(
    r'<a\b[^>]*href=["\'](?P<url>https://(?:touch\.go|touch\.travel)\.qunar\.com/poi/\d+)["\'][^>]*>.*?'
    r'<dt>(?P<title>.*?)</dt>',
    re.I | re.S,
)
_HTML_TAG = re.compile(r"<[^>]+>")


def _entity_ref(planned: Mapping[str, Any]) -> str:
    entity_type = str(planned.get("entityType") or "").strip()
    canonical = str(planned.get("canonicalEntityRef") or "").strip()
    if not canonical.startswith(f"/entity/{entity_type}/"):
        raise MediaWikiSourceReadyRejected(
            "site-frontier candidate canonical entity ref/type drift"
        )
    return canonical


def _article_attribution(
    *, platform: str, source_url: str, terms_url: str, captured_at: str
) -> dict[str, Any]:
    editor = f"{platform}公开页面编辑者"
    return canonical_source_attribution(
        {
            "isOriginal": False,
            "originalCreatorId": None,
            "originalCreatorName": editor,
            "originalCreatorProfileUrl": None,
            "platform": platform,
            "sourcePostUrl": source_url,
            "originalAssetUrl": source_url,
            "attributionText": f"正文参考来源：{platform}（{editor}）",
            "rightsBasis": "factual_reference_only",
            "commercialAuthorizationStatus": "unverified",
            "publicationAdmission": "research_release",
            "authorizationProofUrl": None,
            "termsUrl": terms_url,
            "riskAcceptanceId": None,
            "watermarkStatus": "absent",
            "audioRightsStatus": "no_audio",
            "modelReleaseStatus": "not_required",
            "propertyReleaseStatus": "not_required",
            "collectedAt": captured_at,
            "takedownPolicy": "remove_on_verified_rights_or_source_dispute",
        }
    )


def _candidate_title_is_exact(
    *, site_id: str, title: str, aliases: tuple[str, ...]
) -> bool:
    # Search-result/listing pages are useful discovery evidence but never a
    # source unit. Their body may mention the requested entity among many rows.
    # The same exact-title boundary applies to every fallback provider: a
    # Wikivoyage child district is related to its parent city, but it cannot be
    # relabelled as the parent entity without an explicit governed relation.
    del site_id
    return any(_title_matches_entity(title, alias) for alias in aliases)


def _candidate_batches(
    *,
    entity_ref: str,
    entity_name: str,
    aliases: tuple[str, ...],
    topics: tuple[str, ...] = _TOPICS,
) -> Any:
    """Yield site-direct Qunar candidates before search-based fallbacks.

    Qunar's public JSON search and creator pages are a governed site-level
    frontier.  They avoid making a general search engine the primary source
    selector while retaining the exact per-work entity gate below.
    """

    qunar_sites = article_search_sites(site_ids=frozenset({"qunar_guide"}))
    if qunar_sites:
        site = qunar_sites[0]
        profile_digest = article_profile_digest(site)
        search_url = (
            "https://touch.travel.qunar.com/search?q="
            + urllib.parse.quote(entity_name)
        )
        try:
            search_html = network_io.curl_text(
                search_url,
                timeout=active_runtime_policy().provider_timeouts.qunar_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - provider shard checkpoint
            search_html = ""
            search_error = f"{type(exc).__name__}: {exc}"
        else:
            search_error = ""
        poi_candidates: list[ArticleSourceCandidate] = []
        for index, match in enumerate(_QUNAR_POI_LINK.finditer(search_html), start=1):
            title = _HTML_TAG.sub("", match.group("title")).strip()
            if not any(_title_matches_entity(title, alias) for alias in aliases):
                continue
            poi_candidates.append(
                ArticleSourceCandidate(
                    source_id=f"qunar-poi-direct-{index}",
                    site_id="qunar_guide",
                    platform=str(site.get("platform") or "去哪儿攻略"),
                    category=str(site.get("category") or "travelogue"),
                    canonical_url=match.group("url").replace(
                        "https://touch.go.qunar.com/",
                        "https://touch.travel.qunar.com/",
                    ),
                    title=title,
                    discovery_method="qunar_site_exact_poi_search",
                    relevance_score=0.99,
                    profile_digest=profile_digest,
                    discovery_query=entity_name,
                )
            )
        yield (
            "qunar_guide",
            {
                "schema": "quwoquan_data.article_site_direct_discovery_evidence",
                "entityRef": entity_ref,
                "entityName": entity_name,
                "siteId": "qunar_guide",
                "profileDigest": profile_digest,
                "discoveryMethod": "site_exact_poi_search",
                "searchUrl": search_url,
                "searchResponseContentSha256": source_ready_sha256(
                    search_html.encode("utf-8")
                ),
                "providerError": search_error,
                "candidates": [
                    candidate.as_evidence() for candidate in poi_candidates
                ],
            },
            tuple(poi_candidates),
        )

        try:
            sources = _qunar_travelogue_sources(
                entity_name,
                entity_aliases=aliases,
                # A source-ready capsule needs one strong immutable work, not
                # a creator catalog.  Keep one spare candidate for per-work
                # quality rejection while avoiding a long six-work crawl on
                # the latency-critical M100 producer path.
                limit=2,
            )
        except Exception as exc:  # noqa: BLE001 - provider shard checkpoint
            sources = []
            error = f"{type(exc).__name__}: {exc}"
        else:
            error = ""
        candidates: list[ArticleSourceCandidate] = []
        for index, source in enumerate(sources, start=1):
            url = str(source.get("url") or "").strip()
            title = str(source.get("title") or "").strip()
            if not url or not title:
                continue
            candidates.append(
                ArticleSourceCandidate(
                    source_id=str(source.get("source_id") or f"qunar-direct-{index}"),
                    site_id="qunar_guide",
                    platform=str(source.get("platform") or site.get("platform") or "去哪儿攻略"),
                    category=str(source.get("category") or site.get("category") or "travelogue"),
                    canonical_url=url,
                    title=title,
                    discovery_method=str(source.get("discoveryProvider") or "qunar_site_direct"),
                    relevance_score=float(source.get("matchConfidence") or 0.0),
                    profile_digest=profile_digest,
                    discovery_query=entity_name,
                )
            )
        yield (
            "qunar_guide",
            {
                "schema": "quwoquan_data.article_site_direct_discovery_evidence",
                "entityRef": entity_ref,
                "entityName": entity_name,
                "siteId": "qunar_guide",
                "profileDigest": profile_digest,
                "discoveryMethod": "site_public_api_then_creator_public_works",
                "providerError": error,
                "candidates": [candidate.as_evidence() for candidate in candidates],
            },
            tuple(candidates),
        )

    for site_id in _SEARCH_FALLBACK_PRIORITY:
        outcome = discover_article_source_frontier(
            entity_name,
            entity_aliases=aliases,
            topics=topics,
            limit=6,
            site_ids=frozenset({site_id}),
        )
        yield site_id, outcome.as_evidence(), outcome.candidates


def acquire_article_site_source_ready_candidate(
    planned: Mapping[str, Any],
    *,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
    captured_at: str,
) -> AcquiredSourceReadyCandidate:
    """Discover site-first, fetch exact bytes, and return one text-only source."""

    entity_ref = _entity_ref(planned)
    entity_name = str(planned.get("candidateName") or "").strip()
    if not entity_name:
        raise MediaWikiSourceReadyRejected("site-frontier candidate name is missing")
    aliases = tuple(_entity_name_variants(entity_name))
    seed = planned.get("seed")
    seed = seed if isinstance(seed, Mapping) else {}
    article_category = str(seed.get("articleCategory") or "").strip()
    topics = ("摄影",) if article_category == "photography" else _TOPICS
    rejection_reasons: list[str] = []
    for site_id, discovery, discovered_candidates in _candidate_batches(
        entity_ref=entity_ref,
        entity_name=entity_name,
        aliases=aliases,
        topics=topics,
    ):
        for discovered in discovered_candidates:
            if not _candidate_title_is_exact(
                site_id=site_id, title=discovered.title, aliases=aliases
            ):
                rejection_reasons.append(f"{site_id}: non-exact listing title")
                continue
            site = resolve_article_source_binding(
                discovered.canonical_url,
                site_id=site_id,
                profile_digest=discovered.profile_digest,
            )
            profile = site.get("siteCrawlProfile")
            profile = profile if isinstance(profile, Mapping) else {}
            source = discovered.as_source()
            source["extractor"] = str(
                profile.get("extractor") or site.get("extractor") or ""
            )
            try:
                payload = fetch_source_payload(
                    discovered.canonical_url,
                    source=source,
                    include_page_images=False,
                    entity_id=entity_name,
                )
            except Exception as exc:  # noqa: BLE001 - object-level typed reject
                rejection_reasons.append(
                    f"{site_id}: fetch {type(exc).__name__}: {exc}"
                )
                continue
            body_text = str(payload.get("text") or "").strip()
            readiness = base_draft_readiness(body_text, publish_media_mode="text_only")
            assessment = score_source_markdown(
                site_id, body_text, entity_name=entity_name
            )
            if not readiness["ready"] or assessment.quality == "Reject":
                rejection_reasons.append(
                    f"{site_id}: article body quality blocked "
                    f"(chars={readiness['effectiveChars']}, quality={assessment.quality})"
                )
                continue
            source_classification: dict[str, Any] | None = None
            if article_category:
                try:
                    source_classification = photography_classification(
                        entity_ref=entity_ref,
                        entity_name=entity_name,
                        title=discovered.title,
                        body=body_text,
                        discovery_query=discovered.discovery_query or entity_name,
                    )
                except ArticleSourceClassificationRejected as exc:
                    rejection_reasons.append(f"{site_id}: {exc}")
                    continue
            raw_body = bytes(payload.get("htmlBytes") or b"")
            raw_evidence = json.dumps(
                {
                    "schema": "quwoquan_data.article_site_source_ready_raw_evidence",
                    "entityRef": entity_ref,
                    "sourceUrl": discovered.canonical_url,
                    "finalUrl": str(
                        (payload.get("runtime") or {}).get("fetchFinalUrl")
                        or discovered.canonical_url
                    ),
                    "htmlContentSha256": source_ready_sha256(raw_body),
                    "htmlBytesBase64": base64.b64encode(raw_body).decode("ascii"),
                    "runtime": dict(payload.get("runtime") or {}),
                    "discovery": discovery,
                    "sourceClassification": source_classification,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            body = body_text.encode("utf-8")
            body_sha = source_ready_sha256(body)
            source_unit_id = source_ready_stable_id(
                "article-source", entity_ref, discovered.canonical_url, body_sha
            )
            source_unit_ref = f"sources/{source_unit_id}"
            body_ref = f"{source_unit_ref}/source.md"
            source_unit_digest = source_ready_sha256(
                (
                    discovered.canonical_url
                    + "\n"
                    + body_sha
                    + "\n"
                    + source_ready_sha256(raw_evidence)
                ).encode("utf-8")
            )
            candidate_id = source_ready_stable_id(
                "article", entity_ref, source_unit_digest, source_revision
            )
            platform = str(site.get("platform") or discovered.platform)
            source_kind = str(site.get("category") or discovered.category)
            extractor = str(profile.get("extractor") or site.get("extractor") or "")
            attribution = _article_attribution(
                platform=platform,
                source_url=discovered.canonical_url,
                terms_url=str(profile.get("termsUrl") or ""),
                captured_at=captured_at,
            )
            candidate = {
                "candidateId": candidate_id,
                "entityRef": entity_ref,
                "observedEntityRef": entity_ref,
                "sourceRevision": source_revision,
                "sourceDigest": source_digest,
                "entityCatalogDigest": entity_catalog_digest,
                "sourceAttribution": attribution,
                "publishMediaMode": "text_only",
                "sourceUnitId": source_unit_id,
                "sourceUnitRef": source_unit_ref,
                "sourceUnitDigest": source_unit_digest,
                "articleSiteId": site_id,
                "sourceDiscoveryProfileDigest": discovered.profile_digest,
                "sourceKind": source_kind,
                "platform": platform,
                "extractor": extractor,
                "policyRevision": "article-source-registry-v1",
                "sourceUrl": discovered.canonical_url,
                "capturedAt": captured_at,
                "bodyEvidenceRef": body_ref,
                "bodyContentSha256": body_sha,
                "accessEvidence": dict(PUBLIC_ACCESS),
                "assets": [],
            }
            if source_classification is not None:
                candidate.update(
                    {
                        "articleCategory": source_classification["articleCategory"],
                        "writingIntent": source_classification["writingIntent"],
                        "topicTagRefs": list(source_classification["topicTagRefs"]),
                        "sourceClassification": source_classification,
                    }
                )
            source_unit = {
                "sourceUnitId": source_unit_id,
                "sourceUnitRef": source_unit_ref,
                "sourceUnitDigest": source_unit_digest,
                "sourceUrl": discovered.canonical_url,
                "sourceKind": source_kind,
                "extractor": extractor,
                "resolvedTitle": discovered.title,
                "bodyEvidenceRef": body_ref,
                "bodyContentSha256": body_sha,
                "accessEvidence": dict(PUBLIC_ACCESS),
                "qualityStatus": "passed",
                "qualityScore": assessment.score,
                "qualityReasons": list(assessment.reasons),
            }
            if source_classification is not None:
                source_unit.update(
                    {
                        "articleCategory": source_classification["articleCategory"],
                        "writingIntent": source_classification["writingIntent"],
                        "topicTagRefs": list(source_classification["topicTagRefs"]),
                        "sourceClassification": source_classification,
                    }
                )
            return AcquiredSourceReadyCandidate(
                carrier="article",
                candidate=candidate,
                source_unit=source_unit,
                body=body,
                raw_evidence=raw_evidence,
                assets=(),
                source_selection_origin="site_frontier",
            )
    summary = "; ".join(rejection_reasons[:8]) or "no governed site candidate"
    raise MediaWikiSourceReadyRejected(
        f"article site frontier produced no source-ready detail page: {summary}"
    )


__all__ = ["acquire_article_site_source_ready_candidate"]
