from __future__ import annotations

from governance.coverage.distribution import (
    AcquisitionStatus,
    DistributionDecision,
    RightsStatus,
    distribution_decision,
    load_content_distribution_policy,
    project_asset_admission,
)


def _asset(*, rights_status: str, proof: str = "") -> dict[str, object]:
    return {
        "assetId": f"asset-{rights_status}",
        "asset": {"sha256": "sha256:" + "a" * 64, "bytes": 12},
        "rightsAuditStatus": rights_status,
        "sourceUrl": "https://media.example/item",
        "platform": "Pinterest",
        "creator": "摄影师",
        "capturedAt": "2026-08-02T00:00:00Z",
        "license": "unknown",
        "termsUrl": "https://media.example/terms",
        "authorizationProof": proof,
        "rightsAuditIssues": (
            [] if rights_status == "verified" else ["commercial authorization missing"]
        ),
    }


def test_research_policy_is_explicit_and_disables_media_generation() -> None:
    policy = load_content_distribution_policy()

    assert policy.product_lifecycle_state.value == "research"
    assert policy.release_class.value == "research"
    assert policy.image_generation_allowed is False
    assert policy.video_generation_allowed is False
    assert policy.image_provider_priority[:2] == ("pinterest", "tuchong")
    assert policy.minimum_illustrated_rate == 0.9
    assert policy.m100_per_carrier == 100
    assert policy.m1000_per_carrier == 1000


def test_acquisition_and_distribution_rights_are_independent() -> None:
    assert distribution_decision(
        acquisition_status=AcquisitionStatus.ACQUIRED,
        rights_status=RightsStatus.UNVERIFIED,
        authorization_proof="",
    ) is DistributionDecision.RESEARCH_ALLOWED
    assert distribution_decision(
        acquisition_status=AcquisitionStatus.ACQUIRED,
        rights_status=RightsStatus.VERIFIED,
        authorization_proof="https://rights.example/proof",
    ) is DistributionDecision.COMMERCIAL_ALLOWED
    assert distribution_decision(
        acquisition_status=AcquisitionStatus.ACQUIRED,
        rights_status=RightsStatus.RESTRICTED,
        authorization_proof="",
    ) is DistributionDecision.BLOCKED
    assert distribution_decision(
        acquisition_status=AcquisitionStatus.BLOCKED,
        rights_status=RightsStatus.VERIFIED,
        authorization_proof="https://rights.example/proof",
    ) is DistributionDecision.BLOCKED


def test_projected_unverified_asset_keeps_exact_rights_gap() -> None:
    projected = project_asset_admission(_asset(rights_status="unverified"), object_ref="posts/p1")

    assert projected["acquisitionStatus"] == "acquired"
    assert projected["rightsStatus"] == "unverified"
    assert projected["authorizationRequired"] is True
    assert projected["distributionDecision"] == "research_allowed"
    assert projected["rightsIssues"] == ["commercial authorization missing"]

