"""Bind professional image acquisition facts to canonical SourceAttribution."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.source_attribution import canonical_source_attribution


def bound_image_source_attribution(
    item: Mapping[str, Any],
    *,
    platform: str,
    distribution_decision: str,
) -> dict[str, Any]:
    attribution = canonical_source_attribution(item.get("sourceAttribution"))
    source_url = str(item.get("sourceUrl") or "")
    original_url = str(item.get("assetUrl") or source_url)
    proof = str(item.get("authorizationProof") or "").strip()
    terms = str(item.get("termsUrl") or "").strip()
    expected: dict[str, object] = {
        "isOriginal": False,
        "originalCreatorName": str(item.get("creator") or ""),
        "platform": platform,
        "sourcePostUrl": source_url,
        "originalAssetUrl": original_url,
        "rightsBasis": str(item.get("license") or ""),
        "authorizationProofUrl": proof if proof.startswith("https://") else None,
        "termsUrl": terms if terms.startswith("https://") else None,
        "watermarkStatus": str((item.get("safetyReview") or {}).get("watermarkStatus") or ""),
        "audioRightsStatus": "no_audio",
        "modelReleaseStatus": str(item.get("modelReleaseStatus") or ""),
        "collectedAt": str(item.get("capturedAt") or ""),
        "takedownPolicy": "quwoquan_standard_notice_and_takedown",
    }
    if distribution_decision in {"research_allowed", "commercial_allowed"}:
        expected.update(
            {
                "commercialAuthorizationStatus": (
                    "verified"
                    if distribution_decision == "commercial_allowed"
                    else "unverified"
                ),
                "publicationAdmission": (
                    "commercial_release"
                    if distribution_decision == "commercial_allowed"
                    else "research_release"
                ),
            }
        )
    drift = sorted(
        field for field, value in expected.items() if attribution.get(field) != value
    )
    if drift:
        raise ValueError(
            "professional image sourceAttribution binding drift: "
            + ",".join(drift)
        )
    return attribution


def build_image_plan_spec(
    item: Mapping[str, Any],
    *,
    platform: str,
    source_id: str,
    cas_uri: str,
    content_sha256: str,
    acquisition_status: str,
    rights_status: str,
    authorization_required: bool,
    distribution_decision: str,
    width: int,
    height: int,
) -> dict[str, Any]:
    attribution = bound_image_source_attribution(
        item,
        platform=platform,
        distribution_decision=distribution_decision,
    )
    return {
        "url": cas_uri,
        "sourceUrl": str(item["sourceUrl"]),
        "collectionPageUrl": str(item["sourceUrl"]),
        "originalAssetUrl": str(item.get("assetUrl") or item["sourceUrl"]),
        "platform": platform,
        "sourceId": source_id,
        "discoveryCandidateId": str(item["discoveryCandidateId"]),
        "discoveryUrl": str(item["discoveryUrl"]),
        "creator": str(item["creator"]),
        "credit": str(item["creator"]),
        "capturedAt": str(item["capturedAt"]),
        "contentSha256": content_sha256,
        "acquisitionStatus": acquisition_status,
        "rightsStatus": rights_status,
        "authorizationRequired": authorization_required,
        "distributionDecision": distribution_decision,
        "rightsAuditStatus": rights_status,
        "rightsIssues": list(item["rightsIssues"]),
        "license": str(item["license"]),
        "licenseSnapshot": str(item["licenseSnapshot"]),
        "usageScope": str(item["usageScope"]),
        "modelReleaseStatus": str(item["modelReleaseStatus"]),
        "termsUrl": str(item["termsUrl"]),
        "authorizationProof": str(item.get("authorizationProof") or "").strip(),
        "caption": str(item["caption"]),
        "relevance": str(item["relevance"]),
        "width": width,
        "height": height,
        "sourceAttribution": attribution,
    }


__all__ = ["bound_image_source_attribution", "build_image_plan_spec"]
