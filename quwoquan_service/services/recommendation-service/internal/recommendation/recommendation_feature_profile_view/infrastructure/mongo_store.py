from __future__ import annotations

from datetime import datetime, timezone
import base64
import hashlib
import json
import math
from typing import Any, Mapping

from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

from ..application.projector import (
    BehaviorFeatureMutation,
    ExposureFeatureMutation,
    TagFeedbackMutation,
)
from ..application.author_impact_reader import (
    AuthorImpactEvidence,
    AuthorImpactEvidencePage,
    AuthorImpactItem,
    AuthorImpactSummary,
)
from ..application.intersection_reader import (
    IntersectionSupplySnapshot,
    ObjectIntersectionSnapshot,
    SubjectIntersectionSnapshot,
)
from ..application.intersection_projector import (
    IntersectionSupplyMaterialization,
    ObjectIntersectionMaterialization,
    SubjectIntersectionMaterialization,
)
from ..application.intersection_materializer import (
    BehaviorSnapshot,
    PersonaProfileSnapshot,
)
from ..application.intersection_rebuild import (
    IntersectionProjectionInventory,
    IntersectionSupplyInventory,
)


MAX_PROFILE_FEATURE_KEYS = 256
MAX_COLLABORATIVE_NEIGHBORS = 128
MAX_HARD_EXCLUSIONS = 1000


class MongoFeatureProfileStore:
    """Single owner of the long-lived recommendation feature profile."""

    def __init__(self, database: Any) -> None:
        self._profiles = database["rm_recommend_feature"]
        self._author_impact = database["rm_author_impact"]
        self._author_impact_evidence = database["rm_author_impact_evidence"]
        self._collaborative_i2i = database["rm_collaborative_i2i"]
        self._collaborative_u2i = database["rm_collaborative_u2i"]
        self._intersection_features = database["rm_intersection_feature"]
        self._intersection_reasons = database["rm_viewer_object_intersection"]
        self._intersection_supply = database["rm_intersection_supply"]
        self._intersection_inbox = database[
            "recommendation_intersection_projection_inbox"
        ]
        self._intersection_relationships = database[
            "recommendation_intersection_persona_relationships"
        ]
        self._intersection_memberships = database[
            "recommendation_intersection_circle_memberships"
        ]
        self._intersection_behaviors = database[
            "recommendation_intersection_behaviors"
        ]
        self._intersection_wishlist = database[
            "recommendation_intersection_wishlist_state"
        ]
        self._intersection_persona_profiles = database[
            "recommendation_intersection_persona_profiles"
        ]
        self._intersection_declared_visits = database[
            "recommendation_intersection_declared_visits"
        ]
        self._checkpoints = database["recommendation_feature_projection_checkpoints"]
        self._failures = database["recommendation_feature_projection_failures"]

    def ensure_indexes(self) -> None:
        self._profiles.create_index(
            [("subjectId", ASCENDING)],
            unique=True,
            name="uq_recommendation_feature_subject",
        )
        self._author_impact.create_index(
            [("authorId", ASCENDING), ("impactId", ASCENDING)],
            unique=True,
            name="uq_recommendation_author_impact",
        )
        self._author_impact.create_index(
            [("authorId", ASCENDING), ("count", DESCENDING), ("updatedAt", DESCENDING)],
            name="idx_recommendation_author_impact_rank",
        )
        self._author_impact_evidence.create_index(
            [("eventId", ASCENDING), ("authorId", ASCENDING), ("impactId", ASCENDING)],
            unique=True,
            name="uq_recommendation_author_impact_evidence",
        )
        self._author_impact_evidence.create_index(
            [
                ("authorId", ASCENDING),
                ("impactId", ASCENDING),
                ("occurredAt", DESCENDING),
                ("_id", DESCENDING),
            ],
            name="idx_recommendation_author_impact_evidence_page",
        )
        self._collaborative_i2i.create_index(
            [("leftContentId", ASCENDING), ("rightContentId", ASCENDING)],
            unique=True,
            name="uq_recommendation_collaborative_i2i_pair",
        )
        self._collaborative_u2i.create_index(
            [("subjectId", ASCENDING), ("contentId", ASCENDING)],
            unique=True,
            name="uq_recommendation_collaborative_u2i_pair",
        )
        self._collaborative_u2i.create_index(
            [("subjectId", ASCENDING), ("score", DESCENDING), ("updatedAt", DESCENDING)],
            name="idx_recommendation_collaborative_u2i_subject_score",
        )
        self._intersection_features.create_index(
            [("subjectId", ASCENDING), ("feature", ASCENDING)],
            unique=True,
            name="uq_recommendation_intersection_subject_feature",
        )
        self._intersection_reasons.create_index(
            [("subjectId", ASCENDING), ("scopeKind", ASCENDING), ("scopeKey", ASCENDING)],
            unique=True,
            name="uq_recommendation_intersection_subject_scope",
        )
        self._intersection_reasons.create_index(
            [("generatedAt", DESCENDING)],
            name="idx_recommendation_intersection_generated",
        )
        self._intersection_supply.create_index(
            [("supplyKey", ASCENDING)],
            unique=True,
            name="uq_recommendation_intersection_supply_key",
        )
        self._intersection_inbox.create_index(
            [("sourceEventId", ASCENDING), ("scopeKind", ASCENDING)],
            name="idx_recommendation_intersection_projection_source",
        )
        self._intersection_relationships.create_index(
            [("sourcePersonaId", ASCENDING), ("following", ASCENDING), ("targetPersonaId", ASCENDING)],
            name="idx_recommendation_intersection_following",
        )
        self._intersection_relationships.create_index(
            [("targetPersonaId", ASCENDING), ("following", ASCENDING), ("sourcePersonaId", ASCENDING)],
            name="idx_recommendation_intersection_followers",
        )
        self._intersection_memberships.create_index(
            [("personaId", ASCENDING), ("active", ASCENDING), ("circleId", ASCENDING)],
            name="idx_recommendation_intersection_membership_persona",
        )
        self._intersection_memberships.create_index(
            [("circleId", ASCENDING), ("active", ASCENDING), ("personaId", ASCENDING)],
            name="idx_recommendation_intersection_membership_circle",
        )
        self._intersection_behaviors.create_index(
            [("subjectId", ASCENDING), ("occurredAt", DESCENDING), ("_id", DESCENDING)],
            name="idx_recommendation_intersection_behavior_subject",
        )
        self._intersection_behaviors.create_index(
            [("action", ASCENDING), ("entityRefs", ASCENDING)],
            name="idx_recommendation_intersection_behavior_entity",
        )
        self._intersection_wishlist.create_index(
            [("active", ASCENDING), ("entityId", ASCENDING)],
            name="idx_recommendation_intersection_wishlist_active",
        )
        self._intersection_declared_visits.create_index(
            [("active", ASCENDING), ("entityId", ASCENDING)],
            name="idx_recommendation_intersection_declared_visit_active",
        )
        self._intersection_persona_profiles.create_index(
            [("personaId", ASCENDING), ("occurredAt", DESCENDING), ("_id", DESCENDING)],
            name="idx_recommendation_intersection_persona_profile_latest",
        )
        self._checkpoints.create_index(
            [("subjectId", ASCENDING), ("appliedAt", DESCENDING)],
            name="idx_recommendation_feature_checkpoint_subject",
        )
        self._failures.create_index(
            [("updatedAt", DESCENDING)],
            name="idx_recommendation_feature_failure_updated",
        )

    def record_source_failure(
        self,
        stream_id: str,
        event_id: str,
        cause: Exception,
    ) -> int:
        normalized_stream_id = stream_id.strip()
        if not normalized_stream_id:
            raise ValueError("feature projection failure streamId is required")
        self._failures.update_one(
            {"_id": normalized_stream_id},
            {
                "$set": {
                    "eventId": event_id.strip(),
                    "error": str(cause)[:1024],
                    "updatedAt": datetime.now(timezone.utc),
                },
                "$inc": {"attempts": 1},
            },
            upsert=True,
        )
        document = self._failures.find_one(
            {"_id": normalized_stream_id},
            {"attempts": 1},
        ) or {}
        return int(document.get("attempts") or 0)

    def clear_source_failure(self, stream_id: str) -> None:
        self._failures.delete_one({"_id": stream_id.strip()})

    def read_for_scoring(self, subject_id: str) -> dict[str, Any]:
        document = self._profiles.find_one({"_id": subject_id.strip()})
        if document is None:
            return {
                "checkpoint": 0,
                "sparseFeatures": {},
                "tagAffinities": {},
                "influenceScore": 0.0,
                "collaborativeFeatures": {},
                "intersectionFeatures": {},
                "negativeContentIds": [],
                "hiddenAuthorIds": [],
                "hiddenContentTypes": [],
            }
        sparse = dict(document.get("sparseFeatures") or {})
        return {
            "checkpoint": int(document.get("checkpoint", 0)),
            "sparseFeatures": sparse,
            "tagAffinities": dict(document.get("tagAffinities") or {}),
            "influenceScore": float(document.get("influenceScore", 0.0)),
            "collaborativeFeatures": dict(document.get("collaborativeFeatures") or {}),
            "intersectionFeatures": dict(document.get("intersectionFeatures") or {}),
            "negativeContentIds": list(document.get("negativeContentIds") or []),
            "hiddenAuthorIds": list(document.get("hiddenAuthorIds") or []),
            "hiddenContentTypes": list(document.get("hiddenContentTypes") or []),
        }

    def read_subject_intersections(
        self,
        subject_id: str,
        intersection_class: str,
        channel: str,
    ) -> SubjectIntersectionSnapshot:
        scope_key = f"{intersection_class}\x1f{channel}"
        document = self._intersection_reasons.find_one(
            {
                "subjectId": subject_id,
                "scopeKind": "subject",
                "scopeKey": scope_key,
            }
        )
        resolved_channel = channel
        if document is None and channel:
            document = self._intersection_reasons.find_one(
                {
                    "subjectId": subject_id,
                    "scopeKind": "subject",
                    "scopeKey": f"{intersection_class}\x1f",
                }
            )
            resolved_channel = ""
        if document is None:
            raise RuntimeError("subject intersection projection is unavailable")
        return SubjectIntersectionSnapshot(
            subject_id=subject_id,
            intersection_class=intersection_class,
            channel=resolved_channel,
            reasons=tuple(dict(reason) for reason in document.get("reasons") or []),
            generated_at=self._utc_datetime(document.get("generatedAt")),
        )

    def read_object_intersections(
        self,
        subject_id: str,
        object_type: str,
        object_id: str,
    ) -> ObjectIntersectionSnapshot:
        scope_key = f"{object_type}\x1f{object_id}"
        document = self._intersection_reasons.find_one(
            {
                "subjectId": subject_id,
                "scopeKind": "object",
                "scopeKey": scope_key,
            }
        )
        if document is None:
            raise RuntimeError("object intersection projection is unavailable")
        return ObjectIntersectionSnapshot(
            subject_id=subject_id,
            object_type=object_type,
            object_id=object_id,
            reasons=tuple(dict(reason) for reason in document.get("reasons") or []),
            generated_at=self._utc_datetime(document.get("generatedAt")),
        )

    def read_intersection_supply(self, supply_key: str) -> IntersectionSupplySnapshot:
        document = self._intersection_supply.find_one({"supplyKey": supply_key})
        if document is None:
            raise RuntimeError("intersection supply projection is unavailable")
        return IntersectionSupplySnapshot(
            supply_key=supply_key,
            distinct_object_count=int(document.get("distinctObjectCount") or 0),
            computed_at=self._utc_datetime(document.get("computedAt")),
        )

    @staticmethod
    def _intersection_receipt_id(
        source_event_id: str,
        scope_kind: str,
        scope_key: str,
    ) -> str:
        return f"{source_event_id}\x1f{scope_kind}\x1f{scope_key}"

    def _existing_intersection_receipt(
        self,
        *,
        receipt_id: str,
        expected_digest: str,
        session: Any | None = None,
    ) -> bool:
        receipt = self._intersection_inbox.find_one(
            {"_id": receipt_id},
            {"sourceEventDigest": 1},
            session=session,
        )
        if receipt is None:
            return False
        if str(receipt.get("sourceEventDigest") or "") != expected_digest:
            raise RuntimeError(
                "intersection projection source event conflicts with an existing receipt"
            )
        return True

    def replace_subject_intersections_if_absent(
        self,
        mutation: SubjectIntersectionMaterialization,
    ) -> bool:
        scope_key = f"{mutation.intersection_class}\x1f{mutation.channel}"
        return self._replace_intersection_snapshot_if_absent(
            source_event_id=mutation.source_event_id,
            source_event_digest=mutation.source_event_digest,
            subject_id=mutation.subject_id,
            scope_kind="subject",
            scope_key=scope_key,
            reasons=mutation.reasons,
            generated_at=mutation.generated_at,
        )

    def replace_object_intersections_if_absent(
        self,
        mutation: ObjectIntersectionMaterialization,
    ) -> bool:
        scope_key = f"{mutation.object_type}\x1f{mutation.object_id}"
        return self._replace_intersection_snapshot_if_absent(
            source_event_id=mutation.source_event_id,
            source_event_digest=mutation.source_event_digest,
            subject_id=mutation.subject_id,
            scope_kind="object",
            scope_key=scope_key,
            reasons=mutation.reasons,
            generated_at=mutation.generated_at,
        )

    def _replace_intersection_snapshot_if_absent(
        self,
        *,
        source_event_id: str,
        source_event_digest: str,
        subject_id: str,
        scope_kind: str,
        scope_key: str,
        reasons: tuple[Mapping[str, Any], ...],
        generated_at: datetime,
    ) -> bool:
        receipt_id = self._intersection_receipt_id(
            source_event_id,
            scope_kind,
            f"{subject_id}\x1f{scope_key}",
        )
        if self._existing_intersection_receipt(
            receipt_id=receipt_id,
            expected_digest=source_event_digest,
        ):
            return False
        try:
            with self._profiles.database.client.start_session() as session:
                with session.start_transaction():
                    if self._existing_intersection_receipt(
                        receipt_id=receipt_id,
                        expected_digest=source_event_digest,
                        session=session,
                    ):
                        return False
                    identity = {
                        "subjectId": subject_id,
                        "scopeKind": scope_kind,
                        "scopeKey": scope_key,
                    }
                    current = self._intersection_reasons.find_one(
                        identity,
                        {"checkpoint": 1},
                        session=session,
                    ) or {}
                    checkpoint = int(current.get("checkpoint") or 0) + 1
                    self._intersection_reasons.replace_one(
                        identity,
                        {
                            **identity,
                            "reasons": [dict(reason) for reason in reasons],
                            "generatedAt": generated_at.astimezone(timezone.utc),
                            "checkpoint": checkpoint,
                            "sourceEventId": source_event_id,
                            "sourceEventDigest": source_event_digest,
                        },
                        upsert=True,
                        session=session,
                    )
                    self._intersection_inbox.insert_one(
                        {
                            "_id": receipt_id,
                            "sourceEventId": source_event_id,
                            "sourceEventDigest": source_event_digest,
                            "subjectId": subject_id,
                            "scopeKind": scope_kind,
                            "scopeKey": scope_key,
                            "projectionCheckpoint": checkpoint,
                            "appliedAt": datetime.now(timezone.utc),
                        },
                        session=session,
                    )
            return True
        except DuplicateKeyError:
            if self._existing_intersection_receipt(
                receipt_id=receipt_id,
                expected_digest=source_event_digest,
            ):
                return False
            raise

    def replace_intersection_supply_if_absent(
        self,
        mutation: IntersectionSupplyMaterialization,
    ) -> bool:
        receipt_id = self._intersection_receipt_id(
            mutation.source_event_id,
            "supply",
            mutation.supply_key,
        )
        if self._existing_intersection_receipt(
            receipt_id=receipt_id,
            expected_digest=mutation.source_event_digest,
        ):
            return False
        try:
            with self._profiles.database.client.start_session() as session:
                with session.start_transaction():
                    if self._existing_intersection_receipt(
                        receipt_id=receipt_id,
                        expected_digest=mutation.source_event_digest,
                        session=session,
                    ):
                        return False
                    current = self._intersection_supply.find_one(
                        {"supplyKey": mutation.supply_key},
                        {"checkpoint": 1},
                        session=session,
                    ) or {}
                    checkpoint = int(current.get("checkpoint") or 0) + 1
                    self._intersection_supply.replace_one(
                        {"supplyKey": mutation.supply_key},
                        {
                            "supplyKey": mutation.supply_key,
                            "distinctObjectCount": mutation.distinct_object_count,
                            "computedAt": mutation.computed_at.astimezone(timezone.utc),
                            "checkpoint": checkpoint,
                            "sourceEventId": mutation.source_event_id,
                            "sourceEventDigest": mutation.source_event_digest,
                        },
                        upsert=True,
                        session=session,
                    )
                    self._intersection_inbox.insert_one(
                        {
                            "_id": receipt_id,
                            "sourceEventId": mutation.source_event_id,
                            "sourceEventDigest": mutation.source_event_digest,
                            "scopeKind": "supply",
                            "scopeKey": mutation.supply_key,
                            "projectionCheckpoint": checkpoint,
                            "appliedAt": datetime.now(timezone.utc),
                        },
                        session=session,
                    )
            return True
        except DuplicateKeyError:
            if self._existing_intersection_receipt(
                receipt_id=receipt_id,
                expected_digest=mutation.source_event_digest,
            ):
                return False
            raise

    @staticmethod
    def _normalize_digest(value: str) -> str:
        normalized = value.strip().lower()
        if len(normalized) != 64 or any(
            character not in "0123456789abcdef" for character in normalized
        ):
            raise ValueError("intersection evidence source digest is invalid")
        return normalized

    @staticmethod
    def _replace_versioned_evidence(
        collection: Any,
        *,
        identity: str,
        version_field: str,
        version: int,
        digest: str,
        document: dict[str, Any],
        conflict_message: str,
    ) -> bool:
        for _attempt in range(8):
            current = collection.find_one({"_id": identity})
            if current is None:
                try:
                    collection.insert_one(document)
                    return True
                except DuplicateKeyError:
                    continue
            current_version = int(current.get(version_field) or 0)
            if current_version > version:
                return False
            if current_version == version:
                if str(current.get("eventDigest") or "") != digest:
                    raise RuntimeError(conflict_message)
                return False
            result = collection.replace_one(
                {
                    "_id": identity,
                    version_field: current_version,
                    "eventDigest": str(current.get("eventDigest") or ""),
                },
                document,
            )
            if result.matched_count == 1:
                return True
        raise RuntimeError("intersection evidence update did not converge")

    def apply_persona_relationship_evidence(
        self,
        *,
        event_id: str,
        event_digest: str,
        source_persona_id: str,
        target_persona_id: str,
        following: bool,
        blocked: bool,
        version: int,
        occurred_at: datetime,
    ) -> bool:
        normalized_event = event_id.strip()
        digest = self._normalize_digest(event_digest)
        source = source_persona_id.strip()
        target = target_persona_id.strip()
        if (
            not normalized_event
            or not source
            or not target
            or source == target
            or version <= 0
            or occurred_at.tzinfo is None
            or (blocked and following)
        ):
            raise ValueError("intersection persona relationship evidence is invalid")
        identity = f"{source}\x1f{target}"
        return self._replace_versioned_evidence(
            self._intersection_relationships,
            identity=identity,
            version_field="version",
            version=version,
            digest=digest,
            document={
                "_id": identity,
                "sourcePersonaId": source,
                "targetPersonaId": target,
                "following": following and not blocked,
                "blocked": blocked,
                "version": version,
                "eventId": normalized_event,
                "eventDigest": digest,
                "occurredAt": occurred_at.astimezone(timezone.utc),
            },
            conflict_message="persona relationship evidence version conflicts",
        )

    def apply_circle_membership_evidence(
        self,
        *,
        event_id: str,
        event_digest: str,
        membership_id: str,
        circle_id: str,
        persona_id: str,
        state: str,
        version: int,
        occurred_at: datetime,
    ) -> bool:
        normalized_event = event_id.strip()
        digest = self._normalize_digest(event_digest)
        membership = membership_id.strip()
        circle = circle_id.strip()
        persona = persona_id.strip()
        normalized_state = state.strip()
        if (
            not normalized_event
            or not membership
            or not circle
            or not persona
            or normalized_state not in {"pending", "active", "rejected", "left", "removed"}
            or version <= 0
            or occurred_at.tzinfo is None
        ):
            raise ValueError("intersection circle membership evidence is invalid")
        return self._replace_versioned_evidence(
            self._intersection_memberships,
            identity=membership,
            version_field="version",
            version=version,
            digest=digest,
            document={
                "_id": membership,
                "circleId": circle,
                "personaId": persona,
                "state": normalized_state,
                "active": normalized_state == "active",
                "version": version,
                "eventId": normalized_event,
                "eventDigest": digest,
                "occurredAt": occurred_at.astimezone(timezone.utc),
            },
            conflict_message="circle membership evidence version conflicts",
        )

    def apply_behavior_evidence(
        self,
        *,
        event_id: str,
        event_digest: str,
        subject_id: str,
        target_id: str,
        target_type: str,
        action: str,
        entity_refs: tuple[str, ...],
        display_name: str,
        occurred_at: datetime,
    ) -> bool:
        normalized_event = event_id.strip()
        digest = self._normalize_digest(event_digest)
        subject = subject_id.strip()
        target = target_id.strip()
        normalized_type = target_type.strip() or "post"
        normalized_action = action.strip()
        normalized_refs = tuple(
            dict.fromkeys(ref.strip() for ref in entity_refs if ref.strip())
        )
        if (
            not normalized_event
            or not subject
            or not target
            or not normalized_action
            or occurred_at.tzinfo is None
        ):
            raise ValueError("intersection behavior evidence is invalid")
        current = self._intersection_behaviors.find_one({"_id": normalized_event})
        if current is not None:
            if str(current.get("eventDigest") or "") != digest:
                raise RuntimeError("intersection behavior evidence identity conflicts")
            return False
        try:
            with self._profiles.database.client.start_session() as session:
                with session.start_transaction():
                    current = self._intersection_behaviors.find_one(
                        {"_id": normalized_event}, session=session
                    )
                    if current is not None:
                        if str(current.get("eventDigest") or "") != digest:
                            raise RuntimeError(
                                "intersection behavior evidence identity conflicts"
                            )
                        return False
                    document = {
                        "_id": normalized_event,
                        "eventDigest": digest,
                        "subjectId": subject,
                        "targetId": target,
                        "targetType": normalized_type,
                        "action": normalized_action,
                        "entityRefs": list(normalized_refs),
                        "displayName": display_name.strip(),
                        "occurredAt": occurred_at.astimezone(timezone.utc),
                    }
                    self._intersection_behaviors.insert_one(document, session=session)
                    if normalized_action in {"wishlist_add", "wishlist_remove"}:
                        for entity_id in normalized_refs:
                            identity = f"{subject}\x1f{entity_id}"
                            self._intersection_wishlist.update_one(
                                {"_id": identity},
                                {
                                    "$set": {
                                        "subjectId": subject,
                                        "entityId": entity_id,
                                        "active": normalized_action == "wishlist_add",
                                        "sourceEventId": normalized_event,
                                        "sourceEventDigest": digest,
                                        "updatedAt": occurred_at.astimezone(timezone.utc),
                                    }
                                },
                                upsert=True,
                                session=session,
                            )
        except DuplicateKeyError:
            current = self._intersection_behaviors.find_one({"_id": normalized_event})
            if current is not None and str(current.get("eventDigest") or "") == digest:
                return False
            raise
        return True

    def apply_persona_profile_evidence(
        self,
        *,
        event_id: str,
        event_digest: str,
        persona_id: str,
        display_name: str,
        avatar_url: str,
        source_version: int,
        occurred_at: datetime,
    ) -> bool:
        digest = self._normalize_digest(event_digest)
        persona = persona_id.strip()
        name = display_name.strip()
        if (
            not event_id.strip()
            or not persona
            or not name
            or source_version <= 0
            or occurred_at.tzinfo is None
        ):
            raise ValueError("intersection persona profile evidence is invalid")
        identity = event_id.strip()
        current = self._intersection_persona_profiles.find_one({"_id": identity})
        if current is not None:
            if str(current.get("eventDigest") or "") != digest:
                raise RuntimeError("intersection persona profile event conflicts")
            return False
        try:
            self._intersection_persona_profiles.insert_one(
                {
                    "_id": identity,
                    "personaId": persona,
                    "displayName": name,
                    "avatarUrl": avatar_url.strip(),
                    "sourceVersion": source_version,
                    "eventId": identity,
                    "eventDigest": digest,
                    "occurredAt": occurred_at.astimezone(timezone.utc),
                }
            )
        except DuplicateKeyError:
            current = self._intersection_persona_profiles.find_one({"_id": identity})
            if current is not None and str(current.get("eventDigest") or "") == digest:
                return False
            raise
        return True

    def apply_declared_visit_evidence(
        self,
        *,
        event_id: str,
        event_digest: str,
        post_id: str,
        persona_id: str,
        entity_id: str,
        active: bool,
        source_version: int,
        occurred_at: datetime,
    ) -> bool:
        digest = self._normalize_digest(event_digest)
        post = post_id.strip()
        persona = persona_id.strip()
        entity = entity_id.strip()
        if (
            not event_id.strip()
            or not post
            or (active and (not persona or not entity))
            or source_version <= 0
            or occurred_at.tzinfo is None
        ):
            raise ValueError("intersection declared visit evidence is invalid")
        current = self._intersection_declared_visits.find_one({"_id": post}) or {}
        if not active:
            persona = persona or str(current.get("personaId") or "")
            entity = entity or str(current.get("entityId") or "")
        return self._replace_versioned_evidence(
            self._intersection_declared_visits,
            identity=post,
            version_field="sourceVersion",
            version=source_version,
            digest=digest,
            document={
                "_id": post,
                "postId": post,
                "personaId": persona,
                "entityId": entity,
                "active": active,
                "sourceVersion": source_version,
                "eventId": event_id.strip(),
                "eventDigest": digest,
                "occurredAt": occurred_at.astimezone(timezone.utc),
            },
            conflict_message="intersection declared visit version conflicts",
        )

    def list_following(self, persona_id: str, limit: int) -> tuple[str, ...]:
        documents = self._intersection_relationships.find(
            {
                "sourcePersonaId": persona_id.strip(),
                "following": True,
                "blocked": False,
            },
            {"targetPersonaId": 1},
        ).sort("targetPersonaId", ASCENDING).limit(limit)
        return tuple(
            str(document.get("targetPersonaId") or "")
            for document in documents
            if str(document.get("targetPersonaId") or "").strip()
        )

    def list_followers(self, persona_id: str, limit: int) -> tuple[str, ...]:
        documents = self._intersection_relationships.find(
            {
                "targetPersonaId": persona_id.strip(),
                "following": True,
                "blocked": False,
            },
            {"sourcePersonaId": 1},
        ).sort("sourcePersonaId", ASCENDING).limit(limit)
        return tuple(
            str(document.get("sourcePersonaId") or "")
            for document in documents
            if str(document.get("sourcePersonaId") or "").strip()
        )

    def list_circle_ids(self, persona_id: str, limit: int) -> tuple[str, ...]:
        documents = self._intersection_memberships.find(
            {"personaId": persona_id.strip(), "active": True},
            {"circleId": 1},
        ).sort("circleId", ASCENDING).limit(limit)
        return tuple(
            str(document.get("circleId") or "")
            for document in documents
            if str(document.get("circleId") or "").strip()
        )

    def list_behaviors(self, persona_id: str, limit: int) -> tuple[BehaviorSnapshot, ...]:
        documents = self._intersection_behaviors.find(
            {"subjectId": persona_id.strip()},
        ).sort([("occurredAt", DESCENDING), ("_id", DESCENDING)]).limit(limit)
        return tuple(
            BehaviorSnapshot(
                subject_id=str(document.get("subjectId") or ""),
                target_id=str(document.get("targetId") or ""),
                target_type=str(document.get("targetType") or ""),
                action=str(document.get("action") or ""),
                entity_refs=tuple(
                    str(value)
                    for value in document.get("entityRefs") or []
                    if str(value).strip()
                ),
                display_name=str(document.get("displayName") or ""),
                occurred_at=self._utc_datetime(document.get("occurredAt")),
            )
            for document in documents
        )

    def read_persona_profile(self, persona_id: str) -> PersonaProfileSnapshot | None:
        document = self._intersection_persona_profiles.find_one(
            {"personaId": persona_id.strip()},
            sort=[("occurredAt", DESCENDING), ("_id", DESCENDING)],
        )
        if document is None:
            return None
        return PersonaProfileSnapshot(
            persona_id=str(document.get("personaId") or ""),
            display_name=str(document.get("displayName") or ""),
            avatar_url=str(document.get("avatarUrl") or ""),
        )

    def count_intersection_supply(self, supply_key: str) -> int:
        normalized = supply_key.strip()
        if normalized == "entity_page_view":
            values = self._intersection_behaviors.distinct(
                "entityRefs", {"action": "entity_page_view"}
            )
        elif normalized == "entity_wishlist":
            values = self._intersection_wishlist.distinct("entityId", {"active": True})
        elif normalized == "circle_membership":
            values = self._intersection_memberships.distinct("circleId", {"active": True})
        elif normalized == "post_declared_visit":
            values = self._intersection_declared_visits.distinct(
                "entityId", {"active": True}
            )
        else:
            raise ValueError("intersection supply key is not canonical")
        return len({str(value).strip() for value in values if str(value).strip()})

    @staticmethod
    def _intersection_evidence_digest(payload: Mapping[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
                default=lambda value: (
                    value.astimezone(timezone.utc).isoformat()
                    if isinstance(value, datetime)
                    else str(value)
                ),
            ).encode("utf-8")
        ).hexdigest()

    def subject_intersection_evidence_digest(self, subject_id: str) -> str:
        subject = subject_id.strip()
        following = self.list_following(subject, 200)
        actors: list[dict[str, Any]] = []
        for actor_id in following:
            profile = self.read_persona_profile(actor_id)
            actors.append(
                {
                    "actorId": actor_id,
                    "profile": (
                        {
                            "displayName": profile.display_name,
                            "avatarUrl": profile.avatar_url,
                        }
                        if profile is not None
                        else None
                    ),
                    "behaviors": [
                        {
                            "targetId": behavior.target_id,
                            "targetType": behavior.target_type,
                            "action": behavior.action,
                            "entityRefs": behavior.entity_refs,
                            "displayName": behavior.display_name,
                            "occurredAt": behavior.occurred_at,
                        }
                        for behavior in self.list_behaviors(actor_id, 3)
                    ],
                }
            )
        return self._intersection_evidence_digest(
            {"subjectId": subject, "followingActors": actors}
        )

    def object_intersection_evidence_digest(
        self,
        subject_id: str,
        object_type: str,
        object_id: str,
    ) -> str:
        subject = subject_id.strip()
        normalized_type = object_type.strip()
        normalized_object = object_id.strip()
        following = self.list_following(subject, 200)
        actor_evidence = [
            {
                "actorId": actor_id,
                "circleIds": self.list_circle_ids(actor_id, 200),
                "behaviors": [
                    {
                        "targetId": behavior.target_id,
                        "targetType": behavior.target_type,
                        "action": behavior.action,
                        "entityRefs": behavior.entity_refs,
                        "occurredAt": behavior.occurred_at,
                    }
                    for behavior in self.list_behaviors(actor_id, 200)
                ],
                "profile": (
                    {
                        "displayName": profile.display_name,
                        "avatarUrl": profile.avatar_url,
                    }
                    if (profile := self.read_persona_profile(actor_id)) is not None
                    else None
                ),
            }
            for actor_id in following
        ]
        target_evidence: dict[str, Any] = {}
        if normalized_type in {"user", "persona", "person"}:
            target_evidence = {
                "following": self.list_following(normalized_object, 200),
                "circleIds": self.list_circle_ids(normalized_object, 200),
            }
        return self._intersection_evidence_digest(
            {
                "subjectId": subject,
                "objectType": normalized_type,
                "objectId": normalized_object,
                "subjectCircleIds": self.list_circle_ids(subject, 200),
                "actors": actor_evidence,
                "target": target_evidence,
            }
        )

    def intersection_supply_evidence_digest(self) -> str:
        return self._intersection_evidence_digest(
            {
                supply_key: self.count_intersection_supply(supply_key)
                for supply_key in (
                    "entity_page_view",
                    "entity_wishlist",
                    "circle_membership",
                    "post_declared_visit",
                )
            }
        )

    def list_intersection_rebuild_subject_ids(self) -> tuple[str, ...]:
        subjects: set[str] = set()
        for field in ("sourcePersonaId", "targetPersonaId"):
            subjects.update(
                str(value).strip()
                for value in self._intersection_relationships.distinct(field)
                if str(value).strip()
            )
        for collection, field in (
            (self._intersection_memberships, "personaId"),
            (self._intersection_behaviors, "subjectId"),
            (self._intersection_wishlist, "subjectId"),
            (self._intersection_declared_visits, "personaId"),
        ):
            subjects.update(
                str(value).strip()
                for value in collection.distinct(field)
                if str(value).strip()
            )
        return tuple(sorted(subjects))

    def list_subject_projection_inventory(
        self,
        subject_ids: tuple[str, ...],
    ) -> tuple[IntersectionProjectionInventory, ...]:
        if not subject_ids:
            return ()
        documents = self._intersection_reasons.find(
            {
                "subjectId": {"$in": list(subject_ids)},
                "scopeKind": "subject",
            },
            {
                "subjectId": 1,
                "scopeKey": 1,
                "sourceEventDigest": 1,
                "checkpoint": 1,
            },
        )
        inventory: list[IntersectionProjectionInventory] = []
        for document in documents:
            scope_parts = str(document.get("scopeKey") or "").split("\x1f", 1)
            if len(scope_parts) != 2:
                raise RuntimeError("intersection subject projection scope is invalid")
            inventory.append(
                IntersectionProjectionInventory(
                    subject_id=str(document.get("subjectId") or ""),
                    intersection_class=scope_parts[0],
                    channel=scope_parts[1],
                    source_event_digest=str(document.get("sourceEventDigest") or ""),
                    checkpoint=int(document.get("checkpoint") or 0),
                )
            )
        return tuple(inventory)

    def list_supply_projection_inventory(
        self,
    ) -> tuple[IntersectionSupplyInventory, ...]:
        return tuple(
            IntersectionSupplyInventory(
                supply_key=str(document.get("supplyKey") or ""),
                source_event_digest=str(document.get("sourceEventDigest") or ""),
                checkpoint=int(document.get("checkpoint") or 0),
            )
            for document in self._intersection_supply.find(
                {},
                {"supplyKey": 1, "sourceEventDigest": 1, "checkpoint": 1},
            )
        )

    def read_author_impact(self, author_id: str, limit: int) -> AuthorImpactSummary:
        normalized = author_id.strip()
        if not normalized or limit < 1 or limit > 50:
            raise ValueError("author impact query is invalid")
        documents = list(
            self._author_impact.find({"authorId": normalized})
            .sort([("count", DESCENDING), ("updatedAt", DESCENDING), ("_id", ASCENDING)])
            .limit(limit)
        )
        total_rows = list(
            self._author_impact.aggregate(
                [
                    {"$match": {"authorId": normalized}},
                    {"$group": {"_id": None, "total": {"$sum": "$count"}}},
                ]
            )
        )
        total = int(total_rows[0].get("total") or 0) if total_rows else 0
        return AuthorImpactSummary(
            author_id=normalized,
            total=total,
            items=tuple(
                AuthorImpactItem(
                    impact_id=str(document.get("impactId") or ""),
                    help_type=str(document.get("helpType") or ""),
                    action=str(document.get("action") or ""),
                    intersection_dimension=str(
                        document.get("intersectionDimension") or ""
                    ),
                    tag_ref=str(document.get("tagRef") or ""),
                    source=str(document.get("source") or ""),
                    count=int(document.get("count") or 0),
                    updated_at=self._utc_datetime(document.get("updatedAt")),
                    representative_content_id=str(
                        document.get("representativeContentId") or ""
                    ),
                )
                for document in documents
            ),
        )

    def read_author_impact_evidence(
        self,
        author_id: str,
        impact_id: str,
        cursor: str | None,
        limit: int,
    ) -> AuthorImpactEvidencePage:
        normalized_author = author_id.strip()
        normalized_impact = impact_id.strip()
        if not normalized_author or not normalized_impact or limit < 1 or limit > 50:
            raise ValueError("author impact evidence query is invalid")
        query: dict[str, Any] = {
            "authorId": normalized_author,
            "impactId": normalized_impact,
        }
        if cursor:
            occurred_at, evidence_id = self._decode_impact_cursor(cursor)
            query["$or"] = [
                {"occurredAt": {"$lt": occurred_at}},
                {"occurredAt": occurred_at, "_id": {"$lt": evidence_id}},
            ]
        documents = list(
            self._author_impact_evidence.find(query)
            .sort([("occurredAt", DESCENDING), ("_id", DESCENDING)])
            .limit(limit + 1)
        )
        has_more = len(documents) > limit
        page_documents = documents[:limit]
        next_cursor = None
        if has_more and page_documents:
            tail = page_documents[-1]
            next_cursor = self._encode_impact_cursor(
                self._utc_datetime(tail.get("occurredAt")),
                str(tail.get("_id") or ""),
            )
        total = self._author_impact_evidence.count_documents(
            {"authorId": normalized_author, "impactId": normalized_impact}
        )
        return AuthorImpactEvidencePage(
            impact_id=normalized_impact,
            total_count=int(total),
            items=tuple(
                AuthorImpactEvidence(
                    evidence_id=str(document.get("_id") or ""),
                    impact_id=str(document.get("impactId") or ""),
                    content_id=str(document.get("contentId") or ""),
                    content_type=str(document.get("contentType") or ""),
                    help_type=str(document.get("helpType") or ""),
                    action=str(document.get("action") or ""),
                    intersection_dimension=str(
                        document.get("intersectionDimension") or ""
                    ),
                    occurred_at=self._utc_datetime(document.get("occurredAt")),
                )
                for document in page_documents
            ),
            next_cursor=next_cursor,
            has_more=has_more,
        )

    @staticmethod
    def _utc_datetime(value: Any) -> datetime:
        if not isinstance(value, datetime):
            raise ValueError("author impact projection timestamp is invalid")
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _encode_impact_cursor(occurred_at: datetime, evidence_id: str) -> str:
        payload = json.dumps(
            {
                "occurredAt": occurred_at.astimezone(timezone.utc).isoformat(),
                "evidenceId": evidence_id,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_impact_cursor(cursor: str) -> tuple[datetime, str]:
        try:
            padded = cursor + "=" * (-len(cursor) % 4)
            raw = base64.urlsafe_b64decode(padded.encode("ascii"))
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict) or set(payload) != {
                "occurredAt",
                "evidenceId",
            }:
                raise ValueError
            occurred_at = datetime.fromisoformat(str(payload["occurredAt"]))
            if occurred_at.tzinfo is None:
                raise ValueError
            evidence_id = str(payload["evidenceId"]).strip()
            if not evidence_id:
                raise ValueError
            return occurred_at.astimezone(timezone.utc), evidence_id
        except Exception as error:
            raise ValueError("author impact cursor is invalid") from error

    @staticmethod
    def _merge_features(
        current: Any,
        increments: Any,
        *,
        maximum: int,
    ) -> dict[str, float]:
        merged: dict[str, float] = {}
        for key, value in dict(current or {}).items():
            numeric = float(value)
            if str(key).strip() and math.isfinite(numeric):
                merged[str(key)] = numeric
        for key, value in dict(increments or {}).items():
            numeric = float(value)
            if not str(key).strip() or not math.isfinite(numeric):
                raise ValueError("feature mutation contains an invalid value")
            merged[str(key)] = merged.get(str(key), 0.0) + numeric
        return dict(
            sorted(
                merged.items(),
                key=lambda item: (-abs(item[1]), item[0]),
            )[:maximum]
        )

    def _next_profile(
        self,
        *,
        current: dict[str, Any] | None,
        subject_id: str,
        mutation: BehaviorFeatureMutation,
        influence_delta: float = 0.0,
        sparse_increments: dict[str, float] | None = None,
        include_viewer_features: bool = True,
    ) -> dict[str, Any]:
        source = dict(current or {})
        collaborative_increments = (
            {mutation.target_id: mutation.collaborative_signal}
            if include_viewer_features and mutation.collaborative_signal != 0
            else {}
        )
        negative_content_ids = list(source.get("negativeContentIds") or [])
        hidden_author_ids = list(source.get("hiddenAuthorIds") or [])
        hidden_content_types = list(source.get("hiddenContentTypes") or [])
        if mutation.action in {"dislike", "report"}:
            negative_content_ids = self._append_hard_exclusion(
                negative_content_ids,
                mutation.target_id,
            )
        elif mutation.action == "hide_author" and mutation.author_id:
            hidden_author_ids = self._append_hard_exclusion(
                hidden_author_ids,
                mutation.author_id,
            )
        elif mutation.action == "hide_content_type" and mutation.content_type:
            hidden_content_types = self._append_hard_exclusion(
                hidden_content_types,
                mutation.content_type,
            )
        return {
            "_id": subject_id,
            "subjectId": subject_id,
            "lastFeedbackFactId": mutation.feedback_fact_id,
            "lastExposureFactId": mutation.exposure_fact_id,
            "lastTagFeedbackFactId": source.get("lastTagFeedbackFactId"),
            "sparseFeatures": self._merge_features(
                source.get("sparseFeatures"),
                sparse_increments if sparse_increments is not None else mutation.sparse_increments,
                maximum=MAX_PROFILE_FEATURE_KEYS,
            ),
            "tagAffinities": dict(source.get("tagAffinities") or {}),
            "influenceScore": float(source.get("influenceScore") or 0.0) + influence_delta,
            "collaborativeFeatures": self._merge_features(
                source.get("collaborativeFeatures"),
                collaborative_increments,
                maximum=MAX_COLLABORATIVE_NEIGHBORS,
            ),
            "intersectionFeatures": self._merge_features(
                source.get("intersectionFeatures"),
                mutation.intersection_increments if include_viewer_features else {},
                maximum=MAX_PROFILE_FEATURE_KEYS,
            ),
            "negativeContentIds": negative_content_ids,
            "hiddenAuthorIds": hidden_author_ids,
            "hiddenContentTypes": hidden_content_types,
            "checkpoint": int(source.get("checkpoint") or 0) + 1,
            "updatedAt": mutation.occurred_at.astimezone(timezone.utc),
        }

    @staticmethod
    def _append_hard_exclusion(values: list[Any], value: str) -> list[str]:
        normalized = value.strip()
        current = [str(item).strip() for item in values if str(item).strip()]
        current = [item for item in current if item != normalized]
        current.append(normalized)
        return current[-MAX_HARD_EXCLUSIONS:]

    def apply_behavior_if_absent(self, mutation: BehaviorFeatureMutation) -> bool:
        receipt_id = f"{mutation.event_id}\x1f{mutation.subject_id}"
        if self._checkpoints.find_one({"_id": receipt_id}, {"_id": 1}) is not None:
            return False
        try:
            with self._profiles.database.client.start_session() as session:
                with session.start_transaction():
                    if self._checkpoints.find_one(
                        {"_id": receipt_id},
                        {"_id": 1},
                        session=session,
                    ) is not None:
                        return False
                    current = self._profiles.find_one(
                        {"_id": mutation.subject_id},
                        session=session,
                    )
                    profile = self._next_profile(
                        current=current,
                        subject_id=mutation.subject_id,
                        mutation=mutation,
                    )
                    self._profiles.replace_one(
                        {"_id": mutation.subject_id},
                        profile,
                        upsert=True,
                        session=session,
                    )
                    self._apply_collaborative(mutation, session=session)
                    self._apply_intersection(mutation, session=session)
                    self._apply_author_impact(mutation, session=session)
                    self._checkpoints.insert_one(
                        {
                            "_id": receipt_id,
                            "eventId": mutation.event_id,
                            "subjectId": mutation.subject_id,
                            "sourceSequence": mutation.source_sequence,
                            "profileCheckpoint": profile["checkpoint"],
                            "appliedAt": datetime.now(timezone.utc),
                        },
                        session=session,
                    )
            return True
        except DuplicateKeyError:
            if self._checkpoints.find_one({"_id": receipt_id}, {"_id": 1}) is not None:
                return False
            raise

    def apply_exposure_if_absent(self, mutation: ExposureFeatureMutation) -> bool:
        receipt_id = f"{mutation.exposure_fact_id}\x1f{mutation.subject_id}"
        if self._checkpoints.find_one({"_id": receipt_id}, {"_id": 1}) is not None:
            return False
        try:
            with self._profiles.database.client.start_session() as session:
                with session.start_transaction():
                    if self._checkpoints.find_one(
                        {"_id": receipt_id},
                        {"_id": 1},
                        session=session,
                    ) is not None:
                        return False
                    current = self._profiles.find_one(
                        {"_id": mutation.subject_id},
                        session=session,
                    ) or {}
                    profile = {
                        "_id": mutation.subject_id,
                        "subjectId": mutation.subject_id,
                        "lastFeedbackFactId": current.get("lastFeedbackFactId"),
                        "lastExposureFactId": mutation.exposure_fact_id,
                        "lastTagFeedbackFactId": current.get("lastTagFeedbackFactId"),
                        "sparseFeatures": self._merge_features(
                            current.get("sparseFeatures"),
                            {"deliveryCount": 1.0},
                            maximum=MAX_PROFILE_FEATURE_KEYS,
                        ),
                        "tagAffinities": dict(current.get("tagAffinities") or {}),
                        "influenceScore": float(current.get("influenceScore") or 0.0),
                        "collaborativeFeatures": dict(
                            current.get("collaborativeFeatures") or {}
                        ),
                        "intersectionFeatures": dict(
                            current.get("intersectionFeatures") or {}
                        ),
                        "negativeContentIds": list(
                            current.get("negativeContentIds") or []
                        ),
                        "hiddenAuthorIds": list(current.get("hiddenAuthorIds") or []),
                        "hiddenContentTypes": list(
                            current.get("hiddenContentTypes") or []
                        ),
                        "checkpoint": int(current.get("checkpoint") or 0) + 1,
                        "updatedAt": mutation.occurred_at.astimezone(timezone.utc),
                    }
                    self._profiles.replace_one(
                        {"_id": mutation.subject_id},
                        profile,
                        upsert=True,
                        session=session,
                    )
                    self._checkpoints.insert_one(
                        {
                            "_id": receipt_id,
                            "eventId": mutation.exposure_fact_id,
                            "subjectId": mutation.subject_id,
                            "targetId": mutation.target_id,
                            "profileCheckpoint": profile["checkpoint"],
                            "appliedAt": datetime.now(timezone.utc),
                        },
                        session=session,
                    )
            return True
        except DuplicateKeyError:
            if self._checkpoints.find_one({"_id": receipt_id}, {"_id": 1}) is not None:
                return False
            raise

    def apply_tag_feedback_if_absent(self, mutation: TagFeedbackMutation) -> bool:
        receipt_id = f"{mutation.event_id}\x1f{mutation.subject_id}"
        if self._checkpoints.find_one({"_id": receipt_id}, {"_id": 1}) is not None:
            return False
        try:
            with self._profiles.database.client.start_session() as session:
                with session.start_transaction():
                    if self._checkpoints.find_one(
                        {"_id": receipt_id},
                        {"_id": 1},
                        session=session,
                    ) is not None:
                        return False
                    current = self._profiles.find_one(
                        {"_id": mutation.subject_id},
                        session=session,
                    ) or {}
                    tag_affinities = dict(current.get("tagAffinities") or {})
                    if mutation.action == "click":
                        tag_affinities[mutation.tag_ref] = 1.0
                    elif mutation.action == "dislike":
                        tag_affinities[mutation.tag_ref] = -1.0
                    elif mutation.action == "ignore":
                        tag_affinities.pop(mutation.tag_ref, None)
                    elif mutation.action != "correct":
                        raise ValueError("unsupported tag feedback action")
                    profile = {
                        "_id": mutation.subject_id,
                        "subjectId": mutation.subject_id,
                        "lastFeedbackFactId": current.get("lastFeedbackFactId"),
                        "lastExposureFactId": current.get("lastExposureFactId"),
                        "lastTagFeedbackFactId": mutation.event_id,
                        "sparseFeatures": dict(current.get("sparseFeatures") or {}),
                        "tagAffinities": tag_affinities,
                        "influenceScore": float(current.get("influenceScore") or 0.0),
                        "collaborativeFeatures": dict(
                            current.get("collaborativeFeatures") or {}
                        ),
                        "intersectionFeatures": dict(
                            current.get("intersectionFeatures") or {}
                        ),
                        "negativeContentIds": list(
                            current.get("negativeContentIds") or []
                        ),
                        "hiddenAuthorIds": list(current.get("hiddenAuthorIds") or []),
                        "hiddenContentTypes": list(
                            current.get("hiddenContentTypes") or []
                        ),
                        "checkpoint": int(current.get("checkpoint") or 0) + 1,
                        "updatedAt": mutation.recorded_at.astimezone(timezone.utc),
                    }
                    self._profiles.replace_one(
                        {"_id": mutation.subject_id},
                        profile,
                        upsert=True,
                        session=session,
                    )
                    self._checkpoints.insert_one(
                        {
                            "_id": receipt_id,
                            "eventId": mutation.event_id,
                            "subjectId": mutation.subject_id,
                            "sourceType": "TagFeedbackRecorded",
                            "actorKind": mutation.actor_kind,
                            "tagRef": mutation.tag_ref,
                            "action": mutation.action,
                            "profileCheckpoint": profile["checkpoint"],
                            "appliedAt": datetime.now(timezone.utc),
                        },
                        session=session,
                    )
            return True
        except DuplicateKeyError:
            if self._checkpoints.find_one({"_id": receipt_id}, {"_id": 1}) is not None:
                return False
            raise

    def _apply_collaborative(self, mutation: BehaviorFeatureMutation, *, session: Any) -> None:
        if mutation.collaborative_signal == 0:
            return
        pair_id = f"{mutation.subject_id}\x1f{mutation.target_id}"
        previous = list(
            self._collaborative_u2i.find(
                {
                    "subjectId": mutation.subject_id,
                    "contentId": {"$ne": mutation.target_id},
                    "score": {"$gt": 0},
                },
                {"contentId": 1},
                session=session,
            )
            .sort([("updatedAt", DESCENDING), ("contentId", ASCENDING)])
            .limit(20)
        )
        self._collaborative_u2i.update_one(
            {"_id": pair_id},
            {
                "$set": {
                    "subjectId": mutation.subject_id,
                    "contentId": mutation.target_id,
                    "lastEventId": mutation.event_id,
                    "updatedAt": mutation.occurred_at.astimezone(timezone.utc),
                },
                "$inc": {
                    "score": mutation.collaborative_signal,
                    "positiveCount": 1 if mutation.collaborative_signal > 0 else 0,
                    "negativeCount": 1 if mutation.collaborative_signal < 0 else 0,
                },
            },
            upsert=True,
            session=session,
        )
        if mutation.collaborative_signal <= 0:
            return
        for document in previous:
            other_id = str(document.get("contentId") or "").strip()
            if not other_id:
                continue
            left, right = sorted((mutation.target_id, other_id))
            self._collaborative_i2i.update_one(
                {"_id": f"{left}\x1f{right}"},
                {
                    "$set": {
                        "leftContentId": left,
                        "rightContentId": right,
                        "updatedAt": mutation.occurred_at.astimezone(timezone.utc),
                    },
                    "$inc": {"cooccurrenceCount": 1},
                },
                upsert=True,
                session=session,
            )

    def _apply_intersection(self, mutation: BehaviorFeatureMutation, *, session: Any) -> None:
        for feature, increment in mutation.intersection_increments.items():
            self._intersection_features.update_one(
                {"_id": f"{mutation.subject_id}\x1f{feature}"},
                {
                    "$set": {
                        "subjectId": mutation.subject_id,
                        "feature": feature,
                        "lastEventId": mutation.event_id,
                        "updatedAt": mutation.occurred_at.astimezone(timezone.utc),
                    },
                    "$inc": {"value": float(increment)},
                },
                upsert=True,
                session=session,
            )

    def _apply_author_impact(self, mutation: BehaviorFeatureMutation, *, session: Any) -> None:
        author_id = (mutation.author_id or "").strip()
        help_type = (mutation.impact_help_type or "").strip()
        if not author_id or author_id == mutation.subject_id or not help_type:
            return
        tag_refs = mutation.intersection_tag_refs or ("",)
        occurred_at = mutation.occurred_at.astimezone(timezone.utc)
        for tag_ref in tag_refs:
            source = "behavior"
            impact_id = self._stable_impact_id(
                author_id=author_id,
                help_type=help_type,
                action=mutation.action,
                dimension=(mutation.intersection_dimension or ""),
                tag_ref=tag_ref,
                source=source,
            )
            evidence_id = f"{mutation.event_id}\x1f{author_id}\x1f{tag_ref}"
            self._author_impact_evidence.insert_one(
                {
                    "_id": evidence_id,
                    "eventId": mutation.event_id,
                    "impactId": impact_id,
                    "authorId": author_id,
                    "contentId": mutation.target_id,
                    "contentType": mutation.content_type or "",
                    "helpType": help_type,
                    "action": mutation.action,
                    "intersectionDimension": mutation.intersection_dimension or "",
                    "tagRef": tag_ref,
                    "source": source,
                    "occurredAt": occurred_at,
                },
                session=session,
            )
            self._author_impact.update_one(
                {"_id": f"{author_id}\x1f{impact_id}"},
                {
                    "$setOnInsert": {
                        "authorId": author_id,
                        "impactId": impact_id,
                        "helpType": help_type,
                        "action": mutation.action,
                        "intersectionDimension": mutation.intersection_dimension or "",
                        "tagRef": tag_ref,
                        "source": source,
                        "createdAt": occurred_at,
                    },
                    "$set": {
                        "representativeContentId": mutation.target_id,
                        "updatedAt": occurred_at,
                    },
                    "$inc": {"count": 1},
                },
                upsert=True,
                session=session,
            )
        author_current = self._profiles.find_one({"_id": author_id}, session=session)
        author_profile = self._next_profile(
            current=author_current,
            subject_id=author_id,
            mutation=mutation,
            influence_delta=mutation.collaborative_signal,
            sparse_increments={},
            include_viewer_features=False,
        )
        self._profiles.replace_one(
            {"_id": author_id},
            author_profile,
            upsert=True,
            session=session,
        )

    @staticmethod
    def _stable_impact_id(
        *,
        author_id: str,
        help_type: str,
        action: str,
        dimension: str,
        tag_ref: str,
        source: str,
    ) -> str:
        raw = "|".join(
            value.strip()
            for value in (author_id, help_type, action, dimension, tag_ref, source)
        )
        return hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()[:20]

    def erase_subject(self, subject_id: str) -> int:
        normalized = subject_id.strip()
        if not normalized:
            raise ValueError("subjectId is required")
        selectors = (
            (self._profiles, {"$or": [{"_id": normalized}, {"subjectId": normalized}, {"userId": normalized}]}),
            (self._author_impact, {"authorId": normalized}),
            (
                self._author_impact_evidence,
                {"$or": [{"authorId": normalized}, {"subjectId": normalized}, {"userId": normalized}]},
            ),
            (
                self._collaborative_i2i,
                {"$or": [{"subjectId": normalized}, {"userId": normalized}, {"authorId": normalized}]},
            ),
            (
                self._collaborative_u2i,
                {"$or": [{"subjectId": normalized}, {"userId": normalized}]},
            ),
            (
                self._intersection_features,
                {"$or": [{"subjectId": normalized}, {"userId": normalized}, {"personaId": normalized}]},
            ),
            (self._intersection_reasons, {"subjectId": normalized}),
            (self._intersection_inbox, {"subjectId": normalized}),
            (
                self._intersection_relationships,
                {"$or": [{"sourcePersonaId": normalized}, {"targetPersonaId": normalized}]},
            ),
            (self._intersection_memberships, {"personaId": normalized}),
            (self._intersection_behaviors, {"subjectId": normalized}),
            (self._intersection_wishlist, {"subjectId": normalized}),
            (self._intersection_persona_profiles, {"personaId": normalized}),
            (self._intersection_declared_visits, {"personaId": normalized}),
            (self._checkpoints, {"subjectId": normalized}),
            (self._failures, {"subjectId": normalized}),
        )
        deleted = 0
        for collection, selector in selectors:
            deleted += int(collection.delete_many(selector).deleted_count)
        return deleted
