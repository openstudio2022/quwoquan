# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from content.execution.campaign.external_input_runtime import (
    ExternalInputRuntimeContext,
)
from content.execution.campaign.external_inputs import (
    PROFESSIONAL_VIDEO_ACQUISITION_KIND,
    CampaignExternalInputError,
    bind_external_input_refs,
    content_source_revision,
    materialize_external_input_bundle,
    verify_external_input_refs,
)
from content.source import handler_fetch_setup, source_inputs
from content.source.professional_video_acquisition import (
    acquire_professional_videos,
)
from content.source.research.auto_plan_video import write_video_lane
from core.io import read_json, write_json

SOURCE_DIGEST = "sha256:" + "4" * 64
ENTITY_CATALOG_DIGEST = "sha256:" + "5" * 64
SOURCE_REVISION = content_source_revision(
    source_digest=SOURCE_DIGEST,
    entity_catalog_digest=ENTITY_CATALOG_DIGEST,
)
EXECUTION_ID = "20260805--travel-video-m100--china--scale-201"


@pytest.fixture(autouse=True)
def _governed_acquisition_handoff(monkeypatch: pytest.MonkeyPatch) -> None:
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


def _write_motion_video(path: Path, *, variant: int = 0) -> None:
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (320, 180)
    )
    if not writer.isOpened():
        raise RuntimeError("test MP4 writer did not open")
    try:
        for index in range(36):
            frame = np.full((180, 320, 3), 18 + variant, dtype=np.uint8)
            left = round(index * 240 / 35)
            cv2.rectangle(
                frame,
                (left, 20),
                (left + 72, 145),
                (255 - variant, 255, 255),
                thickness=-1,
            )
            cv2.putText(
                frame,
                f"frame-{index:02d}",
                (8, 170),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
            writer.write(frame)
    finally:
        writer.release()


def _video_item(
    *,
    asset_id: str = "west-lake-professional-video",
    manual_file: str = "west-lake.mp4",
    play_count: int = 50_000,
) -> dict[str, object]:
    return {
        "assetId": asset_id,
        "entityId": "西湖",
        "observedEntityId": "西湖",
        "entityAliases": ["杭州西湖", "西湖风景名胜区"],
        "provider": "pexels_videos",
        "platform": "Pexels Videos",
        "displayName": "Pexels 专业旅行视频",
        "sourceKind": "tourism_video_site",
        "acquisitionPath": "manual_file",
        "sourceUrl": f"https://videos.example.test/posts/{asset_id}",
        "assetUrl": "",
        "manualFile": manual_file,
        "apiEvidence": "",
        "accessEvidence": {
            "anonymousAssetAccess": False,
            "loginRequired": False,
            "captchaRequired": False,
            "paywallRequired": False,
            "drmProtected": False,
            "accessControlBypass": False,
        },
        "title": "西湖旅行实拍",
        "relevance": "杭州西湖风景名胜区水面与沿岸旅行实景",
        "creator": "Creator West Lake",
        "capturedAt": "2026-08-05T02:00:00Z",
        "rightsStatus": "verified",
        "license": "commercial redistribution authorization verified",
        "termsUrl": "https://videos.example.test/terms",
        "authorizationProof": f"https://videos.example.test/authorizations/{asset_id}",
        "rightsIssues": [],
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
            "playCount": play_count,
            "likeCount": play_count // 50,
            "commentCount": play_count // 625,
            "shareCount": play_count // 1250,
            "favoriteCount": play_count // 500,
            "observedAt": "2026-08-05T01:00:00Z",
            "provider": "pexels_videos",
            "topic": "west-lake-travel",
            "timeBucket": "2026-W32",
        },
    }


def _acquisition(tmp_path: Path) -> tuple[Path, list[dict[str, object]]]:
    acquisition_root = tmp_path / "source-acquisition"
    video_root = acquisition_root / "video"
    manual_root = tmp_path / "manual"
    manifest_path = video_root / "manifests/video.json"
    manual_root.mkdir(parents=True)
    _write_motion_video(manual_root / "west-lake.mp4")
    _write_motion_video(
        manual_root / "west-lake-secondary.mp4",
        variant=7,
    )
    write_json(
        manifest_path,
        {
            "schema": "quwoquan_data.professional_video_acquisition_manifest",
            "manifestId": "campaign-video-input",
            "sourceRevision": SOURCE_REVISION,
            "sourceDigest": SOURCE_DIGEST,
            "entityCatalogDigest": ENTITY_CATALOG_DIGEST,
            "items": [
                _video_item(),
                _video_item(
                    asset_id="west-lake-professional-video-secondary",
                    manual_file="west-lake-secondary.mp4",
                    play_count=25_000,
                ),
            ],
        },
    )
    _, receipt_path = acquire_professional_videos(
        manifest_path,
        handoff_ref=tmp_path / "handoff.json",
        manual_root=manual_root,
        output_root=video_root,
    )
    refs = bind_external_input_refs(
        "video",
        [
            {
                "kind": PROFESSIONAL_VIDEO_ACQUISITION_KIND,
                "acquisitionRootRef": "video",
                "manifestRef": manifest_path.relative_to(video_root).as_posix(),
                "receiptRef": receipt_path.relative_to(video_root).as_posix(),
            }
        ],
        acquisition_root=acquisition_root,
        source_revision=SOURCE_REVISION,
        source_digest=SOURCE_DIGEST,
        entity_catalog_digest=ENTITY_CATALOG_DIGEST,
    )
    return acquisition_root, refs


def _context(bundle: Path, refs: list[dict[str, object]]) -> ExternalInputRuntimeContext:
    blobs = {
        str(blob["contentSha256"]): (
            Path(str(row["acquisitionRootRef"])) / str(blob["blobRef"])
        ).as_posix()
        for row in refs
        for blob in row["blobRefs"]
    }
    return ExternalInputRuntimeContext(
        root=bundle,
        envelope={"executionId": EXECUTION_ID, "carrier": "video"},
        refs=tuple(dict(row) for row in refs),
        blob_refs_by_digest=blobs,
    )


def test_video_external_input_freezes_typed_manifest_receipt_and_cas(
    tmp_path: Path,
) -> None:
    acquisition_root, refs = _acquisition(tmp_path)
    assert refs[0]["kind"] == PROFESSIONAL_VIDEO_ACQUISITION_KIND
    assert refs[0]["acquisitionRootRef"] == "video"
    assert refs[0]["sourceRevision"] == SOURCE_REVISION
    assert refs[0]["sourceDigest"] == SOURCE_DIGEST
    assert refs[0]["entityCatalogDigest"] == ENTITY_CATALOG_DIGEST
    assert refs[0]["manifestFileDigest"].startswith("sha256:")
    assert refs[0]["receiptFileDigest"].startswith("sha256:")
    assert refs[0]["blobRefs"][0]["contentSha256"].startswith("sha256:")

    bundle = tmp_path / "capsule/external-inputs/video"
    materialize_external_input_bundle(
        bundle,
        refs,
        acquisition_root=acquisition_root,
        carrier="video",
        source_revision=SOURCE_REVISION,
        source_digest=SOURCE_DIGEST,
        entity_catalog_digest=ENTITY_CATALOG_DIGEST,
    )
    assert verify_external_input_refs(
        "video",
        refs,
        acquisition_root=bundle,
        source_revision=SOURCE_REVISION,
        source_digest=SOURCE_DIGEST,
        entity_catalog_digest=ENTITY_CATALOG_DIGEST,
    ) == refs

    with pytest.raises(CampaignExternalInputError, match="not admitted for image"):
        bind_external_input_refs(
            "image",
            [
                {
                    "kind": PROFESSIONAL_VIDEO_ACQUISITION_KIND,
                    "acquisitionRootRef": "video",
                    "manifestRef": refs[0]["manifestRef"],
                    "receiptRef": refs[0]["receiptRef"],
                }
            ],
            acquisition_root=acquisition_root,
            source_revision=SOURCE_REVISION,
            source_digest=SOURCE_DIGEST,
            entity_catalog_digest=ENTITY_CATALOG_DIGEST,
        )
    with pytest.raises(CampaignExternalInputError, match="IDENTITY_DRIFT"):
        verify_external_input_refs(
            "video",
            refs,
            acquisition_root=acquisition_root,
            source_revision=SOURCE_REVISION,
            source_digest="sha256:" + "9" * 64,
            entity_catalog_digest=ENTITY_CATALOG_DIGEST,
        )


def test_video_plan_and_fetch_consume_only_explicit_capsule_refs_and_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acquisition_root, refs = _acquisition(tmp_path)
    bundle = tmp_path / "capsule/external-inputs/video"
    materialize_external_input_bundle(
        bundle,
        refs,
        acquisition_root=acquisition_root,
        carrier="video",
        source_revision=SOURCE_REVISION,
        source_digest=SOURCE_DIGEST,
        entity_catalog_digest=ENTITY_CATALOG_DIGEST,
    )
    context = _context(bundle, refs)
    receipt_refs = context.receipt_refs(PROFESSIONAL_VIDEO_ACQUISITION_KIND)
    professional_root = context.acquisition_root(
        PROFESSIONAL_VIDEO_ACQUISITION_KIND
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
        acquisition_receipt_refs=receipt_refs,
        acquisition_root=professional_root,
    )
    plan_path = plan_dir / "video_source_plan.json"
    plan = read_json(plan_path)
    payload = plan["payload"]
    assert plan["acquisitionReceiptRefs"] == receipt_refs
    assert "acquisitionReceiptRefs" not in payload
    assert payload["videos"][0]["professionalAcquisitionReceiptRef"] in receipt_refs

    monkeypatch.setattr(
        source_inputs,
        "_source_plan_files",
        lambda *_args, **_kwargs: [("video", plan_path)],
    )
    candidates = source_inputs.curated_sourced_videos_for_entity(
        EXECUTION_ID,
        "西湖",
        "景区",
        external_input_context=context,
    )
    assert len(candidates) == 1
    assert source_inputs.curated_images_for_entity(
        EXECUTION_ID,
        "西湖",
        "景区",
        research_lane="video",
        external_input_context=context,
    ) == []
    captured: dict[str, object] = {}

    def fake_fetch(**kwargs: object) -> list[Path]:
        captured.update(kwargs)
        return []

    monkeypatch.setattr(handler_fetch_setup, "fetch_admitted_sourced_videos", fake_fetch)
    monkeypatch.setattr(
        handler_fetch_setup,
        "_curated_sources_for_lanes",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        handler_fetch_setup,
        "resolve_entity_object_dir",
        lambda *_args, **_kwargs: tmp_path / "entity",
    )
    fetch_plan = handler_fetch_setup.prepare_entity_fetch_plan(
        execution_id=EXECUTION_ID,
        entity_id="西湖",
        entity_type="景区",
        domain="travel",
        etype="scenic_spot",
        selected_lanes={"video"},
        external_input_context=context,
    )
    assert fetch_plan.sourced_video_candidates == candidates
    assert captured["professional_acquisition_root"] == professional_root

    blob = context.blob_path(str(refs[0]["blobRefs"][0]["contentSha256"]))
    blob.write_bytes(blob.read_bytes() + b"replacement")
    with pytest.raises(CampaignExternalInputError, match="DIGEST_DRIFT|digest mismatch"):
        verify_external_input_refs(
            "video",
            refs,
            acquisition_root=bundle,
            source_revision=SOURCE_REVISION,
            source_digest=SOURCE_DIGEST,
            entity_catalog_digest=ENTITY_CATALOG_DIGEST,
        )
