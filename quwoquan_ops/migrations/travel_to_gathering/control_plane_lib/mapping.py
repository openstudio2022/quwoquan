"""travel 源对象到 canonical Gathering/GatheringPlan 的映射主流程。

本模块只承载单一函数 ``build_mapping``（逐字来自原 ``control_plane.py``）。
该函数是一体化的映射编排流程，行数由源逻辑决定；按「逐字搬移、不改逻辑」
约束不在本次拆分中再切函数体。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.codec import (
    _identity_digest,
    canonical_digest,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.constants import (
    MIGRATION_ID,
    SOURCE_OBJECT_TYPES,
    MappingResult,
    TargetContractBinding,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.contract_validation import (
    _validate_contract_document,
    validate_gathering_document,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.mapping_support import (
    _binding_trip_id,
    _canonical_object_ref,
    _dedupe_blockers,
    _index_objects,
    _map_lifecycle_status,
    _map_membership_closed_reason,
    _map_plan_item,
    _mapping_record,
    _new_conflicts,
    _record_conflict,
    _safe_blocker,
    _target_plan_id,
    _target_revision_id,
    _trip_binding_issues,
)


def build_mapping(
    snapshot: Mapping[str, Any],
    target_contract: TargetContractBinding,
) -> MappingResult:
    conflicts = _new_conflicts()
    indexed = _index_objects(snapshot, conflicts)
    blockers: list[dict[str, Any]] = []
    records_by_key: dict[tuple[str, int], dict[str, Any]] = {}
    documents: list[dict[str, Any]] = []
    validation_errors: list[dict[str, Any]] = []
    plan_validation_errors: list[dict[str, Any]] = []

    plans_by_id: dict[str, tuple[int, dict[str, Any]]] = {}
    duplicate_plan_ids: set[str] = set()
    for index, plan, trip_id in indexed["TripPlan"]:
        if trip_id in plans_by_id:
            duplicate_plan_ids.add(trip_id)
        else:
            plans_by_id[trip_id] = (index, plan)
    revisions_by_trip: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for index, revision, _ in indexed["TripPlanRevision"]:
        trip_id = str(revision.get("tripId") or "").strip()
        revisions_by_trip.setdefault(trip_id, []).append((index, revision))
    memberships_by_trip: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    membership_identity_seen: set[tuple[str, str]] = set()
    duplicate_membership_indexes: set[int] = set()
    for index, membership, _ in indexed["TripMembership"]:
        trip_id = str(membership.get("tripId") or "").strip()
        persona_id = str(membership.get("personaId") or "").strip()
        identity = (trip_id, persona_id)
        if identity in membership_identity_seen:
            duplicate_membership_indexes.add(index)
            _record_conflict(
                conflicts,
                "member",
                {"tripId": trip_id, "personaId": persona_id},
            )
        membership_identity_seen.add(identity)
        memberships_by_trip.setdefault(trip_id, []).append((index, membership))

    trip_bindings = snapshot["bindings"]["tripBindings"]
    membership_bindings = snapshot["bindings"]["membershipBindings"]
    placement_route_ids = snapshot["bindings"]["placementRouteIds"]
    plan_item_source_refs: dict[
        tuple[str, int, str],
        list[dict[str, str]],
    ] = {}
    for _, moment, _ in indexed["TripMoment"]:
        content_ref = _canonical_object_ref(moment.get("contentRef"))
        if moment.get("status") == "active" and content_ref is not None:
            key = (
                str(moment.get("tripId") or ""),
                int(moment.get("revisionNumber") or 0),
                str(moment.get("itemId") or ""),
            )
            plan_item_source_refs.setdefault(key, []).append(content_ref)
    for _, link, _ in indexed["TripPlanContentLink"]:
        post_id = str(link.get("postId") or "").strip()
        if link.get("status") == "active" and post_id:
            key = (
                str(link.get("tripId") or ""),
                int(link.get("revisionNumber") or 0),
                str(link.get("itemId") or ""),
            )
            plan_item_source_refs.setdefault(key, []).append(
                {
                    "objectTypeRef": "content.Post",
                    "objectId": post_id,
                }
            )
    gathering_identity_seen: dict[str, str] = {}
    conversation_seen: dict[str, str] = {}
    mapped_trip_ids: dict[str, str] = {}

    for trip_id, (plan_index, plan) in sorted(plans_by_id.items()):
        if trip_id in duplicate_plan_ids:
            records_by_key[("TripPlan", plan_index)] = _mapping_record(
                "TripPlan",
                trip_id,
                plan,
                disposition="quarantined",
                reason="duplicate_source_identity",
            )
            blockers.append(
                _safe_blocker(
                    "SOURCE_IDENTITY_COLLISION",
                    object_type="TripPlan",
                    object_id=trip_id,
                    reason="duplicate TripPlan identity",
                )
            )
            continue
        if plan.get("status") == "archived":
            records_by_key[("TripPlan", plan_index)] = _mapping_record(
                "TripPlan",
                trip_id,
                plan,
                disposition="archived",
                reason="source_plan_archived",
            )
            continue
        binding = trip_bindings.get(trip_id)
        memberships = [value for _, value in memberships_by_trip.get(trip_id, [])]
        issues = _trip_binding_issues(
            plan,
            binding if isinstance(binding, dict) else None,
            memberships,
            membership_bindings,
        )
        if isinstance(binding, dict):
            gathering_id = _binding_trip_id(binding)
            if gathering_id:
                previous_trip = gathering_identity_seen.get(gathering_id)
                if previous_trip and previous_trip != trip_id:
                    issues.append("target_gathering_identity_collision")
                    _record_conflict(
                        conflicts,
                        "objectIdentity",
                        {
                            "gatheringId": gathering_id,
                            "firstTripId": previous_trip,
                            "secondTripId": trip_id,
                        },
                    )
                gathering_identity_seen[gathering_id] = trip_id
            conversation_id = str(binding.get("conversationId") or "").strip()
            if conversation_id:
                previous_trip = conversation_seen.get(conversation_id)
                if previous_trip and previous_trip != trip_id:
                    issues.append("duplicate_conversation_id")
                    _record_conflict(
                        conflicts,
                        "conversationId",
                        {
                            "conversationId": conversation_id,
                            "firstTripId": previous_trip,
                            "secondTripId": trip_id,
                        },
                    )
                conversation_seen[conversation_id] = trip_id
        for issue in issues:
            category = (
                "host"
                if "host" in issue or "organizer" in issue
                else "capacity"
                if "capacity" in issue
                else "timezone"
                if "timezone" in issue
                else "disclosure"
                if "disclosure" in issue
                else "member"
                if issue.startswith("membership_")
                else "reference"
            )
            _record_conflict(
                conflicts,
                category,
                {"tripId": trip_id, "issue": issue},
            )
        revision_candidates = revisions_by_trip.get(trip_id, [])
        current_revision_id = str(plan.get("currentRevisionId") or "").strip()
        current_revision_number = plan.get("currentRevisionNumber")
        current_revisions = [
            value
            for _, value in revision_candidates
            if str(value.get("_id") or "").strip() == current_revision_id
            and value.get("revisionNumber") == current_revision_number
        ]
        if len(current_revisions) != 1:
            issues.append("current_revision_missing_or_ambiguous")
            _record_conflict(
                conflicts,
                "reference",
                {"tripId": trip_id, "reference": "currentRevision"},
            )
        if issues:
            reason = min(set(issues))
            records_by_key[("TripPlan", plan_index)] = _mapping_record(
                "TripPlan",
                trip_id,
                plan,
                disposition="quarantined",
                reason=reason,
            )
            blockers.append(
                _safe_blocker(
                    "TRIP_MAPPING_QUARANTINED",
                    object_type="TripPlan",
                    object_id=trip_id,
                    reason=reason,
                )
            )
            continue

        assert isinstance(binding, dict)
        gathering_id = _binding_trip_id(binding)
        purpose_binding = dict(binding["purpose"])
        source_ref = {
            "objectRef": {
                "objectTypeRef": "travel.TripPlan",
                "objectId": trip_id,
            },
            "routeId": str(binding.get("sourceRouteId") or ""),
            "sourceDigest": canonical_digest(plan),
        }
        purpose = {
            "title": plan.get("title"),
            "summary": purpose_binding.get("summary"),
            "coverRef": _canonical_object_ref(purpose_binding.get("coverRef")),
            "topicRefs": purpose_binding.get("topicRefs"),
            "requirementRefs": purpose_binding.get("requirementRefs"),
            "sourceObjectRefs": [source_ref],
            "costNotice": purpose_binding.get("costNotice"),
            "costDescription": purpose_binding.get("costDescription"),
        }
        schedule = {
            "timezone": binding["schedule"].get("timezone"),
            "startAt": plan.get("startAt"),
            "endAt": plan.get("endAt"),
            "admissionClosesAt": binding["schedule"].get("admissionClosesAt"),
        }
        place = dict(binding["place"])
        policy_set = dict(binding["policySet"])
        host_binding = dict(binding["hostBinding"])
        host_snapshot = {
            "hostSubjectKind": host_binding.get("hostSubjectKind"),
            "hostSubjectId": host_binding.get("hostSubjectId"),
            "authorityEvidenceRef": host_binding.get("authorityEvidenceRef"),
            "authorityVersion": host_binding.get("authorityVersion"),
            "hostDigest": canonical_digest(host_binding),
        }
        mapped_participations: list[dict[str, Any]] = []
        organizer_assignments: list[dict[str, Any]] = []
        membership_mapping_failed = False
        for membership_index, membership in memberships_by_trip.get(trip_id, []):
            membership_id = str(membership.get("_id") or "").strip()
            if membership_index in duplicate_membership_indexes:
                membership_mapping_failed = True
                continue
            membership_binding = membership_bindings[membership_id]
            target_state = "active" if membership.get("state") == "active" else "closed"
            participation = {
                "gatheringId": gathering_id,
                "personaId": membership.get("personaId"),
                "state": target_state,
                "admissionSource": membership_binding.get("admissionSource"),
                "closedReason": _map_membership_closed_reason(membership.get("state")),
                "attemptNo": membership_binding.get("attemptNo"),
                "seatHoldUntil": membership_binding.get("seatHoldUntil"),
                "joinedAt": membership.get("joinedAt"),
                "closedAt": (
                    membership.get("updatedAt") if target_state == "closed" else None
                ),
                "closedByPersonaId": membership_binding.get("closedByPersonaId"),
                "reasonRef": membership_binding.get("reasonRef"),
                "reviewExpectedBy": membership_binding.get("reviewExpectedBy"),
                "version": membership.get("version"),
                "applicationAnswers": membership_binding.get(
                    "applicationAnswers",
                    [],
                ),
                "attendance": membership_binding.get("attendance"),
                "currentChangeAcknowledgement": membership_binding.get(
                    "currentChangeAcknowledgement"
                ),
            }
            mapped_participations.append(participation)
            target_refs: list[dict[str, str]] = [
                {
                    "objectType": "circle.gathering",
                    "objectId": gathering_id,
                }
            ]
            if membership.get("role") == "organizer":
                assignment = dict(membership_binding["organizerAssignment"])
                organizer_assignments.append(assignment)
            records_by_key[("TripMembership", membership_index)] = _mapping_record(
                "TripMembership",
                membership_id,
                membership,
                disposition="migrated",
                reason="participation_and_authority_split",
                target_refs=target_refs,
            )
        if membership_mapping_failed:
            for membership_index, membership in memberships_by_trip.get(trip_id, []):
                records_by_key[("TripMembership", membership_index)] = _mapping_record(
                    "TripMembership",
                    str(membership.get("_id") or ""),
                    membership,
                    disposition="quarantined",
                    reason="duplicate_member_identity",
                )
            records_by_key[("TripPlan", plan_index)] = _mapping_record(
                "TripPlan",
                trip_id,
                plan,
                disposition="quarantined",
                reason="duplicate_member_identity",
            )
            blockers.append(
                _safe_blocker(
                    "TRIP_MAPPING_QUARANTINED",
                    object_type="TripPlan",
                    object_id=trip_id,
                    reason="duplicate member identity",
                )
            )
            continue

        current_revision = current_revisions[0]
        target_revision_id = _target_revision_id(current_revision_id)
        gathering_revision_stable = {
            "revisionId": target_revision_id,
            "revisionNumber": current_revision_number,
            "purpose": purpose,
            "schedule": schedule,
            "place": place,
            "policySet": policy_set,
            "hostSnapshot": host_snapshot,
            "materialChange": current_revision.get("severity") != "minor",
            "createdByPersonaId": current_revision.get("createdByPersonaId"),
            "createdAt": current_revision.get("createdAt"),
        }
        gathering_revision = {
            **gathering_revision_stable,
            "digest": canonical_digest(gathering_revision_stable),
        }
        lifecycle_status = _map_lifecycle_status(plan.get("status"))
        gathering = {
            "_id": gathering_id,
            "version": plan.get("version"),
            "createdByPersonaId": plan.get("organizerPersonaId"),
            "hostBinding": host_binding,
            "organizerAssignments": organizer_assignments,
            "purpose": purpose,
            "schedule": schedule,
            "place": place,
            "policySet": policy_set,
            "admissionControl": dict(binding["admissionControl"]),
            "lifecycleStatus": lifecycle_status,
            "outcome": binding.get("outcome"),
            "conversationId": binding.get("conversationId"),
            "roomBindingStatus": binding.get("roomBindingStatus"),
            "currentGatheringRevisionId": target_revision_id,
            "currentGatheringRevisionNumber": current_revision_number,
            "participations": mapped_participations,
            "revisions": [gathering_revision],
            "availabilityWatches": [],
            "createdAt": plan.get("createdAt"),
            "updatedAt": plan.get("updatedAt"),
            "cancelledAt": None,
            "completedAt": binding.get("completedAt"),
        }
        gathering_errors = validate_gathering_document(
            gathering,
            target_contract.fields_contract,
        )

        mapped_revisions: list[dict[str, Any]] = []
        for revision_index, revision in sorted(
            revision_candidates,
            key=lambda item: (
                int(item[1].get("revisionNumber") or 0),
                str(item[1].get("_id") or ""),
            ),
        ):
            source_revision_id = str(revision.get("_id") or "")
            revision_number = int(revision.get("revisionNumber") or 0)
            affected_persona_ids = sorted(
                {
                    str(persona_id).strip()
                    for persona_id in revision.get("affectedPersonaIds", [])
                    if str(persona_id).strip()
                }
            )
            plan_revision_stable: dict[str, Any] = {
                "revisionId": _target_revision_id(source_revision_id),
                "revisionNumber": revision_number,
                "baseRevisionId": (
                    _target_revision_id(str(revision.get("previousRevisionId")))
                    if revision.get("previousRevisionId")
                    else None
                ),
                "baseRevisionNumber": max(0, revision_number - 1),
                "baseRevisionDigest": (
                    mapped_revisions[-1]["revisionDigest"]
                    if mapped_revisions
                    else canonical_digest(
                        {
                            "migrationId": MIGRATION_ID,
                            "tripId": trip_id,
                            "baseRevision": None,
                        }
                    )
                ),
                "committedProposalId": None,
                "committedByPersonaId": revision.get("createdByPersonaId"),
                "items": [
                    _map_plan_item(
                        item,
                        extra_source_refs=plan_item_source_refs.get(
                            (
                                trip_id,
                                revision_number,
                                str(item.get("itemId") or ""),
                            ),
                            (),
                        ),
                    )
                    for item in revision.get("items", [])
                    if isinstance(item, dict)
                ],
                "acknowledgementPolicy": {
                    "mode": (
                        "affected_participations"
                        if affected_persona_ids
                        else "none"
                    ),
                    "deadlineAt": None,
                },
                "affectedParticipationRefs": [
                    {
                        "gatheringId": gathering_id,
                        "personaId": persona_id,
                    }
                    for persona_id in affected_persona_ids
                ],
                "committedAt": revision.get("createdAt"),
            }
            revision_digest = canonical_digest(plan_revision_stable)
            mapped_revisions.append(
                {
                    **plan_revision_stable,
                    "revisionDigest": revision_digest,
                }
            )
            records_by_key[("TripPlanRevision", revision_index)] = _mapping_record(
                "TripPlanRevision",
                source_revision_id,
                revision,
                disposition="migrated",
                reason="immutable_revision_identity_preserved",
                target_refs=[
                    {
                        "objectType": "circle.gathering_plan",
                        "objectId": _target_plan_id(gathering_id),
                    }
                ],
            )
        current_mapped_revisions = [
            revision
            for revision in mapped_revisions
            if revision["revisionId"] == target_revision_id
            and revision["revisionNumber"] == current_revision_number
        ]
        if len(current_mapped_revisions) != 1:
            candidate_errors = ["canonical current GatheringPlan revision is missing"]
            current_revision_digest = ""
        else:
            candidate_errors = []
            current_revision_digest = current_mapped_revisions[0]["revisionDigest"]
        plan_candidate = {
            "_id": _target_plan_id(gathering_id),
            "gatheringId": gathering_id,
            "version": plan.get("version"),
            "currentRevisionId": target_revision_id,
            "currentRevisionNumber": current_revision_number,
            "currentRevisionDigest": current_revision_digest,
            "revisions": mapped_revisions,
            "proposals": [],
            "acknowledgements": [],
            "createdAt": plan.get("createdAt"),
            "updatedAt": plan.get("updatedAt"),
        }
        candidate_errors.extend(
            _validate_contract_document(
                plan_candidate,
                target_contract.plan_fields_contract,
                object_name="GatheringPlan",
            )
        )
        if gathering_errors or candidate_errors:
            if gathering_errors:
                validation_errors.append(
                    {
                        "targetIdentityDigest": _identity_digest(
                            "circle.gathering",
                            gathering_id,
                        ),
                        "errorDigests": [
                            canonical_digest(error) for error in gathering_errors
                        ],
                    }
                )
            if candidate_errors:
                plan_validation_errors.append(
                    {
                        "targetIdentityDigest": _identity_digest(
                            "circle.gathering_plan",
                            plan_candidate["_id"],
                        ),
                        "errorDigests": [
                            canonical_digest(error) for error in candidate_errors
                        ],
                    }
                )
            for membership_index, membership in memberships_by_trip.get(trip_id, []):
                records_by_key[("TripMembership", membership_index)] = _mapping_record(
                    "TripMembership",
                    str(membership.get("_id") or ""),
                    membership,
                    disposition="quarantined",
                    reason="parent_target_schema_validation_failed",
                )
            for revision_index, revision in revision_candidates:
                records_by_key[("TripPlanRevision", revision_index)] = _mapping_record(
                    "TripPlanRevision",
                    str(revision.get("_id") or ""),
                    revision,
                    disposition="quarantined",
                    reason="parent_target_schema_validation_failed",
                )
            records_by_key[("TripPlan", plan_index)] = _mapping_record(
                "TripPlan",
                trip_id,
                plan,
                disposition="quarantined",
                reason="target_schema_validation_failed",
            )
            blockers.append(
                _safe_blocker(
                    "TARGET_SCHEMA_VALIDATION_FAILED",
                    object_type="TripPlan",
                    object_id=trip_id,
                    reason="mapped canonical Gathering/GatheringPlan is invalid",
                )
            )
            continue

        documents.extend(
            (
                {"kind": "circle.gathering", "document": gathering},
                {"kind": "circle.gathering_plan", "document": plan_candidate},
            )
        )
        mapped_trip_ids[trip_id] = gathering_id
        records_by_key[("TripPlan", plan_index)] = _mapping_record(
            "TripPlan",
            trip_id,
            plan,
            disposition="migrated",
            reason="canonical_gathering_and_plan_validated",
            target_refs=[
                {"objectType": "circle.gathering", "objectId": gathering_id},
                {
                    "objectType": "circle.gathering_plan",
                    "objectId": plan_candidate["_id"],
                },
                *[
                    {
                        "objectType": "content.post",
                        "objectId": post_id,
                    }
                    for post_id in sorted(
                        {
                            str(value).strip()
                            for value in plan.get("sourcePostIds", [])
                            if str(value).strip()
                        }
                    )
                ],
            ],
        )

    # Duplicate TripPlan entries not selected as the canonical first entry.
    for index, plan, trip_id in indexed["TripPlan"]:
        key = ("TripPlan", index)
        if key not in records_by_key:
            records_by_key[key] = _mapping_record(
                "TripPlan",
                trip_id,
                plan,
                disposition="quarantined",
                reason=(
                    "duplicate_source_identity"
                    if trip_id in duplicate_plan_ids
                    else "mapping_not_reached"
                ),
            )

    parent_bound_types = (
        "TripPlanRevision",
        "TripMembership",
        "TripMoment",
        "TripPlanContentLink",
        "TripGuideAssignment",
        "TripPlanPlacement",
        "TripMapView",
        "TripTimelineView",
        "TripShareSnapshot",
    )
    for object_type in parent_bound_types:
        for index, value, object_id in indexed[object_type]:
            key = (object_type, index)
            if key in records_by_key:
                continue
            trip_id = str(value.get("tripId") or "").strip()
            if trip_id not in plans_by_id:
                _record_conflict(
                    conflicts,
                    "reference",
                    {"objectType": object_type, "tripId": trip_id},
                )
                records_by_key[key] = _mapping_record(
                    object_type,
                    object_id,
                    value,
                    disposition="quarantined",
                    reason="orphan_trip_reference",
                )
                blockers.append(
                    _safe_blocker(
                        "ORPHAN_SOURCE_REFERENCE",
                        object_type=object_type,
                        object_id=object_id,
                        reason="source object references a missing TripPlan",
                    )
                )
                continue
            gathering_id = mapped_trip_ids.get(trip_id)
            if not gathering_id:
                records_by_key[key] = _mapping_record(
                    object_type,
                    object_id,
                    value,
                    disposition="quarantined",
                    reason="parent_trip_quarantined",
                )
                continue
            if object_type == "TripMoment":
                if value.get("status") == "deleted":
                    records_by_key[key] = _mapping_record(
                        object_type,
                        object_id,
                        value,
                        disposition="archived",
                        reason="source_moment_deleted",
                    )
                    continue
                content_ref = _canonical_object_ref(value.get("contentRef"))
                if content_ref is None:
                    records_by_key[key] = _mapping_record(
                        object_type,
                        object_id,
                        value,
                        disposition="quarantined",
                        reason="canonical_content_reference_missing",
                    )
                    blockers.append(
                        _safe_blocker(
                            "CONTENT_REFERENCE_MISSING",
                            object_type=object_type,
                            object_id=object_id,
                            reason="inline Moment content is not copied",
                        )
                    )
                    continue
                records_by_key[key] = _mapping_record(
                    object_type,
                    object_id,
                    value,
                    disposition="migrated",
                    reason="canonical_content_reference_recirculated",
                    target_refs=[
                        {
                            "objectType": "circle.gathering_plan",
                            "objectId": _target_plan_id(gathering_id),
                        },
                        {
                            "objectType": "content.post",
                            "objectId": content_ref["objectId"],
                        },
                    ],
                )
                continue
            if object_type == "TripPlanContentLink":
                if value.get("status") == "removed":
                    records_by_key[key] = _mapping_record(
                        object_type,
                        object_id,
                        value,
                        disposition="archived",
                        reason="source_content_link_removed",
                    )
                    continue
                post_id = str(value.get("postId") or "").strip()
                if not post_id:
                    records_by_key[key] = _mapping_record(
                        object_type,
                        object_id,
                        value,
                        disposition="quarantined",
                        reason="canonical_post_reference_missing",
                    )
                    continue
                records_by_key[key] = _mapping_record(
                    object_type,
                    object_id,
                    value,
                    disposition="migrated",
                    reason="content_owner_reference_recirculated",
                    target_refs=[
                        {
                            "objectType": "circle.gathering_plan",
                            "objectId": _target_plan_id(gathering_id),
                        },
                        {
                            "objectType": "content.post",
                            "objectId": post_id,
                        },
                    ],
                )
                continue
            if object_type == "TripGuideAssignment":
                if value.get("status") == "cancelled":
                    records_by_key[key] = _mapping_record(
                        object_type,
                        object_id,
                        value,
                        disposition="archived",
                        reason="source_guide_assignment_cancelled",
                    )
                    continue
                qualification_id = str(
                    value.get("publicQualificationPersonaId") or ""
                ).strip()
                if not qualification_id:
                    records_by_key[key] = _mapping_record(
                        object_type,
                        object_id,
                        value,
                        disposition="quarantined",
                        reason="public_authority_evidence_missing",
                    )
                    blockers.append(
                        _safe_blocker(
                            "HOST_AUTHORITY_EVIDENCE_MISSING",
                            object_type=object_type,
                            object_id=object_id,
                            reason="GuideAssignment cannot manufacture Host authority",
                        )
                    )
                    continue
                records_by_key[key] = _mapping_record(
                    object_type,
                    object_id,
                    value,
                    disposition="not_applicable",
                    reason="canonical_target_guide_assignment_contract_unavailable",
                )
                continue
            if object_type == "TripPlanPlacement":
                if value.get("status") == "removed":
                    records_by_key[key] = _mapping_record(
                        object_type,
                        object_id,
                        value,
                        disposition="archived",
                        reason="source_placement_removed",
                    )
                    continue
                route_id = str(placement_route_ids.get(object_id) or "").strip()
                if not route_id:
                    records_by_key[key] = _mapping_record(
                        object_type,
                        object_id,
                        value,
                        disposition="quarantined",
                        reason="target_route_binding_missing",
                    )
                    continue
                target_kind = (
                    "chat.conversation"
                    if value.get("surfaceKind") == "conversation"
                    else "circle.circle"
                )
                records_by_key[key] = _mapping_record(
                    object_type,
                    object_id,
                    value,
                    disposition="migrated",
                    reason="typed_target_placement_binding_preserved",
                    target_refs=[
                        {
                            "objectType": "circle.gathering_plan",
                            "objectId": _target_plan_id(gathering_id),
                        },
                        {
                            "objectType": target_kind,
                            "objectId": str(value.get("surfaceId") or ""),
                        },
                    ],
                )
                continue
            if object_type in {"TripMapView", "TripTimelineView"}:
                records_by_key[key] = _mapping_record(
                    object_type,
                    object_id,
                    value,
                    disposition="not_applicable",
                    reason="derived_projection_rebuild_only",
                )
                continue
            if object_type == "TripShareSnapshot":
                records_by_key[key] = _mapping_record(
                    object_type,
                    object_id,
                    value,
                    disposition="not_applicable",
                    reason="privacy_trimmed_snapshot_is_parity_input_only",
                )
                continue
            # Remaining parent-bound objects are revisions/memberships already
            # handled with their aggregate.
            records_by_key[key] = _mapping_record(
                object_type,
                object_id,
                value,
                disposition="quarantined",
                reason="parent_mapping_incomplete",
            )

    for index, template, template_id in indexed["TripPlanTemplate"]:
        if template.get("status") == "archived":
            disposition = "archived"
            reason = "source_template_archived"
        else:
            disposition = "not_applicable"
            reason = "canonical_target_plan_template_contract_unavailable"
        records_by_key[("TripPlanTemplate", index)] = _mapping_record(
            "TripPlanTemplate",
            template_id,
            template,
            disposition=disposition,
            reason=reason,
        )

    for object_type in SOURCE_OBJECT_TYPES:
        for index, value, object_id in indexed[object_type]:
            key = (object_type, index)
            if key not in records_by_key:
                records_by_key[key] = _mapping_record(
                    object_type,
                    object_id,
                    value,
                    disposition="quarantined",
                    reason="unmapped_source_object",
                )
                blockers.append(
                    _safe_blocker(
                        "UNMAPPED_SOURCE_OBJECT",
                        object_type=object_type,
                        object_id=object_id,
                        reason="source object has no completed disposition rule",
                    )
                )

    records = tuple(
        records_by_key[key]
        for key in sorted(records_by_key, key=lambda item: (item[0], item[1]))
    )
    canonical_target_ids = set(target_contract.object_ids)
    for record in records:
        for target_ref in record["targetRefs"]:
            object_type = str(target_ref.get("objectType") or "")
            if object_type not in canonical_target_ids:
                blockers.append(
                    _safe_blocker(
                        "NON_CANONICAL_TARGET_KIND",
                        object_type=str(record["sourceObjectType"]),
                        reason=f"target ref {object_type!r} is absent from ContractGraph",
                    )
                )
    for wrapper in documents:
        object_type = str(wrapper.get("kind") or "")
        if object_type not in canonical_target_ids:
            blockers.append(
                _safe_blocker(
                    "NON_CANONICAL_TARGET_KIND",
                    reason=f"target document {object_type!r} is absent from ContractGraph",
                )
            )
    quarantined = [
        record for record in records if record["disposition"] == "quarantined"
    ]
    if quarantined:
        blockers.append(
            _safe_blocker(
                "QUARANTINED_SOURCE_OBJECTS",
                reason=f"{len(quarantined)} source objects are quarantined",
            )
        )
    for category, bucket in conflicts.items():
        if bucket["count"]:
            blockers.append(
                _safe_blocker(
                    "MIGRATION_COLLISION",
                    reason=f"{category} conflicts: {bucket['count']}",
                )
            )
    validation = {
        "gatheringSchema": {
            "contractDigest": target_contract.digest,
            "validatedDocumentCount": len(
                [
                    value
                    for value in documents
                    if value.get("kind") == "circle.gathering"
                ]
            ),
            "errorCount": len(validation_errors),
            "errors": validation_errors,
        },
        "gatheringPlanSchema": {
            "validatedDocumentCount": len(
                [
                    value
                    for value in documents
                    if value.get("kind") == "circle.gathering_plan"
                ]
            ),
            "errorCount": len(plan_validation_errors),
            "errors": plan_validation_errors,
            "targetContractStatus": "canonical_generated_contract",
        },
    }
    return MappingResult(
        documents=tuple(
            sorted(
                documents,
                key=lambda value: (
                    str(value.get("kind") or ""),
                    canonical_digest(value.get("document")),
                ),
            )
        ),
        records=records,
        conflicts=conflicts,
        blockers=_dedupe_blockers(blockers),
        validation=validation,
    )
