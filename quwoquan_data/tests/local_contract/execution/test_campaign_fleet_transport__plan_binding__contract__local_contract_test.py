# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
from __future__ import annotations

from pathlib import Path

import pytest
from content.execution.campaign import fleet_transport as campaign_fleet_transport
from content.execution.campaign.workspace import CampaignRuntimePaths
from content.execution.queue.reliabletask.transport import ReliableTaskFleetTransport
from core.io import read_json

ROOT_ID = "20260805--travel-homepage-m3--china--scale-016"


def _runtime(tmp_path: Path) -> CampaignRuntimePaths:
    output_root = tmp_path / "output"
    return CampaignRuntimePaths(
        repo_root=tmp_path / "repo",
        output_root=output_root,
        publish_root=tmp_path / "publish",
        campaigns_root=(
            output_root / "data/local/workspace/content-campaign-submissions"
        ),
        workspaces_root=output_root / "data/local/cache/campaign-workspaces",
    )


def test_campaign_fleet_transport_is_create_once_and_plan_bound(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    transport = ReliableTaskFleetTransport(
        target="data-execution-local",
        mongo_uri="mongodb://127.0.0.1:27117/quwoquan",
        redis_addr="127.0.0.1:6389",
    )
    calls = 0

    def prepare() -> ReliableTaskFleetTransport:
        nonlocal calls
        calls += 1
        return transport

    first = campaign_fleet_transport.resolve_campaign_fleet_transport(
        runtime,
        ROOT_ID,
        plan_digest="sha256:" + "a" * 64,
        preparer=prepare,
    )
    second = campaign_fleet_transport.resolve_campaign_fleet_transport(
        runtime,
        ROOT_ID,
        plan_digest="sha256:" + "a" * 64,
        preparer=lambda: pytest.fail("resume must not resolve topology again"),
    )

    assert first == second
    assert first.transport == transport
    assert calls == 1
    envelope = read_json(
        campaign_fleet_transport.campaign_fleet_transport_path(runtime, ROOT_ID)
    )
    assert envelope["bindingDigest"] == first.binding_digest

    with pytest.raises(ValueError, match="plan digest drift"):
        campaign_fleet_transport.resolve_campaign_fleet_transport(
            runtime,
            ROOT_ID,
            plan_digest="sha256:" + "b" * 64,
            preparer=lambda: pytest.fail("drift must not resolve topology"),
        )
