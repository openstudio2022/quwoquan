"""Immutable release desired-state contract helpers。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from core.paths import RELEASE_ROOT
from core.release_layout import payload_file

DESIRED_SCHEMA = "quwoquan_data.release_desired_state/1"


def build_release_contract(
    *,
    release_id: str,
    post_refs: list[str],
    entity_refs: list[str],
    actions: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """构造 environment-neutral 静态选择集；环境策略属于 run，不进入本合同。"""
    if not release_id:
        raise ValueError("release_id required")
    return {
        "schemaVersion": DESIRED_SCHEMA,
        "releaseId": release_id,
        "desiredRefs": {
            "posts": sorted({str(ref) for ref in post_refs}),
            "entities": sorted({str(ref) for ref in entity_refs}),
        },
        "actions": [dict(row) for row in actions or []],
    }


def write_release_contract(
    contract: Mapping[str, Any],
    *,
    release_root: Path | None = None,
) -> Path:
    """create-once 写 desired_state；拒绝 legacy env contract 与覆盖。"""
    if contract.get("schemaVersion") != DESIRED_SCHEMA:
        raise ValueError("legacy release contract rejected")
    release_id = str(contract.get("releaseId") or "")
    if not release_id:
        raise ValueError("releaseId required")
    forbidden = {"env", "environment", "sampleRatio", "activatedAt", "importRun"}
    present = sorted(forbidden & set(contract))
    if present:
        raise ValueError(f"release must be environment-neutral: {present}")
    path = payload_file((release_root or RELEASE_ROOT) / release_id, "desired_state.json")
    payload = (
        json.dumps(dict(contract), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    if path.exists():
        if path.read_bytes() != payload:
            raise FileExistsError(f"release create-once conflict: {path}")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path
