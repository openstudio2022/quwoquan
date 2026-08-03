"""Generic campaign request envelopes freeze once and validate schema."""

from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace

import pytest

import content.execution.campaign_request_envelope as envelopes
import content.execution.scale_promotion as scale_promotion
from content.execution.campaign_scale import CampaignScaleError, resolve_campaign_scale
from core.io import write_json
from core.runtime_policy import active_runtime_policy


def _patch_envelope_deps(monkeypatch) -> None:
    monkeypatch.setattr(
        envelopes,
        "_require_clean_source_inputs",
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
    return int(math.ceil(quota * active_runtime_policy().oversample_factor))


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
            "provider": "cursor_sdk",
            "authorModel": "auto",
            "authorModelFamily": "auto",
            "authorModelParameters": [],
            "reviewerModel": "auto",
            "reviewerModelFamily": "auto",
            "reviewerModelParameters": [],
        },
        "modelReadinessDigest": "sha256:" + ("e" * 64),
        "postReviewClosureDigest": "sha256:" + ("f" * 64),
        "publishReceiptDigest": "sha256:" + ("0" * 64),
        "sourceReadyCount": 120,
        "sourceIneligibleCount": 60,
        "candidateCount": 180,
        "approvedQuota": 100,
        "qualifiedCount": 100,
        "finalizedCount": 100,
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
    }
    stable.pop("receiptDigest")
    return {
        **stable,
        "receiptDigest": scale_promotion._sha256(stable),
    }


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


def test_travel_video_m1000_requires_matching_m100_promotion(
    monkeypatch,
) -> None:
    repo = Path(__file__).resolve().parents[4]
    _patch_envelope_deps(monkeypatch)

    with pytest.raises(ValueError, match="requires a video scale promotion receipt"):
        envelopes.build_envelope(
            scale="M1000",
            carrier="video",
            region_ref="china",
            repo_root=repo,
            day="20260731",
        )

    approved = _approved_video_promotion()
    envelope = envelopes.build_envelope(
        scale="M1000",
        carrier="video",
        region_ref="china",
        repo_root=repo,
        day="20260731",
        promotion_receipt=approved,
    )
    assert envelope["count"] == _expected_count(1000)
    assert envelope["videoScalePromotion"] == {
        "predecessorExecutionId": approved["predecessorExecutionId"],
        "receiptDigest": approved["receiptDigest"],
        "gitBranch": approved["gitBranch"],
        "gitCommitSha": approved["gitCommitSha"],
        "sourceDigest": approved["sourceDigest"],
        "entityCatalogDigest": approved["entityCatalogDigest"],
        "qualifiedCount": 100,
        "finalizedCount": 100,
    }

    drifted = dict(approved)
    drifted["sourceDigest"] = {
        "algorithm": "sha256",
        "digest": "sha256:" + ("d" * 64),
        "inputs": ["quwoquan_data/scripts"],
    }
    drifted["receiptDigest"] = scale_promotion._sha256(
        {key: value for key, value in drifted.items() if key != "receiptDigest"}
    )
    with pytest.raises(ValueError, match="inputs drift"):
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
) -> None:
    repo = Path(__file__).resolve().parents[4]
    _patch_envelope_deps(monkeypatch)

    with pytest.raises(ValueError, match="requires an image scale promotion receipt"):
        envelopes.build_envelope(
            scale="M1000",
            carrier="image",
            region_ref="china",
            repo_root=repo,
            day="20260731",
        )

    approved = _approved_image_promotion()
    envelope = envelopes.build_envelope(
        scale="M1000",
        carrier="image",
        region_ref="china",
        repo_root=repo,
        day="20260731",
        promotion_receipt=approved,
    )

    assert envelope["count"] == _expected_count(1000)
    assert envelope["imageScalePromotion"]["predecessorExecutionId"] == (
        "20260731--travel-image-m100--china--scale-002"
    )
    assert envelope["imageScalePromotion"]["qualifiedCount"] == 100
    assert envelope["imageScalePromotion"]["finalizedCount"] == 100

    drifted = dict(approved)
    drifted["entityCatalogDigest"] = "sha256:" + ("d" * 64)
    drifted["receiptDigest"] = scale_promotion._sha256(
        {key: value for key, value in drifted.items() if key != "receiptDigest"}
    )
    with pytest.raises(ValueError, match="inputs drift"):
        envelopes.build_envelope(
            scale="M1000",
            carrier="image",
            region_ref="china",
            repo_root=repo,
            day="20260731",
            promotion_receipt=drifted,
        )


def test_scale_promotion_requires_clean_frozen_source_inputs(monkeypatch) -> None:
    monkeypatch.setattr(
        scale_promotion.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=" M quwoquan_data/scripts\n"),
    )

    with pytest.raises(ValueError, match="requires clean sourceDigest inputs"):
        scale_promotion._require_clean_source_inputs(
            {"inputs": ["quwoquan_data/scripts"]}
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
        "_require_clean_source_inputs",
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
            "sourceReadyCount": 120,
            "sourceIneligibleCount": 60,
            "candidateCount": 180,
        },
    )
    monkeypatch.setattr(
        scale_promotion,
        "_review_and_publish",
        lambda *_args, **_kwargs: (
            {
                "approvedQuota": 100,
                "qualifiedCount": 100,
                "finalizedCount": 100,
                "discardedCount": 80,
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
            "quota": 100,
            "count": 180,
            "topic": None,
            "targetNames": [],
            "sourceProviders": [],
            "retryOf": None,
            "rootExecutionId": (
                "20260731--travel-homepage-m100--china--scale-002"
            ),
            "executionId": execution_id,
            "gitBranch": approved["gitBranch"],
            "gitCommitSha": approved["gitCommitSha"],
            "sourceDigest": approved["sourceDigest"],
            "entityCatalogDigest": approved["entityCatalogDigest"],
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
    assert stored["qualifiedCount"] == 100
    assert (
        scale_promotion.write_video_scale_promotion(
            predecessor_execution_id=execution_id,
            predecessor_envelope={
                **{
                    "schema": "quwoquan_data.content_campaign_request_envelope",
                    "scale": "M100",
                    "carrier": "video",
                    "operation": "video.generate",
                    "vertical": "travel",
                    "familyRef": "content/travel/video/video",
                    "regionRef": "china",
                    "selector": "priority",
                    "quota": 100,
                    "count": 180,
                    "topic": None,
                    "targetNames": [],
                    "sourceProviders": [],
                    "retryOf": None,
                    "rootExecutionId": (
                        "20260731--travel-homepage-m100--china--scale-002"
                    ),
                    "executionId": execution_id,
                    "gitBranch": approved["gitBranch"],
                    "gitCommitSha": approved["gitCommitSha"],
                    "sourceDigest": approved["sourceDigest"],
                    "entityCatalogDigest": approved["entityCatalogDigest"],
                    "allowedStage": "submit-only",
                    "operatorPrompt": "执行视频内容生成",
                    "requestDigest": approved["predecessorInputDigest"],
                    "frozenAt": "2026-07-31T00:00:00+00:00",
                }
            },
            root=tmp_path / "receipts",
        )
        == path
    )
    write_json(
        package_root / "0.plan" / "request.json",
        {
            "familyRef": "content/travel/video/video",
            "quota": 100,
            "count": 180,
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
