"""Blueprint validation helpers."""
from __future__ import annotations

from typing import Any


REQUIRED_BLUEPRINT_FIELDS = [
    "templateId",
    "version",
    "subject",
    "vertical",
    "intent",
    "carrier",
    "styleFamily",
    "styleProfile",
    "audiences",
    "editorialIntent",
    "render",
    "structure",
    "wordCount",
    "imagePlan",
    "crossRefs",
    "recommendation",
]


REQUIRED_CREATOR_FIELDS = [
    "creatorProfileId",
    "subAccountId",
    "authorId",
    "isSystemBuiltin",
    "displayName",
    "userHandle",
    "headline",
    "bio",
    "creatorArchetype",
    "publicProfileTagRefs",
    "recommendationTagRefs",
    "preferredBlueprintIds",
    "voiceStyle",
    "expertiseClaims",
    "mustNotClaim",
]


def validate_required(data: dict[str, Any], fields: list[str], label: str) -> list[str]:
    return [f"{label}: missing required field '{field}'" for field in fields if field not in data]


def collect_tag_refs(value: Any) -> list[str]:
    refs: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key.endswith("TagRef") and isinstance(child, str):
                refs.append(child)
            elif key.endswith("TagRefs") and isinstance(child, list):
                refs.extend(str(item) for item in child)
            else:
                refs.extend(collect_tag_refs(child))
    elif isinstance(value, list):
        for child in value:
            refs.extend(collect_tag_refs(child))
    return refs


def render_template(data: dict[str, Any]) -> str | None:
    render = data.get("render")
    if not isinstance(render, dict):
        return None
    template = render.get("articleTemplate")
    return str(template) if template is not None else None


def render_font(data: dict[str, Any]) -> str | None:
    render = data.get("render")
    if not isinstance(render, dict):
        return None
    font = render.get("fontPreset")
    return str(font) if font is not None else None
