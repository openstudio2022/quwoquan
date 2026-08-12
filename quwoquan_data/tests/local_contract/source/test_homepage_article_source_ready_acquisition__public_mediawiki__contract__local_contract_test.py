from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pytest
from content.source.mediawiki_page import MediaWikiPageBundle
from content.source.research.article_frontier_profile import (
    article_profile_digest,
    article_search_sites,
)
from content.source.research.homepage_article_source_ready_acquisition import (
    HomepageArticleSourceReadyAcquisitionError,
    acquire_homepage_article_source_ready_batch,
)
from content.source.research.homepage_article_source_ready_evidence import (
    canonical_digest,
    write_create_once_json,
)
from content.source.research.homepage_article_seed_selection import (
    HomepageArticleSeedSelectionError,
    load_homepage_article_seed_selection,
    seed_id,
)
from content.source.research.homepage_article_source_ready_mediawiki import (
    AcquiredAsset,
    AcquiredSourceReadyCandidate,
    MediaWikiSourceReadyRejected,
    acquire_mediawiki_source_ready_candidate,
    acquire_open_image_assets,
)
from content.source.research.network_io import HttpFetchResult
from core.image_decode import ImageProbe
from core.image_safety import ImageVerdict

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
        "coverageEntityIdentity": f"name_location:{name}|四川省|成都市|锦江区",
        "canonicalEntityRef": f"/entity/{entity_type}/{name}",
        "candidateName": name,
        "province": "四川省",
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
    }


def _seed_selection(
    path: Path,
    rows: list[dict[str, object]],
    *,
    homepage_count: int,
    seed_origin: str = "legacy_hint",
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
            "province": "四川省",
            "city": "成都市",
            "district": "锦江区",
            "entityType": "地点/景区",
            "sourceKind": source["sourceKind"],
            "extractor": source["extractor"],
        }
        if seed_origin == "legacy_hint":
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


def test_seed_selection_rejects_legacy_identity_and_receipt_fields(
    tmp_path: Path,
) -> None:
    source = _seed_selection(
        tmp_path / "valid-seed-selection.json", [_planned("测试实体")], homepage_count=1
    )
    document = json.loads(source.read_text())
    document["seeds"][0]["sourceDigest"] = IDENTITY["sourceDigest"]
    stable = {key: value for key, value in document.items() if key != "selectionDigest"}
    document["selectionDigest"] = canonical_digest(stable)
    invalid = tmp_path / "legacy-bound-seed-selection.json"
    write_create_once_json(invalid, document)

    with pytest.raises(HomepageArticleSeedSelectionError):
        load_homepage_article_seed_selection(invalid)


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


def test_coverage_snapshot_preserves_absolute_report_as_bound_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from content.source.research import homepage_article_source_ready_acquisition as mod

    source_run = tmp_path / "canonical-run"
    source_run.mkdir()
    for name in mod._COVERAGE_FILES:
        (source_run / name).write_bytes(f"canonical:{name}".encode())
    (source_run / "source_inconclusive.ndjson").write_bytes(b"")
    projection = {
        "schema": "quwoquan_data.coverage_source_ready_catalog_projection",
        **IDENTITY,
        "plannedCandidates": [_planned("首页实体"), _planned("文章实体")],
        "projectionDigest": _sha(b"projection"),
    }
    observed_runs: list[Path] = []

    def project(*, run_dir: Path, **_: object) -> dict[str, object]:
        observed_runs.append(run_dir)
        assert run_dir == source_run
        return projection

    monkeypatch.setattr(
        mod,
        "project_coverage_source_ready_catalog_inputs",
        project,
    )
    snapshot_root = tmp_path / "snapshot"

    frozen = mod._copy_coverage_run(
        source_run,
        evidence_root=snapshot_root,
        identity=IDENTITY,
    )

    assert frozen == projection
    assert observed_runs == [source_run, source_run]
    for name in mod._COVERAGE_FILES:
        assert (snapshot_root / name).read_bytes() == (source_run / name).read_bytes()
    assert json.loads((snapshot_root / "coverage-projection.json").read_text()) == projection


def test_acquisition_writes_replayable_physical_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from content.source.research import homepage_article_source_ready_acquisition as mod

    rows = [_planned("首页实体"), _planned("文章实体")]
    preflight_projection = {
        "plannedCandidates": rows,
        "projectionDigest": _sha(b"preflight-projection"),
    }

    def copy_run(
        _run: Path,
        *,
        evidence_root: Path,
        identity: object,
        expected_projection: object = None,
    ) -> dict[str, object]:
        return _projection(evidence_root, rows)

    def acquire(row: dict[str, object], *, carrier: str, **_: object) -> AcquiredSourceReadyCandidate:
        return _fake_acquired(carrier, str(row["candidateName"]))

    monkeypatch.setattr(mod, "_copy_coverage_run", copy_run)
    monkeypatch.setattr(
        mod, "_project_coverage_run", lambda _run, *, identity: preflight_projection
    )
    monkeypatch.setattr(mod, "acquire_mediawiki_source_ready_candidate", acquire)
    monkeypatch.setattr(
        mod,
        "acquire_article_site_source_ready_candidate",
        lambda row, **kwargs: acquire(row, carrier="article", **kwargs),
    )
    arguments = {
        "coverage_run_dir": tmp_path / "coverage",
        "output_root": tmp_path / "output",
        "source_set_id": "m100-public-mediawiki",
        "target_scale": "M100",
        "source_revision": IDENTITY["sourceRevision"],
        "source_digest": IDENTITY["sourceDigest"],
        "entity_catalog_digest": IDENTITY["entityCatalogDigest"],
        "captured_at": CAPTURED_AT,
        "homepage_count": 1,
        "article_count": 1,
        "seed_selection": _seed_selection(
            tmp_path / "seed-selection.json",
            rows,
            homepage_count=1,
            seed_origin="current_coverage",
        ),
    }
    first = acquire_homepage_article_source_ready_batch(**arguments)
    replay = acquire_homepage_article_source_ready_batch(**arguments)

    assert replay == first
    assert first["counts"] == {"homepage": 1, "article": 1}
    assert Path(first["sourceReadyManifest"]).is_file()
    evidence_root = Path(first["evidenceRoot"])
    report = json.loads((evidence_root / first["reportRef"]).read_text())
    assert report["counts"]["attempted"] == 2
    assert report["counts"]["rejected"] == 0
    assert report["rejections"] == []
    batch = json.loads(Path(first["sourceReadyManifest"]).read_text())
    for binding in batch["candidateCapsules"]:
        capsule = json.loads((evidence_root / binding["ref"]).read_text())
        assert capsule["provenance"]["seedOrigin"] == "current_coverage"
        assert "historicalComparison" not in capsule["provenance"]


def test_acquisition_rejects_seed_drift_before_output_or_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from content.source.research import homepage_article_source_ready_acquisition as mod

    rows = [_planned("首页实体"), _planned("文章实体")]
    drifted = [dict(row) for row in rows]
    drifted[0] = {
        **drifted[0],
        "coverageRecordDigest": _sha(b"changed-coverage-record"),
    }
    monkeypatch.setattr(
        mod,
        "_project_coverage_run",
        lambda _run, *, identity: {
            "plannedCandidates": drifted,
            "projectionDigest": _sha(b"drifted-projection"),
        },
    )
    monkeypatch.setattr(
        mod,
        "_copy_coverage_run",
        lambda *_args, **_kwargs: pytest.fail("output write started before preflight"),
    )
    monkeypatch.setattr(
        mod,
        "acquire_mediawiki_source_ready_candidate",
        lambda *_args, **_kwargs: pytest.fail("network acquisition started before preflight"),
    )

    with pytest.raises(
        HomepageArticleSourceReadyAcquisitionError,
        match="DATA.SOURCE.INVALID_EVIDENCE",
    ):
        acquire_homepage_article_source_ready_batch(
            coverage_run_dir=tmp_path / "coverage",
            output_root=tmp_path / "output",
            source_set_id="m100-preflight-drift",
            target_scale="M100",
            source_revision=IDENTITY["sourceRevision"],
            source_digest=IDENTITY["sourceDigest"],
            entity_catalog_digest=IDENTITY["entityCatalogDigest"],
            captured_at=CAPTURED_AT,
            homepage_count=1,
            article_count=1,
            seed_selection=_seed_selection(
                tmp_path / "seed-selection.json",
                rows,
                homepage_count=1,
                seed_origin="current_coverage",
            ),
        )
    assert not (tmp_path / "output").exists()


def test_acquisition_reports_typed_shortfall_without_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from content.source.research import homepage_article_source_ready_acquisition as mod

    rows = [_planned("首页实体"), _planned("文章实体")]
    preflight_projection = {
        "plannedCandidates": rows,
        "projectionDigest": _sha(b"preflight-projection"),
    }
    monkeypatch.setattr(
        mod, "_project_coverage_run", lambda _run, *, identity: preflight_projection
    )
    monkeypatch.setattr(
        mod,
        "_copy_coverage_run",
        lambda _run, *, evidence_root, identity, expected_projection=None: _projection(evidence_root, rows),
    )

    def acquire(row: dict[str, object], *, carrier: str, **_: object) -> AcquiredSourceReadyCandidate:
        if carrier == "article":
            raise MediaWikiSourceReadyRejected("no illustrated source page")
        return _fake_acquired(carrier, str(row["candidateName"]))

    monkeypatch.setattr(mod, "acquire_mediawiki_source_ready_candidate", acquire)
    monkeypatch.setattr(
        mod,
        "acquire_article_site_source_ready_candidate",
        lambda row, **kwargs: acquire(row, carrier="article", **kwargs),
    )
    with pytest.raises(HomepageArticleSourceReadyAcquisitionError) as captured:
        acquire_homepage_article_source_ready_batch(
            coverage_run_dir=tmp_path / "coverage",
            output_root=tmp_path / "output",
            source_set_id="m100-shortfall",
            target_scale="M100",
            source_revision=IDENTITY["sourceRevision"],
            source_digest=IDENTITY["sourceDigest"],
            entity_catalog_digest=IDENTITY["entityCatalogDigest"],
            captured_at=CAPTURED_AT,
            homepage_count=1,
            article_count=1,
            seed_selection=_seed_selection(
                tmp_path / "seed-selection.json", rows, homepage_count=1
            ),
        )
    assert captured.value.code == "DATA.SOURCE.POOL_SHORTFALL"
    assert not list((tmp_path / "output").rglob("batches/*.json"))


def test_acquisition_can_run_article_carrier_without_waiting_for_homepage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from content.source.research import homepage_article_source_ready_acquisition as mod

    rows = [_planned("首页实体"), _planned("文章实体")]
    projection = {
        "plannedCandidates": rows,
        "projectionDigest": _sha(b"carrier-selective-projection"),
    }
    monkeypatch.setattr(
        mod, "_project_coverage_run", lambda _run, *, identity: projection
    )
    monkeypatch.setattr(
        mod,
        "_copy_coverage_run",
        lambda _run, *, evidence_root, identity, expected_projection=None: _projection(
            evidence_root, rows
        ),
    )

    acquired_carriers: list[str] = []

    def acquire(
        row: dict[str, object], *, carrier: str, **_: object
    ) -> AcquiredSourceReadyCandidate:
        acquired_carriers.append(carrier)
        return _fake_acquired(carrier, str(row["candidateName"]))

    monkeypatch.setattr(
        mod,
        "acquire_mediawiki_source_ready_candidate",
        lambda *_args, **_kwargs: pytest.fail("inactive homepage carrier was called"),
    )
    monkeypatch.setattr(
        mod,
        "acquire_article_site_source_ready_candidate",
        lambda row, **kwargs: acquire(row, carrier="article", **kwargs),
    )
    result = acquire_homepage_article_source_ready_batch(
        coverage_run_dir=tmp_path / "coverage",
        output_root=tmp_path / "output",
        source_set_id="m100-article-only",
        target_scale="M100",
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
        captured_at=CAPTURED_AT,
        homepage_count=0,
        article_count=1,
        seed_selection=_seed_selection(
            tmp_path / "seed-selection.json", rows, homepage_count=1
        ),
    )

    assert acquired_carriers == ["article"]
    assert result["counts"] == {"homepage": 0, "article": 1}


def test_acquisition_shortfall_freezes_replayable_partial_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from content.source.research import homepage_article_source_ready_acquisition as mod

    rows = [_planned(f"实体{index}") for index in range(4)]
    preflight_projection = {
        "plannedCandidates": rows,
        "projectionDigest": _sha(b"preflight-projection"),
    }
    monkeypatch.setattr(
        mod, "_project_coverage_run", lambda _run, *, identity: preflight_projection
    )
    monkeypatch.setattr(
        mod,
        "_copy_coverage_run",
        lambda _run, *, evidence_root, identity, expected_projection=None: _projection(evidence_root, rows),
    )

    def acquire(
        row: dict[str, object], *, carrier: str, **_: object
    ) -> AcquiredSourceReadyCandidate:
        if carrier == "homepage" and row["candidateName"] != "实体0":
            raise MediaWikiSourceReadyRejected("homepage candidate unavailable")
        return _fake_acquired(carrier, str(row["candidateName"]))

    monkeypatch.setattr(mod, "acquire_mediawiki_source_ready_candidate", acquire)
    monkeypatch.setattr(
        mod,
        "acquire_article_site_source_ready_candidate",
        lambda row, **kwargs: acquire(row, carrier="article", **kwargs),
    )
    with pytest.raises(HomepageArticleSourceReadyAcquisitionError) as captured:
        acquire_homepage_article_source_ready_batch(
            coverage_run_dir=tmp_path / "coverage",
            output_root=tmp_path / "output",
            source_set_id="m100-partial-checkpoint",
            target_scale="M100",
            source_revision=IDENTITY["sourceRevision"],
            source_digest=IDENTITY["sourceDigest"],
            entity_catalog_digest=IDENTITY["entityCatalogDigest"],
            captured_at=CAPTURED_AT,
            homepage_count=2,
            article_count=2,
            seed_selection=_seed_selection(
                tmp_path / "seed-selection.json", rows, homepage_count=2
            ),
        )
    checkpoint = captured.value.checkpoint
    assert checkpoint is not None
    assert checkpoint["status"] == "source_pool_shortfall"
    assert checkpoint["counts"] == {"homepage": 1, "article": 2}
    assert Path(checkpoint["sourceReadyManifest"]).is_file()
    report = json.loads(
        (Path(checkpoint["evidenceRoot"]) / checkpoint["reportRef"]).read_text()
    )
    assert report["counts"]["homepageShortfall"] == 1
    assert report["counts"]["articleShortfall"] == 0
    assert len(report["rejections"]) == 1
    assert report["rejections"][0]["reason"] == "homepage candidate unavailable"


def test_wikidata_official_website_is_frozen_as_raw_fact_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from content.source.research import homepage_article_source_ready_mediawiki as mod
    from content.source.research import (
        homepage_article_source_ready_wikidata as wikidata,
    )
    from content.source.research.homepage_source_unit_catalog import (
        build_homepage_source_unit_catalog,
    )

    body = (
        "测试景区位于成都市，历史悠久并保存多处文化遗产。\n"
        "景区包含湖泊、园林和展馆，公共交通可到达。\n\n"
        "游客可以沿步道参观不同区域，了解当地历史、生态保护与社区文化。"
        "园区设有导览、休息和无障碍设施，参观前应核对开放信息并遵守安全提示。"
    )
    bundle = MediaWikiPageBundle(
        requested_title="测试景区",
        resolved_title="测试景区",
        redirect_chain=(),
        page_id=10,
        revision_id=20,
        content_sha256="page-sha",
        rendered_text=body,
        wikitext="{{Infobox}}",
        rendered_image_titles=("File:a.jpg",),
        raw='{"query":{"pages":{"10":{}}}}',
    )
    monkeypatch.setattr(mod, "fetch_mediawiki_page_bundle_for_url", lambda *a, **k: bundle)
    monkeypatch.setattr(
        mod,
        "_mediawiki_page_images",
        lambda *a, **k: [{"url": "https://upload.wikimedia.org/a.jpg", "pageRevisionId": 20, "pageContentSha256": "page-sha"}],
    )
    monkeypatch.setattr(
        wikidata.network_io,
        "wiki_api",
        lambda *a, **k: {"query": {"pages": {"10": {"pageprops": {"wikibase_item": "Q123"}}}}},
    )
    monkeypatch.setattr(
        wikidata.network_io,
        "curl_json",
        lambda *a, **k: {
            "entities": {
                "Q123": {
                    "claims": {
                        "P856": [{"mainsnak": {"datavalue": {"value": "http://official.example.test/"}}}]
                    }
                }
            }
        },
    )
    monkeypatch.setattr(
        wikidata.network_io,
        "fetch_http",
        lambda *a, **k: HttpFetchResult(
            0, 200, "https://official.example.test/", b"official"
        ),
    )

    def acquire_assets(_rows, *, source_unit_ref, roles, captured_at):
        document, asset_body = _asset_document(
            source_unit_ref=source_unit_ref, role=roles[0], seed="wikidata-hero"
        )
        return (AcquiredAsset(body=asset_body, document=document),)

    monkeypatch.setattr(mod, "acquire_open_image_assets", acquire_assets)
    acquired = acquire_mediawiki_source_ready_candidate(
        _planned("测试景区"),
        carrier="homepage",
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
        captured_at=CAPTURED_AT,
    )

    assert acquired.candidate["structuredFacts"]["officialWebsite"] == "https://official.example.test/"
    fact = acquired.candidate["factEvidence"][0]
    assert fact["sourceId"] == "official_site"
    assert str(fact["evidenceRef"]).startswith("raw/homepage/")
    assert fact["contentSha256"] == _sha(acquired.raw_evidence)
    assert b"Q123" in acquired.raw_evidence
    assert b"officialWebsiteAccess" in acquired.raw_evidence
    catalog = build_homepage_source_unit_catalog(
        catalog_id="wikidata-official-site",
        catalog_version="1",
        created_at=CAPTURED_AT,
        minimum_candidate_count=1,
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
        candidates=[acquired.candidate],
    )
    assert catalog["candidates"][0]["structuredFacts"]["factSources"][0][
        "sourceClass"
    ] == "official_site"


@pytest.mark.parametrize("carrier", ("homepage", "article"))
def test_mediawiki_supplements_sparse_page_images_with_entity_matched_originals(
    carrier: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from content.source.research import homepage_article_source_ready_mediawiki as mod

    body = (
        "测试景区位于成都市，历史悠久并保存多处文化遗产。\n"
        "景区包含湖泊、园林和展馆，公共交通可到达。\n\n"
        "游客可以沿步道参观不同区域，了解当地历史、生态保护与社区文化。"
        "园区设有导览、休息和无障碍设施，参观前应核对开放信息并遵守安全提示。"
    )
    bundle = MediaWikiPageBundle(
        requested_title="测试景区",
        resolved_title="测试景区",
        redirect_chain=(),
        page_id=10,
        revision_id=20,
        content_sha256="page-sha",
        rendered_text=body,
        wikitext=(
            "{{Infobox\n"
            "| website = https://example.test/official\n"
            "}}"
        ),
        rendered_image_titles=("File:a.jpg",),
        raw='{"query":{"pages":{"10":{}}}}',
    )
    page_image = {"url": "https://upload.wikimedia.org/a.jpg", "pageRevisionId": 20, "pageContentSha256": "page-sha"}
    supplement = {"url": "https://images.openverse.org/b.jpg", "sourceUrl": "https://example.test/b"}
    page_images = [] if carrier == "homepage" else [page_image]
    monkeypatch.setattr(mod, "fetch_mediawiki_page_bundle_for_url", lambda *a, **k: bundle)
    monkeypatch.setattr(mod, "_mediawiki_page_images", lambda *a, **k: page_images)
    monkeypatch.setattr(
        mod,
        "wikidata_commons_images_for_entity",
        lambda *a, **k: [supplement] if carrier == "homepage" else [],
    )
    monkeypatch.setattr(mod, "commons_images_for_entity", lambda *a, **k: [])
    monkeypatch.setattr(
        mod,
        "openverse_images_for_entity",
        lambda *a, **k: [supplement] if carrier == "article" else [],
    )
    captured_rows: list[dict[str, object]] = []

    def acquire_assets(rows, *, source_unit_ref, roles, captured_at):
        captured_rows.extend(rows)
        result = []
        for index, role in enumerate(roles):
            document, asset_body = _asset_document(
                source_unit_ref=source_unit_ref, role=role, seed=f"supplement-{index}"
            )
            result.append(AcquiredAsset(body=asset_body, document=document))
        return tuple(result)

    monkeypatch.setattr(mod, "acquire_open_image_assets", acquire_assets)
    acquired = acquire_mediawiki_source_ready_candidate(
        _planned("测试景区"),
        carrier=carrier,
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
        captured_at=CAPTURED_AT,
    )

    assert len(acquired.assets) == (1 if carrier == "homepage" else 2)
    expected_urls = (
        [supplement["url"]]
        if carrier == "homepage"
        else [page_image["url"], supplement["url"]]
    )
    assert [row["url"] for row in captured_rows] == expected_urls


def test_public_domain_commons_file_page_is_the_https_terms_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from content.source.research import homepage_article_source_ready_mediawiki as mod
    from core import image_decode

    monkeypatch.setattr(
        mod.network_io,
        "fetch_http",
        lambda *a, **k: HttpFetchResult(0, 200, str(a[0]), b"public-domain-image"),
    )
    monkeypatch.setattr(
        mod,
        "assess_image",
        lambda *a, **k: ImageVerdict(
            path="fixture",
            status="safe",
            faces=0,
            has_watermark=False,
            text_area_ratio=0.0,
            reasons=(),
            backends=("cv", "ocr"),
        ),
    )
    monkeypatch.setattr(
        image_decode,
        "probe_image_bytes",
        lambda body: ImageProbe(width=1600, height=1000, mime_type="image/jpeg"),
    )
    source_page = "https://commons.wikimedia.org/wiki/File:Public_domain.jpg"
    acquired = mod.acquire_open_image_assets(
        [
            {
                "url": "https://upload.wikimedia.org/public-domain.jpg",
                "sourceUrl": source_page,
                "license": "Public domain",
                "termsUrl": "",
                "authorizationProof": source_page,
                "creator": "Archive author",
                "credit": "Archive author",
                "usageScope": "app_publish",
                "modelReleaseStatus": "not_required",
            }
        ],
        source_unit_ref="sources/public-domain",
        roles=("hero",),
        captured_at=CAPTURED_AT,
    )

    assert acquired[0].document["termsUrl"] == source_page


@pytest.mark.parametrize(
    ("carrier", "expected_roles"),
    (("homepage", ("hero",)), ("article", ("cover", "body"))),
)
def test_mediawiki_provider_uses_public_body_original_media_and_safety(
    carrier: str,
    expected_roles: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from content.source.research import homepage_article_source_ready_mediawiki as mod
    from core import image_decode

    body = (
        "成都市位于四川盆地西部。\n成都市拥有悠久的城市历史。\n"
        "成都市分布有多处公共文化空间。\n成都市包括河流与历史建筑。\n"
        "交通可乘坐公共汽车到达，开放区域以现场公告为准。\n\n"
        "园区沿湖分布多处步道、展馆和观景平台，游客可以依次了解"
        "当地生态保护、历史沿革与社区文化。春季和秋季景观层次丰富，"
        "公共服务区域设有导览、休息与无障碍设施。参观前应核对开放"
        "时间、天气和交通信息，并遵守现场的生态保护与安全提示。"
    )
    bundle = MediaWikiPageBundle(
        requested_title="成都市",
        resolved_title="成都市",
        redirect_chain=(),
        page_id=10,
        revision_id=20,
        content_sha256="page-sha",
        rendered_text=body,
        wikitext=(
            "{{Infobox\n"
            "| website = https://example.test/official\n"
            "}}"
        ),
        rendered_image_titles=("File:a.jpg", "File:b.jpg"),
        raw='{"query":{"pages":{"10":{}}}}',
    )
    monkeypatch.setattr(mod, "fetch_mediawiki_page_bundle_for_url", lambda *a, **k: bundle)
    images = [
        {
            "url": f"https://upload.wikimedia.org/{name}.jpg",
            "sourceUrl": f"https://commons.wikimedia.org/wiki/File:{name}.jpg",
            "termsUrl": "http://creativecommons.org/licenses/by-sa/4.0/",
            "authorizationProof": f"https://commons.wikimedia.org/wiki/File:{name}.jpg",
            "license": "CC BY-SA 4.0",
            "credit": f"Creator {name}",
            "creator": f"Creator {name}",
            "usageScope": "app_publish",
            "modelReleaseStatus": "not_required",
            "pageRevisionId": 20,
            "pageContentSha256": "page-sha",
        }
        for name in ("a", "b")
    ]
    monkeypatch.setattr(mod, "_mediawiki_page_images", lambda *a, **k: images)
    monkeypatch.setattr(mod, "wikidata_commons_images_for_entity", lambda *a, **k: [])
    monkeypatch.setattr(mod, "commons_images_for_entity", lambda *a, **k: [])
    monkeypatch.setattr(mod, "openverse_images_for_entity", lambda *a, **k: [])
    responses = iter((b"image-a", b"image-b")[: len(expected_roles)])
    monkeypatch.setattr(
        mod.network_io,
        "fetch_http",
        lambda url, timeout: HttpFetchResult(0, 200, url, next(responses)),
    )
    monkeypatch.setattr(
        mod,
        "assess_image",
        lambda *a, **k: ImageVerdict(
            path="fixture",
            status="safe",
            faces=0,
            has_watermark=False,
            text_area_ratio=0.0,
            reasons=(),
            backends=("cv", "ocr"),
        ),
    )
    monkeypatch.setattr(
        image_decode,
        "probe_image_bytes",
        lambda body: ImageProbe(width=1600, height=1000, mime_type="image/jpeg"),
    )

    acquired = acquire_mediawiki_source_ready_candidate(
        _planned("四川省成都市", "地点/城市", source_title="成都市"),
        carrier=carrier,
        source_revision=IDENTITY["sourceRevision"],
        source_digest=IDENTITY["sourceDigest"],
        entity_catalog_digest=IDENTITY["entityCatalogDigest"],
        captured_at=CAPTURED_AT,
    )

    if carrier == "article":
        assert acquired.candidate["articleSiteId"] == "wikipedia_zh"
    else:
        assert acquired.candidate["entityRef"] == "/entity/地点/城市/四川省成都市"
        assert acquired.candidate["hero"]["entityRef"] == acquired.candidate["entityRef"]
        assert acquired.candidate["hero"]["sourceUnitDigest"] == acquired.candidate[
            "primarySource"
        ]["sourceUnitDigest"]
    assert tuple(asset.document["role"] for asset in acquired.assets) == expected_roles
    assert all(
        asset.document["distributionDecision"] == "research_allowed"
        for asset in acquired.assets
    )
    assert all(
        asset.document["usageScope"] == "app_publish"
        for asset in acquired.assets
    )
    assert all(
        asset.document["modelReleaseStatus"] == "not_required"
        for asset in acquired.assets
    )
    assert all(
        asset.document["termsUrl"].startswith("https://creativecommons.org/")
        for asset in acquired.assets
    )


def test_mediawiki_rejects_page_title_different_from_frozen_coverage_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from content.source.research import homepage_article_source_ready_mediawiki as mod

    bundle = MediaWikiPageBundle(
        requested_title="成都市",
        resolved_title="成都",
        redirect_chain=(),
        page_id=10,
        revision_id=20,
        content_sha256="page-sha",
        rendered_text="成都页面",
        wikitext="{{Infobox}}",
        rendered_image_titles=(),
        raw='{"query":{"pages":{"10":{}}}}',
    )
    monkeypatch.setattr(
        mod, "fetch_mediawiki_page_bundle_for_url", lambda *args, **kwargs: bundle
    )

    with pytest.raises(MediaWikiSourceReadyRejected, match="page identity drift"):
        acquire_mediawiki_source_ready_candidate(
            _planned("四川省成都市", "地点/城市", source_title="成都市"),
            carrier="homepage",
            source_revision=IDENTITY["sourceRevision"],
            source_digest=IDENTITY["sourceDigest"],
            entity_catalog_digest=IDENTITY["entityCatalogDigest"],
            captured_at=CAPTURED_AT,
        )


def test_openverse_supplement_preserves_provider_and_original_rights(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from content.source.research import homepage_article_source_ready_mediawiki as mod
    from core import image_decode

    monkeypatch.setattr(
        mod.network_io,
        "fetch_http",
        lambda url, timeout: HttpFetchResult(0, 200, url, b"openverse-image"),
    )
    monkeypatch.setattr(
        mod,
        "assess_image",
        lambda *a, **k: ImageVerdict(
            path="fixture",
            status="safe",
            faces=0,
            has_watermark=False,
            text_area_ratio=0.0,
            reasons=(),
            backends=("cv", "ocr"),
        ),
    )
    monkeypatch.setattr(
        image_decode,
        "probe_image_bytes",
        lambda body: ImageProbe(width=1600, height=1000, mime_type="image/jpeg"),
    )
    acquired = acquire_open_image_assets(
        [
            {
                "url": "https://images.openverse.org/test.jpg",
                "platform": "Openverse",
                "sourceUrl": "https://example.test/original-work",
                "termsUrl": "https://creativecommons.org/licenses/by/4.0/",
                "authorizationProof": "https://example.test/original-work",
                "license": "CC BY 4.0",
                "credit": "Original Creator",
                "creator": "Original Creator",
                "usageScope": "app_publish",
                "modelReleaseStatus": "not_required",
            }
        ],
        source_unit_ref="sources/openverse-test",
        roles=("hero",),
        captured_at=CAPTURED_AT,
    )
    assert acquired[0].document["provider"] == "openverse"
    assert acquired[0].document["platform"] == "Openverse"
    assert acquired[0].document["creator"] == "Original Creator"


def test_acquisition_cli_freezes_exact_identity_and_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import content.source.research.handler_cli as handler

    captured: dict[str, object] = {}

    def acquire(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "schema": "quwoquan_data.homepage_article_source_ready_acquisition_result",
            "counts": {"homepage": 180, "article": 180},
        }

    monkeypatch.setattr(handler, "acquire_homepage_article_source_ready_batch", acquire)
    parser = argparse.ArgumentParser()
    handler.register_parser(parser.add_subparsers(dest="command", required=True))
    arguments = parser.parse_args(
        [
            "source-pool",
            "acquire-homepage-article",
            "--coverage-run-dir",
            str(tmp_path / "coverage"),
            "--source-set-id",
            "m100-public-mediawiki",
            "--target-scale",
            "M100",
            "--source-revision",
            IDENTITY["sourceRevision"],
            "--source-digest",
            IDENTITY["sourceDigest"],
            "--entity-catalog-digest",
            IDENTITY["entityCatalogDigest"],
            "--captured-at",
            CAPTURED_AT,
            "--homepage-count",
            "180",
            "--article-count",
            "180",
            "--seed-selection",
            str(tmp_path / "seed-selection.json"),
            "--output-root",
            str(tmp_path / "output"),
        ]
    )

    arguments.handler(arguments)

    assert captured == {
        "coverage_run_dir": tmp_path / "coverage",
        "output_root": tmp_path / "output",
        "source_set_id": "m100-public-mediawiki",
        "target_scale": "M100",
        "source_revision": IDENTITY["sourceRevision"],
        "source_digest": IDENTITY["sourceDigest"],
        "entity_catalog_digest": IDENTITY["entityCatalogDigest"],
        "captured_at": CAPTURED_AT,
        "homepage_count": 180,
        "article_count": 180,
        "seed_selection": tmp_path / "seed-selection.json",
    }
    assert json.loads(capsys.readouterr().out)["counts"] == {
        "homepage": 180,
        "article": 180,
    }
