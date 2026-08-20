"""Read and revalidate one immutable campaign request envelope."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core import paths
from core.io import read_json
from core.schema import assert_valid

from content.execution.campaign.lane import normalize_active_carriers, normalize_workloads
from content.execution.identity import parse_execution_id
from content.execution.planning.semantic_preflight_admission import (
    validate_semantic_preflight_binding_at,
)


def load_campaign_envelope(
    path: Path,
    *,
    semantic_preflight_output_root: Path | None = None,
) -> dict[str, Any]:
    from content.execution.campaign.request_envelope import _sha256

    payload = read_json(path)
    if not isinstance(payload, dict):
        raise TypeError("campaign envelope must be an object")
    assert_valid(
        payload,
        "execution",
        "content_campaign_request_envelope",
        label=f"campaign envelope:{path}",
    )
    stable = {
        key: value
        for key, value in payload.items()
        if key != "requestDigest"
    }
    if payload.get("requestDigest") != _sha256(stable):
        raise ValueError("campaign envelope requestDigest drift")
    active = normalize_active_carriers(payload["activeCarriers"])
    workloads = normalize_workloads(payload["workloads"], active_carriers=active)
    carrier = str(payload["carrier"])
    if (
        carrier not in active
        or int(payload["quota"]) != workloads[carrier]
        or str(payload["rootExecutionId"])
        != str(payload["executionId"] if carrier == active[0] else payload["rootExecutionId"])
    ):
        raise ValueError("campaign envelope active workload drift")
    root = parse_execution_id(str(payload["rootExecutionId"]))
    execution = parse_execution_id(str(payload["executionId"]))
    if root.content_type.value != active[0] or execution.content_type.value != carrier:
        raise ValueError("campaign envelope root/carrier identity drift")
    binding = payload.get("semanticPreflightReceipt")
    if binding is not None:
        validate_semantic_preflight_binding_at(
            binding,
            semantic_selection_id=str(payload["semanticSelectionId"]),
            admitted_at=str(payload["frozenAt"]),
            output_root=(semantic_preflight_output_root or paths.OUTPUT_ROOT),
        )
    return payload


__all__ = ["load_campaign_envelope"]
