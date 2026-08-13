"""场景组：M100 video popularity 排名观测的 execution review 证据绑定。

从 test_campaign_scale_evidence__derived__contract__local_contract_test.py
按场景拆出；测试逐字搬移。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from content.release.canonical.research_scale_video_popularity import (
    ResearchScaleVideoPopularityError,
    collect_m100_video_popularity_observations,
)

from support.campaign_scale_evidence_fixture import (
    CATALOG_DIGEST,
    SOURCE_DIGEST,
    _digest,
    _execution_id,
    _file_digest,
    _write,
    _write_ranked_release_videos,
)


def _single_video_popularity_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    release = tmp_path / "output/data/releases/research-release"
    execution_id = _execution_id("video")
    source_revision = _digest(
        {
            "schema": "quwoquan_data.campaign_content_source_revision",
            "sourceDigest": SOURCE_DIGEST,
            "entityCatalogDigest": CATALOG_DIGEST,
        }
    )
    _write_ranked_release_videos(
        release,
        count=1,
        execution_id=execution_id,
        source_revision=source_revision,
    )
    rights_path = release / "payload/objects/posts/video/work-000/rights.json"
    rights = json.loads(rights_path.read_text(encoding="utf-8"))
    receipt_ref = rights["assets"][0]["independentAssetReview"]["receiptRef"]
    return release, rights_path, release.parents[2] / receipt_ref


def test_video_popularity_reads_digest_bound_execution_review(tmp_path: Path) -> None:
    release, _rights_path, _receipt_path = _single_video_popularity_fixture(tmp_path)

    observations = collect_m100_video_popularity_observations(
        release,
        expected_video_count=1,
    )

    assert observations[0]["assetId"] == "video-asset-000"
    assert observations[0]["rankingEligible"] is True


def test_video_popularity_rejects_legacy_object_local_review_ref(
    tmp_path: Path,
) -> None:
    release, rights_path, _receipt_path = _single_video_popularity_fixture(tmp_path)
    rights = json.loads(rights_path.read_text(encoding="utf-8"))
    rights["assets"][0]["independentAssetReview"]["receiptRef"] = (
        "asset_reviews/receipts/review.json"
    )
    _write(rights_path, rights)

    with pytest.raises(
        ResearchScaleVideoPopularityError,
        match="must name execution evidence",
    ):
        collect_m100_video_popularity_observations(
            release,
            expected_video_count=1,
        )


def test_video_popularity_rejects_review_ref_traversal(tmp_path: Path) -> None:
    release, rights_path, _receipt_path = _single_video_popularity_fixture(tmp_path)
    rights = json.loads(rights_path.read_text(encoding="utf-8"))
    rights["assets"][0]["independentAssetReview"]["receiptRef"] = (
        "data/tasks/execution/evidence/asset_reviews/receipts/../../review.json"
    )
    _write(rights_path, rights)

    with pytest.raises(
        ResearchScaleVideoPopularityError,
        match="must name execution evidence",
    ):
        collect_m100_video_popularity_observations(
            release,
            expected_video_count=1,
        )


def test_video_popularity_rejects_execution_review_digest_drift(
    tmp_path: Path,
) -> None:
    release, rights_path, receipt_path = _single_video_popularity_fixture(tmp_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["assetSnapshot"]["popularitySignals"]["playCount"] += 1
    _write(receipt_path, receipt)
    rights = json.loads(rights_path.read_text(encoding="utf-8"))
    rights["assets"][0]["independentAssetReview"]["receiptFileSha256"] = (
        _file_digest(receipt_path)
    )
    _write(rights_path, rights)

    with pytest.raises(
        ResearchScaleVideoPopularityError,
        match="execution review binding drift",
    ):
        collect_m100_video_popularity_observations(
            release,
            expected_video_count=1,
        )


def test_video_popularity_rejects_cross_execution_review_binding(
    tmp_path: Path,
) -> None:
    release, rights_path, receipt_path = _single_video_popularity_fixture(tmp_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["reviewerExecution"]["executionId"] = _execution_id("video", 3)
    receipt["receiptDigest"] = _digest(
        {key: value for key, value in receipt.items() if key != "receiptDigest"}
    )
    _write(receipt_path, receipt)
    rights = json.loads(rights_path.read_text(encoding="utf-8"))
    binding = rights["assets"][0]["independentAssetReview"]
    binding["receiptDigest"] = receipt["receiptDigest"]
    binding["receiptFileSha256"] = _file_digest(receipt_path)
    _write(rights_path, rights)

    with pytest.raises(
        ResearchScaleVideoPopularityError,
        match="execution review binding drift",
    ):
        collect_m100_video_popularity_observations(
            release,
            expected_video_count=1,
        )


@pytest.mark.parametrize(
    ("binding_field", "drifted_value"),
    (
        ("objectRef", "video/different-work"),
        ("contentSha256", "sha256:" + "f" * 64),
    ),
)
def test_video_popularity_rejects_review_object_or_content_drift(
    tmp_path: Path,
    binding_field: str,
    drifted_value: str,
) -> None:
    release, rights_path, _receipt_path = _single_video_popularity_fixture(tmp_path)
    rights = json.loads(rights_path.read_text(encoding="utf-8"))
    rights["assets"][0]["independentAssetReview"][binding_field] = drifted_value
    _write(rights_path, rights)

    with pytest.raises(
        ResearchScaleVideoPopularityError,
        match="execution review binding drift",
    ):
        collect_m100_video_popularity_observations(
            release,
            expected_video_count=1,
        )
