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
    "publicationAdmission": "commercial_release",
    "authorizationProofUrl": "https://media.example/proofs/hailuogou",
    "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
    "riskAcceptanceId": None,
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
        canonical_source_attribution(_attribution(["resize"]))


def test_repeated_member_is_refused_so_one_modification_is_stated_once() -> None:
    with pytest.raises(ValueError, match="derivedModifications"):
        canonical_source_attribution(_attribution(["crop", "crop"]))


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
