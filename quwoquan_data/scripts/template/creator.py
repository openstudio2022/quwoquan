"""System builtin creator profile matching and validation."""
from __future__ import annotations

import hashlib
import re
from typing import Any

from _common.creator_pool.constants import PHOTOGRAPHY_TOPIC_REFS, TRAVEL_TOPIC_REFS
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
VALID_COVERAGE_KINDS = {"nationwide", "regional", "thematic", "regional_topic"}
_CARRIER_KEYS = ("article", "image", "video")
SYS_CREATOR_ID_RE = re.compile(r"^sys_(travel|photo|travelphoto)_[0-9]{4}$")
PUBLISHED_INTEREST_TAGS = frozenset((*TRAVEL_TOPIC_REFS, *PHOTOGRAPHY_TOPIC_REFS))
FORBIDDEN_SYS_CREATOR_FIELDS = (
    "legacyAliases",
    "archiveAliases",
    "avatarObjectKey",
    "backgroundObjectKey",
    "coverObjectKey",
    "ipLocation",
    "provenance",
    "operations",
)


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
        errors.extend(_sys_creator_hard_gate_errors(creator, label))

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

        errors.extend(_coverage_scope_errors(creator.get("coverageScope"), label))
        errors.extend(_carrier_affinity_errors(creator.get("carrierAffinity"), label))

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


def _coverage_scope_errors(scope: Any, label: str) -> list[str]:
    if not isinstance(scope, dict):
        return [f"{label}: coverageScope must be an object"]
    errors: list[str] = []
    kind = str(scope.get("kind") or "")
    if kind not in VALID_COVERAGE_KINDS:
        errors.append(f"{label}: unsupported coverageScope.kind '{kind}'")
    if kind == "regional" and not scope.get("regionRefs"):
        errors.append(f"{label}: regional coverageScope requires regionRefs")
    if kind == "thematic" and not (scope.get("topicRefs") or scope.get("regionRefs")):
        errors.append(f"{label}: thematic coverageScope requires topicRefs")
    return errors


def _sys_creator_hard_gate_errors(creator: dict[str, Any], label: str) -> list[str]:
    creator_id = str(creator.get("creatorProfileId") or "")
    if not creator_id.startswith("sys_"):
        return []
    errors: list[str] = []
    if not SYS_CREATOR_ID_RE.match(creator_id):
        errors.append(f"{label}: creatorProfileId must match sys travel/photo pattern")
    if len(creator_id) > 32:
        errors.append(f"{label}: creatorProfileId must be <= 32 chars")
    sub_id = str(creator.get("subAccountId") or creator.get("authorId") or "")
    if sub_id != f"{creator_id}_sub_01":
        errors.append(f"{label}: subAccountId/authorId must equal {creator_id}_sub_01")
    if len(sub_id) > 32:
        errors.append(f"{label}: subAccountId must be <= 32 chars")
    if re.search(r"\d", str(creator.get("displayName") or "")):
        errors.append(f"{label}: displayName must not contain digits")
    for field in FORBIDDEN_SYS_CREATOR_FIELDS:
        if field in creator:
            errors.append(f"{label}: forbidden field {field}")
    for bucket in ("interestTagRefs", "recommendationTagRefs"):
        for tag_ref in creator.get(bucket) or []:
            tag = str(tag_ref)
            if tag.startswith("Topic/") and tag not in PUBLISHED_INTEREST_TAGS:
                errors.append(f"{label}: {bucket} contains unpublished leaf tag {tag}")
    return errors


def _carrier_affinity_errors(aff: Any, label: str) -> list[str]:
    if not isinstance(aff, dict):
        return [f"{label}: carrierAffinity must be an object"]
    errors: list[str] = []
    positive = False
    for carrier_key in _CARRIER_KEYS:
        if carrier_key not in aff:
            errors.append(f"{label}: carrierAffinity missing '{carrier_key}'")
            continue
        try:
            value = float(aff.get(carrier_key))
        except (TypeError, ValueError):
            errors.append(f"{label}: carrierAffinity.{carrier_key} must be a number")
            continue
        if value < 0 or value > 1:
            errors.append(f"{label}: carrierAffinity.{carrier_key} must be within 0..1")
        if value > 0:
            positive = True
    if not errors and not positive:
        errors.append(f"{label}: carrierAffinity must have at least one carrier > 0")
    return errors


def carrier_affinity(creator: dict[str, Any], carrier: str) -> float:
    aff = creator.get("carrierAffinity")
    if not isinstance(aff, dict):
        return 0.0
    try:
        return float(aff.get(carrier, 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _tag_prefix_hit(scope_refs: list[str], tags: list[str], region_name: str) -> bool:
    """范围 ref 命中：与内容标签互为前缀（行政区/题材树自上而下），或与 region 名相关。"""
    for ref in scope_refs:
        if region_name and (ref.endswith(region_name) or region_name and region_name in ref):
            return True
        for tag in tags:
            if tag == ref or tag.startswith(ref + "/") or ref.startswith(tag + "/"):
                return True
    return False


def coverage_range_fit(creator: dict[str, Any], *, region: str | None, tag_refs: list[str] | None) -> float:
    """范围契合度 [0,1]：nationwide 给中性基线；regional/thematic 命中给高分、未命中给低分。

    使「川西范围」作者只在川西内容上胜出，「全国」作者在无地域信号或跨地域时胜出。
    """
    scope = creator.get("coverageScope")
    if not isinstance(scope, dict):
        return 0.5
    kind = str(scope.get("kind") or "")
    if kind == "nationwide":
        return 0.6
    tags = [str(t) for t in (tag_refs or [])]
    region_name = str(region or "")
    region_refs = [str(x) for x in (scope.get("regionRefs") or []) if x]
    topic_refs = [str(x) for x in (scope.get("topicRefs") or []) if x]
    if _tag_prefix_hit(region_refs, tags, region_name):
        return 1.0
    if _tag_prefix_hit(topic_refs, tags, region_name):
        return 1.0
    return 0.1


def _tag_overlap(creator: dict[str, Any], tag_refs: list[str] | None) -> float:
    content = {str(t) for t in (tag_refs or [])}
    if not content:
        return 0.0
    creator_tags = {str(t) for t in creator.get("publicProfileTagRefs", [])}
    creator_tags |= {str(t) for t in creator.get("recommendationTagRefs", [])}
    if not creator_tags:
        return 0.0
    return len(creator_tags & content) / len(content)


def _stable_jitter(creator_id: str, seed: str) -> float:
    digest = hashlib.sha1(f"{seed}|{creator_id}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def blueprint_preference_fit(creator: dict[str, Any], blueprint_id: str | None) -> float:
    """1.0 当 blueprint.templateId ∈ creator.preferredBlueprintIds（软偏好），否则 0.0。

    让 persona 的 preferredBlueprintIds 真正参与路由：同 archetype/载体候选里，
    显式偏好该蓝图的作者优先胜出，而不再是死元数据。
    """
    if not blueprint_id:
        return 0.0
    preferred = {str(b) for b in (creator.get("preferredBlueprintIds") or [])}
    return 1.0 if blueprint_id in preferred else 0.0


def _creator_match_score(
    creator: dict[str, Any],
    *,
    carrier: str,
    tag_refs: list[str] | None,
    region: str | None,
    vertical: str | None,
    seed: str,
    blueprint_id: str | None = None,
) -> float:
    range_fit = coverage_range_fit(creator, region=region, tag_refs=tag_refs)
    affinity = carrier_affinity(creator, carrier)
    tag_fit = _tag_overlap(creator, tag_refs)
    quality = float(creator.get("qualityScore") or 0.0)
    fatigue = float(creator.get("fatigueScore") or 0.0)
    vertical_fit = 1.0 if (vertical and vertical in [str(v) for v in creator.get("verticalRefs", [])]) else 0.0
    blueprint_fit = blueprint_preference_fit(creator, blueprint_id)
    jitter = _stable_jitter(str(creator.get("creatorProfileId") or ""), seed)
    return (
        3.0 * range_fit
        + 2.0 * affinity
        + 1.5 * tag_fit
        + 1.2 * blueprint_fit
        + 0.5 * vertical_fit
        + 1.0 * quality
        - 1.0 * fatigue
        + 0.2 * jitter
    )


def match_creator(
    registry: TemplateRegistry,
    blueprint: dict[str, Any],
    *,
    carrier: str | None = None,
    tag_refs: list[str] | None = None,
    region: str | None = None,
    vertical: str | None = None,
    seed: str = "",
    preferred_archetype: str | None = None,
    selection_mode: str = "best",
) -> dict[str, Any]:
    """按底稿内容信号在「合适的虚拟作者」中择优，避免随意安排。

    选择逻辑（archetype 为主轴，范围/载体在同 archetype 内择优）：
      1. blueprint 显式 preferredCreatorIds 优先。
      2. 主轴：取该 archetype 的 active 候选；按载体偏向>0 硬过滤。
      3. 同 archetype 内按「范围契合 + 载体偏向 + 标签重叠 + vertical + 质量 - 疲劳 + 稳定抖动」评分择优。
      4. archetype 无候选时跨 archetype 回退，仍按载体偏向与评分择优。
    seed（建议传内容 ref/subject）保证同一内容确定性命中同一作者，并在等分作者间分摊负载。
    """
    persona = blueprint.get("creatorPersona") if isinstance(blueprint.get("creatorPersona"), dict) else {}
    for creator_id in (str(x) for x in persona.get("preferredCreatorIds", [])):
        if creator_id in registry.creators:
            return registry.creators[creator_id]

    archetype = preferred_archetype or str(persona.get("archetype", ""))
    eff_carrier = str(carrier or blueprint.get("carrier") or "article")
    blueprint_id = str(blueprint.get("templateId") or "")

    def is_active(creator: dict[str, Any]) -> bool:
        return str(creator.get("status") or "") == "active"

    pool = [c for c in registry.creators_by_archetype(archetype) if is_active(c)]
    carrier_pool = [c for c in pool if carrier_affinity(c, eff_carrier) > 0]
    candidates = carrier_pool or pool
    if not candidates:
        all_active = [c for c in registry.creators.values() if is_active(c)]
        carrier_all = [c for c in all_active if carrier_affinity(c, eff_carrier) > 0]
        candidates = carrier_all or all_active
    if not candidates:
        if registry.creators:
            return next(iter(registry.creators.values()))
        raise ValueError("No creator profiles available")
    if len(candidates) == 1:
        return candidates[0]

    scored = [
        (
            _creator_match_score(
                c,
                carrier=eff_carrier,
                tag_refs=tag_refs,
                region=region,
                vertical=vertical,
                seed=seed,
                blueprint_id=blueprint_id,
            ),
            c,
        )
        for c in candidates
    ]
    if str(selection_mode or "best") != "spread":
        return max(scored, key=lambda row: row[0])[1]

    max_score = max(score for score, _ in scored)
    viable = [
        c
        for score, c in scored
        if score >= max_score - 1.25
        and (
            not vertical
            or not c.get("verticalRefs")
            or vertical in [str(v) for v in c.get("verticalRefs", [])]
        )
    ]
    if not viable:
        viable = [c for _, c in scored]
    return max(viable, key=lambda c: _stable_jitter(str(c.get("creatorProfileId") or ""), seed))


def choose_creator(registry: TemplateRegistry, blueprint: dict[str, Any], preferred_archetype: str | None = None) -> dict[str, Any]:
    """无内容信号的稳定选择（兼容旧调用方）：委托 match_creator，仅按 archetype + 载体 + 质量择优。"""
    return match_creator(registry, blueprint, preferred_archetype=preferred_archetype)
