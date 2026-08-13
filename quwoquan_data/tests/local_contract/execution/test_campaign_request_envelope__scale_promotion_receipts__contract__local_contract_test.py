"""Generic campaign request envelopes freeze once and validate schema."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from content.execution.campaign.external_inputs import (
    content_source_revision,
    external_inputs_digest,
)
from content.execution.scale import promotion as scale_promotion
from core.io import write_json
from support.campaign_request_envelope_fixture import (
    _expected_count,
    _wave_targets,
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


def test_scale_promotion_accepts_governed_auto_model_pair_before_m1000() -> None:
    assert scale_promotion.require_scale_promotion_model_binding(
        {
            "provider": "cursor_sdk",
            "authorModel": "auto",
            "authorModelFamily": "auto",
            "reviewerModel": "auto",
            "reviewerModelFamily": "auto",
        },
        label="video M100 scale promotion",
    ) == {
        "provider": "cursor_sdk",
        "authorModel": "auto",
        "authorModelFamily": "auto",
        "reviewerModel": "auto",
        "reviewerModelFamily": "auto",
    }

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
    assert scale_promotion.require_video_m1000_promotion(
        auto_receipt,
        git_branch=str(auto_receipt["gitBranch"]),
        git_commit_sha=str(auto_receipt["gitCommitSha"]),
        source_digest=auto_receipt["sourceDigest"],
        entity_catalog_digest=str(auto_receipt["entityCatalogDigest"]),
    ) == auto_receipt


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
                "approvedQuota": 10,
                "qualifiedCount": 1,
                "finalizedCount": 1,
                "discardedCount": 89,
                "shortfallCount": 9,
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
            "quota": 10,
            "count": _expected_count(10),
            "requiredWorkers": 1,
            "partitionCount": 16,
            "capacityPlanDigest": "sha256:" + "7" * 64,
            "workerHostSetBinding": None,
            "scaleSourcePool": {
                "poolId": "pool-local-contract",
                "targetScale": "M100",
                "sourceRevision": content_source_revision(
                    source_digest=str(approved["sourceDigest"]["digest"]),
                    entity_catalog_digest=str(approved["entityCatalogDigest"]),
                ),
                "sourceDigest": approved["sourceDigest"]["digest"],
                "entityCatalogDigest": approved["entityCatalogDigest"],
                "planRef": "data/local/workspace/source-pool/plan.json",
                "planDigest": "sha256:" + "4" * 64,
                "planFileSha256": "sha256:" + "5" * 64,
            },
            "sourcePoolEvidenceRootRef": "data/local/workspace/source-pool/evidence",
            "sourcePoolSelection": {
                "carrier": "video",
                "candidateIds": [f"video-{index:02d}" for index in range(18)],
                "candidateCount": 18,
                "selectionDigest": "sha256:" + "6" * 64,
            },
            "topic": None,
            "targetNames": list(_wave_targets("promotion")),
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
            "sourceRevision": content_source_revision(
                source_digest=str(approved["sourceDigest"]["digest"]),
                entity_catalog_digest=str(approved["entityCatalogDigest"]),
            ),
            "entityCatalogDigest": approved["entityCatalogDigest"],
            "preAcquisitionHandoff": {
                "handoffId": "local-contract",
                "handoffRevision": 1,
                "handoffRef": (
                    "data/local/workspace/content-pre-acquisition-handoffs/"
                    "local-contract/revision-001.json"
                ),
                "handoffDigest": "sha256:" + "9" * 64,
                "handoffFileDigest": "sha256:" + "8" * 64,
            },
            "externalInputRefs": [],
            "externalInputsDigest": external_inputs_digest([]),
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
    assert stored["qualifiedCount"] == 1
    assert stored["shortfallCount"] == 9
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
                "quota": 10,
                "count": _expected_count(10),
                "requiredWorkers": 1,
                "partitionCount": 16,
                "capacityPlanDigest": "sha256:" + "7" * 64,
                "workerHostSetBinding": None,
                "scaleSourcePool": {
                    "poolId": "pool-local-contract",
                    "targetScale": "M100",
                    "sourceRevision": content_source_revision(
                        source_digest=str(approved["sourceDigest"]["digest"]),
                        entity_catalog_digest=str(approved["entityCatalogDigest"]),
                    ),
                    "sourceDigest": approved["sourceDigest"]["digest"],
                    "entityCatalogDigest": approved["entityCatalogDigest"],
                    "planRef": "data/local/workspace/source-pool/plan.json",
                    "planDigest": "sha256:" + "4" * 64,
                    "planFileSha256": "sha256:" + "5" * 64,
                },
                "sourcePoolEvidenceRootRef": "data/local/workspace/source-pool/evidence",
                "sourcePoolSelection": {
                    "carrier": "video",
                    "candidateIds": [f"video-{index:02d}" for index in range(18)],
                    "candidateCount": 18,
                    "selectionDigest": "sha256:" + "6" * 64,
                },
                "topic": None,
                "targetNames": list(_wave_targets("promotion")),
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
                "sourceRevision": content_source_revision(
                    source_digest=str(approved["sourceDigest"]["digest"]),
                    entity_catalog_digest=str(
                        approved["entityCatalogDigest"]
                    ),
                ),
                "entityCatalogDigest": approved["entityCatalogDigest"],
                "preAcquisitionHandoff": {
                    "handoffId": "local-contract",
                    "handoffRevision": 1,
                    "handoffRef": (
                        "data/local/workspace/content-pre-acquisition-handoffs/"
                        "local-contract/revision-001.json"
                    ),
                    "handoffDigest": "sha256:" + "9" * 64,
                    "handoffFileDigest": "sha256:" + "8" * 64,
                },
                "externalInputRefs": [],
                "externalInputsDigest": external_inputs_digest([]),
                "allowedStage": "submit-only",
                "operatorPrompt": "执行视频内容生成",
                "requestDigest": approved["predecessorInputDigest"],
                "frozenAt": "2026-07-31T00:00:00+00:00",
            },
            root=tmp_path / "receipts",
        )
        == path
    )
    write_json(
        package_root / "0.plan" / "request.json",
        {
            "familyRef": "content/travel/video/video",
            "quota": 10,
            "count": _expected_count(10),
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
