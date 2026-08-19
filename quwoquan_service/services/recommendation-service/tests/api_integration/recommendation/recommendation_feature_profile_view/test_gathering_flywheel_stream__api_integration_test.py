# spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-008
# spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#req-009
#
# 交集飞轮回流环的端到端投影契约（真实 Redis Stream + 真实 Mongo）：
# - 双方 GatheringParticipationChanged(active) + 各自 PostPublished(公开
#   gatheringRef 回顾) 经 durable consumer 投影后，读面必须物化
#   coExperiencedGathering；
# - 仅单方发布回顾时不产出（诚实红线：经历交集要求双方都主动沉淀）。
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json

from internal.recommendation.recommendation_feature_profile_view.adapters.inbound.stream.gathering_participation_consumer import (
    GATHERING_STREAM,
    GatheringParticipationConsumer,
)
from internal.recommendation.recommendation_feature_profile_view.adapters.inbound.stream.content_behavior_consumer import (
    CONTENT_BEHAVIOR_STREAM,
    ContentBehaviorConsumer,
)
from internal.recommendation.recommendation_feature_profile_view.adapters.inbound.stream.gathering_publication_consumer import (
    GatheringPublicationConsumer,
)
from internal.recommendation.recommendation_feature_profile_view.infrastructure.facilitation_event_publisher import (
    INTERSECTION_EVENT_STREAM,
    RedisIntersectionFacilitationEventPublisher,
)
from internal.recommendation.recommendation_feature_profile_view.adapters.inbound.stream.post_lifecycle_consumer import (
    POST_LIFECYCLE_STREAM,
    PostLifecycleConsumer,
)
from internal.recommendation.recommendation_feature_profile_view.application.intersection_event_projector import (
    IntersectionEventProjector,
)
from internal.recommendation.recommendation_feature_profile_view.application.intersection_materializer import (
    Materializer as IntersectionMaterializer,
)
from internal.recommendation.recommendation_feature_profile_view.application.intersection_projector import (
    Projector as IntersectionProjector,
)
from internal.recommendation.recommendation_feature_profile_view.application.intersection_reader import (
    Reader as IntersectionReader,
)
from internal.recommendation.recommendation_feature_profile_view.infrastructure.mongo_store import (
    MongoFeatureProfileStore,
)

from tests.support.recommendation_mongo import mongo_client, mongo_database
from tests.support.recommendation_redis import real_redis

__all__ = ["mongo_client", "mongo_database", "real_redis"]


class _OpenSubjects:
    def exists(self, _subject_id: str) -> bool:
        return False


def _build_pipeline(mongo_database, facilitation_publisher=None):
    store = MongoFeatureProfileStore(mongo_database)
    store.ensure_indexes()
    materializer = IntersectionMaterializer(
        evidence=store,
        projector=IntersectionProjector(store),
    )
    projector = IntersectionEventProjector(
        store=store,
        materializer=materializer,
        subject_closures=_OpenSubjects(),
        facilitation_publisher=facilitation_publisher,
    )
    reader = IntersectionReader(store, materializer, _OpenSubjects())
    return store, projector, reader


def _emit_participation(real_redis, *, gathering_id: str, persona_id: str) -> None:
    event_id = hashlib.sha256(
        f"GatheringParticipationChanged:{gathering_id}:{persona_id}".encode()
    ).hexdigest()
    real_redis.xadd(
        GATHERING_STREAM,
        {
            "eventId": event_id,
            "eventType": "GatheringParticipationChanged",
            "aggregateType": "Gathering",
            "aggregateId": gathering_id,
            "aggregateVersion": "3",
            "occurredAt": "2026-08-10T09:00:00Z",
            "payload": json.dumps(
                {
                    "gatheringId": gathering_id,
                    "participantPersonaId": persona_id,
                    "participationState": "active",
                }
            ),
        },
    )


def _emit_publication(
    real_redis,
    *,
    gathering_id: str,
    organizer_id: str,
    source_refs: list[dict[str, str]] | None = None,
    max_participants: int = 0,
    admission_policy: str = "",
) -> None:
    event_id = hashlib.sha256(
        f"GatheringPublished:{gathering_id}".encode()
    ).hexdigest()
    payload: dict = {
        "gatheringId": gathering_id,
        "actorPersonaId": organizer_id,
        "lifecycleStatus": "published",
        "sourceRefs": source_refs or [],
    }
    if max_participants:
        payload["maxParticipants"] = max_participants
    if admission_policy:
        payload["admissionPolicy"] = admission_policy
    real_redis.xadd(
        GATHERING_STREAM,
        {
            "eventId": event_id,
            "eventType": "GatheringPublished",
            "aggregateType": "Gathering",
            "aggregateId": gathering_id,
            "aggregateVersion": "2",
            "occurredAt": "2026-08-10T08:00:00Z",
            "payload": json.dumps(payload),
        },
    )


def _emit_recap_post(
    real_redis,
    *,
    post_id: str,
    author_id: str,
    gathering_id: str,
    tag_refs: list[str] | None = None,
    occurred_at: str = "2026-08-10T18:00:00Z",
) -> None:
    event_id = hashlib.sha256(f"PostPublished:{post_id}".encode()).hexdigest()
    real_redis.xadd(
        POST_LIFECYCLE_STREAM,
        {
            "eventId": event_id,
            "eventType": "PostPublished",
            "aggregateType": "Post",
            "aggregateId": post_id,
            "aggregateVersion": "1",
            "occurredAt": occurred_at,
            "payload": json.dumps(
                {
                    "postId": post_id,
                    "authorId": author_id,
                    "authorDisplayNameSnapshot": f"作者-{author_id}",
                    "authorAvatarUrlSnapshot": "",
                    "status": "published",
                    "visibility": "public",
                    "moderationStatus": "approved",
                    "primaryHomepageId": "",
                    "visitedAt": "",
                    "gatheringRef": gathering_id,
                    "tagRefs": tag_refs or [],
                }
            ),
        },
    )


def _drain(consumer) -> None:
    while consumer.process_once() > 0:
        pass


def _experienced_reasons(reader, subject_id: str, object_id: str):
    snapshot = reader.list_object_intersections(
        subject_id=subject_id,
        object_type="person",
        object_id=object_id,
    )
    return [
        reason
        for reason in snapshot.reasons
        if reason["kind"] == "coExperiencedGathering"
    ]


def test_gathering_flywheel_stream_materializes_co_experienced(
    mongo_database,
    real_redis,
) -> None:
    store, projector, reader = _build_pipeline(mongo_database)
    gathering_id = "gathering_flywheel_stream_pos"
    subject_a = "persona-recap-stream-a"
    subject_b = "persona-recap-stream-b"

    _emit_participation(real_redis, gathering_id=gathering_id, persona_id=subject_a)
    _emit_participation(real_redis, gathering_id=gathering_id, persona_id=subject_b)
    _drain(
        GatheringParticipationConsumer(
            redis_client=real_redis,
            feature_store=store,
            projector=projector,
            consumer="gathering-flywheel-api-test",
        )
    )
    _emit_recap_post(
        real_redis,
        post_id="post-recap-stream-a",
        author_id=subject_a,
        gathering_id=gathering_id,
    )
    _emit_recap_post(
        real_redis,
        post_id="post-recap-stream-b",
        author_id=subject_b,
        gathering_id=gathering_id,
    )
    _drain(
        PostLifecycleConsumer(
            redis_client=real_redis,
            feature_store=store,
            projector=projector,
            consumer="gathering-flywheel-api-test",
        )
    )

    reasons = _experienced_reasons(reader, subject_a, subject_b)
    assert len(reasons) == 1
    reason = reasons[0]
    assert reason["intersectionClass"] == "fact"
    assert reason["dimension"] == "relationship"
    assert reason["moment"] == "retrospective"
    action_keys = [hint["actionKey"] for hint in reason["actionHints"]]
    assert action_keys == ["start_gathering", "open_object"]


def test_gathering_flywheel_stream_requires_both_sides_to_publish(
    mongo_database,
    real_redis,
) -> None:
    store, projector, reader = _build_pipeline(mongo_database)
    gathering_id = "gathering_flywheel_stream_neg"
    subject_a = "persona-recap-solo-a"
    subject_b = "persona-recap-solo-b"

    _emit_participation(real_redis, gathering_id=gathering_id, persona_id=subject_a)
    _emit_participation(real_redis, gathering_id=gathering_id, persona_id=subject_b)
    _drain(
        GatheringParticipationConsumer(
            redis_client=real_redis,
            feature_store=store,
            projector=projector,
            consumer="gathering-flywheel-api-test-neg",
        )
    )
    # 只有 a 发布回顾：经历交集不得产出。
    _emit_recap_post(
        real_redis,
        post_id="post-recap-solo-a",
        author_id=subject_a,
        gathering_id=gathering_id,
    )
    _drain(
        PostLifecycleConsumer(
            redis_client=real_redis,
            feature_store=store,
            projector=projector,
            consumer="gathering-flywheel-api-test-neg",
        )
    )

    assert _experienced_reasons(reader, subject_a, subject_b) == []
    assert _experienced_reasons(reader, subject_b, subject_a) == []


def _emit_wishlist_add(
    real_redis,
    *,
    persona_id: str,
    entity_id: str,
) -> None:
    client_event_id = f"wishlist-{persona_id}-{entity_id}"
    event_id = hashlib.sha256(
        f"ContentBehaviorRecorded:{persona_id}:{client_event_id}".encode()
    ).hexdigest()
    occurred_at = "2026-08-09T10:00:00+00:00"
    real_redis.xadd(
        CONTENT_BEHAVIOR_STREAM,
        {
            "eventId": event_id,
            "eventName": "ContentBehaviorRecorded",
            "subjectId": persona_id,
            "targetId": entity_id,
            "occurredAt": occurred_at,
            "payload": json.dumps(
                {
                    "clientEventId": client_event_id,
                    "personaId": persona_id,
                    "contentId": entity_id,
                    "objectId": entity_id,
                    "objectKind": "homepage",
                    "displayName": "黄龙雪山",
                    "action": "wishlist_add",
                    "entityRefs": [entity_id],
                    "occurredAt": occurred_at,
                }
            ),
        },
    )


def test_co_wishlisted_intent_stream_requires_both_sides(
    mongo_database,
    real_redis,
) -> None:
    """九步旅程第 1-2 步（意图环）：双方想去同一实体 → coWishlistedEntity；
    单方想去不产出（诚实红线）。"""
    store, projector, reader = _build_pipeline(mongo_database)
    subject_a = "persona-wish-stream-a"
    subject_b = "persona-wish-stream-b"
    subject_solo = "persona-wish-stream-solo"
    entity = "homepage-wish-stream-1"

    _emit_wishlist_add(real_redis, persona_id=subject_a, entity_id=entity)
    _emit_wishlist_add(real_redis, persona_id=subject_b, entity_id=entity)
    _emit_wishlist_add(
        real_redis, persona_id=subject_solo, entity_id="homepage-wish-stream-solo"
    )
    _drain(
        ContentBehaviorConsumer(
            redis_client=real_redis,
            feature_store=store,
            projector=projector,
            consumer="wishlist-intent-api-test",
        )
    )

    snapshot = reader.list_object_intersections(
        subject_id=subject_a,
        object_type="person",
        object_id=subject_b,
    )
    matched = [
        reason
        for reason in snapshot.reasons
        if reason["kind"] == "coWishlistedEntity"
    ]
    assert len(matched) == 1
    assert matched[0]["intersectionClass"] == "fact"

    solo_snapshot = reader.list_object_intersections(
        subject_id=subject_a,
        object_type="person",
        object_id=subject_solo,
    )
    assert [
        reason
        for reason in solo_snapshot.reasons
        if reason["kind"] == "coWishlistedEntity"
    ] == []


def test_gathering_social_proof_counts_two_honest_tiers(
    mongo_database,
    real_redis,
) -> None:
    """四锚点两级诚实计数：发起→成形→经历逐级收紧；无内容行动不进经历级。"""
    store, projector, reader = _build_pipeline(mongo_database)
    organizer = "persona-proof-organizer"
    seed_post = "post-proof-seed"
    seed_entity = "homepage-proof-entity"
    source_refs = [
        {"objectKind": "content", "objectId": seed_post},
        {"objectKind": "place", "objectId": seed_entity},
    ]
    # 行动一：成形且双方回顾（经历级）。行动二：成形但无内容（对照组）。
    experienced_gathering = "gathering_proof_experienced"
    formed_only_gathering = "gathering_proof_formed_only"
    for gathering_id in (experienced_gathering, formed_only_gathering):
        _emit_publication(
            real_redis,
            gathering_id=gathering_id,
            organizer_id=organizer,
            source_refs=source_refs,
        )
    _drain(
        GatheringPublicationConsumer(
            redis_client=real_redis,
            feature_store=store,
            projector=projector,
            consumer="gathering-social-proof-api-test",
        )
    )
    participants = ("persona-proof-a", "persona-proof-b")
    for gathering_id in (experienced_gathering, formed_only_gathering):
        for persona in participants:
            _emit_participation(
                real_redis, gathering_id=gathering_id, persona_id=persona
            )
    _drain(
        GatheringParticipationConsumer(
            redis_client=real_redis,
            feature_store=store,
            projector=projector,
            consumer="gathering-social-proof-api-test",
        )
    )
    # 种草内容作者映射（创作者锚点）+ 仅行动一的双方回顾。
    _emit_recap_post(
        real_redis,
        post_id=seed_post,
        author_id="persona-proof-creator",
        gathering_id="",
    )
    for index, persona in enumerate(participants):
        _emit_recap_post(
            real_redis,
            post_id=f"post-proof-recap-{index}",
            author_id=persona,
            gathering_id=experienced_gathering,
        )
    _drain(
        PostLifecycleConsumer(
            redis_client=real_redis,
            feature_store=store,
            projector=projector,
            consumer="gathering-social-proof-api-test",
        )
    )

    organizer_counts = reader.get_gathering_social_proof(
        anchor_kind="organizer", object_id=organizer
    )
    assert organizer_counts == {
        "publishedCount": 2,
        "formedCount": 2,
        "experiencedCount": 1,
    }
    entity_counts = reader.get_gathering_social_proof(
        anchor_kind="entity", object_id=seed_entity
    )
    assert entity_counts["formedCount"] == 2
    assert entity_counts["experiencedCount"] == 1
    content_counts = reader.get_gathering_social_proof(
        anchor_kind="content", object_id=seed_post
    )
    assert content_counts["experiencedCount"] == 1
    creator_counts = reader.get_gathering_social_proof(
        anchor_kind="creator", object_id="persona-proof-creator"
    )
    assert creator_counts == {
        "publishedCount": 2,
        "formedCount": 2,
        "experiencedCount": 1,
    }
    # 无关锚点诚实归零。
    unrelated = reader.get_gathering_social_proof(
        anchor_kind="entity", object_id="homepage-unrelated"
    )
    assert unrelated == {
        "publishedCount": 0,
        "formedCount": 0,
        "experiencedCount": 0,
    }


def _facilitation_events(real_redis) -> list[dict[str, str]]:
    entries = real_redis.xrange(INTERSECTION_EVENT_STREAM, "-", "+")
    decoded = []
    for _, values in entries:
        decoded.append(
            {
                (k.decode() if isinstance(k, bytes) else k): (
                    v.decode() if isinstance(v, bytes) else v
                )
                for k, v in values.items()
            }
        )
    return decoded


def test_facilitation_event_fires_once_on_experienced_transition(
    mongo_database,
    real_redis,
) -> None:
    """创作者促成事件：经历级首次达成时按种草内容作者各发布一次；
    第三个回顾不重复发布；溯源链断（无 content sourceRef）永不发布。"""
    real_redis.delete(INTERSECTION_EVENT_STREAM)
    publisher = RedisIntersectionFacilitationEventPublisher(real_redis)
    store, projector, _reader = _build_pipeline(mongo_database, publisher)
    seed_post = "post-facilitation-seed"
    creator = "persona-facilitation-creator"
    organizer = "persona-facilitation-organizer"
    gathering = "gathering_facilitation_pos"
    orphan_gathering = "gathering_facilitation_no_source"

    _emit_publication(
        real_redis,
        gathering_id=gathering,
        organizer_id=organizer,
        source_refs=[{"objectKind": "content", "objectId": seed_post}],
    )
    # 溯源链断对照组：无 sourceRefs。
    _emit_publication(
        real_redis,
        gathering_id=orphan_gathering,
        organizer_id=organizer,
        source_refs=[],
    )
    _drain(
        GatheringPublicationConsumer(
            redis_client=real_redis,
            feature_store=store,
            projector=projector,
            consumer="facilitation-api-test",
        )
    )
    participants = ("persona-fac-a", "persona-fac-b", "persona-fac-c")
    for gathering_id in (gathering, orphan_gathering):
        for persona in participants:
            _emit_participation(
                real_redis, gathering_id=gathering_id, persona_id=persona
            )
    _drain(
        GatheringParticipationConsumer(
            redis_client=real_redis,
            feature_store=store,
            projector=projector,
            consumer="facilitation-api-test",
        )
    )
    # 种草作者映射 + 双方回顾（两个 gathering 都发回顾，但只有溯源完整的发事件）。
    _emit_recap_post(
        real_redis, post_id=seed_post, author_id=creator, gathering_id=""
    )
    for index, persona in enumerate(participants[:2]):
        for gathering_id in (gathering, orphan_gathering):
            _emit_recap_post(
                real_redis,
                post_id=f"post-fac-recap-{gathering_id}-{index}",
                author_id=persona,
                gathering_id=gathering_id,
            )
    _drain(
        PostLifecycleConsumer(
            redis_client=real_redis,
            feature_store=store,
            projector=projector,
            consumer="facilitation-api-test",
        )
    )

    events = _facilitation_events(real_redis)
    assert len(events) == 1
    event = events[0]
    assert event["eventType"] == "IntersectionFacilitationRecorded"
    payload = json.loads(event["payload"])
    assert payload["gatheringId"] == gathering
    assert payload["creatorPersonaId"] == creator
    assert payload["seedPostId"] == seed_post
    receipt = mongo_database["recommendation_intersection_facilitations"].find_one(
        {"_id": gathering}
    )
    assert receipt is not None
    assert receipt["occurredAt"].replace(tzinfo=timezone.utc) == datetime(
        2026, 8, 10, 18, 0, tzinfo=timezone.utc
    )
    assert "notifiedAt" not in receipt

    # 第三名参与者补充回顾：经历级已达成过，占位收据幂等，不再发布。
    _emit_recap_post(
        real_redis,
        post_id="post-fac-recap-third",
        author_id=participants[2],
        gathering_id=gathering,
    )
    _drain(
        PostLifecycleConsumer(
            redis_client=real_redis,
            feature_store=store,
            projector=projector,
            consumer="facilitation-api-test",
        )
    )
    assert len(_facilitation_events(real_redis)) == 1


def _funnel(reader, **filters):
    return reader.get_flywheel_funnel(
        window_from=datetime(2026, 8, 1, tzinfo=timezone.utc),
        window_to=datetime(2026, 8, 31, tzinfo=timezone.utc),
        **filters,
    )


def test_flywheel_funnel_multi_dimension_honest_counts(
    mongo_database,
    real_redis,
) -> None:
    """北极星三比例多维诚实快照：空库全零；九步数据后分子分母精确；
    duo/group 与 tagRef 切片差异；时间窗外排除；单侧数据不虚增。"""
    real_redis.delete(INTERSECTION_EVENT_STREAM)
    publisher = RedisIntersectionFacilitationEventPublisher(real_redis)
    store, projector, reader = _build_pipeline(mongo_database, publisher)

    # 0. 空库全零（诚实基线）。
    empty = _funnel(reader)
    assert empty == {
        "wishlistedPersonaCount": 0,
        "wishlistToJoinedCount": 0,
        "publishedCount": 0,
        "formedCount": 0,
        "experiencedCount": 0,
        "facilitationNotifiedCount": 0,
        "creatorRepublishedCount": 0,
        "truncated": False,
    }

    entity = "homepage-funnel-lake"
    seed_post = "post-funnel-seed"
    creator = "persona-funnel-creator"
    organizer = "persona-funnel-organizer"
    joiner = "persona-funnel-joiner"
    dreamer = "persona-funnel-dreamer"  # 只想去、从未参加（分母不虚增分子）。

    # 想去意图（窗口内）：joiner 与 dreamer 都想去该实体。
    _emit_wishlist_add(real_redis, persona_id=joiner, entity_id=entity)
    _emit_wishlist_add(real_redis, persona_id=dreamer, entity_id=entity)
    _drain(
        ContentBehaviorConsumer(
            redis_client=real_redis,
            feature_store=store,
            projector=projector,
            consumer="funnel-api-test",
        )
    )

    # 种草内容（带类目标签）先于行动发布，供 tagRef 切片与促成链。
    _emit_recap_post(
        real_redis,
        post_id=seed_post,
        author_id=creator,
        gathering_id="",
        tag_refs=["hiking"],
        occurred_at="2026-08-09T09:00:00Z",
    )

    # 行动一（group·成形+经历）：来源=实体+种草内容；行动二（duo·成形无内容）。
    group_id = "gathering_funnel_group"
    duo_id = "gathering_funnel_duo"
    _emit_publication(
        real_redis,
        gathering_id=group_id,
        organizer_id=organizer,
        source_refs=[
            {"objectKind": "place", "objectId": entity},
            {"objectKind": "content", "objectId": seed_post},
        ],
        max_participants=4,
        admission_policy="approval",
    )
    _emit_publication(
        real_redis,
        gathering_id=duo_id,
        organizer_id=organizer,
        source_refs=[{"objectKind": "place", "objectId": entity}],
        max_participants=2,
        admission_policy="invite_only",
    )
    _drain(
        GatheringPublicationConsumer(
            redis_client=real_redis,
            feature_store=store,
            projector=projector,
            consumer="funnel-api-test",
        )
    )
    for gathering_id, personas in (
        (group_id, (organizer, joiner)),
        (duo_id, (organizer, joiner)),
    ):
        for persona in personas:
            _emit_participation(
                real_redis, gathering_id=gathering_id, persona_id=persona
            )
    _drain(
        GatheringParticipationConsumer(
            redis_client=real_redis,
            feature_store=store,
            projector=projector,
            consumer="funnel-api-test",
        )
    )
    # 仅行动一双方回顾（经历级 + 促成事件）；促成后创作者续发一条新内容。
    for index, persona in enumerate((organizer, joiner)):
        _emit_recap_post(
            real_redis,
            post_id=f"post-funnel-recap-{index}",
            author_id=persona,
            gathering_id=group_id,
            occurred_at="2026-08-10T18:00:00Z",
        )
    _drain(
        PostLifecycleConsumer(
            redis_client=real_redis,
            feature_store=store,
            projector=projector,
            consumer="funnel-api-test",
        )
    )
    _emit_recap_post(
        real_redis,
        post_id="post-funnel-followup",
        author_id=creator,
        gathering_id="",
        tag_refs=["hiking"],
        occurred_at="2026-08-12T09:00:00Z",
    )
    _drain(
        PostLifecycleConsumer(
            redis_client=real_redis,
            feature_store=store,
            projector=projector,
            consumer="funnel-api-test",
        )
    )

    # 全窗口无过滤：分子分母精确。
    snapshot = _funnel(reader)
    assert snapshot["wishlistedPersonaCount"] == 2
    assert snapshot["wishlistToJoinedCount"] == 1  # dreamer 不虚增
    assert snapshot["publishedCount"] == 2
    assert snapshot["formedCount"] == 2
    assert snapshot["experiencedCount"] == 1  # duo 无内容不进经历级
    assert snapshot["facilitationNotifiedCount"] == 1
    assert snapshot["creatorRepublishedCount"] == 1
    assert snapshot["truncated"] is False

    # 活动特征切片：duo 只见成形无经历；group 只见经历行动。
    duo_slice = _funnel(reader, capacity_tier="duo")
    assert duo_slice["publishedCount"] == 1
    assert duo_slice["formedCount"] == 1
    assert duo_slice["experiencedCount"] == 0
    group_slice = _funnel(reader, capacity_tier="group")
    assert group_slice["publishedCount"] == 1
    assert group_slice["experiencedCount"] == 1

    # 类目切片：hiking 标签只命中带种草内容来源的行动一。
    tag_slice = _funnel(reader, tag_ref="hiking")
    assert tag_slice["publishedCount"] == 1
    assert tag_slice["experiencedCount"] == 1
    missing_tag = _funnel(reader, tag_ref="cycling")
    assert missing_tag["publishedCount"] == 0

    # 来源对象切片与无关来源诚实归零。
    entity_slice = _funnel(reader, source_object_id=entity)
    assert entity_slice["publishedCount"] == 2
    unrelated = _funnel(reader, source_object_id="homepage-unrelated")
    assert unrelated["publishedCount"] == 0
    assert unrelated["wishlistedPersonaCount"] == 0

    # 时间窗外排除：窗口移到 9 月后全零。
    from datetime import datetime, timezone

    later = reader.get_flywheel_funnel(
        window_from=datetime(2026, 9, 1, tzinfo=timezone.utc),
        window_to=datetime(2026, 9, 30, tzinfo=timezone.utc),
    )
    assert later["publishedCount"] == 0
    assert later["wishlistedPersonaCount"] == 0
