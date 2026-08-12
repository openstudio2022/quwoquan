"""Resolve campaign scale labels and quotas from the control-plane catalog."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from content.execution.identity import parse_execution_id
from core.paths import REPO_DATA_ROOT

SCALE_CATALOG_PATH = REPO_DATA_ROOT / "control_plane" / "campaigns" / "scale_catalog.yaml"
_SCALE_RE = re.compile(r"^M([1-9][0-9]{0,5})$")
_CAMPAIGN_CARRIERS = ("homepage", "article", "image", "video")
_GOVERNED_RESEARCH_SCALES = frozenset({"M100", "M1000", "M10000"})
_EXECUTION_SCALE_INTENT_RE = re.compile(r"^m(?P<count>[1-9][0-9]{0,5})$")


@dataclass(frozen=True, slots=True)
class ResolvedCampaignScale:
    scale: str
    quota: int


class CampaignScaleError(ValueError):
    """Invalid campaign scale or minimum workload floor (GATE_BLOCK)."""


@lru_cache(maxsize=1)
def load_scale_catalog() -> dict[str, Any]:
    if not SCALE_CATALOG_PATH.is_file():
        raise CampaignScaleError(
            f"GATE_BLOCK campaign scale catalog missing: {SCALE_CATALOG_PATH}"
        )
    raw = yaml.safe_load(SCALE_CATALOG_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise CampaignScaleError("GATE_BLOCK campaign scale catalog must be a mapping")
    min_quota = int(raw.get("minQuota") or 1)
    max_quota = int(raw.get("maxQuota") or 100000)
    if min_quota < 1 or max_quota < min_quota:
        raise CampaignScaleError(
            "GATE_BLOCK campaign scale catalog minQuota/maxQuota invalid"
        )
    named = raw.get("namedScales") or {}
    if not isinstance(named, dict) or not named:
        raise CampaignScaleError(
            "GATE_BLOCK campaign scale catalog namedScales must be a non-empty mapping"
        )
    resolved_named: dict[str, int] = {}
    for name, body in named.items():
        label = str(name).strip()
        match = _SCALE_RE.fullmatch(label)
        if match is None:
            raise CampaignScaleError(
                f"GATE_BLOCK named scale label invalid: {label}"
            )
        if not isinstance(body, dict) or "quota" not in body:
            raise CampaignScaleError(
                f"GATE_BLOCK named scale {label} requires quota"
            )
        quota = int(body["quota"])
        if quota != int(match.group(1)):
            raise CampaignScaleError(
                f"GATE_BLOCK named scale {label} quota {quota} must equal label number"
            )
        if not (min_quota <= quota <= max_quota):
            raise CampaignScaleError(
                f"GATE_BLOCK named scale {label} quota {quota} outside "
                f"[{min_quota}, {max_quota}]"
            )
        resolved_named[label] = quota
    return {
        "minQuota": min_quota,
        "maxQuota": max_quota,
        "namedScales": resolved_named,
    }


def clear_scale_catalog_cache() -> None:
    load_scale_catalog.cache_clear()


def _bound_quota(quota: int, *, min_quota: int, max_quota: int) -> int:
    if isinstance(quota, bool) or not isinstance(quota, int):
        raise CampaignScaleError("GATE_BLOCK campaign quota must be an integer")
    if quota < min_quota or quota > max_quota:
        raise CampaignScaleError(
            f"GATE_BLOCK campaign quota {quota} outside [{min_quota}, {max_quota}]"
        )
    return quota


def resolve_campaign_scale(
    *,
    scale: str | None = None,
    quota: int | None = None,
) -> ResolvedCampaignScale:
    """Resolve a named preset, arbitrary M{n}, or explicit quota into scale+quota."""

    catalog = load_scale_catalog()
    min_quota = int(catalog["minQuota"])
    max_quota = int(catalog["maxQuota"])
    named: dict[str, int] = catalog["namedScales"]

    if scale is not None and str(scale).strip():
        label = str(scale).strip()
        match = _SCALE_RE.fullmatch(label)
        if match is None:
            raise CampaignScaleError(
                f"GATE_BLOCK unsupported campaign scale: {label}"
            )
        derived = int(match.group(1))
        if label in named:
            derived = named[label]
        else:
            derived = _bound_quota(derived, min_quota=min_quota, max_quota=max_quota)
        if quota is not None:
            explicit = _bound_quota(int(quota), min_quota=min_quota, max_quota=max_quota)
            if explicit != derived:
                raise CampaignScaleError(
                    f"GATE_BLOCK scale {label} conflicts with quota {explicit}"
                )
        return ResolvedCampaignScale(scale=f"M{derived}", quota=derived)

    if quota is None:
        raise CampaignScaleError(
            "GATE_BLOCK campaign scale requires scale= or quota="
        )
    explicit = _bound_quota(int(quota), min_quota=min_quota, max_quota=max_quota)
    return ResolvedCampaignScale(scale=f"M{explicit}", quota=explicit)


def campaign_workload_targets(scale: str) -> dict[str, int]:
    """Resolve the canonical per-carrier minimum for one campaign scale.

    Governed research milestones deliberately do not use the numeric scale as
    the video workload.  Keeping this decision here prevents M10000 from
    silently raising the video floor from 1000 to 10000.  These values never
    truncate a full frontier: every additional qualified object remains
    admissible and publishable.
    """

    resolved = resolve_campaign_scale(scale=scale)
    if resolved.scale not in _GOVERNED_RESEARCH_SCALES:
        return {carrier: resolved.quota for carrier in _CAMPAIGN_CARRIERS}

    # Imported lazily so the low-level scale parser remains usable while the
    # governance package imports execution helpers during verifier startup.
    from governance.coverage.distribution import load_content_distribution_policy

    policy = load_content_distribution_policy()
    return {
        carrier: policy.scale_target(resolved.scale, carrier)
        for carrier in _CAMPAIGN_CARRIERS
    }


def execution_campaign_scale(execution_id: str, *, quota: int) -> str:
    """Derive one campaign scale from immutable intent or non-milestone quota.

    Milestone video quotas deliberately differ from their campaign scale, so
    quota is authoritative only when the execution intent is not ``m<N>``.
    """

    identity = parse_execution_id(execution_id)
    match = _EXECUTION_SCALE_INTENT_RE.fullmatch(identity.intent)
    if match is not None:
        return resolve_campaign_scale(scale=f"M{match.group('count')}").scale
    return resolve_campaign_scale(quota=quota).scale


__all__ = [
    "CampaignScaleError",
    "ResolvedCampaignScale",
    "SCALE_CATALOG_PATH",
    "clear_scale_catalog_cache",
    "campaign_workload_targets",
    "execution_campaign_scale",
    "load_scale_catalog",
    "resolve_campaign_scale",
]
