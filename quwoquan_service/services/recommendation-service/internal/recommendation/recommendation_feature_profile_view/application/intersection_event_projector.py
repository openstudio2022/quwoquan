from __future__ import annotations

from datetime import datetime
from typing import Any

from .intersection_materializer import Materializer


class IntersectionEventProjector:
    """Applies typed upstream facts to object-owned evidence projections."""

    def __init__(
        self,
        *,
        store: Any,
        materializer: Materializer,
        subject_closures: Any,
        facilitation_publisher: Any | None = None,
    ) -> None:
        if store is None or materializer is None or subject_closures is None:
            raise ValueError("intersection event projector dependencies are required")
        self._store = store
        self._materializer = materializer
        self._subject_closures = subject_closures
        # 创作者促成事件出口（可选装配）：只在经历级首次达成时发布。
        self._facilitation_publisher = facilitation_publisher

    def project_persona_relationship(
        self,
        *,
        event_id: str,
        event_digest: str,
        event_name: str,
        source_persona_id: str,
        target_persona_id: str,
        following: bool,
        source_follow_cleared: bool,
        target_follow_cleared: bool,
        version: int,
        occurred_at: datetime,
    ) -> None:
        if self._subject_closures.exists(source_persona_id):
            return
        blocked = event_name == "PersonaBlocked"
        self._store.apply_persona_relationship_evidence(
            event_id=event_id,
            event_digest=event_digest,
            source_persona_id=source_persona_id,
            target_persona_id=target_persona_id,
            following=following and not source_follow_cleared,
            blocked=blocked,
            version=version,
            occurred_at=occurred_at,
        )
        if target_follow_cleared:
            self._store.apply_persona_relationship_evidence(
                event_id=event_id,
                event_digest=event_digest,
                source_persona_id=target_persona_id,
                target_persona_id=source_persona_id,
                following=False,
                blocked=False,
                version=version,
                occurred_at=occurred_at,
            )

    def project_circle_membership(
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
    ) -> None:
        if self._subject_closures.exists(persona_id):
            return
        self._store.apply_circle_membership_evidence(
            event_id=event_id,
            event_digest=event_digest,
            membership_id=membership_id,
            circle_id=circle_id,
            persona_id=persona_id,
            state=state,
            version=version,
            occurred_at=occurred_at,
        )
        self._materializer.rebuild_supplies(
            source_event_id=event_id,
            source_event_digest=event_digest,
        )

    def project_behavior(
        self,
        *,
        event_id: str,
        event_digest: str,
        persona_id: str,
        target_id: str,
        target_type: str,
        action: str,
        entity_refs: tuple[str, ...],
        display_name: str,
        occurred_at: datetime,
    ) -> None:
        if self._subject_closures.exists(persona_id):
            return
        self._store.apply_behavior_evidence(
            event_id=event_id,
            event_digest=event_digest,
            subject_id=persona_id,
            target_id=target_id,
            target_type=target_type,
            action=action,
            entity_refs=entity_refs,
            display_name=display_name,
            occurred_at=occurred_at,
        )
        if action in {"entity_page_view", "wishlist_add", "wishlist_remove"}:
            self._materializer.rebuild_supplies(
                source_event_id=event_id,
                source_event_digest=event_digest,
            )

    def project_gathering_participation(
        self,
        *,
        event_id: str,
        event_digest: str,
        gathering_id: str,
        persona_id: str,
        state: str,
        version: int,
        occurred_at: datetime,
    ) -> None:
        if self._subject_closures.exists(persona_id):
            return
        self._store.apply_gathering_participation_evidence(
            event_id=event_id,
            event_digest=event_digest,
            gathering_id=gathering_id,
            persona_id=persona_id,
            state=state,
            version=version,
            occurred_at=occurred_at,
        )

    def project_gathering_publication(
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
    ) -> None:
        if self._subject_closures.exists(organizer_id):
            return
        self._store.apply_gathering_publication_evidence(
            event_id=event_id,
            event_digest=event_digest,
            gathering_id=gathering_id,
            organizer_id=organizer_id,
            source_refs=source_refs,
            max_participants=max_participants,
            admission_policy=admission_policy,
            version=version,
            occurred_at=occurred_at,
        )

    def project_post_lifecycle(
        self,
        *,
        event_id: str,
        event_digest: str,
        event_type: str,
        post_id: str,
        post_version: int,
        author_id: str,
        author_display_name: str,
        author_avatar_url: str,
        homepage_id: str,
        visited: bool,
        occurred_at: datetime,
        gathering_id: str = "",
        recap: bool = False,
        tag_refs: tuple[str, ...] = (),
    ) -> None:
        if author_id and author_display_name and not self._subject_closures.exists(author_id):
            self._store.apply_persona_profile_evidence(
                event_id=event_id,
                event_digest=event_digest,
                persona_id=author_id,
                display_name=author_display_name,
                avatar_url=author_avatar_url,
                source_version=post_version,
                occurred_at=occurred_at,
            )
        active = event_type in {
            "PostPublished",
            "PostUpdated",
            "PostSettingsUpdated",
            "PostPromotedToWork",
        } and visited
        self._store.apply_declared_visit_evidence(
            event_id=event_id,
            event_digest=event_digest,
            post_id=post_id,
            persona_id=author_id,
            entity_id=homepage_id,
            active=active,
            source_version=post_version,
            occurred_at=occurred_at,
        )
        # 公开回顾事实（gatheringRef 回流）：作者主动关联且内容公开时写入；
        # 删除、隐私撤回或转不可见时同一 postId 回落为 inactive（经历交集收敛）。
        if gathering_id or recap:
            self._store.apply_gathering_recap_evidence(
                event_id=event_id,
                event_digest=event_digest,
                post_id=post_id,
                persona_id=author_id,
                gathering_id=gathering_id,
                active=recap,
                source_version=post_version,
                occurred_at=occurred_at,
            )
            # 创作者促成：仅 active 公开回顾可能触发经历级首次达成；
            # 占位收据保证同一 Gathering 只发布一次，溯源链断/未达成不发布。
            if recap and gathering_id and self._facilitation_publisher is not None:
                facilitation = self._store.claim_experienced_facilitation(
                    gathering_id=gathering_id,
                    occurred_at=occurred_at,
                )
                if facilitation is not None:
                    for seed_post_id, creator_id in facilitation["creators"]:
                        self._facilitation_publisher.publish_facilitation(
                            gathering_id=gathering_id,
                            creator_persona_id=creator_id,
                            seed_post_id=seed_post_id,
                            occurred_at=occurred_at,
                        )
        # postId → authorId 最小映射：创作者锚点沿溯源链（gathering.sourceRefs
        # 中的 content post → 该 post 作者）归集促成计数；删除/撤回回落 inactive。
        post_alive = event_type in {
            "PostPublished",
            "PostUpdated",
            "PostSettingsUpdated",
            "PostPromotedToWork",
        }
        if author_id:
            self._store.apply_post_author_evidence(
                event_id=event_id,
                event_digest=event_digest,
                post_id=post_id,
                author_id=author_id,
                active=post_alive,
                tag_refs=tag_refs,
                source_version=post_version,
                occurred_at=occurred_at,
            )
        self._materializer.rebuild_supplies(
            source_event_id=event_id,
            source_event_digest=event_digest,
        )
