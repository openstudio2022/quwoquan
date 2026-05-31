"""Resolve 8D template routing requests."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from template.creator import choose_creator
from template.registry import TemplateRegistry


@dataclass(frozen=True)
class RouteRequest:
    vertical: str
    subject_kind: str
    subject_type: str
    intent: str
    audience: str | None = None
    creator_archetype: str | None = None
    # 条件修饰维（不参与选模板，仅透传给 brief 注入）
    region: str | None = None
    season: str | None = None


@dataclass(frozen=True)
class RouteResult:
    template_id: str
    creator_profile_id: str
    creator_archetype: str
    blueprint: dict[str, Any]
    creator: dict[str, Any]


def resolve_route(registry: TemplateRegistry, request: RouteRequest) -> RouteResult:
    routing = registry.routes.get(request.vertical)
    if routing is None:
        raise ValueError(f"No routing table for vertical: {request.vertical}")

    selected: dict[str, Any] | None = None
    for route in routing.get("routes", []):
        match = route.get("match", {})
        if _matches(match, request):
            selected = route
            break
    if selected is None:
        selected = routing.get("fallback", {}).get(request.subject_kind)
    if not isinstance(selected, dict):
        raise ValueError(f"No route for request: {request}")

    template_id = str(selected.get("templateId", ""))
    if template_id not in registry.blueprints:
        raise ValueError(f"Route points to missing template: {template_id}")
    blueprint = registry.blueprints[template_id]
    creator_archetype = request.creator_archetype or selected.get("creatorArchetype")
    creator = choose_creator(registry, blueprint, str(creator_archetype) if creator_archetype else None)
    return RouteResult(
        template_id=template_id,
        creator_profile_id=str(creator["creatorProfileId"]),
        creator_archetype=str(creator["creatorArchetype"]),
        blueprint=blueprint,
        creator=creator,
    )


def _matches(match: dict[str, Any], request: RouteRequest) -> bool:
    checks = {
        "subjectKind": request.subject_kind,
        "subjectType": request.subject_type,
        "intent": request.intent,
        "audience": request.audience,
    }
    for key, value in match.items():
        if checks.get(key) != value:
            return False
    return True
