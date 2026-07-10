"""Creator assignment contract shared by content planning, authoring and scale gates."""
from __future__ import annotations

from typing import Any, Mapping


CREATOR_ASSIGNMENT_FIELDS: tuple[str, ...] = (
    "authorId",
    "creatorProfileId",
    "creatorArchetype",
    "creatorProfileVersion",
    "creatorDisclosure",
    "experienceClaimMode",
    "authorQualitySignals",
)

VALID_EXPERIENCE_CLAIM_MODES = {
    "editorial_synthesis",
    "authorized_first_person",
    "public_data_analysis",
    "visual_discovery",
}

COMPACT_CREATOR_PROFILE_VERSION = "compact_profile_v1"
DEFAULT_CREATOR_DISCLOSURE = {
    "type": "platform_virtual_creator",
    "visible": True,
    "displayText": "平台预制创作者",
}


def creator_assignment_required(spec: Mapping[str, Any]) -> bool:
    """Whether content objects must carry a frozen creator assignment.

    Scale workflows can enable this explicitly. Reliable-task authoring also
    requires it because those jobs are expected to be governed end to end.
    """
    policy = spec.get("workflowPolicy") if isinstance(spec.get("workflowPolicy"), Mapping) else {}
    content = spec.get("content") if isinstance(spec.get("content"), Mapping) else {}
    queue_policy = spec.get("queuePolicy") if isinstance(spec.get("queuePolicy"), Mapping) else {}
    content_queue_policy = content.get("queuePolicy") if isinstance(content.get("queuePolicy"), Mapping) else {}
    backend = (
        queue_policy.get("backend")
        or content_queue_policy.get("backend")
        or content.get("queueBackend")
        or spec.get("queueBackend")
    )
    return bool(
        policy.get("requireCreatorAssignment") is True
        or content.get("requireCreatorAssignment") is True
        or backend == "reliabletask"
    )


def creator_from_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Extract platform creator assignment without mixing source-rights creator."""
    nested = payload.get("creator") if isinstance(payload.get("creator"), Mapping) else {}
    row: dict[str, Any] = {}
    for field in CREATOR_ASSIGNMENT_FIELDS:
        value = payload.get(field)
        if value in (None, "", {}):
            value = nested.get(field)
        if value not in (None, "", {}):
            row[field] = value
    profile = _registry_creator(str(row.get("creatorProfileId") or payload.get("creatorProfileId") or nested.get("creatorProfileId") or ""))
    if profile is not None:
        registry_projection = creator_assignment_from_profile(profile)
        if row.get("authorId") and registry_projection.get("authorId") != row.get("authorId"):
            return row
        for field in CREATOR_ASSIGNMENT_FIELDS:
            if row.get(field) in (None, "", {}):
                value = registry_projection.get(field)
                if value not in (None, "", {}):
                    row[field] = value
    return row


def _registry_creator(creator_profile_id: str) -> dict[str, Any] | None:
    if not creator_profile_id:
        return None
    try:
        from template.registry import TemplateRegistry
    except Exception:  # noqa: BLE001
        return None
    try:
        profile = TemplateRegistry.load().creators.get(creator_profile_id)
        if profile is not None:
            return profile
    except Exception:  # noqa: BLE001
        pass
    try:
        from template.registry import CREATORS_ROOT, iter_yaml_files, load_yaml
    except Exception:  # noqa: BLE001
        return None
    for path in iter_yaml_files(CREATORS_ROOT, ".creator.yaml"):
        try:
            data = load_yaml(path)
        except Exception:  # noqa: BLE001
            continue
        if str(data.get("creatorProfileId") or "") == creator_profile_id:
            return data
    try:
        from _common.creator_pool.registry_bridge import travel_creator_batches_root
    except Exception:  # noqa: BLE001
        return None
    for path in iter_yaml_files(travel_creator_batches_root(), ".creator.yaml"):
        try:
            data = load_yaml(path)
        except Exception:  # noqa: BLE001
            continue
        if str(data.get("creatorProfileId") or "") == creator_profile_id:
            return data
    return None


def _disclosure_issues(disclosure: Any, *, prefix: str) -> list[str]:
    if not isinstance(disclosure, Mapping):
        return [f"{prefix}.creatorDisclosure must be an object"]
    issues: list[str] = []
    if disclosure.get("type") != "platform_virtual_creator":
        issues.append(f"{prefix}.creatorDisclosure.type must be platform_virtual_creator")
    if disclosure.get("visible") is not True:
        issues.append(f"{prefix}.creatorDisclosure.visible must be true")
    if not str(disclosure.get("displayText") or "").strip():
        issues.append(f"{prefix}.creatorDisclosure.displayText is required")
    return issues


def _content_signal(payload: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    nested = payload.get("content") if isinstance(payload.get("content"), Mapping) else {}
    subject = payload.get("subject") if isinstance(payload.get("subject"), Mapping) else {}
    for key in keys:
        for source in (payload, nested, subject):
            value = source.get(key)
            if value not in (None, "", [], {}):
                return value
    return None


def _as_str_list(value: Any) -> list[str]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(v) for v in value if str(v).strip()]
    return [str(value)]


def _semantic_consistency_issues(
    registered: Mapping[str, Any],
    *,
    content_vertical: str | None,
    content_region: str | None,
    content_tag_refs: list[str],
    prefix: str,
) -> list[str]:
    """内容 vertical/topic/region 与作者 verticalRefs/coverageScope/tag 的语义一致性门。

    仅在内容携带相应信号时触发；nationwide 作者与命中范围/标签的作者不会被拦。
    与 carrier 硬门互补：拦截"作者覆盖面与内容主题/地域不符"的错误绑定。
    """
    issues: list[str] = []
    vertical_refs = [str(v) for v in (registered.get("verticalRefs") or [])]
    if content_vertical and vertical_refs and content_vertical not in vertical_refs:
        issues.append(
            f"{prefix}.semanticFit: content vertical '{content_vertical}' ∉ creator verticalRefs {vertical_refs}"
        )
    if content_region or content_tag_refs:
        scope = registered.get("coverageScope")
        kind = str(scope.get("kind") or "") if isinstance(scope, Mapping) else ""
        if kind in ("regional", "thematic", "regional_topic"):
            try:
                from template.creator import coverage_range_fit, _tag_overlap

                range_fit = coverage_range_fit(
                    dict(registered), region=content_region, tag_refs=content_tag_refs
                )
                tag_overlap = _tag_overlap(dict(registered), content_tag_refs)
            except Exception:  # noqa: BLE001
                range_fit, tag_overlap = 1.0, 1.0
            if range_fit < 0.5 and tag_overlap <= 0.0:
                signal = content_region or ",".join(content_tag_refs)
                issues.append(
                    f"{prefix}.semanticFit: content topic/region '{signal}' ∉ creator "
                    f"coverageScope({kind})/topic tags (rangeFit={range_fit:.2f})"
                )
    return issues


def creator_assignment_issues(
    payload: Mapping[str, Any],
    *,
    carrier: str | None = None,
    prefix: str = "creatorAssignment",
    require_registered: bool = True,
    content_vertical: str | None = None,
    content_region: str | None = None,
    content_tag_refs: list[str] | None = None,
) -> list[str]:
    """Validate that a content object has a frozen, registry-backed creator.

    When the content carries vertical/region/topic signals (explicit args or
    payload fields), also enforce semantic persona↔content fit so a wrong-coverage
    author is blocked before publish (not only the carrier hard gate).
    """
    creator = creator_from_payload(payload)
    issues: list[str] = []
    for field in CREATOR_ASSIGNMENT_FIELDS:
        if field not in creator:
            issues.append(f"{prefix}.{field} required")
    if issues:
        return issues

    claim_mode = str(creator.get("experienceClaimMode") or "")
    if claim_mode not in VALID_EXPERIENCE_CLAIM_MODES:
        issues.append(f"{prefix}.experienceClaimMode unsupported: {claim_mode or '<missing>'}")
    issues.extend(_disclosure_issues(creator.get("creatorDisclosure"), prefix=prefix))
    signals = creator.get("authorQualitySignals")
    if not isinstance(signals, Mapping):
        issues.append(f"{prefix}.authorQualitySignals must be an object")
    else:
        for field in ("qualityScore", "fatigueScore", "riskTier"):
            if signals.get(field) in (None, ""):
                issues.append(f"{prefix}.authorQualitySignals.{field} required")

    if not require_registered:
        return issues

    registered = _registry_creator(str(creator.get("creatorProfileId") or ""))
    if registered is None:
        issues.append(f"{prefix}.creatorProfileId not found in creator registry")
        return issues
    if str(registered.get("status") or "") != "active":
        issues.append(f"{prefix}.creatorProfileId is not active")
    registered_author_id = str(registered.get("authorId") or registered.get("subAccountId") or "")
    if registered_author_id != str(creator.get("authorId") or ""):
        issues.append(f"{prefix}.authorId does not match creator registry")
    if str(registered.get("creatorArchetype") or "") != str(creator.get("creatorArchetype") or ""):
        issues.append(f"{prefix}.creatorArchetype does not match creator registry")
    if str(_creator_profile_version(registered)) != str(creator.get("creatorProfileVersion") or ""):
        issues.append(f"{prefix}.creatorProfileVersion does not match creator registry")
    if carrier:
        try:
            from template.creator import carrier_affinity
            affinity = carrier_affinity(registered, "image" if carrier == "gallery" else carrier)
        except Exception:  # noqa: BLE001
            affinity = 0.0
        if affinity <= 0:
            issues.append(f"{prefix}.carrierAffinity is zero for carrier={carrier}")

    eff_vertical = content_vertical or (
        str(_content_signal(payload, ("vertical", "contentVertical")) or "") or None
    )
    eff_region = content_region or (
        str(_content_signal(payload, ("region", "regionRef", "coverageRegion")) or "") or None
    )
    eff_tag_refs = content_tag_refs if content_tag_refs is not None else _as_str_list(
        _content_signal(payload, ("tagRefs", "topicRefs", "primaryTagRefs"))
    )
    if eff_vertical or eff_region or eff_tag_refs:
        issues.extend(
            _semantic_consistency_issues(
                registered,
                content_vertical=eff_vertical,
                content_region=eff_region,
                content_tag_refs=eff_tag_refs,
                prefix=prefix,
            )
        )
    return issues


def creator_assignment_from_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Project a registry profile into content-object creator assignment fields."""
    return {
        "authorId": profile.get("authorId") or profile.get("subAccountId"),
        "creatorProfileId": profile.get("creatorProfileId"),
        "creatorArchetype": profile.get("creatorArchetype"),
        "creatorProfileVersion": _creator_profile_version(profile),
        "creatorDisclosure": profile.get("disclosure") if isinstance(profile.get("disclosure"), Mapping) else DEFAULT_CREATOR_DISCLOSURE,
        "experienceClaimMode": _experience_claim_mode(profile),
        "authorQualitySignals": {
            "qualityScore": profile.get("qualityScore", 0.8),
            "fatigueScore": profile.get("fatigueScore", 0.2),
            "riskTier": profile.get("riskTier") or "low",
        },
    }


def _creator_profile_version(profile: Mapping[str, Any]) -> str:
    return str(profile.get("profileVersion") or COMPACT_CREATOR_PROFILE_VERSION)


def _experience_claim_mode(profile: Mapping[str, Any]) -> str:
    claim_policy = profile.get("claimPolicy") if isinstance(profile.get("claimPolicy"), Mapping) else {}
    return str(claim_policy.get("experienceClaimMode") or "editorial_synthesis")


def resolve_registry_creator_assignment(
    blueprint: Mapping[str, Any] | None = None,
    *,
    carrier: str,
    region: str | None = None,
    vertical: str | None = None,
    tag_refs: list[str] | None = None,
    preferred_archetype: str | None = None,
    seed: str = "",
    selection_mode: str = "best",
    registry: Any = None,
) -> dict[str, Any]:
    """Single source of truth for resolving a registered platform creator.

    Deterministically (by ``seed``) matches an active registered creator by content
    carrier / region / vertical and projects it into content-object creator
    assignment fields. Shared by single-mode managed runs and fan-out dispatch so
    both paths attribute the same author for the same content object (R24/R25).

    Returns ``{}`` gracefully when the template registry or a match is unavailable
    (e.g. dev/mock without a creator registry), so callers never crash.
    """
    try:
        from template.creator import match_creator
    except Exception:  # noqa: BLE001
        return {}
    if registry is None:
        try:
            from template.registry import TemplateRegistry

            registry = TemplateRegistry.load()
        except Exception:  # noqa: BLE001
            return {}
    if not getattr(registry, "creators", None):
        return {}
    try:
        creator = match_creator(
            registry,
            dict(blueprint or {}),
            carrier=carrier,
            tag_refs=tag_refs,
            region=region,
            vertical=vertical,
            seed=seed,
            preferred_archetype=preferred_archetype,
            selection_mode=selection_mode,
        )
    except Exception:  # noqa: BLE001
        return {}
    if not creator:
        return {}
    return creator_assignment_from_profile(creator)
