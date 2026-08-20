# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-006
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-006.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-006.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-006.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-006.t4
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-006.t5
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-006.t6
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-006.t7
"""Video work-unit projection from immutable accepted media assets.

`REQ-001` and `GWT-006` require that every accepted asset freezes its own
`workUnit` bound to one receipt/asset/content digest and one canonical coverage
target, that several assets of the same entity produce several content objects,
that an asset which cannot be uniquely mapped becomes a typed exclusion without
failing its siblings, and that `0 < qualified < quota` stays `partial` while
only zero mapped objects is `blocked`.
"""
from __future__ import annotations

import pytest
from content.execution.planning.media_work_units import (
    project_media_work_units,
    validate_frozen_work_unit_exclusions,
    validate_frozen_work_units,
)

UNMAPPED = "DATA.SOURCE.ENTITY_CATALOG_UNMAPPED"
AMBIGUOUS = "DATA.SOURCE.ENTITY_CATALOG_AMBIGUOUS"


def _sha(token: str) -> str:
    filler = token.encode("utf-8").hex()
    return "sha256:" + (filler * 64)[:64]


def _candidate(
    *,
    asset_id: str,
    entity: str,
    aliases: tuple[str, ...] = (),
    receipt: str = "receipt-1",
) -> dict[str, object]:
    return {
        "carrier": "video",
        "manifestRef": "acquisition/video/manifest.json",
        "manifestDigest": _sha("m"),
        "receiptRef": f"acquisition/video/{receipt}.json",
        "receiptDigest": _sha("r"),
        "assetId": asset_id,
        "contentSha256": _sha(asset_id),
        "sourceEntityId": entity,
        "sourceEntityAliases": list(aliases),
    }


def _target(name: str, *, entity_type: str = "scenic_area") -> dict[str, object]:
    return {"name": name, "entityType": entity_type}


def test_several_assets_of_one_entity_freeze_several_work_units() -> None:
    """`GWT-006` allows many workUnits under a single coverage target."""

    projection = project_media_work_units(
        [
            _candidate(asset_id="a1", entity="青城山"),
            _candidate(asset_id="a2", entity="青城山"),
            _candidate(asset_id="a3", entity="青城山"),
        ],
        [_target("青城山")],
    )

    assert projection.mapped_object_count == 3
    assert projection.exclusions == ()
    assert projection.coverage_target_names == ("青城山",)
    assert len({unit["workUnitId"] for unit in projection.work_units}) == 3


def test_each_work_unit_binds_exactly_one_receipt_asset_and_content_digest() -> None:
    """Every workUnit must carry its own manifest/receipt exact pair."""

    projection = project_media_work_units(
        [
            _candidate(asset_id="a1", entity="青城山"),
            _candidate(asset_id="a2", entity="青城山"),
        ],
        [_target("青城山")],
    )

    for unit in projection.work_units:
        assert unit["carrier"] == "video"
        assert unit["manifestRef"]
        assert unit["manifestDigest"].startswith("sha256:")
        assert unit["receiptRef"]
        assert unit["receiptDigest"].startswith("sha256:")
        assert unit["contentSha256"].startswith("sha256:")
        assert unit["coverageTarget"] == {
            "name": "青城山",
            "entityType": "scenic_area",
        }
    assert len({unit["assetId"] for unit in projection.work_units}) == 2
    assert len({unit["contentSha256"] for unit in projection.work_units}) == 2


def test_an_unmappable_asset_is_a_typed_exclusion_and_siblings_continue() -> None:
    """One bad asset must not fail the other workUnits."""

    projection = project_media_work_units(
        [
            _candidate(asset_id="a1", entity="青城山"),
            _candidate(asset_id="a2", entity="不在目录中的实体"),
            _candidate(asset_id="a3", entity="青城山"),
        ],
        [_target("青城山")],
    )

    assert projection.mapped_object_count == 2
    assert len(projection.exclusions) == 1
    exclusion = projection.exclusions[0]
    assert exclusion["code"] == UNMAPPED
    assert exclusion["assetId"] == "a2"
    assert exclusion["candidateNames"] == ["不在目录中的实体"]
    assert exclusion["workUnitCandidateId"].startswith("sha256:")


def test_an_ambiguous_asset_is_excluded_without_synthesizing_a_target() -> None:
    """No coverage target may be synthesized to absorb an ambiguous asset."""

    projection = project_media_work_units(
        [
            _candidate(
                asset_id="a1",
                entity="双流",
                aliases=("青城山", "都江堰"),
            ),
        ],
        [_target("青城山"), _target("都江堰")],
    )

    assert projection.work_units == ()
    assert len(projection.exclusions) == 1
    assert projection.exclusions[0]["code"] == AMBIGUOUS
    assert projection.coverage_target_names == ()


def test_unrelated_targets_are_never_padded_into_work_units() -> None:
    """`GWT-006` forbids padding with entities that have no accepted asset."""

    projection = project_media_work_units(
        [_candidate(asset_id="a1", entity="青城山")],
        [_target("青城山"), _target("都江堰"), _target("峨眉山")],
    )

    assert projection.mapped_object_count == 1
    assert projection.coverage_target_names == ("青城山",)


def test_partial_keeps_mapped_objects_and_reports_shortfall_against_quota() -> None:
    """`0 < qualified < quota` is `partial`; quota must not be rewritten."""

    projection = project_media_work_units(
        [
            _candidate(asset_id="a1", entity="青城山"),
            _candidate(asset_id="a2", entity="未知实体"),
        ],
        [_target("青城山")],
    )

    assert projection.mapped_object_count == 1
    assert projection.shortfall(10) == 9
    assert projection.shortfall(1) == 0


def test_zero_mapped_objects_is_the_only_blocked_outcome() -> None:
    """Only an empty mapped set may collapse the lane to `blocked`."""

    projection = project_media_work_units(
        [_candidate(asset_id="a1", entity="未知实体")],
        [_target("青城山")],
    )

    assert projection.mapped_object_count == 0
    assert projection.shortfall(4) == 4
    assert len(projection.exclusions) == 1


def test_no_candidates_projects_an_empty_result_without_inventing_units() -> None:
    """An absent candidate set is present-and-empty, never a synthesized unit."""

    projection = project_media_work_units([], [_target("青城山")])

    assert projection.work_units == ()
    assert projection.exclusions == ()
    assert projection.coverage_target_names == ()


def test_a_repeated_receipt_asset_pair_fails_closed() -> None:
    """The manifest/receipt exact pair is the asset identity and is unique."""

    with pytest.raises(ValueError, match="duplicate receipt/asset identity"):
        project_media_work_units(
            [
                _candidate(asset_id="a1", entity="青城山"),
                _candidate(asset_id="a1", entity="青城山"),
            ],
            [_target("青城山")],
        )


def test_a_repeated_content_digest_fails_closed() -> None:
    """Two assets may not share one immutable content digest."""

    duplicate = _candidate(asset_id="a2", entity="青城山")
    duplicate["contentSha256"] = _sha("a1")

    with pytest.raises(ValueError, match="duplicate contentSha256"):
        project_media_work_units(
            [_candidate(asset_id="a1", entity="青城山"), duplicate],
            [_target("青城山")],
        )


def test_a_candidate_without_entity_identity_fails_closed() -> None:
    """Entity identity is required; it must not degrade to an empty name."""

    candidate = _candidate(asset_id="a1", entity="青城山")
    candidate["sourceEntityId"] = "   "

    with pytest.raises(TypeError, match="sourceEntityId must be non-empty"):
        project_media_work_units([candidate], [_target("青城山")])


def test_frozen_work_units_reject_work_unit_id_digest_drift() -> None:
    """A frozen workUnit is replayable only through its own digest."""

    projection = project_media_work_units(
        [_candidate(asset_id="a1", entity="青城山")],
        [_target("青城山")],
    )
    frozen = [dict(unit) for unit in projection.work_units]

    assert validate_frozen_work_units(frozen) == projection.work_units

    frozen[0]["assetId"] = "tampered"
    with pytest.raises(ValueError, match="workUnitId digest drift"):
        validate_frozen_work_units(frozen)


def test_frozen_exclusions_reject_an_unsupported_typed_code() -> None:
    """The exclusion code closed set is owned by the media projection."""

    projection = project_media_work_units(
        [_candidate(asset_id="a1", entity="未知实体")],
        [_target("青城山")],
    )
    frozen = [dict(row) for row in projection.exclusions]

    assert validate_frozen_work_unit_exclusions(frozen) == projection.exclusions

    frozen[0]["code"] = "DATA.SOURCE.SOMETHING_ELSE"
    with pytest.raises(ValueError, match="exclusion code is unsupported"):
        validate_frozen_work_unit_exclusions(frozen)


def test_projection_is_deterministic_for_the_same_immutable_inputs() -> None:
    """Replaying the same frozen assets must yield the same workUnit ids."""

    candidates = [
        _candidate(asset_id="a1", entity="青城山"),
        _candidate(asset_id="a2", entity="都江堰"),
    ]
    targets = [_target("青城山"), _target("都江堰")]

    first = project_media_work_units(candidates, targets)
    second = project_media_work_units(candidates, targets)

    assert first.work_units == second.work_units
    assert first.coverage_target_names == second.coverage_target_names == (
        "青城山",
        "都江堰",
    )
