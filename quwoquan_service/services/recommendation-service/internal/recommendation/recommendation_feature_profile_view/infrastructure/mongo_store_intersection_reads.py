"""交集读面：投影快照读取、社会证明诚实计数、rebuild 清点与证据 digest。

本模块是 ``MongoFeatureProfileStore`` 的读 mixin，实例属性
（``_intersection_*`` 等集合句柄）与 ``_utc_datetime`` 工具由组合类提供。
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping

from pymongo import ASCENDING, DESCENDING

from ..application.intersection_reader import (
    IntersectionSupplySnapshot,
    ObjectIntersectionSnapshot,
    SubjectIntersectionSnapshot,
)
from ..application.intersection_materializer import (
    BehaviorSnapshot,
    PersonaProfileSnapshot,
)
from ..application.intersection_rebuild import (
    IntersectionProjectionInventory,
    IntersectionSupplyInventory,
)


class MongoIntersectionReadOps:
    """交集投影读取与清点操作（``MongoFeatureProfileStore`` 的一部分）。"""

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

    # 社会证明扫描上限：单锚点候选行动数的诚实边界，防止无界聚合。
    _SOCIAL_PROOF_MAX_GATHERINGS = 500
    _SOCIAL_PROOF_MAX_CREATOR_POSTS = 500

    def read_gathering_social_proof(
        self,
        *,
        anchor_kind: str,
        object_id: str,
    ) -> dict[str, int]:
        """四锚点两级诚实计数（读时聚合，与交集读面 rebuild-on-read 同轨）。

        - published：发起级，仅 organizer 锚点语义完整（其余锚点也返回，
          但产品面只展示成形/经历两级）。
        - formed：published 且 ≥2 名 active 参与者（publish 前置已保证 room ready）。
        - experienced：formed 且 ≥2 名 active 参与者各自持有 active 公开回顾。
        时间已过但无内容的行动永远停在 formed，不进 experienced——不伪造。
        """
        anchor = anchor_kind.strip()
        normalized_object = object_id.strip()
        if not normalized_object:
            raise ValueError("social proof objectId is required")
        if anchor == "organizer":
            publication_filter: dict[str, object] = {"organizerId": normalized_object}
        elif anchor in {"entity", "content"}:
            publication_filter = {"sourceRefs.objectId": normalized_object}
        elif anchor == "creator":
            author_posts = self._intersection_post_authors.find(
                {"authorId": normalized_object, "active": True},
                {"_id": 1},
            ).limit(self._SOCIAL_PROOF_MAX_CREATOR_POSTS)
            post_ids = [str(document["_id"]) for document in author_posts]
            if not post_ids:
                return {"publishedCount": 0, "formedCount": 0, "experiencedCount": 0}
            publication_filter = {"sourceRefs.objectId": {"$in": post_ids}}
        else:
            raise ValueError("social proof anchorKind is invalid")

        publications = self._intersection_gathering_publications.find(
            publication_filter,
            {"_id": 1},
        ).limit(self._SOCIAL_PROOF_MAX_GATHERINGS)
        gathering_ids = [str(document["_id"]) for document in publications]
        published = len(gathering_ids)
        formed = 0
        experienced = 0
        for gathering_id in gathering_ids:
            participants = {
                str(document.get("personaId") or "")
                for document in self._intersection_gathering_participations.find(
                    {"gatheringId": gathering_id, "active": True},
                    {"personaId": 1},
                )
            }
            participants.discard("")
            if len(participants) < 2:
                continue
            formed += 1
            recap_authors = {
                str(document.get("personaId") or "")
                for document in self._intersection_gathering_recaps.find(
                    {"gatheringId": gathering_id, "active": True},
                    {"personaId": 1},
                )
            }
            if len(recap_authors.intersection(participants)) >= 2:
                experienced += 1
        return {
            "publishedCount": published,
            "formedCount": formed,
            "experiencedCount": experienced,
        }

    # 漏斗扫描上限：候选行动/想去事实的诚实边界；越界以 truncated 标注。
    _FUNNEL_MAX_GATHERINGS = 1000
    _FUNNEL_MAX_WISHLISTS = 5000
    _FUNNEL_MAX_FACILITATIONS = 1000

    @staticmethod
    def _funnel_capacity_tier(document: dict) -> str:
        """duo = 容量 2 且邀请制；group = 其余合法政策；旧事件缺字段归 unclassified。"""
        max_participants = int(document.get("maxParticipants") or 0)
        admission = str(document.get("admissionPolicy") or "").strip()
        if max_participants <= 0 or not admission:
            return "unclassified"
        if max_participants == 2 and admission == "invite_only":
            return "duo"
        return "group"

    def read_flywheel_funnel(
        self,
        *,
        window_from: datetime,
        window_to: datetime,
        source_object_kind: str = "",
        source_object_id: str = "",
        capacity_tier: str = "",
        tag_ref: str = "",
    ) -> dict[str, object]:
        """北极星漏斗多维诚实快照（读时聚合，不落预聚合缓存）。

        分子分母只从域事实投影派生；空数据为零、越界标 truncated、
        旧事件缺维度字段归 unclassified（指定维度过滤时被排除，不臆造）。
        比例由消费方自算：①=wishlistToJoined/wishlisted、②=experienced/formed、
        ③=creatorRepublished/facilitationNotified。
        """
        if window_from.tzinfo is None or window_to.tzinfo is None:
            raise ValueError("flywheel funnel window must be timezone-aware")
        if window_to <= window_from:
            raise ValueError("flywheel funnel window is empty")
        tier = capacity_tier.strip()
        if tier and tier not in {"duo", "group"}:
            raise ValueError("flywheel funnel capacityTier is invalid")
        kind = source_object_kind.strip()
        object_id = source_object_id.strip()
        tag = tag_ref.strip()
        truncated = False

        # 1. 候选行动：时间窗 + 来源过滤（维度事实全部来自 publication 证据）。
        publication_filter: dict[str, object] = {
            "occurredAt": {"$gte": window_from, "$lt": window_to},
        }
        if object_id:
            publication_filter["sourceRefs.objectId"] = object_id
        if kind:
            publication_filter["sourceRefs.objectKind"] = kind
        publications = list(
            self._intersection_gathering_publications.find(
                publication_filter,
                {
                    "_id": 1,
                    "sourceRefs": 1,
                    "maxParticipants": 1,
                    "admissionPolicy": 1,
                },
            ).limit(self._FUNNEL_MAX_GATHERINGS + 1)
        )
        if len(publications) > self._FUNNEL_MAX_GATHERINGS:
            truncated = True
            publications = publications[: self._FUNNEL_MAX_GATHERINGS]
        if tier:
            publications = [
                document
                for document in publications
                if self._funnel_capacity_tier(document) == tier
            ]
        if tag:
            # 类目镜头：行动的 content 来源（种草内容）标签含 tag 才入选。
            filtered = []
            for document in publications:
                seed_posts = [
                    str(ref.get("objectId") or "").strip()
                    for ref in document.get("sourceRefs") or []
                    if str(ref.get("objectKind") or "").strip() == "content"
                ]
                matched = False
                for post_id in seed_posts:
                    author = self._intersection_post_authors.find_one(
                        {"_id": post_id},
                        {"tagRefs": 1},
                    )
                    if tag in (author or {}).get("tagRefs", []):
                        matched = True
                        break
                if matched:
                    filtered.append(document)
            publications = filtered

        published = len(publications)
        formed = 0
        experienced = 0
        gathering_participants: dict[str, set[str]] = {}
        source_entities_by_gathering: dict[str, set[str]] = {}
        for document in publications:
            gathering_id = str(document["_id"])
            source_entities_by_gathering[gathering_id] = {
                str(ref.get("objectId") or "").strip()
                for ref in document.get("sourceRefs") or []
                if str(ref.get("objectId") or "").strip()
            }
            participants = {
                str(row.get("personaId") or "")
                for row in self._intersection_gathering_participations.find(
                    {"gatheringId": gathering_id, "active": True},
                    {"personaId": 1},
                )
            }
            participants.discard("")
            gathering_participants[gathering_id] = participants
            if len(participants) < 2:
                continue
            formed += 1
            recap_authors = {
                str(row.get("personaId") or "")
                for row in self._intersection_gathering_recaps.find(
                    {"gatheringId": gathering_id, "active": True},
                    {"personaId": 1},
                )
            }
            if len(recap_authors.intersection(participants)) >= 2:
                experienced += 1

        # 2. 比例①：窗口内 active 想去的 persona 中，后来在「以其想去实体为
        #    来源的候选行动」持有 active participation 的数（意图→行动的严格口径）。
        wishlist_filter: dict[str, object] = {
            "active": True,
            "updatedAt": {"$gte": window_from, "$lt": window_to},
        }
        if object_id:
            wishlist_filter["entityId"] = object_id
        wishlist_rows = list(
            self._intersection_wishlist.find(
                wishlist_filter,
                {"subjectId": 1, "entityId": 1},
            ).limit(self._FUNNEL_MAX_WISHLISTS + 1)
        )
        if len(wishlist_rows) > self._FUNNEL_MAX_WISHLISTS:
            truncated = True
            wishlist_rows = wishlist_rows[: self._FUNNEL_MAX_WISHLISTS]
        wishlisted_personas: set[str] = set()
        entities_by_persona: dict[str, set[str]] = {}
        for row in wishlist_rows:
            persona = str(row.get("subjectId") or "").strip()
            entity = str(row.get("entityId") or "").strip()
            if not persona or not entity:
                continue
            wishlisted_personas.add(persona)
            entities_by_persona.setdefault(persona, set()).add(entity)
        joined_personas: set[str] = set()
        for gathering_id, participants in gathering_participants.items():
            source_entities = source_entities_by_gathering.get(gathering_id, set())
            if not source_entities:
                continue
            for persona in participants:
                if persona in joined_personas:
                    continue
                if entities_by_persona.get(persona, set()) & source_entities:
                    joined_personas.add(persona)

        # 3. 比例③：窗口内促成收据（notifiedAt）中，收据冻结的创作者在
        #    notifiedAt 之后存在新的 active 内容（post_authors 事实）。
        facilitations = list(
            self._intersection_facilitations.find(
                {"notifiedAt": {"$gte": window_from, "$lt": window_to}},
                {"notifiedAt": 1, "creatorPersonaIds": 1},
            ).limit(self._FUNNEL_MAX_FACILITATIONS + 1)
        )
        if len(facilitations) > self._FUNNEL_MAX_FACILITATIONS:
            truncated = True
            facilitations = facilitations[: self._FUNNEL_MAX_FACILITATIONS]
        facilitation_notified = len(facilitations)
        republished = 0
        for receipt in facilitations:
            notified_at = receipt.get("notifiedAt")
            creators = [
                str(value).strip()
                for value in receipt.get("creatorPersonaIds") or []
                if str(value).strip()
            ]
            if notified_at is None or not creators:
                # 旧收据缺创作者名单：unclassified，不臆造续发。
                continue
            follow_up = self._intersection_post_authors.find_one(
                {
                    "authorId": {"$in": creators},
                    "active": True,
                    "occurredAt": {"$gt": notified_at},
                },
                {"_id": 1},
            )
            if follow_up is not None:
                republished += 1

        return {
            "wishlistedPersonaCount": len(wishlisted_personas),
            "wishlistToJoinedCount": len(joined_personas),
            "publishedCount": published,
            "formedCount": formed,
            "experiencedCount": experienced,
            "facilitationNotifiedCount": facilitation_notified,
            "creatorRepublishedCount": republished,
            "truncated": truncated,
        }

    def list_wishlisted_entities(self, persona_id: str, limit: int) -> tuple[str, ...]:
        documents = self._intersection_wishlist.find(
            {"subjectId": persona_id.strip(), "active": True},
            {"entityId": 1},
        ).sort("entityId", ASCENDING).limit(limit)
        return tuple(
            str(document.get("entityId") or "")
            for document in documents
            if str(document.get("entityId") or "").strip()
        )

    def list_experienced_gatherings(self, persona_id: str, limit: int) -> tuple[str, ...]:
        """经历事实 = 该 persona 在同一 Gathering 同时持有 active Participation
        与 active 公开回顾；缺任一半即不成立（诚实红线延伸到经历）。"""
        persona = persona_id.strip()
        recap_documents = self._intersection_gathering_recaps.find(
            {"personaId": persona, "active": True},
            {"gatheringId": 1},
        ).sort("gatheringId", ASCENDING)
        recap_gatherings = tuple(
            dict.fromkeys(
                str(document.get("gatheringId") or "")
                for document in recap_documents
                if str(document.get("gatheringId") or "").strip()
            )
        )
        experienced: list[str] = []
        for gathering_id in recap_gatherings:
            participation = self._intersection_gathering_participations.find_one(
                {"_id": f"{gathering_id}\x1f{persona}", "active": True},
                {"_id": 1},
            )
            if participation is not None:
                experienced.append(gathering_id)
            if len(experienced) >= limit:
                break
        return tuple(experienced)

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
