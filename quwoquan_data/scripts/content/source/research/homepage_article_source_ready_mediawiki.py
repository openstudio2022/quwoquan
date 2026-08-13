"""Acquire one homepage/article source-ready candidate from public MediaWiki."""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
import urllib.parse
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.content_source_registry import resolve_source_class
from core.image_rules import pixel_size_issue
from core.image_safety import STATUS_SAFE, assess_image
from core.runtime_policy import active_runtime_policy

from content.post.article.evidence_text import score_source_markdown
from content.source.contracts import MediaProvenance
from content.source.fetch_payload import fetch_source_payload
from content.source.mediawiki_page import fetch_mediawiki_page_bundle_for_url
from content.source.research import network_io
from content.source.research.article_frontier_profile import (
    article_profile_digest,
    article_search_sites,
    resolve_article_source_binding,
)
from content.source.research.baike_com import resolve_toutiao_baike_page
from content.source.research.homepage_article_source_ready_wikidata import (
    wikidata_structured_fact,
)
from content.source.research.homepage_structured_fact_text import (
    extract_structured_fact_from_text,
)
from content.source.research.homepage_article_source_attribution import (
    encyclopedia_source_attribution,
)
from content.source.research.homepage_text_quality import (
    assess_homepage_text_quality,
)
from content.source.research.image_search_providers import (
    commons_images_for_entity,
    openverse_images_for_entity,
    wikidata_commons_images_for_entity,
)
from content.source.research.source_quality import _license_allows_app_publish
from content.source.research.wiki_common import _canonical_terms_url
from content.source.research.wiki_media import _mediawiki_page_images

PUBLIC_ACCESS = {
    "anonymousPublicAccess": True,
    "loginRequired": False,
    "captchaRequired": False,
    "paywallRequired": False,
    "drmProtected": False,
    "accessControlBypass": False,
}
_MEDIAWIKI_HTTP_TIMEOUT_SECONDS = (
    active_runtime_policy().provider_timeouts.mediawiki_seconds
)


class MediaWikiSourceReadyRejected(ValueError):
    """One object-level source candidate was unavailable or not admissible."""


@dataclass(frozen=True, slots=True)
class AcquiredAsset:
    body: bytes
    document: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AcquiredSourceReadyCandidate:
    carrier: str
    candidate: dict[str, Any]
    source_unit: dict[str, Any]
    body: bytes
    raw_evidence: bytes
    assets: tuple[AcquiredAsset, ...]
    source_selection_origin: str = "coverage_source"


def _sha256(body: bytes) -> str:
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _stable_id(prefix: str, *values: object, size: int = 20) -> str:
    raw = "\n".join(str(value) for value in values).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(raw).hexdigest()[:size]}"


def source_ready_sha256(body: bytes) -> str:
    return _sha256(body)


def source_ready_stable_id(prefix: str, *values: object, size: int = 20) -> str:
    return _stable_id(prefix, *values, size=size)


def _entity_ref(planned: Mapping[str, Any]) -> str:
    raw_type = str(planned.get("entityType") or "").strip()
    parts = raw_type.split("/", 1)
    canonical = str(planned.get("canonicalEntityRef") or "").strip()
    expected_prefix = f"/entity/{raw_type}/"
    if canonical:
        if len(parts) != 2 or not all(parts) or not canonical.startswith(expected_prefix):
            raise MediaWikiSourceReadyRejected(
                "coverage candidate canonical entity ref/type drift"
            )
        return canonical
    name = str(planned.get("candidateName") or "").strip()
    if len(parts) != 2 or not all(parts) or not name or "/" in name:
        raise MediaWikiSourceReadyRejected(
            "coverage candidate lacks canonical entity type/name"
        )
    return f"/entity/{parts[0]}/{parts[1]}/{name}"


def _baike_structured_fact(
    *,
    entity_name: str,
    geo_context_terms: tuple[str, ...],
) -> tuple[str, object, str, str, float, bytes] | None:
    """Discover one governed Baike encyclopedia fact for a Wikipedia body.

    The narrative body stays bound to the already qualified Wikipedia page;
    only the structured fact rides an independent encyclopedia fact source,
    exactly as ``structuredFactsPolicy`` splits the two evidence tracks.
    """

    try:
        resolution = resolve_toutiao_baike_page(
            entity_name,
            geo_context_terms=geo_context_terms,
        )
        if resolution is None:
            return None
        payload = fetch_source_payload(
            resolution.url,
            source={
                "sourceKind": "toutiao_baike",
                "extractor": "toutiao_baike_html",
                "fetchable": True,
            },
            include_page_images=False,
            entity_id=entity_name,
        )
    except (OSError, RuntimeError, TypeError, ValueError):
        return None
    text = str(payload.get("text") or "").strip()
    if not text:
        return None
    extracted = extract_structured_fact_from_text(text)
    if extracted is None:
        return None
    field, value = extracted
    raw_body = payload.get("htmlBytes")
    raw_body = bytes(raw_body) if isinstance(raw_body, bytes | bytearray) else b""
    raw = json.dumps(
        {
            "schema": "quwoquan_data.homepage_baike_fact_source_raw_evidence",
            "entityName": entity_name,
            "resolvedTitle": resolution.title,
            "matchedTerm": resolution.matched_term,
            "matchConfidence": resolution.match_confidence,
            "sourceUrl": resolution.url,
            "bodyText": text,
            "htmlContentSha256": _sha256(raw_body),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return field, value, "toutiao_baike", resolution.url, 0.8, raw


def _structured_fact_material(
    wikitext: str,
    *,
    rendered_text: str,
    resolved_title: str,
    source_url: str,
    entity_name: str = "",
    geo_context_terms: tuple[str, ...] = (),
) -> tuple[str, object, str, str, float, bytes | None]:
    official_url = ""
    for match in re.finditer(
        r"(?im)^\|\s*(?:website|homepage|官方网站|官方網站)\s*=\s*(.+)$",
        wikitext,
    ):
        url_match = re.search(r"https://[^\s|}\]<>]+", match.group(1))
        if url_match:
            official_url = url_match.group(0).rstrip(".,;，。；")
            break
    field = ""
    value: object = None
    if official_url:
        field = "officialWebsite"
        value = official_url
    else:
        altitude_match = re.search(
            r"(?im)^\|\s*(?:海拔|elevation(?:_m)?)\s*=\s*"
            r"(?:\{\{[^|}]+\|)?\s*([0-9]{1,4})(?:\.[0-9]+)?\s*(?:米|m)?",
            wikitext,
        )
        if altitude_match:
            altitude = int(altitude_match.group(1))
            if -500 <= altitude <= 9000:
                field = "altitudeMeters"
                value = altitude
    if not field:
        extracted = extract_structured_fact_from_text(rendered_text)
        if extracted is not None:
            field, value = extracted
    if field:
        return field, value, "wikipedia", source_url, 0.9, None
    wikidata = wikidata_structured_fact(resolved_title)
    if wikidata is not None:
        return wikidata
    baike = _baike_structured_fact(
        entity_name=entity_name or resolved_title,
        geo_context_terms=geo_context_terms,
    )
    if baike is not None:
        return baike
    raise MediaWikiSourceReadyRejected(
        "homepage source lacks an immutable structured fact"
    )


def _article_site(source_url: str) -> tuple[dict[str, object], str]:
    sites = {
        str(site.get("siteId") or ""): site
        for site in article_search_sites(site_ids=frozenset({"wikipedia_zh"}))
    }
    site = sites.get("wikipedia_zh")
    if site is None:
        raise MediaWikiSourceReadyRejected(
            "wikipedia_zh is not an admitted article source profile"
        )
    digest = article_profile_digest(site)
    resolve_article_source_binding(
        source_url,
        site_id="wikipedia_zh",
        profile_digest=digest,
    )
    return site, digest


def _asset_extension(mime_type: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }.get(mime_type, "")


def acquire_open_image_assets(
    image_rows: list[dict[str, Any]],
    *,
    source_unit_ref: str,
    roles: tuple[str, ...],
    captured_at: str,
) -> tuple[AcquiredAsset, ...]:
    acquired: list[AcquiredAsset] = []
    seen_content: set[str] = set()
    for raw in image_rows:
        if len(acquired) >= len(roles):
            break
        original_url = str(raw.get("url") or "").strip()
        license_name = str(raw.get("license") or "")
        terms_url = _canonical_terms_url(
            raw.get("termsUrl"),
            license_name=license_name,
            source_url=raw.get("sourceUrl"),
        )
        if not _license_allows_app_publish(license_name, terms_url):
            continue
        response = network_io.fetch_http(
            original_url,
            timeout=_MEDIAWIKI_HTTP_TIMEOUT_SECONDS,
        )
        if not response.ok or not response.body:
            continue
        content_sha = _sha256(response.body)
        if content_sha in seen_content:
            continue
        seen_content.add(content_sha)
        # Reaching this point already proves that the exact license/terms pair
        # is admitted for App publication.  Freeze that decision in the
        # physical source capsule instead of forcing a later execution to
        # infer usage scope from live policy.
        usage_scope = str(raw.get("usageScope") or "app_publish").strip()
        model_release_status = str(
            raw.get("modelReleaseStatus") or "not_required"
        ).strip()
        provenance = MediaProvenance.from_mapping(
            {
                **raw,
                "usageScope": usage_scope,
                "modelReleaseStatus": model_release_status,
            },
            vertical="travel",
        )
        with tempfile.NamedTemporaryFile(suffix=".img") as handle:
            handle.write(response.body)
            handle.flush()
            verdict = assess_image(Path(handle.name), require_ocr=True)
        if verdict.status != STATUS_SAFE or verdict.faces != 0 or verdict.has_watermark:
            continue
        from core.image_decode import probe_image_bytes

        probe = probe_image_bytes(response.body)
        if not probe.succeeded or pixel_size_issue(
            probe.width, probe.height, asset_id=content_sha[-12:]
        ):
            continue
        extension = _asset_extension(probe.mime_type)
        if not extension:
            continue
        role = roles[len(acquired)]
        platform = str(raw.get("platform") or "Wikimedia Commons").strip()
        provider = "openverse" if platform == "Openverse" else "wikimedia_commons"
        asset_id = _stable_id(provider, content_sha, role)
        asset_ref = f"{source_unit_ref}/assets/{content_sha.removeprefix('sha256:')}{extension}"
        rights_status = provenance.rights_audit_status.value
        rights_issues = list(provenance.rights_audit_issues)
        acquired.append(
            AcquiredAsset(
                body=response.body,
                document={
                    "assetId": asset_id,
                    "role": role,
                    "assetRef": asset_ref,
                    "originalAssetUrl": original_url,
                    "sourcePageUrl": str(raw.get("sourceUrl") or original_url),
                    "platform": platform,
                    "provider": provider,
                    "creator": provenance.creator,
                    "capturedAt": captured_at,
                    "contentSha256": content_sha,
                    "license": provenance.license_name,
                    "termsUrl": terms_url,
                    "authorizationProof": str(raw.get("authorizationProof") or ""),
                    "usageScope": usage_scope,
                    "modelReleaseStatus": model_release_status,
                    "authorizationRequired": rights_status != "verified",
                    "rightsStatus": rights_status,
                    "rightsIssues": rights_issues,
                    "acquisitionStatus": "acquired",
                    "distributionDecision": "research_allowed",
                    "qualityStatus": "passed",
                    "safetyStatus": "passed",
                    "generated": False,
                    "width": probe.width,
                    "height": probe.height,
                    "byteCount": len(response.body),
                    "fileSha256": content_sha,
                    "safetyEvidence": {
                        "status": verdict.status,
                        "faces": verdict.faces,
                        "hasWatermark": verdict.has_watermark,
                        "textAreaRatio": round(verdict.text_area_ratio, 4),
                        "reasons": list(verdict.reasons),
                        "backends": list(verdict.backends),
                    },
                    "accessEvidence": dict(PUBLIC_ACCESS),
                },
            )
        )
    if len(acquired) != len(roles):
        raise MediaWikiSourceReadyRejected(
            f"source page lacks {len(roles)} safe open-license original images"
        )
    return tuple(acquired)


def acquire_mediawiki_source_ready_candidate(
    planned: Mapping[str, Any],
    *,
    carrier: str,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
    captured_at: str,
) -> AcquiredSourceReadyCandidate:
    """Fetch, review and freeze one exact public MediaWiki source candidate."""

    if carrier not in {"homepage", "article"}:
        raise ValueError(f"unsupported source-ready carrier: {carrier}")
    source = planned.get("source")
    source = source if isinstance(source, Mapping) else {}
    source_url = str(source.get("sourceUrl") or "").strip()
    source_lookup_title = str(source.get("resolvedTitle") or "").strip()
    if not source_lookup_title:
        raise MediaWikiSourceReadyRejected(
            "coverage candidate lacks exact resolved source title"
        )
    if source.get("sourceKind") != "wikipedia" and carrier == "article":
        source_url = (
            "https://zh.wikipedia.org/wiki/"
            + urllib.parse.quote(source_lookup_title.replace(" ", "_"), safe="()_-.")
        )
    if not source_url.startswith("https://zh.wikipedia.org/wiki/"):
        raise MediaWikiSourceReadyRejected(
            "current producer only accepts coverage-qualified zh.wikipedia pages"
        )
    entity_ref = _entity_ref(planned)
    bundle = fetch_mediawiki_page_bundle_for_url(source_url, include_images=True)
    if (
        bundle is None
        or bundle.page_id < 1
        or bundle.revision_id < 1
        or bundle.resolved_title != source_lookup_title
    ):
        raise MediaWikiSourceReadyRejected("MediaWiki page identity drift")
    body = bundle.rendered_text.strip().encode("utf-8")
    if not body:
        raise MediaWikiSourceReadyRejected("MediaWiki rendered body is empty")
    fact_material: tuple[str, object, str, str, float, bytes | None] | None = None
    raw_evidence = bundle.raw.encode("utf-8")
    if carrier == "homepage":
        verdict = assess_homepage_text_quality(
            bundle.rendered_text, source_lookup_title, require_fact_ready=False
        )
        if not verdict.accepted:
            raise MediaWikiSourceReadyRejected(
                f"homepage body quality blocked: {verdict.issue}"
            )
        fact_material = _structured_fact_material(
            bundle.wikitext,
            rendered_text=bundle.rendered_text,
            resolved_title=bundle.resolved_title,
            source_url=source_url,
            entity_name=str(planned.get("candidateName") or ""),
            geo_context_terms=tuple(
                term
                for term in (
                    str(planned.get(scope) or "").strip()
                    for scope in ("province", "city", "district")
                )
                if term
            ),
        )
        if fact_material[-1] is not None:
            external_raw_key = (
                "baikeRaw" if fact_material[2] == "toutiao_baike" else "wikidataRaw"
            )
            raw_evidence = json.dumps(
                {
                    "mediawikiRaw": bundle.raw,
                    external_raw_key: fact_material[-1].decode("utf-8"),
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        quality_score = 1
        quality_reasons = ["homepage_text_quality_passed"]
    else:
        assessment = score_source_markdown(
            "wikipedia_zh", bundle.rendered_text, entity_name=source_lookup_title
        )
        if assessment.quality == "Reject":
            raise MediaWikiSourceReadyRejected(
                "article body quality blocked: " + ",".join(assessment.reasons)
            )
        quality_score = assessment.score
        quality_reasons = list(assessment.reasons)
    source_unit_id = _stable_id(
        f"{carrier}-source", entity_ref, source_url, bundle.revision_id
    )
    source_unit_ref = f"sources/{source_unit_id}"
    body_ref = f"{source_unit_ref}/source.md"
    body_sha = _sha256(body)
    image_rows = _mediawiki_page_images(
        "zh.wikipedia.org",
        bundle.resolved_title,
        entity_id=source_lookup_title,
        limit=12,
    )
    if any(
        int(row.get("pageRevisionId") or 0) != bundle.revision_id
        or str(row.get("pageContentSha256") or "") != bundle.content_sha256
        for row in image_rows
    ):
        raise MediaWikiSourceReadyRejected(
            "MediaWiki page/image evidence changed during acquisition"
        )
    roles = ("hero",) if carrier == "homepage" else ("cover", "body")
    if len(image_rows) < (6 if carrier == "article" else 1):
        supplement = [
            *wikidata_commons_images_for_entity(
                bundle.resolved_title,
                entity_id=source_lookup_title,
                limit=8,
            ),
            *commons_images_for_entity(source_lookup_title, limit=8),
            *openverse_images_for_entity(source_lookup_title, limit=8),
        ]
        seen_urls = {str(row.get("url") or "") for row in image_rows}
        for row in supplement:
            url = str(row.get("url") or "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            image_rows.append(row)
    try:
        assets = acquire_open_image_assets(
            image_rows,
            source_unit_ref=source_unit_ref,
            roles=roles,
            captured_at=captured_at,
        )
    except MediaWikiSourceReadyRejected:
        if carrier != "article":
            raise
        assets = ()
    publish_media_mode = (
        "illustrated" if carrier == "homepage" or len(assets) >= 2 else "text_only"
    )
    source_unit_digest = _sha256(
        (source_url + "\n" + str(bundle.revision_id) + "\n" + body_sha + "\n")
        .encode("utf-8")
        + _sha256(raw_evidence).encode("utf-8")
        + "\n".join(asset.document["contentSha256"] for asset in assets).encode(
            "utf-8"
        )
    )
    candidate_id = _stable_id(
        carrier, entity_ref, source_unit_digest, source_revision
    )
    common = {
        "candidateId": candidate_id,
        "entityRef": entity_ref,
        "observedEntityRef": entity_ref,
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
        "sourceAttribution": encyclopedia_source_attribution(
            source_kind="wikipedia",
            source_url=source_url,
            captured_at=captured_at,
        ),
    }
    if carrier == "homepage":
        assert fact_material is not None
        field, value, source_id, fact_source_url, confidence, external_raw = fact_material
        evidence_ref = (
            f"raw/homepage/{candidate_id}.json" if external_raw is not None else body_ref
        )
        evidence_sha = _sha256(raw_evidence) if external_raw is not None else body_sha
        structured = {
            field: value,
            "factSources": [{
                "field": field,
                "sourceId": source_id,
                "sourceClass": resolve_source_class(source_id=source_id),
                "sourceUrl": fact_source_url,
                "observedAt": captured_at,
                "confidence": confidence,
            }],
        }
        fact_evidence = [{
            "field": field,
            "sourceId": source_id,
            "sourceUrl": fact_source_url,
            "evidenceRef": evidence_ref,
            "contentSha256": evidence_sha,
            "accessEvidence": dict(PUBLIC_ACCESS),
        }]
        hero = dict(assets[0].document)
        hero.pop("role")
        for field in ("width", "height", "byteCount", "fileSha256", "safetyEvidence"):
            hero.pop(field)
        hero.update(
            {
                "entityRef": entity_ref,
                "observedEntityRef": entity_ref,
                "sourceUnitRef": source_unit_ref,
                "sourceUnitDigest": source_unit_digest,
            }
        )
        candidate = {
            **common,
            "primarySource": {
                "sourceUnitId": source_unit_id,
                "sourceUnitRef": source_unit_ref,
                "sourceUnitDigest": source_unit_digest,
                "sourceKind": "wikipedia",
                "platform": "维基百科",
                "extractor": "wikipedia_api",
                "policyRevision": "encyclopedia-primary",
                "sourceUrl": source_url,
                "capturedAt": captured_at,
                "bodyEvidenceRef": body_ref,
                "bodyContentSha256": body_sha,
                "accessEvidence": dict(PUBLIC_ACCESS),
            },
            "structuredFacts": structured,
            "factEvidence": fact_evidence,
            "factConflicts": [],
            "hero": hero,
        }
    else:
        site, profile_digest = _article_site(source_url)
        candidate_assets: list[dict[str, Any]] = []
        for asset in assets:
            row = dict(asset.document)
            for field in (
                "width",
                "height",
                "byteCount",
                "fileSha256",
                "safetyEvidence",
                "accessEvidence",
                "usageScope",
                "modelReleaseStatus",
            ):
                row.pop(field)
            row["sourceUnitId"] = source_unit_id
            row["sourceUnitRef"] = source_unit_ref
            candidate_assets.append(row)
        profile = site.get("siteCrawlProfile")
        profile = profile if isinstance(profile, Mapping) else {}
        candidate = {
            **common,
            "publishMediaMode": publish_media_mode,
            "sourceUnitId": source_unit_id,
            "sourceUnitRef": source_unit_ref,
            "sourceUnitDigest": source_unit_digest,
            "articleSiteId": "wikipedia_zh",
            "sourceDiscoveryProfileDigest": profile_digest,
            "sourceKind": str(site.get("category") or ""),
            "platform": str(site.get("platform") or ""),
            "extractor": str(profile.get("extractor") or site.get("extractor") or ""),
            "policyRevision": "article-source-registry-v1",
            "sourceUrl": source_url,
            "capturedAt": captured_at,
            "bodyEvidenceRef": body_ref,
            "bodyContentSha256": body_sha,
            "accessEvidence": dict(PUBLIC_ACCESS),
            "assets": candidate_assets,
        }
    return AcquiredSourceReadyCandidate(
        carrier=carrier,
        candidate=candidate,
        source_unit={
            "sourceUnitId": source_unit_id,
            "sourceUnitRef": source_unit_ref,
            "sourceUnitDigest": source_unit_digest,
            "sourceUrl": source_url,
            "sourceKind": "wikipedia",
            "extractor": "wikipedia_api",
            "resolvedTitle": bundle.resolved_title,
            "pageId": bundle.page_id,
            "revisionId": bundle.revision_id,
            "bodyEvidenceRef": body_ref,
            "bodyContentSha256": body_sha,
            "accessEvidence": dict(PUBLIC_ACCESS),
            "qualityStatus": "passed",
            "qualityScore": quality_score,
            "qualityReasons": quality_reasons,
        },
        body=body,
        raw_evidence=raw_evidence,
        assets=assets,
    )


__all__ = [
    "PUBLIC_ACCESS",
    "AcquiredAsset",
    "AcquiredSourceReadyCandidate",
    "MediaWikiSourceReadyRejected",
    "acquire_mediawiki_source_ready_candidate",
    "acquire_open_image_assets",
    "source_ready_sha256",
    "source_ready_stable_id",
]
