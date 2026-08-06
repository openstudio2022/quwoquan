"""Asset review CLI delegates to the provenance validator without selectors."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest
from content.execution import review_asset
from content.source.independent_asset_review import IndependentAssetReviewError
from core.io import write_json


def _args(tmp_path: Path) -> Namespace:
    judgment = tmp_path / "judgment.json"
    write_json(
        judgment,
        {
            "rightsStatus": "unverified",
            "authorizationRequired": True,
            "distributionDecision": "research_allowed",
        },
    )
    return Namespace(
        acquisition_receipt=str(tmp_path / "acquisition-receipt.json"),
        asset_kind="image",
        asset_id="pin-001",
        execution_manifest=str(tmp_path / "execution-manifest.json"),
        author_evidence=str(tmp_path / "author.json"),
        reviewer_evidence=str(tmp_path / "reviewer.json"),
        object_ref="posts/image/九寨沟清晨",
        judgment=str(judgment),
    )


def test_review_asset_passes_only_existing_evidence_paths_to_validator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, object] = {}
    receipt_path = tmp_path / "receipts/asset-review-a.json"

    def write_receipt(**kwargs: object) -> tuple[dict[str, object], Path]:
        captured.update(kwargs)
        return (
            {
                "reviewId": "asset-review-a",
                "reviewDecision": "accepted",
                "assetKind": "image",
                "objectRef": "posts/image/九寨沟清晨",
                "receiptDigest": "sha256:" + "a" * 64,
            },
            receipt_path,
        )

    monkeypatch.setattr(
        review_asset,
        "write_independent_asset_review_receipt",
        write_receipt,
    )
    review_asset.handle_review_asset(_args(tmp_path))

    assert captured == {
        "acquisition_receipt_path": (tmp_path / "acquisition-receipt.json").resolve(),
        "asset_kind": "image",
        "asset_id": "pin-001",
        "execution_manifest_path": (tmp_path / "execution-manifest.json").resolve(),
        "author_evidence_path": (tmp_path / "author.json").resolve(),
        "reviewer_evidence_path": (tmp_path / "reviewer.json").resolve(),
        "object_ref": "posts/image/九寨沟清晨",
        "judgment": {
            "rightsStatus": "unverified",
            "authorizationRequired": True,
            "distributionDecision": "research_allowed",
        },
    }
    assert "independent_asset_review_result" in capsys.readouterr().out


def test_review_asset_preserves_typed_provenance_rejection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        review_asset,
        "write_independent_asset_review_receipt",
        lambda **_kwargs: (_ for _ in ()).throw(
            IndependentAssetReviewError("author/reviewer identity drift")
        ),
    )
    with pytest.raises(SystemExit, match="GATE_BLOCK.*identity drift"):
        review_asset.handle_review_asset(_args(tmp_path))

