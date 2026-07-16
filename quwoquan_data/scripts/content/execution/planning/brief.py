"""Compose brief generation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.quality_gates import normalize_writing_intent
from content.templates.blueprint import collect_tag_refs
from content.templates.recommend import build_recommendation_manifest
from content.templates.registry import TemplateRegistry
from content.templates.router import RouteRequest, resolve_route


def resolve_compose_brief(
    registry: TemplateRegistry,
    request: RouteRequest,
    *,
    title: str | None = None,
    entity_refs: list[str] | None = None,
) -> dict[str, Any]:
    route = resolve_route(registry, request)
    blueprint = route.blueprint
    creator = route.creator
    subject = _subject_ref(blueprint, request)
    refs = entity_refs or []
    tag_refs = _merge_tag_refs(registry, blueprint, creator)
    must_include = _dedupe(list(blueprint.get("mustIncludeFacts", [])))
    image_plan = list(blueprint.get("imagePlan", []))
    narrative_mode = _normalize_optional_mapping(blueprint.get("narrativeMode"))
    evidence_requirements = _normalize_optional_mapping(blueprint.get("evidenceRequirements"))
    continuity_expectations = _normalize_optional_mapping(blueprint.get("continuityExpectations"))
    route_coverage_expectations = _normalize_optional_mapping(blueprint.get("routeCoverageExpectations"))
    recommendation = build_recommendation_manifest(
        registry, blueprint, subject, refs, tag_refs, creator=creator
    )
    return {
        "templateId": route.template_id,
        "titleHint": title or route.template_id,
        "subject": subject,
        "entityRefs": refs,
        "vertical": blueprint.get("vertical"),
        "intent": {
            "name": blueprint.get("intent"),
            "audience": request.audience,
            "editorialIntent": blueprint.get("editorialIntent"),
        },
        "carrier": blueprint.get("carrier"),
        "styleFamily": blueprint.get("styleFamily"),
        "styleProfile": blueprint.get("styleProfile"),
        "creator": {
            "creatorProfileId": creator.get("creatorProfileId"),
            "authorId": creator.get("authorId"),
            "displayName": creator.get("displayName"),
            "headline": creator.get("headline"),
            "bio": creator.get("bio"),
            "creatorArchetype": creator.get("creatorArchetype"),
            "voiceStyle": creator.get("voiceStyle"),
            "expertiseClaims": creator.get("expertiseClaims", []),
            "mustNotClaim": creator.get("mustNotClaim", []),
            "coverageScope": creator.get("coverageScope"),
            "carrierAffinity": creator.get("carrierAffinity"),
        },
        "render": blueprint.get("render"),
        "structure": blueprint.get("structure"),
        "narrativeMode": narrative_mode,
        "evidenceRequirements": evidence_requirements,
        "continuityExpectations": continuity_expectations,
        "routeCoverageExpectations": route_coverage_expectations,
        "openingTension": _normalize_optional_mapping(blueprint.get("openingTension")),
        "explicitFeelings": _normalize_optional_mapping(blueprint.get("explicitFeelings")),
        "decisionPoints": _normalize_optional_mapping(blueprint.get("decisionPoints")),
        "tipsEmbeddingPolicy": _normalize_optional_mapping(blueprint.get("tipsEmbeddingPolicy")),
        "imagePolicy": _normalize_optional_mapping(blueprint.get("imagePolicy")),
        "narrativePlan": _build_narrative_plan(
            blueprint,
            request,
            refs,
            title_hint=title or route.template_id,
            route_coverage_expectations=route_coverage_expectations,
        ),
        "mustIncludeFacts": must_include,
        "forbiddenPhrases": blueprint.get("forbiddenPhrases", []),
        "wordCount": blueprint.get("wordCount"),
        "imagePlan": image_plan,
        "crossRefs": blueprint.get("crossRefs"),
        "tagRefs": tag_refs,
        "recommendation": recommendation,
        "writingIntent": _resolve_writing_intent(blueprint),
        "baseSourceRef": blueprint.get("baseSourceRef"),
        "bannedRegisterTerms": list(blueprint.get("bannedRegisterTerms", [])),
    }


def _resolve_writing_intent(blueprint: dict[str, Any]) -> str:
    """解析写作主线：blueprint 显式声明优先，否则按 intent/editorialIntent/templateId 关键词推断。

    这是确定性默认值；任务层可在 content_plan_packet 覆写每篇 writingIntent。
    """
    explicit = normalize_writing_intent(blueprint.get("writingIntent"))
    if explicit:
        return explicit
    hay = " ".join(
        str(blueprint.get(key) or "")
        for key in ("intent", "editorialIntent", "templateId", "styleFamily", "carrier")
    )
    if any(k in hay for k in ("游记", "日记", "journal", "过程", "记录")):
        return "post_trip_journal"
    if any(k in hay for k in ("体验", "评测", "决策", "值不值", "review", "experience")):
        return "decision_experience"
    return "planning_consultation"


def _dedupe(items: list[Any]) -> list[Any]:
    return [item for item in dict.fromkeys(items) if item is not None]


def _normalize_optional_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def write_brief(path: Path, brief: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(brief, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _subject_ref(blueprint: dict[str, Any], request: RouteRequest) -> dict[str, Any]:
    subject = blueprint.get("subject", {})
    if request.subject_kind == "topic":
        return {
            "kind": "topic",
            "type": request.subject_type,
            "topicRef": subject.get("subjectTagRef"),
        }
    return {
        "kind": "entity",
        "type": request.subject_type,
    }


def _merge_tag_refs(registry: TemplateRegistry, blueprint: dict[str, Any], creator: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    intent_catalog = registry.catalogs.get("intent_catalog", {}).get("intents", {})
    intent = blueprint.get("intent")
    if intent in intent_catalog:
        tags.append(str(intent_catalog[intent].get("tagRef")))
    carrier_catalog = registry.catalogs.get("carrier_catalog", {}).get("carriers", {})
    carrier = blueprint.get("carrier")
    if carrier in carrier_catalog:
        tags.extend(str(t) for t in carrier_catalog[carrier].get("tagRefs", []))
    tags.extend(collect_tag_refs(blueprint))
    tags.extend(str(t) for t in creator.get("publicProfileTagRefs", []))
    tags.extend(str(t) for t in creator.get("recommendationTagRefs", []))
    return [tag for tag in dict.fromkeys(tags) if tag and tag != "None"]


def _build_narrative_plan(
    blueprint: dict[str, Any],
    request: RouteRequest,
    entity_refs: list[str],
    *,
    title_hint: str,
    route_coverage_expectations: dict[str, Any],
) -> dict[str, Any]:
    narrative_mode = _normalize_optional_mapping(blueprint.get("narrativeMode"))
    if not narrative_mode:
        return {}

    route_nodes = [
        {
            "sequence": index,
            "entityRef": ref,
            "entityName": ref.split("/")[-1],
        }
        for index, ref in enumerate(entity_refs, start=1)
    ]
    if route_nodes:
        mid_sections = [{"kind": "route_node", **node} for node in route_nodes]
    else:
        mid_sections = list(narrative_mode.get("sectionPlan") or [])

    section_plan: list[dict[str, Any]] = []
    opening_focus = str(narrative_mode.get("openingFocus") or "hook")
    section_plan.append(
        {
            "kind": "opening",
            "focus": opening_focus,
            "title": str(narrative_mode.get("openingHeading") or title_hint),
        }
    )
    section_plan.extend(mid_sections)
    section_plan.append(
        {
            "kind": "facts_decision",
            "focus": str(narrative_mode.get("factsFocus") or "decision_facts"),
            "title": str(narrative_mode.get("factsHeading") or "把关键判断讲清楚"),
        }
    )
    section_plan.append(
        {
            "kind": "closing",
            "focus": str(narrative_mode.get("closingFocus") or "decision"),
            "title": str(narrative_mode.get("closingHeading") or "最后再做决定"),
        }
    )
    return {
        "kind": str(narrative_mode.get("kind") or "structured"),
        "openingFocus": opening_focus,
        "transitionPolicy": str(narrative_mode.get("transitionPolicy") or "sectional"),
        "sectionPlan": section_plan,
        "routeNodes": route_nodes,
        "routeCoverageTarget": route_coverage_expectations.get("minCoveredEntityRefs"),
        "subjectKind": request.subject_kind,
        "subjectType": request.subject_type,
        "intent": request.intent,
    }
