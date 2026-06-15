"""System builtin creator profile matching and validation."""
from __future__ import annotations

from typing import Any

from template.blueprint import REQUIRED_CREATOR_FIELDS, validate_required, collect_tag_refs
from template.registry import TemplateRegistry, tag_exists


VALID_CREATOR_STATUSES = {"draft", "ai_reviewed", "active", "throttled", "suspended", "retired"}
VALID_EXPERIENCE_CLAIM_MODES = {
    "editorial_synthesis",
    "authorized_first_person",
    "public_data_analysis",
    "visual_discovery",
}
VALID_RISK_TIERS = {"low", "medium", "high"}


def validate_creators(registry: TemplateRegistry) -> list[str]:
    errors: list[str] = []
    seen_profile_ids: set[str] = set()
    seen_author_ids: set[str] = set()

    for creator_id, creator in registry.creators.items():
        label = f"creator {creator_id}"
        errors.extend(validate_required(creator, REQUIRED_CREATOR_FIELDS, label))

        if creator_id in seen_profile_ids:
            errors.append(f"{label}: duplicate creatorProfileId")
        seen_profile_ids.add(creator_id)

        author_id = str(creator.get("authorId", ""))
        if author_id in seen_author_ids:
            errors.append(f"{label}: duplicate authorId '{author_id}'")
        seen_author_ids.add(author_id)
        if str(creator.get("status") or "") not in VALID_CREATOR_STATUSES:
            errors.append(f"{label}: unsupported status '{creator.get('status')}'")
        if str(creator.get("riskTier") or "") not in VALID_RISK_TIERS:
            errors.append(f"{label}: unsupported riskTier '{creator.get('riskTier')}'")
        if creator_id.startswith(("tag:", "entity:", "Topic/", "Entity/", "Format/")):
            errors.append(f"{label}: creatorProfileId must not be a tag/entity ref")

        disclosure = creator.get("disclosure")
        if not isinstance(disclosure, dict):
            errors.append(f"{label}: disclosure must be an object")
        else:
            if disclosure.get("type") != "platform_virtual_creator":
                errors.append(f"{label}: disclosure.type must be platform_virtual_creator")
            if disclosure.get("visible") is not True:
                errors.append(f"{label}: disclosure.visible must be true")
            if not str(disclosure.get("displayText") or "").strip():
                errors.append(f"{label}: disclosure.displayText is required")

        claim_policy = creator.get("claimPolicy")
        if not isinstance(claim_policy, dict):
            errors.append(f"{label}: claimPolicy must be an object")
        else:
            mode = str(claim_policy.get("experienceClaimMode") or "")
            if mode not in VALID_EXPERIENCE_CLAIM_MODES:
                errors.append(f"{label}: unsupported claimPolicy.experienceClaimMode '{mode}'")
            if claim_policy.get("mustCiteEvidenceForClaims") is not True:
                errors.append(f"{label}: claimPolicy.mustCiteEvidenceForClaims must be true")
            if claim_policy.get("mayUseFirstPerson") is True and mode != "authorized_first_person":
                errors.append(f"{label}: first-person claims require authorized_first_person mode")

        cadence = creator.get("publishCadence")
        if not isinstance(cadence, dict):
            errors.append(f"{label}: publishCadence must be an object")
        else:
            interval = int(cadence.get("intervalDays") or 0)
            if interval < 1 or interval > 5:
                errors.append(f"{label}: publishCadence.intervalDays must be 1..5")
            if int(cadence.get("maxDailyPosts") or 0) > 1:
                errors.append(f"{label}: publishCadence.maxDailyPosts must be <= 1")

        for tag_ref in collect_tag_refs(creator):
            if not tag_exists(tag_ref):
                errors.append(f"{label}: tagRef not found: {tag_ref}")

    for template_id, blueprint in registry.blueprints.items():
        persona = blueprint.get("creatorPersona")
        if not isinstance(persona, dict):
            errors.append(f"blueprint {template_id}: missing creatorPersona")
            continue
        archetype = str(persona.get("archetype", ""))
        candidates = registry.creators_by_archetype(archetype)
        if not candidates:
            errors.append(f"blueprint {template_id}: no creator for archetype '{archetype}'")
            continue

        required_tags = set(str(t) for t in persona.get("requiredProfileTagRefs", []))
        if required_tags:
            matched = False
            for creator in candidates:
                creator_tags = set(creator.get("publicProfileTagRefs", [])) | set(creator.get("recommendationTagRefs", []))
                if required_tags & creator_tags:
                    matched = True
                    break
            if not matched:
                errors.append(
                    f"blueprint {template_id}: creator archetype '{archetype}' "
                    "does not overlap requiredProfileTagRefs"
                )

    return errors


def choose_creator(registry: TemplateRegistry, blueprint: dict[str, Any], preferred_archetype: str | None = None) -> dict[str, Any]:
    persona = blueprint.get("creatorPersona") if isinstance(blueprint.get("creatorPersona"), dict) else {}
    preferred_ids = [str(x) for x in persona.get("preferredCreatorIds", [])]
    for creator_id in preferred_ids:
        if creator_id in registry.creators:
            return registry.creators[creator_id]

    archetype = preferred_archetype or str(persona.get("archetype", ""))
    candidates = registry.creators_by_archetype(archetype)
    if candidates:
        return candidates[0]
    if registry.creators:
        return next(iter(registry.creators.values()))
    raise ValueError("No creator profiles available")
