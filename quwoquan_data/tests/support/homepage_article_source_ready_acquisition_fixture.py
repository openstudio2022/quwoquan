"""homepage/article source-ready acquisition 契约测试共享常量与构造 helper。

由 test_homepage_article_source_ready_acquisition__public_mediawiki_* 场景组
测试文件共享；从原单体测试文件逐字下沉，不改变任何 helper 逻辑。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from content.source.research.article_frontier_profile import (
    article_profile_digest,
    article_search_sites,
)
from content.source.research.homepage_article_seed_selection import seed_id
from content.source.research.homepage_article_source_ready_evidence import (
    canonical_digest,
    write_create_once_json,
)
from content.source.research.homepage_article_source_ready_mediawiki import (
    AcquiredAsset,
    AcquiredSourceReadyCandidate,
)

IDENTITY = {
    "sourceRevision": "sha256:" + "1" * 64,
    "sourceDigest": "sha256:" + "2" * 64,
    "entityCatalogDigest": "sha256:" + "3" * 64,
}
CAPTURED_AT = "2026-08-09T00:00:00Z"
ACCESS = {
    "anonymousPublicAccess": True,
    "loginRequired": False,
    "captchaRequired": False,
    "paywallRequired": False,
    "drmProtected": False,
    "accessControlBypass": False,
}


def _sha(body: bytes) -> str:
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _planned(
    name: str,
    entity_type: str = "地点/景区",
    *,
    source_title: str | None = None,
) -> dict[str, object]:
    resolved_title = source_title or name
    row: dict[str, object] = {
        "coverageEntityIdentity": f"name_location:{name}|示例省|示例市|示例区",
        "canonicalEntityRef": f"/entity/{entity_type}/{name}",
        "candidateName": name,
        "province": "示例省",
        "city": "成都市",
        "district": "锦江区",
        "entityType": entity_type,
        "source": {
            "sourceKind": "wikipedia",
            "extractor": "wikipedia_api",
            "sourceUrl": f"https://zh.wikipedia.org/wiki/{resolved_title}",
            "resolvedTitle": resolved_title,
            "observedAt": CAPTURED_AT,
        },
    }
    row["coverageRecordDigest"] = _sha(f"coverage:{name}".encode())
    return row


def _attribution(name: str) -> dict[str, object]:
    source_url = f"https://zh.wikipedia.org/wiki/{name}"
    return {
        "isOriginal": False,
        "originalCreatorId": None,
        "originalCreatorName": "维基百科贡献者",
        "originalCreatorProfileUrl": None,
        "platform": "维基百科",
        "sourcePostUrl": source_url,
        "originalAssetUrl": source_url,
        "attributionText": "正文事实来源：维基百科（维基百科贡献者）",
        "rightsBasis": "CC BY-SA 4.0",
        "commercialAuthorizationStatus": "verified",
        "publicationAdmission": "research_release",
        "authorizationProofUrl": source_url,
        "termsUrl": "https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use",
        "riskAcceptanceId": None,
        "watermarkStatus": "absent",
        "audioRightsStatus": "no_audio",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "collectedAt": CAPTURED_AT,
        "takedownPolicy": "remove_on_verified_rights_or_source_dispute",
        "derivedModifications": [],
    }


def _seed_selection(
    path: Path,
    rows: list[dict[str, object]],
    *,
    homepage_count: int,
    seed_origin: str = "historical_capsule_hint",
) -> Path:
    seeds = []
    for index, row in enumerate(rows):
        source = row["source"]
        assert isinstance(source, dict)
        carrier = "homepage" if index < homepage_count else "article"
        name = str(row["candidateName"])
        coverage_key = {
            "coverageEntityIdentity": row["coverageEntityIdentity"],
            "coverageRecordDigest": row["coverageRecordDigest"],
            "entityRef": row["canonicalEntityRef"],
            "carrier": carrier,
            "sourceUrl": source["sourceUrl"],
        }
        seed = {
            "seedOrigin": seed_origin,
            "seedId": seed_id(
                seed_origin=seed_origin, coverage_key=coverage_key
            ),
            "coverageKey": coverage_key,
            "candidateName": name,
            "province": "示例省",
            "city": "成都市",
            "district": "锦江区",
            "entityType": "地点/景区",
            "sourceKind": source["sourceKind"],
            "extractor": source["extractor"],
        }
        if seed_origin == "historical_capsule_hint":
            seed["historicalBaseline"] = {
                "candidateId": f"historical-{carrier}-{index}",
                "bodyContentSha256": _sha(
                    f"historical:{carrier}:{index}".encode()
                ),
            }
        seeds.append(seed)
    stable = {
        "schema": "quwoquan_data.homepage_article_seed_selection",
        "seedSetId": "test-seed-selection",
        "counts": {
            "homepage": homepage_count,
            "article": len(rows) - homepage_count,
        },
        "seeds": seeds,
    }
    write_create_once_json(path, {**stable, "selectionDigest": canonical_digest(stable)})
    return path


def _asset_document(
    *, source_unit_ref: str, role: str, seed: str
) -> tuple[dict[str, object], bytes]:
    body = f"image:{seed}".encode()
    digest = _sha(body)
    return (
        {
            "assetId": f"asset-{seed}",
            "role": role,
            "assetRef": (
                f"{source_unit_ref}/assets/"
                f"{digest.removeprefix('sha256:')}.jpg"
            ),
            "originalAssetUrl": f"https://upload.wikimedia.org/{seed}.jpg",
            "sourcePageUrl": f"https://commons.wikimedia.org/wiki/File:{seed}.jpg",
            "platform": "维基共享资源",
            "provider": "wikimedia_commons",
            "creator": f"Creator {seed}",
            "capturedAt": CAPTURED_AT,
            "contentSha256": digest,
            "license": "CC BY-SA 4.0",
            "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
            "authorizationProof": f"https://commons.wikimedia.org/wiki/File:{seed}.jpg",
            "usageScope": "app_publish",
            "modelReleaseStatus": "not_required",
            "authorizationRequired": False,
            "rightsStatus": "verified",
            "rightsIssues": [],
            "acquisitionStatus": "acquired",
            "distributionDecision": "research_allowed",
            "qualityStatus": "passed",
            "safetyStatus": "passed",
            "generated": False,
            "width": 1600,
            "height": 1000,
            "byteCount": len(body),
            "fileSha256": digest,
            "safetyEvidence": {
                "status": "safe",
                "faces": 0,
                "hasWatermark": False,
                "textAreaRatio": 0.0,
                "reasons": [],
                "backends": ["cv", "ocr"],
            },
            "accessEvidence": dict(ACCESS),
        },
        body,
    )


def _fake_acquired(carrier: str, name: str) -> AcquiredSourceReadyCandidate:
    source_unit_id = f"{carrier}-{name}"
    source_unit_ref = f"sources/{source_unit_id}"
    body = f"body:{carrier}:{name}".encode()
    body_sha = _sha(body)
    roles = ("hero",) if carrier == "homepage" else ("cover", "body")
    assets: list[AcquiredAsset] = []
    for index, role in enumerate(roles):
        document, asset_body = _asset_document(
            source_unit_ref=source_unit_ref,
            role=role,
            seed=f"{carrier}-{name}-{index}",
        )
        assets.append(AcquiredAsset(body=asset_body, document=dict(document)))
    source_unit_digest = _sha(
        (body_sha + "|" + "|".join(
            str(asset.document["contentSha256"]) for asset in assets
        )).encode()
    )
    candidate_id = f"candidate-{carrier}-{name}"
    entity_ref = f"/entity/地点/景区/{name}"
    common = {
        "candidateId": candidate_id,
        "entityRef": entity_ref,
        "observedEntityRef": entity_ref,
        **IDENTITY,
        "sourceAttribution": _attribution(name),
    }
    if carrier == "homepage":
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
                "sourceUrl": f"https://zh.wikipedia.org/wiki/{name}",
                "capturedAt": CAPTURED_AT,
                "bodyEvidenceRef": f"{source_unit_ref}/source.md",
                "bodyContentSha256": body_sha,
                "accessEvidence": dict(ACCESS),
            },
            "structuredFacts": {
                "officialWebsite": f"https://example.test/{name}",
                "factSources": [
                    {
                        "field": "officialWebsite",
                        "sourceId": "wikipedia",
                        "sourceClass": "encyclopedia",
                        "sourceUrl": f"https://zh.wikipedia.org/wiki/{name}",
                        "observedAt": CAPTURED_AT,
                        "confidence": 0.9,
                    }
                ],
            },
            "factEvidence": [
                {
                    "field": "officialWebsite",
                    "sourceId": "wikipedia",
                    "sourceUrl": f"https://zh.wikipedia.org/wiki/{name}",
                    "evidenceRef": f"{source_unit_ref}/source.md",
                    "contentSha256": body_sha,
                    "accessEvidence": dict(ACCESS),
                }
            ],
            "factConflicts": [],
            "hero": hero,
        }
    else:
        site = next(
            site
            for site in article_search_sites(
                site_ids=frozenset({"wikipedia_zh"})
            )
            if site["siteId"] == "wikipedia_zh"
        )
        article_assets = []
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
            article_assets.append(row)
        candidate = {
            **common,
            "publishMediaMode": "illustrated",
            "sourceUnitId": source_unit_id,
            "sourceUnitRef": source_unit_ref,
            "sourceUnitDigest": source_unit_digest,
            "articleSiteId": "wikipedia_zh",
            "sourceDiscoveryProfileDigest": article_profile_digest(site),
            "sourceKind": "encyclopedia",
            "platform": "维基百科",
            "extractor": "wikipedia_api",
            "policyRevision": "article-source-registry-v1",
            "sourceUrl": f"https://zh.wikipedia.org/wiki/{name}",
            "capturedAt": CAPTURED_AT,
            "bodyEvidenceRef": f"{source_unit_ref}/source.md",
            "bodyContentSha256": body_sha,
            "accessEvidence": dict(ACCESS),
            "assets": article_assets,
        }
    return AcquiredSourceReadyCandidate(
        carrier=carrier,
        candidate=candidate,
        source_unit={
            "sourceUnitId": source_unit_id,
            "sourceUnitRef": source_unit_ref,
            "sourceUnitDigest": source_unit_digest,
            "sourceUrl": f"https://zh.wikipedia.org/wiki/{name}",
            "sourceKind": "wikipedia",
            "extractor": "wikipedia_api",
            "resolvedTitle": name,
            "pageId": 1,
            "revisionId": 1,
            "bodyEvidenceRef": f"{source_unit_ref}/source.md",
            "bodyContentSha256": body_sha,
            "accessEvidence": dict(ACCESS),
            "qualityStatus": "passed",
            "qualityScore": 5,
            "qualityReasons": ["fixture_quality_passed"],
        },
        body=body,
        raw_evidence=b'{"query":{"pages":{}}}',
        assets=tuple(assets),
    )


def _projection(root: Path, rows: list[dict[str, object]]) -> dict[str, object]:
    stable = {
        "schema": "quwoquan_data.coverage_source_ready_catalog_projection",
        **IDENTITY,
        "plannedCandidates": rows,
    }
    projection = {**stable, "projectionDigest": canonical_digest(stable)}
    write_create_once_json(root / "coverage-projection.json", projection)
    return projection
