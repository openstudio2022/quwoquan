# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#gwt-004
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#req-004
"""衍生修改字段在 sourceAttribution 上必填、取值闭集、且只在写侧一次物化。

在场为空（空数组）与缺席是两个不同事实：前者表示发布字节相对原始素材逐字节原样，
后者表示读不出发布物有没有被改过。所以空数组通过而缺席判否，读侧与测试替身都不得
替写侧补一个从未声明过的取值。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core.media_source_provenance import DerivedModification  # noqa: E402
from core.source_attribution import (  # noqa: E402
    canonical_source_attribution,
    derived_modifications_value,
)

ATTRIBUTION = {
    "isOriginal": False,
    "originalCreatorId": None,
    "originalCreatorName": "摄影师甲",
    "originalCreatorProfileUrl": "https://media.example/creators/a",
    "platform": "Wikimedia Commons",
    "sourcePostUrl": "https://media.example/posts/hailuogou",
    "originalAssetUrl": "https://media.example/assets/hailuogou.jpg",
    "attributionText": "摄影师甲 / CC BY-SA 4.0",
    "rightsBasis": "CC BY-SA 4.0",
    "commercialAuthorizationStatus": "verified",
    "publicationAdmission": "production_release",
    "authorizationProofUrl": "https://media.example/proofs/hailuogou",
    "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
    "watermarkStatus": "absent",
    "audioRightsStatus": "no_audio",
    "modelReleaseStatus": "not_required",
    "propertyReleaseStatus": "not_required",
    "collectedAt": "2026-08-11T00:00:00Z",
    "takedownPolicy": "quwoquan_standard_notice_and_takedown",
}


def _attribution(modifications: object) -> dict[str, object]:
    return {**ATTRIBUTION, "derivedModifications": modifications}


def test_empty_array_passes_because_it_states_byte_for_byte_original() -> None:
    observed = canonical_source_attribution(_attribution([]))

    assert observed["derivedModifications"] == []


def test_absent_field_is_refused_rather_than_read_as_unmodified() -> None:
    with pytest.raises(ValueError, match="derivedModifications"):
        canonical_source_attribution(dict(ATTRIBUTION))


def test_declared_modifications_pass_as_closed_set_members() -> None:
    observed = canonical_source_attribution(
        _attribution(["format_conversion", "video_frame_extraction"])
    )

    assert observed["derivedModifications"] == [
        "format_conversion",
        "video_frame_extraction",
    ]


def test_value_outside_the_closed_set_is_refused() -> None:
    with pytest.raises(ValueError, match="derivedModifications"):
        canonical_source_attribution(_attribution(["invented_modification"]))


def test_repeated_member_is_refused_so_one_modification_is_stated_once() -> None:
    with pytest.raises(ValueError, match="derivedModifications"):
        canonical_source_attribution(_attribution(["crop", "crop"]))


@pytest.mark.parametrize("publication", ["research_release", "commercial_release"])
def test_retired_publication_is_rejected_by_schema_and_pool_reader(publication: str) -> None:
    from content.release.canonical.pool_source_attribution import source_attribution_complete

    value = {**_attribution([]), "publicationAdmission": publication}
    with pytest.raises(ValueError, match="publicationAdmission"):
        canonical_source_attribution(value)
    assert source_attribution_complete({"sourceAttribution": value}) is False


@pytest.mark.parametrize("invalid", [
    {"derivedModifications": ["invented_modification"]},
    {"watermarkKind": "invented_watermark"},
    {"watermarkNote": 123},
    {"riskAcceptanceId": "not-a-contract-field"},
    {"audioRightsStatus": "invented_audio"},
])
def test_pool_reader_uses_complete_attribution_schema(invalid: dict[str, object]) -> None:
    from content.release.canonical.pool_source_attribution import source_attribution_complete

    assert source_attribution_complete({"sourceAttribution": {**_attribution([]), **invalid}}) is False


def test_production_keeps_unverified_audio_and_exact_watermark_facts() -> None:
    value = {
        **_attribution(["resize"]), "audioRightsStatus": "unverified",
        "commercialAuthorizationStatus": "unverified", "authorizationProofUrl": None,
        "watermarkStatus": "present", "watermarkKind": "author_signature", "watermarkNote": "右下签名",
    }
    assert canonical_source_attribution(value) == value


def test_data_and_service_source_attribution_authoring_contracts_agree() -> None:
    # spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-032
    import json
    import yaml

    schema = json.loads((DATA_ROOT / "schema/content/post_manifest.schema.json").read_text())
    contract_path = DATA_ROOT.parent / "quwoquan_service/services/content-service/contracts/content/post/fields.yaml"
    contract = yaml.safe_load(contract_path.read_text())
    attribution = schema["$defs"]["sourceAttribution"]
    fields = {row["name"]: row for row in contract["value_objects"]["SourceAttribution"]["fields"]}
    assert set(fields) == set(attribution["properties"])
    assert {name for name, row in fields.items() if "NOT_NULL" in row["constraints"]} == set(attribution["required"])
    assert contract["enums"][fields["publicationAdmission"]["enum_ref"]]["values"] == [attribution["properties"]["publicationAdmission"]["const"]]
    for name in ("derivedModifications", "watermarkKind"):
        expected = attribution["properties"][name]
        if name == "derivedModifications":
            expected = expected["items"]
        assert set(contract["enums"][fields[name]["enum_ref"]]["values"]) == set(expected["enum"])
    media = {row["name"]: row for row in contract["value_objects"]["PostMediaItem"]["fields"]}
    assert media["caption"]["type"] == "string" and "NULLABLE" in media["caption"]["constraints"]
    assert schema["properties"]["assets"]["items"]["properties"]["caption"]["type"] == "string"


def test_write_side_materializes_nothing_done_as_empty_array() -> None:
    assert derived_modifications_value() == []


def test_write_side_materializes_performed_operations_deterministically() -> None:
    performed = {
        DerivedModification.FORMAT_CONVERSION,
        DerivedModification.VIDEO_FRAME_EXTRACTION,
        DerivedModification.CROP,
    }

    # 同一组操作无论遍历顺序都物化为同一份取值，否则同一次交付会写出两种字节。
    assert derived_modifications_value(performed) == derived_modifications_value(
        sorted(performed, key=lambda member: member.value, reverse=True)
    )
    assert canonical_source_attribution(
        _attribution(derived_modifications_value(performed))
    )["derivedModifications"] == ["crop", "format_conversion", "video_frame_extraction"]
