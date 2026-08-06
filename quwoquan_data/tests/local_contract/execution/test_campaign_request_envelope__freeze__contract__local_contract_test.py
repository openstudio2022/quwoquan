"""Generic campaign request envelopes freeze once and validate schema."""

from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace

import content.execution.campaign_request_envelope as envelopes
import pytest
from content.execution import scale_promotion
from content.execution.campaign_scale import CampaignScaleError, resolve_campaign_scale
from core.io import write_json
from core.runtime_policy import active_runtime_policy
from support.semantic_preflight_fixture import ready_semantic_preflight


def _patch_envelope_deps(monkeypatch) -> None:
    monkeypatch.setattr(
        envelopes,
        "_require_stable_source_inputs",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(envelopes, "_git_branch", lambda _repo: "dev1.0")
    monkeypatch.setattr(
        envelopes,
        "_git_commit",
        lambda _repo: "0123456789abcdef0123456789abcdef01234567",
    )
    monkeypatch.setattr(
        envelopes,
        "current_source_digest",
        lambda repo_root=None: type(
            "Digest",
            (),
            {
                "to_document": staticmethod(
                    lambda: {
                        "algorithm": "sha256",
                        "digest": "sha256:" + ("a" * 64),
                        "inputs": ["quwoquan_data/scripts"],
                    }
                )
            },
        )(),
    )
    monkeypatch.setattr(
        envelopes,
        "entity_catalog_digest",
        lambda _ref: "sha256:" + ("b" * 64),
    )


def _expected_count(quota: int) -> int:
    return math.ceil(quota * active_runtime_policy().oversample_factor)


def test_campaign_source_freeze_allows_dirty_tree_when_content_digest_is_stable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen = {
        "algorithm": "sha256",
        "digest": "sha256:" + "a" * 64,
        "inputs": ["quwoquan_data/scripts"],
    }
    monkeypatch.setattr(
        envelopes,
        "current_source_digest",
        lambda **_kwargs: SimpleNamespace(to_document=lambda: dict(frozen)),
    )
    monkeypatch.setattr(
        envelopes.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("Git cleanliness must not be queried"),
    )

    envelopes._require_stable_source_inputs(frozen, repo_root=tmp_path)


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
    monkeypatch.setattr(
        envelopes,
        "current_source_digest",
        lambda **_kwargs: SimpleNamespace(to_document=lambda: dict(observed)),
    )

    with pytest.raises(ValueError, match="changed during freeze"):
        envelopes._require_stable_source_inputs(frozen, repo_root=tmp_path)


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
        "approvedQuota": 50,
        "qualifiedCount": 50,
        "finalizedCount": 50,
        "discardedCount": 40,
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
                "acceptedObjectCount": 50 if carrier == "video" else 100,
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
                {"carrier": "homepage", "researchAcceptedCount": 100},
                {"carrier": "article", "researchAcceptedCount": 100},
                {"carrier": "image", "researchAcceptedCount": 100},
                {"carrier": "video", "researchAcceptedCount": 50},
            ],
            "duplicateAssetCount": 0,
            "crossLaneWriteCount": 0,
            "articleIllustratedRate": 0.9,
            "resourceIsolationPassed": True,
            "soakDurationSeconds": 3600,
            "semanticJobsByLane": semantic_jobs,
            "semanticCalibrationByLane": semantic_calibration,
            "fourLaneOverlapSampleCount": 1,
            "fourLaneOverlapDurationSeconds": 3600,
            "fourLaneLongestContinuousOverlapSeconds": 3600,
            "allSemanticJobsTerminalAt": "2026-08-05T01:00:00Z",
            "terminalResidualSampleAt": "2026-08-05T01:01:00Z",
            "automaticRecoveryStatus": "MEASURED",
            "recoveryEligibleCount": 20,
            "automaticRecoveredCount": 19,
            "automaticRecoveryRate": 0.95,
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
    )
    assert set(first) == {"homepage", "article", "image", "video"}
    homepage = first["homepage"]
    payload = homepage.read_text(encoding="utf-8")
    assert "submit-only" in payload
    assert "执行实体内容生成" in payload
    assert '"quota": 100' in payload
    assert f'"count": {_expected_count(100)}' in payload
    assert '"vertical": "travel"' in payload
    assert "travel/M100/homepage.json" in homepage.as_posix()
    video_payload = envelopes.read_json(first["video"])
    assert video_payload["quota"] == 50
    assert video_payload["count"] == _expected_count(50)

    second = envelopes.write_scale_envelopes(
        "M100",
        region_ref="china",
        repo_root=repo,
        output_root=tmp_path,
        day="20260731",
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
    assert "-m1--" in m1["executionId"]

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


def test_campaign_retry_envelope_requires_one_matching_predecessor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = Path(__file__).resolve().parents[4]
    _patch_envelope_deps(monkeypatch)
    predecessor = "20260805--travel-image-m3--china--scale-001"

    with pytest.raises(ValueError, match="sequence=1 forbids"):
        envelopes.build_envelope(
            scale="M3",
            carrier="image",
            region_ref="china",
            repo_root=repo,
            day="20260805",
            predecessor_execution_id=predecessor,
        )
    with pytest.raises(ValueError, match="sequence>1 requires"):
        envelopes.build_envelope(
            scale="M3",
            carrier="image",
            region_ref="china",
            repo_root=repo,
            day="20260805",
            sequence=2,
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
        "20260805--travel-image-m3--china--scale-002"
    )
    assert retry["rootExecutionId"] == (
        "20260805--travel-homepage-m3--china--scale-002"
    )
    preflight_root = tmp_path / "semantic-output"
    preflight_path, _preflight_binding = ready_semantic_preflight(
        "cursor_auto",
        output_root=preflight_root,
    )
    cursor_retry = envelopes.build_envelope(
        scale="M3",
        carrier="image",
        region_ref="china",
        repo_root=repo,
        day="20260805",
        sequence=2,
        predecessor_execution_id=predecessor,
        semantic_selection_id="cursor_auto",
        semantic_preflight_receipt=preflight_path,
        semantic_preflight_output_root=preflight_root,
    )
    assert cursor_retry["semanticSelectionId"] == "cursor_auto"
    assert cursor_retry["semanticPreflightReceipt"] == _preflight_binding
    with pytest.raises(ValueError, match="cursor_auto.*retryOf"):
        envelopes.build_envelope(
            scale="M3",
            carrier="image",
            region_ref="china",
            repo_root=repo,
            day="20260805",
            semantic_selection_id="cursor_auto",
        )
    with pytest.raises(ValueError, match="preserve execution scope"):
        envelopes.build_envelope(
            scale="M3",
            carrier="image",
            region_ref="china",
            repo_root=repo,
            day="20260805",
            sequence=2,
            predecessor_execution_id=(
                "20260805--travel-video-m3--china--scale-001"
            ),
        )


def test_campaign_retry_write_requires_four_predecessors_and_separate_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = Path(__file__).resolve().parents[4]
    _patch_envelope_deps(monkeypatch)
    predecessors = {
        carrier: (
            f"20260805--travel-{carrier}-m3--china--scale-001"
        )
        for carrier in ("homepage", "article", "image", "video")
    }

    with pytest.raises(ValueError, match="complete four-carrier"):
        envelopes.write_scale_envelopes(
            "M3",
            region_ref="china",
            repo_root=repo,
            output_root=tmp_path,
            day="20260805",
            sequence=2,
            predecessor_execution_ids_by_carrier={
                "homepage": predecessors["homepage"]
            },
        )
    with pytest.raises(ValueError, match="sequence=1 forbids"):
        envelopes.write_scale_envelopes(
            "M3",
            region_ref="china",
            repo_root=repo,
            output_root=tmp_path,
            day="20260805",
            predecessor_execution_ids_by_carrier=predecessors,
        )

    first = envelopes.write_scale_envelopes(
        "M3",
        region_ref="china",
        repo_root=repo,
        output_root=tmp_path,
        day="20260805",
        sequence=2,
        predecessor_execution_ids_by_carrier=predecessors,
    )
    second = envelopes.write_scale_envelopes(
        "M3",
        region_ref="china",
        repo_root=repo,
        output_root=tmp_path,
        day="20260805",
        sequence=2,
        predecessor_execution_ids_by_carrier=predecessors,
    )

    assert second == first
    for carrier, path in first.items():
        assert f"travel/M3/retry-002/{carrier}.json" in path.as_posix()
        payload = envelopes.load_campaign_envelope(path)
        assert payload["retryOf"] == predecessors[carrier]
        assert payload["executionId"].endswith("--scale-002")
        assert payload["rootExecutionId"].endswith("--scale-002")


def test_campaign_retry_envelopes_bind_submission_reconciliation_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = Path(__file__).resolve().parents[4]
    _patch_envelope_deps(monkeypatch)
    receipt_path = tmp_path / "submission-only-abandonment.json"
    predecessors = {
        carrier: f"20260805--travel-{carrier}-m3--china--scale-001"
        for carrier in ("homepage", "article", "image", "video")
    }
    receipt = {
        "rootExecutionId": predecessors["homepage"],
        "reason": "source_drift",
        "originalSourceIdentity": {
            "sourceRevision": envelopes.content_source_revision(
                source_digest="sha256:" + "d" * 64,
                entity_catalog_digest="sha256:" + "b" * 64,
            ),
            "sourceDigest": {
                "algorithm": "sha256",
                "digest": "sha256:" + "d" * 64,
                "inputs": ["quwoquan_data/scripts"],
            },
            "entityCatalogDigest": "sha256:" + "b" * 64,
        },
        "observedSourceIdentity": {
            "sourceRevision": envelopes.content_source_revision(
                source_digest="sha256:" + "c" * 64,
                entity_catalog_digest="sha256:" + "b" * 64,
            ),
            "sourceDigest": {
                "algorithm": "sha256",
                "digest": "sha256:" + "c" * 64,
                "inputs": ["quwoquan_data/scripts"],
            },
            "entityCatalogDigest": "sha256:" + "b" * 64,
        },
        "submissions": {
            carrier: {
                "executionId": execution_id,
                "targetNames": ["乌镇", "成都大熊猫繁育研究基地", "西湖"],
            }
            for carrier, execution_id in predecessors.items()
        },
        "receiptDigest": "sha256:" + "c" * 64,
    }
    monkeypatch.setattr(
        envelopes,
        "load_submission_reconciliation_receipt",
        lambda *_args, **_kwargs: receipt,
    )
    monkeypatch.setattr(
        envelopes,
        "reconciliation_reference",
        lambda *_args, **_kwargs: {
            "predecessorRootExecutionId": predecessors["homepage"],
            "receiptRef": "data/local/reconciliation/submission-only.json",
            "receiptDigest": "sha256:" + "c" * 64,
        },
    )

    paths = envelopes.write_scale_envelopes(
        "M3",
        region_ref="china",
        repo_root=repo,
        output_root=tmp_path / "envelopes",
        day="20260805",
        sequence=2,
        predecessor_reconciliation_receipt=receipt_path,
    )

    for carrier, path in paths.items():
        payload = envelopes.load_campaign_envelope(path)
        assert payload["retryOf"] == predecessors[carrier]
        assert payload["targetNames"] == [
            "乌镇",
            "成都大熊猫繁育研究基地",
            "西湖",
        ]
        assert payload["predecessorReconciliation"]["receiptDigest"] == (
            "sha256:" + "c" * 64
        )

    with pytest.raises(ValueError, match="targetNames differ"):
        envelopes.write_scale_envelopes(
            "M3",
            region_ref="china",
            target_names=["另一个目标"],
            repo_root=repo,
            output_root=tmp_path / "drifted-envelopes",
            day="20260805",
            sequence=2,
            predecessor_reconciliation_receipt=receipt_path,
        )

    current_identity = {
        "sourceRevision": envelopes.content_source_revision(
            source_digest="sha256:" + "a" * 64,
            entity_catalog_digest="sha256:" + "b" * 64,
        ),
        "sourceDigest": {
            "algorithm": "sha256",
            "digest": "sha256:" + "a" * 64,
            "inputs": ["quwoquan_data/scripts"],
        },
        "entityCatalogDigest": "sha256:" + "b" * 64,
    }
    receipt["originalSourceIdentity"] = current_identity
    with pytest.raises(ValueError, match="did not leave the reconciled source"):
        envelopes.write_scale_envelopes(
            "M3",
            region_ref="china",
            repo_root=repo,
            output_root=tmp_path / "original-source-envelopes",
            day="20260805",
            sequence=2,
            predecessor_reconciliation_receipt=receipt_path,
        )


def test_travel_video_m1000_requires_matching_m100_promotion(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[4]
    _patch_envelope_deps(monkeypatch)

    with pytest.raises(ValueError, match="canonical four-carrier M100 receipt"):
        envelopes.build_envelope(
            scale="M1000",
            carrier="video",
            region_ref="china",
            repo_root=repo,
            day="20260731",
        )

    approved = _research_m100_receipt(tmp_path / "m100.json")
    envelope = envelopes.build_envelope(
        scale="M1000",
        carrier="video",
        region_ref="china",
        repo_root=repo,
        day="20260731",
        promotion_receipt=approved,
    )
    assert envelope["quota"] == 300
    assert envelope["count"] == _expected_count(300)
    assert envelope["researchScalePromotion"]["promotionId"] == "research-m100-1"

    drifted = _research_m100_receipt(
        tmp_path / "m100-drifted.json",
        source_digest="sha256:" + ("e" * 64),
    )
    with pytest.raises(ValueError, match="identity drift"):
        envelopes.build_envelope(
            scale="M1000",
            carrier="video",
            region_ref="china",
            repo_root=repo,
            day="20260731",
            promotion_receipt=drifted,
        )


def test_travel_image_m1000_requires_matching_m100_promotion(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[4]
    _patch_envelope_deps(monkeypatch)

    with pytest.raises(ValueError, match="canonical four-carrier M100 receipt"):
        envelopes.build_envelope(
            scale="M1000",
            carrier="image",
            region_ref="china",
            repo_root=repo,
            day="20260731",
        )

    approved = _research_m100_receipt(tmp_path / "m100.json")
    envelope = envelopes.build_envelope(
        scale="M1000",
        carrier="image",
        region_ref="china",
        repo_root=repo,
        day="20260731",
        promotion_receipt=approved,
    )

    assert envelope["count"] == _expected_count(1000)
    assert envelope["quota"] == 1000
    assert envelope["researchScalePromotion"]["releaseId"] == "research-release-1"

    drifted = _research_m100_receipt(tmp_path / "m100-drifted.json")
    drifted_doc = envelopes.read_json(drifted)
    drifted_doc["entityCatalogDigest"] = "sha256:" + ("d" * 64)
    write_json(drifted, drifted_doc)
    with pytest.raises(ValueError, match="identity drift"):
        envelopes.build_envelope(
            scale="M1000",
            carrier="image",
            region_ref="china",
            repo_root=repo,
            day="20260731",
            promotion_receipt=drifted,
        )


def test_scale_promotion_uses_frozen_digest_without_live_git_cleanliness() -> None:
    scale_promotion._require_frozen_source_inputs(
        {
            "algorithm": "sha256",
            "digest": "sha256:" + "a" * 64,
            "inputs": ["quwoquan_data/scripts"],
        }
    )
    with pytest.raises(ValueError, match="sourceDigest inputs are missing"):
        scale_promotion._require_frozen_source_inputs({"inputs": []})


def test_scale_promotion_blocks_auto_model_pair_before_m1000() -> None:
    with pytest.raises(
        RuntimeError,
        match="DATA.AGENT.SCALE_CALIBRATION_REQUIRED",
    ):
        scale_promotion.require_scale_promotion_model_binding(
            {
                "provider": "cursor_sdk",
                "authorModel": "auto",
                "authorModelFamily": "auto",
                "reviewerModel": "auto",
                "reviewerModelFamily": "auto",
            },
            label="video M100 scale promotion",
        )

    assert scale_promotion.require_scale_promotion_model_binding(
        _approved_video_promotion()["modelBinding"],
        label="video M100 scale promotion",
    ) == {
        "provider": "codex_sdk",
        "authorModel": "gpt-5.6-terra",
        "authorModelFamily": "gpt",
        "reviewerModel": "gpt-5.6-terra",
        "reviewerModelFamily": "gpt",
    }

    auto_receipt = _approved_video_promotion()
    auto_receipt["modelBinding"] = {
        "provider": "cursor_sdk",
        "authorModel": "auto",
        "authorModelFamily": "auto",
        "authorModelParameters": [],
        "reviewerModel": "auto",
        "reviewerModelFamily": "auto",
        "reviewerModelParameters": [],
    }
    stable = {key: value for key, value in auto_receipt.items() if key != "receiptDigest"}
    auto_receipt["receiptDigest"] = scale_promotion._sha256(stable)
    with pytest.raises(
        RuntimeError,
        match="DATA.AGENT.SCALE_CALIBRATION_REQUIRED",
    ):
        scale_promotion.require_video_m1000_promotion(
            auto_receipt,
            git_branch=str(auto_receipt["gitBranch"]),
            git_commit_sha=str(auto_receipt["gitCommitSha"]),
            source_digest=auto_receipt["sourceDigest"],
            entity_catalog_digest=str(auto_receipt["entityCatalogDigest"]),
        )


def test_video_scale_promotion_writes_immutable_m100_receipt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    execution_id = "20260731--travel-video-m100--china--scale-002"
    approved = _approved_video_promotion()
    package_root = tmp_path / "execution"
    monkeypatch.setattr(
        scale_promotion,
        "execution_root",
        lambda received_execution_id: (
            package_root
            if received_execution_id == execution_id
            else pytest.fail("unexpected execution ID")
        ),
    )
    monkeypatch.setattr(
        scale_promotion,
        "load_frozen_execution_manifest",
        lambda _execution_id: {
            "sourceDigest": approved["sourceDigest"],
            "targetSetDigest": approved["targetSetDigest"],
            "modelBinding": approved["modelBinding"],
        },
    )
    monkeypatch.setattr(
        scale_promotion,
        "load_frozen_target_set",
        lambda _execution_id: {
            "entityCatalogDigest": approved["entityCatalogDigest"],
        },
    )
    monkeypatch.setattr(
        scale_promotion,
        "_require_frozen_source_inputs",
        lambda _source_document: None,
    )
    monkeypatch.setattr(
        scale_promotion,
        "_model_readiness",
        lambda *_args, **_kwargs: {"ready": True},
    )
    monkeypatch.setattr(
        scale_promotion,
        "_source_availability",
        lambda *_args, **_kwargs: {
            "sourceReadyCount": 60,
            "sourceIneligibleCount": 30,
            "candidateCount": 90,
        },
    )
    monkeypatch.setattr(
        scale_promotion,
        "_review_and_publish",
        lambda *_args, **_kwargs: (
            {
                "approvedQuota": 50,
                "qualifiedCount": 50,
                "finalizedCount": 50,
                "discardedCount": 40,
                "shortfallCount": 0,
            },
            {"schema": "quwoquan_data.post_review_closure"},
            {"schema": "quwoquan_data.publish_ref"},
        ),
    )

    path = scale_promotion.write_video_scale_promotion(
        predecessor_execution_id=execution_id,
        predecessor_envelope={
            "schema": "quwoquan_data.content_campaign_request_envelope",
            "scale": "M100",
            "carrier": "video",
            "operation": "video.generate",
            "vertical": "travel",
            "familyRef": "content/travel/video/video",
            "regionRef": "china",
            "selector": "priority",
            "quota": 50,
            "count": 90,
            "topic": None,
            "targetNames": [],
            "sourceProviders": [],
            "semanticSelectionId": "default",
            "retryOf": None,
            "rootExecutionId": (
                "20260731--travel-homepage-m100--china--scale-002"
            ),
            "executionId": execution_id,
            "gitBranch": approved["gitBranch"],
            "gitCommitSha": approved["gitCommitSha"],
                "sourceDigest": approved["sourceDigest"],
                "sourceRevision": envelopes.content_source_revision(
                    source_digest=str(approved["sourceDigest"]["digest"]),
                    entity_catalog_digest=str(approved["entityCatalogDigest"]),
                ),
                "entityCatalogDigest": approved["entityCatalogDigest"],
                "externalInputRefs": [],
                "externalInputsDigest": envelopes.external_inputs_digest([]),
            "allowedStage": "submit-only",
            "operatorPrompt": "执行视频内容生成",
            "requestDigest": approved["predecessorInputDigest"],
            "frozenAt": "2026-07-31T00:00:00+00:00",
        },
        root=tmp_path / "receipts",
    )

    assert path.is_file()
    stored = scale_promotion.load_video_scale_promotion(path)
    assert stored["predecessorExecutionId"] == execution_id
    assert stored["qualifiedCount"] == 50
    assert (
        scale_promotion.write_video_scale_promotion(
            predecessor_execution_id=execution_id,
            predecessor_envelope={
                    "schema": "quwoquan_data.content_campaign_request_envelope",
                    "scale": "M100",
                    "carrier": "video",
                    "operation": "video.generate",
                    "vertical": "travel",
                    "familyRef": "content/travel/video/video",
                    "regionRef": "china",
                    "selector": "priority",
                    "quota": 50,
                    "count": 90,
                    "topic": None,
                    "targetNames": [],
                    "sourceProviders": [],
                    "semanticSelectionId": "default",
                    "retryOf": None,
                    "rootExecutionId": (
                        "20260731--travel-homepage-m100--china--scale-002"
                    ),
                    "executionId": execution_id,
                        "gitBranch": approved["gitBranch"],
                        "gitCommitSha": approved["gitCommitSha"],
                        "sourceDigest": approved["sourceDigest"],
                        "sourceRevision": envelopes.content_source_revision(
                            source_digest=str(approved["sourceDigest"]["digest"]),
                            entity_catalog_digest=str(
                                approved["entityCatalogDigest"]
                            ),
                        ),
                        "entityCatalogDigest": approved["entityCatalogDigest"],
                        "externalInputRefs": [],
                        "externalInputsDigest": envelopes.external_inputs_digest([]),
                    "allowedStage": "submit-only",
                    "operatorPrompt": "执行视频内容生成",
                    "requestDigest": approved["predecessorInputDigest"],
                    "frozenAt": "2026-07-31T00:00:00+00:00"
            },
            root=tmp_path / "receipts",
        )
        == path
    )
    write_json(
        package_root / "0.plan" / "request.json",
        {
            "familyRef": "content/travel/video/video",
            "quota": 50,
            "count": 90,
        },
    )
    monkeypatch.setattr(
        scale_promotion.subprocess,
        "run",
        lambda command, **_kwargs: SimpleNamespace(
            stdout=(
                "dev1.0\n"
                if command == ["git", "branch", "--show-current"]
                else "0123456789abcdef0123456789abcdef01234567\n"
            )
        ),
    )
    direct_path = scale_promotion.write_video_scale_promotion(
        predecessor_execution_id=execution_id,
        root=tmp_path / "direct-receipts",
    )
    direct = scale_promotion.load_video_scale_promotion(direct_path)
    assert direct["predecessorInputMode"] == "direct_execution"
    assert direct["predecessorInputDigest"].startswith("sha256:")
