"""Immutable release desired-state contract helpers。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.paths import RELEASE_ROOT
from core.release_layout import payload_file
from core.schema import assert_valid

DESIRED_SCHEMA = "quwoquan_data.release_desired_state"


def build_release_contract(
    *,
    release_id: str,
    post_refs: list[str],
    entity_refs: list[str],
    creator_refs: list[str] | None = None,
    tag_refs: list[str] | None = None,
) -> dict[str, Any]:
    """构造 environment-neutral 静态选择集；环境策略属于 run，不进入本合同。"""
    if not release_id:
        raise ValueError("release_id required")
    return {
        "schema": DESIRED_SCHEMA,
        "releaseId": release_id,
        "desiredRefs": {
            "posts": sorted({str(ref) for ref in post_refs}),
            "entities": sorted({str(ref) for ref in entity_refs}),
            "creators": sorted({str(ref) for ref in creator_refs or []}),
            "tags": sorted({str(ref) for ref in tag_refs or []}),
        },
    }


def write_release_contract(
    contract: Mapping[str, Any],
    *,
    release_root: Path | None = None,
) -> Path:
    """create-once 写 desired_state；拒绝非当前合同与覆盖。"""
    if contract.get("schema") != DESIRED_SCHEMA:
        raise ValueError("release contract schema invalid")
    release_id = str(contract.get("releaseId") or "")
    if not release_id:
        raise ValueError("releaseId required")
    forbidden = {"env", "environment", "sampleRatio", "activatedAt", "importRun"}
    present = sorted(forbidden & set(contract))
    if present:
        raise ValueError(f"release must be environment-neutral: {present}")
    assert_valid(
        dict(contract),
        "release",
        "release_desired_state",
        label=f"release_desired_state:{release_id}",
    )
    path = payload_file((release_root or RELEASE_ROOT) / release_id, "desired_state.json")
    payload = (json.dumps(dict(contract), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    if path.exists():
        if path.read_bytes() != payload:
            raise FileExistsError(f"release create-once conflict: {path}")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path
