from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import content.release.canonical.research_scale_promotion as promotion_module
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
from core.release_layout import payload_digest


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


def _research_release(output_root: Path, *, article_count: int = 100) -> Path:
    release = output_root / "data/releases/research-release"
    carrier_counts = [
        {
            "carrier": carrier,
            "researchAcceptedCount": (
                article_count if carrier == "article" else (10 if carrier == "video" else 100)
            ),
        }
        for carrier in ("homepage", "article", "image", "video")
    ]
    _write(
        release / "payload/release.json",
        {
            "releaseId": "research-release",
            "releaseClass": "research",
            "productLifecycleState": "research",
            "sourceDigests": [
                {"algorithm": "sha256", "digest": "sha256:" + "a" * 64}
            ],
        },
    )
    _write(
        release / "payload/asset_admission.json",
        {
            "releaseClass": "research",
            "productLifecycleState": "research",
            "authorizationRequiredAssetIds": ["old-unverified"],
            "carrierCounts": carrier_counts,
            "articleMediaCoverage": {"illustratedRate": 0.9},
            "assets": [
                {
                    "assetId": "old-unverified",
                    "objectRef": "posts/image/example",
                    "distributionDecision": "research_allowed",
                }
            ],
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
            "sourceDigests": [
                {"algorithm": "sha256", "digest": "sha256:" + "c" * 64}
            ],
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


def test_research_m100_promotion_keeps_targets_and_rates_statistical(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    release = _research_release(output_root, article_count=1)
    admission_path = release / "payload/asset_admission.json"
    admission = json.loads(admission_path.read_text(encoding="utf-8"))
    admission["carrierCounts"] = [
        {"carrier": carrier, "researchAcceptedCount": 1}
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
        "sourceRevision": "sha256:" + "b" * 64,
        "sourceDigest": "sha256:" + "a" * 64,
        "entityCatalogDigest": "sha256:" + "d" * 64,
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
        "_assert_m100_video_popularity",
        lambda *_args, **_kwargs: None,
    )

    promotion, _path = write_research_scale_promotion(
        release_id="research-release",
        promotion_id="promotion-statistics",
        campaign_evidence_path=evidence_path,
        release_root=output_root / "data/releases",
        output_root=output_root,
    )

    assert promotion["m1000Eligible"] is True
    assert promotion["carrierCounts"] == [
        {
            "carrier": carrier,
            "targetCount": target_counts[carrier],
            "qualifiedCount": 1,
            "finalizedCount": 1,
            "selectedCount": 2,
            "discardedCount": 1,
            "shortfallCount": target_counts[carrier] - 1,
            "researchAcceptedCount": 1,
        }
        for carrier in ("homepage", "article", "image", "video")
    ]

    homepage_receipt = (
        output_root / "data/campaigns/campaign-1/receipts/homepage-publish.json"
    )
    homepage_receipt.write_text(
        homepage_receipt.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ResearchScalePromotionError, match="publish receipt digest drift"):
        write_research_scale_promotion(
            release_id="research-release",
            promotion_id="promotion-tampered-receipt",
            campaign_evidence_path=evidence_path,
            release_root=output_root / "data/releases",
            output_root=output_root,
        )
    statistics = promotion["statistics"]
    assert statistics["objectPassRate"] == {
        "numerator": 4,
        "denominator": 8,
        "rate": 0.5,
    }
    assert statistics["illustratedRate"] == {
        "numerator": 0,
        "denominator": 1,
        "rate": 0.0,
    }
    assert statistics["automaticRecoveryRate"] == {
        "numerator": 1,
        "denominator": 4,
        "rate": 0.25,
    }
    assert statistics["firstPassRate"] == {
        "numerator": 3,
        "denominator": 4,
        "rate": 0.75,
    }
    assert statistics["discardRate"] == {
        "numerator": 4,
        "denominator": 8,
        "rate": 0.5,
    }
    assert statistics["quotaAttainmentByCarrier"] == [
        {
            "carrier": carrier,
            "numerator": 1,
            "denominator": target_counts[carrier],
            "rate": 0.1 if carrier == "video" else 0.01,
        }
        for carrier in ("homepage", "article", "image", "video")
    ]


def test_research_m100_promotion_rejects_handwritten_boolean_evidence(
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
            "sourceRevision": "sha256:" + "b" * 64,
            "sourceDigest": "sha256:" + "a" * 64,
            "entityCatalogDigest": "sha256:" + "d" * 64,
            "duplicateAssetCount": 0,
            "crossLaneWriteCount": 0,
            "resourceIsolationPassed": True,
            "automaticRecoveryRate": 0.97,
        },
    )

    with pytest.raises(ResearchScalePromotionError, match="schema violation"):
        write_research_scale_promotion(
            release_id="research-release",
            promotion_id="promotion-1",
            campaign_evidence_path=evidence,
            release_root=output_root / "data/releases",
            output_root=output_root,
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
            "sourceRevision": "sha256:" + "b" * 64,
            "sourceDigest": "sha256:" + "a" * 64,
            "entityCatalogDigest": "sha256:" + "d" * 64,
            "duplicateAssetCount": 0,
            "crossLaneWriteCount": 0,
            "resourceIsolationPassed": True,
            "automaticRecoveryRate": 0.97,
        },
    )

    with pytest.raises(ResearchScalePromotionError, match="schema violation"):
        write_research_scale_promotion(
            release_id="research-release",
            promotion_id="promotion-1",
            campaign_evidence_path=evidence,
            release_root=output_root / "data/releases",
            output_root=output_root,
        )


def _cleanup_evidence(
    output_root: Path,
    *,
    research_release: Path,
    commercial_release: Path,
) -> Path:
    research_digest = payload_digest(research_release)
    commercial_digest = payload_digest(commercial_release)
    environment_receipts: list[tuple[Path, Path]] = []
    for environment in ("alpha", "beta", "gamma", "prod"):
        _cleanup_document, cleanup_path = (
            write_commercial_transition_cleanup_receipt(
                environment=environment,
                run_id="cleanup-1",
                research_release_id="research-release",
                research_manifest_digest=research_digest,
                commercial_release_id="commercial-release",
                commercial_manifest_digest=commercial_digest,
                cache_purged=True,
                media_copies_purged=True,
                signed_urls_revoked=True,
                output_root=output_root,
            )
        )
        _readback_document, readback_path = (
            write_commercial_transition_readback_receipt(
                environment=environment,
                run_id="readback-1",
                research_release_id="research-release",
                research_manifest_digest=research_digest,
                commercial_release_id="commercial-release",
                commercial_manifest_digest=commercial_digest,
                unauthorized_readback_count=0,
                unauthorized_asset_ids=[],
                output_root=output_root,
            )
        )
        environment_receipts.append((cleanup_path, readback_path))
    _document, path = write_commercial_transition_evidence(
        evidence_id="evidence-1",
        research_release_id="research-release",
        research_manifest_digest=research_digest,
        commercial_release_id="commercial-release",
        commercial_manifest_digest=commercial_digest,
        environment_receipts=environment_receipts,
        output_root=output_root,
    )
    return path


def test_commercial_transition_records_replacement_and_four_environment_cleanup(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    research_release = _research_release(output_root)
    commercial_release = _commercial_release(output_root)
    cleanup = _cleanup_evidence(
        output_root,
        research_release=research_release,
        commercial_release=commercial_release,
    )

    document, path = write_commercial_transition(
        research_release_id="research-release",
        commercial_release_id="commercial-release",
        transition_run_id="transition-1",
        cleanup_evidence_path=cleanup,
        release_root=output_root / "data/releases",
        output_root=output_root,
    )

    assert document["objectMigrations"] == [
        {
            "researchAssetId": "old-unverified",
            "objectRef": "posts/image/example",
            "action": "replaced",
            "commercialAssetIds": ["new-verified"],
        }
    ]
    assert document["unauthorizedReadbackCount"] == 0
    assert document["cleanupEvidenceDigest"].startswith("sha256:")
    assert document["receiptDigest"].startswith("sha256:")
    assert path.is_file()


def test_commercial_transition_blocks_nonzero_unauthorized_readback(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    research_release = _research_release(output_root)
    commercial_release = _commercial_release(output_root)
    cleanup = _cleanup_evidence(
        output_root,
        research_release=research_release,
        commercial_release=commercial_release,
    )
    evidence = json.loads(cleanup.read_text(encoding="utf-8"))
    beta = next(
        row for row in evidence["environments"] if row["environment"] == "beta"
    )
    readback = output_root / beta["readbackReceiptRef"]
    tampered = json.loads(readback.read_text(encoding="utf-8"))
    tampered["unauthorizedReadbackCount"] = 1
    tampered["unauthorizedAssetIds"] = ["old-unverified"]
    _write(readback, tampered)

    with pytest.raises(CommercialTransitionError, match="schema violation"):
        write_commercial_transition(
            research_release_id="research-release",
            commercial_release_id="commercial-release",
            transition_run_id="transition-1",
            cleanup_evidence_path=cleanup,
            release_root=output_root / "data/releases",
            output_root=output_root,
        )


def test_commercial_transition_rejects_handwritten_boolean_evidence(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    research_release = _research_release(output_root)
    commercial_release = _commercial_release(output_root)
    path = (
        output_root
        / "data/commercial-transition-evidence/commercial-release/handwritten/evidence.json"
    )
    _write(
        path,
        {
            "researchReleaseId": "research-release",
            "researchManifestDigest": payload_digest(research_release),
            "commercialReleaseId": "commercial-release",
            "commercialManifestDigest": payload_digest(commercial_release),
            "environments": [
                {"environment": environment, "cachePurged": True}
                for environment in ("alpha", "beta", "gamma", "prod")
            ],
        },
    )

    with pytest.raises(CommercialTransitionError, match="schema violation"):
        write_commercial_transition(
            research_release_id="research-release",
            commercial_release_id="commercial-release",
            transition_run_id="transition-1",
            cleanup_evidence_path=path,
            release_root=output_root / "data/releases",
            output_root=output_root,
        )


def test_commercial_transition_cleanup_receipt_is_create_once(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    common = {
        "environment": "alpha",
        "run_id": "cleanup-1",
        "research_release_id": "research-release",
        "research_manifest_digest": "sha256:" + "a" * 64,
        "commercial_release_id": "commercial-release",
        "commercial_manifest_digest": "sha256:" + "c" * 64,
        "cache_purged": True,
        "media_copies_purged": True,
        "signed_urls_revoked": True,
        "output_root": output_root,
    }
    first, _path = write_commercial_transition_cleanup_receipt(**common)
    second, _path = write_commercial_transition_cleanup_receipt(**common)
    assert second == first

    with pytest.raises(
        CommercialTransitionEvidenceError,
        match="create-once.*identity conflict",
    ):
        write_commercial_transition_cleanup_receipt(
            **{**common, "research_manifest_digest": "sha256:" + "b" * 64}
        )
