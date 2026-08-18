"""Verify acquisition items against one immutable image-discovery plan."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.io import read_json
from core.schema import assert_valid


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def load_discovery_candidates(
    manifest: Mapping[str, Any],
    *,
    output_root: Path,
) -> dict[str, Mapping[str, Any]]:
    """Load and digest-check the discovery plan bound by the manifest."""
    relative = Path(str(manifest["discoveryPlanRef"]))
    if relative.is_absolute() or not str(relative):
        raise ValueError("professional image discoveryPlanRef must be relative")
    root = output_root.resolve()
    plan_path = (root / relative).resolve()
    if root not in plan_path.parents or not plan_path.is_file():
        raise ValueError("professional image discoveryPlanRef escapes or is missing")
    plan = read_json(plan_path)
    if not isinstance(plan, dict):
        raise TypeError("professional image discovery plan must be an object")
    assert_valid(
        plan,
        "source",
        "professional_image_discovery_plan",
        label="professional image discovery plan",
    )
    if plan.get("planDigest") != manifest.get("discoveryPlanDigest"):
        raise ValueError("professional image discovery plan digest binding mismatch")
    stable = {
        key: plan[key]
        for key in (
            "catalogRef",
            "catalogDigest",
            "dimensions",
            "candidateCount",
            "providerCandidateCounts",
            "candidates",
        )
    }
    if _digest(stable) != plan.get("planDigest"):
        raise ValueError("professional image discovery plan content digest mismatch")
    candidates = {
        str(row["candidateId"]): row
        for row in plan["candidates"]
        if isinstance(row, Mapping)
    }
    if len(candidates) != len(plan["candidates"]):
        raise ValueError("professional image discovery candidate IDs must be unique")
    return candidates


def validate_discovery_binding(
    item: Mapping[str, Any],
    *,
    candidates: Mapping[str, Mapping[str, Any]],
) -> None:
    """Reject any asset that does not match its frozen discovery candidate."""
    candidate_id = str(item["discoveryCandidateId"])
    candidate = candidates.get(candidate_id)
    if candidate is None:
        raise ValueError(f"{item['assetId']}: discovery candidate is not frozen")
    if str(candidate["provider"]) != str(item["sourceId"]):
        raise ValueError(f"{item['assetId']}: discovery provider mismatch")
    if str(candidate["entity"]) != str(item["observedEntityId"]):
        raise ValueError(f"{item['assetId']}: discovery entity mismatch")
    if str(candidate["discoveryUrl"]) != str(item["discoveryUrl"]):
        raise ValueError(f"{item['assetId']}: discovery URL mismatch")
    if str(item["acquisitionPath"]) not in {
        str(value) for value in candidate["acquisitionPaths"]
    }:
        raise ValueError(f"{item['assetId']}: discovery acquisition path mismatch")


__all__ = ["load_discovery_candidates", "validate_discovery_binding"]
