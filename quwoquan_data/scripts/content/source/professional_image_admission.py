"""Shared non-rights admission gates for professional image assets."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.image_rules import image_caption_quality_issue, relevance_issue

from content.source.research.text_match import _normalized_title


def admit_independently_reviewed_image(
    asset: Mapping[str, Any],
    review_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Admit one exact image only through its independent frozen receipt.

    ``pre_acquisition_block`` remains an acquisition-stage quality filter.  It
    cannot promote an image to release admission.  This seam requires the later
    reviewer receipt and cross-checks every source/rights/CAS field so the
    acquisition writer cannot self-report a second role.
    """

    from content.source.independent_asset_review import (
        IndependentAssetReviewError,
        assert_asset_review_accepted,
    )

    snapshot = review_receipt.get("assetSnapshot")
    if not isinstance(snapshot, Mapping):
        raise IndependentAssetReviewError(
            "professional image independent review lacks assetSnapshot"
        )
    expected = {
        "assetId": str(asset.get("assetId") or "").strip(),
        "entityId": str(asset.get("entityId") or "").strip(),
        "observedEntityId": str(asset.get("observedEntityId") or "").strip(),
        "contentSha256": str(asset.get("contentSha256") or "").strip(),
        "casRef": str(asset.get("assetRef") or "").strip(),
        "sourceUrl": str(asset.get("sourceUrl") or "").strip(),
        "platform": str(asset.get("platform") or "").strip(),
        "creator": str(asset.get("creator") or "").strip(),
        "capturedAt": str(asset.get("capturedAt") or "").strip(),
        "license": str(asset.get("license") or "").strip(),
        "licenseSnapshot": str(asset.get("licenseSnapshot") or "").strip(),
        "usageScope": str(asset.get("usageScope") or "").strip(),
        "modelReleaseStatus": str(asset.get("modelReleaseStatus") or "").strip(),
        "termsUrl": str(asset.get("termsUrl") or "").strip(),
        "authorizationProof": str(asset.get("authorizationProof") or "").strip(),
        "rightsIssues": [
            str(item).strip()
            for item in (asset.get("rightsIssues") or [])
            if str(item).strip()
        ],
        "acquisitionStatus": str(asset.get("acquisitionStatus") or "").strip(),
        "rightsStatus": str(asset.get("rightsStatus") or "").strip(),
        "authorizationRequired": asset.get("authorizationRequired"),
        "distributionDecision": str(asset.get("distributionDecision") or "").strip(),
    }
    if dict(snapshot) != expected:
        raise IndependentAssetReviewError(
            "professional image acquisition/reviewer asset snapshot drift"
        )
    assert_asset_review_accepted(
        review_receipt,
        content_sha256=expected["contentSha256"],
        source_digest=str(review_receipt.get("sourceDigest") or ""),
        asset_id=expected["assetId"],
    )
    return {**dict(asset), "independentAssetReviewId": review_receipt["reviewId"]}


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


__all__ = ["admit_independently_reviewed_image", "pre_acquisition_block"]
