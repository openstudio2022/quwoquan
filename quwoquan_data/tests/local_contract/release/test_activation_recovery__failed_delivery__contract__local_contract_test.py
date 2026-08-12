from __future__ import annotations

import json
from pathlib import Path

import pytest

from content.release.environment.activation_recovery import (
    ContentDeliveryRecoveryError,
    restore_after_delivery_failure,
)


_DIGEST = "sha256:" + "a" * 64


def _write(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def test_delivery_failure_replays_only_a_verified_previous_release(
    tmp_path: Path,
) -> None:
    previous = "release-previous"
    _write(
        tmp_path
        / "env/alpha/runs/data-release"
        / previous
        / "verify-001/release-readiness.json",
        {
            "schema": "quwoquan_data.environment_release_readiness",
            "environment": "alpha",
            "releaseId": previous,
            "manifestDigest": _DIGEST,
            "verifyRunId": "verify-001",
            "verifiedAt": "2026-08-11T00:00:00Z",
            "passed": True,
        },
    )
    import_report = _write(
        tmp_path / "candidate-import.json",
        {
            "auditEvents": [
                "DataReleasePrepared",
                "DataReleaseActivated",
                f"PreviousDataRelease|{previous}|{_DIGEST}",
            ]
        },
    )
    replayed: list[str] = []
    result = restore_after_delivery_failure(
        output_root=tmp_path,
        environment="alpha",
        failed_release_id="release-candidate",
        import_report_path=import_report,
        replay_previous=lambda release: replayed.append(release.release_id),
    )
    assert result.release_id == previous
    assert replayed == [previous]


def test_delivery_failure_without_previous_verified_release_fails_closed(
    tmp_path: Path,
) -> None:
    import_report = _write(
        tmp_path / "candidate-import.json",
        {"auditEvents": ["DataReleasePrepared", "DataReleaseActivated"]},
    )
    with pytest.raises(
        ContentDeliveryRecoveryError,
        match="DATA.DELIVERY_RESTORE_UNAVAILABLE",
    ):
        restore_after_delivery_failure(
            output_root=tmp_path,
            environment="alpha",
            failed_release_id="release-candidate",
            import_report_path=import_report,
            replay_previous=lambda _release: pytest.fail("must not replay"),
        )
