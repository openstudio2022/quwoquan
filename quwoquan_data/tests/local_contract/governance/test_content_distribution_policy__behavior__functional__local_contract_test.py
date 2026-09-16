from __future__ import annotations

import pytest

from governance.coverage.distribution import (
    RightsStatus,
    asset_contract_missing_fields,
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


def test_production_policy_is_explicit_and_disables_media_generation() -> None:
    policy = load_content_distribution_policy()

    assert policy.policy_id == "content-distribution"
    assert not hasattr(policy, "product_lifecycle_state")
    assert not hasattr(policy, "release_class")
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
    assert dict(policy.m100000_targets) == {
        "homepage": 100000,
        "article": 100000,
        "image": 100000,
        "video": 100000,
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
    assert policy.scale_target("M100000", "video") == 100000


def test_missing_asset_contract_fields_fail_admission_validation() -> None:
    missing = asset_contract_missing_fields(
        {
            "assetId": "asset-incomplete",
            "acquisitionStatus": "acquired",
            "rightsStatus": "unknown",
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

    assert policy.policy_id == "content-distribution"
    assert not hasattr(policy, "product_lifecycle_state")
    assert not hasattr(policy, "release_class")



def test_projection_keeps_rights_facts_without_object_classification() -> None:
    projected = project_asset_admission(_asset(rights_status="unverified"), object_ref="posts/p1")
    assert projected["acquisitionStatus"] == "acquired"
    assert projected["rightsStatus"] == "unverified"
    assert projected["authorizationRequired"] is True
    assert projected["rightsIssues"] == ["commercial authorization missing"]
    assert "distributionDecision" not in projected


def test_projection_rejects_retired_distribution_decision() -> None:
    with pytest.raises(ValueError, match="retired distributionDecision"):
        project_asset_admission(
            {**_asset(rights_status="unverified"), "distributionDecision": "research_allowed"},
            object_ref="posts/p1",
        )
