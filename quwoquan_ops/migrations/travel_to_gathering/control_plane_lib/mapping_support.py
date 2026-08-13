"""mapping 阶段的冲突登记、blocker、索引与字段级换算辅助。

内容逐字来自原 ``control_plane.py``。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any

from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.codec import (
    _identity_digest,
    canonical_digest,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.constants import (
    DISPOSITIONS,
    SOURCE_OBJECT_TYPES,
    TIMEZONE_RE,
)
from quwoquan_ops.migrations.travel_to_gathering.control_plane_lib.snapshots import (
    _source_object_id,
)


def _new_conflicts() -> dict[str, Any]:
    return {
        category: {"count": 0, "collisionDigests": []}
        for category in (
            "objectIdentity",
            "conversationId",
            "host",
            "member",
            "capacity",
            "timezone",
            "disclosure",
            "reference",
        )
    }


def _record_conflict(
    conflicts: dict[str, Any],
    category: str,
    evidence: Mapping[str, Any],
) -> None:
    digest = canonical_digest(evidence)
    bucket = conflicts[category]
    if digest in bucket["collisionDigests"]:
        return
    bucket["collisionDigests"].append(digest)
    bucket["collisionDigests"].sort()
    bucket["count"] = len(bucket["collisionDigests"])


def _safe_blocker(
    code: str,
    *,
    object_type: str = "",
    object_id: str = "",
    reason: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "objectType": object_type,
        "objectIdentityDigest": (
            _identity_digest(object_type, object_id)
            if object_type and object_id
            else ""
        ),
        "reason": reason,
    }


def _dedupe_blockers(
    blockers: Iterable[dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    by_digest = {canonical_digest(blocker): blocker for blocker in blockers}
    return tuple(by_digest[key] for key in sorted(by_digest))


def _index_objects(
    snapshot: Mapping[str, Any],
    conflicts: dict[str, Any],
) -> dict[str, list[tuple[int, dict[str, Any], str]]]:
    indexed: dict[str, list[tuple[int, dict[str, Any], str]]] = {}
    for object_type in SOURCE_OBJECT_TYPES:
        seen: dict[str, int] = {}
        entries: list[tuple[int, dict[str, Any], str]] = []
        for index, value in enumerate(snapshot["objects"][object_type]):
            object_id = _source_object_id(object_type, value)
            entries.append((index, value, object_id))
            if not object_id:
                _record_conflict(
                    conflicts,
                    "objectIdentity",
                    {"objectType": object_type, "index": index, "reason": "missing"},
                )
                continue
            if object_id in seen:
                _record_conflict(
                    conflicts,
                    "objectIdentity",
                    {
                        "objectType": object_type,
                        "objectId": object_id,
                        "reason": "duplicate",
                    },
                )
            seen[object_id] = seen.get(object_id, 0) + 1
        indexed[object_type] = entries
    return indexed


def _binding_trip_id(binding: Mapping[str, Any]) -> str:
    return str(binding.get("gatheringId") or "").strip()


def _trip_binding_issues(
    plan: Mapping[str, Any],
    binding: Mapping[str, Any] | None,
    memberships: Sequence[Mapping[str, Any]],
    membership_bindings: Mapping[str, Any],
) -> list[str]:
    issues: list[str] = []
    if not isinstance(binding, dict):
        return ["trip_binding_missing"]
    gathering_id = _binding_trip_id(binding)
    if not gathering_id:
        issues.append("gathering_identity_missing")
    for key in (
        "hostBinding",
        "purpose",
        "schedule",
        "place",
        "policySet",
        "admissionControl",
    ):
        if not isinstance(binding.get(key), dict):
            issues.append(f"{key}_missing")
    host = binding.get("hostBinding")
    if isinstance(host, dict):
        if not str(host.get("authorityEvidenceRef") or "").strip():
            issues.append("host_authority_evidence_missing")
        if not isinstance(host.get("authorityVersion"), int):
            issues.append("host_authority_version_missing")
    schedule = binding.get("schedule")
    timezone_name = (
        str(schedule.get("timezone") or "").strip()
        if isinstance(schedule, dict)
        else ""
    )
    if TIMEZONE_RE.fullmatch(timezone_name) is None:
        issues.append("timezone_missing_or_invalid")
    policy = binding.get("policySet")
    disclosure = policy.get("disclosurePolicy") if isinstance(policy, dict) else None
    if not isinstance(disclosure, dict) or any(
        not str(disclosure.get(key) or "").strip()
        for key in ("timeDisclosure", "placeDisclosure", "rosterDisclosure")
    ):
        issues.append("disclosure_policy_missing")
    capacity = policy.get("capacityPolicy") if isinstance(policy, dict) else None
    max_participants = (
        capacity.get("maxParticipants") if isinstance(capacity, dict) else None
    )
    if (
        isinstance(max_participants, bool)
        or not isinstance(max_participants, int)
        or max_participants < 1
    ):
        issues.append("capacity_missing_or_invalid")
    active_memberships = [
        value for value in memberships if value.get("state") == "active"
    ]
    if isinstance(max_participants, int) and len(active_memberships) > max_participants:
        issues.append("capacity_below_active_members")
    organizer_id = str(plan.get("organizerPersonaId") or "").strip()
    active_organizers = [
        value
        for value in active_memberships
        if value.get("role") == "organizer"
        and str(value.get("personaId") or "").strip() == organizer_id
    ]
    if len(active_organizers) != 1:
        issues.append("primary_organizer_membership_not_unique")
    for membership in memberships:
        membership_id = str(membership.get("_id") or "").strip()
        membership_binding = membership_bindings.get(membership_id)
        if not isinstance(membership_binding, dict):
            issues.append("membership_binding_missing")
            continue
        for key in (
            "admissionSource",
            "attemptNo",
            "attendance",
            "currentChangeAcknowledgement",
        ):
            if key not in membership_binding:
                issues.append(f"membership_{key}_missing")
        if membership.get("role") == "organizer" and not isinstance(
            membership_binding.get("organizerAssignment"),
            dict,
        ):
            issues.append("organizer_assignment_evidence_missing")
    if plan.get("status") == "completed":
        if not isinstance(binding.get("outcome"), dict):
            issues.append("completed_outcome_evidence_missing")
        if not str(binding.get("completedAt") or "").strip():
            issues.append("completed_at_missing")
    return sorted(set(issues))


def _map_lifecycle_status(source_status: Any) -> str:
    return {
        "planning": "draft",
        "active": "published",
        "completed": "completed",
    }.get(str(source_status or ""), "")


def _map_membership_closed_reason(source_state: Any) -> str | None:
    return {
        "left": "left",
        "revoked": "removed",
    }.get(str(source_state or ""))


def _target_revision_id(source_revision_id: str) -> str:
    return f"gathering-revision:{source_revision_id}"


def _target_plan_id(gathering_id: str) -> str:
    return f"gathering-plan:{gathering_id}"


def _canonical_object_ref(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    object_type = str(value.get("objectTypeRef") or "").strip()
    object_id = str(value.get("objectId") or "").strip()
    if not object_type or not object_id:
        return None
    return {"objectTypeRef": object_type, "objectId": object_id}


def _duration_minutes(start_at: Any, end_at: Any) -> int | None:
    if not isinstance(start_at, str) or not isinstance(end_at, str):
        return None
    try:
        start = datetime.fromisoformat(start_at.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    seconds = int((end - start).total_seconds())
    return max(0, seconds // 60)


def _map_plan_item(
    value: Mapping[str, Any],
    *,
    extra_source_refs: Sequence[Mapping[str, str]] = (),
) -> dict[str, Any]:
    """把旧 activity item 收敛到 GatheringPlan 的 typed agenda item。"""

    source_refs: list[dict[str, str]] = []
    place_ref = _canonical_object_ref(value.get("placeRef"))
    if place_ref is not None:
        source_refs.append(place_ref)
    source_refs.extend(
        {
            "objectTypeRef": str(ref.get("objectTypeRef") or ""),
            "objectId": str(ref.get("objectId") or ""),
        }
        for ref in extra_source_refs
        if str(ref.get("objectTypeRef") or "").strip()
        and str(ref.get("objectId") or "").strip()
    )
    source_refs = [
        dict(value)
        for _, value in sorted(
            {
                canonical_digest(ref): ref
                for ref in source_refs
            }.items()
        )
    ]
    title = str(value.get("title") or "").strip()
    note = str(value.get("note") or "").strip()
    content = title or note
    return {
        "itemId": str(value.get("itemId") or ""),
        "kind": "agenda",
        "order": int(value.get("dayIndex") or 0) * 1000
        + int(value.get("orderInDay") or 0),
        "agenda": {
            "content": content,
            "startsAt": value.get("startAt"),
            "durationMinutes": _duration_minutes(
                value.get("startAt"),
                value.get("endAt"),
            ),
        },
        "sourceRefs": source_refs,
    }


def _mapping_record(
    object_type: str,
    object_id: str,
    value: Mapping[str, Any],
    *,
    disposition: str,
    reason: str,
    target_refs: Sequence[Mapping[str, str]] = (),
) -> dict[str, Any]:
    if disposition not in DISPOSITIONS:
        raise ValueError(f"invalid disposition: {disposition}")
    return {
        "sourceObjectType": object_type,
        "sourceObjectIdentityDigest": (
            _identity_digest(object_type, object_id)
            if object_id
            else canonical_digest(
                {"objectType": object_type, "sourceDigest": canonical_digest(value)}
            )
        ),
        "sourceObjectDigest": canonical_digest(value),
        "disposition": disposition,
        "reason": reason,
        "targetRefs": [
            {
                "objectType": str(ref.get("objectType") or ""),
                "objectIdentityDigest": _identity_digest(
                    str(ref.get("objectType") or ""),
                    str(ref.get("objectId") or ""),
                ),
            }
            for ref in target_refs
        ],
    }
