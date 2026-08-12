from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from content.source.research.homepage_article_source_ready_baike import (
    acquire_baike_homepage_source_ready_candidate,
)
from content.source.research.homepage_article_source_ready_batch import (
    HomepageArticleSourceReadyBatchError,
    validate_source_ready_candidate_capsule,
)
from content.source.research.homepage_article_source_ready_evidence import (
    canonical_digest,
    file_sha256,
    write_create_once_json,
)
from content.source.research.homepage_article_source_ready_mediawiki import (
    AcquiredAsset,
    MediaWikiSourceReadyRejected,
)
from content.source.research.homepage_article_seed_selection import seed_id
from content.source.research.homepage_source_unit_catalog import (
    build_homepage_source_unit_catalog,
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


def _planned(source_kind: str = "baidu_baike") -> dict[str, object]:
    source_url = (
        "https://baike.baidu.com/item/%E6%B5%8B%E8%AF%95%E9%9B%AA%E5%B1%B1"
        if source_kind == "baidu_baike"
        else "https://www.baike.com/wiki/%E6%B5%8B%E8%AF%95%E9%9B%AA%E5%B1%B1"
    )
    return {
        "coverageEntityIdentity": "name_location:测试雪山|四川省|成都市|都江堰市",
        "candidateName": "测试雪山",
        "entityType": "地点/景区",
        "source": {
            "sourceKind": source_kind,
            "extractor": (
                "baidu_baike_html"
                if source_kind == "baidu_baike"
                else "toutiao_baike_html"
            ),
            "sourceUrl": source_url,
            "observedAt": CAPTURED_AT,
        },
    }


def _asset(source_unit_ref: str) -> AcquiredAsset:
    body = b"safe-open-image"
    digest = _sha(body)
    return AcquiredAsset(
        body=body,
        document={
            "assetId": "asset-test-snow-mountain",
            "role": "hero",
            "assetRef": (
                f"{source_unit_ref}/assets/{digest.removeprefix('sha256:')}.jpg"
            ),
            "originalAssetUrl": "https://upload.wikimedia.org/test-snow-mountain.jpg",
            "sourcePageUrl": "https://commons.wikimedia.org/wiki/File:Test.jpg",
            "platform": "维基共享资源",
            "provider": "wikimedia_commons",
            "creator": "Fixture Creator",
            "capturedAt": CAPTURED_AT,
            "contentSha256": digest,
            "license": "CC BY-SA 4.0",
            "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
            "authorizationProof": "https://commons.wikimedia.org/wiki/File:Test.jpg",
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
    )


@pytest.mark.parametrize("source_kind", ("baidu_baike", "toutiao_baike"))
def test_baike_homepage_freezes_body_fact_commons_hero_and_physical_evidence(
    source_kind: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from content.source.research import (
        homepage_article_source_ready_acquisition as batch,
    )
    from content.source.research import homepage_article_source_ready_baike as provider

    provider_title = "百度百科" if source_kind == "baidu_baike" else "快懂百科"
    raw = f"<html><title>测试雪山 - {provider_title}</title></html>".encode()
    text = (
        "测试雪山位于四川省成都市，主峰海拔三千米，景区海拔3000米。"
        "测试雪山形成于漫长的地质演化期，占地范围包括高山森林与河谷。"
        "景区开放区域设有徒步路线、生态展示和观景平台，交通可从城区换乘。"
        "游客参观时应遵守生态保护要求，并根据天气调整游览计划。"
    )
    fetch_responses = iter(
        (
            {"htmlBytes": b"<html><title>loading</title></html>", "text": ""},
            {"htmlBytes": raw, "text": text},
        )
    )
    fetch_calls: list[str] = []

    def fetch(*args: object, **kwargs: object) -> dict[str, object]:
        fetch_calls.append(str(args[0]))
        return next(fetch_responses)

    monkeypatch.setattr(provider, "fetch_source_payload", fetch)
    monkeypatch.setattr(
        provider,
        "commons_images_for_entity",
        lambda *args, **kwargs: [{"url": "https://upload.wikimedia.org/test.jpg"}],
    )
    monkeypatch.setattr(
        provider,
        "openverse_images_for_entity",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        provider,
        "acquire_open_image_assets",
        lambda rows, *, source_unit_ref, **kwargs: (_asset(source_unit_ref),),
    )

    acquired = acquire_baike_homepage_source_ready_candidate(
        _planned(source_kind),
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
        captured_at=CAPTURED_AT,
    )

    assert acquired.candidate["primarySource"]["sourceKind"] == source_kind
    assert acquired.candidate["structuredFacts"]["altitudeMeters"] == 3000
    assert len(fetch_calls) == 2
    assert acquired.candidate["hero"]["entityRef"] == acquired.candidate["entityRef"]
    assert "pageId" not in acquired.source_unit
    build_homepage_source_unit_catalog(
        catalog_id="baike-homepage",
        catalog_version="v1",
        created_at=CAPTURED_AT,
        minimum_candidate_count=1,
        candidates=[acquired.candidate],
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
    )
    coverage_stable = {
        "schema": "quwoquan_data.coverage_source_ready_catalog_projection",
        **IDENTITY,
        "plannedCandidates": [_planned(source_kind)],
    }
    coverage = {
        **coverage_stable,
        "projectionDigest": canonical_digest(coverage_stable),
    }
    coverage_path = write_create_once_json(
        tmp_path / "coverage-projection.json", coverage
    )
    coverage_key = {
        "coverageEntityIdentity": "name_location:测试雪山|四川省|成都市|都江堰市",
        "coverageRecordDigest": _sha(b"coverage-record"),
        "entityRef": acquired.candidate["entityRef"],
        "carrier": "homepage",
        "sourceUrl": _planned(source_kind)["source"]["sourceUrl"],
    }
    seed = {
        "seedOrigin": "current_coverage",
        "seedId": seed_id(
            seed_origin="current_coverage", coverage_key=coverage_key
        ),
        "coverageKey": coverage_key,
        "candidateName": "测试雪山",
        "province": "四川省",
        "city": "成都市",
        "district": "都江堰市",
        "entityType": "地点/景区",
        "sourceKind": source_kind,
        "extractor": _planned(source_kind)["source"]["extractor"],
    }
    seed_selection_stable = {
        "schema": "quwoquan_data.homepage_article_seed_selection",
        "seedSetId": f"test-{source_kind}",
        "counts": {"homepage": 1, "article": 0},
        "seeds": [seed],
    }
    seed_selection = {
        **seed_selection_stable,
        "selectionDigest": canonical_digest(seed_selection_stable),
    }
    seed_selection_path = write_create_once_json(
        tmp_path / "seed-selection.json", seed_selection
    )
    binding = batch._write_acquired_candidate(
        acquired,
        evidence_root=tmp_path,
        identity=IDENTITY,
        captured_at=CAPTURED_AT,
        coverage_binding={
            "ref": "coverage-projection.json",
            "digest": coverage["projectionDigest"],
            "fileSha256": file_sha256(coverage_path),
        },
        seed_selection_binding={
            "ref": "seed-selection.json",
            "digest": seed_selection["selectionDigest"],
            "fileSha256": file_sha256(seed_selection_path),
        },
        seed=seed,
    )
    capsule = json.loads((tmp_path / binding["ref"]).read_text())
    assert capsule["candidate"]["primarySource"]["sourceKind"] == source_kind
    raw_path = tmp_path / f"raw/homepage/{acquired.candidate['candidateId']}.json"
    raw_path.write_bytes(b"tampered")
    with pytest.raises(HomepageArticleSourceReadyBatchError, match="rawEvidence"):
        validate_source_ready_candidate_capsule(capsule, evidence_root=tmp_path)


def test_baike_structured_facts_freeze_season_or_https_official_website() -> None:
    from content.source.research.homepage_article_source_ready_baike import (
        _structured_fact_from_text,
    )

    season, season_evidence = _structured_fact_from_text(
        "测试山最佳游览季节是春季和秋季。",
        raw_html=b"<html></html>",
        source_kind="toutiao_baike",
        source_url=_planned("toutiao_baike")["source"]["sourceUrl"],
        body_ref="sources/test/source.md",
        raw_ref="raw/homepage/test.json",
        body_sha256=_sha(b"season"),
        captured_at=CAPTURED_AT,
    )
    assert season["bestSeasonTagRefs"] == [
        "Topic/时间/四季/春季",
        "Topic/时间/四季/秋季",
    ]
    assert season_evidence[0]["evidenceRef"] == "sources/test/source.md"

    official, official_evidence = _structured_fact_from_text(
        "测试县位于四川省，辖区包含多个公共服务区域。",
        raw_html=(
            b'<script>{"property_id":"\xe6\x94\xbf\xe5\xba\x9c\xe5\xae\x98\xe6\x96\xb9'
            b'\xe7\xbd\x91\xe7\xab\x99","url":"https://www.test.gov.cn/"}</script>'
        ),
        source_kind="toutiao_baike",
        source_url=_planned("toutiao_baike")["source"]["sourceUrl"],
        body_ref="sources/test/source.md",
        raw_ref="raw/homepage/test.json",
        body_sha256=_sha(b"official"),
        captured_at=CAPTURED_AT,
    )
    assert official["officialWebsite"] == "https://www.test.gov.cn/"
    assert official_evidence[0]["evidenceRef"] == "raw/homepage/test.json"


def test_baike_homepage_rejects_source_identity_outside_registry() -> None:
    planned = _planned()
    planned["source"] = {
        **planned["source"],
        "sourceUrl": "https://example.test/not-baike",
    }
    with pytest.raises(MediaWikiSourceReadyRejected, match="closed set"):
        acquire_baike_homepage_source_ready_candidate(
            planned,
            source_revision=IDENTITY["sourceRevision"],
            source_digest=IDENTITY["sourceDigest"],
            entity_catalog_digest=IDENTITY["entityCatalogDigest"],
            captured_at=CAPTURED_AT,
        )
