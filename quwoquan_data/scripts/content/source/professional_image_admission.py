"""Shared non-rights admission gates for professional image assets."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.image_rules import image_caption_quality_issue, relevance_issue

from content.source.research.text_match import _normalized_title


def pre_acquisition_block(item: Mapping[str, Any]) -> tuple[str, str]:
    """Return one typed safety/entity/relevance blocker before acceptance."""

    access = item["accessEvidence"]
    if any(
        bool(access[field])
        for field in (
            "loginRequired",
            "captchaRequired",
            "paywallRequired",
            "drmProtected",
            "accessControlBypass",
        )
    ):
        return "DATA.SOURCE.ACCESS_CONTROL_BLOCKED", "access barrier or bypass declared"
    if item["acquisitionPath"] != "manual_file" and not access["anonymousAssetAccess"]:
        return (
            "DATA.SOURCE.ANONYMOUS_ACCESS_REQUIRED",
            "network image is not anonymously accessible",
        )
    review = item["safetyReview"]
    if review["status"] != "passed":
        return "DATA.SOURCE.SAFETY_REVIEW_BLOCKED", "safety review is not passed"
    if review["entityMatch"] != "matched":
        return "DATA.SOURCE.ENTITY_MISMATCH", "safety review entity does not match"
    if any(
        review[field] != "none"
        for field in ("privacyRisk", "minorRisk", "maliciousMediaRisk")
    ):
        return (
            "DATA.SOURCE.SAFETY_RISK_BLOCKED",
            "privacy, minor or malicious-media risk",
        )
    if review["watermarkStatus"] != "absent":
        return "DATA.SOURCE.WATERMARK_BLOCKED", "watermark is present or unknown"
    entity_key = _normalized_title(str(item["entityId"]))
    observed_key = _normalized_title(str(item["observedEntityId"]))
    identity_keys = {
        _normalized_title(value)
        for value in [item["entityId"], *item["entityAliases"]]
        if _normalized_title(value)
    }
    if not entity_key or observed_key not in identity_keys:
        return (
            "DATA.SOURCE.ENTITY_MISMATCH",
            "observedEntityId is outside the canonical entity alias closure",
        )
    evidence_key = _normalized_title(f"{item['caption']} {item['relevance']}")
    if not any(alias in evidence_key for alias in identity_keys):
        return (
            "DATA.SOURCE.ENTITY_MISMATCH",
            "caption and relevance do not identify entity",
        )
    relevance_problem = relevance_issue(
        str(item["relevance"]),
        entity_id=str(item["entityId"]),
        asset_id=str(item["assetId"]),
    )
    caption_problem = image_caption_quality_issue(
        str(item["caption"]),
        entity_id=str(item["entityId"]),
        asset_id=str(item["assetId"]),
    )
    if relevance_problem or caption_problem:
        return (
            "DATA.SOURCE.IMAGE_QUALITY_BLOCKED",
            relevance_problem or caption_problem or "image quality review failed",
        )
    return "", ""


__all__ = ["pre_acquisition_block"]
