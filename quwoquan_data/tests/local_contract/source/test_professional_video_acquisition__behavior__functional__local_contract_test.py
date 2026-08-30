from __future__ import annotations

import json
import shutil
from pathlib import Path

import cv2
import numpy as np
import pytest
from content.source import professional_video_acquisition
from content.source import professional_video_receipt
from content.source.professional_video_acquisition import (
    ProfessionalVideoAcquisitionBlocked,
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
from content.source.professional_video_spec_index import (
    build_acquired_video_spec_index,
)
from content.source.professional_video_store import (
    ProfessionalVideoCasCollision,
    put_video_cas,
)
from content.source.research.auto_plan_video import write_video_lane
from core.io import read_json, write_json

_DIGEST_A = "sha256:" + "a" * 64
_DIGEST_B = "sha256:" + "b" * 64
_DIGEST_C = "sha256:" + "c" * 64


@pytest.fixture(autouse=True)
def _acquisition_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "content.source.professional_video_acquisition.guard_acquisition_source_identity",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        "content.source.professional_video_acquisition.load_bound_safety_evidence",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        "content.source.professional_video_acquisition.validate_video_safety_payload",
        lambda *_args, **_kwargs: None,
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
            "safetyEvidenceFileSha256": "sha256:" + "f" * 64,
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
    monkeypatch: pytest.MonkeyPatch,
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

    digest_calls: list[Path] = []
    active_digest_calls = 0
    max_active_digest_calls = 0
    original_file_digest = professional_video_receipt.file_digest

    def counted_file_digest(path: Path) -> str:
        nonlocal active_digest_calls, max_active_digest_calls
        active_digest_calls += 1
        max_active_digest_calls = max(max_active_digest_calls, active_digest_calls)
        digest_calls.append(path)
        try:
            return original_file_digest(path)
        finally:
            active_digest_calls -= 1

    monkeypatch.setattr(
        professional_video_receipt,
        "file_digest",
        counted_file_digest,
    )
    index = build_acquired_video_spec_index(
        [receipt_path.relative_to(output_root).as_posix()],
        root=output_root,
    )
    unique_acquired_digests = {
        str(row["contentSha256"])
        for row in receipt["assets"]
        if row["acquisitionStatus"] == "acquired"
    }
    assert len(digest_calls) == len(unique_acquired_digests)
    assert max_active_digest_calls == 1
    assert index.accepted_asset_count == 2
    assert index.entity_names == ("西湖",)

    # One verified immutable index serves every catalog lookup. Repeated entity
    # and alias probes must not reopen or rehash the capsule CAS.
    for entity_name in ("西湖", "杭州西湖", "西湖"):
        projected = index.specs_for_names((entity_name, "西湖"))
        assert [row["professionalAssetId"] for row in projected] == [
            "higher",
            "lower",
        ]
    assert len(digest_calls) == len(unique_acquired_digests)

    projected[0]["title"] = "mutated caller copy"
    assert index.specs_for_entity("西湖")[0]["title"] != "mutated caller copy"


def test_reference_only_manual_video_records_rights_without_blocking_research(
    tmp_path: Path,
) -> None:
    manual_root = tmp_path / "manual"
    manual_root.mkdir()
    _write_video(manual_root / "youtube.mp4", moving=True, seed=31)
    item = _item(
        "youtube-manual",
        "youtube.mp4",
        counts=(None, None, None, None, None),
    )
    item.update(
        provider="youtube",
        platform="YouTube",
        displayName="YouTube research reference",
        sourceUrl="https://www.youtube.com/watch?v=research-reference",
        termsUrl="https://www.youtube.com/static?template=terms",
        popularitySignals={
            **item["popularitySignals"],
            "provider": "youtube",
        },
    )
    manifest_path = tmp_path / "youtube.json"
    write_json(manifest_path, _manifest([item], manifest_id="youtube-research"))

    receipt, _receipt_path = acquire_professional_videos(
        manifest_path,
        handoff_ref=tmp_path / "handoff.json",
        manual_root=manual_root,
        output_root=tmp_path / "acquisition",
    )

    row = receipt["assets"][0]
    assert receipt["acceptedAssetCount"] == 1
    assert row["acquisitionStatus"] == "acquired"
    assert row["rightsStatus"] == "unverified"
    assert row["authorizationRequired"] is True
    assert row["distributionDecision"] == "research_allowed"
    assert row["planVideoSpec"]["distributionDecision"] == "research_allowed"
    assert row["planVideoSpec"]["commercialAuthorizationStatus"] == "unverified"


def test_reference_only_video_forbids_unapproved_network_acquisition(
    tmp_path: Path,
) -> None:
    item = _item(
        "youtube-public-direct",
        "",
        counts=(None, None, None, None, None),
        acquisition_path="public_direct",
        asset_url="https://cdn.youtube.example.test/video.mp4",
    )
    item.update(
        provider="youtube",
        platform="YouTube",
        displayName="YouTube research reference",
        sourceUrl="https://www.youtube.com/watch?v=research-reference",
        termsUrl="https://www.youtube.com/static?template=terms",
        popularitySignals={
            **item["popularitySignals"],
            "provider": "youtube",
        },
    )
    manifest_path = tmp_path / "youtube-public-direct.json"
    write_json(manifest_path, _manifest([item], manifest_id="youtube-public-direct"))

    with pytest.raises(ProfessionalVideoAcquisitionBlocked) as captured:
        acquire_professional_videos(
            manifest_path,
            handoff_ref=tmp_path / "handoff.json",
            output_root=tmp_path / "acquisition",
        )
    assert captured.value.code == "DATA.SOURCE.VIDEO_BATCH_NO_SUCCESS"
    assert captured.value.receipt["assets"][0]["failureCode"] == (
        "DATA.SOURCE.ITEM_PREVALIDATION_FAILED"
    )
    assert "public_direct is not allowed" in captured.value.receipt["assets"][0][
        "failure"
    ]


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
    with pytest.raises(ProfessionalVideoAcquisitionBlocked) as captured:
        acquire("same-identity")
    duplicate = captured.value.receipt
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

