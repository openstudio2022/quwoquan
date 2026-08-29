"""scale source pool homepage/article 合约测试共享常量与 catalog 构建器。

spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-004.t1

由 test_scale_source_pool_homepage_article__catalog_projection_* 场景组
测试文件共享；从原单体测试文件逐字下沉，不改变任何 fixture 逻辑。
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path

from content.source.research.article_frontier_profile import (
    article_profile_digest,
    article_search_sites,
)
from content.source.research.article_source_unit_catalog import (
    ARTICLE_SOURCE_POLICY_REVISION,
    build_article_source_unit_catalog,
    write_create_once_article_source_unit_catalog,
)
from content.source.research.homepage_source_unit_catalog import (
    build_homepage_source_unit_catalog,
    write_create_once_homepage_source_unit_catalog,
)
from PIL import Image


IDENTITY = {
    "sourceRevision": "sha256:" + "a" * 64,
    "sourceDigest": "sha256:" + "b" * 64,
    "entityCatalogDigest": "sha256:" + "c" * 64,
}


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _document_digest(value: dict[str, object]) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_evidence_file(path: Path, value: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return _file_digest(path)


def _image_bytes(seed: str) -> bytes:
    color = tuple(hashlib.sha256(seed.encode("utf-8")).digest()[:3])
    image = Image.new("RGB", (64, 64), color)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _write_evidence_bytes(path: Path, value: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)
    return _file_digest(path)


def _access() -> dict[str, bool]:
    return {
        "anonymousPublicAccess": True,
        "loginRequired": False,
        "captchaRequired": False,
        "paywallRequired": False,
        "drmProtected": False,
        "accessControlBypass": False,
    }


def _source_attribution(*, platform: str, source_url: str, asset_url: str) -> dict[str, object]:
    return {
        "isOriginal": False,
        "originalCreatorName": "来源作者",
        "platform": platform,
        "sourcePostUrl": source_url,
        "originalAssetUrl": asset_url,
        "attributionText": f"来源作者 / {platform}",
        "rightsBasis": "public research reference",
        "commercialAuthorizationStatus": "unverified",
        "publicationAdmission": "research_release",
        "watermarkStatus": "absent",
        "audioRightsStatus": "no_audio",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "collectedAt": "2026-08-08T00:00:00Z",
        "takedownPolicy": "remove on substantiated request",
        "derivedModifications": [],
    }


def _homepage_candidate(index: int = 0) -> dict[str, object]:
    entity_ref = f"/entity/地点/景区/西湖-{index}"
    source_url = f"https://zh.wikipedia.org/wiki/西湖-{index}"
    fact_url = f"https://example.test/{index}/opening-hours"
    return {
        "candidateId": f"homepage-west-lake-{index}",
        "entityRef": entity_ref,
        "observedEntityRef": entity_ref,
        **IDENTITY,
        "sourceAttribution": _source_attribution(
            platform="维基百科",
            source_url=source_url,
            asset_url=f"https://images.example.test/{index}/hero-original.jpg",
        ),
        "primarySource": {
            "sourceUnitId": f"homepage-unit-{index}",
            "sourceUnitRef": f"sources/homepage-unit-{index}",
            "sourceUnitDigest": _digest(f"homepage-unit:{index}"),
            "sourceKind": "wikipedia",
            "platform": "维基百科",
            "extractor": "wikipedia_api",
            "policyRevision": "encyclopedia-primary",
            "sourceUrl": source_url,
            "capturedAt": "2026-08-08T00:00:00Z",
            "bodyEvidenceRef": f"sources/homepage-unit-{index}/source.md",
            "bodyContentSha256": _digest(f"body:homepage-west-lake-{index}"),
            "accessEvidence": _access(),
        },
        "structuredFacts": {
            "openingHours": [{"openMinuteOfDay": 480, "closeMinuteOfDay": 1080}],
            "factSources": [
                {
                    "field": "openingHours",
                    "sourceId": "official_site",
                    "sourceClass": "official_site",
                    "sourceUrl": fact_url,
                    "observedAt": "2026-08-08T00:00:00Z",
                    "confidence": 0.98,
                }
            ],
        },
        "factEvidence": [
            {
                "field": "openingHours",
                "sourceId": "official_site",
                "sourceUrl": fact_url,
                "evidenceRef": f"facts/{index}/opening-hours.json",
                "contentSha256": _digest(f"fact:{index}"),
                "accessEvidence": _access(),
            }
        ],
        "factConflicts": [],
        "hero": {
            "assetId": f"hero-{index}",
            "entityRef": entity_ref,
            "observedEntityRef": entity_ref,
            "sourceUnitRef": f"sources/homepage-media-{index}",
            "sourceUnitDigest": _digest(f"homepage-media:{index}"),
            "assetRef": f"sources/homepage-media-{index}/assets/hero.jpg",
            "originalAssetUrl": f"https://images.example.test/{index}/hero-original.jpg",
            "sourcePageUrl": f"https://gallery.example.test/{index}/hero",
            "platform": "专业摄影图库",
            "provider": "public_gallery",
            "creator": f"摄影师-{index}",
            "capturedAt": "2026-08-08T00:00:00Z",
            "contentSha256": "sha256:" + hashlib.sha256(
                _image_bytes(f"homepage-west-lake-{index}:hero-{index}")
            ).hexdigest(),
            "license": "authorization pending",
            "termsUrl": "https://gallery.example.test/terms",
            "authorizationProof": "",
            "authorizationRequired": True,
            "rightsStatus": "unverified",
            "rightsIssues": ["authorization pending"],
            "usageScope": "internal_reference",
            "modelReleaseStatus": "not_required",
            "acquisitionStatus": "acquired",
            "distributionDecision": "research_allowed",
            "qualityStatus": "passed",
            "safetyStatus": "passed",
            "generated": False,
            "accessEvidence": _access(),
        },
    }


def _article_candidate(
    index: int = 0,
    *,
    content_seed: int | None = None,
) -> dict[str, object]:
    content_index = index if content_seed is None else content_seed
    source_unit_id = f"article-unit-{index}"
    source_unit_ref = f"sources/{source_unit_id}"
    source_url = f"https://zh.wikipedia.org/wiki/杭州-{index}"
    site = {
        str(row["siteId"]): row for row in article_search_sites()
    }["wikipedia_zh"]
    entity_ref = f"/entity/地点/景区/杭州-{index}"
    assets = []
    for role in ("cover", "body"):
        assets.append(
            {
                "assetId": f"article-{index}-{role}",
                "role": role,
                "sourceUnitId": source_unit_id,
                "sourceUnitRef": source_unit_ref,
                "assetRef": f"{source_unit_ref}/assets/{role}.jpg",
                "originalAssetUrl": f"https://images.example.test/{index}/{role}-original.jpg",
                "sourcePageUrl": source_url,
                "platform": str(site["platform"]),
                "provider": str(site["siteId"]),
                "creator": f"摄影师-{index}-{role}",
                "capturedAt": "2026-08-08T00:00:00Z",
                "contentSha256": "sha256:" + hashlib.sha256(
                    _image_bytes(
                        f"article-hangzhou-{index}:article-{index}-{role}"
                    )
                ).hexdigest(),
                "license": "CC BY-SA 4.0",
                "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                "authorizationProof": "",
                "authorizationRequired": True,
                "rightsStatus": "unverified",
                "rightsIssues": ["attribution review pending"],
                "acquisitionStatus": "acquired",
                "distributionDecision": "research_allowed",
                "qualityStatus": "passed",
                "safetyStatus": "passed",
                "generated": False,
            }
        )
    return {
        "candidateId": f"article-hangzhou-{index}",
        "entityRef": entity_ref,
        "observedEntityRef": entity_ref,
        **IDENTITY,
        "sourceAttribution": _source_attribution(
            platform=str(site["platform"]),
            source_url=source_url,
            asset_url=f"https://images.example.test/{index}/cover-original.jpg",
        ),
        "publishMediaMode": "illustrated",
        "sourceUnitId": source_unit_id,
        "sourceUnitRef": source_unit_ref,
        "sourceUnitDigest": _digest(f"article-unit:{index}"),
        "articleSiteId": str(site["siteId"]),
        "sourceDiscoveryProfileDigest": article_profile_digest(site),
        "sourceKind": str(site["category"]),
        "platform": str(site["platform"]),
        "extractor": str(site["extractor"]),
        "policyRevision": ARTICLE_SOURCE_POLICY_REVISION,
        "sourceUrl": source_url,
        "capturedAt": "2026-08-08T00:00:00Z",
        "bodyEvidenceRef": f"{source_unit_ref}/source.md",
        "bodyContentSha256": _digest(
            f"body:article-hangzhou-{content_index}"
        ),
        "accessEvidence": _access(),
        "assets": assets,
    }


def _photography_article_candidate(index: int = 0) -> dict[str, object]:
    candidate = _article_candidate(index)
    body_sha = str(candidate["bodyContentSha256"])
    entity_ref = str(candidate["entityRef"])
    stable = {
        "schema": "quwoquan_data.article_source_classification",
        "classifierVersion": "article-source-topic-v1",
        "articleCategory": "photography",
        "writingIntent": "planning_consultation",
        "topicTagRefs": ["Topic/旅行/玩法/摄影旅拍"],
        "requestedTopic": "摄影",
        "entityRef": entity_ref,
        "entityName": entity_ref.rsplit("/", 1)[-1],
        "entityMatched": True,
        "photographyIntentMatched": True,
        "discoveryQuery": f"{entity_ref.rsplit('/', 1)[-1]} 摄影",
        "sourceTitle": f"{entity_ref.rsplit('/', 1)[-1]}摄影机位攻略",
        "matchedTitleSignals": ["摄影", "机位"],
        "matchedBodySignals": ["机位", "构图", "焦段"],
        "bodyContentSha256": body_sha,
    }
    candidate.update(
        {
            "articleCategory": "photography",
            "writingIntent": "planning_consultation",
            "topicTagRefs": ["Topic/旅行/玩法/摄影旅拍"],
            "sourceClassification": {
                **stable,
                "classificationDigest": _document_digest(stable),
            },
        }
    )
    return candidate


def _catalogs(
    root: Path,
    *,
    homepage_candidates: list[dict[str, object]] | None = None,
    article_candidates: list[dict[str, object]] | None = None,
    article_identity: dict[str, str] | None = None,
) -> tuple[dict[str, object], dict[str, object], Path, Path]:
    homepage = build_homepage_source_unit_catalog(
        catalog_id="homepage-catalog",
        created_at="2026-08-08T00:00:00Z",
        minimum_candidate_count=1,
        candidates=homepage_candidates or [_homepage_candidate()],
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
    )
    article_ids = article_identity or IDENTITY
    article_rows = copy.deepcopy(
        article_candidates or [_article_candidate()]
    )
    for row in article_rows:
        row.update(article_ids)
    article = build_article_source_unit_catalog(
        catalog_id="article-catalog",
        created_at="2026-08-08T00:00:00Z",
        minimum_candidate_count=1,
        candidates=article_rows,
        source_revision=article_ids["sourceRevision"],
        source_digest=article_ids["sourceDigest"],
        entity_catalog_digest=article_ids["entityCatalogDigest"],
    )
    homepage_path = root / "catalogs" / "homepage.json"
    article_path = root / "catalogs" / "article.json"
    write_create_once_homepage_source_unit_catalog(homepage_path, homepage)
    write_create_once_article_source_unit_catalog(article_path, article)
    return homepage, article, homepage_path, article_path
