"""交集投影与证据写入面：幂等收据、快照替换与八类交集证据的版本化写入。

本模块是 ``MongoFeatureProfileStore`` 的写入 mixin，实例属性
（``_profiles`` / ``_intersection_*`` 等集合句柄）由组合类的 ``__init__`` 提供。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from pymongo.errors import DuplicateKeyError

from ..application.intersection_projector import (
    IntersectionSupplyMaterialization,
    ObjectIntersectionMaterialization,
    SubjectIntersectionMaterialization,
)


class MongoIntersectionWriteOps:
    """交集投影快照与证据写入操作（``MongoFeatureProfileStore`` 的一部分）。"""

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

    def apply_gathering_participation_evidence(
        self,
        *,
        event_id: str,
        event_digest: str,
        gathering_id: str,
        persona_id: str,
        state: str,
        version: int,
        occurred_at: datetime,
    ) -> bool:
        normalized_event = event_id.strip()
        digest = self._normalize_digest(event_digest)
        gathering = gathering_id.strip()
        persona = persona_id.strip()
        normalized_state = state.strip()
        if (
            not normalized_event
            or not gathering
            or not persona
            or normalized_state
            not in {"invited_pending", "application_pending", "active", "closed"}
            or version <= 0
            or occurred_at.tzinfo is None
        ):
            raise ValueError("intersection gathering participation evidence is invalid")
        identity = f"{gathering}\x1f{persona}"
        return self._replace_versioned_evidence(
            self._intersection_gathering_participations,
            identity=identity,
            version_field="version",
            version=version,
            digest=digest,
            document={
                "_id": identity,
                "gatheringId": gathering,
                "personaId": persona,
                "state": normalized_state,
                "active": normalized_state == "active",
                "version": version,
                "eventId": normalized_event,
                "eventDigest": digest,
                "occurredAt": occurred_at.astimezone(timezone.utc),
            },
            conflict_message="gathering participation evidence version conflicts",
        )

    def apply_gathering_recap_evidence(
        self,
        *,
        event_id: str,
        event_digest: str,
        post_id: str,
        persona_id: str,
        gathering_id: str,
        active: bool,
        source_version: int,
        occurred_at: datetime,
    ) -> bool:
        digest = self._normalize_digest(event_digest)
        post = post_id.strip()
        persona = persona_id.strip()
        gathering = gathering_id.strip()
        if (
            not event_id.strip()
            or not post
            or (active and (not persona or not gathering))
            or source_version <= 0
            or occurred_at.tzinfo is None
        ):
            raise ValueError("intersection gathering recap evidence is invalid")
        current = self._intersection_gathering_recaps.find_one({"_id": post}) or {}
        if not active:
            persona = persona or str(current.get("personaId") or "")
            gathering = gathering or str(current.get("gatheringId") or "")
        return self._replace_versioned_evidence(
            self._intersection_gathering_recaps,
            identity=post,
            version_field="sourceVersion",
            version=source_version,
            digest=digest,
            document={
                "_id": post,
                "postId": post,
                "personaId": persona,
                "gatheringId": gathering,
                "active": active,
                "sourceVersion": source_version,
                "eventId": event_id.strip(),
                "eventDigest": digest,
                "occurredAt": occurred_at.astimezone(timezone.utc),
            },
            conflict_message="intersection gathering recap version conflicts",
        )

    def apply_gathering_publication_evidence(
        self,
        *,
        event_id: str,
        event_digest: str,
        gathering_id: str,
        organizer_id: str,
        source_refs: tuple[tuple[str, str], ...],
        version: int,
        occurred_at: datetime,
        max_participants: int = 0,
        admission_policy: str = "",
    ) -> bool:
        normalized_event = event_id.strip()
        digest = self._normalize_digest(event_digest)
        gathering = gathering_id.strip()
        organizer = organizer_id.strip()
        if (
            not normalized_event
            or not gathering
            or not organizer
            or version <= 0
            or occurred_at.tzinfo is None
        ):
            raise ValueError("intersection gathering publication evidence is invalid")
        refs = [
            {"objectKind": kind.strip(), "objectId": object_id.strip()}
            for kind, object_id in source_refs
            if kind.strip() and object_id.strip()
        ]
        return self._replace_versioned_evidence(
            self._intersection_gathering_publications,
            identity=gathering,
            version_field="version",
            version=version,
            digest=digest,
            document={
                "_id": gathering,
                "gatheringId": gathering,
                "organizerId": organizer,
                "sourceRefs": refs,
                # 发布时冻结的公开政策维度事实；旧事件缺失为 0/空（unclassified）。
                "maxParticipants": max(int(max_participants), 0),
                "admissionPolicy": admission_policy.strip(),
                "version": version,
                "eventId": normalized_event,
                "eventDigest": digest,
                "occurredAt": occurred_at.astimezone(timezone.utc),
            },
            conflict_message="gathering publication evidence version conflicts",
        )

    def apply_post_author_evidence(
        self,
        *,
        event_id: str,
        event_digest: str,
        post_id: str,
        author_id: str,
        active: bool,
        source_version: int,
        occurred_at: datetime,
        tag_refs: tuple[str, ...] = (),
    ) -> bool:
        digest = self._normalize_digest(event_digest)
        post = post_id.strip()
        author = author_id.strip()
        if (
            not event_id.strip()
            or not post
            or not author
            or source_version <= 0
            or occurred_at.tzinfo is None
        ):
            raise ValueError("intersection post author evidence is invalid")
        return self._replace_versioned_evidence(
            self._intersection_post_authors,
            identity=post,
            version_field="sourceVersion",
            version=source_version,
            digest=digest,
            document={
                "_id": post,
                "postId": post,
                "authorId": author,
                "active": active,
                # 内容标签（发布确认页真实采集）：漏斗类目镜头维度源。
                "tagRefs": [tag.strip() for tag in tag_refs if tag.strip()],
                "sourceVersion": source_version,
                "eventId": event_id.strip(),
                "eventDigest": digest,
                "occurredAt": occurred_at.astimezone(timezone.utc),
            },
            conflict_message="intersection post author version conflicts",
        )

    def claim_experienced_facilitation(
        self,
        *,
        gathering_id: str,
        occurred_at: datetime,
    ) -> dict[str, Any] | None:
        """经历级首次达成 + 溯源链完整时原子占位创作者促成事实。

        诚实口径：
        - 溯源链断（publication 无 content sourceRef）不占位、不通知；
        - 未达成经历级（<2 名 active 参与者各自持有 active 公开回顾）不占位；
        - 同一 Gathering 只占位一次（``recommendation_intersection_facilitations``
          收据是幂等真相源），重复达成信号返回 None。
        返回 ``{"organizerId", "creators": [(seedPostId, authorId), ...]}``。
        """
        gathering = gathering_id.strip()
        if not gathering or occurred_at.tzinfo is None:
            return None
        publication = self._intersection_gathering_publications.find_one(
            {"_id": gathering},
            {"organizerId": 1, "sourceRefs": 1},
        )
        if publication is None:
            return None
        seed_posts = [
            str(ref.get("objectId") or "").strip()
            for ref in publication.get("sourceRefs") or []
            if str(ref.get("objectKind") or "").strip() == "content"
            and str(ref.get("objectId") or "").strip()
        ]
        if not seed_posts:
            return None
        participants = {
            str(document.get("personaId") or "")
            for document in self._intersection_gathering_participations.find(
                {"gatheringId": gathering, "active": True},
                {"personaId": 1},
            )
        }
        participants.discard("")
        if len(participants) < 2:
            return None
        recap_authors = {
            str(document.get("personaId") or "")
            for document in self._intersection_gathering_recaps.find(
                {"gatheringId": gathering, "active": True},
                {"personaId": 1},
            )
        }
        if len(recap_authors.intersection(participants)) < 2:
            return None
        creators: list[tuple[str, str]] = []
        for post_id in seed_posts:
            author = self._intersection_post_authors.find_one(
                {"_id": post_id, "active": True},
                {"authorId": 1},
            )
            author_id = str((author or {}).get("authorId") or "").strip()
            if author_id:
                creators.append((post_id, author_id))
        claim = self._intersection_facilitations.update_one(
            {"_id": gathering},
            {
                "$setOnInsert": {
                    "_id": gathering,
                    "notifiedAt": occurred_at.astimezone(timezone.utc),
                    # 促成时刻冻结的创作者名单（漏斗比例③的分母事实）；
                    # 旧收据缺该字段归 unclassified，不回填臆造。
                    "creatorPersonaIds": sorted(
                        {author_id for _, author_id in creators}
                    ),
                }
            },
            upsert=True,
        )
        if claim.upserted_id is None:
            return None
        return {
            "organizerId": str(publication.get("organizerId") or "").strip(),
            "creators": creators,
        }
