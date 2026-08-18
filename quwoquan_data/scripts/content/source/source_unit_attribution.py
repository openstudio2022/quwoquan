"""Resolve the source-unit attribution that pool delivery later requires."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# article/homepage 的 post manifest 必须携带 sourceAttribution，而它只能从来源单元
# 继承。站点标识与来源类别两套词汇都可能出现在采集载荷里，所以两者都登记。
ENCYCLOPEDIA_ATTRIBUTION_SITES = {
    "wikipedia_zh": "wikipedia",
    "wikipedia": "wikipedia",
    "baidu_baike": "baidu_baike",
    "toutiao_baike": "toutiao_baike",
}
ATTRIBUTION_REQUIRED_LANES = {"homepage", "article"}


def attribution_required(research_lane: str) -> bool:
    """Whether this lane's post manifest inherits ``sourceAttribution``."""
    return str(research_lane or "").strip() in ATTRIBUTION_REQUIRED_LANES


def resolve_source_unit_kind(
    *,
    source_kind: str = "",
    source_payload: Mapping[str, Any] | None = None,
    source_category: str = "",
    platform: str = "",
) -> str:
    """Derive the manifest ``sourceKind`` exactly as ``write_source_unit`` records it.

    Admission checks that run before the unit is written must classify a source
    by the identity the manifest will carry, otherwise the pre-check and the
    writer disagree about which attribution contract applies.
    """
    return (
        str(source_kind or "").strip()
        or str((source_payload or {}).get("sourceKind") or "").strip()
        or source_category
        or platform
        or "web"
    )


def registered_attribution_kind(
    source_payload: Mapping[str, Any],
    *,
    resolved_source_kind: str,
) -> str | None:
    """Return the registered encyclopedia kind, or ``None`` when unregistered.

    Site identity and source category are two separate vocabularies in the
    acquisition payload, so both are looked up. ``None`` is the absent-mapping
    verdict, not a failure: callers decide whether an unregistered site rejects
    one source unit or fails the whole delivery contract.
    """
    site_id = str(source_payload.get("articleSiteId") or "").strip()
    return ENCYCLOPEDIA_ATTRIBUTION_SITES.get(
        site_id
    ) or ENCYCLOPEDIA_ATTRIBUTION_SITES.get(str(resolved_source_kind or "").strip())


def unresolvable_attribution_detail(
    source_payload: Mapping[str, Any],
    *,
    research_lane: str,
    resolved_source_kind: str,
) -> str:
    """Render the audit text naming both sides of an attribution mismatch."""
    site_id = str(source_payload.get("articleSiteId") or "").strip()
    return (
        "sourceAttribution cannot be resolved for "
        f"lane={research_lane} articleSiteId={site_id!r} "
        f"sourceKind={resolved_source_kind!r}"
    )


def resolve_source_unit_attribution(
    source_payload: Mapping[str, Any],
    *,
    research_lane: str,
    resolved_source_kind: str,
    source_url: str,
    captured_at: str,
) -> dict[str, Any] | None:
    """Resolve the attribution pool delivery requires, or fail closed.

    Returning ``None`` is only valid for carriers whose post manifest never
    reaches this contract. For article and homepage an unmapped site must raise
    here, because silently omitting the field defers the gap to publish closure
    where it surfaces as an unattributable OBJECT_PREPARATION_FAILED.
    """
    if not attribution_required(research_lane):
        return None
    kind = registered_attribution_kind(
        source_payload,
        resolved_source_kind=resolved_source_kind,
    )
    if kind is None:
        raise ValueError(
            unresolvable_attribution_detail(
                source_payload,
                research_lane=research_lane,
                resolved_source_kind=resolved_source_kind,
            )
        )
    from content.source.research.homepage_article_source_attribution import (
        encyclopedia_source_attribution,
    )

    return encyclopedia_source_attribution(
        source_kind=kind,
        source_url=source_url,
        captured_at=captured_at,
    )


__all__ = [
    "ATTRIBUTION_REQUIRED_LANES",
    "ENCYCLOPEDIA_ATTRIBUTION_SITES",
    "attribution_required",
    "registered_attribution_kind",
    "resolve_source_unit_attribution",
    "resolve_source_unit_kind",
    "unresolvable_attribution_detail",
]
