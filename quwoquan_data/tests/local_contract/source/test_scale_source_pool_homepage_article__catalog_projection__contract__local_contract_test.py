# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-004.t1
from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path

import pytest
from content.execution.campaign.external_input_runtime import (
    ExternalInputRuntimeContext,
    bind_runtime_external_input_context,
)
from content.execution.campaign.source_pool_binding import (
    bind_scale_source_pool,
    materialize_bound_scale_source_pool,
    validate_capsule_scale_source_pool,
)
from content.source.research.article_frontier_profile import (
    article_profile_digest,
    article_search_sites,
)
from content.source.research.article_source_unit_catalog import (
    ARTICLE_SOURCE_POLICY_REVISION,
    build_article_source_unit_catalog,
    write_create_once_article_source_unit_catalog,
)
from content.source.research.auto_plan_writer import _write_auto_research_plans_impl
from content.source.research.homepage_source_unit_catalog import (
    build_homepage_source_unit_catalog,
    write_create_once_homepage_source_unit_catalog,
)
from content.source.research.scale_source_pool import (
    build_scale_source_pool_plan,
    validate_scale_source_pool_evidence,
)
from content.source.research.scale_source_pool_homepage_article import (
    PROJECTION_INVALID,
    ScaleSourcePoolProjectionError,
    project_scale_source_pool_homepage_article,
)
from content.source.research.scale_source_pool_runtime import (
    ScaleSourcePoolRuntimeError,
    _frozen_homepage_media_inputs,
    frozen_scale_source_pool_candidates,
    frozen_scale_source_pool_targets,
    materialize_frozen_scale_source_pool_entity,
    select_frozen_source_pool_targets,
)
from core.carrier_contract import research_plan_files
from PIL import Image

IDENTITY = {
    "sourceRevision": "sha256:" + "a" * 64,
    "sourceDigest": "sha256:" + "b" * 64,
    "entityCatalogDigest": "sha256:" + "c" * 64,
}


def test_frozen_source_pool_selection_joins_exact_governed_geo_target(
    tmp_path: Path,
) -> None:
    discovery = tmp_path / "entities"
    province = discovery / "四川省"
    province.mkdir(parents=True)
    (province / "成都市.yaml").write_text(
        """schema: quwoquan_data.discovery_seed
country: 中国
province: 四川省
city: 成都市
districts:
- district: 都江堰市
  leaves:
  - name: 都江堰
    canonicalName: 都江堰
    entityType: 地点/景区
    geoTagRef: Topic/地理/行政区/中国/四川省/成都市/都江堰市
    typeTagRefs:
    - Entity/地点/景区/世界遗产
""",
        encoding="utf-8",
    )

    rows, report = select_frozen_source_pool_targets(
        targets=({"entityType": "地点/景区", "name": "都江堰"},),
        requested_limit=1,
        approved_quota=1,
        target_names=("都江堰",),
        discovery_path=discovery,
        pool_binding={"planDigest": "sha256:" + "d" * 64},
        lane_selection={
            "candidateCount": 1,
            "selectionDigest": "sha256:" + "e" * 64,
        },
    )

    assert rows == [
        {
            "entityType": "地点/景区",
            "name": "都江堰",
            "geoTagRef": "Topic/地理/行政区/中国/四川省/成都市/都江堰市",
            "typeTagRefs": ["Entity/地点/景区/世界遗产"],
        }
    ]
    assert report["selectionAuthority"] == "frozen_scale_source_pool"


def test_frozen_source_pool_selection_nfkc_normalizes_exact_canonical_name(
    tmp_path: Path,
) -> None:
    discovery = tmp_path / "entities"
    province = discovery / "浙江省"
    province.mkdir(parents=True)
    (province / "台州市.yaml").write_text(
        """schema: quwoquan_data.discovery_seed
country: 中国
province: 浙江省
city: 台州市
districts:
- district: 天台县
  leaves:
  - name: 天台山
    canonicalName: 天台山（台州）
    entityType: 地点/景区
    geoTagRef: Topic/地理/行政区/中国/浙江省/台州市/天台县
    typeTagRefs:
    - Entity/地点/景区
""",
        encoding="utf-8",
    )

    rows, _report = select_frozen_source_pool_targets(
        targets=({"entityType": "地点/景区", "name": "天台山(台州)"},),
        requested_limit=1,
        approved_quota=1,
        target_names=("天台山(台州)",),
        discovery_path=discovery,
        pool_binding={"planDigest": "sha256:" + "d" * 64},
        lane_selection={
            "candidateCount": 1,
            "selectionDigest": "sha256:" + "e" * 64,
        },
    )

    assert rows[0]["name"] == "天台山(台州)"
    assert rows[0]["geoTagRef"].endswith("/天台县")


def test_frozen_source_pool_selection_joins_exact_admin_regions_in_frozen_order(
    tmp_path: Path,
) -> None:
    entity_refs = (
        "/entity/地点/城市/四川省",
        "/entity/地点/城市/四川省乐山市",
        "/entity/地点/城市/四川省乐山市夹江县",
        "/entity/地点/城市/四川省乐山市沙湾区",
        "/entity/地点/城市/四川省乐山市马边彝族自治县",
        "/entity/地点/城市/四川省内江市威远县",
        "/entity/地点/城市/四川省凉山彝族自治州",
        "/entity/地点/城市/四川省凉山彝族自治州西昌市",
        "/entity/地点/城市/四川省南充市",
        "/entity/地点/城市/四川省南充市阆中市",
        "/entity/地点/城市/四川省宜宾市",
        "/entity/地点/城市/四川省成都市",
    )
    targets = tuple(
        {
            "entityType": "地点/城市",
            "name": entity_ref.rsplit("/", 1)[-1],
            "canonicalEntityRef": entity_ref,
        }
        for entity_ref in entity_refs
    )

    rows, report = select_frozen_source_pool_targets(
        targets=targets,
        requested_limit=12,
        approved_quota=12,
        target_names=tuple(row["name"] for row in targets),
        # 行政实体只能来自 canonical pca projection；这里故意不给旅游 master。
        discovery_path=tmp_path / "absent-tourism-master",
        pool_binding={"planDigest": "sha256:" + "d" * 64},
        lane_selection={
            "candidateCount": 12,
            "selectionDigest": "sha256:" + "e" * 64,
        },
    )

    assert [row["canonicalEntityRef"] for row in rows] == list(entity_refs)
    assert [row["name"] for row in rows] == [row["name"] for row in targets]
    assert all(row["geoTagRef"].startswith("Topic/地理/行政区/中国/四川省") for row in rows)
    assert all(row["typeTagRefs"] == ["Entity/地点/城市"] for row in rows)
    assert report["selectedCount"] == 12


def test_frozen_source_pool_selection_rejects_admin_canonical_ref_drift(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ScaleSourcePoolRuntimeError,
        match="missing governed admin target for 地点/城市/四川省",
    ):
        select_frozen_source_pool_targets(
            targets=(
                {
                    "entityType": "地点/城市",
                    "name": "四川省",
                    "canonicalEntityRef": "/entity/地点/城市/冒名四川省",
                },
            ),
            requested_limit=1,
            approved_quota=1,
            target_names=("四川省",),
            discovery_path=tmp_path / "absent-tourism-master",
            pool_binding={"planDigest": "sha256:" + "d" * 64},
            lane_selection={
                "candidateCount": 1,
                "selectionDigest": "sha256:" + "e" * 64,
            },
        )


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
        catalog_version="2026-08-08.1",
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
        catalog_version="2026-08-08.1",
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


def test_photography_article_runtime_freezes_category_and_source_title(
) -> None:
    """The frozen category must survive projection into the runtime source unit."""

    candidate = _photography_article_candidate()
    article = build_article_source_unit_catalog(
        catalog_id="photography-article",
        catalog_version="2026-08-12.1",
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


def _source_ready_batch(
    root: Path,
    *,
    homepage_candidates: list[dict[str, object]],
    article_candidates: list[dict[str, object]],
    per_member_roots: bool = False,
) -> tuple[str, str, str]:
    coverage_ref = "coverage/projection.json"
    coverage_digest = "sha256:" + "f" * 64
    _write_json(
        root / coverage_ref,
        {"schema": "test.coverage_projection", "projectionDigest": coverage_digest},
    )
    seeds = []
    seeds_by_candidate_id: dict[str, dict[str, object]] = {}
    for carrier, candidates in (
        ("homepage", homepage_candidates),
        ("article", article_candidates),
    ):
        for candidate in candidates:
            source = candidate["primarySource"] if carrier == "homepage" else candidate
            assert isinstance(source, dict)
            entity_ref = str(candidate["entityRef"])
            candidate_name = entity_ref.rsplit("/", 1)[-1]
            coverage_key = {
                "coverageEntityIdentity": (
                    f"name_location:{candidate_name}|浙江省|杭州市|西湖区"
                ),
                "coverageRecordDigest": _digest(
                    f"coverage:{carrier}:{entity_ref}:{source['sourceUrl']}"
                ),
                "entityRef": entity_ref,
                "carrier": carrier,
                "sourceUrl": source["sourceUrl"],
            }
            seed = {
                "seedOrigin": "current_coverage",
                "seedId": _document_digest(
                    {
                        "seedOrigin": "current_coverage",
                        "coverageKey": coverage_key,
                    }
                ),
                "coverageKey": coverage_key,
                "candidateName": entity_ref.rsplit("/", 1)[-1],
                "province": "浙江省",
                "city": "杭州市",
                "district": "西湖区",
                "entityType": "/".join(entity_ref.split("/")[2:4]),
                "sourceKind": "wikipedia",
                "extractor": "wikipedia_api",
            }
            seeds.append(seed)
            seeds_by_candidate_id[str(candidate["candidateId"])] = seed
    stable_seed_selection = {
        "schema": "quwoquan_data.homepage_article_seed_selection",
        "seedSetId": "projection-test-seeds",
        "counts": {
            "homepage": len(homepage_candidates),
            "article": len(article_candidates),
        },
        "seeds": seeds,
    }
    seed_selection = {
        **stable_seed_selection,
        "selectionDigest": _document_digest(stable_seed_selection),
    }
    seed_selection_ref = "seed-selection.json"
    _write_json(root / seed_selection_ref, seed_selection)
    seed_selection_binding = {
        "ref": seed_selection_ref,
        "digest": seed_selection["selectionDigest"],
        "fileSha256": _file_digest(root / seed_selection_ref),
    }
    body_values = {
        _digest(f"body:{candidate['candidateId']}"): f"body:{candidate['candidateId']}"
        for candidate in [*homepage_candidates, *article_candidates]
    }
    capsule_bindings: list[dict[str, object]] = []
    for carrier, candidates in (
        ("homepage", homepage_candidates),
        ("article", article_candidates),
    ):
        for candidate in candidates:
            candidate_id = str(candidate["candidateId"])
            member_root_ref = (
                f"members/{carrier}/{candidate_id}" if per_member_roots else "."
            )
            candidate_root = (
                root / member_root_ref if member_root_ref != "." else root
            )
            candidate_coverage_ref = (
                "shared/coverage.json" if per_member_roots else coverage_ref
            )
            if per_member_roots:
                _write_json(
                    candidate_root / candidate_coverage_ref,
                    {
                        "schema": "test.coverage_projection",
                        "projectionDigest": coverage_digest,
                    },
                )
                candidate_seed_ref = "shared/seed-selection.json"
                _write_json(candidate_root / candidate_seed_ref, seed_selection)
                candidate_seed_binding = {
                    "ref": candidate_seed_ref,
                    "digest": seed_selection["selectionDigest"],
                    "fileSha256": _file_digest(candidate_root / candidate_seed_ref),
                }
            else:
                candidate_seed_binding = seed_selection_binding
            if carrier == "homepage":
                primary = candidate["primarySource"]
                hero = candidate["hero"]
                assert isinstance(primary, dict) and isinstance(hero, dict)
                body_ref = str(primary["bodyEvidenceRef"])
                body_content = str(primary["bodyContentSha256"])
                media_rows = [{
                    "assetId": hero["assetId"],
                    "role": "hero",
                    "ref": hero["assetRef"],
                    "contentSha256": hero["contentSha256"],
                }]
            else:
                body_ref = str(candidate["bodyEvidenceRef"])
                body_content = str(candidate["bodyContentSha256"])
                media_rows = [
                    {
                        "assetId": row["assetId"],
                        "role": row["role"],
                        "ref": row["assetRef"],
                        "contentSha256": row["contentSha256"],
                    }
                    for row in candidate["assets"]
                    if isinstance(row, dict)
                ]
            body_value = body_values.get(body_content)
            if body_value is None:
                raise AssertionError(f"test body content preimage missing: {body_content}")
            body_file_sha = _write_evidence_file(
                candidate_root / body_ref,
                body_value,
            )
            materialized_media: list[dict[str, object]] = []
            for row in media_rows:
                ref = str(row["ref"])
                media_bytes = _image_bytes(f"{candidate_id}:{row['assetId']}")
                assert "sha256:" + hashlib.sha256(media_bytes).hexdigest() == row[
                    "contentSha256"
                ]
                materialized_media.append({
                    **row,
                    "fileSha256": _write_evidence_bytes(
                        candidate_root / ref, media_bytes
                    ),
                })
            evidence_bindings: list[dict[str, str]] = []
            for name in ("discovery", "acquisition", "rights", "quality"):
                ref = (
                    f"provenance/{name}.json"
                    if per_member_roots
                    else f"provenance/{candidate_id}-{name}.json"
                )
                _write_json(
                    candidate_root / ref,
                    {"schema": f"test.{name}", "id": candidate_id},
                )
                evidence_bindings.append({
                    "ref": ref,
                    "fileSha256": _file_digest(candidate_root / ref),
                })
            stable_capsule: dict[str, object] = {
                "schema": "quwoquan_data.homepage_article_source_ready_candidate",
                "carrier": carrier,
                **IDENTITY,
                "candidate": candidate,
                "materialization": {
                    "body": {
                        "ref": body_ref,
                        "contentSha256": body_content,
                        "fileSha256": body_file_sha,
                    },
                    "media": materialized_media,
                },
                "provenance": {
                    "coverageProjectionRef": candidate_coverage_ref,
                    "coverageProjectionDigest": coverage_digest,
                    "coverageProjectionFileSha256": _file_digest(
                        candidate_root / candidate_coverage_ref
                    ),
                    "seedSelectionRef": candidate_seed_binding["ref"],
                    "seedSelectionDigest": candidate_seed_binding["digest"],
                    "seedSelectionFileSha256": candidate_seed_binding["fileSha256"],
                    "seedOrigin": seeds_by_candidate_id[candidate_id]["seedOrigin"],
                    "seedId": seeds_by_candidate_id[candidate_id]["seedId"],
                    "coverageKey": seeds_by_candidate_id[candidate_id]["coverageKey"],
                    "discoveryEvidenceRef": evidence_bindings[0]["ref"],
                    "discoveryEvidenceFileSha256": evidence_bindings[0]["fileSha256"],
                    "acquisitionEvidenceRefs": [evidence_bindings[1]],
                    "rightsEvidenceRefs": [evidence_bindings[2]],
                    "qualityEvidenceRefs": [evidence_bindings[3]],
                },
            }
            capsule = {
                **stable_capsule,
                "capsuleDigest": _document_digest(stable_capsule),
            }
            capsule_ref = (
                "capsule.json"
                if per_member_roots
                else f"capsules/{carrier}/{candidate_id}.json"
            )
            _write_json(candidate_root / capsule_ref, capsule)
            capsule_bindings.append({
                "carrier": carrier,
                "candidateId": candidate_id,
                "evidenceRootRef": member_root_ref,
                "ref": capsule_ref,
                "digest": capsule["capsuleDigest"],
                "fileSha256": _file_digest(candidate_root / capsule_ref),
            })
    stable_batch: dict[str, object] = {
        "schema": "quwoquan_data.homepage_article_source_ready_batch",
        "sourceSetId": "projection-source-set",
        "targetScale": "M100",
        **IDENTITY,
        "createdAt": "2026-08-08T00:00:00Z",
        "coverageProjection": {
            "ref": coverage_ref,
            "digest": coverage_digest,
            "fileSha256": _file_digest(root / coverage_ref),
        },
        "seedSelection": seed_selection_binding,
        "candidateCapsules": capsule_bindings,
        "counts": {
            "homepage": len(homepage_candidates),
            "article": len(article_candidates),
        },
    }
    batch = {**stable_batch, "sourceSetDigest": _document_digest(stable_batch)}
    batch_ref = "batches/homepage-article.json"
    _write_json(root / batch_ref, batch)
    return batch_ref, str(batch["sourceSetDigest"]), _file_digest(root / batch_ref)


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


def _project(
    root: Path,
    *,
    per_member_roots: bool = False,
    **catalog_kwargs: object,
) -> dict[str, object]:
    homepage, article, homepage_path, article_path = _catalogs(
        root, **catalog_kwargs
    )
    batch_ref, batch_digest, batch_file_sha = _source_ready_batch(
        root,
        homepage_candidates=list(homepage["candidates"]),
        article_candidates=list(article["candidates"]),
        per_member_roots=per_member_roots,
    )
    return project_scale_source_pool_homepage_article(
        evidence_root=root,
        homepage_catalog_ref=homepage_path.relative_to(root).as_posix(),
        homepage_catalog_digest=str(homepage["catalogDigest"]),
        homepage_catalog_file_sha256=_file_digest(homepage_path),
        article_catalog_ref=article_path.relative_to(root).as_posix(),
        article_catalog_digest=str(article["catalogDigest"]),
        article_catalog_file_sha256=_file_digest(article_path),
        source_ready_set_ref=batch_ref,
        source_ready_set_digest=batch_digest,
        source_ready_set_file_sha256=batch_file_sha,
    )


def test_projection_is_deterministic_and_contains_no_go_decision(tmp_path: Path) -> None:
    projection = _project(tmp_path)
    replay = _project(tmp_path)

    assert replay == projection
    assert "decision" not in projection
    assert projection["projectionDigest"].startswith("sha256:")
    assert projection["rowCounts"] == [
        {"carrier": "homepage", "candidateCount": 1},
        {"carrier": "article", "candidateCount": 1},
    ]
    rows = {row["carrier"]: row for row in projection["rows"]}
    assert rows["homepage"]["objectRef"].startswith("entities/")
    assert rows["article"]["objectRef"].startswith("posts/article/")
    for row in rows.values():
        for prefix in ("sourceUnit", "acquisition", "rights", "quality"):
            assert row[f"{prefix}Ref"].startswith("capsules/")
            assert row[f"{prefix}Digest"].startswith("sha256:")
            assert row[f"{prefix}FileSha256"].startswith("sha256:")


def test_projection_allows_homepage_only_without_article_catalog(tmp_path: Path) -> None:
    homepage, article, homepage_path, _article_path = _catalogs(tmp_path)
    batch_ref, batch_digest, batch_file_sha = _source_ready_batch(
        tmp_path,
        homepage_candidates=list(homepage["candidates"]),
        article_candidates=list(article["candidates"]),
    )

    projection = project_scale_source_pool_homepage_article(
        evidence_root=tmp_path,
        homepage_catalog_ref=homepage_path.relative_to(tmp_path).as_posix(),
        homepage_catalog_digest=str(homepage["catalogDigest"]),
        homepage_catalog_file_sha256=_file_digest(homepage_path),
        article_catalog_ref=None,
        article_catalog_digest=None,
        article_catalog_file_sha256=None,
        source_ready_set_ref=batch_ref,
        source_ready_set_digest=batch_digest,
        source_ready_set_file_sha256=batch_file_sha,
        active_carriers=("homepage",),
    )

    assert [row["carrier"] for row in projection["rows"]] == ["homepage"]
    assert [row["carrier"] for row in projection["catalogBindings"]] == [
        "homepage",
        "homepage_article_source_set",
    ]


def test_projection_allows_article_only_without_homepage_catalog(tmp_path: Path) -> None:
    homepage, article, _homepage_path, article_path = _catalogs(tmp_path)
    batch_ref, batch_digest, batch_file_sha = _source_ready_batch(
        tmp_path,
        homepage_candidates=list(homepage["candidates"]),
        article_candidates=list(article["candidates"]),
    )

    projection = project_scale_source_pool_homepage_article(
        evidence_root=tmp_path,
        homepage_catalog_ref=None,
        homepage_catalog_digest=None,
        homepage_catalog_file_sha256=None,
        article_catalog_ref=article_path.relative_to(tmp_path).as_posix(),
        article_catalog_digest=str(article["catalogDigest"]),
        article_catalog_file_sha256=_file_digest(article_path),
        source_ready_set_ref=batch_ref,
        source_ready_set_digest=batch_digest,
        source_ready_set_file_sha256=batch_file_sha,
        active_carriers=("article",),
    )

    assert [row["carrier"] for row in projection["rows"]] == ["article"]
    assert [row["carrier"] for row in projection["catalogBindings"]] == [
        "article",
        "homepage_article_source_set",
    ]


def test_projection_rebases_nested_source_set_member_root_to_evidence_root(
    tmp_path: Path,
) -> None:
    homepage, article, homepage_path, article_path = _catalogs(tmp_path)
    source_set_root = tmp_path / "homepage-article-source-ready" / "m100" / "set-1"
    batch_ref, batch_digest, batch_file_sha = _source_ready_batch(
        source_set_root,
        homepage_candidates=list(homepage["candidates"]),
        article_candidates=list(article["candidates"]),
    )
    source_set_ref = (source_set_root / batch_ref).relative_to(tmp_path).as_posix()

    projection = project_scale_source_pool_homepage_article(
        evidence_root=tmp_path,
        homepage_catalog_ref=homepage_path.relative_to(tmp_path).as_posix(),
        homepage_catalog_digest=str(homepage["catalogDigest"]),
        homepage_catalog_file_sha256=_file_digest(homepage_path),
        article_catalog_ref=article_path.relative_to(tmp_path).as_posix(),
        article_catalog_digest=str(article["catalogDigest"]),
        article_catalog_file_sha256=_file_digest(article_path),
        source_ready_set_ref=source_set_ref,
        source_ready_set_digest=batch_digest,
        source_ready_set_file_sha256=batch_file_sha,
    )

    assert {
        row["sourceReadyEvidenceRootRef"] for row in projection["rows"]
    } == {"homepage-article-source-ready/m100/set-1"}


def test_projection_accepts_different_catalog_and_capsule_order(tmp_path: Path) -> None:
    homepage, article, homepage_path, article_path = _catalogs(
        tmp_path,
        homepage_candidates=[_homepage_candidate(0), _homepage_candidate(1)],
    )
    batch_ref, batch_digest, batch_file_sha = _source_ready_batch(
        tmp_path,
        homepage_candidates=list(reversed(homepage["candidates"])),
        article_candidates=list(article["candidates"]),
    )

    projection = project_scale_source_pool_homepage_article(
        evidence_root=tmp_path,
        homepage_catalog_ref=homepage_path.relative_to(tmp_path).as_posix(),
        homepage_catalog_digest=str(homepage["catalogDigest"]),
        homepage_catalog_file_sha256=_file_digest(homepage_path),
        article_catalog_ref=article_path.relative_to(tmp_path).as_posix(),
        article_catalog_digest=str(article["catalogDigest"]),
        article_catalog_file_sha256=_file_digest(article_path),
        source_ready_set_ref=batch_ref,
        source_ready_set_digest=batch_digest,
        source_ready_set_file_sha256=batch_file_sha,
    )

    assert [
        row["candidateId"]
        for row in projection["rows"]
        if row["carrier"] == "homepage"
    ] == ["homepage-west-lake-0", "homepage-west-lake-1"]


def test_text_only_article_projects_without_inventing_media_or_commercial_rights(
    tmp_path: Path,
) -> None:
    article = _article_candidate()
    article["publishMediaMode"] = "text_only"
    article["assets"] = []

    projection = _project(tmp_path, article_candidates=[article])
    row = next(row for row in projection["rows"] if row["carrier"] == "article")

    assert row["publishMediaMode"] == "text_only"
    assert row["distributionDecision"] == "research_allowed"
    assert row["rightsStatus"] == "unverified"


def _clone_row(
    template: dict[str, object],
    *,
    carrier: str,
    index: int,
    provider: str,
) -> dict[str, object]:
    row = copy.deepcopy(template)
    entity_ref = f"/entity/地点/景区/{carrier}-{index:05d}"
    row.update(
        {
            "candidateId": f"{carrier}-{index:05d}",
            "carrier": carrier,
            "objectRef": f"{'entities' if carrier == 'homepage' else f'posts/{carrier}'}/{carrier}-{index:05d}",
            "entityRef": entity_ref,
            "observedEntityRef": entity_ref,
            "provider": provider,
            "contentSha256": _digest(f"projected:{carrier}:{index}"),
        }
    )
    if carrier == "video":
        row.update(
            {
                "playabilityRef": row["sourceUnitRef"],
                "playabilityDigest": _digest(f"playability:{index}"),
                "playabilityFileSha256": row["sourceUnitFileSha256"],
                "videoReadiness": {
                    "playable": True,
                    "motion": True,
                    "premiumEligible": True,
                    "playCount": 10000 + index,
                    "likeCount": 500 + index,
                    "commentCount": 40 + index,
                    "shareCount": 30 + index,
                    "favoriteCount": 200 + index,
                    "observedAt": "2026-08-08T00:00:00Z",
                    "popularityPercentile": round(index / 18, 6),
                    "comparisonBucket": {
                        "provider": provider,
                        "topic": "旅行",
                        "timeBucket": "2026-W32",
                        "candidateCount": 18,
                    },
                },
            }
        )
    else:
        row.update(
            {
                "playabilityRef": None,
                "playabilityDigest": None,
                "playabilityFileSha256": None,
                "videoReadiness": None,
            }
        )
    return row


def test_projected_refs_are_physically_reverified_by_scale_validator(
    tmp_path: Path,
) -> None:
    projection = _project(tmp_path)
    base = {row["carrier"]: row for row in projection["rows"]}
    candidates = [
        *(
            _clone_row(base["homepage"], carrier="homepage", index=index, provider="维基百科")
            for index in range(180)
        ),
        *(
            _clone_row(base["article"], carrier="article", index=index, provider="维基百科")
            for index in range(180)
        ),
    ]
    image_providers = ["Pinterest"] * 80 + ["图虫"] * 20 + ["Pexels"] * 50 + ["Wikimedia Commons"] * 30
    candidates.extend(
        _clone_row(base["article"], carrier="image", index=index, provider=provider)
        for index, provider in enumerate(image_providers)
    )
    candidates.extend(
        _clone_row(base["article"], carrier="video", index=index, provider="Pexels Videos")
        for index in range(18)
    )
    plan = build_scale_source_pool_plan(
        pool_id="projection-physical-proof",
        target_scale="M100",
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
        created_at="2026-08-08T00:00:00Z",
        candidates=candidates,
    )
    evidence = validate_scale_source_pool_evidence(plan, evidence_root=tmp_path)
    assert evidence["evidenceFileSha256Verified"] is True
    assert evidence["evidenceFileCount"] == 2
    assert evidence["evidenceBindingCount"] == 2250


def test_campaign_capsule_copies_only_selected_candidate_capsules_and_cas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "output"
    evidence_root = output_root / "evidence"
    projection = _project(
        evidence_root,
        homepage_candidates=[_homepage_candidate(0), _homepage_candidate(1)],
        article_candidates=[_article_candidate(0), _article_candidate(1)],
        per_member_roots=True,
    )
    rows = {
        (row["carrier"], row["candidateId"]): row for row in projection["rows"]
    }
    homepage_rows = [
        copy.deepcopy(rows[("homepage", f"homepage-west-lake-{index}")])
        for index in range(2)
    ]
    article_rows = [
        copy.deepcopy(rows[("article", f"article-hangzhou-{index}")])
        for index in range(2)
    ]
    candidates = [*homepage_rows, *article_rows]
    candidates.extend(
        _clone_row(homepage_rows[0], carrier="homepage", index=index, provider="维基百科")
        for index in range(2, 180)
    )
    candidates.extend(
        _clone_row(article_rows[0], carrier="article", index=index, provider="Wikivoyage")
        for index in range(2, 180)
    )
    image_providers = (
        ["Pinterest"] * 80 + ["图虫"] * 20
        + ["Pexels"] * 50 + ["Wikimedia Commons"] * 30
    )
    candidates.extend(
        _clone_row(article_rows[0], carrier="image", index=index, provider=provider)
        for index, provider in enumerate(image_providers)
    )
    candidates.extend(
        _clone_row(
            article_rows[0], carrier="video", index=index, provider="Pexels Videos"
        )
        for index in range(18)
    )
    plan = build_scale_source_pool_plan(
        pool_id="selected-only-physical-pool",
        target_scale="M100",
        created_at="2026-08-08T00:00:00Z",
        candidates=candidates,
        **{
            "source_revision": IDENTITY["sourceRevision"],
            "source_digest": IDENTITY["sourceDigest"],
            "entity_catalog_digest": IDENTITY["entityCatalogDigest"],
        },
    )
    plan_path = output_root / "pool/plan.json"
    _write_json(plan_path, plan)
    selections: dict[str, dict[str, object]] = {}
    evidence_ref = ""
    binding: dict[str, object] | None = None
    for carrier in ("homepage", "article", "image", "video"):
        lane_binding, lane_evidence_ref, selection = bind_scale_source_pool(
            plan_path,
            evidence_root=evidence_root,
            output_root=output_root,
            target_scale="M100",
            carrier=carrier,
            count=1,
            source_revision=IDENTITY["sourceRevision"],
            source_digest=IDENTITY["sourceDigest"],
            entity_catalog_digest=IDENTITY["entityCatalogDigest"],
        )
        binding = lane_binding
        evidence_ref = lane_evidence_ref
        selections[carrier] = selection
    for carrier, candidate_id in (
        ("homepage", "homepage-west-lake-0"),
        ("article", "article-hangzhou-0"),
    ):
        stable_selection = {
            "carrier": carrier,
            "candidateIds": [candidate_id],
            "candidateCount": 1,
        }
        selections[carrier] = {
            **stable_selection,
            "selectionDigest": _document_digest(stable_selection),
        }
    assert binding is not None
    snapshot_root = tmp_path / "capsule/scale-source-pool"
    snapshot_digest = materialize_bound_scale_source_pool(
        binding,
        evidence_root_ref=evidence_ref,
        output_root=output_root,
        destination=snapshot_root,
        lane_selections=selections,
    )
    validate_capsule_scale_source_pool(
        binding,
        snapshot_root=snapshot_root,
        lane_selections=selections,
        expected_snapshot_digest=snapshot_digest,
    )
    copied = {
        path.relative_to(snapshot_root / "evidence").as_posix()
        for path in (snapshot_root / "evidence").rglob("*")
        if path.is_file()
    }
    homepage_member = "members/homepage/homepage-west-lake-0"
    article_member = "members/article/article-hangzhou-0"
    assert f"{homepage_member}/capsule.json" in copied
    assert f"{article_member}/capsule.json" in copied
    assert f"{homepage_member}/provenance/discovery.json" in copied
    assert f"{article_member}/provenance/discovery.json" in copied
    assert "members/homepage/homepage-west-lake-1/capsule.json" not in copied
    assert "members/article/article-hangzhou-1/capsule.json" not in copied
    assert not any("west-lake-1" in ref or "hangzhou-1" in ref for ref in copied)

    empty_digest = "sha256:" + "0" * 64
    capsule_root = snapshot_root.parent
    lane_inputs = {
        carrier: {
            "rootRef": f"external-inputs/{carrier}",
            "externalInputRefs": [],
            "externalInputsDigest": empty_digest,
        }
        for carrier in ("homepage", "article", "image", "video")
    }
    _write_json(
        capsule_root / ".qwq_campaign_capsule.json",
        {
            "schema": "quwoquan_data.content_campaign_source_capsule",
            "format": "source-capsule-v2",
            "gitBranch": "main",
            "gitCommitSha": "a" * 40,
            **IDENTITY,
            "executionBundle": {
                "algorithm": "sha256",
                "digest": "sha256:" + "f" * 64,
                "inputs": ["quwoquan_data/scripts"],
            },
            "roots": ["quwoquan_data"],
            "laneExternalInputs": lane_inputs,
            "externalInputsDigest": empty_digest,
            "scaleSourcePool": binding,
            "sourcePoolSnapshotRootRef": "scale-source-pool",
            "sourcePoolSnapshotDigest": snapshot_digest,
            "laneSourcePoolSelections": selections,
            "capsuleDigest": "sha256:" + "b" * 64,
            "treeDigest": "sha256:" + "c" * 64,
        },
    )
    monkeypatch.setattr(
        "content.source.research.scale_source_pool_runtime._frozen_homepage_media_inputs",
        lambda **_kwargs: (
            {
                "schema": "quwoquan_data.source_layout",
                "sourceKind": "wikipedia",
                "extractor": "wikipedia_api",
                "title": "西湖-0",
                "parseStatus": "ok",
                "rejectReason": "",
                "blocks": [
                    {
                        "type": "figure",
                        "figureId": "fig_001",
                        "sourceOrder": 0,
                        "fileTitle": "west-lake-hero-0.jpg",
                        "caption": "西湖-0湖景",
                        "sectionSlug": "",
                        "groupId": "",
                        "placementType": "infoboxLead",
                        "coverCandidateRank": 1,
                        "isMapLike": False,
                        "paragraphIndex": 0,
                    }
                ],
                "figureCount": 1,
                "tables": [],
            },
            {
                "hero-0": {
                    "fileName": "west-lake-hero-0.jpg",
                    "caption": "西湖-0湖景",
                    "placementType": "infoboxLead",
                    "sourceOrder": 0,
                    "coverCandidateRank": 1,
                    "pageResolvedTitle": "西湖-0",
                    "pageId": 1,
                    "pageRevisionId": 1,
                }
            },
            {
                "candidateCount": 1,
                "keptCount": 1,
                "droppedCount": 0,
                "dedupeRemoved": 0,
                "drops": [],
                "fetchFailures": [],
            },
        ),
    )
    for carrier in ("homepage", "article"):
        execution_id = f"20260808--travel-{carrier}-m100--china--scale-991"
        bind_runtime_external_input_context(
            ExternalInputRuntimeContext(
                root=capsule_root / f"external-inputs/{carrier}",
                envelope={"executionId": execution_id, "carrier": carrier},
                refs=(),
                blob_refs_by_digest={},
                capsule_root=capsule_root,
            )
        )
        resolved = frozen_scale_source_pool_candidates(execution_id, carrier)
        targets = frozen_scale_source_pool_targets(execution_id, carrier)
        assert [row["candidateId"] for row in resolved] == [
            selections[carrier]["candidateIds"][0]
        ]
        assert len(targets) == 1
        assert targets[0]["entityType"] == "地点/景区"
        if carrier == "homepage":
            assert targets[0]["qualifiedHomepageSource"]["provider"] == "wikipedia"
        execution_root = tmp_path / "tasks" / execution_id
        monkeypatch.setattr(
            "content.source.research.scale_source_pool_runtime.resolve_entity_object_dir",
            lambda _execution_id, name, etype_hint="": (
                execution_root / "entities" / Path(etype_hint) / name
            ),
        )
        monkeypatch.setattr(
            "content.source.source_unit_writer.execution_source_unit_dir",
            lambda _execution_id, source_unit_id: execution_root
            / "sources"
            / source_unit_id,
        )
        monkeypatch.setattr(
            "content.source.source_unit_writer.stage_execution_context",
            lambda _execution_id: {
                "executionId": execution_id,
                "executionBinding": "frozen",
            },
        )
        monkeypatch.setattr(
            "content.source.source_unit_writer.relative_execution_ref",
            lambda path, _execution_id: path.relative_to(execution_root).as_posix(),
        )
        spec = {
            "scope": {"coverageTargets": [dict(targets[0])]},
            "executionPolicy": {"scaleSourcePool": binding},
        }
        monkeypatch.setattr(
            "content.execution.store.load_spec", lambda _execution_id: spec
        )
        plan_path = (
            execution_root
            / "entities"
            / Path(targets[0]["entityType"])
            / targets[0]["name"]
            / "1.download"
            / research_plan_files()[carrier]
        )

        def prepare_plan(_execution_id: str, _entities: list[dict[str, object]]) -> Path:
            _write_json(plan_path, {"payload": {}})
            return plan_path

        monkeypatch.setattr(
            "content.source.research.auto_plan_writer.prepare_source_plan",
            prepare_plan,
        )
        monkeypatch.setattr(
            "content.source.research.auto_plan_writer.discover_homepage_authority",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("frozen source-pool runtime must not discover online")
            ),
        )
        report = _write_auto_research_plans_impl(
            execution_id,
            [targets[0]["name"]],
            entity_type=targets[0]["entityType"],
            lanes={carrier},
            write_shared_report=False,
        )
        assert report["selectionAuthority"] == "frozen_scale_source_pool"
        assert json.loads(plan_path.read_text(encoding="utf-8"))["payload"][
            "runtimeInputAuthority"
        ] == (
            "frozen_scale_source_pool"
        )
        manifest = materialize_frozen_scale_source_pool_entity(
            execution_id,
            carrier,
            targets[0]["name"],
            targets[0]["entityType"],
        )
        assert manifest is not None
        unit = execution_root / "sources" / manifest["sourceUnitId"]
        assert (unit / "source.md").is_file()
        assert (unit / "assets/index.json").is_file()
        assert manifest["assetCount"] >= 1
        if carrier == "homepage":
            assert manifest["imagePlacements"] == [
                {
                    "fileName": "west-lake-hero-0.jpg",
                    "caption": "西湖-0湖景",
                    "sectionSlug": "",
                    "paragraphIndex": 0,
                    "sourceOrder": 0,
                    "placementType": "infoboxLead",
                    "groupId": "",
                    "coverCandidateRank": 1,
                    "placeholderId": "source-inline-001",
                    "subjectKey": "西湖0湖景",
                    "isMapLike": False,
                }
            ]
            assert manifest["assetFunnel"] == {
                "candidateCount": 1,
                "keptCount": 1,
                "droppedCount": 0,
                "dedupeRemoved": 0,
                "drops": [],
                "fetchFailures": [],
            }
            index = json.loads(
                (unit / "assets/index.json").read_text(encoding="utf-8")
            )
            assert index["assets"][0]["placementType"] == "infoboxLead"
            assert index["assets"][0]["pageRevisionId"] == 1
        assert materialize_frozen_scale_source_pool_entity(
            execution_id,
            carrier,
            targets[0]["name"],
            targets[0]["entityType"],
        ) == manifest
        (unit / "source.md").write_text("tampered", encoding="utf-8")
        with pytest.raises(
            ScaleSourcePoolRuntimeError, match="existing frozen source unit"
        ):
            materialize_frozen_scale_source_pool_entity(
                execution_id,
                carrier,
                targets[0]["name"],
                targets[0]["entityType"],
            )

    def with_member_root(value: str) -> dict[str, object]:
        drifted = copy.deepcopy(plan)
        for candidate in drifted["candidates"]:
            if candidate["candidateId"] == "homepage-west-lake-0":
                candidate["sourceReadyEvidenceRootRef"] = value
                break
        stable = {
            key: item for key, item in drifted.items() if key != "planDigest"
        }
        drifted["planDigest"] = _document_digest(stable)
        return drifted

    wrong_member = "members/homepage/homepage-west-lake-1"
    with pytest.raises(ValueError, match="FileSha256 drift"):
        validate_scale_source_pool_evidence(
            with_member_root(wrong_member),
            evidence_root=evidence_root,
        )

    symlink_ref = "members/homepage/symlink-member"
    (evidence_root / symlink_ref).symlink_to(
        evidence_root / homepage_member,
        target_is_directory=True,
    )
    with pytest.raises(ValueError, match="must not traverse a symlink"):
        validate_scale_source_pool_evidence(
            with_member_root(symlink_ref),
            evidence_root=evidence_root,
        )

    homepage_capsule = evidence_root / homepage_member / "capsule.json"
    homepage_capsule.write_bytes(homepage_capsule.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="FileSha256 drift"):
        validate_scale_source_pool_evidence(plan, evidence_root=evidence_root)


def test_scale_source_pool_runtime_forbids_unbound_campaign_context() -> None:
    with pytest.raises(ScaleSourcePoolRuntimeError, match="RUNTIME_INPUT_UNBOUND"):
        frozen_scale_source_pool_targets(
            "20260808--travel-homepage-m100--china--scale-992", "homepage"
        )


def test_projection_rejects_cross_catalog_identity(tmp_path: Path) -> None:
    drifted = {**IDENTITY, "sourceDigest": "sha256:" + "d" * 64}
    with pytest.raises(
        ScaleSourcePoolProjectionError, match="source identity drift"
    ) as captured:
        _project(tmp_path, article_identity=drifted)
    assert captured.value.code == PROJECTION_INVALID


def test_projection_rejects_duplicate_object_and_content(tmp_path: Path) -> None:
    object_root = tmp_path / "object"
    homepage, article, homepage_path, article_path = _catalogs(
        object_root,
        homepage_candidates=[_homepage_candidate(0), _homepage_candidate(1)],
    )
    batch_ref, batch_digest, batch_file_sha = _source_ready_batch(
        object_root,
        homepage_candidates=list(homepage["candidates"]),
        article_candidates=list(article["candidates"]),
    )
    duplicate_ref = homepage["candidates"][0]["entityRef"]
    homepage["candidates"][1]["entityRef"] = duplicate_ref
    homepage["candidates"][1]["observedEntityRef"] = duplicate_ref
    homepage["candidates"][1]["hero"]["entityRef"] = duplicate_ref
    homepage["candidates"][1]["hero"]["observedEntityRef"] = duplicate_ref
    homepage = _redigest(homepage)
    homepage_path.write_text(
        json.dumps(homepage, ensure_ascii=False), encoding="utf-8"
    )
    with pytest.raises(ScaleSourcePoolProjectionError, match="duplicate entityRef"):
        project_scale_source_pool_homepage_article(
            evidence_root=object_root,
            homepage_catalog_ref="catalogs/homepage.json",
            homepage_catalog_digest=str(homepage["catalogDigest"]),
            homepage_catalog_file_sha256=_file_digest(homepage_path),
            article_catalog_ref="catalogs/article.json",
            article_catalog_digest=str(article["catalogDigest"]),
            article_catalog_file_sha256=_file_digest(article_path),
            source_ready_set_ref=batch_ref,
            source_ready_set_digest=batch_digest,
            source_ready_set_file_sha256=batch_file_sha,
        )

    duplicate_content = [
        _article_candidate(0, content_seed=0),
        _article_candidate(1, content_seed=0),
    ]
    with pytest.raises(
        ScaleSourcePoolProjectionError, match="duplicate physical content"
    ):
        _project(tmp_path / "content", article_candidates=duplicate_content)


def _redigest(catalog: dict[str, object]) -> dict[str, object]:
    stable = {key: value for key, value in catalog.items() if key != "catalogDigest"}
    return {**stable, "catalogDigest": _digest(json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")))}


@pytest.mark.parametrize("carrier", ["homepage", "article"])
def test_projection_rejects_missing_media_closure(
    tmp_path: Path,
    carrier: str,
) -> None:
    homepage, article, homepage_path, article_path = _catalogs(tmp_path)
    batch_ref, batch_digest, batch_file_sha = _source_ready_batch(
        tmp_path,
        homepage_candidates=list(homepage["candidates"]),
        article_candidates=list(article["candidates"]),
    )
    if carrier == "homepage":
        homepage["candidates"][0]["hero"]["generated"] = True
        homepage = _redigest(homepage)
        homepage_path.write_text(json.dumps(homepage, ensure_ascii=False), encoding="utf-8")
    else:
        article["candidates"][0]["assets"] = article["candidates"][0]["assets"][:1]
        article = _redigest(article)
        article_path.write_text(json.dumps(article, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ScaleSourcePoolProjectionError, match="catalog contract is invalid"):
        project_scale_source_pool_homepage_article(
            evidence_root=tmp_path,
            homepage_catalog_ref="catalogs/homepage.json",
            homepage_catalog_digest=str(homepage["catalogDigest"]),
            homepage_catalog_file_sha256=_file_digest(homepage_path),
            article_catalog_ref="catalogs/article.json",
            article_catalog_digest=str(article["catalogDigest"]),
            article_catalog_file_sha256=_file_digest(article_path),
            source_ready_set_ref=batch_ref,
            source_ready_set_digest=batch_digest,
            source_ready_set_file_sha256=batch_file_sha,
        )


def test_projection_rejects_catalog_digest_and_file_drift(tmp_path: Path) -> None:
    homepage, article, homepage_path, article_path = _catalogs(tmp_path)
    batch_ref, batch_digest, batch_file_sha = _source_ready_batch(
        tmp_path,
        homepage_candidates=list(homepage["candidates"]),
        article_candidates=list(article["candidates"]),
    )
    with pytest.raises(ScaleSourcePoolProjectionError, match="catalogDigest drift"):
        project_scale_source_pool_homepage_article(
            evidence_root=tmp_path,
            homepage_catalog_ref="catalogs/homepage.json",
            homepage_catalog_digest="sha256:" + "f" * 64,
            homepage_catalog_file_sha256=_file_digest(homepage_path),
            article_catalog_ref="catalogs/article.json",
            article_catalog_digest=str(article["catalogDigest"]),
            article_catalog_file_sha256=_file_digest(article_path),
            source_ready_set_ref=batch_ref,
            source_ready_set_digest=batch_digest,
            source_ready_set_file_sha256=batch_file_sha,
        )

    original_sha = _file_digest(homepage_path)
    homepage_path.write_bytes(homepage_path.read_bytes() + b"\n")
    with pytest.raises(ScaleSourcePoolProjectionError, match="fileSha256 drift"):
        project_scale_source_pool_homepage_article(
            evidence_root=tmp_path,
            homepage_catalog_ref="catalogs/homepage.json",
            homepage_catalog_digest=str(homepage["catalogDigest"]),
            homepage_catalog_file_sha256=original_sha,
            article_catalog_ref="catalogs/article.json",
            article_catalog_digest=str(article["catalogDigest"]),
            article_catalog_file_sha256=_file_digest(article_path),
            source_ready_set_ref=batch_ref,
            source_ready_set_digest=batch_digest,
            source_ready_set_file_sha256=batch_file_sha,
        )
