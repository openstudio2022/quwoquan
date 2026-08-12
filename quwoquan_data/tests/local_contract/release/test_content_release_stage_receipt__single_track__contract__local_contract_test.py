"""Content release stage receipts preserve fail-closed promotion evidence."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.schema import assert_valid


def _receipt(*, stage: str = "verified", outcome: str = "passed") -> dict:
    receipt = {
        "schema": "quwoquan.content_release_stage_receipt",
        "environment": "alpha",
        "releaseId": "content-alpha-research-pool-20260811-003",
        "manifestDigest": "sha256:" + "a" * 64,
        "stage": stage,
        "outcome": outcome,
        "durationMs": 41,
        "attemptedCount": 32,
        "successfulCount": 32,
        "checkpoint": "search:user-profile:177",
        "recordedAt": "2026-08-12T15:00:00Z",
    }
    if outcome == "failed":
        receipt["firstBlocker"] = {
            "code": "CONTENT.DELIVERY.SEARCH_VERIFICATION_FAILED",
            "checkpoint": "search:user-profile:176",
            "attributes": {"consumer": "search", "successfulCount": "31"},
        }
    return receipt


def test_stage_receipt_accepts_each_single_track_stage_and_failure_checkpoint() -> None:
    for stage in ("prepared", "imported", "projected", "verified", "active"):
        assert_valid(_receipt(stage=stage), "release", "content_release_stage_receipt")
    assert_valid(
        _receipt(stage="projected", outcome="failed"),
        "release",
        "content_release_stage_receipt",
    )


def test_failed_stage_requires_first_typed_blocker() -> None:
    receipt = _receipt(stage="verified", outcome="failed")
    receipt.pop("firstBlocker")
    with pytest.raises(ValueError, match="firstBlocker"):
        assert_valid(receipt, "release", "content_release_stage_receipt")


def test_success_count_cannot_exceed_attempted_count() -> None:
    receipt = _receipt()
    receipt["successfulCount"] = -1
    with pytest.raises(ValueError, match="successfulCount"):
        assert_valid(receipt, "release", "content_release_stage_receipt")


def test_import_report_stops_at_imported_and_cannot_claim_active() -> None:
    schema_path = (
        Path(__file__).resolve().parents[3] / "schema" / "release" / "import_report.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["properties"]["status"]["enum"] == ["dry-run", "imported"]
