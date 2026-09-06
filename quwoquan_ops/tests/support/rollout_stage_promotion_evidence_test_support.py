from __future__ import annotations

import datetime as dt
from typing import Any

from quwoquan_ops.cli.prod.rollout_stage_promotion_evidence import canonical_digest


DIGEST = "sha256:" + ("9" * 64)
THRESHOLDS = {
    "canary": (0, 0, {"android": 2, "ios": 2, "web": 2}, 120),
    "5": (1800, 1000, {"android": 30, "ios": 10, "web": 10}, 0),
    "20": (7200, 5000, {"android": 140, "ios": 30, "web": 30}, 0),
    "50": (86400, 20000, {"android": 800, "ios": 100, "web": 100}, 0),
    "100": (0, 0, {"android": 1, "ios": 1, "web": 1}, 0),
}


def promotion_evidence(
    *,
    candidate_id: str,
    artifact_digest: str,
    stage: str,
) -> dict[str, Any]:
    duration, requests, installation_counts, synthetic = THRESHOLDS[stage]
    started = dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc)
    ended = started + dt.timedelta(seconds=duration)
    platform_names = sorted(installation_counts)
    platform_requests = {
        platform: 0 for platform in platform_names
    }
    if requests:
        platform_requests[platform_names[0]] = requests
    value: dict[str, Any] = {
        "schema": "prod-rollout-stage-promotion-evidence",
        "authority": "protected-prod-runner",
        "releaseCompositionId": candidate_id,
        "artifactDigest": artifact_digest,
        "campaignId": "release-test-campaign",
        "routingPolicyDigest": DIGEST,
        "stage": stage,
        "observedFrom": started.isoformat().replace("+00:00", "Z"),
        "observedUntil": ended.isoformat().replace("+00:00", "Z"),
        "durationSeconds": duration,
        "syntheticRequestCount": synthetic,
        "candidateRequestCount": requests,
        "uniqueCandidateInstallations": sum(installation_counts.values()),
        "platforms": {
            platform: {
                "candidateRequestCount": platform_requests[platform],
                "uniqueCandidateInstallations": installation_counts[platform],
            }
            for platform in platform_names
        },
        "audiences": {
            dimension: {
                "mode": "all",
                "observations": [
                    {
                        "value": "top-segment",
                        "top": True,
                        "candidateRequestCount": requests,
                        "uniqueCandidateInstallations": sum(
                            installation_counts.values()
                        ),
                    },
                    {
                        "value": "unknown",
                        "top": False,
                        "candidateRequestCount": 0,
                        "uniqueCandidateInstallations": 0,
                    },
                ],
            }
            for dimension in ("regions", "carriers")
        },
        "supportedAppCoverage": {
            "mode": "supported",
            "complete": stage == "100",
        },
        "source": {
            "authority": "prod-observability-plane",
            "queryDigest": DIGEST,
            "receiptDigest": DIGEST,
            "generatedAt": ended.isoformat().replace("+00:00", "Z"),
        },
    }
    value["evidenceDigest"] = canonical_digest(value)
    return value
