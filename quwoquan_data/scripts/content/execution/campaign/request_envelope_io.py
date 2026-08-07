"""Read and revalidate one immutable campaign request envelope."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core import paths
from core.io import read_json
from core.schema import assert_valid

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
        if key not in {"requestDigest", "frozenAt"}
    }
    if payload.get("requestDigest") != _sha256(stable):
        raise ValueError("campaign envelope requestDigest drift")
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
