"""Acquire homepage source-ready candidates from public Baidu/Toutiao Baike."""
from __future__ import annotations

import html
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from core.baike_source_contract import (
    HOMEPAGE_SOURCE_POLICY_REVISION,
    source_identity_matches_contract,
)

from content.source.fetch_payload import fetch_source_payload
from content.source.research.homepage_article_source_ready_mediawiki import (
    PUBLIC_ACCESS,
    AcquiredSourceReadyCandidate,
    MediaWikiSourceReadyRejected,
    acquire_open_image_assets,
    source_ready_sha256,
    source_ready_stable_id,
)
from content.source.research.homepage_article_source_attribution import (
    encyclopedia_source_attribution,
)
from content.source.research.homepage_structured_fact_text import (
    extract_structured_fact_from_baike_infobox,
    extract_structured_fact_from_text,
)
from content.source.research.homepage_text_quality import (
    assess_homepage_text_quality,
)
from content.source.research.image_search_providers import (
    commons_images_for_entity,
    openverse_images_for_entity,
)
from content.source.research.text_match import (
    _wiki_resolved_title_matches_entity,
)

_PROVIDER_NAMES = {
    "baidu_baike": "百度百科",
    "toutiao_baike": "今日头条百科",
}
_OFFICIAL_LABEL = re.compile(r"政府官方网站|官方网站|官网")
_HTTPS_URL = re.compile(r"https://[^\s\"'<>\\]+", re.IGNORECASE)


def _entity_ref(planned: Mapping[str, Any]) -> str:
    raw_type = str(planned.get("entityType") or "").strip()
    entity_type = raw_type.split("/", 1)
    canonical = str(planned.get("canonicalEntityRef") or "").strip()
    if canonical:
        if (
            len(entity_type) != 2
            or not all(entity_type)
            or not canonical.startswith(f"/entity/{raw_type}/")
        ):
            raise MediaWikiSourceReadyRejected(
                "coverage candidate canonical entity ref/type drift"
            )
        return canonical
    name = str(planned.get("candidateName") or "").strip()
    if len(entity_type) != 2 or not all(entity_type) or not name or "/" in name:
        raise MediaWikiSourceReadyRejected(
            "coverage candidate lacks canonical entity type/name"
        )
    return f"/entity/{entity_type[0]}/{entity_type[1]}/{name}"


def _resolved_html_title(body: bytes, source_kind: str) -> str:
    raw = body.decode("utf-8", errors="replace")
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw)
    title = html.unescape(re.sub(r"(?is)<[^>]+>", " ", match.group(1))) if match else ""
    title = re.sub(r"\s+", " ", title).strip()
    suffix = "百度百科" if source_kind == "baidu_baike" else "快懂百科"
    return re.sub(rf"\s*[-_|—]\s*{suffix}.*$", "", title).strip()


def _official_website_from_html(body: bytes) -> str:
    raw = html.unescape(body.decode("utf-8", errors="replace"))
    normalized = (
        raw.replace("\\u002F", "/")
        .replace("\\u002f", "/")
        .replace("\\/", "/")
    )
    for label in _OFFICIAL_LABEL.finditer(normalized):
        window = normalized[label.start() : label.start() + 4096]
        for match in _HTTPS_URL.finditer(window):
            candidate = match.group(0).rstrip(".,;:)]}，。；：）】")
            parsed = urlsplit(candidate)
            hostname = (parsed.hostname or "").casefold()
            if not hostname or hostname.endswith(
                ("baike.com", "baidu.com", "byteimg.com", "bytedance.com")
            ):
                continue
            return candidate
    return ""


def _structured_fact_from_text(
    text: str,
    *,
    raw_html: bytes,
    source_kind: str,
    source_url: str,
    body_ref: str,
    raw_ref: str,
    body_sha256: str,
    captured_at: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    field = ""
    value: object = None
    extracted = extract_structured_fact_from_text(
        text
    ) or extract_structured_fact_from_baike_infobox(raw_html)
    if extracted is not None:
        field, value = extracted
    if not field:
        official_website = _official_website_from_html(raw_html)
        if official_website:
            field = "officialWebsite"
            value = official_website
    if not field:
        raise MediaWikiSourceReadyRejected(
            "homepage source lacks an immutable structured fact"
        )
    source_row = {
        "field": field,
        "sourceId": source_kind,
        "sourceClass": "encyclopedia",
        "sourceUrl": source_url,
        "observedAt": captured_at,
        "confidence": 0.8,
    }
    return (
        {field: value, "factSources": [source_row]},
        [
            {
                "field": field,
                "sourceId": source_kind,
                "sourceUrl": source_url,
                "evidenceRef": raw_ref if field == "officialWebsite" else body_ref,
                "contentSha256": body_sha256,
                "accessEvidence": dict(PUBLIC_ACCESS),
            }
        ],
    )


def _fetch_bound_baike_source(
    *,
    name: str,
    source_kind: str,
    extractor: str,
    source_url: str,
) -> tuple[bytes, str, str]:
    last_error: Exception | None = None
    invalid_response_seen = False
    for _attempt in range(2):
        try:
            payload = fetch_source_payload(
                source_url,
                source={
                    "sourceKind": source_kind,
                    "extractor": extractor,
                    "fetchable": True,
                },
                include_page_images=False,
                entity_id=name,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            last_error = exc
            continue
        raw = payload.get("htmlBytes")
        raw = bytes(raw) if isinstance(raw, bytes | bytearray) else b""
        text = str(payload.get("text") or "").strip()
        title = _resolved_html_title(raw, source_kind)
        if raw and text and _wiki_resolved_title_matches_entity(title, name):
            return raw, text, title
        invalid_response_seen = True
    if invalid_response_seen:
        raise MediaWikiSourceReadyRejected("homepage Baike source identity drift")
    raise MediaWikiSourceReadyRejected(
        f"homepage Baike source fetch failed: {last_error}"
    )


def acquire_baike_homepage_source_ready_candidate(
    planned: Mapping[str, Any],
    *,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
    captured_at: str,
) -> AcquiredSourceReadyCandidate:
    """Freeze one public Baidu/Toutiao body with an independent Commons hero."""

    name = str(planned.get("candidateName") or "").strip()
    source = planned.get("source")
    source = source if isinstance(source, Mapping) else {}
    source_kind = str(source.get("sourceKind") or "")
    extractor = str(source.get("extractor") or "")
    source_url = str(source.get("sourceUrl") or "")
    if source_kind not in _PROVIDER_NAMES or not source_identity_matches_contract(
        source_kind=source_kind,
        url=source_url,
        extractor=extractor,
        policy_revision=HOMEPAGE_SOURCE_POLICY_REVISION,
    ):
        raise MediaWikiSourceReadyRejected(
            "homepage Baike source identity is outside the governed closed set"
        )
    raw, text, title = _fetch_bound_baike_source(
        name=name,
        source_kind=source_kind,
        extractor=extractor,
        source_url=source_url,
    )
    verdict = assess_homepage_text_quality(text, name, require_fact_ready=True)
    if not verdict.accepted:
        raise MediaWikiSourceReadyRejected(
            f"homepage body quality blocked: {verdict.issue}"
        )
    entity_ref = _entity_ref(planned)
    body = text.encode("utf-8")
    body_sha = source_ready_sha256(body)
    source_unit_id = source_ready_stable_id(
        "homepage-source",
        entity_ref,
        source_url,
        source_ready_sha256(raw),
    )
    source_unit_ref = f"sources/{source_unit_id}"
    body_ref = f"{source_unit_ref}/source.md"
    images = commons_images_for_entity(name, limit=8)
    images.extend(
        row
        for row in openverse_images_for_entity(name, limit=8)
        if all(row.get("url") != existing.get("url") for existing in images)
    )
    assets = acquire_open_image_assets(
        images,
        source_unit_ref=source_unit_ref,
        roles=("hero",),
        captured_at=captured_at,
    )
    source_unit_digest = source_ready_sha256(
        (
            source_url
            + "\n"
            + source_ready_sha256(raw)
            + "\n"
            + body_sha
            + "\n"
            + str(assets[0].document["contentSha256"])
        ).encode("utf-8")
    )
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
    candidate_id = source_ready_stable_id(
        "homepage", entity_ref, source_unit_digest, source_revision
    )
    structured, fact_evidence = _structured_fact_from_text(
        text,
        raw_html=raw,
        source_kind=source_kind,
        source_url=source_url,
        body_ref=body_ref,
        raw_ref=f"raw/homepage/{candidate_id}.json",
        body_sha256=body_sha,
        captured_at=captured_at,
    )
    candidate = {
        "candidateId": candidate_id,
        "entityRef": entity_ref,
        "observedEntityRef": entity_ref,
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
        "sourceAttribution": encyclopedia_source_attribution(
            source_kind=source_kind,
            source_url=source_url,
            captured_at=captured_at,
        ),
        "primarySource": {
            "sourceUnitId": source_unit_id,
            "sourceUnitRef": source_unit_ref,
            "sourceUnitDigest": source_unit_digest,
            "sourceKind": source_kind,
            "platform": _PROVIDER_NAMES[source_kind],
            "extractor": extractor,
            "policyRevision": HOMEPAGE_SOURCE_POLICY_REVISION,
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
    return AcquiredSourceReadyCandidate(
        carrier="homepage",
        candidate=candidate,
        source_unit={
            "sourceUnitId": source_unit_id,
            "sourceUnitRef": source_unit_ref,
            "sourceUnitDigest": source_unit_digest,
            "sourceUrl": source_url,
            "sourceKind": source_kind,
            "extractor": extractor,
            "resolvedTitle": title,
            "bodyEvidenceRef": body_ref,
            "bodyContentSha256": body_sha,
            "accessEvidence": dict(PUBLIC_ACCESS),
            "qualityStatus": "passed",
            "qualityScore": 1,
            "qualityReasons": ["homepage_text_quality_passed"],
        },
        body=body,
        raw_evidence=raw,
        assets=assets,
    )


__all__ = ["acquire_baike_homepage_source_ready_candidate"]
