"""content import report must keep counts.entitiesLoaded even when zero."""

from __future__ import annotations

import pytest

from content.release.environment.importers import assert_import_report_contract


def _base_report(*, entities_loaded: int | None) -> dict:
    counts: dict[str, int] = {"postsLoaded": 4}
    if entities_loaded is not None:
        counts["entitiesLoaded"] = entities_loaded
    return {
        "schema": "quwoquan.content_import_report",
        "status": "dry-run",
        "environment": "gamma",
        "releaseId": "20260804--travel-article-commercial-rights-closure--china--pilot-002",
        "sourceOwner": "qwq_data",
        "manifestDigest": (
            "sha256:fa24047969b8416253e95b422e37f312205441d4195b726975312f3c4737442c"
        ),
        "activationMode": "stage-only",
        "mode": "sync",
        "deletePolicy": "tombstone",
        "counts": counts,
        "postBindings": [],
        "auditEvents": ["DataReleasePrepared"],
        "stageResult": {
            "postsExpected": 4,
            "postsProjected": 4,
            "mediaExpected": 0,
            "mediaProjected": 0,
            "outboxExpected": 4,
            "outboxProjected": 4,
            "projectionVersion": 1,
            "replayed": False,
        },
    }


def test_import_report_accepts_zero_entities_loaded() -> None:
    report = assert_import_report_contract(
        _base_report(entities_loaded=0),
        expected_release_id=(
            "20260804--travel-article-commercial-rights-closure--china--pilot-002"
        ),
        expected_manifest_digest=(
            "sha256:fa24047969b8416253e95b422e37f312205441d4195b726975312f3c4737442c"
        ),
    )
    assert report["counts"]["entitiesLoaded"] == 0


def test_import_report_rejects_missing_entities_loaded() -> None:
    with pytest.raises(ValueError, match="entitiesLoaded") as exc:
        assert_import_report_contract(_base_report(entities_loaded=None))
    assert "$.counts" in str(exc.value)


@pytest.mark.parametrize("status", ["dry-run", "imported", "replay_validated"])
def test_content_import_report_accepts_stage_only_status_contract(status: str) -> None:
    report = _base_report(entities_loaded=0)
    report["status"] = status
    assert_import_report_contract(report, expected_activation_mode="stage-only")


def test_content_import_report_rejects_activation_claim() -> None:
    report = _base_report(entities_loaded=0)
    report.update(status="activated", activationMode="activate")
    with pytest.raises(ValueError, match="activationMode|activated"):
        assert_import_report_contract(report)


def test_content_import_report_requires_activation_mode() -> None:
    report = _base_report(entities_loaded=0)
    report.pop("activationMode")

    with pytest.raises(ValueError, match="activationMode"):
        assert_import_report_contract(report)


def test_content_import_report_rejects_requested_activation_mode_drift() -> None:
    report = _base_report(entities_loaded=0)

    with pytest.raises(RuntimeError, match="activationMode 不一致"):
        assert_import_report_contract(
            report,
            expected_activation_mode="activate",
        )
