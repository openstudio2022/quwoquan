"""Template library lint gates."""
from __future__ import annotations

from template.blueprint import (
    REQUIRED_BLUEPRINT_FIELDS,
    collect_tag_refs,
    render_font,
    render_template,
    validate_required,
)
from template.condition import scan_region_locked_terms, validate_region_season
from template.creator import validate_creators
from template.recommend import validate_recommendation_contract
from template.registry import TemplateRegistry, tag_exists


ARTICLE_TEMPLATES = {"gentle", "ritual", "diffuse", "journal", "tech"}
FONT_PRESETS = {"clean", "classic", "handwritten", "rounded", "mono"}


def lint_templates(registry: TemplateRegistry) -> list[str]:
    errors: list[str] = []
    if not registry.blueprints:
        errors.append("No template blueprints found")

    for template_id, blueprint in registry.blueprints.items():
        label = f"blueprint {template_id}"
        errors.extend(validate_required(blueprint, REQUIRED_BLUEPRINT_FIELDS, label))

        category = str(blueprint.get("category") or _category_for_vertical(blueprint.get("vertical")))
        template = render_template(blueprint)
        font = render_font(blueprint)
        if template not in ARTICLE_TEMPLATES:
            errors.append(f"{label}: invalid articleTemplate '{template}'")
        if font not in FONT_PRESETS:
            errors.append(f"{label}: invalid fontPreset '{font}'")
        allowed = registry.article_recommendations.get(category)
        if allowed and template not in allowed:
            errors.append(f"{label}: articleTemplate '{template}' not recommended for category '{category}'")

        for tag_ref in collect_tag_refs(blueprint):
            if not tag_exists(tag_ref):
                errors.append(f"{label}: tagRef not found: {tag_ref}")

        subject = blueprint.get("subject")
        if not isinstance(subject, dict) or subject.get("kind") not in {"entity", "topic"}:
            errors.append(f"{label}: subject.kind must be entity or topic")
        if not isinstance(blueprint.get("imagePlan"), list) or not blueprint.get("imagePlan"):
            errors.append(f"{label}: imagePlan must be a non-empty list")

        for hit in scan_region_locked_terms(blueprint):
            errors.append(
                f"{label}: region-locked term in structure/mustIncludeFacts: {hit}; "
                "move it to region_catalog and declare conditionAxes instead"
            )

    return errors


def lint_all() -> list[str]:
    registry = TemplateRegistry.load()
    errors = []
    errors.extend(lint_templates(registry))
    errors.extend(validate_recommendation_contract(registry))
    errors.extend(validate_creators(registry))
    errors.extend(validate_region_season(registry))
    return errors


def _category_for_vertical(vertical: object) -> str:
    if vertical == "campus":
        return "life"
    return "travel"
