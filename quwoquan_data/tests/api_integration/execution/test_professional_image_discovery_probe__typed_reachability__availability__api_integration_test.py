from __future__ import annotations

import json
from pathlib import Path

import pytest

from content.source.professional_image_discovery import (
    create_professional_image_discovery_plan,
)
from content.source import professional_image_discovery_probe as probe


def test_professional_image_discovery_probe_keeps_dns_distinct_from_access_control(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, plan_path = create_professional_image_discovery_plan(
        entities=["西湖"],
        category="风光",
        season="秋季",
        style="纪实",
        viewpoint="航拍",
        popularity="热门",
        output_root=tmp_path / "plans",
    )

    def fake_probe(url: str, *, timeout_seconds: float) -> dict[str, object]:
        assert timeout_seconds == 3.0
        if "pinterest.com" in url:
            return {
                "reachable": False,
                "statusCode": 403,
                "errorCode": "access_controlled",
                "errorDetail": "HTTP 403",
            }
        return {
            "reachable": False,
            "statusCode": None,
            "errorCode": "dns_unavailable",
            "errorDetail": "gaierror",
        }

    monkeypatch.setattr(probe, "_probe_url", fake_probe)
    receipt, receipt_path = probe.probe_professional_image_discovery_plan(
        plan_path,
        output_root=tmp_path / "probes",
        timeout_seconds=3.0,
    )

    assert receipt_path.is_file()
    assert receipt["planDigest"] == plan["planDigest"]
    assert receipt["overallReady"] is False
    assert [row["errorCode"] for row in receipt["probes"]] == [
        "access_controlled",
        "dns_unavailable",
        "dns_unavailable",
        "dns_unavailable",
    ]
    assert receipt["providerProbeCounts"] == [
        {"provider": "pinterest", "plannedProbeCount": 1, "reachableProbeCount": 0},
        {"provider": "tuchong", "plannedProbeCount": 1, "reachableProbeCount": 0},
        {
            "provider": "wikimedia_commons",
            "plannedProbeCount": 1,
            "reachableProbeCount": 0,
        },
        {"provider": "openverse", "plannedProbeCount": 1, "reachableProbeCount": 0},
    ]


def test_professional_image_discovery_probe_rejects_plan_tampering(
    tmp_path: Path,
) -> None:
    _plan, plan_path = create_professional_image_discovery_plan(
        entities=["西湖"],
        category="风光",
        season="秋季",
        style="纪实",
        viewpoint="航拍",
        popularity="热门",
        output_root=tmp_path / "plans",
    )
    document = json.loads(plan_path.read_text(encoding="utf-8"))
    document["candidates"][0]["queryText"] = "tampered"
    plan_path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(probe.ProfessionalImageDiscoveryProbeError, match="digest mismatch"):
        probe.probe_professional_image_discovery_plan(
            plan_path,
            output_root=tmp_path / "probes",
            timeout_seconds=3.0,
        )
