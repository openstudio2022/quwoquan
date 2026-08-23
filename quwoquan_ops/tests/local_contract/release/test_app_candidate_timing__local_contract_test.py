from __future__ import annotations

import pytest

from quwoquan_ops.ci.render_app_candidate_timing import calculate

SPEC_REF = "specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001"
PRODUCT_DURATIONS = {
    "android-nonprod-apk": 120,
    "android-prod-apk": 150,
    "ios-nonprod-app": 180,
    "ios-prod-app": 183,
    "web-shared": 90,
}


def _job(name: str, started: str, completed: str) -> dict[str, object]:
    return {
        "name": name,
        "conclusion": "success",
        "started_at": started,
        "completed_at": completed,
        "steps": [],
    }


def _jobs() -> list[dict[str, object]]:
    jobs = [
        _job(
            f"caller / App package product / {product_id}",
            "2026-07-28T00:00:00Z",
            f"2026-07-28T00:0{seconds // 60}:{seconds % 60:02d}Z",
        )
        for product_id, seconds in PRODUCT_DURATIONS.items()
    ]
    jobs.append(
        {
            **_job(
                "caller / App candidate OCI / aggregate",
                "2026-07-28T00:03:30Z",
                "",
            ),
            "conclusion": None,
            "steps": [
                {
                    "name": "Expose immutable App OCI identity",
                    "conclusion": "success",
                    "started_at": "2026-07-28T00:04:00Z",
                    "completed_at": "2026-07-28T00:04:30Z",
                }
            ],
        }
    )
    return jobs


def test_app_critical_path_uses_exactly_five_products_and_oci_ready_step() -> None:
    assert SPEC_REF

    result = calculate(_jobs())

    assert result["machine_critical_path_seconds"] == 243
    assert result["aggregate_seconds"] == 60
    assert result["shard_seconds"] == PRODUCT_DURATIONS
    assert result["candidate_ready_at"] == "2026-07-28T00:04:30Z"


def test_app_critical_path_rejects_missing_baseline_product() -> None:
    assert SPEC_REF
    jobs = [
        job
        for job in _jobs()
        if "App package product / ios-prod-app" not in str(job["name"])
    ]

    with pytest.raises(ValueError, match="ios-prod-app"):
        calculate(jobs)


def test_app_critical_path_ignores_unrelated_legacy_macos_job() -> None:
    assert SPEC_REF
    jobs = _jobs()
    jobs.append(
        _job(
            "caller / App package shard / macOS / prod",
            "2026-07-28T00:00:00Z",
            "2026-07-28T00:09:59Z",
        )
    )

    result = calculate(jobs)

    assert result["machine_critical_path_seconds"] == 243
    assert set(result["shard_seconds"]) == set(PRODUCT_DURATIONS)
