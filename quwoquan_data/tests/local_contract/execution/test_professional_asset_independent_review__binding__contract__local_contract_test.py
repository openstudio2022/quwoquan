"""Professional review must resolve each acquisition receipt from its canonical root."""
from __future__ import annotations

import sys
import json
from pathlib import Path
from types import SimpleNamespace


DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
for path in (DATA_ROOT / "scripts", DATA_ROOT / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from content.execution.controller.professional_asset_independent_review import (  # noqa: E402
    _acquisition_receipt_path,
    _professional_asset_review_candidates,
    run_professional_asset_independent_reviews,
)
from core.paths import OUTPUT_ROOT  # noqa: E402


def test_professional_receipt_roots_match_acquisition_cli_layout() -> None:
    receipt_ref = "receipts/" + ("a" * 64) + ".json"

    assert _acquisition_receipt_path("image", receipt_ref) == (
        OUTPUT_ROOT / "data/local/workspace/source-acquisition" / receipt_ref
    )
    assert _acquisition_receipt_path("video", receipt_ref) == (
        OUTPUT_ROOT / "data/local/workspace/source-acquisition/video" / receipt_ref
    )


def test_missing_materialized_manifest_has_no_professional_review_candidate(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from content.execution.controller import professional_asset_independent_review
    from content.post import object_index

    ctx = SimpleNamespace(execution_id="20260808--travel-video-m1--china--scale-095")
    object_dir = tmp_path / "post"
    object_dir.mkdir()
    monkeypatch.setattr(
        professional_asset_independent_review,
        "execution_root",
        lambda _execution_id: tmp_path,
    )
    monkeypatch.setattr(
        object_index,
        "content_object_dir",
        lambda *_args: object_dir,
    )

    assert _professional_asset_review_candidates(ctx, "video-ref") == []


def test_homepage_professional_asset_is_resolved_from_entity_manifest(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from content.execution.controller import professional_asset_independent_review

    ctx = SimpleNamespace(execution_id="20260808--travel-homepage-m1--china--scale-096")
    object_ref = "/entity/地点/景区/南浔古镇"
    object_dir = tmp_path / "entities/地点/景区/南浔古镇"
    asset_dir = object_dir / "assets"
    source_dir = tmp_path / "sources/nanxun/assets"
    asset_dir.mkdir(parents=True)
    source_dir.mkdir(parents=True)
    (asset_dir / "cover.jpg").write_bytes(b"not-decoded-in-this-test")
    (source_dir / "cover.jpg").write_bytes(b"same-source")
    source_ref = "sources/nanxun/assets/cover.jpg"
    source_sha = "sha256:" + ("a" * 64)
    (object_dir / "manifest.json").write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "assetId": "homepage-cover",
                        "fileName": "cover.jpg",
                        "sourceAssetId": "source-cover",
                        "sourceAssetRef": source_ref,
                    }
                ]
            }
        )
    )
    (source_dir / "index.json").write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "sourceAssetId": "source-cover",
                        "fileName": "cover.jpg",
                        "acquisitionReceiptRef": "receipts/" + ("b" * 64) + ".json",
                        "professionalAssetId": "professional-cover",
                        "professionalContentSha256": source_sha,
                    }
                ]
            }
        )
    )
    monkeypatch.setattr(
        professional_asset_independent_review,
        "execution_root",
        lambda _execution_id: tmp_path,
    )
    monkeypatch.setattr(
        "content.release.canonical.object_transaction._image_dimensions",
        lambda _path: (1600, 900, "image/jpeg"),
    )

    candidates = _professional_asset_review_candidates(ctx, object_ref)

    assert candidates == [
        {
            "assetKind": "image",
            "assetId": "professional-cover",
            "contentSha256": source_sha,
            "acquisitionReceiptPath": (
                OUTPUT_ROOT
                / "data/local/workspace/source-acquisition/receipts"
                / (("b" * 64) + ".json")
            ).as_posix(),
        }
    ]


def test_blocked_professional_review_is_reused_as_quality_feedback(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from content.execution.controller import professional_asset_independent_review
    from content.post import object_index
    from core.data_issue import DataIssueCode, DataRecoveryAction

    ctx = SimpleNamespace(execution_id="20260808--travel-image-m1--china--scale-094")
    candidate = {
        "assetKind": "image",
        "assetId": "professional-asset-001",
        "contentSha256": "sha256:" + ("a" * 64),
        "acquisitionReceiptPath": "/tmp/acquisition.json",
    }
    receipt = {
        "reviewDecision": "blocked",
        "judgment": {"findings": ["画面主体与目标景点不一致"]},
    }
    reviewer = SimpleNamespace(
        model_id="auto",
        family=SimpleNamespace(value="auto"),
        parameters={},
    )
    monkeypatch.setattr(
        professional_asset_independent_review,
        "_professional_asset_review_candidates",
        lambda *_args: [candidate],
    )
    monkeypatch.setattr(
        professional_asset_independent_review,
        "_existing_asset_review_decision",
        lambda *_args, **_kwargs: ("blocked", receipt),
    )
    monkeypatch.setattr(
        object_index,
        "content_object_dir",
        lambda *_args: tmp_path / "object",
    )
    monkeypatch.setattr(
        "content.execution.model_contract.execution_model_pair_for_execution",
        lambda _execution_id: SimpleNamespace(reviewer=reviewer),
    )

    issues = run_professional_asset_independent_reviews(ctx, ["杭州西湖_image"])

    assert len(issues) == 1
    assert issues[0].code is DataIssueCode.QUALITY_FAILED
    assert issues[0].recovery is DataRecoveryAction.REWIND_COMPOSE
    assert "画面主体与目标景点不一致" in issues[0].message
