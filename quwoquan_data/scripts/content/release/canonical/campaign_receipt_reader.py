"""Read-only neutral boundary for canonical campaign lane receipts."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.io import read_json
from core.schema import assert_valid
from content.execution.identity import validate_execution_id


def lane_receipt_path(
    root_execution_id: str, carrier: str, phase: str, *, root: Path
) -> Path:
    if carrier not in {"homepage", "article", "image", "video"}:
        raise ValueError(f"campaign carrier is invalid: {carrier}")
    if phase not in {"review", "publish"}:
        raise ValueError(f"campaign receipt phase is invalid: {phase}")
    return root / validate_execution_id(root_execution_id) / "receipts" / f"{carrier}-{phase}.json"


def load_lane_receipt(
    root_execution_id: str, carrier: str, phase: str, *, root: Path
) -> dict[str, Any]:
    path = lane_receipt_path(root_execution_id, carrier, phase, root=root)
    payload = read_json(path)
    assert_valid(
        payload,
        "execution",
        "content_campaign_lane_receipt",
        label=f"campaign lane receipt:{path.name}",
    )
    if not isinstance(payload, Mapping):
        raise TypeError(f"campaign lane receipt must be an object: {path}")
    if (
        str(payload.get("rootExecutionId") or "") != validate_execution_id(root_execution_id)
        or str(payload.get("carrier") or "") != carrier
        or str(payload.get("phase") or "") != phase
    ):
        raise ValueError(f"campaign lane receipt identity drift: {path}")
    return dict(payload)


__all__ = ["lane_receipt_path", "load_lane_receipt"]
