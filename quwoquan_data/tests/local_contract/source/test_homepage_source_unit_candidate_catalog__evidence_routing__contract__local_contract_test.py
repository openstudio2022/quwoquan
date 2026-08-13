# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002.t1
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from content.source.research.homepage_source_unit_catalog import (
    SOURCE_CATALOG_CREATE_ONCE_COLLISION,
    SOURCE_INVALID_EVIDENCE,
    SOURCE_POOL_SHORTFALL,
    HomepageSourceUnitCatalogError,
    build_homepage_source_unit_catalog,
    validate_homepage_source_unit_catalog,
    write_create_once_homepage_source_unit_catalog,
)


IDENTITY = {
    "sourceRevision": "sha256:" + "a" * 64,
    "sourceDigest": "sha256:" + "b" * 64,
    "entityCatalogDigest": "sha256:" + "c" * 64,
}


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _access() -> dict[str, bool]:
    return {
        "anonymousPublicAccess": True,
        "loginRequired": False,
        "captchaRequired": False,
        "paywallRequired": False,
        "drmProtected": False,
        "accessControlBypass": False,
    }


def _candidate(index: int = 0) -> dict[str, object]:
    name = f"西湖-{index}"
    entity_ref = f"/entity/地点/景区/{name}"
    primary_url = f"https://zh.wikipedia.org/wiki/{name}"
    official_url = f"https://example.test/{index}/opening-hours"
    return {
        "candidateId": f"homepage-west-lake-{index}",
        "entityRef": entity_ref,
        "observedEntityRef": entity_ref,
        **IDENTITY,
        "primarySource": {
            "sourceUnitId": f"homepage-wikipedia-{index}",
            "sourceUnitRef": f"sources/homepage-wikipedia-{index}",
            "sourceUnitDigest": _digest(f"homepage-unit:{index}"),
            "sourceKind": "wikipedia",
            "platform": "维基百科",
            "extractor": "wikipedia_api",
            "policyRevision": "encyclopedia-primary",
            "sourceUrl": primary_url,
            "capturedAt": "2026-08-08T00:00:00Z",
            "bodyEvidenceRef": f"sources/homepage-wikipedia-{index}/source.md",
            "bodyContentSha256": _digest(f"homepage-body:{index}"),
            "accessEvidence": _access(),
        },
        "structuredFacts": {
            "openingHours": [
                {"openMinuteOfDay": 480, "closeMinuteOfDay": 1080}
            ],
            "factSources": [
                {
                    "field": "openingHours",
                    "sourceId": "official_site",
                    "sourceClass": "official_site",
                    "sourceUrl": official_url,
                    "observedAt": "2026-08-08T00:00:00Z",
                    "confidence": 0.98,
                }
            ],
        },
        "factEvidence": [
            {
                "field": "openingHours",
                "sourceId": "official_site",
                "sourceUrl": official_url,
                "evidenceRef": f"facts/{index}/official-opening-hours.json",
                "contentSha256": _digest(f"fact:{index}:openingHours"),
                "accessEvidence": _access(),
            }
        ],
        "factConflicts": [],
        "hero": {
            "assetId": f"homepage-hero-{index}",
            "entityRef": entity_ref,
            "observedEntityRef": entity_ref,
            "sourceUnitRef": f"sources/homepage-media-{index}",
            "sourceUnitDigest": _digest(f"homepage-media:{index}"),
            "assetRef": f"sources/homepage-media-{index}/assets/hero.jpg",
            "originalAssetUrl": f"https://images.example.test/{index}/west-lake-original.jpg",
            "sourcePageUrl": f"https://gallery.example.test/{index}/west-lake",
            "platform": "专业摄影图库",
            "provider": "public_gallery",
            "creator": f"摄影师-{index}",
            "capturedAt": "2026-08-08T00:00:00Z",
            "contentSha256": _digest(f"hero:{index}"),
            "license": "authorization pending",
            "termsUrl": "https://gallery.example.test/terms",
            "authorizationProof": "",
            "usageScope": "app_publish",
            "modelReleaseStatus": "not_required",
            "authorizationRequired": True,
            "rightsStatus": "unverified",
            "rightsIssues": ["creator distribution authorization pending"],
            "acquisitionStatus": "acquired",
            "distributionDecision": "research_allowed",
            "qualityStatus": "passed",
            "safetyStatus": "passed",
            "generated": False,
            "accessEvidence": _access(),
        },
    }


def _catalog(
    candidates: list[dict[str, object]] | None = None,
    *,
    minimum: int = 1,
) -> dict[str, object]:
    return build_homepage_source_unit_catalog(
        catalog_id="travel-homepage-source-units",
        created_at="2026-08-08T00:00:00Z",
        minimum_candidate_count=minimum,
        candidates=candidates if candidates is not None else [_candidate()],
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
    )


def _redigest(catalog: dict[str, object]) -> dict[str, object]:
    stable = {key: value for key, value in catalog.items() if key != "catalogDigest"}
    encoded = json.dumps(
        stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {**stable, "catalogDigest": "sha256:" + hashlib.sha256(encoded).hexdigest()}


def test_catalog_keeps_narrative_and_structured_fact_sources_separate() -> None:
    catalog = _catalog()
    evidence = validate_homepage_source_unit_catalog(catalog)
    candidate = catalog["candidates"][0]

    assert candidate["primarySource"]["sourceKind"] == "wikipedia"
    assert candidate["structuredFacts"]["factSources"][0]["sourceClass"] == "official_site"
    assert evidence == {
        "catalogId": "travel-homepage-source-units",
        "catalogDigest": catalog["catalogDigest"],
        "candidateCount": 1,
        "heroReadyCount": 1,
        "structuredFactsReadyCount": 1,
        "minimumCandidateCount": 1,
        "ready": True,
    }


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda row: row["primarySource"].update(
                {
                    "sourceKind": "wikipedia",
                    "extractor": "wikipedia_api",
                    "sourceUrl": "https://www.wikivoyage.org/wiki/西湖",
                }
            ),
            "three-encyclopedia closed set",
        ),
        (
            lambda row: row["primarySource"]["accessEvidence"].update(
                {"captchaRequired": True}
            ),
            "captchaRequired",
        ),
        (
            lambda row: row.update({"observedEntityRef": "/entity/地点/景区/太湖"}),
            "entity mismatch",
        ),
    ],
)
def test_catalog_rejects_narrative_source_or_entity_drift(
    mutate: object,
    message: str,
) -> None:
    row = _candidate()
    assert callable(mutate)
    mutate(row)
    with pytest.raises(HomepageSourceUnitCatalogError, match=message) as captured:
        _catalog([row])
    assert captured.value.code == SOURCE_INVALID_EVIDENCE


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda row: row["structuredFacts"].update({"factSources": []}),
            "factSources",
        ),
        (
            lambda row: row.update({"factEvidence": []}),
            "factEvidence",
        ),
        (
            lambda row: row["factEvidence"][0]["accessEvidence"].update(
                {"loginRequired": True}
            ),
            "loginRequired",
        ),
    ],
)
def test_catalog_requires_field_level_public_fact_evidence(
    mutate: object,
    message: str,
) -> None:
    row = _candidate()
    assert callable(mutate)
    mutate(row)
    with pytest.raises(HomepageSourceUnitCatalogError, match=message) as captured:
        _catalog([row])
    assert captured.value.code == SOURCE_INVALID_EVIDENCE


def test_catalog_requires_explicit_official_conflict_record() -> None:
    row = _candidate()
    fact_sources = row["structuredFacts"]["factSources"]
    fact_sources[0]["conflictsWithSourceIds"] = ["wikipedia"]
    fact_sources.append(
        {
            "field": "openingHours",
            "sourceId": "wikipedia",
            "sourceClass": "encyclopedia",
            "sourceUrl": "https://zh.wikipedia.org/wiki/西湖",
            "observedAt": "2026-08-08T00:00:00Z",
            "confidence": 0.7,
        }
    )
    row["factEvidence"].append(
        {
            "field": "openingHours",
            "sourceId": "wikipedia",
            "sourceUrl": "https://zh.wikipedia.org/wiki/西湖",
            "evidenceRef": "facts/0/wikipedia-opening-hours.json",
            "contentSha256": _digest("wikipedia-conflict"),
            "accessEvidence": _access(),
        }
    )
    with pytest.raises(
        HomepageSourceUnitCatalogError,
        match="conflictsWithSourceIds/factConflicts mismatch",
    ):
        _catalog([row])

    row["factConflicts"] = [
        {
            "field": "openingHours",
            "preferredSourceId": "official_site",
            "conflictingSourceId": "wikipedia",
            "resolution": "official_source_preferred",
            "observedAt": "2026-08-08T00:00:00Z",
        }
    ]
    assert validate_homepage_source_unit_catalog(_catalog([row]))["ready"] is True


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda row: row["hero"].update(
                {"originalAssetUrl": "https://images.example.test/thumb/236x-west-lake.jpg"}
            ),
            "thumbnail/transformed URL",
        ),
        (
            lambda row: row["hero"].update({"generated": True}),
            "generated",
        ),
        (
            lambda row: row["hero"].update({"creator": "unknown"}),
            "Creator identity is missing",
        ),
        (
            lambda row: row["hero"]["accessEvidence"].update(
                {"anonymousPublicAccess": False}
            ),
            "anonymousPublicAccess",
        ),
        (
            lambda row: row["hero"].update({"observedEntityRef": "/entity/地点/景区/太湖"}),
            "cross-entity media",
        ),
    ],
)
def test_catalog_rejects_unusable_or_untraceable_hero(
    mutate: object,
    message: str,
) -> None:
    row = _candidate()
    assert callable(mutate)
    mutate(row)
    with pytest.raises(HomepageSourceUnitCatalogError, match=message) as captured:
        _catalog([row])
    assert captured.value.code == SOURCE_INVALID_EVIDENCE


def test_catalog_shortfall_is_typed() -> None:
    with pytest.raises(HomepageSourceUnitCatalogError) as captured:
        _catalog([_candidate()], minimum=2)
    assert captured.value.code == SOURCE_POOL_SHORTFALL
    assert "required=2 actual=1" in str(captured.value)


def test_create_once_catalog_replays_and_rejects_collision(tmp_path: Path) -> None:
    destination = tmp_path / "homepage-source-units" / "2026-08-08.1.json"
    catalog = _catalog()
    assert write_create_once_homepage_source_unit_catalog(destination, catalog) == catalog
    assert write_create_once_homepage_source_unit_catalog(destination, catalog) == catalog

    changed = copy.deepcopy(catalog)
    changed["createdAt"] = "2026-08-08T00:00:01Z"
    changed = _redigest(changed)
    with pytest.raises(HomepageSourceUnitCatalogError) as captured:
        write_create_once_homepage_source_unit_catalog(destination, changed)
    assert captured.value.code == SOURCE_CATALOG_CREATE_ONCE_COLLISION
