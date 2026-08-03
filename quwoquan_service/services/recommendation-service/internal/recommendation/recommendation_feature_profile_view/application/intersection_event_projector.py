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
    ) -> None:
        if store is None or materializer is None or subject_closures is None:
            raise ValueError("intersection event projector dependencies are required")
        self._store = store
        self._materializer = materializer
        self._subject_closures = subject_closures

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
        self._materializer.rebuild_supplies(
            source_event_id=event_id,
            source_event_digest=event_digest,
        )
