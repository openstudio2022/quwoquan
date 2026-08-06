from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from content.release.canonical.asset_review_adoption import _binding
from content.release.canonical.object_transaction_contract import ObjectTransactionError
from content.release.canonical.release_admission import (
    _article_media_coverage,
    build_release_asset_admission,
)
from content.source.independent_asset_review_contract import (
    canonical_digest,
    file_digest,
)
from core.source_digest import content_source_revision
from governance.coverage.distribution import (
    ProductLifecycleState,
    ReleaseClass,
    load_content_distribution_policy,
)


def _digest(seed: str) -> str:
    return "sha256:" + hashlib.sha256(seed.encode("utf-8")).hexdigest()


_SOURCE_DIGEST = _digest("release-admission-source")
_ENTITY_CATALOG_DIGEST = _digest("release-admission-entities")


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _rights_asset(asset_id: str) -> dict[str, object]:
    return {
        "assetId": asset_id,
        "asset": {"sha256": _digest(asset_id), "bytes": 128},
        "rightsAuditStatus": "unverified",
        "rightsAuditIssues": ["commercial authorization missing"],
        "sourceUrl": f"https://media.example/{asset_id}",
        "platform": "Pinterest",
        "creator": "摄影师",
        "capturedAt": "2026-08-02T00:00:00Z",
        "license": "unknown",
        "termsUrl": "https://media.example/terms",
        "authorizationProof": "",
    }


def _research_policy():
    return replace(
        load_content_distribution_policy(),
        product_lifecycle_state=ProductLifecycleState.RESEARCH,
        release_class=ReleaseClass.RESEARCH,
    )


def _source_asset_counts(asset_count: int) -> list[dict[str, object]]:
    return [
        {
            "displayName": "文章同源素材",
            "provider": "Pinterest",
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
    ]


def _article_render_profile(
    *,
    mode: str,
    cover_asset_id: str = "",
    body_asset_ids: list[str] | None = None,
) -> dict[str, object]:
    body_ids = list(body_asset_ids or [])
    asset_count = int(bool(cover_asset_id)) + len(body_ids)
    return {
        "mediaClosure": {
            "schema": "quwoquan_data.article_media_closure",
            "mode": mode,
            "sourceRef": "sources/article-1/source.md",
            "sourceUnitRef": "sources/article-1",
            "assetCount": asset_count,
            "coverAssetId": cover_asset_id,
            "bodyAssetIds": body_ids,
            "sourceAssetReceiptRef": "5.review/article_source_asset_receipt.json",
            "sourceAssetReceiptDigest": _digest(
                f"article-source-assets:{mode}:{cover_asset_id}:{','.join(body_ids)}"
            ),
            "sourceAssetCounts": _source_asset_counts(asset_count),
        }
    }


def _publishable_video_receipt() -> dict[str, object]:
    source_revision = content_source_revision(
        source_digest=_SOURCE_DIGEST,
        entity_catalog_digest=_ENTITY_CATALOG_DIGEST,
    )
    snapshot = {
        "assetId": "asset-v",
        "entityId": "video",
        "observedEntityId": "video",
        "contentSha256": _digest("asset-v"),
        "casRef": "data/local/workspace/source-acquisition/video/cas/video.mp4",
        "sourceUrl": "https://video.example/work/asset-v",
        "platform": "Pexels Videos",
        "creator": "摄影师乙",
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
            "topic": "video",
            "timeBucket": "2026-W32",
            "popularityScore": 9.2,
            "popularityPercentile": 1.0,
            "rankingEligible": True,
            "rankingIneligibleReason": "",
            "comparisonCandidateCount": 2,
        },
    }
    execution = {
        "executionId": "video-acquisition",
        "objectRef": "video",
        "provider": "professional_video_acquisition",
        "model": "deterministic",
        "runId": "video-acquisition-run",
        "evidenceRef": "evidence/acquisition.json",
        "evidenceSha256": _digest("video-acquisition-evidence"),
    }
    author = {
        **execution,
        "executionId": "video-author",
        "provider": "codex_sdk",
        "model": "gpt-5.6-terra",
        "runId": "video-author-run",
        "evidenceRef": "evidence/author.json",
        "evidenceSha256": _digest("video-author-evidence"),
    }
    reviewer = {
        **author,
        "executionId": "video-reviewer",
        "runId": "video-reviewer-run",
        "modelFamily": "gpt",
        "resultHash": _digest("video-review-result"),
        "evidenceRef": "evidence/reviewer.json",
        "evidenceSha256": _digest("video-reviewer-evidence"),
    }
    receipt: dict[str, object] = {
        "schema": "quwoquan_data.independent_asset_review_receipt",
        "reviewId": "asset-review-" + hashlib.sha256(b"video-review").hexdigest(),
        "assetKind": "video",
        "objectRef": "video",
        "sourceRevision": source_revision,
        "sourceDigest": _SOURCE_DIGEST,
        "entityCatalogDigest": _ENTITY_CATALOG_DIGEST,
        "acquisitionReceiptRef": (
            "data/local/workspace/source-acquisition/video/receipts/"
            + hashlib.sha256(b"video-acquisition").hexdigest()
            + ".json"
        ),
        "acquisitionReceiptDigest": _digest("video-acquisition-receipt"),
        "acquisitionReceiptSha256": _digest("video-acquisition-file"),
        "executionManifestRef": "data/tasks/video/execution_manifest.json",
        "executionManifestSha256": _digest("video-execution-manifest"),
        "assetSnapshot": snapshot,
        "acquisitionExecution": execution,
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


def _bind_video_review(root: Path, receipt: dict[str, object] | None = None) -> Path:
    selected = receipt or _publishable_video_receipt()
    receipt_ref = Path("asset_reviews/receipts") / f"{selected['reviewId']}.json"
    receipt_path = root / "posts/video" / receipt_ref
    _write(receipt_path, selected)
    rights_path = root / "posts/video/rights.json"
    rights = json.loads(rights_path.read_text(encoding="utf-8"))
    rights["assets"][0]["acquisitionReceiptRef"] = selected["acquisitionReceiptRef"]
    rights["assets"][0]["independentAssetReview"] = _binding(
        selected,
        receipt_ref=receipt_ref.as_posix(),
        receipt_file_sha256=file_digest(receipt_path),
    )
    _write(rights_path, rights)
    return receipt_path


def _release_objects(root: Path) -> dict[str, list[str]]:
    desired = {
        "entities": ["home"],
        "posts": ["article", "image", "video"],
        "creators": ["creator"],
        "tags": [],
    }
    _write(
        root / "entities/home/manifest.json",
        {
            "entityRef": "home",
            "assets": [
                {
                    "assetId": "asset-h",
                    "kind": "image",
                    "role": "cover",
                    "objectKey": "media/objects/sha256/" + "h" * 64,
                }
            ],
        },
    )
    _write(root / "entities/home/rights.json", {"assets": [_rights_asset("asset-h")]})
    _write(
        root / "posts/article/manifest.json",
        {
            "contentType": "article",
            "publishMediaMode": "same_source_illustrated",
            "articleRenderProfile": _article_render_profile(
                mode="illustrated",
                cover_asset_id="asset-a",
                body_asset_ids=["asset-b"],
            ),
            "assets": [
                {
                    "assetId": "asset-a",
                    "kind": "image",
                    "role": "cover",
                    "sourceRef": "sources/article-1/source.md",
                },
                {
                    "assetId": "asset-b",
                    "kind": "image",
                    "role": "embedded",
                    "sourceRef": "sources/article-1/source.md",
                },
            ],
            "imageBindings": [
                {"assetId": "asset-a"},
                {"assetId": "asset-b"},
            ],
        },
    )
    _write(
        root / "posts/article/rights.json",
        {"assets": [_rights_asset("asset-a"), _rights_asset("asset-b")]},
    )
    _write(
        root / "posts/image/manifest.json",
        {
            "contentType": "image",
            "assets": [
                {
                    "assetId": "asset-i",
                    "kind": "image",
                    "role": "cover",
                    "objectKey": "media/objects/sha256/" + "i" * 64,
                }
            ],
        },
    )
    _write(root / "posts/image/rights.json", {"assets": [_rights_asset("asset-i")]})
    _write(
        root / "posts/video/manifest.json",
        {
            "contentType": "video",
            "sourceDigest": {
                "algorithm": "sha256",
                "digest": _SOURCE_DIGEST,
                "inputs": ["quwoquan_data/control_plane"],
            },
            "assets": [
                {
                    "assetId": "asset-v",
                    "kind": "video",
                    "mimeType": "video/mp4",
                    "sha256": _digest("asset-v"),
                    "objectKey": "media/objects/sha256/" + _digest("asset-v")[7:],
                    "posterAssetId": "asset-p",
                },
                {
                    "assetId": "asset-p",
                    "kind": "image",
                    "role": "cover",
                    "sha256": _digest("asset-p"),
                    "objectKey": "media/objects/sha256/" + _digest("asset-p")[7:],
                },
            ],
        },
    )
    _write(
        root / "posts/video/rights.json",
        {"assets": [_rights_asset("asset-v"), _rights_asset("asset-p")]},
    )
    _bind_video_review(root)
    _write(
        root / "creators/creator/rights_snapshots/avatar.json",
        {"commercialRights": _rights_asset("asset-c")},
    )
    return desired


def test_research_release_accepts_unverified_assets_for_all_four_carriers(
    tmp_path: Path,
) -> None:
    desired = _release_objects(tmp_path)
    admission = build_release_asset_admission(
        release_id="research-release",
        objects_root=tmp_path,
        desired=desired,
        policy=_research_policy(),
    )

    assert admission["releaseClass"] == "research"
    assert admission["containsUnverifiedAssets"] is True
    assert admission["rightsStatusCounts"]["unverified"] == 7
    assert admission["researchAcceptedCount"] == 4
    assert admission["commercialAcceptedCount"] == 0
    assert {row["carrier"]: row["researchAcceptedCount"] for row in admission["carrierCounts"]} == {
        "homepage": 1,
        "article": 1,
        "image": 1,
        "video": 1,
    }


def test_commercial_release_rejects_same_unverified_assets(tmp_path: Path) -> None:
    desired = _release_objects(tmp_path)
    research = load_content_distribution_policy()
    commercial = replace(
        research,
        product_lifecycle_state=ProductLifecycleState.COMMERCIAL,
        release_class=ReleaseClass.COMMERCIAL,
    )

    with pytest.raises(ObjectTransactionError, match="non-commercial assets"):
        build_release_asset_admission(
            release_id="commercial-release",
            objects_root=tmp_path,
            desired=desired,
            policy=commercial,
        )


def test_professional_acquisition_without_frozen_review_is_gate_blocked(
    tmp_path: Path,
) -> None:
    desired = _release_objects(tmp_path)
    rights_path = tmp_path / "posts/image/rights.json"
    rights = json.loads(rights_path.read_text(encoding="utf-8"))
    rights["assets"][0]["acquisitionReceiptRef"] = (
        "data/local/workspace/source-acquisition/image/receipts/"
        + "a" * 64
        + ".json"
    )
    _write(rights_path, rights)

    with pytest.raises(ObjectTransactionError, match="review binding is incomplete"):
        build_release_asset_admission(
            release_id="acquisition-only-release",
            objects_root=tmp_path,
            desired=desired,
            policy=_research_policy(),
        )


def test_article_media_coverage_reports_target_shortfall_without_blocking() -> None:
    policy = load_content_distribution_policy()
    illustrated = {
        "carrier": "article",
        "objectRef": "posts/illustrated",
        "manifest": {
            "publishMediaMode": "same_source_illustrated",
            "articleRenderProfile": _article_render_profile(
                mode="illustrated",
                cover_asset_id="cover",
                body_asset_ids=["body"],
            ),
            "assets": [
                {
                    "assetId": "cover",
                    "kind": "image",
                    "role": "cover",
                    "sourceRef": "sources/article-1/source.md",
                },
                {
                    "assetId": "body",
                    "kind": "image",
                    "role": "embedded",
                    "sourceRef": "sources/article-1/source.md",
                },
            ],
        },
    }
    text_only = {
        "carrier": "article",
        "objectRef": "posts/text-only",
        "manifest": {
            "assets": [],
            "publishMediaMode": "text_only",
            "articleRenderProfile": _article_render_profile(mode="text_only"),
        },
    }
    coverage = _article_media_coverage(
        [illustrated] * 9 + [text_only],
        policy=policy,
    )
    assert coverage["illustratedRate"] == 0.9

    below_target = _article_media_coverage(
        [illustrated] * 8 + [text_only] * 2,
        policy=policy,
    )
    assert below_target == {
        "articleCount": 10,
        "illustratedCount": 8,
        "textOnlyCount": 2,
        "illustratedRate": 0.8,
        "textOnlyRate": 0.2,
    }


def test_article_release_rejects_two_cover_assets_despite_two_bindings(
    tmp_path: Path,
) -> None:
    desired = _release_objects(tmp_path)
    manifest_path = tmp_path / "posts/article/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["assets"][1]["role"] = "cover"
    manifest["imageBindings"] = [{"assetId": "asset-a"}, {"assetId": "asset-b"}]
    _write(manifest_path, manifest)

    with pytest.raises(ObjectTransactionError, match="non-cover body asset"):
        build_release_asset_admission(
            release_id="two-cover-release",
            objects_root=tmp_path,
            desired=desired,
            policy=_research_policy(),
        )


def test_video_release_requires_independent_publishable_review(
    tmp_path: Path,
) -> None:
    desired = _release_objects(tmp_path)
    rights_path = tmp_path / "posts/video/rights.json"
    rights = json.loads(rights_path.read_text(encoding="utf-8"))
    rights["assets"][0].pop("acquisitionReceiptRef")
    rights["assets"][0].pop("independentAssetReview")
    _write(rights_path, rights)

    with pytest.raises(ObjectTransactionError, match="video required media closure"):
        build_release_asset_admission(
            release_id="unreviewed-video-release",
            objects_root=tmp_path,
            desired=desired,
            policy=_research_policy(),
        )


@pytest.mark.parametrize(
    ("section", "field", "value", "expected"),
    [
        (
            "mediaProbe",
            "motionVideo",
            False,
            "playable motion-media evidence",
        ),
    ],
)
def test_video_release_revalidates_motion_evidence(
    tmp_path: Path,
    section: str,
    field: str,
    value: object,
    expected: str,
) -> None:
    desired = _release_objects(tmp_path)
    receipt_path = next(
        (tmp_path / "posts/video/asset_reviews/receipts").glob("*.json")
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["assetSnapshot"][section][field] = value
    receipt["receiptDigest"] = canonical_digest(receipt, excluded="receiptDigest")
    _bind_video_review(tmp_path, receipt)

    with pytest.raises(ObjectTransactionError, match=expected):
        build_release_asset_admission(
            release_id="invalid-video-evidence-release",
            objects_root=tmp_path,
            desired=desired,
            policy=_research_policy(),
        )


@pytest.mark.parametrize("reason", ["incomplete", "single_candidate"])
def test_daily_research_release_accepts_truthfully_unranked_video(
    tmp_path: Path,
    reason: str,
) -> None:
    desired = _release_objects(tmp_path)
    receipt_path = next(
        (tmp_path / "posts/video/asset_reviews/receipts").glob("*.json")
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    signals = receipt["assetSnapshot"]["popularitySignals"]
    signals["rankingEligible"] = False
    signals["popularityPercentile"] = None
    if reason == "incomplete":
        signals["favoriteCount"] = None
        signals["popularityScore"] = None
        signals["rankingIneligibleReason"] = "incomplete_popularity_signals"
    else:
        signals["comparisonCandidateCount"] = 1
        signals["rankingIneligibleReason"] = "insufficient_comparable_candidates"
    receipt["receiptDigest"] = canonical_digest(receipt, excluded="receiptDigest")
    _bind_video_review(tmp_path, receipt)

    admission = build_release_asset_admission(
        release_id="daily-research-release",
        objects_root=tmp_path,
        desired=desired,
        policy=_research_policy(),
    )

    assert next(
        row for row in admission["carrierCounts"] if row["carrier"] == "video"
    )["researchAcceptedCount"] == 1


def test_required_carrier_media_cannot_be_inferred_from_rights_only(
    tmp_path: Path,
) -> None:
    desired = _release_objects(tmp_path)
    _write(tmp_path / "posts/image/manifest.json", {"contentType": "image", "assets": []})

    with pytest.raises(ObjectTransactionError, match="manifest/rights asset closure drift"):
        build_release_asset_admission(
            release_id="research-release",
            objects_root=tmp_path,
            desired=desired,
            policy=_research_policy(),
        )


def test_required_carrier_media_rejects_empty_manifest_and_rights(
    tmp_path: Path,
) -> None:
    desired = _release_objects(tmp_path)
    _write(tmp_path / "posts/image/manifest.json", {"contentType": "image", "assets": []})
    _write(tmp_path / "posts/image/rights.json", {"assets": []})

    with pytest.raises(ObjectTransactionError, match="image required media closure"):
        build_release_asset_admission(
            release_id="research-release",
            objects_root=tmp_path,
            desired=desired,
            policy=_research_policy(),
        )
