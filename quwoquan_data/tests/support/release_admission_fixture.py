"""Frozen article/video admission fixtures shared by release contract tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from content.release.canonical.asset_review_adoption import _binding
from content.source.independent_asset_review_contract import (
    canonical_digest,
    file_digest,
)
from core.source_digest import content_source_revision


def digest(seed: str) -> str:
    return "sha256:" + hashlib.sha256(seed.encode("utf-8")).hexdigest()


def article_render_profile(
    *,
    mode: str,
    source_ref: str,
    cover_asset_id: str = "",
    body_asset_ids: list[str] | None = None,
) -> dict[str, object]:
    body_ids = list(body_asset_ids or [])
    asset_count = int(bool(cover_asset_id)) + len(body_ids)
    source_unit_ref = source_ref.rsplit("/", 1)[0]
    return {
        "mediaClosure": {
            "schema": "quwoquan_data.article_media_closure",
            "mode": mode,
            "sourceRef": source_ref,
            "sourceUnitRef": source_unit_ref,
            "assetCount": asset_count,
            "coverAssetId": cover_asset_id,
            "bodyAssetIds": body_ids,
            "sourceAssetReceiptRef": "5.review/article_source_asset_receipt.json",
            "sourceAssetReceiptDigest": digest(
                f"article-source-assets:{mode}:{cover_asset_id}:{','.join(body_ids)}"
            ),
            "sourceAssetCounts": [
                {
                    "displayName": "文章同源素材",
                    "provider": "Research Media",
                    "plannedAssetCount": asset_count,
                    "discoveredAssetCount": asset_count,
                    "downloadedAssetCount": asset_count,
                    "acceptedAssetCount": asset_count,
                    "rejectedAssetCount": 0,
                    "verifiedAssetCount": 0,
                    "unverifiedAssetCount": asset_count,
                    "restrictedAssetCount": 0,
                    "unknownAssetCount": 0,
                }
            ],
        }
    }


def publishable_video_review_receipt(
    *,
    asset_id: str,
    content_sha256: str,
    object_ref: str,
    source_digest: str,
    entity_catalog_digest: str,
) -> dict[str, Any]:
    identity_seed = f"{object_ref}:{asset_id}:{content_sha256}"
    snapshot = {
        "assetId": asset_id,
        "entityId": object_ref,
        "observedEntityId": object_ref,
        "contentSha256": content_sha256,
        "casRef": f"data/local/workspace/source-acquisition/video/cas/{asset_id}.mp4",
        "sourceUrl": f"https://video.example/work/{asset_id}",
        "platform": "Pexels Videos",
        "creator": "Research Video Creator",
        "capturedAt": "2026-08-05T00:00:00Z",
        "license": "unknown",
        "termsUrl": "https://video.example/terms",
        "authorizationProof": "",
        "rightsIssues": ["commercial authorization missing"],
        "acquisitionStatus": "acquired",
        "rightsStatus": "unverified",
        "authorizationRequired": True,
        "distributionDecision": "research_allowed",
        "mediaProbe": {
            "width": 1920,
            "height": 1080,
            "frameCount": 300,
            "framesPerSecond": 30.0,
            "durationMs": 10000,
            "codec": "h264",
            "hasAudio": False,
            "sampleCount": 12,
            "distinctFrameCount": 12,
            "movingTransitionCount": 11,
            "meanTransitionDelta": 0.3,
            "playable": True,
            "motionVideo": True,
            "staticImageSequence": False,
            "premiumPlayableEligible": True,
        },
        "popularitySignals": {
            "playCount": 10000,
            "likeCount": 1200,
            "commentCount": 80,
            "shareCount": 45,
            "favoriteCount": 300,
            "observedAt": "2026-08-05T00:00:00Z",
            "provider": "pexels_videos",
            "topic": object_ref,
            "timeBucket": "2026-W32",
            "popularityScore": 9.2,
            "popularityPercentile": 1.0,
            "rankingEligible": True,
            "rankingIneligibleReason": "",
            "comparisonCandidateCount": 2,
        },
    }
    acquisition = {
        "executionId": "video-acquisition",
        "objectRef": object_ref,
        "provider": "professional_video_acquisition",
        "model": "deterministic",
        "runId": f"video-acquisition-{digest(identity_seed)[7:19]}",
        "evidenceRef": "evidence/acquisition.json",
        "evidenceSha256": digest(f"acquisition:{identity_seed}"),
    }
    author = {
        **acquisition,
        "executionId": "video-author",
        "provider": "codex_sdk",
        "model": "gpt-5.6-terra",
        "runId": f"video-author-{digest(identity_seed)[19:31]}",
        "evidenceRef": "evidence/author.json",
        "evidenceSha256": digest(f"author:{identity_seed}"),
    }
    reviewer = {
        **author,
        "executionId": "video-reviewer",
        "runId": f"video-reviewer-{digest(identity_seed)[31:43]}",
        "modelFamily": "gpt",
        "resultHash": digest(f"review-result:{identity_seed}"),
        "evidenceRef": "evidence/reviewer.json",
        "evidenceSha256": digest(f"reviewer:{identity_seed}"),
    }
    receipt: dict[str, Any] = {
        "schema": "quwoquan_data.independent_asset_review_receipt",
        "reviewId": "asset-review-" + hashlib.sha256(identity_seed.encode()).hexdigest(),
        "assetKind": "video",
        "objectRef": object_ref,
        "sourceRevision": content_source_revision(
            source_digest=source_digest,
            entity_catalog_digest=entity_catalog_digest,
        ),
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
        "acquisitionReceiptRef": (
            "data/local/workspace/source-acquisition/video/receipts/"
            + hashlib.sha256(f"acquisition:{identity_seed}".encode()).hexdigest()
            + ".json"
        ),
        "acquisitionReceiptDigest": digest(f"acquisition-receipt:{identity_seed}"),
        "acquisitionReceiptSha256": digest(f"acquisition-file:{identity_seed}"),
        "executionManifestRef": "data/tasks/video/execution_manifest.json",
        "executionManifestSha256": digest(f"execution-manifest:{identity_seed}"),
        "assetSnapshot": snapshot,
        "acquisitionExecution": acquisition,
        "authorExecution": author,
        "reviewerExecution": reviewer,
        "judgment": {
            "rightsStatus": "unverified",
            "authorizationRequired": True,
            "distributionDecision": "research_allowed",
            "safetyStatus": "passed",
            "entityMatch": "matched",
            "qualityStatus": "passed",
            "privacyRisk": "none",
            "minorRisk": "none",
            "maliciousMediaRisk": "none",
            "watermarkStatus": "absent",
            "findings": ["independent review passed"],
        },
        "reviewDecision": "accepted",
        "recordedAt": "2026-08-05T00:10:00Z",
    }
    receipt["receiptDigest"] = canonical_digest(receipt)
    return receipt


def bind_publishable_video_review(
    *,
    object_root: Path,
    asset_id: str,
    content_sha256: str,
    object_ref: str,
    source_digest: str,
    entity_catalog_digest: str,
    receipt: dict[str, Any] | None = None,
) -> Path:
    selected = receipt or publishable_video_review_receipt(
        asset_id=asset_id,
        content_sha256=content_sha256,
        object_ref=object_ref,
        source_digest=source_digest,
        entity_catalog_digest=entity_catalog_digest,
    )
    receipt_ref = Path("asset_reviews/receipts") / f"{selected['reviewId']}.json"
    receipt_path = object_root / receipt_ref
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(selected), encoding="utf-8")
    rights_path = object_root / "rights.json"
    rights = json.loads(rights_path.read_text(encoding="utf-8"))
    matches = [row for row in rights["assets"] if row.get("assetId") == asset_id]
    if len(matches) != 1:
        raise ValueError(f"video fixture rights asset is missing or ambiguous: {asset_id}")
    matches[0]["acquisitionReceiptRef"] = selected["acquisitionReceiptRef"]
    matches[0]["independentAssetReview"] = _binding(
        selected,
        receipt_ref=receipt_ref.as_posix(),
        receipt_file_sha256=file_digest(receipt_path),
    )
    rights_path.write_text(json.dumps(rights), encoding="utf-8")
    return receipt_path


__all__ = [
    "article_render_profile",
    "bind_publishable_video_review",
    "digest",
    "publishable_video_review_receipt",
]
