"""Acquisition implementation for MediaWiki source-ready candidates."""

from __future__ import annotations

from content.source.research.homepage_article_source_ready_mediawiki import (
    PUBLIC_ACCESS,
    AcquiredSourceReadyCandidate,
    Any,
    Mapping,
    MediaWikiSourceReadyRejected,
    _article_site,
    _entity_ref,
    _sha256,
    _stable_id,
    _structured_fact_material,
    assess_homepage_text_quality,
    encyclopedia_source_attribution,
    json,
    resolve_source_class,
    score_source_markdown,
    urllib,
)


def acquire_mediawiki_source_ready_candidate(
    planned: Mapping[str, Any],
    *,
    carrier: str,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
    captured_at: str,
    fetch_page: Any,
    page_images: Any,
    wikidata_images: Any,
    commons_images: Any,
    openverse_images: Any,
    acquire_assets: Any,
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
        source_url = "https://zh.wikipedia.org/wiki/" + urllib.parse.quote(
            source_lookup_title.replace(" ", "_"), safe="()_-."
        )
    if not source_url.startswith("https://zh.wikipedia.org/wiki/"):
        raise MediaWikiSourceReadyRejected(
            "current producer only accepts coverage-qualified zh.wikipedia pages"
        )
    entity_ref = _entity_ref(planned)
    bundle = fetch_page(source_url, include_images=True)
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
    image_rows = page_images(
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
            *wikidata_images(
                bundle.resolved_title,
                entity_id=source_lookup_title,
                limit=8,
            ),
            *commons_images(source_lookup_title, limit=8),
            *openverse_images(source_lookup_title, limit=8),
        ]
        seen_urls = {str(row.get("url") or "") for row in image_rows}
        for row in supplement:
            url = str(row.get("url") or "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            image_rows.append(row)
    try:
        assets = acquire_assets(
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
        (source_url + "\n" + str(bundle.revision_id) + "\n" + body_sha + "\n").encode(
            "utf-8"
        )
        + _sha256(raw_evidence).encode("utf-8")
        + "\n".join(asset.document["contentSha256"] for asset in assets).encode("utf-8")
    )
    candidate_id = _stable_id(carrier, entity_ref, source_unit_digest, source_revision)
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
        field, value, source_id, fact_source_url, confidence, external_raw = (
            fact_material
        )
        evidence_ref = (
            f"raw/homepage/{candidate_id}.json"
            if external_raw is not None
            else body_ref
        )
        evidence_sha = _sha256(raw_evidence) if external_raw is not None else body_sha
        structured = {
            field: value,
            "factSources": [
                {
                    "field": field,
                    "sourceId": source_id,
                    "sourceClass": resolve_source_class(source_id=source_id),
                    "sourceUrl": fact_source_url,
                    "observedAt": captured_at,
                    "confidence": confidence,
                }
            ],
        }
        fact_evidence = [
            {
                "field": field,
                "sourceId": source_id,
                "sourceUrl": fact_source_url,
                "evidenceRef": evidence_ref,
                "contentSha256": evidence_sha,
                "accessEvidence": dict(PUBLIC_ACCESS),
            }
        ]
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
