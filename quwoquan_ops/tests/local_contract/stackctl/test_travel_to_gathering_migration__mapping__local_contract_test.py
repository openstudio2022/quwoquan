"""M6 travel-service -> Gathering target-only 迁移控制面契约（crosswalk 映射与 receipt）。

由 1000 行硬顶拆分自根目录
test_travel_to_gathering_migration__local_contract_test.py；测试逐字搬移，
共享构造 helper 见 quwoquan_ops/tests/support/travel_to_gathering_migration_test_support.py。

spec_ref: specs/feature-tree/travel-journey/spec.md#dom-001
"""

from __future__ import annotations

import copy
import json

from quwoquan_ops.migrations.travel_to_gathering import control_plane
from quwoquan_ops.tests.support.travel_to_gathering_migration_test_support import (
    _reseal,
    _source_snapshot,
    _target_contract,
)


def test_full_crosswalk_maps_or_disposes_every_source_object() -> None:
    result = control_plane.build_mapping(_source_snapshot(), _target_contract())

    assert len(result.records) == len(control_plane.SOURCE_OBJECT_TYPES)
    assert not [
        record for record in result.records if record["disposition"] == "quarantined"
    ]
    assert {record["sourceObjectType"] for record in result.records} == set(
        control_plane.SOURCE_OBJECT_TYPES
    )
    assert {wrapper["kind"] for wrapper in result.documents} == {
        "circle.gathering",
        "circle.gathering_plan",
    }
    assert all(
        ref["objectType"] in control_plane.CANONICAL_TARGET_OBJECT_IDS
        for record in result.records
        for ref in record["targetRefs"]
    )
    policies = {
        record["sourceObjectType"]: (
            record["disposition"],
            record["reason"],
        )
        for record in result.records
        if record["sourceObjectType"]
        in {
            "TripGuideAssignment",
            "TripMapView",
            "TripTimelineView",
            "TripShareSnapshot",
            "TripPlanTemplate",
        }
    }
    assert policies["TripGuideAssignment"] == (
        "not_applicable",
        "canonical_target_guide_assignment_contract_unavailable",
    )
    assert policies["TripMapView"] == (
        "not_applicable",
        "derived_projection_rebuild_only",
    )
    assert policies["TripTimelineView"] == (
        "not_applicable",
        "derived_projection_rebuild_only",
    )
    assert policies["TripShareSnapshot"] == (
        "not_applicable",
        "privacy_trimmed_snapshot_is_parity_input_only",
    )
    assert policies["TripPlanTemplate"] == (
        "not_applicable",
        "canonical_target_plan_template_contract_unavailable",
    )
    assert all(
        record["targetRefs"] == []
        for record in result.records
        if record["disposition"] == "not_applicable"
    )
    assert result.validation["gatheringSchema"]["errorCount"] == 0
    assert result.validation["gatheringPlanSchema"]["errorCount"] == 0


def test_missing_target_field_quarantines_without_fabrication() -> None:
    snapshot = _source_snapshot()
    snapshot["bindings"]["tripBindings"]["trip-1"]["schedule"].pop("timezone")
    _reseal(snapshot)

    result = control_plane.build_mapping(snapshot, _target_contract())

    trip_record = next(
        record for record in result.records if record["sourceObjectType"] == "TripPlan"
    )
    assert trip_record["disposition"] == "quarantined"
    assert trip_record["reason"] == "timezone_missing_or_invalid"
    assert not [
        wrapper
        for wrapper in result.documents
        if wrapper["kind"] == "circle.gathering"
    ]


def test_template_policy_archives_only_already_archived_source_templates() -> None:
    snapshot = _source_snapshot()
    snapshot["objects"]["TripPlanTemplate"][0]["status"] = "archived"
    _reseal(snapshot)

    result = control_plane.build_mapping(snapshot, _target_contract())
    record = next(
        value
        for value in result.records
        if value["sourceObjectType"] == "TripPlanTemplate"
    )

    assert record["disposition"] == "archived"
    assert record["reason"] == "source_template_archived"
    assert record["targetRefs"] == []


def test_receipt_is_idempotent_and_never_emits_raw_pii() -> None:
    snapshot = _source_snapshot()
    snapshot["objects"]["TripMoment"][0]["inlineText"] = (
        "联系 alice@example.com 或 13800138000"
    )
    _reseal(snapshot)
    mapping = control_plane.build_mapping(snapshot, _target_contract())

    first = control_plane.build_receipt(
        environment="alpha",
        phase="dry-run",
        snapshot=snapshot,
        target_contract=_target_contract(),
        mapping=mapping,
    )
    second = control_plane.build_receipt(
        environment="alpha",
        phase="dry-run",
        snapshot=snapshot,
        target_contract=_target_contract(),
        mapping=mapping,
    )
    encoded = json.dumps(first, ensure_ascii=False, sort_keys=True)

    assert first == second
    assert first["receiptId"] == second["receiptId"]
    assert first["writeSet"] == []
    assert first["piiRedaction"]["rawValuesEmitted"] is False
    assert first["piiRedaction"]["detectedValuePatterns"] == {
        "email": 1,
        "phone": 1,
    }
    assert "alice@example.com" not in encoded
    assert "13800138000" not in encoded
    assert "persona-host" not in encoded
    assert "东门" not in encoded


def test_duplicate_conversation_is_a_deterministic_collision() -> None:
    snapshot = _source_snapshot()
    plan = copy.deepcopy(snapshot["objects"]["TripPlan"][0])
    plan.update(
        {
            "_id": "trip-2",
            "organizerPersonaId": "persona-host-2",
            "currentRevisionId": "revision-2",
        }
    )
    revision = copy.deepcopy(snapshot["objects"]["TripPlanRevision"][0])
    revision.update(
        {
            "_id": "revision-2",
            "tripId": "trip-2",
            "createdByPersonaId": "persona-host-2",
        }
    )
    membership = copy.deepcopy(snapshot["objects"]["TripMembership"][0])
    membership.update(
        {
            "_id": "membership-2",
            "tripId": "trip-2",
            "personaId": "persona-host-2",
        }
    )
    trip_binding = copy.deepcopy(snapshot["bindings"]["tripBindings"]["trip-1"])
    trip_binding.update(
        {
            "gatheringId": "gathering-2",
            "conversationId": "conversation-1",
        }
    )
    membership_binding = copy.deepcopy(
        snapshot["bindings"]["membershipBindings"]["membership-1"]
    )
    membership_binding["organizerAssignment"]["personaId"] = "persona-host-2"
    snapshot["objects"]["TripPlan"].append(plan)
    snapshot["objects"]["TripPlanRevision"].append(revision)
    snapshot["objects"]["TripMembership"].append(membership)
    snapshot["bindings"]["tripBindings"]["trip-2"] = trip_binding
    snapshot["bindings"]["membershipBindings"]["membership-2"] = membership_binding
    _reseal(snapshot)

    result = control_plane.build_mapping(snapshot, _target_contract())

    assert result.conflicts["conversationId"]["count"] == 1
    assert any(
        record["sourceObjectType"] == "TripPlan"
        and record["disposition"] == "quarantined"
        and record["reason"] == "duplicate_conversation_id"
        for record in result.records
    )
    receipt = control_plane.build_receipt(
        environment="alpha",
        phase="inventory",
        snapshot=snapshot,
        target_contract=_target_contract(),
        mapping=result,
    )
    assert receipt["status"] == "GATE_BLOCK"
    assert receipt["conflicts"]["totalCount"] > 0


def test_parity_reconciles_all_dimensions_deterministically() -> None:
    mapping = control_plane.build_mapping(
        _source_snapshot(),
        _target_contract(),
    )

    first = control_plane.build_parity(mapping.documents, mapping.documents)
    second = control_plane.build_parity(mapping.documents, mapping.documents)

    assert first == second
    assert first["status"] == "passed"
    assert first["percentage"] == 100
    assert set(first["dimensions"]) == {
        "identity",
        "count",
        "state",
        "host",
        "membership",
        "plan",
        "contentRefs",
        "outcome",
    }


def test_orphan_is_quarantined_and_blocks_mapping() -> None:
    snapshot = _source_snapshot()
    snapshot["objects"]["TripMoment"][0]["tripId"] = "trip-missing"
    _reseal(snapshot)

    mapping = control_plane.build_mapping(snapshot, _target_contract())

    assert any(
        blocker["code"] == "ORPHAN_SOURCE_REFERENCE"
        for blocker in mapping.blockers
    )
    assert any(
        record["sourceObjectType"] == "TripMoment"
        and record["disposition"] == "quarantined"
        and record["reason"] == "orphan_trip_reference"
        for record in mapping.records
    )
