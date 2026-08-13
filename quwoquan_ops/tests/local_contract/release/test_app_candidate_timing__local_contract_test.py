from __future__ import annotations

from quwoquan_ops.ci.render_app_candidate_timing import calculate


SPEC_REF = "specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#sit-001"


def _job(name: str, started: str, completed: str) -> dict[str, object]:
    return {
        "name": name,
        "conclusion": "success",
        "started_at": started,
        "completed_at": completed,
        "steps": [],
    }


def test_app_critical_path_uses_longest_real_shard_and_oci_ready_step() -> None:
    assert SPEC_REF
    jobs = []
    for platform, seconds in {
        "Android": 120,
        "iOS": 180,
        "Web": 90,
        "macOS": 120,
    }.items():
        for index, environment in enumerate(("alpha", "beta", "gamma", "prod")):
            duration = seconds + index
            jobs.append(
                _job(
                    f"caller / App package shard / {platform} / {environment}",
                    "2026-07-28T00:00:00Z",
                    f"2026-07-28T00:0{duration // 60}:{duration % 60:02d}Z",
                )
            )
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

    result = calculate(jobs)

    assert result["machine_critical_path_seconds"] == 243
    assert result["aggregate_seconds"] == 60
    assert result["shard_seconds"]["ios/prod"] == 183
    assert result["candidate_ready_at"] == "2026-07-28T00:04:30Z"
