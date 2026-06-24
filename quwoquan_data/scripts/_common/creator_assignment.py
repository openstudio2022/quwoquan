"""Creator assignment contract shared by content planning, authoring and scale gates."""
from __future__ import annotations

from typing import Any, Mapping


CREATOR_ASSIGNMENT_FIELDS: tuple[str, ...] = (
    "authorId",
    "creatorProfileId",
    "creatorArchetype",
    "creatorProfileVersion",
    "creatorDisclosure",
    "experienceClaimMode",
    "authorQualitySignals",
)

VALID_EXPERIENCE_CLAIM_MODES = {
    "editorial_synthesis",
    "authorized_first_person",
    "public_data_analysis",
    "visual_discovery",
}


def creator_assignment_required(spec: Mapping[str, Any]) -> bool:
    """Whether content objects must carry a frozen creator assignment.

    Scale workflows can enable this explicitly. Reliable-task authoring also
    requires it because those jobs are expected to be governed end to end.
    """
    policy = spec.get("workflowPolicy") if isinstance(spec.get("workflowPolicy"), Mapping) else {}
    content = spec.get("content") if isinstance(spec.get("content"), Mapping) else {}
    queue_policy = spec.get("queuePolicy") if isinstance(spec.get("queuePolicy"), Mapping) else {}
    content_queue_policy = content.get("queuePolicy") if isinstance(content.get("queuePolicy"), Mapping) else {}
    backend = (
        queue_policy.get("backend")
        or content_queue_policy.get("backend")
        or content.get("queueBackend")
        or spec.get("queueBackend")
    )
    return bool(
        policy.get("requireCreatorAssignment") is True
        or content.get("requireCreatorAssignment") is True
        or backend == "reliabletask"
    )


def creator_from_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Extract platform creator assignment without mixing source-rights creator."""
    nested = payload.get("creator") if isinstance(payload.get("creator"), Mapping) else {}
    row: dict[str, Any] = {}
    for field in CREATOR_ASSIGNMENT_FIELDS:
        value = payload.get(field)
        if value in (None, "", {}):
            value = nested.get(field)
        if value not in (None, "", {}):
            row[field] = value
    profile = _registry_creator(str(row.get("creatorProfileId") or payload.get("creatorProfileId") or nested.get("creatorProfileId") or ""))
    if profile is not None:
        registry_projection = creator_assignment_from_profile(profile)
        if row.get("authorId") and registry_projection.get("authorId") != row.get("authorId"):
            return row
        for field in CREATOR_ASSIGNMENT_FIELDS:
            if row.get(field) in (None, "", {}):
                value = registry_projection.get(field)
                if value not in (None, "", {}):
                    row[field] = value
    return row


def _registry_creator(creator_profile_id: str) -> dict[str, Any] | None:
    if not creator_profile_id:
        return None
    try:
        from template.registry import TemplateRegistry
    except Exception:  # noqa: BLE001
        return None
    try:
        return TemplateRegistry.load().creators.get(creator_profile_id)
    except Exception:  # noqa: BLE001
        pass
    try:
        from template.registry import CREATORS_ROOT, iter_yaml_files, load_yaml
    except Exception:  # noqa: BLE001
        return None
    for path in iter_yaml_files(CREATORS_ROOT, ".creator.yaml"):
        try:
            data = load_yaml(path)
        except Exception:  # noqa: BLE001
            continue
        if str(data.get("creatorProfileId") or "") == creator_profile_id:
            return data
    return None


def _disclosure_issues(disclosure: Any, *, prefix: str) -> list[str]:
    if not isinstance(disclosure, Mapping):
        return [f"{prefix}.creatorDisclosure must be an object"]
    issues: list[str] = []
    if disclosure.get("type") != "platform_virtual_creator":
        issues.append(f"{prefix}.creatorDisclosure.type must be platform_virtual_creator")
    if disclosure.get("visible") is not True:
        issues.append(f"{prefix}.creatorDisclosure.visible must be true")
    if not str(disclosure.get("displayText") or "").strip():
        issues.append(f"{prefix}.creatorDisclosure.displayText is required")
    return issues


def creator_assignment_issues(
    payload: Mapping[str, Any],
    *,
    carrier: str | None = None,
    prefix: str = "creatorAssignment",
    require_registered: bool = True,
) -> list[str]:
    """Validate that a content object has a frozen, registry-backed creator."""
    creator = creator_from_payload(payload)
    issues: list[str] = []
    for field in CREATOR_ASSIGNMENT_FIELDS:
        if field not in creator:
            issues.append(f"{prefix}.{field} required")
    if issues:
        return issues

    claim_mode = str(creator.get("experienceClaimMode") or "")
    if claim_mode not in VALID_EXPERIENCE_CLAIM_MODES:
        issues.append(f"{prefix}.experienceClaimMode unsupported: {claim_mode or '<missing>'}")
    issues.extend(_disclosure_issues(creator.get("creatorDisclosure"), prefix=prefix))
    signals = creator.get("authorQualitySignals")
    if not isinstance(signals, Mapping):
        issues.append(f"{prefix}.authorQualitySignals must be an object")
    else:
        for field in ("qualityScore", "fatigueScore", "riskTier"):
            if signals.get(field) in (None, ""):
                issues.append(f"{prefix}.authorQualitySignals.{field} required")

    if not require_registered:
        return issues

    registered = _registry_creator(str(creator.get("creatorProfileId") or ""))
    if registered is None:
        issues.append(f"{prefix}.creatorProfileId not found in creator registry")
        return issues
    if str(registered.get("status") or "") != "active":
        issues.append(f"{prefix}.creatorProfileId is not active")
    if str(registered.get("authorId") or "") != str(creator.get("authorId") or ""):
        issues.append(f"{prefix}.authorId does not match creator registry")
    if str(registered.get("creatorArchetype") or "") != str(creator.get("creatorArchetype") or ""):
        issues.append(f"{prefix}.creatorArchetype does not match creator registry")
    if str(registered.get("profileVersion") or "") != str(creator.get("creatorProfileVersion") or ""):
        issues.append(f"{prefix}.creatorProfileVersion does not match creator registry")
    if carrier:
        try:
            from template.creator import carrier_affinity
            affinity = carrier_affinity(registered, "image" if carrier == "gallery" else carrier)
        except Exception:  # noqa: BLE001
            affinity = 0.0
        if affinity <= 0:
            issues.append(f"{prefix}.carrierAffinity is zero for carrier={carrier}")
    return issues


def creator_assignment_from_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Project a registry profile into content-object creator assignment fields."""
    return {
        "authorId": profile.get("authorId"),
        "creatorProfileId": profile.get("creatorProfileId"),
        "creatorArchetype": profile.get("creatorArchetype"),
        "creatorProfileVersion": profile.get("profileVersion"),
        "creatorDisclosure": profile.get("disclosure"),
        "experienceClaimMode": (profile.get("claimPolicy") or {}).get("experienceClaimMode")
        if isinstance(profile.get("claimPolicy"), Mapping)
        else None,
        "authorQualitySignals": {
            "qualityScore": profile.get("qualityScore"),
            "fatigueScore": profile.get("fatigueScore"),
            "riskTier": profile.get("riskTier"),
        },
    }
