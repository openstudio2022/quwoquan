# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002.t1
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from content.source.research.article_frontier_profile import (
    article_profile_digest,
    article_search_sites,
)
from content.source.research.article_source_unit_catalog import (
    ARTICLE_SOURCE_POLICY_REVISION,
    SOURCE_CATALOG_CREATE_ONCE_COLLISION,
    SOURCE_INVALID_EVIDENCE,
    SOURCE_POOL_SHORTFALL,
    ArticleSourceUnitCatalogError,
    build_article_source_unit_catalog,
    validate_article_source_unit_catalog,
    write_create_once_article_source_unit_catalog,
)

IDENTITY = {
    "sourceRevision": "sha256:" + "a" * 64,
    "sourceDigest": "sha256:" + "b" * 64,
    "entityCatalogDigest": "sha256:" + "c" * 64,
}
SOURCE_CASES = (
    (
        "wikivoyage_zh",
        "https://zh.wikivoyage.org/wiki/西湖",
        "https://upload.wikimedia.org/wikipedia/commons/a/a1/West_Lake_original.jpg",
    ),
    (
        "ctrip_sight_guide",
        "https://you.ctrip.com/sight/hangzhou14/105586.html",
        "https://bkimg.cdn.bcebos.com/pic/west-lake-original.jpg",
    ),
    (
        "qunar_guide",
        "https://travel.qunar.com/p-cs299878-hangzhou-jingdian",
        "https://p3-sign.douyinpic.com/tos-cn-i-0813/west-lake-original.jpg",
    ),
)


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _candidate(index: int) -> dict[str, object]:
    site_id, source_url, image_url = SOURCE_CASES[index]
    sites = {
        str(site["siteId"]): site
        for site in article_search_sites()
    }
    site = sites[site_id]
    source_kind = str(site["category"])
    platform = str(site["platform"])
    extractor = str(site["extractor"])
    source_unit_id = f"west-lake-{site_id}"
    source_unit_ref = f"sources/{source_unit_id}"
    entity_ref = "/entity/地点/景区/西湖"
    assets: list[dict[str, object]] = []
    for role in ("cover", "body"):
        asset_url = image_url.replace(".jpg", f"-{role}.jpg")
        assets.append(
            {
                "assetId": f"{source_unit_id}-{role}",
                "role": role,
                "sourceUnitId": source_unit_id,
                "sourceUnitRef": source_unit_ref,
                "assetRef": f"{source_unit_ref}/assets/{role}.jpg",
                "originalAssetUrl": asset_url,
                "sourcePageUrl": source_url,
                "platform": platform,
                "provider": source_kind,
                "creator": f"{platform}词条原图作者-{role}",
                "capturedAt": "2026-08-08T00:00:00Z",
                "contentSha256": _digest(f"{source_unit_id}:{role}"),
                "license": "source page terms; authorization pending",
                "termsUrl": "https://example.test/terms",
                "authorizationProof": "",
                "authorizationRequired": True,
                "rightsStatus": "unverified",
                "rightsIssues": ["author distribution authorization pending"],
                "acquisitionStatus": "acquired",
                "distributionDecision": "research_allowed",
                "qualityStatus": "passed",
                "safetyStatus": "passed",
                "generated": False,
            }
        )
    return {
        "candidateId": f"article-{site_id}-west-lake",
        "entityRef": entity_ref,
        "observedEntityRef": entity_ref,
        **IDENTITY,
        "sourceUnitId": source_unit_id,
        "sourceUnitRef": source_unit_ref,
        "sourceUnitDigest": _digest(f"source-unit:{source_unit_id}"),
        "articleSiteId": site_id,
        "sourceDiscoveryProfileDigest": article_profile_digest(site),
        "sourceKind": source_kind,
        "platform": platform,
        "extractor": extractor,
        "policyRevision": ARTICLE_SOURCE_POLICY_REVISION,
        "sourceUrl": source_url,
        "capturedAt": "2026-08-08T00:00:00Z",
        "bodyEvidenceRef": f"{source_unit_ref}/source.md",
        "bodyContentSha256": _digest(f"body:{source_unit_id}"),
        "accessEvidence": {
            "anonymousPublicAccess": True,
            "loginRequired": False,
            "captchaRequired": False,
            "paywallRequired": False,
            "drmProtected": False,
            "accessControlBypass": False,
        },
        "assets": assets,
    }


def _catalog(
    candidates: list[dict[str, object]] | None = None,
    *,
    minimum: int = 3,
) -> dict[str, object]:
    return build_article_source_unit_catalog(
        catalog_id="travel-article-source-units-west-lake",
        catalog_version="2026-08-08.1",
        created_at="2026-08-08T00:00:00Z",
        minimum_candidate_count=minimum,
        candidates=candidates if candidates is not None else [_candidate(i) for i in range(3)],
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
    )


def _redigest(catalog: dict[str, object]) -> dict[str, object]:
    stable = {key: value for key, value in catalog.items() if key != "catalogDigest"}
    payload = json.dumps(
        stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {**stable, "catalogDigest": "sha256:" + hashlib.sha256(payload).hexdigest()}


def test_registry_admitted_catalog_freezes_illustrated_source_units() -> None:
    catalog = _catalog()
    evidence = validate_article_source_unit_catalog(catalog)

    assert evidence == {
        "catalogId": "travel-article-source-units-west-lake",
        "catalogVersion": "2026-08-08.1",
        "catalogDigest": catalog["catalogDigest"],
        "candidateCount": 3,
        "illustratedCandidateCount": 3,
        "closedSourceUnitCount": 3,
        "minimumCandidateCount": 3,
        "ready": True,
    }


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda row: row.update({"sourceUrl": "https://example.test/西湖"}),
            "allowed paths",
        ),
        (
            lambda row: row["accessEvidence"].update({"loginRequired": True}),
            "loginRequired",
        ),
        (
            lambda row: row["accessEvidence"].update({"captchaRequired": True}),
            "captchaRequired",
        ),
        (
            lambda row: row.update({"observedEntityRef": "/entity/地点/景区/太湖"}),
            "entity mismatch",
        ),
    ],
)
def test_catalog_rejects_non_public_or_non_registry_body_evidence(
    mutate: object,
    message: str,
) -> None:
    row = _candidate(0)
    assert callable(mutate)
    mutate(row)

    with pytest.raises(ArticleSourceUnitCatalogError, match=message) as captured:
        _catalog([row], minimum=1)

    assert captured.value.code == SOURCE_INVALID_EVIDENCE


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("articleSiteId", "xiaohongshu_travel_reference", "not currently admitted"),
        ("sourceDiscoveryProfileDigest", "sha256:" + "f" * 64, "profile drift"),
        ("platform", "未登记平台", "platform differs"),
        ("extractor", "generic_html", "extractor differs"),
    ],
)
def test_catalog_binds_registry_site_profile(
    field: str,
    value: str,
    message: str,
) -> None:
    row = _candidate(0)
    row[field] = value
    with pytest.raises(ArticleSourceUnitCatalogError, match=message):
        _catalog([row], minimum=1)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda row: row["assets"].pop(),
            "assets",
        ),
        (
            lambda row: row["assets"][1].update(
                {
                    "sourceUnitId": "other-unit",
                    "sourceUnitRef": "sources/other-unit",
                }
            ),
            "cross-sourceUnit",
        ),
        (
            lambda row: row["assets"][0].update(
                {
                    "originalAssetUrl": (
                        "https://upload.wikimedia.org/wikipedia/thumb/a/a1/236x-West_Lake.jpg"
                    )
                }
            ),
            "thumbnail/transformed URL",
        ),
        (
            lambda row: row["assets"][0].update({"creator": "unknown"}),
            "Creator identity is missing",
        ),
        (
            lambda row: row["assets"][0].update({"generated": True}),
            "generated",
        ),
    ],
)
def test_catalog_rejects_non_illustrated_or_untraceable_assets(
    mutate: object,
    message: str,
) -> None:
    row = _candidate(0)
    assert callable(mutate)
    mutate(row)

    with pytest.raises(ArticleSourceUnitCatalogError, match=message) as captured:
        _catalog([row], minimum=1)

    assert captured.value.code == SOURCE_INVALID_EVIDENCE


def test_catalog_shortfall_is_typed_without_accepting_old_receipts() -> None:
    with pytest.raises(ArticleSourceUnitCatalogError) as captured:
        _catalog([_candidate(0)], minimum=2)

    assert captured.value.code == SOURCE_POOL_SHORTFALL
    assert "required=2 actual=1" in str(captured.value)


def test_catalog_identity_drift_and_digest_drift_are_invalid_evidence() -> None:
    candidate = _candidate(0)
    candidate["sourceDigest"] = "sha256:" + "d" * 64
    with pytest.raises(ArticleSourceUnitCatalogError, match="source identity drift"):
        _catalog([candidate], minimum=1)

    catalog = _catalog([_candidate(0)], minimum=1)
    catalog["catalogDigest"] = "sha256:" + "e" * 64
    with pytest.raises(ArticleSourceUnitCatalogError, match="catalogDigest mismatch"):
        validate_article_source_unit_catalog(catalog)


def test_create_once_catalog_replays_identically_and_rejects_collision(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "article-source-units" / "2026-08-08.1.json"
    catalog = _catalog()
    first = write_create_once_article_source_unit_catalog(destination, catalog)
    second = write_create_once_article_source_unit_catalog(destination, catalog)
    assert first == second == catalog

    changed = copy.deepcopy(catalog)
    changed["createdAt"] = "2026-08-08T00:00:01Z"
    changed = _redigest(changed)
    with pytest.raises(ArticleSourceUnitCatalogError) as captured:
        write_create_once_article_source_unit_catalog(destination, changed)
    assert captured.value.code == SOURCE_CATALOG_CREATE_ONCE_COLLISION
