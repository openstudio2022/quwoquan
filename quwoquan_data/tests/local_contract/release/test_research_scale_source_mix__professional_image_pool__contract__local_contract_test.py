# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
from __future__ import annotations

import pytest

from content.release.canonical.research_scale_source_mix import (
    ResearchScaleSourceMixError,
    validate_research_scale_source_mix,
)


def _asset(index: int, platform: str, *, source_url: str = "") -> dict[str, object]:
    return {
        "assetId": f"image-{index}",
        "objectRef": f"posts/image/画报/作品-{index}/1",
        "acquisitionStatus": "acquired",
        "rightsStatus": "unverified",
        "authorizationRequired": True,
        "distributionDecision": "research_allowed",
        "sourceUrl": source_url or f"https://media.example/originals/image-{index}.jpg",
        "platform": platform,
        "creator": f"摄影师-{index}",
        "capturedAt": "2026-08-08T00:00:00Z",
        "contentSha256": "sha256:" + f"{index:064x}",
        "license": "unknown",
        "termsUrl": "https://media.example/terms",
        "authorizationProof": "",
        "rightsIssues": ["commercial authorization missing"],
        "generated": False,
    }


def _admission(platforms: list[str]) -> dict[str, object]:
    return {"assets": [_asset(index + 1, platform) for index, platform in enumerate(platforms)]}


def test_professional_image_mix_projects_normalized_provider_counts() -> None:
    admission = _admission(
        [
            "Pinterest",
            "PINTEREST.COM",
            " pinterest ",
            "www.pinterest.com",
            "图虫",
            "TUCHONG",
            "Wikimedia Commons",
            "Wikimedia Commons",
            "Pexels",
            "pinterest-clone",
        ]
    )

    projection = validate_research_scale_source_mix(admission)

    assert projection["acceptedImageAssetCount"] == 10
    assert projection["originalAssetClosureCount"] == 10
    assert projection["pinterestAcceptedAssetCount"] == 4
    assert projection["tuchongAcceptedAssetCount"] == 2
    assert projection["pinterestTuchongAcceptedAssetRatio"] == 0.6
    assert projection["largestProvider"] == "pinterest"
    assert projection["maxProviderAcceptedAssetRatio"] == 0.4
    assert projection["policyObservations"] == {
        "pinterestUniqueLargest": True,
        "tuchongPresent": True,
        "pinterestTuchongAtLeastHalf": True,
        "providerAboveSeventyPercent": [],
    }
    counts = {
        row["provider"]: row["acceptedAssetCount"]
        for row in projection["providerAssetCounts"]
    }
    assert counts["pinterest-clone"] == 1
    assert counts["pinterest"] == 4


@pytest.mark.parametrize(
    ("platforms", "observation"),
    [
        (
            ["Pinterest"] * 3 + ["图虫"] * 2 + ["Wikimedia"] * 3 + ["Pexels"] * 2,
            "pinterestUniqueLargest",
        ),
        (
            ["Pinterest"] * 5 + ["Wikimedia"] * 3 + ["Pexels"] * 2,
            "tuchongPresent",
        ),
        (
            ["Pinterest"] * 4 + ["图虫"] + ["Wikimedia"] * 3 + ["Pexels"] * 3,
            "pinterestTuchongAtLeastHalf",
        ),
        (
            ["Pinterest"] * 8 + ["图虫"] + ["Pexels"],
            "providerAboveSeventyPercent",
        ),
    ],
)
def test_professional_image_mix_reports_nonblocking_policy_observation(
    platforms: list[str],
    observation: str,
) -> None:
    projection = validate_research_scale_source_mix(_admission(platforms))
    policy = projection["policyObservations"]

    if observation == "providerAboveSeventyPercent":
        assert policy[observation] == ["pinterest"]
    else:
        assert policy[observation] is False


def test_professional_image_mix_rejects_provider_platform_identity_drift() -> None:
    admission = _admission(["Pinterest"] * 4 + ["图虫"] * 2 + ["Pexels"] * 4)
    first = admission["assets"][0]
    assert isinstance(first, dict)
    first["provider"] = "tuchong"

    with pytest.raises(ResearchScaleSourceMixError, match="identity drift"):
        validate_research_scale_source_mix(admission)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"contentSha256": ""}, "contentSha256"),
        ({"creator": "unknown"}, "creator"),
        (
            {"sourceUrl": "https://i.pinimg.com/236x/aa/bb/thumbnail.jpg"},
            "thumbnail/preview",
        ),
        ({"generated": True}, "generated"),
        ({"generated": None}, "generated flag"),
    ],
)
def test_professional_image_mix_requires_original_asset_closure(
    mutation: dict[str, object],
    message: str,
) -> None:
    admission = _admission(["Pinterest"] * 4 + ["图虫"] * 2 + ["Pexels"] * 4)
    first = admission["assets"][0]
    assert isinstance(first, dict)
    first.update(mutation)

    with pytest.raises(ResearchScaleSourceMixError, match=message):
        validate_research_scale_source_mix(admission)


def test_professional_image_mix_ignores_non_image_and_nonaccepted_assets() -> None:
    admission = _admission(["Pinterest"] * 5 + ["图虫"] * 2 + ["Pexels"] * 3)
    article = _asset(100, "Pinterest")
    article["objectRef"] = "posts/article/攻略/文章/1"
    rejected = _asset(101, "Pinterest")
    rejected["distributionDecision"] = "blocked"
    admission["assets"].extend([article, rejected])

    projection = validate_research_scale_source_mix(admission)

    assert projection["acceptedImageAssetCount"] == 10
    assert projection["pinterestAcceptedAssetCount"] == 5
