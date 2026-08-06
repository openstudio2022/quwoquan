from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from pymongo import ASCENDING, DESCENDING, ReturnDocument

from ..application.gathering_projector import (
    GatheringCandidateSnapshot,
    decide_gathering_projection,
    gathering_event_receipt_is_duplicate,
)
from ..application.projector import (
    CandidateLifecycleSnapshot,
    PremiumAdmissionSnapshot,
)


class MongoCandidateIndexStore:
    """Single owner of candidate, premium, entity-tag and tombstone projections."""

    def __init__(self, database: Any) -> None:
        self._database = database
        self._candidates = database["rm_discovery_feed"]
        self._gathering_candidates = database["rm_gathering_candidates"]
        self._premium = database["rm_premium_pool"]
        self._entity_tags = database["rm_entity_tags"]
        self._tombstones = database["recommendation_candidate_tombstones"]
        self._inbox = database["recommendation_candidate_source_inbox"]
        self._failures = database["recommendation_candidate_source_failures"]
        self._account_restrictions = database[
            "recommendation_candidate_account_restrictions"
        ]
        self._account_restriction_inbox = database[
            "recommendation_candidate_account_restriction_inbox"
        ]
        self._persona_relationships = database[
            "recommendation_candidate_persona_relationships"
        ]
        self._persona_relationship_inbox = database[
            "recommendation_candidate_persona_relationship_inbox"
        ]

    def ensure_indexes(self) -> None:
        self._candidates.create_index(
            [("scenario", ASCENDING), ("contentId", ASCENDING)],
            unique=True,
            name="uq_recommendation_candidate_scenario_content",
        )
        self._candidates.create_index(
            [("scenario", ASCENDING), ("updatedAt", DESCENDING), ("contentId", ASCENDING)],
            name="idx_recommendation_candidate_rank_scan",
        )
        self._gathering_candidates.create_index(
            [("sourceKey", ASCENDING)],
            unique=True,
            name="uq_recommendation_gathering_candidate_source",
        )
        self._gathering_candidates.create_index(
            [("updatedAt", DESCENDING), ("sourceKey", ASCENDING)],
            name="idx_recommendation_gathering_candidate_rank_scan",
        )
        self._premium.create_index(
            [("scenario", ASCENDING), ("contentId", ASCENDING)],
            unique=True,
            name="uq_recommendation_premium_scenario_content",
        )
        self._entity_tags.create_index(
            [("entityTagId", ASCENDING), ("scenario", ASCENDING), ("contentId", ASCENDING)],
            unique=True,
            name="uq_recommendation_entity_tag_candidate",
        )
        self._tombstones.create_index(
            [("sourceSequence", ASCENDING)],
            name="idx_recommendation_candidate_tombstone_sequence",
        )
        self._failures.create_index(
            [("updatedAt", ASCENDING)],
            name="idx_recommendation_candidate_source_failure_updated",
        )
        self._account_restrictions.create_index(
            [("subjectIds", ASCENDING), ("restricted", ASCENDING)],
            name="idx_recommendation_candidate_restricted_subject",
        )
        self._persona_relationships.create_index(
            [("sourcePersonaId", ASCENDING), ("targetPersonaId", ASCENDING)],
            unique=True,
            name="uq_recommendation_candidate_persona_relationship_direction",
        )
        self._persona_relationships.create_index(
            [
                ("sourcePersonaId", ASCENDING),
                ("following", ASCENDING),
                ("blocked", ASCENDING),
                ("targetPersonaId", ASCENDING),
            ],
            name="idx_recommendation_candidate_following_subject",
        )

    @staticmethod
    def _identity(scenario: str, content_id: str) -> str:
        return f"{scenario.strip()}\x1f{content_id.strip()}"

    def _refresh_entity_tags(
        self,
        *,
        identity: str,
        scenario: str,
        content_id: str,
        entity_tag_ids: tuple[str, ...],
        source_sequence: int,
        updated_at: datetime,
        session: Any,
    ) -> None:
        self._entity_tags.delete_many(
            {"scenario": scenario, "contentId": content_id},
            session=session,
        )
        if entity_tag_ids:
            self._entity_tags.insert_many(
                [
                    {
                        "_id": f"{tag_id}\x1f{identity}",
                        "entityTagId": tag_id,
                        "scenario": scenario,
                        "contentId": content_id,
                        "sourceSequence": source_sequence,
                        "updatedAt": updated_at,
                    }
                    for tag_id in entity_tag_ids
                ],
                ordered=True,
                session=session,
            )

    def _upsert_lifecycle(
        self,
        snapshot: CandidateLifecycleSnapshot,
        *,
        session: Any,
    ) -> bool:
        identity = self._identity(snapshot.scenario, snapshot.content_id)
        tombstone = self._tombstones.find_one({"_id": identity}, session=session)
        if tombstone and int(tombstone.get("sourceSequence", 0)) >= snapshot.source_sequence:
            return False
        current = self._candidates.find_one({"_id": identity}, session=session)
        if current and int(current.get("sourceSequence", 0)) >= snapshot.source_sequence:
            return False
        document = dict(current or {})
        document.update(
            {
                "_id": identity,
                "scenario": snapshot.scenario.strip(),
                "contentId": snapshot.content_id.strip(),
                "contentType": snapshot.content_type.strip(),
                "authorId": snapshot.author_id.strip(),
                "tagRefs": list(snapshot.tag_refs),
                "entityRefs": list(snapshot.entity_refs),
                "primaryHomepageId": (
                    snapshot.object_card.homepage_id if snapshot.object_card else None
                ),
                "primaryHomepageSnapshot": (
                    {
                        "homepageId": snapshot.object_card.homepage_id,
                        "canonicalEntityId": snapshot.object_card.canonical_entity_id,
                        "title": snapshot.object_card.title,
                        "subtitle": snapshot.object_card.subtitle,
                        "coverUrl": snapshot.object_card.cover_url,
                        "tagRefs": list(snapshot.object_card.tag_refs),
                    }
                    if snapshot.object_card
                    else None
                ),
                "publishedAt": snapshot.published_at.astimezone(timezone.utc),
                "contentVertical": snapshot.content_vertical,
                "entityTagIds": list(snapshot.entity_tag_ids),
                "sourceSequence": snapshot.source_sequence,
                "updatedAt": snapshot.updated_at.astimezone(timezone.utc),
            }
        )
        restriction = self._account_restrictions.find_one(
            {"subjectIds": snapshot.author_id, "restricted": True},
            {"_id": 1},
            session=session,
        )
        document["accountRestricted"] = restriction is not None
        for name, default in (
            ("viewCount", 0),
            ("likeCount", 0),
            ("commentCount", 0),
            ("shareCount", 0),
            ("qualityScore", 0.0),
            ("supplySource", None),
            ("intersectionFeatures", {}),
            ("premiumEligible", False),
            ("premiumExpiresAt", None),
            ("premiumAdmissionUpdatedAt", None),
        ):
            document.setdefault(name, default)
        premium = self._premium.find_one({"_id": identity}, session=session)
        if premium is not None:
            expires_at = premium.get("expiresAt")
            document["premiumEligible"] = bool(
                premium.get("eligibilityState") == "eligible"
                and isinstance(expires_at, datetime)
                and expires_at > datetime.now(timezone.utc)
            )
            document["premiumExpiresAt"] = expires_at
            document["premiumAdmissionUpdatedAt"] = premium.get("updatedAt")
        self._candidates.replace_one(
            {"_id": identity},
            document,
            upsert=True,
            session=session,
        )
        self._refresh_entity_tags(
            identity=identity,
            scenario=snapshot.scenario,
            content_id=snapshot.content_id,
            entity_tag_ids=snapshot.entity_tag_ids,
            source_sequence=snapshot.source_sequence,
            updated_at=document["updatedAt"],
            session=session,
        )
        return True

    def upsert_lifecycle_if_newer(self, snapshot: CandidateLifecycleSnapshot) -> bool:
        with self._database.client.start_session() as session:
            with session.start_transaction():
                return self._upsert_lifecycle(snapshot, session=session)

    def _remove_if_newer(
        self,
        *,
        scenario: str,
        content_id: str,
        source_sequence: int,
        session: Any,
    ) -> bool:
        identity = self._identity(scenario, content_id)
        current = self._tombstones.find_one({"_id": identity}, session=session)
        if current and int(current.get("sourceSequence", 0)) >= source_sequence:
            return False
        candidate = self._candidates.find_one({"_id": identity}, session=session)
        if candidate and int(candidate.get("sourceSequence", 0)) > source_sequence:
            return False
        self._tombstones.update_one(
            {"_id": identity},
            {"$set": {"sourceSequence": source_sequence}},
            upsert=True,
            session=session,
        )
        deleted = self._candidates.delete_one(
            {"_id": identity},
            session=session,
        )
        self._premium.update_many(
            {"scenario": scenario, "contentId": content_id},
            {
                "$set": {
                    "eligibilityState": "ineligible",
                    "ineligibleReasons": ["content_removed"],
                }
            },
            session=session,
        )
        self._entity_tags.delete_many(
            {"scenario": scenario, "contentId": content_id},
            session=session,
        )
        return deleted.deleted_count == 1

    def remove_if_newer(self, *, scenario: str, content_id: str, source_sequence: int) -> bool:
        with self._database.client.start_session() as session:
            with session.start_transaction():
                return self._remove_if_newer(
                    scenario=scenario,
                    content_id=content_id,
                    source_sequence=source_sequence,
                    session=session,
                )

    def source_event_applied(self, event_id: str, *, session: Any = None) -> bool:
        return self._inbox.find_one(
            {"_id": event_id.strip()},
            {"_id": 1},
            session=session,
        ) is not None

    def apply_source_event(
        self,
        *,
        event_id: str,
        snapshot: CandidateLifecycleSnapshot | None = None,
        removal: tuple[str, str, int] | None = None,
    ) -> bool:
        normalized_event_id = event_id.strip()
        if not normalized_event_id or snapshot is not None and removal is not None:
            raise ValueError("candidate source event identity or mutation is invalid")
        if self.source_event_applied(normalized_event_id):
            return False
        with self._database.client.start_session() as session:
            with session.start_transaction():
                if self.source_event_applied(normalized_event_id, session=session):
                    return False
                changed = False
                if snapshot is not None:
                    changed = self._upsert_lifecycle(snapshot, session=session)
                elif removal is not None:
                    scenario, content_id, source_sequence = removal
                    changed = self._remove_if_newer(
                        scenario=scenario,
                        content_id=content_id,
                        source_sequence=source_sequence,
                        session=session,
                    )
                self._inbox.insert_one(
                    {
                        "_id": normalized_event_id,
                        "contentId": snapshot.content_id if snapshot else removal[1] if removal else None,
                        "sourceSequence": snapshot.source_sequence if snapshot else removal[2] if removal else None,
                        "changed": changed,
                        "appliedAt": datetime.now(timezone.utc),
                    },
                    session=session,
                )
                return changed

    @staticmethod
    def _gathering_identity(gathering_id: str) -> str:
        return f"gathering\x1f{gathering_id.strip()}"

    def apply_gathering_source_event(
        self,
        *,
        event_id: str,
        event_digest: str,
        snapshot: GatheringCandidateSnapshot | None = None,
        removal: tuple[str, int] | None = None,
    ) -> bool:
        normalized_event_id = event_id.strip()
        normalized_digest = event_digest.strip().lower()
        if (
            not normalized_event_id
            or len(normalized_digest) != 64
            or any(value not in "0123456789abcdef" for value in normalized_digest)
            or (snapshot is None) == (removal is None)
        ):
            raise ValueError("Gathering candidate source event is incomplete")
        gathering_id = (
            snapshot.gathering_id.strip() if snapshot is not None else removal[0].strip()
        )
        source_version = (
            snapshot.source_version if snapshot is not None else int(removal[1])
        )
        if not gathering_id or source_version <= 0:
            raise ValueError("Gathering candidate source identity is incomplete")
        identity = self._gathering_identity(gathering_id)

        with self._database.client.start_session() as session:
            with session.start_transaction():
                receipt = self._inbox.find_one(
                    {"_id": normalized_event_id},
                    session=session,
                )
                if gathering_event_receipt_is_duplicate(
                    recorded_event_digest=(
                        str(receipt.get("eventDigest")) if receipt is not None else None
                    ),
                    incoming_event_digest=normalized_digest,
                ):
                    return False

                current = self._gathering_candidates.find_one(
                    {"_id": identity},
                    session=session,
                )
                tombstone = self._tombstones.find_one(
                    {"_id": identity},
                    session=session,
                )
                current_version = int((current or {}).get("sourceVersion") or 0)
                tombstone_version = int((tombstone or {}).get("sourceVersion") or 0)
                changed = False
                decision = decide_gathering_projection(
                    current_version=current_version,
                    current_card_digest=(current or {}).get("cardDigest"),
                    tombstone_version=tombstone_version,
                    incoming_version=source_version,
                    incoming_card_digest=(
                        snapshot.card_digest if snapshot is not None else None
                    ),
                    removal=removal is not None,
                )
                stale = decision == "ignore"

                if snapshot is not None and decision == "upsert":
                    document = {
                            "_id": identity,
                            "objectKind": "gathering",
                            "sourceKey": gathering_id,
                            "sourceVersion": source_version,
                            "cardDigest": snapshot.card_digest,
                            "hostSubjectKind": snapshot.host_subject_kind.strip(),
                            "hostSubjectId": snapshot.host_subject_id.strip(),
                            "title": snapshot.title.strip(),
                            "summary": (
                                snapshot.summary.strip() if snapshot.summary else None
                            ),
                            "coverRef": (
                                {
                                    "objectTypeRef": snapshot.cover_object_type_ref,
                                    "objectId": snapshot.cover_object_id,
                                }
                                if snapshot.cover_object_id
                                else None
                            ),
                            "tagRefs": list(snapshot.tag_refs),
                            "startAt": (
                                snapshot.start_at.astimezone(timezone.utc)
                                if snapshot.start_at
                                else None
                            ),
                            "endAt": (
                                snapshot.end_at.astimezone(timezone.utc)
                                if snapshot.end_at
                                else None
                            ),
                            "dateLabel": snapshot.date_label,
                            "placeMode": snapshot.place_mode.strip(),
                            "coarsePlaceRef": (
                                {
                                    "objectTypeRef": (
                                        snapshot.coarse_place_object_type_ref
                                    ),
                                    "objectId": snapshot.coarse_place_object_id,
                                }
                                if snapshot.coarse_place_object_id
                                else None
                            ),
                            "coarsePlaceLabel": snapshot.coarse_place_label,
                            "maxParticipants": snapshot.max_participants,
                            "occupiedSeats": snapshot.occupied_seats,
                            "remainingSeats": snapshot.remaining_seats,
                            "full": snapshot.full,
                            "admissionState": snapshot.admission_state.strip(),
                            "lifecycleStatus": snapshot.lifecycle_status,
                            "updatedAt": snapshot.updated_at.astimezone(timezone.utc),
                    }
                    self._gathering_candidates.replace_one(
                        {"_id": identity},
                        document,
                        upsert=True,
                        session=session,
                    )
                    self._tombstones.delete_one(
                        {"_id": identity},
                        session=session,
                    )
                    changed = True
                elif removal is not None and decision == "remove":
                    card_digest = (current or {}).get("cardDigest")
                    self._tombstones.replace_one(
                        {"_id": identity},
                        {
                            "_id": identity,
                            "objectKind": "gathering",
                            "sourceKey": gathering_id,
                            "sourceVersion": source_version,
                            "cardDigest": card_digest,
                            "removedAt": datetime.now(timezone.utc),
                        },
                        upsert=True,
                        session=session,
                    )
                    self._gathering_candidates.delete_one(
                        {"_id": identity},
                        session=session,
                    )
                    changed = True

                self._inbox.insert_one(
                    {
                        "_id": normalized_event_id,
                        "source": "circle_gathering",
                        "sourceKey": gathering_id,
                        "sourceVersion": source_version,
                        "eventDigest": normalized_digest,
                        "changed": changed,
                        "stale": stale,
                        "appliedAt": datetime.now(timezone.utc),
                    },
                    session=session,
                )
                return changed

    def apply_account_restriction_event(
        self,
        *,
        event_id: str,
        event_digest: str,
        account_id: str,
        account_version: int,
        subject_ids: tuple[str, ...],
        restricted: bool,
        terminal: bool = False,
    ) -> int:
        normalized_event_id = event_id.strip()
        normalized_digest = event_digest.strip()
        normalized_account_id = account_id.strip()
        normalized_subjects = tuple(
            dict.fromkeys(value.strip() for value in subject_ids if value.strip())
        )
        if (
            not normalized_event_id
            or len(normalized_digest) != 64
            or any(value not in "0123456789abcdef" for value in normalized_digest)
            or not normalized_account_id
            or account_version <= 0
            or normalized_account_id not in normalized_subjects
        ):
            raise ValueError("candidate account restriction event is incomplete")
        with self._database.client.start_session() as session:
            with session.start_transaction():
                receipt = self._account_restriction_inbox.find_one(
                    {"_id": normalized_event_id},
                    session=session,
                )
                if receipt is not None:
                    if receipt.get("eventDigest") != normalized_digest:
                        raise RuntimeError(
                            "candidate account restriction event identity conflict"
                        )
                    return int(receipt.get("affected") or 0)

                affected = 0
                stale = terminal
                current = self._account_restrictions.find_one(
                    {"_id": normalized_account_id},
                    session=session,
                )
                if not terminal and current is not None:
                    current_version = int(current.get("accountVersion") or 0)
                    if current_version > account_version:
                        stale = True
                    elif current_version == account_version:
                        if current.get("eventDigest") != normalized_digest:
                            raise RuntimeError(
                                "candidate account restriction version conflict"
                            )
                        stale = True

                if not stale:
                    result = self._candidates.update_many(
                        {"authorId": {"$in": list(normalized_subjects)}},
                        {
                            "$set": {
                                "accountRestricted": restricted,
                                "accountRestrictionVersion": account_version,
                                "accountRestrictionUpdatedAt": datetime.now(
                                    timezone.utc
                                ),
                            }
                        },
                        session=session,
                    )
                    affected = int(result.modified_count)
                    self._account_restrictions.replace_one(
                        {"_id": normalized_account_id},
                        {
                            "_id": normalized_account_id,
                            "subjectIds": list(normalized_subjects),
                            "restricted": restricted,
                            "accountVersion": account_version,
                            "eventDigest": normalized_digest,
                            "updatedAt": datetime.now(timezone.utc),
                        },
                        upsert=True,
                        session=session,
                    )

                self._account_restriction_inbox.insert_one(
                    {
                        "_id": normalized_event_id,
                        "eventDigest": normalized_digest,
                        "accountVersion": account_version,
                        "restricted": restricted,
                        "terminal": terminal,
                        "stale": stale,
                        "affected": affected,
                        "appliedAt": datetime.now(timezone.utc),
                    },
                    session=session,
                )
                return affected

    @staticmethod
    def _relationship_identity(source_persona_id: str, target_persona_id: str) -> str:
        return f"{source_persona_id.strip()}\x1f{target_persona_id.strip()}"

    def apply_persona_relationship_event(
        self,
        *,
        event_id: str,
        event_digest: str,
        event_name: str,
        source_persona_id: str,
        target_persona_id: str,
        following: bool,
        version: int,
        occurred_at: datetime,
    ) -> bool:
        normalized_event_id = event_id.strip()
        normalized_digest = event_digest.strip()
        normalized_name = event_name.strip()
        source_id = source_persona_id.strip()
        target_id = target_persona_id.strip()
        if (
            not normalized_event_id
            or len(normalized_digest) != 64
            or any(value not in "0123456789abcdef" for value in normalized_digest)
            or normalized_name
            not in {"PersonaFollowStateChanged", "PersonaBlocked", "PersonaUnblocked"}
            or not source_id
            or not target_id
            or source_id == target_id
            or version <= 0
            or occurred_at.tzinfo is None
        ):
            raise ValueError("candidate persona relationship event is incomplete")

        directions = ((source_id, target_id),)
        if normalized_name in {"PersonaBlocked", "PersonaUnblocked"}:
            directions = ((source_id, target_id), (target_id, source_id))

        with self._database.client.start_session() as session:
            with session.start_transaction():
                receipt = self._persona_relationship_inbox.find_one(
                    {"_id": normalized_event_id},
                    session=session,
                )
                if receipt is not None:
                    if receipt.get("eventDigest") != normalized_digest:
                        raise RuntimeError(
                            "candidate persona relationship event identity conflict"
                        )
                    return bool(receipt.get("changed"))

                changed = False
                for direction_source, direction_target in directions:
                    identity = self._relationship_identity(
                        direction_source,
                        direction_target,
                    )
                    current = self._persona_relationships.find_one(
                        {"_id": identity},
                        session=session,
                    ) or {}
                    current_version = int(current.get("version") or 0)
                    if current_version > version:
                        continue
                    if current_version == version:
                        if current.get("eventDigest") != normalized_digest:
                            raise RuntimeError(
                                "candidate persona relationship version conflict"
                            )
                        continue

                    next_following = bool(current.get("following"))
                    next_blocked = bool(current.get("blocked"))
                    if normalized_name == "PersonaFollowStateChanged":
                        next_following = following
                    elif normalized_name == "PersonaBlocked":
                        next_following = False
                        next_blocked = True
                    else:
                        # Unblocking never restores the follow state that the
                        # block command cleared.
                        next_following = False
                        next_blocked = False
                    self._persona_relationships.replace_one(
                        {"_id": identity},
                        {
                            "_id": identity,
                            "sourcePersonaId": direction_source,
                            "targetPersonaId": direction_target,
                            "following": next_following,
                            "blocked": next_blocked,
                            "version": version,
                            "eventDigest": normalized_digest,
                            "updatedAt": occurred_at.astimezone(timezone.utc),
                        },
                        upsert=True,
                        session=session,
                    )
                    changed = True

                self._persona_relationship_inbox.insert_one(
                    {
                        "_id": normalized_event_id,
                        "eventDigest": normalized_digest,
                        "eventName": normalized_name,
                        "version": version,
                        "changed": changed,
                        "appliedAt": datetime.now(timezone.utc),
                    },
                    session=session,
                )
                return changed

    def following_persona_ids(self, source_persona_id: str) -> tuple[str, ...]:
        normalized_source = source_persona_id.strip()
        if not normalized_source:
            raise ValueError("following source persona identity is required")
        return tuple(
            str(document.get("targetPersonaId") or "").strip()
            for document in self._persona_relationships.find(
                {
                    "sourcePersonaId": normalized_source,
                    "following": True,
                    "blocked": {"$ne": True},
                },
                {"targetPersonaId": 1},
            ).sort("targetPersonaId", ASCENDING)
            if str(document.get("targetPersonaId") or "").strip()
        )

    def erase_subject(self, subject_id: str) -> int:
        normalized_subject = subject_id.strip()
        if not normalized_subject:
            raise ValueError("candidate subject identity is required")
        with self._database.client.start_session() as session:
            with session.start_transaction():
                candidates = list(
                    self._candidates.find(
                        {"authorId": normalized_subject},
                        {"scenario": 1, "contentId": 1, "sourceSequence": 1},
                        session=session,
                    )
                )
                removed = 0
                for candidate in candidates:
                    scenario = str(candidate.get("scenario") or "").strip()
                    content_id = str(candidate.get("contentId") or "").strip()
                    source_sequence = int(candidate.get("sourceSequence") or 0)
                    if scenario and content_id and source_sequence > 0:
                        removed += int(
                            self._remove_if_newer(
                                scenario=scenario,
                                content_id=content_id,
                                source_sequence=source_sequence,
                                session=session,
                            )
                        )
                self._account_restrictions.delete_many(
                    {"subjectIds": normalized_subject},
                    session=session,
                )
                self._persona_relationships.delete_many(
                    {
                        "$or": [
                            {"sourcePersonaId": normalized_subject},
                            {"targetPersonaId": normalized_subject},
                        ]
                    },
                    session=session,
                )
                return removed

    def apply_premium_source_event(
        self,
        *,
        event_id: str,
        snapshot: PremiumAdmissionSnapshot,
    ) -> bool:
        normalized_event_id = event_id.strip()
        identity = self._identity("content_feed", snapshot.content_id)
        with self._database.client.start_session() as session:
            with session.start_transaction():
                if self.source_event_applied(normalized_event_id, session=session):
                    return False
                current = self._premium.find_one({"_id": identity}, session=session)
                changed = not (
                    current is not None
                    and isinstance(current.get("updatedAt"), datetime)
                    and current["updatedAt"] >= snapshot.updated_at
                )
                if changed:
                    now = datetime.now(timezone.utc)
                    eligible = snapshot.eligible_at(now)
                    reasons: list[str] = []
                    if snapshot.status != "active":
                        reasons.append(snapshot.status)
                    if snapshot.takedown_ejected and "takedown_ejected" not in reasons:
                        reasons.append("takedown_ejected")
                    if snapshot.expires_at <= now:
                        reasons.append("expired")
                    if snapshot.quality_score < 0.75:
                        reasons.append("quality_below_threshold")
                    document = {
                        "_id": identity,
                        "scenario": "content_feed",
                        "contentId": snapshot.content_id,
                        "scope": snapshot.scope,
                        "status": snapshot.status,
                        "eligibilityState": "eligible" if eligible else "ineligible",
                        "ineligibleReasons": reasons,
                        "qualityAdmission": snapshot.quality_admission,
                        "qualityScore": snapshot.quality_score,
                        "supplySource": snapshot.supply_source,
                        "sourceTaskId": snapshot.source_task_id,
                        "auditId": snapshot.audit_id,
                        "rollbackToken": snapshot.rollback_token,
                        "featuredAt": snapshot.featured_at,
                        "expiresAt": snapshot.expires_at,
                        "takedownEjected": snapshot.takedown_ejected,
                        "updatedAt": snapshot.updated_at,
                    }
                    self._premium.replace_one(
                        {"_id": identity},
                        document,
                        upsert=True,
                        session=session,
                    )
                    self._candidates.update_one(
                        {"_id": identity},
                        {
                            "$set": {
                                "premiumEligible": eligible,
                                "premiumExpiresAt": snapshot.expires_at,
                                "premiumAdmissionUpdatedAt": snapshot.updated_at,
                            }
                        },
                        session=session,
                    )
                self._inbox.insert_one(
                    {
                        "_id": normalized_event_id,
                        "source": "premium_pool",
                        "contentId": snapshot.content_id,
                        "changed": changed,
                        "appliedAt": datetime.now(timezone.utc),
                    },
                    session=session,
                )
                return changed

    def record_source_failure(self, stream_id: str, event_id: str, cause: Exception) -> int:
        message = str(cause)[:1024]
        document = self._failures.find_one_and_update(
            {"_id": stream_id.strip()},
            {
                "$inc": {"attempts": 1},
                "$set": {
                    "eventId": event_id.strip(),
                    "lastError": message,
                    "updatedAt": datetime.now(timezone.utc),
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return int(document.get("attempts", 0))

    def clear_source_failure(self, stream_id: str) -> None:
        self._failures.delete_one({"_id": stream_id.strip()})

    @staticmethod
    def ranking_query(
        scenario: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        normalized_scenario = scenario.strip()
        query: dict[str, Any] = {
            "scenario": "content_feed",
            "accountRestricted": {"$ne": True},
        }
        if normalized_scenario == "premium_stream":
            query["premiumEligible"] = True
            query["premiumExpiresAt"] = {"$gt": now or datetime.now(timezone.utc)}
        elif normalized_scenario == "travel_photography":
            query["contentVertical"] = "travel_photography"
        elif normalized_scenario != "content_feed":
            raise ValueError("unsupported recommendation ranking scenario")
        return query

    def list_for_ranking(
        self,
        *,
        scenario: str,
        subject_id: str = "",
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        normalized_scenario = scenario.strip()
        query = self.ranking_query(
            "content_feed" if normalized_scenario == "following" else normalized_scenario
        )
        if normalized_scenario == "following":
            followed = self.following_persona_ids(subject_id)
            if not followed:
                return []
            query["authorId"] = {"$in": list(followed)}
        return list(
            self._candidates.find(query).sort(
                [("updatedAt", DESCENDING), ("contentId", ASCENDING)]
            ).limit(max(1, min(limit, 500)))
        )

    def list_object_card_candidates(self, *, limit: int = 400) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(limit, 400))
        entity_candidates = list(
            self._candidates.find(
                {
                    "scenario": "content_feed",
                    "accountRestricted": {"$ne": True},
                    "primaryHomepageId": {"$type": "string", "$ne": ""},
                    "primaryHomepageSnapshot": {"$type": "object"},
                },
                {
                    "_id": 0,
                    "primaryHomepageId": 1,
                    "primaryHomepageSnapshot": 1,
                    "updatedAt": 1,
                },
            )
            .sort([("updatedAt", DESCENDING), ("primaryHomepageId", ASCENDING)])
            .limit(bounded_limit)
        )
        for candidate in entity_candidates:
            candidate["objectKind"] = "entity_homepage"
        gathering_candidates = list(
            self._gathering_candidates.find(
                {"lifecycleStatus": "published"},
                {
                    "_id": 0,
                    "objectKind": 1,
                    "sourceKey": 1,
                    "sourceVersion": 1,
                    "cardDigest": 1,
                    "title": 1,
                    "summary": 1,
                    "coverRef": 1,
                    "tagRefs": 1,
                    "startAt": 1,
                    "endAt": 1,
                    "dateLabel": 1,
                    "placeMode": 1,
                    "coarsePlaceRef": 1,
                    "coarsePlaceLabel": 1,
                    "updatedAt": 1,
                },
            )
            .sort([("updatedAt", DESCENDING), ("sourceKey", ASCENDING)])
            .limit(bounded_limit)
        )

        def order_key(value: Mapping[str, Any]) -> tuple[float, str]:
            updated_at = value.get("updatedAt")
            timestamp = (
                updated_at.timestamp() if isinstance(updated_at, datetime) else 0.0
            )
            identity = str(
                value.get("sourceKey") or value.get("primaryHomepageId") or ""
            )
            return (-timestamp, identity)

        return sorted(
            [*entity_candidates, *gathering_candidates],
            key=order_key,
        )[:bounded_limit]
