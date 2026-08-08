from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from content.source.professional_video_acquisition import (
    acquire_professional_videos,
    acquired_video_specs_for_entity,
    load_professional_video_acquisition_receipt,
)
from content.source.professional_video_popular_catalog import (
    build_professional_video_popular_candidate_catalog,
    write_create_once_professional_video_popular_candidate_catalog,
)
from content.source.professional_video_receipt import (
    assert_publishable_popularity_signals,
)
from content.source.research.auto_plan_video import write_video_lane
from core.io import read_json, write_json
from governance.coverage.distribution import ProductLifecycleState

_DIGEST_A = "sha256:" + "a" * 64
_DIGEST_B = "sha256:" + "b" * 64
_DIGEST_C = "sha256:" + "c" * 64


@pytest.fixture(autouse=True)
def _explicit_research_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "content.source.professional_video_acquisition.load_content_distribution_policy",
        lambda: SimpleNamespace(
            product_lifecycle_state=ProductLifecycleState.RESEARCH
        ),
    )
    monkeypatch.setattr(
        "content.source.professional_video_acquisition.guard_acquisition_source_identity",
        lambda *_args, **_kwargs: {},
    )


def _write_video(path: Path, *, moving: bool, seed: int) -> None:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        10.0,
        (320, 180),
    )
    if not writer.isOpened():
        raise RuntimeError("test MP4 writer did not open")
    static_frame = (
        np.random.default_rng(seed).integers(
            0, 256, size=(180, 320, 3), dtype=np.uint8
        )
        if not moving
        else None
    )
    try:
        for index in range(36):
            frame = (
                static_frame.copy()
                if static_frame is not None
                else np.full(
                    (180, 320, 3), 10 + (seed * 5) % 70, dtype=np.uint8
                )
            )
            if moving:
                left = round(index * 250 / 35)
                cv2.rectangle(
                    frame,
                    (left, 20),
                    (left + 70, 140),
                    (255, 255, 255),
                    thickness=-1,
                )
                cv2.putText(
                    frame,
                    f"frame-{index:02d}-{seed}",
                    (8, 165),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )
            writer.write(frame)
    finally:
        writer.release()
    assert path.stat().st_size > 8_000


def _write_slideshow(path: Path) -> None:
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (320, 180)
    )
    assert writer.isOpened()
    frames = [
        np.random.default_rng(seed).integers(
            0, 256, size=(180, 320, 3), dtype=np.uint8
        )
        for seed in (101, 102, 103)
    ]
    try:
        for index in range(36):
            writer.write(frames[index // 12])
    finally:
        writer.release()
    assert path.stat().st_size > 8_000


def _item(
    asset_id: str,
    manual_file: str,
    *,
    counts: tuple[int | None, int | None, int | None, int | None, int | None],
    time_bucket: str = "2026-W32",
    observed_entity_id: str = "西湖",
    login_required: bool = False,
    acquisition_path: str = "manual_file",
    asset_url: str = "",
    api_evidence: str = "",
) -> dict[str, object]:
    play, like, comment, share, favorite = counts
    return {
        "assetId": asset_id,
        "entityId": "西湖",
        "observedEntityId": observed_entity_id,
        "entityAliases": ["杭州西湖", "西湖风景名胜区"],
        "provider": "pexels_videos",
        "platform": "Pexels Videos",
        "displayName": "Pexels 专业旅行视频",
        "sourceKind": "tourism_video_site",
        "acquisitionPath": acquisition_path,
        "sourceUrl": f"https://videos.example.test/posts/{asset_id}",
        "assetUrl": asset_url,
        "manualFile": manual_file,
        "apiEvidence": api_evidence,
        "accessEvidence": {
            "anonymousAssetAccess": acquisition_path != "manual_file",
            "loginRequired": login_required,
            "captchaRequired": False,
            "paywallRequired": False,
            "drmProtected": False,
            "accessControlBypass": False,
        },
        "title": f"西湖旅行实拍 {asset_id}",
        "relevance": "杭州西湖风景名胜区水面与沿岸旅行实景",
        "creator": f"Creator {asset_id}",
        "capturedAt": "2026-08-05T02:00:00Z",
        "rightsStatus": "unverified",
        "license": "platform rights pending verification",
        "termsUrl": "https://videos.example.test/terms",
        "authorizationProof": "",
        "rightsIssues": ["commercial redistribution authorization is unverified"],
        "modelReleaseStatus": "unverified",
        "propertyReleaseStatus": "not_required",
        "safetyReview": {
            "status": "passed",
            "entityMatch": "matched",
            "privacyRisk": "none",
            "minorRisk": "none",
            "maliciousMediaRisk": "none",
            "watermarkStatus": "absent",
            "reviewedAt": "2026-08-05T02:05:00Z",
            "reviewer": "local-contract-reviewer",
            "evidenceRef": f"evidence/{asset_id}.json",
        },
        "popularitySignals": {
            "playCount": play,
            "likeCount": like,
            "commentCount": comment,
            "shareCount": share,
            "favoriteCount": favorite,
            "observedAt": "2026-08-05T01:00:00Z",
            "provider": "pexels_videos",
            "topic": "west-lake-travel",
            "timeBucket": time_bucket,
        },
    }


def _manifest(
    items: list[dict[str, object]],
    *,
    manifest_id: str = "video-test",
    source_revision: str = "local-contract-revision",
    source_digest: str = _DIGEST_A,
    entity_catalog_digest: str = _DIGEST_B,
) -> dict[str, object]:
    return {
        "schema": "quwoquan_data.professional_video_acquisition_manifest",
        "manifestId": manifest_id,
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
        "items": items,
    }


def _acquire(
    tmp_path: Path,
    items: list[dict[str, object]],
    *,
    manifest_id: str = "video-test",
) -> tuple[dict[str, object], Path, Path]:
    manual_root = tmp_path / "manual"
    output_root = tmp_path / "acquisition"
    manual_root.mkdir(exist_ok=True)
    manifest_path = tmp_path / f"{manifest_id}.json"
    write_json(manifest_path, _manifest(items, manifest_id=manifest_id))
    receipt, receipt_path = acquire_professional_videos(
        manifest_path,
        handoff_ref=tmp_path / "handoff.json",
        manual_root=manual_root,
        output_root=output_root,
    )
    return receipt, receipt_path, output_root


def test_acquisition_freezes_bytes_and_rejects_duplicate_static_mismatch_and_access(
    tmp_path: Path,
) -> None:
    manual_root = tmp_path / "manual"
    manual_root.mkdir()
    _write_video(manual_root / "lower.mp4", moving=True, seed=1)
    _write_video(manual_root / "higher.mp4", moving=True, seed=2)
    _write_video(manual_root / "static.mp4", moving=False, seed=3)
    items = [
        _item("lower", "lower.mp4", counts=(1_000, 10, 2, 1, 2)),
        _item("higher", "higher.mp4", counts=(50_000, 900, 80, 40, 100)),
        _item("duplicate", "lower.mp4", counts=(500_000, 9_000, 800, 400, 1_000)),
        _item("static", "static.mp4", counts=(100, 2, 0, 0, 0)),
        _item(
            "mismatch",
            "lower.mp4",
            counts=(100, 2, 0, 0, 0),
            observed_entity_id="西塘",
        ),
        _item(
            "login",
            "higher.mp4",
            counts=(100, 2, 0, 0, 0),
            login_required=True,
        ),
    ]
    manifest_path = tmp_path / "manifest.json"
    write_json(manifest_path, _manifest(items))
    output_root = tmp_path / "acquisition"

    receipt, receipt_path = acquire_professional_videos(
        manifest_path,
        handoff_ref=tmp_path / "handoff.json",
        manual_root=manual_root,
        output_root=output_root,
    )

    assert receipt["plannedAssetCount"] == 6
    assert receipt["downloadedAssetCount"] == 4
    assert receipt["acceptedAssetCount"] == 2
    assert receipt["rejectedAssetCount"] == 4
    assert receipt["providerAssetCounts"] == [{
        "displayName": "Pexels 专业旅行视频",
        "provider": "pexels_videos",
        "platform": "Pexels Videos",
        "plannedAssetCount": 6,
        "discoveredAssetCount": 6,
        "downloadedAssetCount": 4,
        "acceptedAssetCount": 2,
        "rejectedAssetCount": 4,
        "verifiedAssetCount": 0,
        "unverifiedAssetCount": 6,
        "restrictedAssetCount": 0,
        "unknownAssetCount": 0,
        "rankingEligibleAssetCount": 2,
    }]
    by_id = {row["assetId"]: row for row in receipt["assets"]}
    assert by_id["higher"]["popularitySignals"]["popularityPercentile"] == 1.0
    assert by_id["lower"]["popularitySignals"]["popularityPercentile"] == 0.0
    assert by_id["duplicate"]["duplicateOf"] == "lower"
    assert by_id["duplicate"]["failureCode"] == "DATA.SOURCE.DUPLICATE_ASSET"
    assert by_id["static"]["mediaProbe"]["staticImageSequence"] is True
    assert by_id["static"]["mediaProbe"]["premiumPlayableEligible"] is False
    assert by_id["mismatch"]["failureCode"] == "DATA.SOURCE.ENTITY_MISMATCH"
    assert by_id["login"]["failureCode"] == "DATA.SOURCE.ACCESS_CONTROL_BLOCKED"
    assert by_id["mismatch"]["acquisitionStatus"] == "blocked"
    for asset_id in ("lower", "higher", "duplicate", "static"):
        row = by_id[asset_id]
        assert (output_root / row["assetRef"]).is_file()
    assert load_professional_video_acquisition_receipt(
        receipt_path.relative_to(output_root).as_posix(), root=output_root
    ) == receipt
    repeated, repeated_path = acquire_professional_videos(
        manifest_path,
        handoff_ref=tmp_path / "handoff.json",
        manual_root=manual_root,
        output_root=output_root,
    )
    assert repeated == receipt
    assert repeated_path == receipt_path
    specs = acquired_video_specs_for_entity(
        [receipt_path.relative_to(output_root).as_posix()],
        entity_id="西湖",
        root=output_root,
    )
    assert [spec["professionalAssetId"] for spec in specs] == ["higher", "lower"]
    assert all(spec["premiumPlayableEligible"] is True for spec in specs)


def test_prior_receipt_deduplication_is_scoped_to_exact_source_identity(
    tmp_path: Path,
) -> None:
    manual_root = tmp_path / "manual"
    manual_root.mkdir()
    _write_video(manual_root / "shared.mp4", moving=True, seed=12)
    output_root = tmp_path / "acquisition"

    def acquire(
        asset_id: str,
        *,
        source_revision: str = "local-contract-revision",
        source_digest: str = _DIGEST_A,
        entity_catalog_digest: str = _DIGEST_B,
    ) -> tuple[dict[str, object], Path]:
        manifest_path = tmp_path / f"{asset_id}.json"
        write_json(
            manifest_path,
            _manifest(
                [_item(asset_id, "shared.mp4", counts=(1_000, 20, 2, 1, 3))],
                manifest_id=asset_id,
                source_revision=source_revision,
                source_digest=source_digest,
                entity_catalog_digest=entity_catalog_digest,
            ),
        )
        return acquire_professional_videos(
            manifest_path,
            handoff_ref=tmp_path / "handoff.json",
            manual_root=manual_root,
            output_root=output_root,
        )

    original, original_path = acquire("original")
    duplicate, _duplicate_path = acquire("same-identity")
    original_row = original["assets"][0]
    duplicate_row = duplicate["assets"][0]
    original_ref = original_path.relative_to(output_root).as_posix()

    assert original["acceptedAssetCount"] == 1
    assert duplicate["acceptedAssetCount"] == 0
    assert duplicate_row["failureCode"] == "DATA.SOURCE.DUPLICATE_ASSET"
    assert duplicate_row["duplicateOf"] == f"{original_ref}#original"

    identity_variants = (
        ("new-revision", "local-contract-revision-2", _DIGEST_A, _DIGEST_B),
        ("new-source-digest", "local-contract-revision", _DIGEST_C, _DIGEST_B),
        ("new-catalog-digest", "local-contract-revision", _DIGEST_A, _DIGEST_C),
    )
    for asset_id, source_revision, source_digest, entity_catalog_digest in identity_variants:
        rebound, _rebound_path = acquire(
            asset_id,
            source_revision=source_revision,
            source_digest=source_digest,
            entity_catalog_digest=entity_catalog_digest,
        )
        rebound_row = rebound["assets"][0]
        assert rebound["acceptedAssetCount"] == 1
        assert rebound_row["failureCode"] == ""
        assert rebound_row["duplicateOf"] == ""
        assert rebound_row["assetRef"] == original_row["assetRef"]


def test_foreign_identity_legacy_receipt_body_does_not_block_fresh_acquisition(
    tmp_path: Path,
) -> None:
    manual_root = tmp_path / "manual"
    manual_root.mkdir()
    _write_video(manual_root / "fresh.mp4", moving=True, seed=13)
    output_root = tmp_path / "acquisition"
    receipts = output_root / "receipts"
    receipts.mkdir(parents=True)
    write_json(
        receipts / "foreign-legacy.json",
        {
            "schema": "quwoquan_data.professional_video_acquisition_receipt",
            "sourceRevision": "foreign-revision",
            "sourceDigest": _DIGEST_C,
            "entityCatalogDigest": _DIGEST_B,
            "legacyBody": {"planVideoSpec": "retired-shape"},
        },
    )
    manifest_path = tmp_path / "fresh.json"
    write_json(
        manifest_path,
        _manifest(
            [_item("fresh", "fresh.mp4", counts=(1_000, 20, 2, 1, 3))],
            manifest_id="fresh-after-foreign-legacy",
        ),
    )

    receipt, _receipt_path = acquire_professional_videos(
        manifest_path,
        handoff_ref=tmp_path / "handoff.json",
        manual_root=manual_root,
        output_root=output_root,
    )

    assert receipt["acceptedAssetCount"] == 1
    assert receipt["assets"][0]["failureCode"] == ""


def test_same_identity_corrupt_receipt_body_still_fails_closed(
    tmp_path: Path,
) -> None:
    manual_root = tmp_path / "manual"
    manual_root.mkdir()
    _write_video(manual_root / "fresh.mp4", moving=True, seed=14)
    output_root = tmp_path / "acquisition"
    receipts = output_root / "receipts"
    receipts.mkdir(parents=True)
    write_json(
        receipts / "same-identity-corrupt.json",
        {
            "schema": "quwoquan_data.professional_video_acquisition_receipt",
            "sourceRevision": "local-contract-revision",
            "sourceDigest": _DIGEST_A,
            "entityCatalogDigest": _DIGEST_B,
            "corruptBody": True,
        },
    )
    manifest_path = tmp_path / "fresh.json"
    write_json(
        manifest_path,
        _manifest(
            [_item("fresh", "fresh.mp4", counts=(1_000, 20, 2, 1, 3))],
            manifest_id="fresh-after-same-identity-corruption",
        ),
    )

    with pytest.raises(ValueError, match="schema violation"):
        acquire_professional_videos(
            manifest_path,
            handoff_ref=tmp_path / "handoff.json",
            manual_root=manual_root,
            output_root=output_root,
        )


def test_popularity_never_invents_comparability(tmp_path: Path) -> None:
    manual_root = tmp_path / "manual"
    manual_root.mkdir()
    _write_video(manual_root / "missing.mp4", moving=True, seed=4)
    _write_video(manual_root / "single.mp4", moving=True, seed=5)
    items = [
        _item("missing", "missing.mp4", counts=(None, None, None, None, None)),
        _item(
            "single",
            "single.mp4",
            counts=(100, 4, 2, 1, 2),
            time_bucket="2026-W33",
        ),
    ]
    manifest_path = tmp_path / "manifest.json"
    write_json(manifest_path, _manifest(items, manifest_id="no-fake-rank"))
    receipt, receipt_path = acquire_professional_videos(
        manifest_path,
        handoff_ref=tmp_path / "handoff.json",
        manual_root=manual_root,
        output_root=tmp_path / "acquisition",
    )
    by_id = {row["assetId"]: row for row in receipt["assets"]}
    assert by_id["missing"]["popularitySignals"]["rankingEligible"] is False
    assert by_id["missing"]["popularitySignals"]["ineligibleReason"] == (
        "incomplete_popularity_signals"
    )
    assert by_id["single"]["popularitySignals"]["rankingEligible"] is False
    assert by_id["single"]["popularitySignals"]["ineligibleReason"] == (
        "insufficient_comparable_candidates"
    )
    assert receipt["acceptedAssetCount"] == 2
    specs = acquired_video_specs_for_entity(
        [receipt_path.relative_to(tmp_path / "acquisition").as_posix()],
        entity_id="西湖",
        root=tmp_path / "acquisition",
    )
    assert {row["professionalAssetId"] for row in specs} == {"missing", "single"}
    with pytest.raises(
        ValueError,
        match="professional video popularity counts are incomplete: missing",
    ):
        acquired_video_specs_for_entity(
            [receipt_path.relative_to(tmp_path / "acquisition").as_posix()],
            entity_id="西湖",
            root=tmp_path / "acquisition",
            require_popularity_ranking=True,
        )
    with pytest.raises(
        ValueError,
        match="professional video lacks comparable popularity percentile: single",
    ):
        assert_publishable_popularity_signals(
            by_id["single"]["popularitySignals"],
            asset_id="single",
        )


def test_acquisition_physically_consumes_popular_catalog_binding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manual_root = tmp_path / "manual"
    manual_root.mkdir()
    _write_video(manual_root / "high.mp4", moving=True, seed=21)
    response = {
        "provider": "bilibili",
        "sourcePageUrl": "https://www.bilibili.com/video/BV-popular",
        "apiEvidenceUrl": "https://api.bilibili.com/x/web-interface/archive/stat",
        "statusCode": 200,
        "contentType": "application/json",
        "accessEvidence": {
            "supportedApi": True, "cookiesSent": False, "loginRequired": False,
            "paywallRequired": False, "drmProtected": False,
            "accessControlBypass": False,
        },
        "items": [
            {
                "sourceId": source_id, "entityId": "西湖", "observedEntityId": "西湖",
                "creator": f"Creator {source_id}", "title": f"西湖热门旅行 {source_id}",
                "observedAt": "2026-08-08T09:00:00Z", "topic": "west-lake-travel",
                "timeBucket": "2026-W32", "playCount": score * 100,
                "likeCount": score * 10, "commentCount": score,
                "shareCount": score, "favoriteCount": score * 2,
            }
            for source_id, score in (("low", 10), ("high", 20))
        ],
    }
    catalog = build_professional_video_popular_candidate_catalog(
        source_revision="sha256:" + "1" * 64,
        source_digest=_DIGEST_A,
        entity_catalog_digest=_DIGEST_B,
        metadata_responses=[response],
        manual_file_manifests=[{
            "provider": "bilibili", "sourceId": "high",
            "sourcePageUrl": response["sourcePageUrl"], "manualFileRef": "high.mp4",
        }],
        evidence_root=manual_root,
    )
    output_root = tmp_path / "acquisition"
    catalog_ref = (
        "professional-video-popular-catalogs/"
        f"{catalog['catalogDigest'][7:]}.json"
    )
    catalog_path = output_root / catalog_ref
    write_create_once_professional_video_popular_candidate_catalog(catalog_path, catalog)
    catalog_sha = "sha256:" + __import__("hashlib").sha256(
        catalog_path.read_bytes()
    ).hexdigest()
    candidate = next(row for row in catalog["candidates"] if row["sourceId"] == "high")
    popularity = candidate["popularity"]
    item = _item(
        "popular", "high.mp4",
        counts=tuple(popularity[field] for field in (
            "playCount", "likeCount", "commentCount", "shareCount", "favoriteCount"
        )),
    )
    item.update(
        provider="bilibili", platform="B站", displayName="B站热门旅行视频",
        sourceUrl=candidate["sourcePageUrl"], title=candidate["title"],
        creator=candidate["creator"],
        popularitySignals={
            **{field: popularity[field] for field in (
                "playCount", "likeCount", "commentCount", "shareCount", "favoriteCount"
            )},
            "observedAt": candidate["observedAt"], "provider": candidate["provider"],
            "topic": candidate["topic"], "timeBucket": candidate["timeBucket"],
        },
        popularCandidateId=candidate["candidateId"], popularCatalogRef=catalog_ref,
        popularCatalogDigest=catalog["catalogDigest"],
        popularCatalogFileSha256=catalog_sha,
    )
    monkeypatch.setattr(
        "content.source.professional_video_acquisition.assert_video_source_admitted",
        lambda *_args, **_kwargs: None,
    )
    manifest_path = tmp_path / "popular.json"
    write_json(manifest_path, _manifest(
        [item], manifest_id="popular-catalog-bound",
        source_revision="sha256:" + "1" * 64,
    ))
    receipt, _receipt_path = acquire_professional_videos(
        manifest_path, handoff_ref=tmp_path / "handoff.json",
        manual_root=manual_root, output_root=output_root,
    )
    row = receipt["assets"][0]
    assert row["popularCatalogRef"] == catalog_ref
    assert row["contentSha256"] == candidate["manualFileSha256"]
    assert row["popularitySignals"] == {
        **popularity, "observedAt": candidate["observedAt"],
        "provider": candidate["provider"], "topic": candidate["topic"],
        "timeBucket": candidate["timeBucket"], "rankingEligible": True,
        "ineligibleReason": "",
    }


def test_slideshow_is_not_counted_as_sourced_or_premium_video(tmp_path: Path) -> None:
    manual_root = tmp_path / "manual"
    manual_root.mkdir()
    _write_slideshow(manual_root / "slides.mp4")
    manifest_path = tmp_path / "manifest.json"
    write_json(
        manifest_path,
        _manifest(
            [_item("slides", "slides.mp4", counts=(1_000, 20, 2, 1, 3))],
            manifest_id="slides",
        ),
    )
    receipt, _receipt_path = acquire_professional_videos(
        manifest_path,
        handoff_ref=tmp_path / "handoff.json",
        manual_root=manual_root,
        output_root=tmp_path / "acquisition",
    )
    row = receipt["assets"][0]
    assert row["acquisitionStatus"] == "acquired"
    assert row["distributionDecision"] == "blocked"
    assert row["mediaProbe"]["staticImageSequence"] is True
    assert row["mediaProbe"]["premiumPlayableEligible"] is False
    assert row["planVideoSpec"] is None


def test_commercial_lifecycle_rejects_unverified_acquired_video(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manual_root = tmp_path / "manual"
    manual_root.mkdir()
    _write_video(manual_root / "research-only.mp4", moving=True, seed=11)
    monkeypatch.setattr(
        "content.source.professional_video_acquisition.load_content_distribution_policy",
        lambda: SimpleNamespace(
            product_lifecycle_state=ProductLifecycleState.COMMERCIAL
        ),
    )
    manifest_path = tmp_path / "manifest.json"
    write_json(
        manifest_path,
        _manifest(
            [
                _item(
                    "research-only",
                    "research-only.mp4",
                    counts=(1_000, 20, 2, 1, 3),
                )
            ],
            manifest_id="commercial-filter",
        ),
    )
    receipt, _receipt_path = acquire_professional_videos(
        manifest_path,
        handoff_ref=tmp_path / "handoff.json",
        manual_root=manual_root,
        output_root=tmp_path / "acquisition",
    )
    row = receipt["assets"][0]
    assert row["acquisitionStatus"] == "acquired"
    assert row["distributionDecision"] == "blocked"
    assert row["failureCode"] == "DATA.SOURCE.COMMERCIAL_RIGHTS_REQUIRED"
    assert receipt["acceptedAssetCount"] == 0


def test_commercial_lifecycle_emits_commercial_plan_for_verified_video(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manual_root = tmp_path / "manual"
    manual_root.mkdir()
    _write_video(manual_root / "commercial.mp4", moving=True, seed=17)
    monkeypatch.setattr(
        "content.source.professional_video_acquisition.load_content_distribution_policy",
        lambda: SimpleNamespace(
            product_lifecycle_state=ProductLifecycleState.COMMERCIAL
        ),
    )
    item = _item(
        "commercial",
        "commercial.mp4",
        counts=(8_000, 420, 36, 24, 180),
    )
    item.update(
        rightsStatus="verified",
        license="Pexels License",
        authorizationProof="https://www.pexels.com/license/",
        rightsIssues=[],
        modelReleaseStatus="not_required",
    )
    manifest_path = tmp_path / "commercial.json"
    write_json(manifest_path, _manifest([item], manifest_id="commercial"))

    receipt, _receipt_path = acquire_professional_videos(
        manifest_path,
        handoff_ref=tmp_path / "handoff.json",
        manual_root=manual_root,
        output_root=tmp_path / "acquisition",
    )

    row = receipt["assets"][0]
    assert row["distributionDecision"] == "commercial_allowed"
    assert row["planVideoSpec"]["publicationAdmission"] == "commercial_release"
    assert row["planVideoSpec"]["commercialAuthorizationStatus"] == "verified"


@pytest.mark.parametrize(
    ("path_name", "api_evidence"),
    [
        ("public_direct", ""),
        ("supported_api", "https://api.pexels.example.test/evidence/asset"),
    ],
)
def test_public_and_supported_api_paths_freeze_transport_bytes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    path_name: str,
    api_evidence: str,
) -> None:
    source = tmp_path / "source.mp4"
    _write_video(source, moving=True, seed=6)

    def fake_fetch(url: str, destination: Path, *, supported_api: bool) -> str:
        assert url == "https://cdn.pexels.example.test/video.mp4"
        assert supported_api is (path_name == "supported_api")
        shutil.copyfile(source, destination)
        return ".mp4"

    monkeypatch.setattr(
        "content.source.professional_video_acquisition.fetch_public_video",
        fake_fetch,
    )
    item = _item(
        path_name,
        "",
        counts=(200, 10, 2, 1, 4),
        acquisition_path=path_name,
        asset_url="https://cdn.pexels.example.test/video.mp4",
        api_evidence=api_evidence,
    )
    receipt, _path, output_root = _acquire(
        tmp_path,
        [item],
        manifest_id=f"network-{path_name}",
    )
    row = receipt["assets"][0]
    assert row["acquisitionStatus"] == "acquired"
    assert row["distributionDecision"] == "research_allowed"
    assert (output_root / row["assetRef"]).is_file()


def test_receipt_and_plan_bindings_fail_closed_on_tamper(tmp_path: Path) -> None:
    manual_root = tmp_path / "manual"
    manual_root.mkdir()
    _write_video(manual_root / "accepted.mp4", moving=True, seed=7)
    manifest_path = tmp_path / "manifest.json"
    write_json(
        manifest_path,
        _manifest(
            [_item("accepted", "accepted.mp4", counts=(20, 3, 1, 1, 1))],
            manifest_id="tamper",
        ),
    )
    output_root = tmp_path / "acquisition"
    receipt, receipt_path = acquire_professional_videos(
        manifest_path,
        handoff_ref=tmp_path / "handoff.json",
        manual_root=manual_root,
        output_root=output_root,
    )
    receipt_ref = receipt_path.relative_to(output_root).as_posix()
    tampered = json.loads(json.dumps(receipt))
    tampered["acceptedAssetCount"] = 0
    write_json(receipt_path, tampered)
    with pytest.raises(ValueError, match="digest mismatch"):
        load_professional_video_acquisition_receipt(receipt_ref, root=output_root)


def test_auto_plan_selects_highest_comparable_professional_video(tmp_path: Path) -> None:
    manual_root = tmp_path / "manual"
    manual_root.mkdir()
    _write_video(manual_root / "low.mp4", moving=True, seed=8)
    _write_video(manual_root / "high.mp4", moving=True, seed=9)
    manifest_path = tmp_path / "manifest.json"
    write_json(
        manifest_path,
        _manifest([
            _item("low", "low.mp4", counts=(10, 1, 0, 0, 0)),
            _item("high", "high.mp4", counts=(10_000, 300, 30, 20, 50)),
        ], manifest_id="auto-plan"),
    )
    output_root = tmp_path / "acquisition"
    _receipt, receipt_path = acquire_professional_videos(
        manifest_path,
        handoff_ref=tmp_path / "handoff.json",
        manual_root=manual_root,
        output_root=output_root,
    )
    plan_dir = tmp_path / "plan"
    report: dict[str, object] = {"sourceUnavailable": []}
    write_video_lane(
        entity_id="西湖",
        plan_dir=plan_dir,
        force=True,
        report=report,
        updated=[],
        sourced_video_pool=[],
        acquisition_receipt_refs=[receipt_path.relative_to(output_root).as_posix()],
        acquisition_root=output_root,
    )
    plan = read_json(plan_dir / "video_source_plan.json")
    payload = plan["payload"]
    assert plan["acquisitionReceiptRefs"] == [
        receipt_path.relative_to(output_root).as_posix()
    ]
    assert "acquisitionReceiptRefs" not in payload
    assert payload["videos"][0]["professionalAssetId"] == "high"
    assert report["videoDiscovery"][0]["professionalAcquisitionCandidates"] == 2
    assert report["videoDiscovery"][0]["rankingEligibleCandidates"] == 2
