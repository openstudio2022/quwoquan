"""交集信号 intersectionHints ——「明」：讲清楚一篇内容凭什么被推荐。

四原则之「明」：结合推荐与规划，从「交集」角度说明为什么推荐这条内容。
云侧 read model `IntersectionReason`（recommendation-service/contracts/recommendation/recommendation_model_release/projections/
intersection_reason.yaml）是跨会话真相源：端只读展示、禁止本地拼装文案。

post 是内容生产期、没有具体用户，因此只预生成「内容侧可交集锚点」intersectionHints——
使用与契约同一套闭集枚举（dimension/source/actionType）与字段名子集，声明这条内容能从哪些
维度（内容实体/兴趣标签/地域）与用户产生交集；displayText / sharedCount / strength 等个性化
字段由云侧推荐管线在 runtime 据具体用户补全，端再只读展示。

完备性门：每篇内容至少覆盖 content + interest 两个可交集维度，且每条 hint 的枚举合法、
锚点与 manifest.entityRefs / tagRefs 闭环（避免悬空、口径漂移）。
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Mapping

import yaml

from core.paths import service_contracts_root

INTERSECTION_CONTRACT_PATH = (
    service_contracts_root("recommendation-service")
    / "recommendation"
    / "recommendation_feature_profile_view"
    / "projections"
    / "intersection_reason.yaml"
)

# 闭集枚举，对齐 intersection_reason.yaml 的 description（端按字符串解析）。
DIMENSIONS = ("identity", "location", "content", "interest", "relationship")
SOURCES = ("tagRef", "geoTagRef", "entityRef", "relationship", "contact")
ACTION_TYPES = ("follow", "join", "add_contact", "view_object")

# post 内容生产期可预生成的 hint 字段（契约字段子集，个性化字段留给 runtime 补全）。
HINT_FIELDS = ("dimension", "source", "tagRefs", "actionType", "actionTargetId")

# 每篇内容必须覆盖的可交集维度（content=内容实体，interest=兴趣标签）。
REQUIRED_DIMENSIONS = ("content", "interest")
MIN_HINTS = 2


@lru_cache(maxsize=1)
def contract_field_names() -> frozenset[str]:
    """读契约 fields 的字段名集合，作为 hint 字段对齐校验的真相源。"""
    if not INTERSECTION_CONTRACT_PATH.is_file():
        raise FileNotFoundError(
            f"IntersectionReason metadata is required: {INTERSECTION_CONTRACT_PATH}"
        )
    with INTERSECTION_CONTRACT_PATH.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    fields = data.get("fields") or []
    names = frozenset(str(f.get("name")) for f in fields if f.get("name"))
    if not names:
        raise ValueError("IntersectionReason metadata must declare fields")
    return names


def build_intersection_hints(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    """据 manifest 的 entityRefs / tagRefs 预生成内容侧交集锚点。"""
    hints: list[dict[str, Any]] = []
    entity_refs = [str(r) for r in (manifest.get("normalizedEntityRefs") or []) if r]
    tag_refs = [str(t) for t in (manifest.get("tagRefs") or []) if t]

    for ref in entity_refs[:3]:
        hints.append(
            {
                "dimension": "content",
                "source": "entityRef",
                "tagRefs": [],
                "actionType": "view_object",
                "actionTargetId": ref,
            }
        )
    interest_tags = [
        t
        for t in tag_refs
        if t and not t.startswith("地理/")
    ]
    for tag in interest_tags[:3]:
        hints.append(
            {
                "dimension": "interest",
                "source": "tagRef",
                "tagRefs": [tag],
                "actionType": "join",
                "actionTargetId": tag,
            }
        )
    return hints


def intersection_hint_issues(
    hints: Any,
    manifest: Mapping[str, Any],
    *,
    strict_alignment: bool = True,
) -> list[str]:
    """信号完备性 + 闭集合法 + 锚点闭环 + 字段口径对齐校验。"""
    issues: list[str] = []
    if not isinstance(hints, list) or len(hints) < MIN_HINTS:
        issues.append(f"intersectionHints < {MIN_HINTS} (交集信号不足，无法解释推荐理由)")
        hints = hints if isinstance(hints, list) else []

    contract_fields = contract_field_names()
    entity_set = {str(r) for r in (manifest.get("normalizedEntityRefs") or [])}
    tag_set = {str(t) for t in (manifest.get("tagRefs") or [])}
    dims_seen: set[str] = set()

    for hint in hints:
        if not isinstance(hint, Mapping):
            issues.append(f"intersection hint not an object: {hint!r}")
            continue
        if strict_alignment and contract_fields:
            unknown = [k for k in hint if k not in contract_fields]
            if unknown:
                issues.append(f"intersection hint fields off-contract: {unknown}")
        dimension = hint.get("dimension")
        source = hint.get("source")
        action = hint.get("actionType")
        if dimension not in DIMENSIONS:
            issues.append(f"intersection hint.dimension invalid: {dimension}")
        if source not in SOURCES:
            issues.append(f"intersection hint.source invalid: {source}")
        if action not in ACTION_TYPES:
            issues.append(f"intersection hint.actionType invalid: {action}")
        dims_seen.add(str(dimension))
        if source == "entityRef" and str(hint.get("actionTargetId")) not in entity_set:
            issues.append(
                f"entityRef hint target not in manifest.entityRefs: {hint.get('actionTargetId')}"
            )
        if source == "tagRef":
            for tag in hint.get("tagRefs") or []:
                if str(tag) not in tag_set:
                    issues.append(f"tagRef hint tag not in manifest.tagRefs: {tag}")

    for required in REQUIRED_DIMENSIONS:
        if required not in dims_seen:
            issues.append(f"intersection dimension missing: {required} (推荐理由维度不完备)")
    return issues


__all__ = [
    "DIMENSIONS",
    "SOURCES",
    "ACTION_TYPES",
    "HINT_FIELDS",
    "REQUIRED_DIMENSIONS",
    "MIN_HINTS",
    "contract_field_names",
    "build_intersection_hints",
    "intersection_hint_issues",
]
