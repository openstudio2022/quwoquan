from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING, DESCENDING, ReturnDocument

from ..application.projector import (
    CandidateLifecycleSnapshot,
    PremiumAdmissionSnapshot,
)


class MongoCandidateIndexStore:
    """Single owner of candidate, premium, entity-tag and tombstone projections."""

    def __init__(self, database: Any) -> None:
        self._database = database
        self._candidates = database["rm_discovery_feed"]
        self._premium = database["rm_premium_pool"]
        self._entity_tags = database["rm_entity_tags"]
        self._tombstones = database["recommendation_candidate_tombstones"]
        self._inbox = database["recommendation_candidate_source_inbox"]
        self._failures = database["recommendation_candidate_source_failures"]

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
                "publishedAt": snapshot.published_at.astimezone(timezone.utc),
                "contentVertical": snapshot.content_vertical,
                "entityTagIds": list(snapshot.entity_tag_ids),
                "sourceSequence": snapshot.source_sequence,
                "updatedAt": snapshot.updated_at.astimezone(timezone.utc),
            }
        )
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
        query: dict[str, Any] = {"scenario": "content_feed"}
        if normalized_scenario == "premium_stream":
            query["premiumEligible"] = True
            query["premiumExpiresAt"] = {"$gt": now or datetime.now(timezone.utc)}
        elif normalized_scenario == "travel_photography":
            query["contentVertical"] = "travel_photography"
        elif normalized_scenario != "content_feed":
            raise ValueError("unsupported recommendation ranking scenario")
        return query

    def list_for_ranking(self, *, scenario: str, limit: int = 500) -> list[dict[str, Any]]:
        query = self.ranking_query(scenario)
        return list(
            self._candidates.find(query).sort(
                [("updatedAt", DESCENDING), ("contentId", ASCENDING)]
            ).limit(max(1, min(limit, 500)))
        )
