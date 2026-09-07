from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Protocol

from generated.recommendation.recommendation_feature_profile_view.intersection_policy import (
    ACTION_KEYS_BY_KIND,
    ACTION_POLICY_BY_KEY,
    OBJECT_KIND_BY_OBJECT_TYPE,
    ROUTE_ID_BY_OBJECT_KIND,
    RELATION_LABEL_BY_KIND,
    RELATION_LABEL_DEFAULT,
    STATEMENT_FORM_BY_KIND,
    SUBJECT_PATTERN_BY_NAME,
    WIRE_OBJECT_TYPE_BY_OBJECT_KIND,
)

from .intersection_projector import Projector


MAX_INTERSECTION_ACTORS = 200
MAX_INTERSECTION_SAMPLES = 3
_STATEMENT_SLOT_PATTERN = re.compile(r"\{([A-Za-z]+)\}")


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


@dataclass(frozen=True, slots=True)
class WishlistEntitySnapshot:
    entity_id: str
    display_name: str


class IntersectionEvidenceStore(Protocol):
    def list_following(self, persona_id: str, limit: int) -> tuple[str, ...]: ...

    def list_followers(self, persona_id: str, limit: int) -> tuple[str, ...]: ...

    def list_circle_ids(self, persona_id: str, limit: int) -> tuple[str, ...]: ...

    def list_behaviors(self, persona_id: str, limit: int) -> tuple[BehaviorSnapshot, ...]: ...

    def read_persona_profile(self, persona_id: str) -> PersonaProfileSnapshot | None: ...

    def count_intersection_supply(self, supply_key: str) -> int: ...

    def list_wishlisted_entities(
        self, persona_id: str, limit: int
    ) -> tuple[WishlistEntitySnapshot, ...]: ...

    def list_experienced_gatherings(self, persona_id: str, limit: int) -> tuple[str, ...]: ...

    def list_gathering_experiencers(self, gathering_id: str, limit: int) -> tuple[str, ...]: ...


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
        grouped_behaviors: dict[
            tuple[str, str], dict[str, tuple[PersonaProfileSnapshot, BehaviorSnapshot]]
        ] = {}
        for actor_id in following:
            profile = self._evidence.read_persona_profile(actor_id)
            if profile is None or not profile.display_name.strip():
                continue
            for behavior in self._evidence.list_behaviors(
                actor_id, MAX_INTERSECTION_SAMPLES
            ):
                target_id = behavior.target_id.strip()
                target_type = behavior.target_type.strip()
                if not target_id or not target_type:
                    continue
                grouped_behaviors.setdefault((target_type, target_id), {}).setdefault(
                    profile.persona_id, (profile, behavior)
                )

        facts = tuple(
            reason
            for _, by_actor in sorted(grouped_behaviors.items())
            if (
                reason := _actor_behavior_reason(
                    subject_id=normalized_subject,
                    actor_behaviors=tuple(by_actor.values()),
                    generated_at=generated_at,
                    intersection_class="fact",
                    channel=(channel or "").strip(),
                )
            )
            is not None
        ) + self._co_experienced_subject_reasons(normalized_subject, generated_at)
        affinities = tuple(
            reason
            for _, by_actor in sorted(grouped_behaviors.items())
            if (
                reason := _actor_behavior_reason(
                    subject_id=normalized_subject,
                    actor_behaviors=tuple(by_actor.values()),
                    generated_at=generated_at,
                    intersection_class="affinity",
                    channel=(channel or "").strip(),
                )
            )
            is not None
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

    def _co_experienced_subject_reasons(
        self, subject_id: str, generated_at: datetime
    ) -> tuple[dict[str, object], ...]:
        """subject 快照里的经历交集：按对方本人聚合「我们一起经历过的行动」。

        收件箱「双方交集列表」与「我的经历」资产行都读 subject 快照（DEC-003 / REQ-009），
        经历事实不能只落在对方对象页快照里。口径与对象页一致：双方都在同一 Gathering 持有
        active Participation 且各自发布了 active 公开回顾；单方不成立。
        """
        peers: dict[str, list[str]] = {}
        for gathering_id in self._evidence.list_experienced_gatherings(
            subject_id, MAX_INTERSECTION_ACTORS
        ):
            for peer_id in self._evidence.list_gathering_experiencers(
                gathering_id, MAX_INTERSECTION_ACTORS
            ):
                peer = peer_id.strip()
                if not peer or peer == subject_id:
                    continue
                peers.setdefault(peer, []).append(gathering_id)
        reasons: list[dict[str, object]] = []
        for peer, gathering_ids in sorted(peers.items()):
            reason = _co_experienced_gathering_reason(
                subject_id=subject_id,
                object_id=peer,
                peer_profile=self._evidence.read_persona_profile(peer),
                gathering_ids=tuple(sorted(set(gathering_ids))),
                generated_at=generated_at,
            )
            if reason is not None:
                reasons.append(reason)
        return tuple(reasons)

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
                shared_circle = _object_set_reason(
                    subject_id=normalized_subject,
                    object_id=normalized_object,
                    object_type="user",
                    kind="sharedCircle",
                    dimension="relationship",
                    related_ids=tuple(shared_circles),
                    generated_at=generated_at,
                )
                if shared_circle is not None:
                    reasons.append(shared_circle)
            # 意图交集（交集飞轮入口环）：双方当前均想去的相同实体。
            # 事实成立只看 entityId：缺展示名是展示层降级问题，不能在读面把
            # active 想去事实整条丢掉，否则计数与「双方没有共同想去」同形。
            subject_wishlisted = {
                item.entity_id.strip(): item
                for item in self._evidence.list_wishlisted_entities(
                    normalized_subject, MAX_INTERSECTION_ACTORS
                )
                if item.entity_id.strip()
            }
            object_wishlisted = {
                item.entity_id.strip(): item
                for item in self._evidence.list_wishlisted_entities(
                    normalized_object, MAX_INTERSECTION_ACTORS
                )
                if item.entity_id.strip()
            }
            shared_wishlisted_ids = sorted(
                set(subject_wishlisted).intersection(object_wishlisted)
            )
            if shared_wishlisted_ids:
                co_wishlisted = _co_wishlisted_reason(
                    subject_id=normalized_subject,
                    object_id=normalized_object,
                    peer_profile=self._evidence.read_persona_profile(normalized_object),
                    entities=tuple(
                        subject_wishlisted[entity_id]
                        for entity_id in shared_wishlisted_ids
                    ),
                    generated_at=generated_at,
                )
                # 结论句渲染不成立时只隐藏这一条（降级链末级），不让整份读面失败。
                if co_wishlisted is not None:
                    reasons.append(co_wishlisted)
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
                co_experienced = _co_experienced_gathering_reason(
                    subject_id=normalized_subject,
                    object_id=normalized_object,
                    peer_profile=self._evidence.read_persona_profile(normalized_object),
                    gathering_ids=tuple(shared_experienced),
                    generated_at=generated_at,
                )
                # 模板不可渲染只隐藏这一条（降级链末级），不让整份读面失败。
                if co_experienced is not None:
                    reasons.append(co_experienced)
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
) -> dict[str, object] | None:
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
    # 主句只由注册表模板产出：对象缺展示名时不造「这条内容」这类泛对象，整条隐藏。
    object_label = first_behavior.display_name.strip()
    statement = _render_statement(
        kind="followeeViewing",
        slots={
            "subject": _representative_subject_spans(first_profile, count),
            "object": (
                {"text": object_label, "role": "object", "target": target, "visual": None},
            ),
        },
    )
    if statement is None:
        return None
    primary_text, primary_spans, primary_text_l10n_key = statement
    reason = _base_reason(
        subject_id=subject_id,
        intersection_id=(
            f"{subject_id}:followeeViewing:{first_behavior.target_type}:"
            f"{first_behavior.target_id}:{intersection_class}:{channel or 'all'}"
        ),
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
            "subjectContext": _subject_context(first_behavior),
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
            "primaryTextL10nKey": primary_text_l10n_key,
            "primarySpans": list(primary_spans),
            "sampleVisuals": [_visual(profile) for profile, _ in samples],
            "representativeActor": _representative_actor(
                first_profile, kind="followeeViewing"
            ),
            "actorEvidenceTotalCount": count,
            "actorEvidenceCompleteness": "complete",
            "actorEvidence": actor_evidence,
            "factPointCount": 1 if intersection_class == "fact" else 0,
            "recommendedPointCount": 1 if intersection_class == "affinity" else 0,
            "totalPointCount": 1,
            "actionHints": _action_hints("followeeViewing", target),
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
    # 这些 kind 只在宿主即对象的面（对方主页 / 圈子页 / 实体页）成句，对象位由
    # host_implicit 剔除，因此取注册表的 noObject 变体；缺模板即隐藏，不拼谓语。
    statement = _render_statement(
        kind=kind,
        variant="noObject",
        slots={"subject": _representative_subject_spans(samples[0], count)},
    )
    if statement is None:
        return None
    primary_text, primary_spans, primary_text_l10n_key = statement
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
            "primaryTextL10nKey": primary_text_l10n_key,
            "primarySpans": list(primary_spans),
            "sampleVisuals": [_visual(profile) for profile in samples],
            "representativeActor": _representative_actor(samples[0], kind=kind),
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
            "actionHints": _action_hints(kind, target),
        }
    )
    return reason


def _co_wishlisted_reason(
    *,
    subject_id: str,
    object_id: str,
    peer_profile: PersonaProfileSnapshot | None,
    entities: tuple[WishlistEntitySnapshot, ...],
    generated_at: datetime,
) -> dict[str, object] | None:
    """coWishlistedEntity（都想去）：意图交集，行动阶梯首位是发起聚集。

    主句由 registry 的 statementTemplates.byKind.coWishlistedEntity 主模板渲染，
    主语取 subjectPatterns.mutualPair；保鲜窗口对齐 registry timeWindowDays=14。

    模板或槽位不可渲染时返回 None（降级链末级：隐藏该句），不产出半句话，
    也不把单条展示失败升级成整份读面失败。注册表为本 kind 登记的 counted 模板
    以「具名第三方主语 + 你」成句，与 mutualPair 主语不可组合，因此本生产者的
    降级链只有「具名 → 隐藏」两级；缺具名对象时不造名、不借邻近语义。
    """
    named = next(
        (item for item in entities if item.display_name.strip()),
        None,
    )
    if named is None:
        return None
    samples = tuple(item for item in entities if item.display_name.strip())[
        :MAX_INTERSECTION_SAMPLES
    ]
    count = len(entities)
    entity_label = named.display_name.strip()
    entity_id = named.entity_id.strip()
    # Wishlist 事实锚点是 canonical Entity Homepage；wire target 必须落在
    # registry 的 place + homepageDetail 绑定，不能用宽泛 person/entity 身份制造漂移。
    entity_target = _target(object_type="homepage", object_id=entity_id)
    statement = _render_statement(
        kind="coWishlistedEntity",
        slots={
            "subject": (_plain_span(_subject_pattern_text("mutualPair")),),
            "object": (
                {
                    "text": entity_label,
                    "role": "object",
                    "target": entity_target,
                    "visual": None,
                },
            ),
        },
    )
    if statement is None:
        return None
    primary_text, primary_spans, primary_text_l10n_key = statement
    reason = _base_reason(
        subject_id=subject_id,
        intersection_id=f"{subject_id}:user:{object_id}:coWishlistedEntity",
        intersection_class="fact",
        kind="coWishlistedEntity",
        dimension="location",
        source="entity_wishlist_events",
        object_kind="place",
        relation_object_id=entity_id,
        action_target_id=entity_id,
        primary_text=primary_text,
        generated_at=generated_at,
        ttl=timedelta(days=14),
    )
    reason.update(
        {
            "primaryTextL10nKey": primary_text_l10n_key,
            "subjectContext": f"homepage:{entity_id}",
            "displayBinding": "explicit_link",
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
                    sample_text="、".join(item.display_name.strip() for item in samples),
                    visuals=[],
                )
            ],
            "primarySpans": list(primary_spans),
            "factPointCount": 1,
            "totalPointCount": 1,
            "actionHints": _action_hints("coWishlistedEntity", entity_target),
        }
    )
    # REQ-004：mutualPair 主语「你们」在非对方主页的宿主面（内容卡等）只能靠具名代表人
    # ——也就是对方本人——解释；对方缺名则不挂代表人，输出口据此在这些面隐藏该句。
    reason.update(_mutual_pair_peer_evidence(peer_profile, kind="coWishlistedEntity"))
    return reason


def _mutual_pair_peer_evidence(
    peer_profile: PersonaProfileSnapshot | None, *, kind: str
) -> dict[str, object]:
    if peer_profile is None or not peer_profile.display_name.strip():
        return {}
    return {
        "representativeActor": _representative_actor(peer_profile, kind=kind),
        "actorEvidenceTotalCount": 1,
        "actorEvidenceCompleteness": "complete",
        "actorEvidence": [
            _actor_evidence(
                peer_profile,
                source_ref=kind,
                source_point_id=f"{peer_profile.persona_id}:{kind}",
                rank=1,
            )
        ],
        "sampleVisuals": [_visual(peer_profile)],
    }


def _co_experienced_gathering_reason(
    *,
    subject_id: str,
    object_id: str,
    peer_profile: PersonaProfileSnapshot | None,
    gathering_ids: tuple[str, ...],
    generated_at: datetime,
) -> dict[str, object] | None:
    """coExperiencedGathering（一起参加过）：经历交集，强度最高的事实交集。

    只由「双方 active Participation + 双方各自公开回顾」触发（诚实红线延伸）。
    主对象是对方本人（DEC-003）：对方主页 host_implicit 校验要求 reason target 等于宿主，
    收件箱以对方为行对象；共同行动经 subjectContext `gathering:<id>` 与 intersectionPoints
    承载，端侧「回看行动详情」据此解析，不用 actionTargetId 冒充。

    主句按 registry counted 模板以 mutualPair 主语渲染（快照不持有行动名）；
    模板不可渲染时返回 None（降级链末级：隐藏该句）。保鲜窗口对齐 timeWindowDays=30。
    """
    samples = gathering_ids[:MAX_INTERSECTION_SAMPLES]
    count = len(gathering_ids)
    statement = _render_statement(
        kind="coExperiencedGathering",
        counted=True,
        slots={
            "subject": (_plain_span(_subject_pattern_text("mutualPair")),),
            "count": (
                {"text": str(count), "role": "count", "target": None, "visual": None},
            ),
        },
    )
    if statement is None:
        return None
    primary_text, primary_spans, primary_text_l10n_key = statement
    peer_target = _target(object_type="user", object_id=object_id)
    reason = _base_reason(
        subject_id=subject_id,
        intersection_id=f"{subject_id}:user:{object_id}:coExperiencedGathering",
        intersection_class="fact",
        kind="coExperiencedGathering",
        dimension="relationship",
        source="gathering_shared_experience_events",
        object_kind="person",
        relation_object_id=object_id,
        action_target_id=object_id,
        primary_text=primary_text,
        generated_at=generated_at,
        ttl=timedelta(days=30),
    )
    reason.update(
        {
            "primaryTextL10nKey": primary_text_l10n_key,
            "subjectContext": f"gathering:{samples[0]}",
            "displayBinding": "host_implicit",
            "moment": "retrospective",
            "iconKey": "experience",
            "tone": "sage",
            # 排序权重不在生产者手写：强度取 _base_reason 的 valueTier 基线，
            # 「经历最强」由注册表 evidenceRank=5 表达并由 Content 读面消费。
            "intersectionPoints": [
                _point(
                    point_id=f"{object_id}:coExperiencedGathering",
                    point_class="fact",
                    dimension="relationship",
                    label="共同经历",
                    source_ref="coExperiencedGathering",
                    count=count,
                    # gathering id 不是展示文本：样本文本留空，行动锚点只经 subjectContext 下发，
                    # 否则 Content 水合会把 id 当代表人名。
                    sample_text="",
                    visuals=[],
                )
            ],
            "primarySpans": list(primary_spans),
            "factPointCount": 1,
            "totalPointCount": 1,
            "actionHints": _action_hints("coExperiencedGathering", peer_target),
        }
    )
    # 对方主页与收件箱行以宿主解释「你们」；内容卡等非人宿主面靠这位具名代表人（对方）解释。
    reason.update(
        _mutual_pair_peer_evidence(peer_profile, kind="coExperiencedGathering")
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
) -> dict[str, object] | None:
    samples = related_ids[:MAX_INTERSECTION_SAMPLES]
    count = len(related_ids)
    # 宿主即对方本人：mutualPair 主语 + 计数，取注册表 noObject 变体；缺模板即隐藏。
    statement = _render_statement(
        kind=kind,
        variant="noObject",
        slots={
            "subject": (_plain_span(_subject_pattern_text("mutualPair")),),
            "count": (
                {"text": str(count), "role": "count", "target": None, "visual": None},
            ),
        },
    )
    if statement is None:
        return None
    primary_text, primary_spans, primary_text_l10n_key = statement
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
            # 关系事实的主对象是对方本人（DEC-003 同形）；被计数对象只经 subjectContext 锚点
            # 与 intersectionPoints 样本承载，端侧「回看共同圈子」从 subjectContext 解析。
            "subjectContext": f"circle:{samples[0]}" if samples else "",
            "intersectionPoints": [
                _point(
                    point_id=f"{object_id}:{kind}",
                    point_class="fact",
                    dimension=dimension,
                    label="共同圈子",
                    source_ref=kind,
                    count=count,
                    # 圈子 id 不是展示文本：样本文本留空，共同圈子锚点只经 subjectContext 下发，
                    # 否则 Content 水合会把 id 当代表名（与 coExperiencedGathering 同一红线）。
                    sample_text="",
                    visuals=[],
                )
            ],
            "primaryTextL10nKey": primary_text_l10n_key,
            "primarySpans": list(primary_spans),
            "factPointCount": 1,
            "totalPointCount": 1,
            "actionHints": _action_hints(
                kind, _target(object_type=object_type, object_id=object_id)
            ),
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
        # 证据行由 Content 水合出口按契约闭集实例化；物化侧只保证字段存在。
        "evidenceRows": [],
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
        "subjectContext": "",
        # 策略身份（cohort）由 Content 水合出口按生成表 IntersectionPolicyDigest 盖章；
        # 生产者只保留槽位，不自行签发第二份策略身份。
        "cohort": "",
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


def _subject_context(behavior: BehaviorSnapshot) -> str:
    """宿主锚点 `<objectType>:<objectId>`：前缀就是行为目标的 objectType。

    objectType→objectKind 只由注册表 objectTypeBindings 翻译（消费方查同一张生成表），
    这里不再维护第二份词汇；未登记 objectType 不产出锚点。
    """
    target_type = behavior.target_type.strip()
    target_id = behavior.target_id.strip()
    if not target_type or not target_id or not _object_kind(target_type):
        return ""
    return f"{target_type}:{target_id}"


def _target(*, object_type: str, object_id: str) -> dict[str, object]:
    """把开放的 objectType 收口为 canonical wire target。

    objectType 先经 objectTypeBindings 收口成 objectKind，再由 objectKinds[].objectType
    给出 wire objectType（user / circle / homepage / post …），与 Content 水合侧同一张表；
    未登记的 objectType 三个字段全落空串，由展示合同 fail-closed，而不是把原始词汇透传到端。
    """
    object_kind = _object_kind(object_type)
    return {
        "objectType": WIRE_OBJECT_TYPE_BY_OBJECT_KIND.get(object_kind, ""),
        "objectId": object_id,
        "objectKind": object_kind,
        "routeId": ROUTE_ID_BY_OBJECT_KIND.get(object_kind, ""),
    }


def _plain_span(text: str) -> dict[str, object]:
    return {"text": text, "role": "plain", "target": None, "visual": None}


def _representative_subject_spans(
    representative: PersonaProfileSnapshot,
    count: int,
) -> tuple[dict[str, object], ...]:
    """代表人主语：具名代表人是可点击的 object span，人数 > 1 时按
    subjectPatterns.namedWithMore 追加「等 N 人」尾部（与 Content 水合侧
    representativeSubjectSpans 同形）。代表人缺名则不可渲染（返回空，由模板判 None）。"""
    name = representative.display_name.strip()
    if not name:
        return ()
    name_span = {
        "text": name,
        "role": "object",
        "target": _target(object_type="user", object_id=representative.persona_id),
        "visual": None,
    }
    if count <= 1:
        return (name_span,)
    pattern = _subject_pattern_text("namedWithMore")
    if "{subject}" not in pattern:
        return ()
    tail = pattern.replace("{subject}", "", 1).replace("{count}", str(count))
    return (name_span, _plain_span(tail)) if tail else (name_span,)


def _subject_pattern_text(name: str) -> str:
    """取 registry.presentationText.subjectPatterns 的主语短语；未登记返回空串。"""
    pattern = SUBJECT_PATTERN_BY_NAME.get(name)
    return str(pattern["text"]).strip() if pattern else ""


def _render_statement(
    *,
    kind: str,
    slots: dict[str, tuple[dict[str, object], ...]],
    counted: bool = False,
    variant: str | None = None,
) -> tuple[str, tuple[dict[str, object], ...], str] | None:
    """按 registry.statementTemplates 渲染结论句：文本与 spans 出自同一模板，
    join(primarySpans.text) == primaryText 因此是渲染的结构性结果而非手工对齐。

    `counted=True` 取该 kind 登记的 counted 形式（纯计数降级句）；`variant` 取登记的
    形态变体（personPlace / noObject / circleTag）；未登记即 None。
    模板引用的槽位缺值时返回 None，由调用方走降级链，不用空串拼出半句话。
    """
    form = STATEMENT_FORM_BY_KIND.get(kind)
    if form and variant:
        form = (form.get("variants") or {}).get(variant)
    elif form and counted:
        form = form.get("counted")
    if not form:
        return None
    template = str(form.get("template") or "")
    l10n_key = str(form.get("l10n_key") or "")
    if not template.strip() or not l10n_key.strip():
        return None
    spans: list[dict[str, object]] = []
    cursor = 0
    for match in _STATEMENT_SLOT_PATTERN.finditer(template):
        literal = template[cursor : match.start()]
        if literal:
            spans.append(_plain_span(literal))
        filled = slots.get(match.group(1))
        if not filled or any(not str(span["text"]).strip() for span in filled):
            return None
        spans.extend(filled)
        cursor = match.end()
    tail = template[cursor:]
    if tail:
        spans.append(_plain_span(tail))
    merged = _merge_plain_spans(spans)
    text = "".join(str(span["text"]) for span in merged)
    if not text.strip():
        return None
    return text, tuple(merged), l10n_key


def _merge_plain_spans(
    spans: list[dict[str, object]],
) -> list[dict[str, object]]:
    """相邻 plain span 合并成一段：模板切片粒度不进 wire，端只看到语义分段。"""
    merged: list[dict[str, object]] = []
    for span in spans:
        if (
            merged
            and span["role"] == "plain"
            and span["target"] is None
            and merged[-1]["role"] == "plain"
            and merged[-1]["target"] is None
        ):
            merged[-1] = _plain_span(f"{merged[-1]['text']}{span['text']}")
            continue
        merged.append(dict(span))
    return merged


def _visual(profile: PersonaProfileSnapshot) -> dict[str, object]:
    return {
        "assetKind": "avatar",
        "imageUrl": profile.avatar_url,
        "displayName": profile.display_name,
        "target": _target(object_type="user", object_id=profile.persona_id),
    }


def _relation_label(kind: str) -> str:
    """代表人关系称谓只出自 registry.presentationText.relationLabels（未登记取 default）。"""
    entry = RELATION_LABEL_BY_KIND.get(kind)
    return str(entry["text"]) if entry else RELATION_LABEL_DEFAULT


def _representative_actor(
    profile: PersonaProfileSnapshot, *, kind: str
) -> dict[str, object]:
    return {
        "actorId": profile.persona_id,
        "displayName": profile.display_name,
        "avatarUrl": profile.avatar_url,
        "relationLabel": _relation_label(kind),
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
        "relationLabel": _relation_label(source_ref),
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


def _action(
    action_key: str,
    target: dict[str, object],
    *,
    is_primary: bool,
    priority: int,
) -> dict[str, object]:
    policy = ACTION_POLICY_BY_KEY[action_key]
    return {
        "actionKey": action_key,
        "label": policy["label"],
        "target": target,
        "isPrimary": is_primary,
        "priority": priority,
        "actionTier": policy["tier"],
        "requiredGates": list(policy["required_gates"]),
        "dispatch": policy["dispatch"],
    }


def _action_hints(kind: str, target: dict[str, object]) -> list[dict[str, object]]:
    """按注册表 actionHintsByKind 生成行动阶梯：首位为 primary，全部指向同一 reason target。

    与云侧 Go `actionHintsForReason` 同源同序；服务代码不再按 kind 手挑 actionKey。
    未登记 kind 不下发 hint，由消费方按注册表兜底。
    """

    return [
        _action(key, target, is_primary=index == 0, priority=index + 1)
        for index, key in enumerate(ACTION_KEYS_BY_KIND.get(kind, ()))
    ]


def _object_kind(object_type: str) -> str:
    return OBJECT_KIND_BY_OBJECT_TYPE.get(object_type.strip(), "")


def _route_id(object_type: str) -> str:
    object_kind = _object_kind(object_type)
    return ROUTE_ID_BY_OBJECT_KIND.get(object_kind, "")


def _aware_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("intersection materializer clock must be timezone-aware")
    return value.astimezone(timezone.utc)
