from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from content.filter_catalog.artifact import (
    digest_test_vector,
    validate_repository,
)
from content.filter_catalog.codec import load_json_decimal
from content.filter_catalog.contract import (
    ADJUSTMENT_FIELD_NAMES,
    CatalogContractError,
    build_release_from_legacy,
    normalize_release,
)


REPO_ROOT = Path(__file__).resolve().parents[4]
CANONICAL = (
    REPO_ROOT
    / "quwoquan_data/reference/filter_catalog/releases"
    / "filter-catalog-20260720-001/filter_catalog_release.json"
)


def test_repository_artifact_bootstrap_and_environment_inputs_are_same_source():
    report = validate_repository(REPO_ROOT)

    assert report["passed"] is True, report["issues"]
    assert report["stats"] == {
        "releaseId": "filter-catalog-20260720-001",
        "canonicalDigest": (
            "9ccd581f6ac73b1e8a623b345fc8b646"
            "05fc99b67d2c71017d4f18177cb70a0d"
        ),
        "sourceOwner": "qwq_data",
        "categoryCount": 10,
        "presetCount": 85,
        "environmentCount": 4,
        "adjustmentFieldCount": 15,
    }


def test_digest_vector_fixes_cross_language_canonical_bytes():
    vector = digest_test_vector()

    assert vector["sha256"] == (
        "01ccbcce8c97768447928166f4598f7a"
        "1c67855f26344e87a6581ebf7c22d2f5"
    )
    assert vector["canonicalJsonUtf8"].startswith('{"categories":[')
    assert "\\u62cd" not in vector["canonicalJsonUtf8"]
    assert "80.5" in vector["canonicalJsonUtf8"]
    assert "80.500" not in vector["canonicalJsonUtf8"]


def test_legacy_initialization_expands_exactly_fifteen_typed_adjustments():
    release = build_release_from_legacy(
        {
            "version": 2,
            "categories": [
                {
                    "id": "camera_photo",
                    "label": "拍照",
                    "sort": 1,
                    "enabled": True,
                }
            ],
            "presets": [
                {
                    "id": "original",
                    "categoryId": "camera_photo",
                    "name": "原图",
                    "sort": 1,
                    "enabled": True,
                    "defaultStrength": 0,
                    "params": {},
                },
                {
                    "id": "vivid",
                    "categoryId": "camera_photo",
                    "name": "鲜明",
                    "sort": 2,
                    "enabled": True,
                    "defaultStrength": 80,
                    "params": {"contrast": 12},
                },
            ],
            "recommendedFallbackPresetIds": ["vivid"],
        },
        release_id="filter-catalog-test-001",
        source_owner="qwq_data",
    )

    for preset in release["presets"]:
        assert tuple(preset["adjustments"]) == ADJUSTMENT_FIELD_NAMES
        assert len(preset["adjustments"]) == 15
    original = next(
        item for item in release["presets"] if item["presetId"] == "original"
    )
    assert set(original["adjustments"].values()) == {0}


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_preset",
        "unknown_category",
        "out_of_range",
        "non_identity_original",
        "digest_mismatch",
    ],
)
def test_contract_rejects_catalog_invariant_violations(mutation: str):
    release = load_json_decimal(CANONICAL.read_text(encoding="utf-8"))
    assert isinstance(release, dict)
    invalid = deepcopy(release)
    presets = invalid["presets"]
    assert isinstance(presets, list)

    if mutation == "duplicate_preset":
        presets[1]["presetId"] = presets[0]["presetId"]
    elif mutation == "unknown_category":
        presets[0]["categoryId"] = "missing"
    elif mutation == "out_of_range":
        presets[0]["adjustments"]["contrast"] = 101
    elif mutation == "non_identity_original":
        original = next(
            item for item in presets if item["presetId"] == "original"
        )
        original["adjustments"]["exposure"] = 1
    elif mutation == "digest_mismatch":
        invalid["canonicalDigest"] = "0" * 64

    with pytest.raises(CatalogContractError):
        normalize_release(invalid)
