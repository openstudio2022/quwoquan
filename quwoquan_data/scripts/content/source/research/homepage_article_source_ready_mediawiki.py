"""Acquire one homepage/article source-ready candidate from public MediaWiki."""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
import urllib.parse as urllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.content_source_registry import resolve_source_class
from core.image_rules import pixel_size_issue
from core.image_safety import STATUS_SAFE, assess_image
from core.runtime_policy import active_runtime_policy

from content.post.article.evidence_text import (
    score_source_markdown,
)
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
from content.source.research.homepage_article_source_attribution import (
    encyclopedia_source_attribution,
)
from content.source.research.homepage_article_source_ready_wikidata import (
    wikidata_structured_fact,
)
from content.source.research.homepage_structured_fact_text import (
    extract_structured_fact_from_text,
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

_EXTRACTED_DEPENDENCIES = (
    assess_homepage_text_quality,
    encyclopedia_source_attribution,
    resolve_source_class,
    score_source_markdown,
    urllib,
)

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
        if (
            len(parts) != 2
            or not all(parts)
            or not canonical.startswith(expected_prefix)
        ):
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
        asset_ref = (
            f"{source_unit_ref}/assets/{content_sha.removeprefix('sha256:')}{extension}"
        )
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
    from content.source.research.homepage_article_source_ready_mediawiki_acquisition import (
        acquire_mediawiki_source_ready_candidate as acquire,
    )

    return acquire(
        planned,
        carrier=carrier,
        source_revision=source_revision,
        source_digest=source_digest,
        entity_catalog_digest=entity_catalog_digest,
        captured_at=captured_at,
        fetch_page=fetch_mediawiki_page_bundle_for_url,
        page_images=_mediawiki_page_images,
        wikidata_images=wikidata_commons_images_for_entity,
        commons_images=commons_images_for_entity,
        openverse_images=openverse_images_for_entity,
        acquire_assets=acquire_open_image_assets,
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
