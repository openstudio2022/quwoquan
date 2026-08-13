# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-004.t1
"""场景组：frozen 分类冻结与 homepage 媒体 locator 从原始证据还原。

从 test_scale_source_pool_homepage_article__catalog_projection__contract
__local_contract_test.py 按场景拆出；测试逐字搬移。
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from content.source.research.article_source_unit_catalog import (
    build_article_source_unit_catalog,
)
from content.source.research.scale_source_pool_runtime import (
    _frozen_homepage_media_inputs,
)

from support.scale_source_pool_catalog_fixture import (
    IDENTITY,
    _digest,
    _document_digest,
    _file_digest,
    _homepage_candidate,
    _photography_article_candidate,
    _write_json,
)


def test_photography_article_runtime_freezes_category_and_source_title(
) -> None:
    """The frozen category must survive projection into the runtime source unit."""

    candidate = _photography_article_candidate()
    article = build_article_source_unit_catalog(
        catalog_id="photography-article",
        created_at="2026-08-12T00:00:00Z",
        minimum_candidate_count=1,
        candidates=[candidate],
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
    )
    frozen = article["candidates"][0]
    assert frozen["articleCategory"] == "photography"
    assert frozen["sourceClassification"]["sourceTitle"].endswith("摄影机位攻略")

    import content.source.research.scale_source_pool_runtime as runtime

    projected = runtime._candidate_source(frozen, "article")
    assert projected["articleCategory"] == "photography"
    assert projected["writingIntent"] == "planning_consultation"
    assert projected["topicTagRefs"] == ["Topic/旅行/玩法/摄影旅拍"]
    assert projected["sourceClassification"] == frozen["sourceClassification"]


def test_frozen_homepage_media_restores_exact_locator_placement_from_raw_evidence(
    tmp_path: Path,
) -> None:
    candidate = copy.deepcopy(_homepage_candidate())
    primary = candidate["primarySource"]
    hero = candidate["hero"]
    assert isinstance(primary, dict) and isinstance(hero, dict)
    hero["sourcePageUrl"] = (
        "https://commons.wikimedia.org/wiki/"
        "File:Location_of_West_Lake_map.jpg"
    )
    candidate["factEvidence"][0]["evidenceRef"] = primary["bodyEvidenceRef"]
    candidate["factEvidence"][0]["contentSha256"] = primary[
        "bodyContentSha256"
    ]
    raw_ref = "raw/homepage/homepage-west-lake-0.json"
    raw_document = {
        "responses": [
            {
                "query": {
                    "pages": {
                        "1": {
                            "pageid": 1,
                            "title": "西湖-0",
                            "revisions": [
                                {
                                    "revid": 9,
                                    "slots": {
                                        "main": {
                                            "*": (
                                                "{{Infobox place\n"
                                                "| name = 西湖-0\n"
                                                "| map = Location_of_West_Lake_map.jpg\n"
                                                "| caption = 西湖位置图\n"
                                                "| website = https://example.test/official\n"
                                                "}}\n"
                                                "== 概述 ==\n"
                                                "西湖-0是测试百科正文。"
                                            )
                                        }
                                    },
                                }
                            ],
                        }
                    }
                }
            }
        ]
    }
    _write_json(tmp_path / raw_ref, raw_document)
    coverage_key = {
        "coverageEntityIdentity": "name_location:西湖-0|浙江省|杭州市|西湖区",
        "coverageRecordDigest": _digest("coverage:homepage:西湖-0"),
        "entityRef": candidate["entityRef"],
        "carrier": "homepage",
        "sourceUrl": primary["sourceUrl"],
    }
    seed_id = _document_digest(
        {"seedOrigin": "current_coverage", "coverageKey": coverage_key}
    )
    acquisition_asset = {
        **{
            field: hero[field]
            for field in (
                "assetId",
                "assetRef",
                "originalAssetUrl",
                "sourcePageUrl",
                "platform",
                "provider",
                "creator",
                "capturedAt",
                "license",
                "termsUrl",
                "authorizationProof",
                "authorizationRequired",
                "rightsStatus",
                "rightsIssues",
                "acquisitionStatus",
                "distributionDecision",
                "contentSha256",
                "qualityStatus",
                "safetyStatus",
                    "generated",
                    "accessEvidence",
                    "usageScope",
                    "modelReleaseStatus",
            )
        },
        "role": "hero",
        "fileSha256": hero["contentSha256"],
        "byteCount": 1,
        "width": 64,
        "height": 64,
        "safetyEvidence": {
            "status": "safe",
            "faces": 0,
            "hasWatermark": False,
            "textAreaRatio": 0.0,
            "reasons": [],
            "backends": ["fixture_decode", "fixture_ocr"],
        },
    }
    stable_evidence = {
        "schema": "quwoquan_data.homepage_article_source_ready_acquisition_evidence",
        "carrier": "homepage",
        "candidateId": candidate["candidateId"],
        "entityRef": candidate["entityRef"],
        **IDENTITY,
        "capturedAt": primary["capturedAt"],
        "sourceAttribution": candidate["sourceAttribution"],
        "publishMediaMode": "illustrated",
        "seedSelection": {
            "ref": "seed-selection.json",
            "digest": _digest("seed-selection"),
            "fileSha256": _digest("seed-selection-file"),
        },
        "seed": {
            "seedOrigin": "current_coverage",
            "seedId": seed_id,
            "coverageKey": coverage_key,
        },
        "sourceUnit": {
            "sourceUnitId": primary["sourceUnitId"],
            "sourceUnitRef": primary["sourceUnitRef"],
            "sourceUnitDigest": primary["sourceUnitDigest"],
            "sourceUrl": primary["sourceUrl"],
            "sourceKind": primary["sourceKind"],
            "extractor": primary["extractor"],
            "resolvedTitle": "西湖-0",
            "pageId": 1,
            "revisionId": 9,
            "bodyEvidenceRef": primary["bodyEvidenceRef"],
            "bodyContentSha256": primary["bodyContentSha256"],
            "bodyFileSha256": primary["bodyContentSha256"],
            "accessEvidence": primary["accessEvidence"],
            "qualityStatus": "passed",
            "qualityScore": 100,
            "qualityReasons": ["fixture_exact_mediawiki"],
            "rawEvidenceRef": raw_ref,
            "rawEvidenceFileSha256": _file_digest(tmp_path / raw_ref),
        },
        "assets": [acquisition_asset],
    }
    evidence = {
        **stable_evidence,
        "evidenceDigest": _document_digest(stable_evidence),
    }
    evidence_ref = "acquisition-evidence/homepage/evidence.json"
    _write_json(tmp_path / evidence_ref, evidence)
    capsule = {
        "carrier": "homepage",
        **IDENTITY,
        "candidate": candidate,
        "provenance": {
            "seedOrigin": "current_coverage",
            "seedId": seed_id,
            "coverageKey": coverage_key,
            "discoveryEvidenceRef": evidence_ref,
        },
    }

    layout, metadata, funnel = _frozen_homepage_media_inputs(
        capsule=capsule,
        evidence_root=tmp_path,
    )

    assert layout["figureCount"] == 1
    assert layout["blocks"][0]["placementType"] == "locatorMap"
    assert layout["blocks"][0]["coverCandidateRank"] == -1
    assert metadata[str(hero["assetId"])]["isMapLike"] is True
    assert metadata[str(hero["assetId"])]["pageRevisionId"] == 9
    assert funnel == {
        "candidateCount": 1,
        "keptCount": 1,
        "droppedCount": 0,
        "dedupeRemoved": 0,
        "drops": [],
        "fetchFailures": [],
    }
