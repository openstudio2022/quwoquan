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


def _import_report(**overrides: object) -> dict:
    report = {
        "schema": "quwoquan.content_import_report",
        "status": "staged",
        "phase": "stage",
        "candidateRevision": 1788678560042,
        "environment": "alpha",
        "releaseId": "content-alpha-research-pool-20260811-003",
        "sourceOwner": "qwq_data",
        "manifestDigest": "sha256:" + "a" * 64,
        "mode": "sync",
        "deletePolicy": "tombstone",
        "counts": {"postsLoaded": 2, "entitiesLoaded": 1, "postsStaged": 2},
        "postBindings": [],
        "auditEvents": ["DataReleasePrepared"],
        "previousReleaseId": "",
        "previousManifestDigest": "",
        "previousRevision": 0,
    }
    report.update(overrides)
    return report


def test_import_report_phases_are_single_track_and_only_activate_claims_revision() -> None:
    schema_path = (
        Path(__file__).resolve().parents[3] / "schema" / "release" / "import_report.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["properties"]["status"]["enum"] == [
        "dry-run", "staged", "verified", "active", "imported",
    ]
    assert_valid(_import_report(), "release", "import_report")
    assert_valid(
        _import_report(
            status="verified", phase="verify",
            candidatePostIds=["data_post_a"], candidateSourceHashes=["sha256:" + "b" * 64],
        ),
        "release",
        "import_report",
    )
    assert_valid(
        _import_report(status="active", phase="activate", revision=3, sourceVersion=1788678560099),
        "release",
        "import_report",
    )
    # staged/verified 候选回执不得携带 active pointer revision。
    with pytest.raises(ValueError):
        assert_valid(_import_report(revision=3, sourceVersion=1), "release", "import_report")
    # active 回执必须绑定 stage 分配的 candidateRevision 与 activate phase。
    with pytest.raises(ValueError):
        assert_valid(
            _import_report(status="active", phase="stage", revision=3, sourceVersion=1),
            "release",
            "import_report",
        )
    with pytest.raises(ValueError):
        assert_valid(
            _import_report(status="active", revision=3, sourceVersion=1, candidateRevision=None),
            "release",
            "import_report",
        )
