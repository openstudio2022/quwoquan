"""Create-once ReliableTask fleet topology bound to one campaign plan."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from core.io import read_json, write_json
from core.schema import assert_valid

from content.execution.campaign_submission import campaign_root
from content.execution.campaign_workspace import CampaignRuntimePaths
from content.execution.identity import validate_execution_id
from content.execution.reliabletask_transport import (
    FrozenReliableTaskFleetBinding,
    ReliableTaskFleetTransport,
    prepare_controller_reliabletask_fleet_transport,
)

CAMPAIGN_FLEET_SCHEMA = "quwoquan_data.content_campaign_fleet_transport_envelope"
CAMPAIGN_FLEET_REF = "fleet_transport_envelope.json"
FleetPreparer = Callable[[], ReliableTaskFleetTransport]


def campaign_fleet_transport_path(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
) -> Path:
    return (
        campaign_root(
            validate_execution_id(root_execution_id),
            root=runtime.campaigns_root,
        )
        / CAMPAIGN_FLEET_REF
    )


def _validate_envelope(
    value: Mapping[str, object],
    *,
    root_execution_id: str,
    plan_digest: str,
) -> FrozenReliableTaskFleetBinding:
    payload = dict(value)
    assert_valid(
        payload,
        "execution",
        "content_campaign_fleet_transport_envelope",
        label=f"campaign fleet transport:{root_execution_id}",
    )
    if payload.get("schema") != CAMPAIGN_FLEET_SCHEMA:
        raise ValueError("campaign fleet transport schema mismatch")
    binding = FrozenReliableTaskFleetBinding.from_document(
        {key: value for key, value in payload.items() if key != "schema"}
    )
    if binding.root_execution_id != root_execution_id:
        raise ValueError("campaign fleet transport root execution mismatch")
    if binding.plan_digest != plan_digest:
        raise ValueError("campaign fleet transport plan digest drift")
    return binding


def resolve_campaign_fleet_transport(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    *,
    plan_digest: str,
    preparer: FleetPreparer = prepare_controller_reliabletask_fleet_transport,
) -> FrozenReliableTaskFleetBinding:
    root_id = validate_execution_id(root_execution_id)
    path = campaign_fleet_transport_path(runtime, root_id)
    if path.is_file():
        payload = read_json(path)
        if not isinstance(payload, dict):
            raise TypeError("campaign fleet transport envelope must be an object")
        return _validate_envelope(
            payload,
            root_execution_id=root_id,
            plan_digest=plan_digest,
        )
    binding = FrozenReliableTaskFleetBinding.create(
        root_execution_id=root_id,
        plan_digest=plan_digest,
        transport=preparer(),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, {"schema": CAMPAIGN_FLEET_SCHEMA, **binding.document()})
    return _validate_envelope(
        read_json(path),
        root_execution_id=root_id,
        plan_digest=plan_digest,
    )


__all__ = [
    "CAMPAIGN_FLEET_REF",
    "CAMPAIGN_FLEET_SCHEMA",
    "campaign_fleet_transport_path",
    "resolve_campaign_fleet_transport",
]
