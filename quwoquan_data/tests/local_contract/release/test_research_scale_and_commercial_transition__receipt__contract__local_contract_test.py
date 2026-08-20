# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001.t3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import content.release.canonical.research_scale_promotion as promotion_module
import pytest
from content.release.canonical.commercial_transition import (
    CommercialTransitionError,
    write_commercial_transition,
)
from content.release.canonical.commercial_transition_evidence import (
    CommercialTransitionEvidenceError,
    write_commercial_transition_cleanup_receipt,
    write_commercial_transition_evidence,
    write_commercial_transition_readback_receipt,
)
from content.release.canonical.research_scale_promotion import (
    ResearchScalePromotionError,
    write_research_scale_promotion,
)
from content.release.canonical.object_source_identity import (
    source_identity_digest,
    source_identity_set,
)
from core.release_layout import payload_digest
from core.source_digest import SourceDefinitionSnapshot, content_source_revision


_SOURCE_DIGEST = "sha256:" + "a" * 64
_ENTITY_CATALOG_DIGEST = "sha256:" + "d" * 64
_SOURCE_REVISION = content_source_revision(
    source_digest=_SOURCE_DIGEST,
    entity_catalog_digest=_ENTITY_CATALOG_DIGEST,
)


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _semantic_jobs(carrier: str) -> dict[str, object]:
    job_ids = [f"{carrier}-job-{index:02d}" for index in range(10)]
    return {
        "carrier": carrier,
        "executionId": f"{carrier}-execution",
        "semanticJobCount": 10,
        "semanticJobSucceededCount": 10,
        "semanticJobTerminalCount": 10,
        "semanticJobIds": job_ids,
        "semanticJobSucceededIds": job_ids,
        "semanticJobTerminalIds": job_ids,
        "perSlotThroughputSamples": [0.01] * 10,
        "activeDurationSeconds": 3600,
        "activeIntervals": [
            {
                "startedAt": "2026-08-05T00:00:00Z",
                "endedAt": "2026-08-05T01:00:00Z",
                "durationSeconds": 3600,
            }
        ],
    }


def _semantic_calibration(carrier: str) -> dict[str, object]:
    return {
        "carrier": carrier,
        "provider": "codex_sdk",
        "authorModel": "gpt-5.6-terra",
        "authorModelFamily": "gpt",
        "reviewerModel": "gpt-5.6-terra",
        "reviewerModelFamily": "gpt",
        "calibrationProvider": "codex_sdk",
        "calibrationModel": "gpt-5.6-sol",
        "calibrationModelFamily": "gpt",
        "executionManifestRef": f"data/tasks/{carrier}-execution/execution_manifest.json",
        "executionManifestSha256": "sha256:" + "1" * 64,
        "authorRun": {
            "objectRef": f"{carrier}-object",
            "runId": f"{carrier}-author-run",
            "evidenceRef": f"data/tasks/{carrier}-execution/author.json",
            "evidenceSha256": "sha256:" + "2" * 64,
        },
        "reviewerRun": {
            "objectRef": f"{carrier}-object",
            "runId": f"{carrier}-reviewer-run",
            "evidenceRef": f"data/tasks/{carrier}-execution/reviewer.json",
            "evidenceSha256": "sha256:" + "3" * 64,
        },
        "selectionPolicy": {
            "sampleRate": 0.1,
            "minimumSampleCount": 10,
            "smallBatchPolicy": "all",
            "acceptedObjectCount": 1,
            "requiredSampleCount": 1,
            "selectedObjectRefs": [f"{carrier}-object"],
            "selectionDigest": "sha256:" + "4" * 64,
        },
        "calibrationRuns": [
            {
                "objectRef": f"{carrier}-object",
                "runId": f"{carrier}-calibration-run",
                "evidenceRef": f"data/tasks/{carrier}-execution/calibration.json",
                "evidenceSha256": "sha256:" + "5" * 64,
            }
        ],
    }


def _video_popularity_statistics() -> dict[str, object]:
    return {
        "signalAvailability": [
            {"signal": signal, "numerator": 1, "denominator": 1, "rate": 1.0}
            for signal in ("play", "like", "comment", "share", "favorite")
        ],
        "rankingCoverage": {"numerator": 1, "denominator": 1, "rate": 1.0},
        "observations": [
            {
                "objectRef": "posts/video/example",
                "assetId": "video-asset-1",
                "playCount": 100,
                "likeCount": 10,
                "commentCount": 2,
                "shareCount": 1,
                "favoriteCount": 3,
                "observedAt": "2026-08-05T00:00:00Z",
                "comparisonBucket": {
                    "provider": "fixture",
                    "topic": "travel",
                    "timeBucket": "2026-W32",
                    "candidateCount": 2,
                },
                "popularityScore": 451,
                "popularityPercentile": 1.0,
                "rankingEligible": True,
                "ineligibleReason": "",
            }
        ],
    }


def _professional_image_assets(count: int = 100) -> list[dict[str, object]]:
    providers = ["Pinterest"] * 60 + ["图虫"] * 20 + ["Wikimedia Commons"] * 20
    assert count == len(providers)
    return [
        {
            "assetId": (
                "old-unverified" if index == 1 else f"image-asset-{index:03d}"
            ),
            "objectRef": f"posts/image/work-{index - 1:03d}/1",
            "acquisitionStatus": "acquired",
            "rightsStatus": "unverified",
            "authorizationRequired": True,
            "distributionDecision": "research_allowed",
            "sourceUrl": f"https://media.example.test/original/{index:03d}.jpg",
            "platform": provider,
            "creator": f"creator-{index:03d}",
            "capturedAt": "2026-08-05T00:00:00Z",
            "contentSha256": "sha256:" + f"{index:064x}",
            "license": "authorization_pending",
            "termsUrl": "https://media.example.test/terms",
            "authorizationProof": "",
            "rightsIssues": ["creator_authorization_pending"],
            "generated": False,
        }
        for index, provider in enumerate(providers, start=1)
    ]


def _research_release(output_root: Path, *, article_count: int = 100) -> Path:
    release = output_root / "data/releases/research-release"
    execution_ids = [
        f"{carrier}-execution"
        for carrier in ("homepage", "article", "image", "video")
    ]
    expanded_identities = [
        {
            "executionId": execution_id,
            "sourceRevision": _SOURCE_REVISION,
            "sourceDigest": _SOURCE_DIGEST,
            "entityCatalogDigest": _ENTITY_CATALOG_DIGEST,
        }
        for execution_id in execution_ids
    ]
    source_identities, source_identity_set_digest = source_identity_set(
        expanded_identities
    )
    identity_digest = source_identity_digest(expanded_identities[0])
    contents = [
        {
            "contentId": f"content-{carrier}-{index:03d}",
            "version": 1,
            "postRef": f"{carrier}/work-{index:03d}/1",
            "executionId": f"{carrier}-execution",
            "sourceIdentityDigest": identity_digest,
        }
        for carrier, count in (("article", 100), ("image", 100), ("video", 10))
        for index in range(count)
    ]
    carrier_counts = [
        {
            "carrier": carrier,
            "researchAcceptedCount": (
                article_count
                if carrier == "article"
                else (10 if carrier == "video" else 100)
            ),
            "objectCount": (
                article_count
                if carrier == "article"
                else (10 if carrier == "video" else 100)
            ),
            "assetCount": 100 if carrier == "image" else 0,
            "commercialAcceptedCount": 0,
        }
        for carrier in ("homepage", "article", "image", "video")
    ]
    _write(
        release / "payload/release.json",
        {
            "schema": "quwoquan_data.release",
            "releaseId": "research-release",
            "sourceOwner": "qwq_data",
            "releaseKind": "content",
            "releaseClass": "research",
            "productLifecycleState": "research",
            "containsUnverifiedAssets": True,
            "rightsStatusCounts": {
                "verified": 0,
                "unverified": 100,
                "restricted": 0,
                "unknown": 0,
            },
            "authorizationRequiredAssetIds": ["old-unverified"],
            "researchAcceptedCount": 310,
            "commercialAcceptedCount": 0,
            "canonicalMerkle": "sha256:" + "2" * 64,
            "executionIds": execution_ids,
            "sourceDigests": [
                SourceDefinitionSnapshot(_SOURCE_DIGEST).to_document()
            ],
            "milestone": "M100",
            "selectionScope": "milestone",
            "milestoneTargets": {
                "homepage": 100,
                "article": 100,
                "image": 100,
                "video": 10,
            },
            "releaseMode": "research",
            "poolDigest": "sha256:" + "3" * 64,
            "counts": {"article": 100, "image": 100, "video": 10, "total": 210},
            "contents": contents,
            "authors": [],
            "buildResult": "completed",
            "sourceIdentities": source_identities,
            "sourceIdentitySetDigest": source_identity_set_digest,
        },
    )
    _write(
        release / "payload/desired_state.json",
        {
            "schema": "quwoquan_data.release_desired_state",
            "releaseId": "research-release",
            "desiredRefs": {
                "entities": [f"entity/work-{index:03d}" for index in range(100)],
                "posts": [str(item["postRef"]) for item in contents],
                "creators": [],
                "tags": [],
            },
        },
    )
    _write(
        release / "payload/asset_admission.json",
        {
            "schema": "quwoquan_data.release_asset_admission",
            "releaseId": "research-release",
            "releaseClass": "research",
            "productLifecycleState": "research",
            "containsUnverifiedAssets": True,
            "rightsStatusCounts": {
                "verified": 0,
                "unverified": 100,
                "restricted": 0,
                "unknown": 0,
            },
            "authorizationRequiredAssetIds": ["old-unverified"],
            "researchAcceptedCount": 310,
            "commercialAcceptedCount": 0,
            "carrierCounts": carrier_counts,
            "articleMediaCoverage": {
                "articleCount": article_count,
                "illustratedCount": int(article_count * 0.9),
                "textOnlyCount": article_count - int(article_count * 0.9),
                "illustratedRate": 0.9,
                "textOnlyRate": 0.1,
            },
            "sourceAssetCounts": [],
            "assets": _professional_image_assets(),
        },
    )
    return release


def _commercial_release(output_root: Path) -> Path:
    release = output_root / "data/releases/commercial-release"
    _write(
        release / "payload/release.json",
        {
            "releaseId": "commercial-release",
            "releaseClass": "commercial",
            "productLifecycleState": "commercial",
            "poolDigest": "sha256:" + "9" * 64,
            # A commercial release is a rights-filtered view over the same
            # frozen pool, so a scalar sourceDigest may remain unchanged.
            "sourceDigest": "sha256:" + "a" * 64,
            "sourceDigests": [
                SourceDefinitionSnapshot("sha256:" + "a" * 64).to_document()
            ],
            "contents": [
                {
                    "contentId": "content-image-example",
                    "version": 2,
                    "postRef": "image/example",
                    "executionId": "commercial-image-execution",
                    "sourceIdentityDigest": "sha256:" + "2" * 64,
                }
            ],
        },
    )
    _write(
        release / "payload/desired_state.json",
        {
            "desiredRefs": {
                "creators": [],
                "entities": [],
                "posts": ["image/example"],
                "tags": [],
            }
        },
    )
    _write(
        release / "payload/asset_admission.json",
        {
            "releaseClass": "commercial",
            "productLifecycleState": "commercial",
            "containsUnverifiedAssets": False,
            "authorizationRequiredAssetIds": [],
            "assets": [
                {
                    "assetId": "new-verified",
                    "objectRef": "posts/image/example",
                    "distributionDecision": "commercial_allowed",
                }
            ],
        },
    )
    return release


def _transition_research_release(output_root: Path) -> Path:
    release = _research_release(output_root)
    header_path = release / "payload/release.json"
    header = json.loads(header_path.read_text(encoding="utf-8"))
    header.pop("sourceIdentities")
    header.pop("sourceIdentitySetDigest")
    header.update(
        {
            "poolDigest": "sha256:" + "9" * 64,
            "sourceDigest": "sha256:" + "a" * 64,
            "contents": [
                {
                    "contentId": "content-image-example",
                    "version": 1,
                    "postRef": "image/example",
                    "executionId": "research-image-execution",
                    "sourceIdentityDigest": "sha256:" + "1" * 64,
                }
            ],
        }
    )
    _write(header_path, header)
    _write(
        release / "payload/desired_state.json",
        {
            "desiredRefs": {
                "creators": [],
                "entities": [],
                "posts": ["image/example"],
                "tags": [],
            }
        },
    )
    admission_path = release / "payload/asset_admission.json"
    admission = json.loads(admission_path.read_text(encoding="utf-8"))
    admission["assets"][0]["objectRef"] = "posts/image/example"
    _write(admission_path, admission)
    return release


def test_research_m100_promotion_blocks_shortfall_and_weak_rates(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    release = _research_release(output_root, article_count=1)
    admission_path = release / "payload/asset_admission.json"
    admission = json.loads(admission_path.read_text(encoding="utf-8"))
    admission["carrierCounts"] = [
        {
            "carrier": carrier,
            "researchAcceptedCount": 1,
            "objectCount": 1,
            "assetCount": 0,
            "commercialAcceptedCount": 0,
        }
        for carrier in ("homepage", "article", "image", "video")
    ]
    admission["articleMediaCoverage"] = {
        "articleCount": 1,
        "illustratedCount": 0,
        "textOnlyCount": 1,
        "illustratedRate": 0.0,
        "textOnlyRate": 1.0,
    }
    _write(admission_path, admission)

    target_counts = {"homepage": 100, "article": 100, "image": 100, "video": 10}
    lanes = []
    for carrier in ("homepage", "article", "image", "video"):
        receipt_path = (
            output_root / f"data/campaigns/campaign-1/receipts/{carrier}-publish.json"
        )
        _write(
            receipt_path,
            {
                "schema": "quwoquan_data.content_campaign_lane_receipt",
                "rootExecutionId": "homepage-execution",
                "executionId": f"{carrier}-execution",
                "carrier": carrier,
                "phase": "publish",
                "status": "partial",
                "approvedQuota": target_counts[carrier],
                "qualifiedCount": 1,
                "reviewQualifiedCount": 1,
                "finalizedCount": 1,
                "selectedCount": 2,
                "discardedCount": 1,
                "shortfallCount": target_counts[carrier] - 1,
                "executionPublishRef": (
                    f"data/tasks/{carrier}-execution/publish_ref.json"
                ),
                "executionPublishSha256": "sha256:" + "6" * 64,
                "campaignRunId": "campaign-run",
                "campaignGeneration": 1,
                "campaignFencingToken": "sha256:" + "7" * 64,
                "discards": [
                    {
                        "objectRef": f"{carrier}-discarded-object",
                        "issues": ["hard object review rejected"],
                    }
                ],
                "publishDiscards": [],
            },
        )
        lanes.append(
            {
                "carrier": carrier,
                "executionId": f"{carrier}-execution",
                "retryChain": (
                    [f"{carrier}-execution", "image-execution-previous"]
                    if carrier == "image"
                    else [f"{carrier}-execution"]
                ),
                "publishReceiptRef": receipt_path.relative_to(output_root).as_posix(),
                "publishReceiptSha256": (
                    "sha256:" + hashlib.sha256(receipt_path.read_bytes()).hexdigest()
                ),
                "finalizedCount": 1,
                "researchAcceptedCount": 1,
                "semanticCalibration": _semantic_calibration(carrier),
            }
        )

    evidence_path = output_root / "data/campaigns/campaign-1/campaign-scale.json"
    _write(evidence_path, {"canonical": True})
    evidence = {
        "status": "failed",
        "releaseId": "research-release",
        "manifestDigest": payload_digest(release),
        "sourceRevision": _SOURCE_REVISION,
        "sourceDigest": _SOURCE_DIGEST,
        "entityCatalogDigest": _ENTITY_CATALOG_DIGEST,
        "targetScale": "M100",
        "sourcePoolDigest": "sha256:" + "1" * 64,
        "predecessorSourcePoolDigests": [],
        "scaleStartedAt": "2026-08-05T00:00:00Z",
        "scaleCompletedAt": "2026-08-05T01:01:00Z",
        "wallClockBudgetSeconds": None,
        "wallClockSeconds": 3660,
        "lanes": lanes,
        "duplicateAssetCount": 0,
        "crossLaneWriteCount": 0,
        "articleIllustratedRate": 0.0,
        "evidenceDigest": "sha256:" + "8" * 64,
        "resourceSoakEvidenceRef": "data/campaigns/campaign-1/resource-soak.json",
        "resourceSoakEvidenceDigest": "sha256:" + "9" * 64,
        "faultInjectionEvidenceRef": "data/campaigns/campaign-1/fault-injection.json",
        "faultInjectionEvidenceDigest": "sha256:" + "0" * 64,
    }
    resource_evidence = {
        "evidenceDigest": "sha256:" + "9" * 64,
        "status": "passed",
        "durationSeconds": 3600,
        "semanticJobsByLane": [
            _semantic_jobs(carrier)
            for carrier in ("homepage", "article", "image", "video")
        ],
        "fourLaneOverlapSampleCount": 60,
        "fourLaneOverlapDurationSeconds": 3600,
        "fourLaneLongestContinuousOverlapSeconds": 3600,
        "allSemanticJobsTerminalAt": "2026-08-05T01:00:00Z",
        "terminalResidualSampleAt": "2026-08-05T01:01:00Z",
        "terminalResidualMeasuredAfterAllJobs": True,
    }
    fault_evidence = {
        "status": "failed",
        "automaticRecoveryStatus": "MEASURED",
        "recoveryEligibleCount": 4,
        "automaticRecoveredCount": 1,
        "automaticRecoveryRate": 0.25,
    }
    monkeypatch.setattr(
        promotion_module,
        "load_campaign_scale_evidence",
        lambda *_args, **_kwargs: (
            evidence,
            resource_evidence,
            fault_evidence,
        ),
    )
    monkeypatch.setattr(
        promotion_module,
        "_collect_m100_video_popularity",
        lambda *_args, **_kwargs: _video_popularity_statistics(),
    )

    with pytest.raises(ResearchScalePromotionError, match="ATTAINMENT_SHORTFALL"):
        write_research_scale_promotion(
            release_id="research-release",
            promotion_id="promotion-shortfall",
            campaign_evidence_path=evidence_path,
            release_root=output_root / "data/releases",
            output_root=output_root,
        )


def test_research_m100_promotion_requires_actual_cumulative_attainment(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    release = _research_release(output_root)
    targets = {"homepage": 100, "article": 100, "image": 100, "video": 10}
    lanes = []
    for carrier, target in targets.items():
        receipt_path = (
            output_root / f"data/campaigns/campaign-1/receipts/{carrier}-publish.json"
        )
        _write(
            receipt_path,
            {
                "schema": "quwoquan_data.content_campaign_lane_receipt",
                "rootExecutionId": "homepage-execution",
                "executionId": f"{carrier}-execution",
                "carrier": carrier,
                "phase": "publish",
                "status": "finalized",
                "approvedQuota": target,
                "qualifiedCount": target,
                "reviewQualifiedCount": target,
                "finalizedCount": target,
                "selectedCount": target,
                "discardedCount": 0,
                "shortfallCount": 0,
                "executionPublishRef": f"data/tasks/{carrier}-execution/publish_ref.json",
                "executionPublishSha256": "sha256:" + "6" * 64,
                "campaignRunId": "campaign-run",
                "campaignGeneration": 1,
                "campaignFencingToken": "sha256:" + "7" * 64,
                "discards": [],
                "publishDiscards": [],
            },
        )
        lanes.append(
            {
                "carrier": carrier,
                "executionId": f"{carrier}-execution",
                "retryChain": [f"{carrier}-execution"],
                "publishReceiptRef": receipt_path.relative_to(output_root).as_posix(),
                "publishReceiptSha256": "sha256:"
                + hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
                "finalizedCount": target,
                "researchAcceptedCount": target,
                "semanticCalibration": _semantic_calibration(carrier),
            }
        )
    evidence_path = output_root / "data/campaigns/campaign-1/campaign-scale.json"
    _write(evidence_path, {"canonical": True})
    evidence = {
        "status": "passed",
        "releaseId": "research-release",
        "manifestDigest": payload_digest(release),
        "sourceRevision": _SOURCE_REVISION,
        "sourceDigest": _SOURCE_DIGEST,
        "entityCatalogDigest": _ENTITY_CATALOG_DIGEST,
        "targetScale": "M100",
        "sourcePoolDigest": "sha256:" + "1" * 64,
        "predecessorSourcePoolDigests": [],
        "scaleStartedAt": "2026-08-05T00:00:00Z",
        "scaleCompletedAt": "2026-08-05T01:01:00Z",
        "wallClockBudgetSeconds": None,
        "wallClockSeconds": 3660,
        "lanes": lanes,
        "duplicateAssetCount": 0,
        "crossLaneWriteCount": 0,
        "articleIllustratedRate": 0.9,
        "evidenceDigest": "sha256:" + "8" * 64,
        "resourceSoakEvidenceRef": "data/campaigns/campaign-1/resource-soak.json",
        "resourceSoakEvidenceDigest": "sha256:" + "9" * 64,
        "faultInjectionEvidenceRef": "data/campaigns/campaign-1/fault-injection.json",
        "faultInjectionEvidenceDigest": "sha256:" + "0" * 64,
    }
    resource_evidence = {
        "evidenceDigest": "sha256:" + "9" * 64,
        "status": "passed",
        "durationSeconds": 3600,
        "semanticJobsByLane": [_semantic_jobs(carrier) for carrier in targets],
        "fourLaneOverlapSampleCount": 60,
        "fourLaneOverlapDurationSeconds": 3600,
        "fourLaneLongestContinuousOverlapSeconds": 3600,
        "allSemanticJobsTerminalAt": "2026-08-05T01:00:00Z",
        "terminalResidualSampleAt": "2026-08-05T01:01:00Z",
        "terminalResidualMeasuredAfterAllJobs": True,
    }
    fault_evidence = {
        "status": "passed",
        "automaticRecoveryStatus": "MEASURED",
        "recoveryEligibleCount": 20,
        "automaticRecoveredCount": 19,
        "automaticRecoveryRate": 0.95,
    }
    monkeypatch.setattr(
        promotion_module,
        "load_campaign_scale_evidence",
        lambda *_args, **_kwargs: (evidence, resource_evidence, fault_evidence),
    )
    monkeypatch.setattr(
        promotion_module,
        "_collect_m100_video_popularity",
        lambda *_args, **_kwargs: _video_popularity_statistics(),
    )

    promotion, _path = write_research_scale_promotion(
        release_id="research-release",
        promotion_id="promotion-m100-attained",
        campaign_evidence_path=evidence_path,
        release_root=output_root / "data/releases",
        output_root=output_root,
    )

    assert promotion["nextScaleEligible"] == "M1000"
    assert all(row["shortfallCount"] == 0 for row in promotion["carrierCounts"])
    assert promotion["carrierCounts"][0]["totalUniqueFinalizedCount"] == 100


def test_research_m100_promotion_ignores_handwritten_campaign_diagnostic(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    release = _research_release(output_root)
    evidence = output_root / "data/campaigns/campaign-1/m100.json"
    _write(
        evidence,
        {
            "releaseId": "research-release",
            "manifestDigest": payload_digest(release),
            "sourceRevision": _SOURCE_REVISION,
            "sourceDigest": _SOURCE_DIGEST,
            "entityCatalogDigest": _ENTITY_CATALOG_DIGEST,
            "duplicateAssetCount": 0,
            "crossLaneWriteCount": 0,
            "resourceIsolationPassed": True,
            "automaticRecoveryRate": 0.97,
        },
    )

    promotion, _path = write_research_scale_promotion(
        release_id="research-release",
        promotion_id="promotion-1",
        campaign_evidence_path=evidence,
        release_root=output_root / "data/releases",
        output_root=output_root,
    )

    assert "campaignEvidenceRef" not in promotion
    assert any(
        "CAMPAIGN_EVIDENCE_UNAVAILABLE" in issue
        for issue in promotion["diagnosticIssues"]
    )


def test_research_m100_promotion_does_not_trust_booleans_despite_release_shortfall(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    release = _research_release(output_root, article_count=99)
    evidence = output_root / "data/campaigns/campaign-1/m100.json"
    _write(
        evidence,
        {
            "releaseId": "research-release",
            "manifestDigest": payload_digest(release),
            "sourceRevision": _SOURCE_REVISION,
            "sourceDigest": _SOURCE_DIGEST,
            "entityCatalogDigest": _ENTITY_CATALOG_DIGEST,
            "duplicateAssetCount": 0,
            "crossLaneWriteCount": 0,
            "resourceIsolationPassed": True,
            "automaticRecoveryRate": 0.97,
        },
    )

    with pytest.raises(ResearchScalePromotionError, match="ATTAINMENT_SHORTFALL"):
        write_research_scale_promotion(
            release_id="research-release",
            promotion_id="promotion-1",
            campaign_evidence_path=evidence,
            release_root=output_root / "data/releases",
            output_root=output_root,
        )

