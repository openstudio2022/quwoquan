"""Generic campaign request envelopes freeze once and validate schema."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import content.execution.campaign.request_envelope as envelopes
import pytest
from content.execution.campaign.scale import CampaignScaleError, resolve_campaign_scale
from content.execution.scale import promotion as scale_promotion
from core.io import read_json, write_json
from core.runtime_policy import active_runtime_policy
from content.execution.campaign import request_envelope_build
from support.campaign_request_envelope_fixture import (
    _expected_count,
    _patch_envelope_deps,
    _wave_targets,
)
from support.semantic_preflight_fixture import ready_semantic_preflight



def test_campaign_source_freeze_allows_dirty_tree_when_content_digest_is_stable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen = {
        "algorithm": "sha256",
        "digest": "sha256:" + "a" * 64,
        "inputs": ["quwoquan_data/scripts"],
    }
    bundle = {**frozen, "digest": "sha256:" + "c" * 64}
    monkeypatch.setattr(
        envelopes,
        "current_source_definition_snapshot",
        lambda **_kwargs: SimpleNamespace(to_document=lambda: dict(frozen)),
    )
    monkeypatch.setattr(
        envelopes,
        "current_execution_bundle_identity",
        lambda **_kwargs: SimpleNamespace(to_document=lambda: dict(bundle)),
    )
    monkeypatch.setattr(
        envelopes.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("Git cleanliness must not be queried"),
    )

    envelopes._require_stable_source_inputs(
        frozen,
        execution_bundle=bundle,
        repo_root=tmp_path,
    )


def test_campaign_source_freeze_blocks_content_digest_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen = {
        "algorithm": "sha256",
        "digest": "sha256:" + "a" * 64,
        "inputs": ["quwoquan_data/scripts"],
    }
    observed = {**frozen, "digest": "sha256:" + "b" * 64}
    bundle = {**frozen, "digest": "sha256:" + "c" * 64}
    monkeypatch.setattr(
        envelopes,
        "current_source_definition_snapshot",
        lambda **_kwargs: SimpleNamespace(to_document=lambda: dict(observed)),
    )
    monkeypatch.setattr(
        envelopes,
        "current_execution_bundle_identity",
        lambda **_kwargs: SimpleNamespace(to_document=lambda: dict(bundle)),
    )

    with pytest.raises(ValueError, match="changed during freeze"):
        envelopes._require_stable_source_inputs(
            frozen,
            execution_bundle=bundle,
            repo_root=tmp_path,
        )


def _approved_video_promotion() -> dict[str, object]:
    stable: dict[str, object] = {
        "schema": "quwoquan_data.video_scale_promotion",
        "status": "approved",
        "predecessorExecutionId": (
            "20260731--travel-video-m100--china--scale-002"
        ),
        "vertical": "travel",
        "carrier": "video",
        "gitBranch": "dev1.0",
        "gitCommitSha": "0123456789abcdef0123456789abcdef01234567",
        "sourceDigest": {
            "algorithm": "sha256",
            "digest": "sha256:" + ("a" * 64),
            "inputs": ["quwoquan_data/scripts"],
        },
        "entityCatalogDigest": "sha256:" + ("b" * 64),
        "targetSetDigest": "c" * 64,
        "predecessorInputMode": "campaign_envelope",
        "predecessorInputDigest": "sha256:" + ("d" * 64),
        "modelBinding": {
            "provider": "codex_sdk",
            "authorModel": "gpt-5.6-terra",
            "authorModelFamily": "gpt",
            "authorModelParameters": [],
            "reviewerModel": "gpt-5.6-terra",
            "reviewerModelFamily": "gpt",
            "reviewerModelParameters": [],
        },
        "modelReadinessDigest": "sha256:" + ("e" * 64),
        "postReviewClosureDigest": "sha256:" + ("f" * 64),
        "publishReceiptDigest": "sha256:" + ("0" * 64),
        "sourceReadyCount": 60,
        "sourceIneligibleCount": 30,
        "candidateCount": 90,
        "approvedQuota": 10,
        "qualifiedCount": 10,
        "finalizedCount": 10,
        "discardedCount": 80,
        "shortfallCount": 0,
    }
    return {
        **stable,
        "receiptDigest": scale_promotion._sha256(stable),
    }


def _approved_image_promotion() -> dict[str, object]:
    stable: dict[str, object] = {
        **_approved_video_promotion(),
        "schema": "quwoquan_data.image_scale_promotion",
        "predecessorExecutionId": (
            "20260731--travel-image-m100--china--scale-002"
        ),
        "carrier": "image",
        "sourceReadyCount": 120,
        "sourceIneligibleCount": 60,
        "candidateCount": 180,
        "approvedQuota": 100,
        "qualifiedCount": 100,
        "finalizedCount": 100,
        "discardedCount": 80,
    }
    stable.pop("receiptDigest")
    return {
        **stable,
        "receiptDigest": scale_promotion._sha256(stable),
    }


def _research_m100_receipt(path: Path, *, source_digest: str | None = None) -> Path:
    semantic_jobs = [
        {
            "carrier": carrier,
            "executionId": f"20260805--travel-{carrier}-m100--china--scale-001",
            "semanticJobCount": 10,
            "semanticJobSucceededCount": 10,
            "semanticJobTerminalCount": 10,
            "semanticJobIds": [
                f"{carrier}-job-{index:02d}" for index in range(10)
            ],
            "semanticJobSucceededIds": [
                f"{carrier}-job-{index:02d}" for index in range(10)
            ],
            "semanticJobTerminalIds": [
                f"{carrier}-job-{index:02d}" for index in range(10)
            ],
            "activeDurationSeconds": 3600,
            "activeIntervals": [
                {
                    "startedAt": "2026-08-05T00:00:00Z",
                    "endedAt": "2026-08-05T01:00:00Z",
                    "durationSeconds": 3600,
                }
            ],
        }
        for carrier in ("homepage", "article", "image", "video")
    ]
    semantic_calibration = [
        {
            "carrier": carrier,
            "provider": "codex_sdk",
            "authorModel": "gpt-5.6-terra",
            "authorModelFamily": "gpt",
            "reviewerModel": "gpt-5.6-terra",
            "reviewerModelFamily": "gpt",
            "calibrationProvider": "codex_sdk",
            "calibrationModel": "gpt-5.6-sol",
            "calibrationModelFamily": "gpt",
            "executionManifestRef": f"data/tasks/{carrier}/execution_manifest.json",
            "executionManifestSha256": "sha256:" + "4" * 64,
            "authorRun": {
                "objectRef": f"{carrier}-primary-object",
                "runId": f"{carrier}-terra-author-run",
                "evidenceRef": f"data/tasks/{carrier}/4.draft/agent_result_envelope.json",
                "evidenceSha256": "sha256:" + "5" * 64,
            },
            "reviewerRun": {
                "objectRef": f"{carrier}-primary-object",
                "runId": f"{carrier}-terra-reviewer-run",
                "evidenceRef": f"data/tasks/{carrier}/5.review/reviewer_result.json",
                "evidenceSha256": "sha256:" + "6" * 64,
            },
            "selectionPolicy": {
                "sampleRate": 0.1,
                "minimumSampleCount": 10,
                "smallBatchPolicy": "all",
                "acceptedObjectCount": 10 if carrier == "video" else 100,
                "requiredSampleCount": 10,
                "selectedObjectRefs": [
                    f"{carrier}-calibration-object-{index:02d}"
                    for index in range(10)
                ],
                "selectionDigest": "sha256:" + "7" * 64,
            },
            "calibrationRuns": [
                {
                    "objectRef": f"{carrier}-calibration-object-{index:02d}",
                    "runId": f"{carrier}-sol-calibration-run-{index:02d}",
                    "evidenceRef": (
                        f"data/tasks/{carrier}/evidence/semantic_calibration/"
                        f"{index:02d}.reviewer_result.json"
                    ),
                    "evidenceSha256": "sha256:" + "8" * 64,
                }
                for index in range(10)
            ],
        }
        for carrier in ("homepage", "article", "image", "video")
    ]
    write_json(
        path,
        {
            "schema": "quwoquan_data.research_scale_promotion",
            "promotionId": "research-m100-1",
            "releaseId": "research-release-1",
            "releaseClass": "research",
            "productLifecycleState": "research",
            "manifestDigest": "sha256:" + ("c" * 64),
            "sourceRevision": envelopes.content_source_revision(
                source_digest=source_digest or ("sha256:" + ("a" * 64)),
                entity_catalog_digest="sha256:" + ("b" * 64),
            ),
            "sourceDigest": source_digest or ("sha256:" + ("a" * 64)),
            "entityCatalogDigest": "sha256:" + ("b" * 64),
            "targetScale": "M100",
            "carrierCounts": [
                {
                    "carrier": carrier,
                    "targetCount": 10 if carrier == "video" else 100,
                    "qualifiedCount": 10 if carrier == "video" else 100,
                    "finalizedCount": 10 if carrier == "video" else 100,
                    "selectedCount": 10 if carrier == "video" else 100,
                    "discardedCount": 0,
                    "shortfallCount": 0,
                    "researchAcceptedCount": 10 if carrier == "video" else 100,
                }
                for carrier in ("homepage", "article", "image", "video")
            ],
            "statistics": {
                "objectPassRate": {
                    "numerator": 310,
                    "denominator": 310,
                    "rate": 1.0,
                },
                "illustratedRate": {
                    "numerator": 90,
                    "denominator": 100,
                    "rate": 0.9,
                },
                "videoPopularity": {
                    "statistical": True,
                    "nonBlocking": True,
                    "signalAvailability": [
                        {
                            "signal": signal,
                            "numerator": 10,
                            "denominator": 10,
                            "rate": 1.0,
                        }
                        for signal in ("play", "like", "comment", "share", "favorite")
                    ],
                    "rankingCoverage": {
                        "numerator": 10,
                        "denominator": 10,
                        "rate": 1.0,
                    },
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
                                "candidateCount": 10,
                            },
                            "popularityScore": 451,
                            "popularityPercentile": 1.0,
                            "rankingEligible": True,
                            "ineligibleReason": "",
                        }
                    ],
                },
                "automaticRecoveryRate": {
                    "statistical": True,
                    "nonBlocking": True,
                    "status": "MEASURED",
                    "eligibleCount": 20,
                    "automaticCount": 19,
                    "targetRate": 0.95,
                    "rate": 0.95,
                },
                "firstPassRate": {
                    "numerator": 4,
                    "denominator": 4,
                    "rate": 1.0,
                },
                "discardRate": {
                    "numerator": 0,
                    "denominator": 310,
                    "rate": 0.0,
                },
                "quotaAttainmentByCarrier": [
                    {
                        "carrier": carrier,
                        "numerator": 10 if carrier == "video" else 100,
                        "denominator": 10 if carrier == "video" else 100,
                        "rate": 1.0,
                    }
                    for carrier in ("homepage", "article", "image", "video")
                ],
            },
            "duplicateAssetCount": 0,
            "crossLaneWriteCount": 0,
            "resourceIsolationPassed": True,
            "soakDurationSeconds": 3600,
            "semanticJobsByLane": semantic_jobs,
            "semanticCalibrationByLane": semantic_calibration,
            "fourLaneOverlapSampleCount": 1,
            "fourLaneOverlapDurationSeconds": 3600,
            "fourLaneLongestContinuousOverlapSeconds": 3600,
            "allSemanticJobsTerminalAt": "2026-08-05T01:00:00Z",
            "terminalResidualSampleAt": "2026-08-05T01:01:00Z",
            "campaignEvidenceRef": "data/local/campaign/evidence.json",
            "campaignEvidenceDigest": "sha256:" + "1" * 64,
            "resourceSoakEvidenceRef": "data/local/campaign/resource-soak.json",
            "resourceSoakEvidenceDigest": "sha256:" + "2" * 64,
            "faultInjectionEvidenceRef": "data/local/campaign/fault-injection.json",
            "faultInjectionEvidenceDigest": "sha256:" + "3" * 64,
            "m1000Eligible": True,
            "recordedAt": "2026-08-05T00:00:00Z",
        },
    )
    return path


def test_campaign_request_envelope_freeze__contract__local_contract_test(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = Path(__file__).resolve().parents[4]
    monkeypatch.chdir(repo)
    _patch_envelope_deps(monkeypatch)

    first = envelopes.write_scale_envelopes(
        "M100",
        region_ref="china",
        repo_root=repo,
        output_root=tmp_path,
        day="20260731",
        target_names=_wave_targets("freeze"),
    )
    assert set(first) == {"homepage", "article", "image", "video"}
    homepage = first["homepage"]
    payload = homepage.read_text(encoding="utf-8")
    assert "submit-only" in payload
    assert "执行实体内容生成" in payload
    assert '"quota": 100' in payload
    assert f'"count": {_expected_count(100)}' in payload
    assert '"vertical": "travel"' in payload
    assert "travel/M100/china/sequence-001/homepage.json" in homepage.as_posix()
    video_payload = envelopes.read_json(first["video"])
    assert video_payload["quota"] == 10
    assert video_payload["count"] == _expected_count(10)

    second = envelopes.write_scale_envelopes(
        "M100",
        region_ref="china",
        repo_root=repo,
        output_root=tmp_path,
        day="20260731",
        target_names=_wave_targets("freeze"),
    )
    assert second["homepage"] == homepage

    named = envelopes.write_campaign_envelopes(
        scales=["M1", "M100000"],
        region_ref="china",
        repo_root=repo,
        output_root=tmp_path,
        day="20260731",
    )
    assert set(named) == {"M1", "M100000"}
    m1 = envelopes.build_envelope(
        scale="M1",
        carrier="homepage",
        region_ref="china",
        repo_root=repo,
        day="20260731",
    )
    assert m1["quota"] == 1
    assert m1["count"] == _expected_count(1)
    assert m1["scale"] == "M1"
    assert m1["executionId"].endswith("--china--scale-001")
    assert "-workload-homepage-1--" in m1["executionId"]

    m100000 = envelopes.build_envelope(
        scale="M100000",
        carrier="video",
        region_ref="china",
        repo_root=repo,
        day="20260731",
    )
    assert m100000["quota"] == 100000
    assert m100000["count"] == _expected_count(100000)

    arbitrary = envelopes.build_envelope(
        scale="M37",
        carrier="article",
        region_ref="china",
        topic="zhejiang",
        repo_root=repo,
        day="20260731",
    )
    assert arbitrary["quota"] == 37
    assert arbitrary["count"] == _expected_count(37)
    assert arbitrary["topic"] == "zhejiang"
    assert arbitrary["regionRef"] == "china"
    assert "--china-zhejiang--" in arbitrary["executionId"]
    assert arbitrary["familyRef"] == "content/travel/article/article"

    by_quota = envelopes.write_campaign_envelopes(
        quota=37,
        region_ref="china",
        topic="zhejiang",
        repo_root=repo,
        output_root=tmp_path / "by-quota",
        day="20260731",
    )
    assert set(by_quota) == {"M37"}

    with pytest.raises(CampaignScaleError, match="GATE_BLOCK"):
        resolve_campaign_scale(quota=0)
    with pytest.raises(CampaignScaleError, match="GATE_BLOCK"):
        resolve_campaign_scale(scale="M100001")
    with pytest.raises(CampaignScaleError, match="GATE_BLOCK"):
        resolve_campaign_scale(quota=100001)
    with pytest.raises(CampaignScaleError, match="GATE_BLOCK"):
        envelopes.build_envelope(
            scale="M100001",
            carrier="homepage",
            region_ref="china",
            repo_root=repo,
            day="20260731",
        )


def test_campaign_envelope_keeps_object_quota_above_unique_entity_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = Path(__file__).resolve().parents[4]
    _patch_envelope_deps(monkeypatch)

    envelope = envelopes.build_envelope(
        scale="M15",
        carrier="video",
        region_ref="china",
        target_names=(
            "杭州西湖", "都江堰", "成都大熊猫繁育研究基地", "乌镇",
            "成昆铁路", "都江堰熊猫谷", "北京故宫", "黄山风景区",
        ),
        repo_root=repo,
        day="20260807",
    )

    assert envelope["quota"] == 15
    assert len(envelope["targetNames"]) == 8
    assert envelope["count"] == _expected_count(15)
    # DEC-002 起对象配额不再被复制成 worker 数：信封只携带工作单元口径
    # （quota/count）与选中的 calibration 来源绑定。
    assert "requiredWorkers" not in envelope
    assert envelope["capacityCalibration"]["frozenCapacity"][
        "fleetMaxConcurrentWorkers"
    ] == 2


def test_campaign_envelope_freeze_rejects_cross_lane_handoff_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = Path(__file__).resolve().parents[4]
    _patch_envelope_deps(monkeypatch)

    def bind(carrier: str, *_args, **_kwargs):
        return (
            [],
            {
                "handoffId": "local-contract",
                "handoffRevision": 1 if carrier == "homepage" else 2,
                "handoffRef": (
                    "data/local/workspace/content-pre-acquisition-handoffs/"
                    "local-contract/revision-001.json"
                ),
                "handoffDigest": "sha256:" + "9" * 64,
                "handoffFileDigest": "sha256:" + "8" * 64,
            },
        )

    monkeypatch.setattr(
        request_envelope_build,
        "freeze_carrier_pre_acquisition_inputs",
        bind,
    )

    with pytest.raises(ValueError, match="handoff identity changed"):
        envelopes.write_scale_envelopes(
            "M100",
            region_ref="china",
            repo_root=repo,
            output_root=tmp_path,
            day="20260731",
            target_names=_wave_targets("handoff"),
        )
    assert not tuple(tmp_path.rglob("*.json"))


def test_campaign_envelope_freeze_records_expired_probe_as_nonblocking_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = Path(__file__).resolve().parents[4]
    _patch_envelope_deps(monkeypatch)
    predecessor = "20260805--travel-image-workload-image-3--china--scale-001"

    with pytest.raises(ValueError, match="sequence=1 forbids"):
        envelopes.build_envelope(
            scale="M3",
            carrier="image",
            region_ref="china",
            repo_root=repo,
            day="20260805",
            predecessor_execution_id=predecessor,
        )
    retry = envelopes.build_envelope(
        scale="M3",
        carrier="image",
        region_ref="china",
        repo_root=repo,
        day="20260805",
        sequence=2,
        predecessor_execution_id=predecessor,
    )

    assert retry["retryOf"] == predecessor
    assert retry["semanticSelectionId"] == "default"
    assert retry["executionId"] == (
        "20260805--travel-image-workload-image-3--china--scale-002"
    )
    # 显式工作量只激活被请求的载体，因此根执行就是它自己。
    assert retry["rootExecutionId"] == retry["executionId"]
    preflight_root = tmp_path / "semantic-output"
    preflight_path, _binding = ready_semantic_preflight(
        "cursor_grok",
        output_root=preflight_root,
    )
    receipt = read_json(preflight_path)
    outside = (
        datetime.fromisoformat(str(receipt["validUntil"]).replace("Z", "+00:00"))
        + timedelta(seconds=1)
    ).isoformat()
    monkeypatch.setattr(envelopes, "_utc_now", lambda: outside)

    envelope = envelopes.build_envelope(
        scale="M3",
        carrier="image",
        region_ref="china",
        repo_root=repo,
        day="20260805",
        semantic_selection_id="cursor_grok",
        semantic_preflight_receipt=preflight_path,
        semantic_preflight_output_root=preflight_root,
    )

    assert envelope["semanticPreflightReceipt"]["receiptId"] == receipt["receiptId"]
