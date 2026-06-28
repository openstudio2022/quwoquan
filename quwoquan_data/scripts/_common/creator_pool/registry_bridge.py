"""Load materialized travel batch creators into TemplateRegistry."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from _common.paths import _REPO_DATA_ROOT
from template.registry import iter_yaml_files, load_yaml


def travel_creator_batches_root() -> Path:
    return _REPO_DATA_ROOT / "templates" / "creator_profiles" / "travel"


def active_creator_batch_id() -> str | None:
    explicit = os.environ.get("QWQ_CREATOR_BATCH")
    if explicit:
        return explicit
    default_batch = "travel_batch_100_v1"
    if (travel_creator_batches_root() / default_batch).is_dir():
        return default_batch
    fallback = "travel_batch_100_v1"
    if (travel_creator_batches_root() / fallback).is_dir():
        return fallback
    return None


def load_travel_batch_creators(batch_id: str | None = None) -> tuple[dict[str, dict[str, Any]], dict[str, Path]]:
    batch = batch_id or active_creator_batch_id()
    if not batch:
        return {}, {}
    root = travel_creator_batches_root() / batch
    if not root.is_dir():
        return {}, {}
    creators: dict[str, dict[str, Any]] = {}
    paths: dict[str, Path] = {}
    for path in iter_yaml_files(root, ".creator.yaml"):
        data = load_yaml(path)
        creator_id = str(data.get("creatorProfileId") or "")
        if creator_id:
            creators[creator_id] = data
            paths[creator_id] = path
    return creators, paths


def author_pool_profile_from_batch(batch_id: str, index: int) -> dict[str, Any] | None:
    creators, _ = load_travel_batch_creators(batch_id)
    if not creators:
        return None
    ordered = sorted(creators.values(), key=lambda row: str(row.get("creatorProfileId") or ""))
    if not ordered:
        return None
    profile = ordered[index % len(ordered)]
    return _to_content_supply_author(profile)


def _to_content_supply_author(profile: dict[str, Any]) -> dict[str, Any]:
    cadence = profile.get("publishCadence") if isinstance(profile.get("publishCadence"), dict) else {}
    interval = int(cadence.get("intervalDays") or 3)
    return {
        "creatorProfileId": profile.get("creatorProfileId"),
        "subAccountId": profile.get("subAccountId"),
        "authorId": profile.get("authorId"),
        "status": profile.get("status", "active"),
        "verticalRefs": profile.get("verticalRefs") or ["travel"],
        "scenarioRefs": profile.get("scenarioRefs") or ["cold_start"],
        "creatorArchetype": profile.get("creatorArchetype"),
        "displayName": profile.get("displayName"),
        "userHandle": profile.get("userHandle"),
        "isVirtualSystemCreator": True,
        "isSystemBuiltin": bool(profile.get("isSystemBuiltin", False)),
        "voiceStyle": profile.get("voiceStyle")
        or {"pointOfView": "editorial_synthesis", "tone": "清楚、具体、保留资料边界"},
        "claimPolicy": profile.get("claimPolicy"),
        "disclosure": profile.get("disclosure"),
        "publishCadence": cadence,
        "publishIntervalDays": interval,
        "qualityScore": profile.get("qualityScore", 0.85),
        "fatigueScore": profile.get("fatigueScore", 0.2),
        "riskTier": profile.get("riskTier", "low"),
        "profileVersion": profile.get("profileVersion", "1.0.0"),
        "identityDisclosure": "platform_virtual_creator",
        "carrierAffinity": profile.get("carrierAffinity"),
        "coverageScope": profile.get("coverageScope"),
    }
