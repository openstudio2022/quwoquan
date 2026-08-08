# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-004.t1
from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path

import pytest
from PIL import Image
from core.carrier_contract import research_plan_files
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
    frozen_scale_source_pool_candidates,
    frozen_scale_source_pool_targets,
    materialize_frozen_scale_source_pool_entity,
)
from content.source.research.auto_plan_writer import _write_auto_research_plans_impl
from content.execution.campaign.external_input_runtime import (
    ExternalInputRuntimeContext,
    bind_runtime_external_input_context,
)
from content.execution.campaign.source_pool_binding import (
    bind_scale_source_pool,
    materialize_bound_scale_source_pool,
    validate_capsule_scale_source_pool,
)

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


def _homepage_candidate(index: int = 0) -> dict[str, object]:
    entity_ref = f"/entity/地点/景区/西湖-{index}"
    source_url = f"https://zh.wikipedia.org/wiki/西湖-{index}"
    fact_url = f"https://example.test/{index}/opening-hours"
    return {
        "candidateId": f"homepage-west-lake-{index}",
        "entityRef": entity_ref,
        "observedEntityRef": entity_ref,
        **IDENTITY,
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
    source_url = f"https://zh.wikivoyage.org/wiki/杭州-{index}"
    site = {
        str(row["siteId"]): row for row in article_search_sites()
    }["wikivoyage_zh"]
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


def _source_ready_batch(
    root: Path,
    *,
    homepage_candidates: list[dict[str, object]],
    article_candidates: list[dict[str, object]],
) -> tuple[str, str, str]:
    coverage_ref = "coverage/projection.json"
    coverage_digest = "sha256:" + "f" * 64
    _write_json(
        root / coverage_ref,
        {"schema": "test.coverage_projection", "projectionDigest": coverage_digest},
    )
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
            body_file_sha = _write_evidence_file(root / body_ref, body_value)
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
                        root / ref, media_bytes
                    ),
                })
            evidence_bindings: list[dict[str, str]] = []
            for name in ("discovery", "acquisition", "rights", "quality"):
                ref = f"provenance/{candidate_id}-{name}.json"
                _write_json(root / ref, {"schema": f"test.{name}", "id": candidate_id})
                evidence_bindings.append({
                    "ref": ref,
                    "fileSha256": _file_digest(root / ref),
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
                    "coverageProjectionRef": coverage_ref,
                    "coverageProjectionDigest": coverage_digest,
                    "coverageProjectionFileSha256": _file_digest(root / coverage_ref),
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
            capsule_ref = f"capsules/{carrier}/{candidate_id}.json"
            _write_json(root / capsule_ref, capsule)
            capsule_bindings.append({
                "carrier": carrier,
                "candidateId": candidate_id,
                "ref": capsule_ref,
                "digest": capsule["capsuleDigest"],
                "fileSha256": _file_digest(root / capsule_ref),
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


def _project(root: Path, **catalog_kwargs: object) -> dict[str, object]:
    homepage, article, homepage_path, article_path = _catalogs(
        root, **catalog_kwargs
    )
    batch_ref, batch_digest, batch_file_sha = _source_ready_batch(
        root,
        homepage_candidates=list(homepage["candidates"]),
        article_candidates=list(article["candidates"]),
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
    assert "capsules/homepage/homepage-west-lake-0.json" in copied
    assert "capsules/article/article-hangzhou-0.json" in copied
    assert "capsules/homepage/homepage-west-lake-1.json" not in copied
    assert "capsules/article/article-hangzhou-1.json" not in copied
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
            "format": "source-snapshot-v1",
            "gitCommitSha": "a" * 40,
            **IDENTITY,
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
