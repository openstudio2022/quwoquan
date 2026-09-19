# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-046
from __future__ import annotations

import json
from pathlib import Path

import pytest

from content.release.canonical.content_pool_record import build_content_pool_fields
from content.release.canonical.object_transaction_contract import ObjectTransactionError
from content.release.canonical.pool_record_history import _validated_pool_record
from core.source_attribution import canonical_source_attribution

DATA_ROOT = Path(__file__).resolve().parents[3]
OLD_ENUMS = {
    "research", "commercial", "research_release", "commercial_release",
    "research_allowed", "commercial_allowed", "commercial_variant",
}
LEGACY_INPUT_ENUMS = {
    Path("release/legacy_release_cohort_v1.schema.json"): {"research"},
    Path("release/legacy_content_pool_handoff_query_v1.schema.json"): {
        "research", "commercial", "commercial_variant",
    },
}


def _attribution() -> dict[str, object]:
    return {
        "isOriginal": False,
        "originalCreatorName": "摄影师甲",
        "platform": "Wikimedia Commons",
        "sourcePostUrl": "https://example.test/post",
        "originalAssetUrl": "https://example.test/asset.jpg",
        "attributionText": "摄影师甲 / CC BY 4.0",
        "rightsBasis": "CC BY 4.0",
        "commercialAuthorizationStatus": "verified",
        "watermarkStatus": "absent",
        "audioRightsStatus": "no_audio",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "collectedAt": "2026-09-15T00:00:00Z",
        "takedownPolicy": "remove_on_verified_request",
        "derivedModifications": [],
    }


def test_all_data_schemas_exclude_retired_object_classification_enums() -> None:
    schema_root = DATA_ROOT / "schema"
    seen_legacy_inputs: set[Path] = set()
    for path in schema_root.rglob("*.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        retired = OLD_ENUMS.intersection(_enum_strings(document))
        relative = path.relative_to(schema_root)
        expected = LEGACY_INPUT_ENUMS.get(relative, set())
        assert retired == expected, path
        if expected:
            seen_legacy_inputs.add(relative)
    assert seen_legacy_inputs == set(LEGACY_INPUT_ENUMS)


def _enum_strings(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value.get("enum", ())) | set().union(*(_enum_strings(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(_enum_strings(v) for v in value))
    return set()


def test_new_pool_writer_omits_retired_dimensions_and_keeps_rights_authority(tmp_path: Path) -> None:
    review = tmp_path / "content_review.json"
    review.write_text('{}\n', encoding="utf-8")
    fields = build_content_pool_fields(
        source_manifest={"contentId": "content-a", "version": 1, "sourceAttribution": _attribution()},
        canonical_ref="article/guide/a/1", source_task_id="task-1", content_review_path=review,
        rights_authority={"ref": "posts/article/guide/a/1/content_review.json", "digest": "sha256:" + "9" * 64},
        publish_root=tmp_path / "publish", rights_rows=[],
        reserved_identity={"contentId": "content-a", "version": 1},
    )
    assert "variantPurpose" not in fields
    assert "usageScope" not in fields["admission"]
    assert fields["admission"]["rightsResult"] == "passed"
    assert fields["admission"]["rightsAuthorityRef"].endswith("content_review.json")


@pytest.mark.parametrize(
    "patch, expected",
    [
        ({"variantPurpose": "commercial_variant"}, "variantPurpose"),
        ({"admission": {"usageScope": "research"}}, "admission.usageScope"),
        ({"sourceAttribution": {**_attribution(), "publicationAdmission": "research_release"}}, "publicationAdmission"),
    ],
)
def test_compatible_dict_writer_rejects_retired_fields(tmp_path: Path, patch: dict[str, object], expected: str) -> None:
    review = tmp_path / "content_review.json"
    review.write_text('{}\n', encoding="utf-8")
    manifest = {"contentId": "content-a", "version": 1, "sourceAttribution": _attribution(), **patch}
    with pytest.raises(ObjectTransactionError, match=expected):
        build_content_pool_fields(
            source_manifest=manifest, canonical_ref="article/guide/a/1", source_task_id="task-1",
            content_review_path=review,
            rights_authority={"ref": "posts/article/guide/a/1/content_review.json", "digest": "sha256:" + "9" * 64},
            publish_root=tmp_path / "publish", rights_rows=[],
            reserved_identity={"contentId": "content-a", "version": 1},
        )


def test_strict_attribution_and_pool_record_readers_reject_old_fields() -> None:
    with pytest.raises(ValueError, match="publicationAdmission"):
        canonical_source_attribution({**_attribution(), "publicationAdmission": "research_release"})
    with pytest.raises(ObjectTransactionError, match="RECORD_SCHEMA_INVALID"):
        _validated_pool_record({
            "schema": "quwoquan_data.pool_object_record", "objectType": "author", "objectId": "a",
            "objectRef": "a", "recordSequence": 1, "contentVersion": 1, "status": "active",
            "processResult": "completed", "qualityResult": "passed", "eligibilityResult": "passed",
            "usageScope": None, "evidenceRef": "e", "evidenceDigest": "sha256:" + "1" * 64,
            "payloadDigest": "sha256:" + "2" * 64,
        })


def test_asset_usage_scope_remains_three_purpose_values() -> None:
    schema = json.loads((DATA_ROOT / "schema/content/post_manifest.schema.json").read_text(encoding="utf-8"))
    assert set(schema["properties"]["assets"]["items"]["properties"]["usageScope"]["enum"]) == {
        "internal_reference", "app_publish", "editorial"
    }
