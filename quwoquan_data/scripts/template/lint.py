"""Template library lint gates."""
from __future__ import annotations

from template.blueprint import (
    REQUIRED_BLUEPRINT_FIELDS,
    canonical_blueprint_relpath,
    collect_tag_refs,
    render_font,
    render_template,
    validate_required,
)
from template.condition import scan_region_locked_terms, validate_region_season
from template.creator import validate_creators
from template.recommend import validate_recommendation_contract
from template.registry import BLUEPRINTS_ROOT, TemplateRegistry, tag_exists
from template.source import validate_source_catalog
from template.style import validate_style_catalog


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
        else:
            expected_rel = canonical_blueprint_relpath(blueprint)
            actual_path = registry.blueprint_paths.get(template_id)
            if expected_rel and actual_path is not None:
                try:
                    actual_rel = actual_path.relative_to(BLUEPRINTS_ROOT).as_posix()
                except ValueError:
                    actual_rel = actual_path.as_posix()
                if actual_rel != expected_rel:
                    errors.append(
                        f"{label}: blueprint path not isomorphic to tag system; "
                        f"expected blueprints/{expected_rel}, found blueprints/{actual_rel}"
                    )
        if not isinstance(blueprint.get("imagePlan"), list) or not blueprint.get("imagePlan"):
            errors.append(f"{label}: imagePlan must be a non-empty list")

        if _is_route_blueprint(blueprint):
            for field in (
                "narrativeMode",
                "evidenceRequirements",
                "continuityExpectations",
                "routeCoverageExpectations",
            ):
                if not isinstance(blueprint.get(field), dict) or not blueprint.get(field):
                    errors.append(f"{label}: route blueprint missing {field}")
            narrative_mode = blueprint.get("narrativeMode") or {}
            if narrative_mode and not narrative_mode.get("transitionPolicy"):
                errors.append(f"{label}: narrativeMode.transitionPolicy is required for route blueprint")
            evidence_requirements = blueprint.get("evidenceRequirements") or {}
            if evidence_requirements and not isinstance(evidence_requirements.get("fact"), dict):
                errors.append(f"{label}: evidenceRequirements.fact must be an object")
            route_coverage = blueprint.get("routeCoverageExpectations") or {}
            if route_coverage and "minCoveredEntityRefs" not in route_coverage:
                errors.append(f"{label}: routeCoverageExpectations.minCoveredEntityRefs is required")
            for field in ("openingTension", "explicitFeelings", "decisionPoints", "tipsEmbeddingPolicy"):
                if not isinstance(blueprint.get(field), dict) or not blueprint.get(field):
                    errors.append(f"{label}: route blueprint missing narrative contract field {field}")
            # 注：不再强制 explicitFeelings 双 true 或 tipsEmbeddingPolicy.forbidStandaloneBlock=true。
            # 这些修辞骨架已在评审聚合中降级为软门（建议），允许 blueprint 不套骨架（底稿轻改范式）。

        if str(blueprint.get("carrier")) == "gallery":
            policy = blueprint.get("imagePolicy")
            if not isinstance(policy, dict) or not policy:
                errors.append(f"{label}: gallery blueprint requires imagePolicy")
            else:
                if not isinstance(policy.get("minImages"), int):
                    errors.append(f"{label}: imagePolicy.minImages must be an integer")
                if not isinstance(policy.get("captionMaxChars"), int):
                    errors.append(f"{label}: imagePolicy.captionMaxChars must be an integer")

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
    errors.extend(validate_source_catalog(registry))
    errors.extend(validate_style_catalog(registry))
    return errors


def _category_for_vertical(vertical: object) -> str:
    if vertical == "campus":
        return "life"
    return "travel"


def _is_route_blueprint(blueprint: dict[str, object]) -> bool:
    subject = blueprint.get("subject")
    return (
        isinstance(subject, dict)
        and subject.get("kind") == "topic"
        and subject.get("type") == "旅行/线路"
    )
