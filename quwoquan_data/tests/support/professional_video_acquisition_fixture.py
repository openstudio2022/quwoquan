"""Reusable professional-video acquisition fixtures."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from content.source.professional_video_acquisition import acquire_professional_videos
from core.io import write_json

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64


def write_video(path: Path, *, moving: bool, seed: int) -> None:
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


def write_slideshow(path: Path) -> None:
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


def video_item(
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


def video_manifest(
    items: list[dict[str, object]],
    *,
    manifest_id: str = "video-test",
    source_revision: str = "local-contract-revision",
    source_digest: str = DIGEST_A,
    entity_catalog_digest: str = DIGEST_B,
) -> dict[str, object]:
    return {
        "schema": "quwoquan_data.professional_video_acquisition_manifest",
        "manifestId": manifest_id,
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
        "items": items,
    }


def acquire_video_fixture(
    tmp_path: Path,
    items: list[dict[str, object]],
    *,
    manifest_id: str = "video-test",
) -> tuple[dict[str, object], Path, Path]:
    manual_root = tmp_path / "manual"
    output_root = tmp_path / "acquisition"
    manual_root.mkdir(exist_ok=True)
    manifest_path = tmp_path / f"{manifest_id}.json"
    write_json(manifest_path, video_manifest(items, manifest_id=manifest_id))
    receipt, receipt_path = acquire_professional_videos(
        manifest_path,
        handoff_ref=tmp_path / "handoff.json",
        manual_root=manual_root,
        output_root=output_root,
    )
    return receipt, receipt_path, output_root


__all__ = [
    "DIGEST_A",
    "DIGEST_B",
    "DIGEST_C",
    "acquire_video_fixture",
    "video_item",
    "video_manifest",
    "write_slideshow",
    "write_video",
]
