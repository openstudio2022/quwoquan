"""Persona rubric evaluation for creator pool validate stage."""
from __future__ import annotations

from typing import Any

from _common.creator_pool.constants import CLAIM_POLICY, TRAVEL_ARCHETYPES
from _common.creator_pool.persona_dedup import persona_similarity

RUBRIC: dict[str, Any] = {
    "schemaVersion": "quwoquan_data.creator_persona_rubric/1",
    "minBioLength": 8,
    "minHeadlineLength": 4,
    "maxBatchSimilarity": 0.85,
    "requireDisclosureVisible": True,
    "minArchetypeCoverage": 6,
    "commercialPassRate": 0.95,
    "trialPassRate": 0.8,
}


def evaluate_persona_rubric(
    bundle: dict[str, Any],
    *,
    enrich_meta: dict[str, Any] | None = None,
    live_mode: bool = False,
    peer_bundles: list[dict[str, Any]] | None = None,
) -> tuple[bool, list[str]]:
    issues: list[str] = []
    profile = bundle.get("profile") or {}
    for field in ("displayName", "userHandle", "bio", "headline"):
        val = str(profile.get(field) or "").strip()
        if field == "bio":
            if len(val) < int(RUBRIC["minBioLength"]):
                issues.append("bio too short")
        elif field == "headline":
            if len(val) < int(RUBRIC["minHeadlineLength"]):
                issues.append("headline too short")
        elif not val:
            issues.append(f"missing profile.{field}")
    disclosure = (bundle.get("content") or {}).get("disclosure") or {}
    if RUBRIC["requireDisclosureVisible"] and not disclosure.get("visible"):
        issues.append("disclosure not visible")
    claim = (bundle.get("content") or {}).get("claimPolicy") or {}
    forbidden = set(CLAIM_POLICY.get("forbiddenClaims") or [])
    bio_text = str(profile.get("bio") or "")
    headline_text = str(profile.get("headline") or "")
    for token in forbidden:
        if token and (token in bio_text or token in headline_text):
            issues.append(f"forbidden claim: {token}")
    if live_mode:
        cited = (bundle.get("provenance") or {}).get("citedSourcePaths") or (enrich_meta or {}).get(
            "citedSourcePaths"
        )
        if not cited:
            issues.append("missing citedSourcePaths")
    if peer_bundles:
        max_sim = 0.0
        for peer in peer_bundles:
            if peer is bundle:
                continue
            max_sim = max(max_sim, persona_similarity(bundle, peer))
        if max_sim >= float(RUBRIC["maxBatchSimilarity"]):
            issues.append(f"batch persona similarity {max_sim:.2f} >= {RUBRIC['maxBatchSimilarity']}")
    return (not issues, issues)


def persona_rubric_pass_rate(
    bundles: list[dict[str, Any]],
    *,
    live_mode: bool = False,
    enrich_meta_by_ref: dict[str, dict[str, Any]] | None = None,
) -> float:
    if not bundles:
        return 0.0
    passed = 0
    enrich_meta_by_ref = enrich_meta_by_ref or {}
    for bundle in bundles:
        ref = str(bundle.get("creatorProfileId") or "")
        ok, _ = evaluate_persona_rubric(
            bundle,
            enrich_meta=enrich_meta_by_ref.get(ref),
            live_mode=live_mode,
            peer_bundles=bundles,
        )
        if ok:
            passed += 1
    return round(passed / len(bundles), 4)


def archetype_coverage(bundles: list[dict[str, Any]]) -> int:
    seen: set[str] = set()
    for bundle in bundles:
        arch = str(bundle.get("creatorArchetype") or (bundle.get("diversitySlots") or {}).get("archetypeBucket") or "")
        if arch in TRAVEL_ARCHETYPES:
            seen.add(arch)
    return len(seen)
