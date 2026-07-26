# spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/filter-catalog-release/spec.md#gwt-004

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from content.filter_catalog.artifact import (
    digest_test_vector,
    validate_repository,
)
from content.filter_catalog.codec import load_json_decimal
from content.filter_catalog.environment_import import load_environment_import
from content.filter_catalog.contract import (
    ADJUSTMENT_FIELD_NAMES,
    CatalogContractError,
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


def test_environment_import_exposes_only_the_bound_stage_payload():
    environment_input = load_environment_import(
        repo_root=REPO_ROOT,
        environment="gamma",
    )

    assert environment_input.manifest_ref.endswith("/gamma.seed.json")
    assert environment_input.canonical_artifact_ref.endswith(
        "/filter_catalog_release.json"
    )
    assert environment_input.release_id == "filter-catalog-20260720-001"
    assert environment_input.category_count == 10
    assert environment_input.preset_count == 85
    assert environment_input.activation_policy == "stage_then_activate"
    assert environment_input.idempotency_key.startswith("filter-catalog:")
    assert environment_input.operation_paths == {
        "stage": "/internal/content/filter-catalog-releases",
        "activate": "/internal/content/filter-catalog-releases/{releaseId}:activate",
        "rollback": "/internal/content/filter-catalog-releases/{releaseId}:rollback",
        "read": "/content/filter-catalog",
    }
    assert set(environment_input.stage_payload()) == {
        "releaseId",
        "sourceOwner",
        "canonicalDigest",
        "categories",
        "presets",
        "recommendedFallbackPresetIds",
    }


def test_digest_vector_fixes_cross_language_canonical_bytes():
    vector = digest_test_vector()

    assert vector["sha256"] == (
        "fba38ede15295f3bbee31375d9955e"
        "dc0baf722b8c204dbf0575f4ab25401242"
    )
    assert vector["canonicalJsonUtf8"].startswith('{"categories":[')
    assert "\\u62cd" not in vector["canonicalJsonUtf8"]
    assert "80.5" in vector["canonicalJsonUtf8"]
    assert "80.500" not in vector["canonicalJsonUtf8"]
    assert "0.0000001" in vector["canonicalJsonUtf8"]
    assert "1e-7" not in vector["canonicalJsonUtf8"]


def test_canonical_presets_define_exactly_fifteen_typed_adjustments():
    release = load_json_decimal(CANONICAL.read_text(encoding="utf-8"))
    assert isinstance(release, dict)
    normalized = normalize_release(release)

    for preset in normalized["presets"]:
        assert tuple(preset["adjustments"]) == ADJUSTMENT_FIELD_NAMES
        assert len(preset["adjustments"]) == 15
    original = next(
        item for item in normalized["presets"] if item["presetId"] == "original"
    )
    assert set(original["adjustments"].values()) == {0}


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_category_sort",
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
    categories = invalid["categories"]
    assert isinstance(categories, list)
    presets = invalid["presets"]
    assert isinstance(presets, list)

    if mutation == "duplicate_category_sort":
        categories[1]["sort"] = categories[0]["sort"]
    elif mutation == "duplicate_preset":
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
