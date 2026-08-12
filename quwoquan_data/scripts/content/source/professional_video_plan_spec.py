"""Project one accepted professional video receipt row into plan input."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def build_video_plan_spec(
    row: Mapping[str, Any],
    *,
    receipt_ref: str,
    publication: str,
) -> dict[str, Any]:
    digest = str(row["contentSha256"])
    proof = str(row["authorizationProof"]).strip()
    original_asset = str(row["assetUrl"] or row["sourceUrl"])
    probe = row["mediaProbe"]
    assert isinstance(probe, Mapping)
    return {
        "sourceId": str(row["provider"]),
        "sourceKind": str(row["sourceKind"]),
        "ordinal": 1,
        "title": str(row["title"]),
        "relevance": str(row["relevance"]),
        "platform": str(row["platform"]),
        "assetUrl": f"cas://sha256/{digest.removeprefix('sha256:')}",
        "originalAssetUrl": original_asset,
        "sourcePostUrl": str(row["sourceUrl"]),
        "authorizationProofUrl": proof if proof.startswith("https://") else "",
        "termsUrl": str(row["termsUrl"]),
        "rightsBasis": str(row["license"]),
        "originalCreatorName": str(row["creator"]),
        "attributionText": (
            f"{row['title']} — {row['creator']} — {row['license']} — "
            f"{row['sourceUrl']}"
        ),
        "commercialAuthorizationStatus": (
            "verified"
            if row["distributionDecision"] == "commercial_allowed"
            else "unverified"
        ),
        "rightsStatus": str(row["rightsStatus"]),
        "rightsIssues": list(row["rightsIssues"]),
        "publicationAdmission": publication,
        "modelReleaseStatus": str(row["modelReleaseStatus"]),
        "propertyReleaseStatus": str(row["propertyReleaseStatus"]),
        "takedownPolicy": "quwoquan_standard_notice_and_takedown",
        "durationSeconds": int(probe["durationMs"]) / 1000,
        "sizeBytes": int(row["bytes"]),
        "mediaProbe": dict(probe),
        "popularitySignals": dict(row["popularitySignals"]),
        "professionalAcquisitionReceiptRef": receipt_ref,
        "professionalAssetId": str(row["assetId"]),
        "professionalContentSha256": digest,
        "premiumPlayableEligible": True,
    }


__all__ = ["build_video_plan_spec"]
