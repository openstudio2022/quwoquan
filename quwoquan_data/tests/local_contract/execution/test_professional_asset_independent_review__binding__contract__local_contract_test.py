"""Professional review must resolve each acquisition receipt from its canonical root."""
from __future__ import annotations

import sys
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
