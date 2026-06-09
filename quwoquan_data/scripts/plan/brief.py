"""Compose brief generation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from _common.io import read_json
from _common.paths import PUBLISH_ROOT, TASKS_ROOT
from _common.quality_gates import normalize_writing_intent
from template.blueprint import collect_tag_refs
from template.recommend import build_recommendation_manifest
from template.registry import TemplateRegistry
from template.router import RouteRequest, resolve_route


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
    condition = _resolve_condition(registry, blueprint, request, entity_refs=refs)
    if condition["tagRefs"]:
        tag_refs = [t for t in dict.fromkeys(tag_refs + condition["tagRefs"]) if t and t != "None"]
    must_include = _dedupe(list(blueprint.get("mustIncludeFacts", [])) + condition["facts"])
    image_plan = list(blueprint.get("imagePlan", [])) + condition["imageSlots"]
    narrative_mode = _normalize_optional_mapping(blueprint.get("narrativeMode"))
    evidence_requirements = _normalize_optional_mapping(blueprint.get("evidenceRequirements"))
    continuity_expectations = _normalize_optional_mapping(blueprint.get("continuityExpectations"))
    route_coverage_expectations = _normalize_optional_mapping(blueprint.get("routeCoverageExpectations"))
    recommendation = build_recommendation_manifest(
        registry, blueprint, subject, refs, tag_refs, condition_context=condition["context"]
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
        },
        "render": blueprint.get("render"),
        "structure": blueprint.get("structure"),
        "conditionAxes": blueprint.get("conditionAxes"),
        "conditionContext": condition["context"],
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
        "hooks": blueprint.get("hooks", []),
        "mustIncludeFacts": must_include,
        "forbiddenPhrases": blueprint.get("forbiddenPhrases", []),
        "wordCount": blueprint.get("wordCount"),
        "imagePlan": image_plan,
        "crossRefs": blueprint.get("crossRefs"),
        "tagRefs": tag_refs,
        "recommendation": recommendation,
        "sopExampleRef": blueprint.get("sopExampleRef"),
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


def _entity_condition_profile(entity_ref: str) -> dict[str, Any] | None:
    """L3：按 entityRef（形如 地点/景区/稻城亚丁，可含 /entity/ 前缀）读取实体真实条件画像。

    从实体 _entity.json 的 conditionProfile 取真实地形(regions)/最佳季节(seasons)/海拔，
    publish 单一主线优先，回退任意 runtime task；缺失或无 regions/seasons 时返回 None。
    """
    parts = [p for p in str(entity_ref).strip().strip("/").split("/") if p]
    if parts and parts[0] == "entity":
        parts = parts[1:]
    if len(parts) < 3:
        return None
    domain, etype, name = parts[0], parts[1], "/".join(parts[2:])
    rel = Path("entities") / domain / etype / name / "_entity.json"
    candidates: list[Path] = [PUBLISH_ROOT / rel]
    if TASKS_ROOT.exists():
        candidates.extend(sorted(TASKS_ROOT.rglob(str(rel))))
    for path in candidates:
        if not path.is_file():
            continue
        try:
            data = read_json(path)
        except Exception:
            continue
        profile = data.get("conditionProfile") if isinstance(data, dict) else None
        if isinstance(profile, dict) and (profile.get("regions") or profile.get("seasons")):
            return profile
    return None


def _resolve_condition(
    registry: TemplateRegistry,
    blueprint: dict[str, Any],
    request: RouteRequest,
    entity_refs: list[str] | None = None,
) -> dict[str, Any]:
    """按 region/season 从 catalog 注入条件化 facts/图位/标签，并产出 conditionContext。

    分层取值（覆盖广 + 精确）：
    - 模板保持地域/季节无关：仅当 conditionAxes 声明 applicable 时才注入 catalog facts/图位。
    - effective region/season：显式 request.region/season（最高） > 实体 conditionProfile 主值 > 无。
    - entity 模式下实体真实画像（多地形/最佳季节/海拔）始终注入 context.entityProfile，
      独立于模板敏感性，让正文事实精确；缺失实体画像时回退地域全谱并记 entityProfileFallback。
    """
    axes = blueprint.get("conditionAxes") or {}
    facts: list[str] = []
    image_slots: list[dict[str, Any]] = []
    tag_refs: list[str] = []
    context: dict[str, Any] = {}

    refs = [r for r in (entity_refs or []) if r]
    entity_profile: dict[str, Any] | None = None
    if request.subject_kind == "entity" and refs:
        entity_profile = _entity_condition_profile(refs[0])
    profile_regions = [str(r) for r in (entity_profile or {}).get("regions") or []]
    profile_seasons = [str(s) for s in (entity_profile or {}).get("seasons") or []]
    eff_region = request.region or (profile_regions[0] if profile_regions else None)
    eff_season = request.season or (profile_seasons[0] if profile_seasons else None)

    region_axis = axes.get("region") or {}
    if eff_region and region_axis.get("applicable"):
        regions = registry.catalogs.get("region_catalog", {}).get("regions", {})
        profile = regions.get(eff_region)
        if profile:
            facts.extend(str(f) for f in profile.get("conditionFacts", []))
            for hint in profile.get("imageHints", []):
                image_slots.append({"slot": str(hint), "imageLayout": "wrapRight", "conditionSource": "region"})
            tag_refs.extend(str(t) for t in profile.get("tagRefs", []))
            context["region"] = {
                "name": eff_region,
                "label": profile.get("label"),
                "slot": region_axis.get("slot"),
                "packing": profile.get("packing", []),
                "riskNotes": profile.get("riskNotes", []),
                "source": "request" if request.region else ("entityProfile" if profile_regions else "request"),
            }

    season_axis = axes.get("season") or {}
    if eff_season and season_axis.get("applicable"):
        seasons = registry.catalogs.get("season_catalog", {}).get("seasons", {})
        profile = seasons.get(eff_season)
        if profile:
            facts.extend(str(f) for f in profile.get("conditionFacts", []))
            for hint in profile.get("imageHints", []):
                image_slots.append({"slot": str(hint), "imageLayout": "wrapLeft", "conditionSource": "season"})
            tag_refs.extend(str(t) for t in profile.get("tagRefs", []))
            context["season"] = {
                "name": eff_season,
                "label": profile.get("label"),
                "slot": season_axis.get("slot"),
                "packing": profile.get("packing", []),
                "crowdNotes": profile.get("crowdNotes", []),
                "source": "request" if request.season else ("entityProfile" if profile_seasons else "request"),
            }

    if entity_profile:
        context["entityProfile"] = {
            "entityRef": refs[0],
            "regions": profile_regions,
            "seasons": profile_seasons,
            "altitudeMeters": entity_profile.get("altitudeMeters"),
            "notes": entity_profile.get("notes"),
            "conditionSource": "entityConditionProfile",
        }
    elif request.subject_kind == "entity" and refs:
        context["entityProfileFallback"] = {
            "entityRef": refs[0],
            "reason": "no_condition_profile; uses region/season menu",
        }

    return {"facts": facts, "imageSlots": image_slots, "tagRefs": tag_refs, "context": context}


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
