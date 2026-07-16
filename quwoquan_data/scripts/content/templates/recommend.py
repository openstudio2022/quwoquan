"""Recommendation-facing manifest helpers."""
from __future__ import annotations

from typing import Any

from content.templates.blueprint import collect_tag_refs
from content.templates.creator import choose_creator
from content.templates.registry import TemplateRegistry


def build_recommendation_manifest(
    registry: TemplateRegistry,
    blueprint: dict[str, Any],
    subject_ref: dict[str, Any],
    entity_refs: list[str],
    tag_refs: list[str],
    *,
    creator: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # 复用 route 已按内容信号匹配出的作者，保证 brief 与 recommendation 同一虚拟作者。
    if creator is None:
        creator = choose_creator(registry, blueprint)
    merged_tags = list(dict.fromkeys(tag_refs + collect_tag_refs(blueprint) + creator.get("recommendationTagRefs", [])))
    manifest = {
        "contentType": _content_type(blueprint),
        "authorId": creator["authorId"],
        "creatorProfileId": creator["creatorProfileId"],
        "creatorArchetype": creator["creatorArchetype"],
        "subjectRef": subject_ref,
        "entityRefs": entity_refs,
        "tagRefs": merged_tags,
        "qualitySignals": {
            "requiredFactsCovered": len(blueprint.get("mustIncludeFacts", [])),
            "imageSlotCoverage": 1.0 if blueprint.get("imagePlan") else 0.0,
            "entityRefCount": len(entity_refs),
            "tagCount": len(merged_tags),
        },
    }
    return manifest


def validate_recommendation_contract(registry: TemplateRegistry) -> list[str]:
    errors: list[str] = []
    required_forbidden = {"qualityScore", "templateId", "routingReason", "coldStartBoost", "isSystemBuiltin"}
    for template_id, blueprint in registry.blueprints.items():
        rec = blueprint.get("recommendation")
        if not isinstance(rec, dict):
            errors.append(f"blueprint {template_id}: missing recommendation")
            continue
        if rec.get("authorBinding", {}).get("required") is not True:
            errors.append(f"blueprint {template_id}: recommendation.authorBinding.required must be true")
        body_forbidden = set(str(item) for item in rec.get("bodyForbiddenFields", []))
        missing = required_forbidden - body_forbidden
        if missing:
            errors.append(f"blueprint {template_id}: bodyForbiddenFields missing {sorted(missing)}")
    return errors


def _content_type(blueprint: dict[str, Any]) -> str:
    carrier = str(blueprint.get("carrier", "article"))
    if carrier == "image":
        return "image"
    if carrier == "video":
        return "video"
    return "article"
