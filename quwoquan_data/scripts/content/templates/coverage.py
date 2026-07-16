"""Coverage reporting for the template library."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from content.templates.registry import TemplateRegistry


def coverage_rows(registry: TemplateRegistry, vertical: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for template_id, blueprint in sorted(registry.blueprints.items()):
        if vertical and blueprint.get("vertical") != vertical:
            continue
        rows.append(
            {
                "templateId": template_id,
                "vertical": blueprint.get("vertical"),
                "subject": blueprint.get("subject", {}).get("type"),
                "subjectKind": blueprint.get("subject", {}).get("kind"),
                "intent": blueprint.get("intent"),
                "carrier": blueprint.get("carrier"),
                "styleFamily": blueprint.get("styleFamily"),
                "audiences": blueprint.get("audiences", []),
                "creatorArchetype": blueprint.get("creatorPersona", {}).get("archetype"),
            }
        )
    return rows


def coverage_summary(registry: TemplateRegistry, vertical: str | None = None) -> dict[str, Any]:
    rows = coverage_rows(registry, vertical)
    audiences: set[str] = set()
    creators: set[str] = set()
    subjects: set[str] = set()
    intents: set[str] = set()
    by_subject: dict[str, int] = defaultdict(int)
    for row in rows:
        subjects.add(str(row.get("subject")))
        intents.add(str(row.get("intent")))
        creators.add(str(row.get("creatorArchetype")))
        for audience in row.get("audiences", []):
            audiences.add(str(audience))
        by_subject[str(row.get("subject"))] += 1

    return {
        "templateCount": len(rows),
        "subjectCount": len(subjects),
        "intentCount": len(intents),
        "audienceCount": len(audiences),
        "creatorArchetypeCount": len(creators),
        "subjects": sorted(subjects),
        "intents": sorted(intents),
        "audiences": sorted(audiences),
        "creatorArchetypes": sorted(creators),
        "bySubject": dict(sorted(by_subject.items())),
        "audienceMatrix": _audience_matrix(registry, vertical),
    }


def _audience_matrix(registry: TemplateRegistry, vertical: str | None) -> dict[str, Any]:
    """受众覆盖矩阵：暴露定义却无任何模板引用的孤儿受众。"""
    defined_audiences = set((registry.catalogs.get("audience_catalog", {}).get("audiences", {}) or {}).keys())

    referenced_audiences: set[str] = set()
    for blueprint in registry.blueprints.values():
        if vertical and blueprint.get("vertical") != vertical:
            continue
        for audience in blueprint.get("audiences", []) or []:
            referenced_audiences.add(str(audience))

    scope_audiences = defined_audiences
    if vertical:
        scope_audiences = {
            a for a, meta in (registry.catalogs.get("audience_catalog", {}).get("audiences", {}) or {}).items()
            if meta.get("vertical") == vertical
        }
    orphan_audiences = sorted(scope_audiences - referenced_audiences)

    return {
        "orphanAudiences": orphan_audiences,
    }
