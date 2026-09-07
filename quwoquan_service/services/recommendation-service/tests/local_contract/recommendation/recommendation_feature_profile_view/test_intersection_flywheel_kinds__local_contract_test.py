# spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-008
# spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#req-009
#
# 交集飞轮两端 kind 的物化契约：
# - coWishlistedEntity（意图环）：双方当前均想去同一实体才产出；单方不产出。
# - coExperiencedGathering（回流环）：双方各自同时持有 active Participation 与
#   公开回顾（list_experienced_gatherings 的口径）且交集非空才产出；单方不产出。
# - 行动阶梯与 registry actionKeyMeta 同轨：start_gathering(dispatch=gathering,
#   heavy gates) 为主行动；文案只用 registry 语义（一起参加过 / 都想去），
#   禁止宣称到场、同期或对方空闲。
from __future__ import annotations

from datetime import datetime, timezone
import hashlib

from internal.recommendation.recommendation_feature_profile_view.application.intersection_materializer import (
    Materializer,
    PersonaProfileSnapshot,
    WishlistEntitySnapshot,
)
from internal.recommendation.recommendation_feature_profile_view.application.intersection_projector import (
    Projector,
)


def _entity_name(entity_id: str) -> str:
    return {
        "homepage-west-lake": "西湖",
        "hp_huanglong": "黄龙",
        "hp_jiuzhaigou": "九寨沟",
    }.get(entity_id, entity_id)


class _Writer:
    def __init__(self) -> None:
        self.objects = []

    def replace_subject_intersections_if_absent(self, mutation) -> bool:
        return True

    def replace_object_intersections_if_absent(self, mutation) -> bool:
        self.objects.append(mutation)
        return True

    def replace_intersection_supply_if_absent(self, mutation) -> bool:
        return True


class _Evidence:
    def __init__(
        self,
        *,
        wishlisted: dict[str, tuple[str, ...]] | None = None,
        experienced: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        self._wishlisted = wishlisted or {}
        self._experienced = experienced or {}

    def list_following(self, persona_id: str, limit: int):
        return ()

    def list_followers(self, persona_id: str, limit: int):
        return ()

    def list_circle_ids(self, persona_id: str, limit: int):
        return ()

    def list_behaviors(self, persona_id: str, limit: int):
        return ()

    def read_persona_profile(self, persona_id: str):
        return PersonaProfileSnapshot(persona_id, persona_id, "")

    def count_intersection_supply(self, supply_key: str) -> int:
        return 0

    def list_wishlisted_entities(self, persona_id: str, limit: int):
        return tuple(
            WishlistEntitySnapshot(entity_id=value, display_name=_entity_name(value))
            for value in self._wishlisted.get(persona_id, ())
        )[:limit]

    def list_experienced_gatherings(self, persona_id: str, limit: int):
        return tuple(self._experienced.get(persona_id, ()))[:limit]

    def list_gathering_experiencers(self, gathering_id: str, limit: int):
        return tuple(
            sorted(
                persona
                for persona, gatherings in self._experienced.items()
                if gathering_id in gatherings
            )
        )[:limit]


def _rebuild(evidence: _Evidence):
    writer = _Writer()
    materializer = Materializer(
        evidence=evidence,
        projector=Projector(writer),
        now=lambda: datetime(2026, 8, 12, 12, tzinfo=timezone.utc),
    )
    assert materializer.rebuild_object(
        source_event_id="flywheel-event",
        source_event_digest=hashlib.sha256(b"flywheel-event").hexdigest(),
        subject_id="persona-a",
        object_type="user",
        object_id="persona-b",
    )
    return writer.objects[-1].reasons


def test_co_wishlisted_entity_requires_both_sides() -> None:
    reasons = _rebuild(
        _Evidence(
            wishlisted={
                "persona-a": ("hp_huanglong", "hp_jiuzhaigou"),
                "persona-b": ("hp_huanglong",),
            }
        )
    )
    matched = [r for r in reasons if r["kind"] == "coWishlistedEntity"]
    assert len(matched) == 1
    reason = matched[0]
    assert reason["intersectionClass"] == "fact"
    assert reason["dimension"] == "location"
    assert reason["moment"] == "prospective"
    assert reason["primaryText"] == "你们都想去黄龙"
    assert reason["objectKind"] == "place"
    assert reason["relationObjectId"] == "hp_huanglong"
    assert reason["displayBinding"] == "explicit_link"
    assert "".join(span["text"] for span in reason["primarySpans"]) == reason["primaryText"]
    assert reason["primarySpans"][-1]["role"] == "object"
    hint = reason["actionHints"][0]
    assert hint["actionKey"] == "start_gathering"
    assert hint["dispatch"] == "gathering"
    assert hint["requiredGates"] == [
        "login",
        "realName",
        "minorMode",
        "blocked",
        "rateLimit",
    ]
    assert hint["target"]["objectId"] == "hp_huanglong"
    assert hint["target"]["objectType"] == "homepage"
    assert hint["target"]["objectKind"] == "place"
    assert hint["target"]["routeId"] == "homepageDetail"
    assert reason["subjectContext"] == "homepage:hp_huanglong"
    assert reason["primarySpans"][-1]["target"] == hint["target"]


def test_co_wishlisted_entity_is_not_fabricated_from_one_side() -> None:
    reasons = _rebuild(
        _Evidence(wishlisted={"persona-a": ("hp_huanglong",), "persona-b": ()})
    )
    assert not [r for r in reasons if r["kind"] == "coWishlistedEntity"]


def test_co_experienced_gathering_requires_both_sides() -> None:
    reasons = _rebuild(
        _Evidence(
            experienced={
                "persona-a": ("gathering_huanglong_walk",),
                "persona-b": ("gathering_huanglong_walk", "gathering_other"),
            }
        )
    )
    matched = [r for r in reasons if r["kind"] == "coExperiencedGathering"]
    assert len(matched) == 1
    reason = matched[0]
    assert reason["intersectionClass"] == "fact"
    assert reason["dimension"] == "relationship"
    assert reason["moment"] == "retrospective"
    assert reason["iconKey"] == "experience"
    # 主句由注册表 counted 模板 + mutualPair 主语渲染，并下发对应 l10nKey；
    # join(spans) == primaryText 是模板渲染的结构性结果。
    from generated.recommendation.recommendation_feature_profile_view.intersection_policy import (
        ACTION_KEYS_BY_KIND,
        STATEMENT_FORM_BY_KIND,
        SUBJECT_PATTERN_BY_NAME,
    )

    counted_form = STATEMENT_FORM_BY_KIND["coExperiencedGathering"]["counted"]
    expected_text = str(counted_form["template"]).format(
        subject=SUBJECT_PATTERN_BY_NAME["mutualPair"]["text"], count=1
    )
    assert reason["primaryText"] == expected_text == "你们一起参加过1次行动"
    assert reason["primaryTextL10nKey"] == counted_form["l10n_key"]
    assert "".join(span["text"] for span in reason["primarySpans"]) == reason["primaryText"]
    assert [span["role"] for span in reason["primarySpans"]] == ["plain", "count", "plain"]
    # 排序权重不在生产者手写：强度与其他 fact 同为 valueTier 基线，「经历最强」由注册表
    # evidenceRank 表达（Content 读面按 EvidenceKindRank 排序）。
    assert reason["strength"] == 1.0
    # 主对象是对方本人（DEC-003）：对方主页 host_implicit 校验与收件箱行对象都落在人上；
    # 共同行动只经 subjectContext 承载。
    assert reason["objectKind"] == "person"
    assert reason["actionTargetId"] == "persona-b"
    assert reason["relationObjectId"] == "persona-b"
    assert reason["displayBinding"] == "host_implicit"
    assert reason["subjectContext"] == "gathering:gathering_huanglong_walk"
    hints = reason["actionHints"]
    # 行动阶梯逐项来自注册表 actionHintsByKind.coExperiencedGathering，不在服务代码里手挑；
    # 全部指向对方本人。
    assert [hint["actionKey"] for hint in hints] == list(ACTION_KEYS_BY_KIND["coExperiencedGathering"])
    assert hints[0]["actionKey"] == "start_gathering" and hints[0]["isPrimary"] is True
    assert {hint["target"]["objectId"] for hint in hints} == {"persona-b"}
    assert {hint["target"]["objectType"] for hint in hints} == {"user"}
    assert {hint["target"]["routeId"] for hint in hints} == {"userProfile"}


def test_co_experienced_gathering_is_not_fabricated_from_one_side() -> None:
    reasons = _rebuild(
        _Evidence(
            experienced={
                "persona-a": ("gathering_huanglong_walk",),
                "persona-b": (),
            }
        )
    )
    assert not [r for r in reasons if r["kind"] == "coExperiencedGathering"]


def test_flywheel_statements_never_claim_attendance_or_availability() -> None:
    reasons = _rebuild(
        _Evidence(
            wishlisted={"persona-a": ("hp_x",), "persona-b": ("hp_x",)},
            experienced={
                "persona-a": ("gathering_y",),
                "persona-b": ("gathering_y",),
            },
        )
    )
    banned = ("到场", "签到", "有空", "同期")
    for reason in reasons:
        for phrase in banned:
            assert phrase not in str(reason["primaryText"])
