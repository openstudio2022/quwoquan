"""Load materialized travel batch creators into TemplateRegistry."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from _common.creator_pool.batch_policy import CANONICAL_BATCH_ID
from _common.paths import _REPO_DATA_ROOT
from _common.creator_pool.constants import CLAIM_POLICY, DISCLOSURE
from template.registry import iter_yaml_files, load_yaml


def travel_creator_batches_root() -> Path:
    return _REPO_DATA_ROOT / "templates" / "creator_profiles" / "travel"


def active_creator_batch_id() -> str | None:
    explicit = os.environ.get("QWQ_CREATOR_BATCH")
    if explicit:
        return explicit
    default_batch = CANONICAL_BATCH_ID
    if (travel_creator_batches_root() / default_batch).is_dir():
        return default_batch
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
        data = _normalize_travel_batch_creator(load_yaml(path), batch)
        creator_id = str(data.get("creatorProfileId") or "")
        if creator_id:
            creators[creator_id] = data
            paths[creator_id] = path
    return creators, paths


def _normalize_travel_batch_creator(data: dict[str, Any], batch_id: str) -> dict[str, Any]:
    """把批量导入的 compact creator profile 提升为 TemplateRegistry 可路由形态。"""
    profile = dict(data)
    creator_id = str(profile.get("creatorProfileId") or "")
    sub_account_id = str(profile.get("subAccountId") or f"{creator_id}_sub_01")
    tags = _dedupe_str_list(
        list(profile.get("publicProfileTagRefs") or [])
        + list(profile.get("interestTagRefs") or [])
    )
    recommendation_tags = _dedupe_str_list(profile.get("recommendationTagRefs") or [])

    profile.setdefault("subAccountId", sub_account_id)
    profile.setdefault("authorId", sub_account_id)
    profile.setdefault("isSystemBuiltin", False)
    profile.setdefault("scenarioRefs", ["cold_start", "long_tail_fill", "refresh_stale"])
    profile.setdefault("claimPolicy", dict(CLAIM_POLICY))
    profile.setdefault("disclosure", dict(DISCLOSURE))
    profile.setdefault(
        "publishCadence",
        {"intervalDays": 3, "randomizedRangeDays": [1, 5], "maxDailyPosts": 1},
    )
    profile.setdefault("qualityScore", 0.85)
    profile.setdefault("fatigueScore", 0.2)
    profile.setdefault("riskTier", "low")
    profile.setdefault("profileVersion", "1.0.0")
    profile.setdefault("publicProfileTagRefs", tags[:3] or ["Topic/旅行"])
    profile.setdefault("recommendationTagRefs", recommendation_tags)
    profile.setdefault(
        "voiceStyle",
        {"narrativePointOfView": "资料整理", "tone": "清楚、具体、保留资料边界"},
    )
    profile.setdefault("expertiseClaims", _expertise_claims(tags))
    profile.setdefault("mustNotClaim", list(CLAIM_POLICY["forbiddenClaims"]))
    profile.setdefault("cohortId", batch_id)
    profile.setdefault("batchId", batch_id)
    return profile


def _dedupe_str_list(values: Any) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    if not isinstance(values, list):
        return out
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _expertise_claims(tag_refs: list[str]) -> list[str]:
    claims: list[str] = []
    for ref in tag_refs:
        if ref.startswith(("Topic/旅行", "Topic/摄影", "Format/内容角度")):
            leaf = ref.rstrip("/").split("/")[-1]
            if leaf and leaf not in claims:
                claims.append(leaf)
        if len(claims) >= 3:
            break
    return claims or ["旅行体验", "路线整理", "资料核对"]


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
