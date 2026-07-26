"""Homepage reviewer response and canonical evidence have distinct contracts."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core.schema import assert_valid
from core.prompt_render import render
from content.homepage.homepage_review import (
    apply_independent_homepage_review,
    homepage_asset_file_evidence,
    homepage_media_review_dispositions,
)


EXECUTION_ID = "20260713--travel-homepage-coverage--test-region-a--pilot-901"
OBJECT_REF = "/entity/地点/景区/测试实体甲"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _review_dir(tmp_path: Path) -> Path:
    review_dir = tmp_path / "5.review"
    _write_json(review_dir / "review.json", {"decision": "approved", "issues": []})
    _write_json(
        review_dir / "attestation.json",
        {
            "schema": "quwoquan_data.review_attestation",
            "stage": "5.review",
            "executionId": EXECUTION_ID,
            "executionBinding": "frozen",
            "objectRef": OBJECT_REF,
            "decision": "approved",
            "deterministicGate": {"status": "passed", "issues": []},
            "independentReviewer": {
                "status": "pending",
                "provider": "cursor_sdk",
                "model": "reviewer",
                "modelFamily": "pending",
                "runId": "review_pending",
                "resultHash": None,
            },
            "mediaRefReview": {"status": "passed", "issues": []},
            "repair": {"status": "not_required"},
            "finalizationRef": "5.review/finalization_report.json",
            "evidenceIndexRef": "5.review/evidence_index.json",
        },
    )
    _write_json(
        review_dir / "evidence_index.json",
        {
            "schema": "quwoquan_data.evidence_index",
            "stage": "5.review",
            "executionId": EXECUTION_ID,
            "executionBinding": "frozen",
            "objectRef": OBJECT_REF,
            "evidence": [],
        },
    )
    return review_dir


def test_homepage_independent_review__binds_typed_response_to_canonical_evidence__local_contract(
    tmp_path: Path,
) -> None:
    review_dir = _review_dir(tmp_path)
    response = {
        "schema": "quwoquan_data.homepage_reviewer_response",
        "executionId": EXECUTION_ID,
        "objectRef": OBJECT_REF,
        "decision": "approved",
        "issues": [],
        "findings": ["正文、图片处置与来源证据已独立核对。"],
    }

    assert apply_independent_homepage_review(
        review_dir=review_dir,
        provider="cursor_sdk",
        model="grok-4.5",
        model_family="grok",
        run_id="review-run-001",
        result_payload=response,
    ) == []

    reviewer_result = json.loads((review_dir / "reviewer_result.json").read_text(encoding="utf-8"))
    assert reviewer_result["modelFamily"] == "grok"
    assert reviewer_result["verdict"] == "passed"
    assert_valid(reviewer_result, "content", "reviewer_result")
    attestation = json.loads((review_dir / "attestation.json").read_text(encoding="utf-8"))
    assert attestation["independentReviewer"]["modelFamily"] == "grok"
    assert_valid(attestation, "content", "review_attestation")


def test_homepage_independent_review__rejects_canonical_result_shaped_agent_reply__local_contract(
    tmp_path: Path,
) -> None:
    review_dir = _review_dir(tmp_path)
    wrong_response = {
        "schema": "quwoquan_data.reviewer_result",
        "executionId": EXECUTION_ID,
        "objectRef": OBJECT_REF,
        "decision": "approved",
        "issues": [],
        "findings": ["wrong schema"],
    }

    issues = apply_independent_homepage_review(
        review_dir=review_dir,
        provider="cursor_sdk",
        model="gpt-5.5",
        model_family="gpt",
        run_id="review-run-002",
        result_payload=wrong_response,
    )

    assert issues
    assert not (review_dir / "reviewer_result.json").exists()


def test_homepage_independent_review__rejects_synthetic_contract_output_run_id__local_contract(
    tmp_path: Path,
) -> None:
    review_dir = _review_dir(tmp_path)
    response = {
        "schema": "quwoquan_data.homepage_reviewer_response",
        "executionId": EXECUTION_ID,
        "objectRef": OBJECT_REF,
        "decision": "approved",
        "issues": [],
        "findings": ["审查结论完整。"],
    }

    issues = apply_independent_homepage_review(
        review_dir=review_dir,
        provider="cursor_sdk",
        model="gpt-5.5",
        model_family="gpt",
        run_id=f"contract-output:{EXECUTION_ID}",
        result_payload=response,
    )

    assert issues == [f"{review_dir}: independent reviewer must bind a real Cursor SDK runId"]
    assert not (review_dir / "reviewer_result.json").exists()


def test_homepage_independent_review__group_members_are_gallery_only__local_contract() -> None:
    dispositions = homepage_media_review_dispositions(
        {
            "imagePlacements": [
                {"assetId": "cover", "role": "cover", "placementType": "lead"},
                {"assetId": "inline", "role": "inline", "placementType": "inline"},
                {"assetId": "gallery", "role": "related", "placementType": "groupMember"},
            ]
        }
    )

    assert [row["expected"] for row in dispositions] == [
        "cover_frontmatter_only",
        "bound_inline_figure",
        "related_gallery_only",
    ]
    prompt = render(
        "homepage_independent_review",
        task_vars={
            "object_ref": OBJECT_REF,
            "object_dir": "/tmp/object",
            "output_path": "/tmp/response.json",
            "media_policy": '{"rightsEnforcementMode":"audit_only","assets":[{"assetId":"gallery","expected":"related_gallery_only"}]}',
        },
    )
    assert "related_gallery_only" in prompt
    assert "禁止以" in prompt
    assert "audit_only" in prompt
    assert "不得进入 issues" in prompt


def test_homepage_independent_review__uses_deterministic_asset_file_evidence__local_contract(
    tmp_path: Path,
) -> None:
    object_dir = tmp_path / "entity"
    asset_path = object_dir / "assets" / "cover.jpg"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_bytes(b"image-bytes")

    evidence = homepage_asset_file_evidence(
        object_dir,
        {
            "assets": [
                {"assetId": "cover", "fileName": "cover.jpg"},
                {"assetId": "missing", "fileName": "missing.jpg"},
            ]
        },
    )

    assert evidence[0]["exists"] is True
    assert str(evidence[0]["sha256"])
    assert evidence[1]["exists"] is False
    assert evidence[1]["sha256"] == ""
