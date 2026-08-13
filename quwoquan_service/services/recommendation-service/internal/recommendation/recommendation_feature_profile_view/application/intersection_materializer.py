from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Protocol

from .intersection_projector import Projector


MAX_INTERSECTION_ACTORS = 200
MAX_INTERSECTION_SAMPLES = 3


@dataclass(frozen=True, slots=True)
class PersonaProfileSnapshot:
    persona_id: str
    display_name: str
    avatar_url: str


@dataclass(frozen=True, slots=True)
class BehaviorSnapshot:
    subject_id: str
    target_id: str
    target_type: str
    action: str
    entity_refs: tuple[str, ...]
    display_name: str
    occurred_at: datetime


class IntersectionEvidenceStore(Protocol):
    def list_following(self, persona_id: str, limit: int) -> tuple[str, ...]: ...

    def list_followers(self, persona_id: str, limit: int) -> tuple[str, ...]: ...

    def list_circle_ids(self, persona_id: str, limit: int) -> tuple[str, ...]: ...

    def list_behaviors(self, persona_id: str, limit: int) -> tuple[BehaviorSnapshot, ...]: ...

    def read_persona_profile(self, persona_id: str) -> PersonaProfileSnapshot | None: ...

    def count_intersection_supply(self, supply_key: str) -> int: ...

    def list_wishlisted_entities(self, persona_id: str, limit: int) -> tuple[str, ...]: ...

    def list_experienced_gatherings(self, persona_id: str, limit: int) -> tuple[str, ...]: ...


class Materializer:
    """Builds complete explainable snapshots from object-owned event projections."""

    def __init__(
        self,
        *,
        evidence: IntersectionEvidenceStore,
        projector: Projector,
        now=lambda: datetime.now(timezone.utc),
    ) -> None:
        if evidence is None or projector is None or now is None:
            raise ValueError("intersection materializer dependencies are required")
        self._evidence = evidence
        self._projector = projector
        self._now = now

    def rebuild_subject(
        self,
        *,
        source_event_id: str,
        source_event_digest: str,
        subject_id: str,
        channel: str | None = None,
    ) -> tuple[bool, bool]:
        normalized_subject = subject_id.strip()
        if not normalized_subject:
            raise ValueError("intersection materializer subjectId is required")
        generated_at = _aware_utc(self._now())
        following = self._evidence.list_following(
            normalized_subject, MAX_INTERSECTION_ACTORS
        )
        actor_behaviors: list[tuple[PersonaProfileSnapshot, BehaviorSnapshot]] = []
        for actor_id in following:
            profile = self._evidence.read_persona_profile(actor_id)
            if profile is None or not profile.display_name.strip():
                continue
            behaviors = self._evidence.list_behaviors(actor_id, MAX_INTERSECTION_SAMPLES)
            for behavior in behaviors:
                if behavior.target_id.strip():
                    actor_behaviors.append((profile, behavior))
                    break

        facts: tuple[dict[str, object], ...] = ()
        affinities: tuple[dict[str, object], ...] = ()
        if actor_behaviors:
            facts = (
                _actor_behavior_reason(
                    subject_id=normalized_subject,
                    actor_behaviors=tuple(actor_behaviors),
                    generated_at=generated_at,
                    intersection_class="fact",
                    channel=(channel or "").strip(),
                ),
            )
            affinities = (
                _actor_behavior_reason(
                    subject_id=normalized_subject,
                    actor_behaviors=tuple(actor_behaviors),
                    generated_at=generated_at,
                    intersection_class="affinity",
                    channel=(channel or "").strip(),
                ),
            )
        fact_changed = self._projector.replace_subject_snapshot(
            source_event_id=source_event_id,
            source_event_digest=source_event_digest,
            subject_id=normalized_subject,
            intersection_class="fact",
            channel=channel,
            reasons=facts,
            generated_at=generated_at,
        )
        affinity_changed = self._projector.replace_subject_snapshot(
            source_event_id=source_event_id,
            source_event_digest=source_event_digest,
            subject_id=normalized_subject,
            intersection_class="affinity",
            channel=channel,
            reasons=affinities,
            generated_at=generated_at,
        )
        return fact_changed, affinity_changed

    def rebuild_object(
        self,
        *,
        source_event_id: str,
        source_event_digest: str,
        subject_id: str,
        object_type: str,
        object_id: str,
    ) -> bool:
        normalized_subject = subject_id.strip()
        normalized_type = object_type.strip()
        normalized_object = object_id.strip()
        if not normalized_subject or not normalized_type or not normalized_object:
            raise ValueError("intersection object materialization identity is required")
        generated_at = _aware_utc(self._now())
        reasons: list[dict[str, object]] = []
        following = set(
            self._evidence.list_following(
                normalized_subject, MAX_INTERSECTION_ACTORS
            )
        )
        if normalized_type in {"user", "persona", "person"}:
            shared_following = sorted(
                following.intersection(
                    self._evidence.list_following(
                        normalized_object, MAX_INTERSECTION_ACTORS
                    )
                )
            )
            shared_circles = sorted(
                set(
                    self._evidence.list_circle_ids(
                        normalized_subject, MAX_INTERSECTION_ACTORS
                    )
                ).intersection(
                    self._evidence.list_circle_ids(
                        normalized_object, MAX_INTERSECTION_ACTORS
                    )
                )
            )
            if shared_following:
                reason = _actor_set_reason(
                    subject_id=normalized_subject,
                    object_id=normalized_object,
                    object_type="user",
                    kind="sharedFollowees",
                    actor_ids=tuple(shared_following),
                    evidence=self._evidence,
                    generated_at=generated_at,
                )
                if reason is not None:
                    reasons.append(reason)
            if shared_circles:
                reasons.append(
                    _object_set_reason(
                        subject_id=normalized_subject,
                        object_id=normalized_object,
                        object_type="user",
                        kind="sharedCircle",
                        dimension="relationship",
                        related_ids=tuple(shared_circles),
                        generated_at=generated_at,
                    )
                )
            # 意图交集（交集飞轮入口环）：双方当前均想去的相同实体。
            shared_wishlisted = sorted(
                set(
                    self._evidence.list_wishlisted_entities(
                        normalized_subject, MAX_INTERSECTION_ACTORS
                    )
                ).intersection(
                    self._evidence.list_wishlisted_entities(
                        normalized_object, MAX_INTERSECTION_ACTORS
                    )
                )
            )
            if shared_wishlisted:
                reasons.append(
                    _co_wishlisted_reason(
                        subject_id=normalized_subject,
                        object_id=normalized_object,
                        entity_ids=tuple(shared_wishlisted),
                        generated_at=generated_at,
                    )
                )
            # 经历交集（交集飞轮回流环）：双方在同一 Gathering 均持有 active
            # Participation 且各自主动发布了公开回顾。单方发布不成立。
            shared_experienced = sorted(
                set(
                    self._evidence.list_experienced_gatherings(
                        normalized_subject, MAX_INTERSECTION_ACTORS
                    )
                ).intersection(
                    self._evidence.list_experienced_gatherings(
                        normalized_object, MAX_INTERSECTION_ACTORS
                    )
                )
            )
            if shared_experienced:
                reasons.append(
                    _co_experienced_gathering_reason(
                        subject_id=normalized_subject,
                        object_id=normalized_object,
                        gathering_ids=tuple(shared_experienced),
                        generated_at=generated_at,
                    )
                )
        else:
            actor_ids: list[str] = []
            for actor_id in sorted(following):
                if normalized_type == "circle" and normalized_object in set(
                    self._evidence.list_circle_ids(actor_id, MAX_INTERSECTION_ACTORS)
                ):
                    actor_ids.append(actor_id)
                    continue
                if any(
                    normalized_object in behavior.entity_refs
                    for behavior in self._evidence.list_behaviors(
                        actor_id, MAX_INTERSECTION_ACTORS
                    )
                ):
                    actor_ids.append(actor_id)
            if actor_ids:
                reason = _actor_set_reason(
                    subject_id=normalized_subject,
                    object_id=normalized_object,
                    object_type=normalized_type,
                    kind=(
                        "followeeInObject"
                        if normalized_type == "circle"
                        else "followeeViewedObject"
                    ),
                    actor_ids=tuple(actor_ids),
                    evidence=self._evidence,
                    generated_at=generated_at,
                )
                if reason is not None:
                    reasons.append(reason)
        return self._projector.replace_object_snapshot(
            source_event_id=source_event_id,
            source_event_digest=source_event_digest,
            subject_id=normalized_subject,
            object_type=normalized_type,
            object_id=normalized_object,
            reasons=tuple(reasons),
            generated_at=generated_at,
        )

    def rebuild_supplies(
        self,
        *,
        source_event_id: str,
        source_event_digest: str,
    ) -> int:
        computed_at = _aware_utc(self._now())
        changed = 0
        for supply_key in (
            "entity_page_view",
            "entity_wishlist",
            "circle_membership",
            "post_declared_visit",
        ):
            if self._projector.replace_supply_snapshot(
                source_event_id=source_event_id,
                source_event_digest=source_event_digest,
                supply_key=supply_key,
                distinct_object_count=self._evidence.count_intersection_supply(
                    supply_key
                ),
                computed_at=computed_at,
            ):
                changed += 1
        return changed


def _actor_behavior_reason(
    *,
    subject_id: str,
    actor_behaviors: tuple[tuple[PersonaProfileSnapshot, BehaviorSnapshot], ...],
    generated_at: datetime,
    intersection_class: str,
    channel: str,
) -> dict[str, object]:
    samples = actor_behaviors[:MAX_INTERSECTION_SAMPLES]
    first_profile, first_behavior = samples[0]
    actor_evidence = [
        _actor_evidence(
            profile,
            source_ref="followeeViewing",
            source_point_id=f"{behavior.target_id}:followee-viewing",
            rank=index + 1,
        )
        for index, (profile, behavior) in enumerate(actor_behaviors)
    ]
    count = len(actor_evidence)
    target = _target(
        object_type=first_behavior.target_type or "post",
        object_id=first_behavior.target_id,
    )
    object_label = first_behavior.display_name.strip() or "这条内容"
    primary_prefix = f"{first_profile.display_name} 等 {count} 人互动过"
    primary_text = primary_prefix + object_label
    reason = _base_reason(
        subject_id=subject_id,
        intersection_id=f"{subject_id}:followeeViewing:{intersection_class}:{channel or 'all'}",
        intersection_class=intersection_class,
        kind="followeeViewing",
        dimension="content",
        source="relationship",
        object_kind=_object_kind(first_behavior.target_type),
        relation_object_id=first_behavior.target_id,
        action_target_id=first_behavior.target_id,
        primary_text=primary_text,
        generated_at=generated_at,
        ttl=timedelta(days=7),
    )
    reason.update(
        {
            "displayBinding": "explicit_link",
            "confidenceLabel": "推荐内容" if intersection_class == "affinity" else "",
            "intersectionPoints": [
                _point(
                    point_id=f"{first_behavior.target_id}:followee-viewing",
                    point_class=intersection_class,
                    dimension="content",
                    label=first_behavior.display_name,
                    source_ref="followeeViewing",
                    count=count,
                    sample_text="、".join(
                        profile.display_name for profile, _ in samples
                    ),
                    visuals=[_visual(profile) for profile, _ in samples],
                )
            ],
            "primarySpans": [
                {"text": primary_prefix, "role": "plain", "target": None, "visual": None},
                {"text": object_label, "role": "object", "target": target, "visual": None},
            ],
            "sampleVisuals": [_visual(profile) for profile, _ in samples],
            "representativeActor": _representative_actor(first_profile),
            "actorEvidenceTotalCount": count,
            "actorEvidenceCompleteness": "complete",
            "actorEvidence": actor_evidence,
            "factPointCount": 1 if intersection_class == "fact" else 0,
            "recommendedPointCount": 1 if intersection_class == "affinity" else 0,
            "totalPointCount": 1,
            "actionHints": [_view_action(target)],
        }
    )
    return reason


def _actor_set_reason(
    *,
    subject_id: str,
    object_id: str,
    object_type: str,
    kind: str,
    actor_ids: tuple[str, ...],
    evidence: IntersectionEvidenceStore,
    generated_at: datetime,
) -> dict[str, object] | None:
    profiles = tuple(
        profile
        for actor_id in actor_ids[:MAX_INTERSECTION_ACTORS]
        if (profile := evidence.read_persona_profile(actor_id)) is not None
        and profile.display_name.strip()
    )
    if not profiles:
        return None
    samples = profiles[:MAX_INTERSECTION_SAMPLES]
    count = len(profiles)
    target = _target(object_type=object_type, object_id=object_id)
    verb = "也在这里" if kind == "followeeInObject" else "也看过这里"
    if kind == "sharedFollowees":
        verb = "是你们共同关注的人"
    primary_text = f"{samples[0].display_name} 等 {count} 人{verb}"
    reason = _base_reason(
        subject_id=subject_id,
        intersection_id=f"{subject_id}:{object_type}:{object_id}:{kind}",
        intersection_class="fact",
        kind=kind,
        dimension="relationship",
        source="relationship",
        object_kind=_object_kind(object_type),
        relation_object_id=object_id,
        action_target_id=object_id,
        primary_text=primary_text,
        generated_at=generated_at,
        ttl=timedelta(days=30 if kind == "followeeInObject" else 7),
    )
    point_id = f"{object_id}:{kind}"
    reason.update(
        {
            "displayBinding": "host_implicit",
            "intersectionPoints": [
                _point(
                    point_id=point_id,
                    point_class="fact",
                    dimension="relationship",
                    label=kind,
                    source_ref=kind,
                    count=count,
                    sample_text="、".join(profile.display_name for profile in samples),
                    visuals=[_visual(profile) for profile in samples],
                )
            ],
            "primarySpans": [
                {"text": primary_text, "role": "plain", "target": None, "visual": None}
            ],
            "sampleVisuals": [_visual(profile) for profile in samples],
            "representativeActor": _representative_actor(samples[0]),
            "actorEvidenceTotalCount": count,
            "actorEvidenceCompleteness": "complete",
            "actorEvidence": [
                _actor_evidence(
                    profile,
                    source_ref=kind,
                    source_point_id=point_id,
                    rank=index + 1,
                )
                for index, profile in enumerate(profiles)
            ],
            "factPointCount": 1,
            "totalPointCount": 1,
            "actionHints": [_view_action(target)],
        }
    )
    return reason


def _co_wishlisted_reason(
    *,
    subject_id: str,
    object_id: str,
    entity_ids: tuple[str, ...],
    generated_at: datetime,
) -> dict[str, object]:
    """coWishlistedEntity（都想去）：意图交集，行动阶梯首位是发起聚集。

    文案口径对齐 registry counted 模板「{subject}和你都想去{count}个相同的地方」；
    保鲜窗口对齐 registry timeWindowDays=14。
    """
    samples = entity_ids[:MAX_INTERSECTION_SAMPLES]
    count = len(entity_ids)
    primary_text = f"你们都想去 {count} 个相同的地方"
    entity_target = _target(object_type="entity", object_id=samples[0])
    reason = _base_reason(
        subject_id=subject_id,
        intersection_id=f"{subject_id}:user:{object_id}:coWishlistedEntity",
        intersection_class="fact",
        kind="coWishlistedEntity",
        dimension="location",
        source="entity_wishlist_events",
        object_kind="person",
        relation_object_id=object_id,
        action_target_id=samples[0],
        primary_text=primary_text,
        generated_at=generated_at,
        ttl=timedelta(days=14),
    )
    reason.update(
        {
            "displayBinding": "host_implicit",
            "moment": "prospective",
            "iconKey": "place",
            "tone": "tea",
            "intersectionPoints": [
                _point(
                    point_id=f"{object_id}:coWishlistedEntity",
                    point_class="fact",
                    dimension="location",
                    label="共同想去",
                    source_ref="coWishlistedEntity",
                    count=count,
                    sample_text="、".join(samples),
                    visuals=[],
                )
            ],
            "primarySpans": [
                {"text": primary_text, "role": "plain", "target": None, "visual": None}
            ],
            "factPointCount": 1,
            "totalPointCount": 1,
            "actionHints": [_start_gathering_action(entity_target)],
        }
    )
    return reason


def _co_experienced_gathering_reason(
    *,
    subject_id: str,
    object_id: str,
    gathering_ids: tuple[str, ...],
    generated_at: datetime,
) -> dict[str, object]:
    """coExperiencedGathering（一起参加过）：经历交集，强度最高的事实交集。

    只由「双方 active Participation + 双方各自公开回顾」触发（诚实红线延伸）；
    文案口径对齐 registry counted 模板「{subject}和你一起参加过{count}次行动」；
    保鲜窗口对齐 registry timeWindowDays=30。
    """
    samples = gathering_ids[:MAX_INTERSECTION_SAMPLES]
    count = len(gathering_ids)
    primary_text = f"你们一起参加过 {count} 次行动"
    gathering_target = _target(object_type="gathering", object_id=samples[0])
    reason = _base_reason(
        subject_id=subject_id,
        intersection_id=f"{subject_id}:user:{object_id}:coExperiencedGathering",
        intersection_class="fact",
        kind="coExperiencedGathering",
        dimension="relationship",
        source="gathering_shared_experience_events",
        object_kind="person",
        relation_object_id=object_id,
        action_target_id=samples[0],
        primary_text=primary_text,
        generated_at=generated_at,
        ttl=timedelta(days=30),
    )
    reason.update(
        {
            "displayBinding": "host_implicit",
            "moment": "retrospective",
            "iconKey": "experience",
            "tone": "sage",
            "strength": 2.0,
            "intersectionPoints": [
                _point(
                    point_id=f"{object_id}:coExperiencedGathering",
                    point_class="fact",
                    dimension="relationship",
                    label="共同经历",
                    source_ref="coExperiencedGathering",
                    count=count,
                    sample_text="、".join(samples),
                    visuals=[],
                )
            ],
            "primarySpans": [
                {"text": primary_text, "role": "plain", "target": None, "visual": None}
            ],
            "factPointCount": 1,
            "totalPointCount": 1,
            "actionHints": [
                _start_gathering_action(gathering_target),
                _open_object_action(gathering_target),
            ],
        }
    )
    return reason


def _object_set_reason(
    *,
    subject_id: str,
    object_id: str,
    object_type: str,
    kind: str,
    dimension: str,
    related_ids: tuple[str, ...],
    generated_at: datetime,
) -> dict[str, object]:
    samples = related_ids[:MAX_INTERSECTION_SAMPLES]
    count = len(related_ids)
    primary_text = f"你们有 {count} 个共同圈子"
    reason = _base_reason(
        subject_id=subject_id,
        intersection_id=f"{subject_id}:{object_type}:{object_id}:{kind}",
        intersection_class="fact",
        kind=kind,
        dimension=dimension,
        source="relationship",
        object_kind=_object_kind(object_type),
        relation_object_id=object_id,
        action_target_id=object_id,
        primary_text=primary_text,
        generated_at=generated_at,
        ttl=timedelta(days=30),
    )
    reason.update(
        {
            "displayBinding": "host_implicit",
            "intersectionPoints": [
                _point(
                    point_id=f"{object_id}:{kind}",
                    point_class="fact",
                    dimension=dimension,
                    label="共同圈子",
                    source_ref=kind,
                    count=count,
                    sample_text="、".join(samples),
                    visuals=[],
                )
            ],
            "primarySpans": [
                {"text": primary_text, "role": "plain", "target": None, "visual": None}
            ],
            "factPointCount": 1,
            "totalPointCount": 1,
        }
    )
    return reason


def _base_reason(
    *,
    subject_id: str,
    intersection_id: str,
    intersection_class: str,
    kind: str,
    dimension: str,
    source: str,
    object_kind: str,
    relation_object_id: str,
    action_target_id: str,
    primary_text: str,
    generated_at: datetime,
    ttl: timedelta,
) -> dict[str, object]:
    snapshot_id = hashlib.sha256(
        json.dumps(
            {
                "subjectId": subject_id,
                "intersectionId": intersection_id,
                "generatedAt": generated_at.isoformat(),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "kind": kind,
        "vertical": "general",
        "dimension": dimension,
        "tagRefs": [],
        "relationKind": "bridge",
        "objectKind": object_kind,
        "relationObjectId": relation_object_id,
        "strength": 1.0,
        "primaryText": primary_text,
        "primaryTextL10nKey": "",
        "displayBinding": "host_implicit",
        "secondaryText": "",
        "weightTier": "heavy",
        "actionType": "view_object",
        "actionTargetId": action_target_id,
        "source": source,
        "intersectionId": intersection_id,
        "intersectionClass": intersection_class,
        "avatarUrl": "",
        "displayName": "",
        "confidenceLabel": "",
        "modelReasonBucket": "",
        "freshAt": generated_at.isoformat(),
        "expiresAt": (generated_at + ttl).isoformat(),
        "intersectionPoints": [],
        "pointSummarySnapshotId": snapshot_id,
        "actorEvidenceTotalCount": 0,
        "actorEvidenceCompleteness": "complete",
        "actorEvidence": [],
        "factPointCount": 0,
        "recommendedPointCount": 0,
        "totalPointCount": 0,
        "dimensionPointSummary": [],
        "pointClassLabel": "事实交集" if intersection_class == "fact" else "推荐线索",
        "connectionSummary": "",
        "lastRecommendedAt": "",
        "seenAt": "",
        "rankState": "fresh",
        "primarySpans": [],
        "sampleVisuals": [],
        "representativeActor": None,
        "actionHints": [],
        "lifecycleState": "active",
        "previousStrength": 0.0,
        "strengthDelta": 1.0,
        "edgeWeight": 1.0,
        "iconKey": dimension,
        "tone": "sage" if dimension == "relationship" else "clay",
        "typeVisual": None,
        "objectVisual": None,
        "timeBucket": "current",
        "dedupeKey": intersection_id,
        "anchorUserWeight": 1.0,
        "mutualCount": 0,
        "moment": "current",
        "subjectId": subject_id,
        "subjectContext": "recommendation",
    }


def _point(
    *,
    point_id: str,
    point_class: str,
    dimension: str,
    label: str,
    source_ref: str,
    count: int,
    sample_text: str,
    visuals: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "pointId": point_id,
        "pointClass": point_class,
        "dimension": dimension,
        "label": label,
        "displayText": label,
        "sourceRef": source_ref,
        "visibility": "public",
        "count": count,
        "sampleText": sample_text,
        "sampleAvatarUrls": [
            str(visual.get("imageUrl") or "")
            for visual in visuals
            if str(visual.get("imageUrl") or "")
        ],
        "sampleVisuals": visuals,
    }


def _target(*, object_type: str, object_id: str) -> dict[str, object]:
    return {
        "objectType": object_type,
        "objectId": object_id,
        "objectKind": _object_kind(object_type),
        "routeId": _route_id(object_type),
    }


def _visual(profile: PersonaProfileSnapshot) -> dict[str, object]:
    return {
        "assetKind": "avatar",
        "imageUrl": profile.avatar_url,
        "displayName": profile.display_name,
        "target": _target(object_type="user", object_id=profile.persona_id),
    }


def _representative_actor(profile: PersonaProfileSnapshot) -> dict[str, object]:
    return {
        "actorId": profile.persona_id,
        "displayName": profile.display_name,
        "avatarUrl": profile.avatar_url,
        "relationLabel": "你关注的人",
        "privacyState": "visible",
        "target": _target(object_type="user", object_id=profile.persona_id),
        "evidenceRank": 1,
        "snapshotVersion": "current",
    }


def _actor_evidence(
    profile: PersonaProfileSnapshot,
    *,
    source_ref: str,
    source_point_id: str,
    rank: int,
) -> dict[str, object]:
    return {
        "actorId": profile.persona_id,
        "displayName": profile.display_name,
        "avatarUrl": profile.avatar_url,
        "relationLabel": "你关注的人",
        "relationSourceRef": "persona_relationship",
        "relationObjectId": profile.persona_id,
        "relationObjectName": profile.display_name,
        "sourcePointId": source_point_id,
        "sourceRef": source_ref,
        "actionSummaryText": "",
        "likeCount": 0,
        "commentCount": 0,
        "shareCount": 0,
        "privacyState": "visible",
        "target": _target(object_type="user", object_id=profile.persona_id),
        "evidenceRank": rank,
        "snapshotVersion": "current",
        "sortKey": rank,
    }


def _view_action(target: dict[str, object]) -> dict[str, object]:
    return {
        "actionKey": "view_object",
        "label": "查看",
        "target": target,
        "isPrimary": True,
        "priority": 1,
        "actionTier": "read",
        "requiredGates": [],
        "dispatch": "route",
    }


def _start_gathering_action(target: dict[str, object]) -> dict[str, object]:
    """canonical `start_gathering`：tier/gates/dispatch/label 与
    intersection_kind_registry.yaml 的 actionKeyMeta / actionLabelByKey 同轨。"""
    return {
        "actionKey": "start_gathering",
        "label": "发起聚集",
        "target": target,
        "isPrimary": True,
        "priority": 1,
        "actionTier": "heavy",
        "requiredGates": ["login", "realName", "minorMode", "blocked", "rateLimit"],
        "dispatch": "gathering",
    }


def _open_object_action(target: dict[str, object]) -> dict[str, object]:
    """canonical `open_object`：与 registry actionKeyMeta 同轨的轻查看行动。"""
    return {
        "actionKey": "open_object",
        "label": "查看对象",
        "target": target,
        "isPrimary": False,
        "priority": 2,
        "actionTier": "light",
        "requiredGates": [],
        "dispatch": "navigate",
    }


def _object_kind(object_type: str) -> str:
    return {
        "user": "person",
        "persona": "person",
        "person": "person",
        "circle": "circle",
        "post": "content",
        "content": "content",
        "entity": "place",
        "homepage": "place",
        "place": "place",
        "gathering": "gathering",
    }.get(object_type.strip(), "content")


def _route_id(object_type: str) -> str:
    return {
        "user": "userProfile",
        "persona": "userProfile",
        "person": "userProfile",
        "circle": "circleDetail",
        "post": "contentDetail",
        "content": "contentDetail",
        "entity": "entityHomepage",
        "homepage": "entityHomepage",
        "place": "entityHomepage",
        "gathering": "gatheringDetail",
    }.get(object_type.strip(), "workBrowser")


def _aware_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("intersection materializer clock must be timezone-aware")
    return value.astimezone(timezone.utc)
