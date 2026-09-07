# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-003
# spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/intersection-algorithm-closure/spec.md#gwt-002
# spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/intersection-sentence-unification/spec.md#gwt-002
# spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/intersection-sentence-unification/spec.md#gwt-002.t1
# spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/intersection-sentence-unification/spec.md#gwt-002.t2
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from internal.recommendation.recommendation_feature_profile_view.application.intersection_materializer import (
    BehaviorSnapshot,
    Materializer,
    PersonaProfileSnapshot,
    WishlistEntitySnapshot,
)
from internal.recommendation.recommendation_feature_profile_view.application.intersection_projector import (
    IntersectionSupplyMaterialization,
    ObjectIntersectionMaterialization,
    Projector,
    SubjectIntersectionMaterialization,
)


def _entity_name(entity_id: str) -> str:
    return {
        "homepage-west-lake": "西湖",
        "hp_huanglong": "黄龙",
        "hp_jiuzhaigou": "九寨沟",
    }.get(entity_id, entity_id)


class _Writer:
    def __init__(self) -> None:
        self.subjects: list[SubjectIntersectionMaterialization] = []
        self.objects: list[ObjectIntersectionMaterialization] = []
        self.supplies: list[IntersectionSupplyMaterialization] = []

    def replace_subject_intersections_if_absent(self, mutation) -> bool:
        self.subjects.append(mutation)
        return True

    def replace_object_intersections_if_absent(self, mutation) -> bool:
        self.objects.append(mutation)
        return True

    def replace_intersection_supply_if_absent(self, mutation) -> bool:
        self.supplies.append(mutation)
        return True


class _Evidence:
    following = {
        "viewer": ("actor-a", "actor-b"),
        "profile-target": ("actor-a", "actor-c"),
    }
    followers = {}
    circles = {
        "viewer": ("circle-a", "circle-b"),
        "profile-target": ("circle-b", "circle-c"),
        "actor-a": ("circle-target",),
    }
    profiles = {
        "actor-a": PersonaProfileSnapshot("actor-a", "甲", "https://img/a"),
        "actor-b": PersonaProfileSnapshot("actor-b", "乙", "https://img/b"),
        "actor-c": PersonaProfileSnapshot("actor-c", "丙", "https://img/c"),
        # 对象页的对方本人：mutualPair 句在非人宿主面靠这位具名代表人解释「你们」。
        "profile-target": PersonaProfileSnapshot(
            "profile-target", "林清越", "https://img/profile-target"
        ),
    }
    behaviors = {
        "actor-a": (
            BehaviorSnapshot(
                subject_id="actor-a",
                target_id="post-001",
                target_type="post",
                action="like",
                entity_refs=("place-001",),
                display_name="西湖游记",
                occurred_at=datetime(2026, 8, 2, 11, tzinfo=timezone.utc),
            ),
        ),
        "actor-b": (
            BehaviorSnapshot(
                subject_id="actor-b",
                target_id="post-002",
                target_type="post",
                action="comment",
                entity_refs=(),
                display_name="山野照片",
                occurred_at=datetime(2026, 8, 2, 10, tzinfo=timezone.utc),
            ),
        ),
    }

    def list_following(self, persona_id: str, limit: int):
        return tuple(self.following.get(persona_id, ()))[:limit]

    def list_followers(self, persona_id: str, limit: int):
        return tuple(self.followers.get(persona_id, ()))[:limit]

    def list_circle_ids(self, persona_id: str, limit: int):
        return tuple(self.circles.get(persona_id, ()))[:limit]

    def list_behaviors(self, persona_id: str, limit: int):
        return tuple(self.behaviors.get(persona_id, ()))[:limit]

    def read_persona_profile(self, persona_id: str):
        return self.profiles.get(persona_id)

    def count_intersection_supply(self, supply_key: str) -> int:
        return {
            "entity_page_view": 3,
            "entity_wishlist": 2,
            "circle_membership": 4,
            "post_declared_visit": 1,
        }[supply_key]

    wishlisted: dict[str, tuple[str, ...]] = {}
    wishlist_display_names: dict[str, str] = {}
    experienced: dict[str, tuple[str, ...]] = {}

    def list_wishlisted_entities(self, persona_id: str, limit: int):
        return tuple(
            WishlistEntitySnapshot(
                entity_id=value,
                display_name=self.wishlist_display_names.get(
                    value, _entity_name(value)
                ),
            )
            for value in self.wishlisted.get(persona_id, ())
        )[:limit]

    def list_experienced_gatherings(self, persona_id: str, limit: int):
        return tuple(self.experienced.get(persona_id, ()))[:limit]

    def list_gathering_experiencers(self, gathering_id: str, limit: int):
        return tuple(
            sorted(
                persona
                for persona, gatherings in self.experienced.items()
                if gathering_id in gatherings
            )
        )[:limit]


def _materializer() -> tuple[Materializer, _Writer]:
    writer = _Writer()
    materializer = Materializer(
        evidence=_Evidence(),
        projector=Projector(writer),
        now=lambda: datetime(2026, 8, 2, 12, tzinfo=timezone.utc),
    )
    return materializer, writer


def test_materializer_publishes_explicit_empty_and_nonempty_subject_snapshots() -> None:
    materializer, writer = _materializer()
    digest = hashlib.sha256(b"behavior-event").hexdigest()
    assert materializer.rebuild_subject(
        source_event_id="behavior-event",
        source_event_digest=digest,
        subject_id="viewer",
        channel="feed",
    ) == (True, True)
    assert len(writer.subjects) == 2
    fact, affinity = writer.subjects
    assert fact.intersection_class == "fact"
    assert len(fact.reasons) == 2
    assert {reason["actorEvidenceTotalCount"] for reason in fact.reasons} == {1}
    by_target = {
        reason["primarySpans"][-1]["target"]["objectId"]: reason
        for reason in fact.reasons
    }
    assert set(by_target) == {"post-001", "post-002"}
    assert by_target["post-001"]["subjectContext"] == "post:post-001"
    assert by_target["post-002"]["subjectContext"] == "post:post-002"
    for target_id, reason in by_target.items():
        assert "".join(str(span["text"]) for span in reason["primarySpans"]) == reason[
            "primaryText"
        ]
        assert reason["actionTargetId"] == target_id
    assert affinity.intersection_class == "affinity"
    assert len(affinity.reasons) == 2

    assert materializer.rebuild_subject(
        source_event_id="empty-event",
        source_event_digest=hashlib.sha256(b"empty-event").hexdigest(),
        subject_id="no-evidence",
    ) == (True, True)
    assert writer.subjects[-2].reasons == ()
    assert writer.subjects[-1].reasons == ()


def test_materializer_builds_person_and_nonperson_object_evidence_without_raw_ids() -> None:
    materializer, writer = _materializer()
    assert materializer.rebuild_object(
        source_event_id="relationship-event",
        source_event_digest=hashlib.sha256(b"relationship-event").hexdigest(),
        subject_id="viewer",
        object_type="user",
        object_id="profile-target",
    )
    reasons = writer.objects[-1].reasons
    assert {reason["kind"] for reason in reasons} == {"sharedFollowees", "sharedCircle"}
    actor_reason = next(reason for reason in reasons if reason["kind"] == "sharedFollowees")
    assert actor_reason["actorEvidence"][0]["displayName"] == "甲"
    assert "actor-a" not in actor_reason["primaryText"]

    assert materializer.rebuild_object(
        source_event_id="circle-event",
        source_event_digest=hashlib.sha256(b"circle-event").hexdigest(),
        subject_id="viewer",
        object_type="circle",
        object_id="circle-target",
    )
    assert writer.objects[-1].reasons[0]["kind"] == "followeeInObject"


def test_materializer_owns_all_four_supply_snapshots() -> None:
    materializer, writer = _materializer()
    changed = materializer.rebuild_supplies(
        source_event_id="supply-event",
        source_event_digest=hashlib.sha256(b"supply-event").hexdigest(),
    )
    assert changed == 4
    assert {item.supply_key for item in writer.supplies} == {
        "entity_page_view",
        "entity_wishlist",
        "circle_membership",
        "post_declared_visit",
    }


def test_materializer_consumes_generated_immutable_registry_policy() -> None:
    from generated.recommendation.recommendation_feature_profile_view.intersection_policy import (
        ACTION_KEYS_BY_KIND,
        ACTION_POLICY_BY_KEY,
        OBJECT_KIND_BY_OBJECT_TYPE,
        ROUTE_ID_BY_OBJECT_KIND,
    )
    from internal.recommendation.recommendation_feature_profile_view.application import (
        intersection_materializer as module,
    )

    assert module.OBJECT_KIND_BY_OBJECT_TYPE is OBJECT_KIND_BY_OBJECT_TYPE
    assert module.ROUTE_ID_BY_OBJECT_KIND is ROUTE_ID_BY_OBJECT_KIND
    assert module.ACTION_POLICY_BY_KEY is ACTION_POLICY_BY_KEY
    assert module.ACTION_KEYS_BY_KIND is ACTION_KEYS_BY_KIND
    target = module._target(object_type="entity", object_id="homepage-west-lake")
    assert target["objectKind"] == "place"
    assert target["routeId"] == "homepageDetail"

    # 行动阶梯逐 kind 来自注册表 actionHintsByKind：顺序、primary 位与 Go 水合同源，
    # 服务代码不再按 kind 手挑 actionKey。
    for kind in ("followeeViewing", "sharedFollowees", "followeeInObject", "coWishlistedEntity"):
        hints = module._action_hints(kind, target)
        assert [hint["actionKey"] for hint in hints] == list(ACTION_KEYS_BY_KIND[kind])
        assert [hint["isPrimary"] for hint in hints] == [True] + [False] * (len(hints) - 1)
        assert [hint["priority"] for hint in hints] == list(range(1, len(hints) + 1))
        for hint in hints:
            policy = ACTION_POLICY_BY_KEY[hint["actionKey"]]
            assert hint["label"] == policy["label"]
            assert hint["dispatch"] == policy["dispatch"]
            assert hint["target"] == target
    assert module._action_hints("unregisteredKind", target) == []


def test_subject_context_anchor_prefix_is_the_registered_object_type() -> None:
    """宿主锚点前缀就是行为目标的 objectType；是否可锚定只由注册表 objectTypeBindings 决定。

    school/enterprise 等已登记 objectType 不得再因手写集合而落空；未登记类型不产出锚点。
    """
    from generated.recommendation.recommendation_feature_profile_view.intersection_policy import (
        OBJECT_KIND_BY_OBJECT_TYPE,
    )
    from internal.recommendation.recommendation_feature_profile_view.application import (
        intersection_materializer as module,
    )

    def behavior(target_type: str) -> BehaviorSnapshot:
        return BehaviorSnapshot(
            subject_id="actor-a",
            target_id="obj-1",
            target_type=target_type,
            action="like",
            entity_refs=(),
            display_name="对象",
            occurred_at=datetime(2026, 8, 2, 11, tzinfo=timezone.utc),
        )

    for object_type in ("post", "content", "homepage", "school", "enterprise", "gathering"):
        assert object_type in OBJECT_KIND_BY_OBJECT_TYPE
        assert module._subject_context(behavior(object_type)) == f"{object_type}:obj-1"
    assert "spaceship" not in OBJECT_KIND_BY_OBJECT_TYPE
    assert module._subject_context(behavior("spaceship")) == ""
    assert module._subject_context(behavior("")) == ""


def test_co_wishlisted_materializer_matches_cross_layer_fixture() -> None:
    evidence = _Evidence()
    evidence.wishlisted = {
        "viewer": ("homepage-west-lake",),
        "profile-target": ("homepage-west-lake",),
    }
    writer = _Writer()
    materializer = Materializer(
        evidence=evidence,
        projector=Projector(writer),
        now=lambda: datetime(2026, 8, 12, 12, tzinfo=timezone.utc),
    )

    assert materializer.rebuild_object(
        source_event_id="canonical-co-wishlist",
        source_event_digest=hashlib.sha256(b"canonical-co-wishlist").hexdigest(),
        subject_id="viewer",
        object_type="user",
        object_id="profile-target",
    )
    reason = next(
        item
        for item in writer.objects[-1].reasons
        if item["kind"] == "coWishlistedEntity"
    )
    fixture_path = (
        Path(__file__).resolve().parents[6]
        / "contracts/metadata/_shared/test_fixtures/recommendation/intersection/co_wishlisted_entity_reason.json"
    )
    assert reason == json.loads(fixture_path.read_text(encoding="utf-8"))


def test_co_wishlisted_statement_is_rendered_from_registry_template() -> None:
    """主句必须由注册表模板 + 主语语法渲染，不能在服务代码里拼中文字面量。

    断言方式是「用注册表自己的模板重算一遍」：模板或主语改文案时本断言随之改变，
    materializer 里若重新出现硬编码句式则会与注册表不一致而失败。
    """
    from generated.recommendation.recommendation_feature_profile_view.intersection_policy import (
        STATEMENT_FORM_BY_KIND,
        SUBJECT_PATTERN_BY_NAME,
    )

    evidence = _Evidence()
    evidence.wishlisted = {
        "viewer": ("homepage-west-lake",),
        "profile-target": ("homepage-west-lake",),
    }
    writer = _Writer()
    materializer = Materializer(
        evidence=evidence,
        projector=Projector(writer),
        now=lambda: datetime(2026, 8, 12, 12, tzinfo=timezone.utc),
    )
    assert materializer.rebuild_object(
        source_event_id="registry-template-co-wishlist",
        source_event_digest=hashlib.sha256(b"registry-template-co-wishlist").hexdigest(),
        subject_id="viewer",
        object_type="user",
        object_id="profile-target",
    )
    reason = next(
        item
        for item in writer.objects[-1].reasons
        if item["kind"] == "coWishlistedEntity"
    )

    form = STATEMENT_FORM_BY_KIND["coWishlistedEntity"]
    expected_text = (
        form["template"]
        .replace("{subject}", SUBJECT_PATTERN_BY_NAME["mutualPair"]["text"])
        .replace("{object}", "西湖")
    )
    assert reason["primaryText"] == expected_text
    assert reason["primaryTextL10nKey"] == form["l10n_key"]
    assert "".join(span["text"] for span in reason["primarySpans"]) == reason["primaryText"]
    object_spans = [
        span for span in reason["primarySpans"] if span["role"] == "object"
    ]
    assert len(object_spans) == 1
    assert object_spans[0]["target"]["objectId"] == "homepage-west-lake"
    assert object_spans[0]["target"]["routeId"] == "homepageDetail"


def test_co_wishlisted_keeps_unnamed_facts_in_count_and_names_only_named_object() -> None:
    """缺展示名是展示层降级，不是事实缺席：计数仍含该事实，主句只具名有名字的对象。"""
    evidence = _Evidence()
    evidence.wishlisted = {
        "viewer": ("homepage-anonymous", "homepage-west-lake"),
        "profile-target": ("homepage-anonymous", "homepage-west-lake"),
    }
    evidence.wishlist_display_names = {"homepage-anonymous": ""}
    writer = _Writer()
    materializer = Materializer(
        evidence=evidence,
        projector=Projector(writer),
        now=lambda: datetime(2026, 8, 12, 12, tzinfo=timezone.utc),
    )
    assert materializer.rebuild_object(
        source_event_id="unnamed-co-wishlist",
        source_event_digest=hashlib.sha256(b"unnamed-co-wishlist").hexdigest(),
        subject_id="viewer",
        object_type="user",
        object_id="profile-target",
    )
    reason = next(
        item
        for item in writer.objects[-1].reasons
        if item["kind"] == "coWishlistedEntity"
    )
    assert reason["intersectionPoints"][0]["count"] == 2
    assert reason["relationObjectId"] == "homepage-west-lake"
    assert "西湖" in reason["primaryText"]


def test_co_wishlisted_statement_hides_when_registry_template_is_unavailable() -> None:
    """模板或槽位缺失时只隐藏这一条，不退回硬编码句式，也不让整份读面失败。"""
    from internal.recommendation.recommendation_feature_profile_view.application import (
        intersection_materializer as module,
    )

    assert (
        module._render_statement(kind="unregisteredKind", slots={"object": ()}) is None
    )
    assert (
        module._render_statement(
            kind="coWishlistedEntity",
            slots={"subject": (module._plain_span("你们"),)},
        )
        is None
    )

    evidence = _Evidence()
    evidence.wishlisted = {
        "viewer": ("homepage-west-lake",),
        "profile-target": ("homepage-west-lake",),
    }
    writer = _Writer()
    materializer = Materializer(
        evidence=evidence,
        projector=Projector(writer),
        now=lambda: datetime(2026, 8, 12, 12, tzinfo=timezone.utc),
    )
    original = module._render_statement

    def only_co_wishlisted_unrenderable(**kwargs):
        # 所有 kind 现在都经模板渲染；只让 coWishlistedEntity 的模板「不可用」，
        # 验证降级只作用于该条，同一读面里其他 kind 照常产出。
        if kwargs.get("kind") == "coWishlistedEntity":
            return None
        return original(**kwargs)

    module._render_statement = only_co_wishlisted_unrenderable
    try:
        assert materializer.rebuild_object(
            source_event_id="unrenderable-co-wishlist",
            source_event_digest=hashlib.sha256(b"unrenderable-co-wishlist").hexdigest(),
            subject_id="viewer",
            object_type="user",
            object_id="profile-target",
        )
    finally:
        module._render_statement = original
    kinds = {item["kind"] for item in writer.objects[-1].reasons}
    assert "coWishlistedEntity" not in kinds
    assert "sharedFollowees" in kinds


def test_co_wishlisted_materialization_targets_place_with_canonical_route() -> None:
    evidence = _Evidence()
    evidence.wishlisted = {
        "viewer": ("homepage-west-lake",),
        "profile-target": ("homepage-west-lake",),
    }
    writer = _Writer()
    materializer = Materializer(
        evidence=evidence,
        projector=Projector(writer),
        now=lambda: datetime(2026, 8, 2, 12, tzinfo=timezone.utc),
    )

    assert materializer.rebuild_object(
        source_event_id="wishlist-event",
        source_event_digest=hashlib.sha256(b"wishlist-event").hexdigest(),
        subject_id="viewer",
        object_type="user",
        object_id="profile-target",
    )
    reason = next(
        item for item in writer.objects[-1].reasons
        if item["kind"] == "coWishlistedEntity"
    )
    hint = reason["actionHints"][0]
    assert reason["objectKind"] == "place"
    assert reason["relationObjectId"] == "homepage-west-lake"
    assert reason["actionTargetId"] == "homepage-west-lake"
    assert reason["subjectContext"] == "homepage:homepage-west-lake"
    assert reason["displayBinding"] == "explicit_link"
    assert "".join(span["text"] for span in reason["primarySpans"]) == reason["primaryText"]
    assert reason["primarySpans"][-1]["role"] == "object"
    assert reason["primarySpans"][-1]["target"] == hint["target"]
    assert hint["target"] == {
        "objectType": "homepage",
        "objectId": "homepage-west-lake",
        "objectKind": "place",
        "routeId": "homepageDetail",
    }
    assert hint["dispatch"] == "gathering"


def test_target_wire_object_type_is_normalized_through_registry_tables() -> None:
    """target.objectType 不透传开放词汇：museum/university 等先收口成 objectKind，再取注册表
    登记的 canonical wire objectType（homepage/user/post…），与 Content 水合侧同一张表；
    未登记 objectType 三字段全空，由展示合同 fail-closed。"""
    from generated.recommendation.recommendation_feature_profile_view.intersection_policy import (
        OBJECT_KIND_BY_OBJECT_TYPE,
        WIRE_OBJECT_TYPE_BY_OBJECT_KIND,
    )
    from internal.recommendation.recommendation_feature_profile_view.application import (
        intersection_materializer as module,
    )

    museum = module._target(object_type="museum", object_id="hp-1")
    assert museum["objectKind"] == OBJECT_KIND_BY_OBJECT_TYPE["museum"] == "place"
    assert museum["objectType"] == WIRE_OBJECT_TYPE_BY_OBJECT_KIND["place"] == "homepage"
    assert museum["routeId"] == "homepageDetail"

    user = module._target(object_type="user", object_id="u-1")
    assert user["objectType"] == "user" and user["objectKind"] == "person"

    unknown = module._target(object_type="unregistered_type", object_id="x-1")
    assert unknown["objectType"] == "" and unknown["objectKind"] == "" and unknown["routeId"] == ""


def test_shared_circle_is_a_person_shaped_relationship_fact_with_circle_subject_context() -> None:
    """sharedCircle 与 coExperiencedGathering 同形（DEC-003）：主对象是对方本人，行动阶梯按注册表
    只到人且全部指向对方；共同圈子经 subjectContext `circle:<id>` 锚点下发，样本文本不放圈子 id。
    调用形状与生产入口一致（object_type="user"，object_id=对方）。"""
    from generated.recommendation.recommendation_feature_profile_view.intersection_policy import (
        ACTION_KEYS_BY_KIND,
    )
    from internal.recommendation.recommendation_feature_profile_view.application import (
        intersection_materializer as module,
    )

    reason = module._object_set_reason(
        subject_id="actor-a",
        object_id="peer-1",
        object_type="user",
        kind="sharedCircle",
        dimension="relationship",
        related_ids=("circle-1", "circle-2"),
        generated_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    assert reason["objectKind"] == "person"
    assert reason["actionTargetId"] == "peer-1"
    assert reason["subjectContext"] == "circle:circle-1"
    assert reason["intersectionPoints"][0]["count"] == 2
    assert reason["intersectionPoints"][0]["sampleText"] == ""
    hints = reason["actionHints"]
    assert [hint["actionKey"] for hint in hints] == list(ACTION_KEYS_BY_KIND["sharedCircle"])
    assert list(ACTION_KEYS_BY_KIND["sharedCircle"]) == ["greet_person", "message_person"]
    assert hints and hints[0]["isPrimary"] is True
    assert {hint["target"]["objectType"] for hint in hints} == {"user"}
    assert {hint["target"]["objectId"] for hint in hints} == {"peer-1"}


def _co_experienced_fixture_reason() -> dict[str, object]:
    """真实 materializer 输出（非手写）：与跨层 golden `co_experienced_gathering_reason.json` 对齐。"""
    evidence = _Evidence()
    evidence.experienced = {
        "viewer": ("gathering-west-lake-walk",),
        "profile-target": ("gathering-west-lake-walk", "gathering-other"),
    }
    writer = _Writer()
    materializer = Materializer(
        evidence=evidence,
        projector=Projector(writer),
        now=lambda: datetime(2026, 8, 12, 12, tzinfo=timezone.utc),
    )
    assert materializer.rebuild_object(
        source_event_id="canonical-co-experienced",
        source_event_digest=hashlib.sha256(b"canonical-co-experienced").hexdigest(),
        subject_id="viewer",
        object_type="user",
        object_id="profile-target",
    )
    return next(
        item
        for item in writer.objects[-1].reasons
        if item["kind"] == "coExperiencedGathering"
    )


def test_co_experienced_gathering_materializer_matches_cross_layer_fixture() -> None:
    """经历交集的跨层 golden 由生产者输出锁定：Content 读面与 App 消费方只把它当 wire 样本解析。

    形状（DEC-003）：主对象是对方本人（objectKind=person、actionTargetId=对方），共同行动只经
    subjectContext 承载，主句由 counted 模板 + mutualPair 渲染。
    """
    reason = _co_experienced_fixture_reason()
    fixture_path = (
        Path(__file__).resolve().parents[6]
        / "contracts/metadata/_shared/test_fixtures/recommendation/intersection/co_experienced_gathering_reason.json"
    )
    assert reason == json.loads(fixture_path.read_text(encoding="utf-8"))


def test_subject_snapshot_carries_co_experienced_gathering_per_peer() -> None:
    """收件箱 / 我的经历读 subject 快照：经历事实按对方本人聚合进入 subject 快照，
    与对象页快照同一口径（双方 active Participation + 各自公开回顾）；单方不成立。"""
    evidence = _Evidence()
    evidence.experienced = {
        "viewer": ("gathering-a", "gathering-b"),
        "peer-1": ("gathering-a", "gathering-b"),
        "peer-2": ("gathering-b",),
        "peer-3": ("gathering-c",),
    }
    writer = _Writer()
    materializer = Materializer(
        evidence=evidence,
        projector=Projector(writer),
        now=lambda: datetime(2026, 8, 12, 12, tzinfo=timezone.utc),
    )
    fact_changed, _ = materializer.rebuild_subject(
        source_event_id="subject-experience",
        source_event_digest=hashlib.sha256(b"subject-experience").hexdigest(),
        subject_id="viewer",
    )
    assert fact_changed
    fact_snapshot = next(s for s in writer.subjects if s.intersection_class == "fact")
    experienced = {
        reason["actionTargetId"]: reason
        for reason in fact_snapshot.reasons
        if reason["kind"] == "coExperiencedGathering"
    }
    assert set(experienced) == {"peer-1", "peer-2"}
    assert experienced["peer-1"]["primaryText"] == "你们一起参加过2次行动"
    assert experienced["peer-2"]["primaryText"] == "你们一起参加过1次行动"
    assert experienced["peer-1"]["objectKind"] == "person"
    assert experienced["peer-1"]["subjectContext"] == "gathering:gathering-a"


def test_every_produced_kind_is_rendered_from_registry_templates() -> None:
    """GWT-002：物化侧全部 kind 的主句、spans 与 primaryTextL10nKey 由 statementTemplates
    一次渲染——文本等于按登记模板/变体格式化的结果，l10nKey 是登记 key，join(spans)==text；
    服务代码内不再有任何 kind 的中文谓语字面量。"""
    from generated.recommendation.recommendation_feature_profile_view.intersection_policy import (
        STATEMENT_FORM_BY_KIND,
        SUBJECT_PATTERN_BY_NAME,
    )

    materializer, writer = _materializer()
    assert materializer.rebuild_subject(
        source_event_id="tpl-subject",
        source_event_digest=hashlib.sha256(b"tpl-subject").hexdigest(),
        subject_id="viewer",
        channel="feed",
    )
    subject_reasons = [
        reason
        for snapshot in writer.subjects
        if snapshot.intersection_class == "fact"
        for reason in snapshot.reasons
    ]
    assert materializer.rebuild_object(
        source_event_id="tpl-user",
        source_event_digest=hashlib.sha256(b"tpl-user").hexdigest(),
        subject_id="viewer",
        object_type="user",
        object_id="profile-target",
    )
    user_reasons = list(writer.objects[-1].reasons)
    assert materializer.rebuild_object(
        source_event_id="tpl-circle",
        source_event_digest=hashlib.sha256(b"tpl-circle").hexdigest(),
        subject_id="viewer",
        object_type="circle",
        object_id="circle-target",
    )
    circle_reasons = list(writer.objects[-1].reasons)
    by_kind = {r["kind"]: r for r in subject_reasons + user_reasons + circle_reasons}
    assert {"followeeViewing", "sharedFollowees", "sharedCircle", "followeeInObject"} <= set(by_kind)

    named_more = SUBJECT_PATTERN_BY_NAME["namedWithMore"]["text"]
    mutual_pair = SUBJECT_PATTERN_BY_NAME["mutualPair"]["text"]

    def expect(kind: str, form: dict, **slots: str) -> None:
        reason = by_kind[kind]
        assert reason["primaryText"] == str(form["template"]).format(**slots), kind
        assert reason["primaryTextL10nKey"] == form["l10n_key"], kind
        assert "".join(s["text"] for s in reason["primarySpans"]) == reason["primaryText"], kind

    viewing = by_kind["followeeViewing"]
    viewing_count = viewing["actorEvidenceTotalCount"]
    viewing_subject = viewing["representativeActor"]["displayName"] + (
        named_more.replace("{subject}", "", 1).replace("{count}", str(viewing_count))
        if viewing_count > 1
        else ""
    )
    expect(
        "followeeViewing",
        STATEMENT_FORM_BY_KIND["followeeViewing"],
        subject=viewing_subject,
        object=viewing["intersectionPoints"][0]["label"],
    )
    # 内容对象是可点击 object span，代表人也是可点击 object span（指向其主页）。
    assert [s["role"] for s in viewing["primarySpans"]][0] == "object"
    assert viewing["primarySpans"][-1]["role"] == "object"

    followees = by_kind["sharedFollowees"]
    n = followees["actorEvidenceTotalCount"]
    subject = followees["representativeActor"]["displayName"] + (
        named_more.replace("{subject}", "", 1).replace("{count}", str(n)) if n > 1 else ""
    )
    expect(
        "sharedFollowees",
        STATEMENT_FORM_BY_KIND["sharedFollowees"]["variants"]["noObject"],
        subject=subject,
    )
    expect(
        "sharedCircle",
        STATEMENT_FORM_BY_KIND["sharedCircle"]["variants"]["noObject"],
        subject=mutual_pair,
        count=by_kind["sharedCircle"]["intersectionPoints"][0]["count"],
    )
    in_object = by_kind["followeeInObject"]
    n = in_object["actorEvidenceTotalCount"]
    subject = in_object["representativeActor"]["displayName"] + (
        named_more.replace("{subject}", "", 1).replace("{count}", str(n)) if n > 1 else ""
    )
    expect(
        "followeeInObject",
        STATEMENT_FORM_BY_KIND["followeeInObject"]["variants"]["noObject"],
        subject=subject,
    )


def test_followee_viewing_hides_instead_of_naming_a_generic_object() -> None:
    """对象缺展示名时不再以「这条内容」兜底：该条隐藏（返回 None），读面其余事实照常。"""
    from internal.recommendation.recommendation_feature_profile_view.application import (
        intersection_materializer as module,
    )

    profile = PersonaProfileSnapshot("actor-a", "甲", "https://img/a")
    nameless = BehaviorSnapshot(
        subject_id="actor-a",
        target_id="post-x",
        target_type="post",
        action="like",
        entity_refs=(),
        display_name="",
        occurred_at=datetime(2026, 8, 2, 11, tzinfo=timezone.utc),
    )
    assert (
        module._actor_behavior_reason(
            subject_id="viewer",
            actor_behaviors=((profile, nameless),),
            generated_at=datetime(2026, 8, 2, 12, tzinfo=timezone.utc),
            intersection_class="fact",
            channel="feed",
        )
        is None
    )
