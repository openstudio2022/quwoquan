"""Image asset strategy contract."""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from core.image_asset_strategy import (  # noqa: E402
    image_asset_strategy_scale_issues,
    image_asset_strategy,
    image_strategy_release_allowed,
    validate_image_asset_strategy,
)


def test_default_strategy_is_open_license_publish():
    spec = {"content": {"research": {"allowAiImages": False}}}

    assert image_asset_strategy(spec) == "open_license_publish"
    assert validate_image_asset_strategy(spec) == []


def test_ai_generated_strategy_requires_ai_flag_and_provider():
    spec = {
        "content": {
            "research": {
                "imageAssetStrategy": "ai_generated_original",
                "allowAiImages": False,
            }
        }
    }

    issues = validate_image_asset_strategy(spec)

    assert any("allowAiImages must be true" in issue for issue in issues)
    assert any("syntheticAssetProvider" in issue for issue in issues)


def test_reference_only_strategy_is_not_release_allowed():
    spec = {
        "content": {
            "research": {
                "imageAssetStrategy": "reference_only_no_image_release",
                "allowAiImages": False,
            }
        }
    }

    assert image_strategy_release_allowed(spec) is False
    assert validate_image_asset_strategy(spec) == []


def test_open_license_scale_requires_prescreened_pool_or_publish_strategy():
    spec = {
        "scope": {
            "coverageTargets": [
                {"entityType": "地点/景区", "name": f"景区{i}"}
                for i in range(100)
            ]
        },
        "content": {
            "quotas": {"imageWorksPerTarget": 2},
            "research": {
                "imageAssetStrategy": "open_license_publish",
                "allowAiImages": False,
            },
        },
        "acceptance": {"minEntities": 100},
    }

    issues = image_asset_strategy_scale_issues(spec)

    assert len(issues) == 1
    assert "openLicenseScaleProof" in issues[0]
    assert "preScreenedEntityCount>=100" in issues[0]
    assert "publishableImageAssets>=200" not in issues[0]


def test_hard_quota_open_license_scale_requires_publishable_asset_count():
    spec = {
        "scope": {
            "coverageTargets": [
                {"entityType": "地点/景区", "name": f"景区{i}"}
                for i in range(100)
            ]
        },
        "content": {
            "quotas": {"imageWorksPerTarget": 2},
            "research": {
                "imageAssetStrategy": "open_license_publish",
                "imageCountPolicy": "hard_quota",
                "allowAiImages": False,
                "openLicenseScaleProof": {
                    "preScreenedEntityCount": 100,
                    "publishableImageAssets": 175,
                    "assetPoolPath": "quwoquan_data/publish/media/library",
                    "verifiedAt": "2026-06-20T00:00:00Z",
                },
            },
        },
        "acceptance": {"minEntities": 100},
    }

    issues = image_asset_strategy_scale_issues(spec)

    assert len(issues) == 1
    assert "publishableImageAssets>=200" in issues[0]


def test_open_license_scale_passes_with_prescreened_pool_proof():
    spec = {
        "scope": {
            "coverageTargets": [
                {"entityType": "地点/景区", "name": f"景区{i}"}
                for i in range(100)
            ]
        },
        "content": {
            "quotas": {"imageWorksPerTarget": 2},
            "research": {
                "imageAssetStrategy": "open_license_publish",
                "allowAiImages": False,
                "openLicenseScaleProof": {
                    "preScreenedEntityCount": 100,
                    "publishableImageAssets": 175,
                    "assetPoolPath": "quwoquan_data/publish/media/library",
                    "verifiedAt": "2026-06-20T00:00:00Z",
                },
            },
        },
        "acceptance": {"minEntities": 100},
    }

    assert image_asset_strategy_scale_issues(spec) == []


def test_licensed_provider_scale_requires_asset_pool_proof():
    spec = {
        "scope": {
            "coverageTargets": [
                {"entityType": "地点/景区", "name": f"景区{i}"}
                for i in range(100)
            ]
        },
        "content": {
            "quotas": {"imageWorksPerTarget": 2},
            "research": {
                "imageAssetStrategy": "licensed_provider_publish",
                "allowAiImages": False,
                "licensedImageProvider": "commercial-photo-provider",
            },
        },
        "acceptance": {"minEntities": 100},
    }

    issues = image_asset_strategy_scale_issues(spec)

    assert len(issues) == 1
    assert "licensedProviderScaleProof" in issues[0]
    assert "licensedEntityCount>=100" in issues[0]


def test_ai_generated_scale_requires_synthetic_pool_proof():
    spec = {
        "scope": {
            "coverageTargets": [
                {"entityType": "地点/景区", "name": f"景区{i}"}
                for i in range(100)
            ]
        },
        "content": {
            "quotas": {"imageWorksPerTarget": 2},
            "research": {
                "imageAssetStrategy": "ai_generated_original",
                "allowAiImages": True,
                "syntheticAssetProvider": "approved-image-generator",
            },
        },
        "acceptance": {"minEntities": 100},
    }

    issues = image_asset_strategy_scale_issues(spec)

    assert len(issues) == 1
    assert "syntheticScaleProof" in issues[0]
    assert "generatedEntityCount>=100" in issues[0]
