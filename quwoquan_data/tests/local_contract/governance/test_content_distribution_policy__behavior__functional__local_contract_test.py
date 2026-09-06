from __future__ import annotations

from governance.coverage.distribution import (
    AcquisitionStatus,
    DistributionDecision,
    RightsStatus,
    asset_contract_missing_fields,
    distribution_decision,
    image_distribution_decision,
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

    assert policy.policy_id == "research-content-cold-start"
    assert policy.product_lifecycle_state.value == "research"
    assert policy.release_class.value == "research"
    assert policy.image_generation_allowed is False
    assert policy.video_generation_allowed is False
    assert policy.image_provider_priority[:2] == ("pinterest", "tuchong")
    assert policy.illustrated_rate_target == 0.9
    assert policy.text_only_rate_target == 0.1
    assert policy.video_popularity_signals == (
        "play",
        "like",
        "comment",
        "share",
        "favorite",
    )
    assert policy.video_popularity_statistical is True
    assert policy.video_popularity_non_blocking is True
    assert dict(policy.m1_targets) == {
        "homepage": 1,
        "article": 1,
        "image": 1,
        "video": 1,
    }
    assert dict(policy.m10_targets) == {
        "homepage": 10,
        "article": 10,
        "image": 10,
        "video": 2,
    }
    assert dict(policy.m100_targets) == {
        "homepage": 100,
        "article": 100,
        "image": 100,
        "video": 10,
    }
    assert dict(policy.m1000_targets) == {
        "homepage": 1000,
        "article": 1000,
        "image": 1000,
        "video": 100,
    }
    assert dict(policy.m10000_targets) == {
        "homepage": 10000,
        "article": 10000,
        "image": 10000,
        "video": 1000,
    }
    assert policy.require_m100_promotion_before_m1000 is False
    assert policy.require_m1000_promotion_before_m10000 is False
    assert policy.milestone_attainment_required is True
    assert policy.attainment_counting_mode == "cumulative_unique_finalized_objects"


def test_scale_target_supports_every_governed_milestone() -> None:
    policy = load_content_distribution_policy()

    assert policy.scale_target("M1", "video") == 1
    assert policy.scale_target("M10", "video") == 2
    assert policy.scale_target("M100", "video") == 10
    assert policy.scale_target("M1000", "video") == 100
    assert policy.scale_target("M10000", "video") == 1000


def test_research_admission_accepts_acquired_non_restricted_rights() -> None:
    for rights_status in (
        RightsStatus.VERIFIED,
        RightsStatus.UNVERIFIED,
        RightsStatus.UNKNOWN,
    ):
        assert distribution_decision(
            acquisition_status=AcquisitionStatus.ACQUIRED,
            rights_status=rights_status,
            authorization_proof="",
        ) is DistributionDecision.RESEARCH_ALLOWED


def test_acquisition_and_distribution_rights_are_independent() -> None:
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
    for acquisition_status in (AcquisitionStatus.FAILED, AcquisitionStatus.BLOCKED):
        assert distribution_decision(
            acquisition_status=acquisition_status,
            rights_status=RightsStatus.VERIFIED,
            authorization_proof="https://rights.example/proof",
        ) is DistributionDecision.BLOCKED


def test_missing_asset_contract_fields_fail_admission_validation() -> None:
    missing = asset_contract_missing_fields(
        {
            "assetId": "asset-incomplete",
            "acquisitionStatus": "acquired",
            "rightsStatus": "unknown",
            "distributionDecision": "research_allowed",
        }
    )

    assert {
        "authorizationProof",
        "authorizationRequired",
        "capturedAt",
        "contentSha256",
        "creator",
        "license",
        "platform",
        "rightsIssues",
        "sourceUrl",
        "termsUrl",
    }.issubset(missing)


def test_environment_cannot_select_lifecycle_or_release_class(monkeypatch) -> None:
    monkeypatch.setenv("QWQ_PRODUCT_LIFECYCLE_STATE", "commercial")
    monkeypatch.setenv("QWQ_RELEASE_CLASS", "commercial")
    monkeypatch.setenv("QWQ_CONTENT_DISTRIBUTION_POLICY", "commercial-rights-closure")

    policy = load_content_distribution_policy()

    assert policy.policy_id == "research-content-cold-start"
    assert policy.product_lifecycle_state.value == "research"
    assert policy.release_class.value == "research"


def test_image_commercial_admission_cannot_exceed_frozen_usage_or_model_release_scope() -> None:
    common = {
        "acquisition_status": AcquisitionStatus.ACQUIRED,
        "rights_status": RightsStatus.VERIFIED,
        "authorization_proof": "https://rights.example/proof",
    }
    assert image_distribution_decision(
        **common,
        usage_scope="internal_reference",
        model_release_status="not_required",
    ) is DistributionDecision.RESEARCH_ALLOWED
    assert image_distribution_decision(
        **common,
        usage_scope="app_publish",
        model_release_status="editorial_only",
    ) is DistributionDecision.RESEARCH_ALLOWED
    assert image_distribution_decision(
        **common,
        usage_scope="app_publish",
        model_release_status="obtained",
    ) is DistributionDecision.COMMERCIAL_ALLOWED
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
