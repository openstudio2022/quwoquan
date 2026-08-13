"""Multi-lane bounded recall over the real Mongo candidate projection.

content_feed 主场景的多路有界召回合同：
  - fresh 路（updatedAt DESC）与 hot 路（likeCount DESC）各自有界、
    合并按先出现去重，总量不超过 limit；
  - hot 路能把高互动的老内容带回候选集（单路时间扫描会漏掉）；
  - recallPath 如实标注每路来源（explore_recall / hot_recall /
    collaborative_recall / following_recall）；
  - 协同点查路只返回仍可推荐的候选（受 scenario 过滤器约束）。
"""
# spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/collaborative-recall/spec.md#gwt-001
# spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/quality-score-cold-start/spec.md#gwt-001
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from internal.recommendation.recommendation_candidate_index_view.application.projector import (
    CandidateLifecycleSnapshot,
)
from internal.recommendation.recommendation_candidate_index_view.infrastructure.mongo_store import (
    MongoCandidateIndexStore,
)
from tests.support.recommendation_mongo import mongo_client, mongo_database  # noqa: F401

NOW = datetime.now(timezone.utc)


def _seed(
    store: MongoCandidateIndexStore,
    *,
    content_id: str,
    age_hours: float,
    like_count: int = 0,
    sequence: int,
) -> None:
    published_at = NOW - timedelta(hours=age_hours)
    assert store.apply_source_event(
        event_id=f"multilane-{content_id}",
        snapshot=CandidateLifecycleSnapshot(
            scenario="content_feed",
            content_id=content_id,
            content_type="article",
            author_id=f"author-{content_id}",
            tag_refs=(),
            entity_refs=(),
            published_at=published_at,
            content_vertical=None,
            entity_tag_ids=(),
            source_sequence=sequence,
            updated_at=published_at,
        ),
    )
    if like_count:
        store._candidates.update_one(  # noqa: SLF001 - 直接写互动量做测试前置
            {"scenario": "content_feed", "contentId": content_id},
            {"$set": {"likeCount": like_count}},
        )


def test_hot_lane_recalls_high_engagement_content_beyond_fresh_window(
    mongo_database,
) -> None:
    store = MongoCandidateIndexStore(mongo_database)
    store.ensure_indexes()
    # 10 条新内容（零互动）+ 1 条 100 小时前的高互动老内容。
    for index in range(10):
        _seed(store, content_id=f"fresh-{index}", age_hours=float(index), sequence=index + 1)
    _seed(store, content_id="hot-old", age_hours=100.0, like_count=500, sequence=99)

    # limit=10 时 fresh 路只装 6 条（3/5），hot 路（1/4 → 2 条）必须把
    # hot-old 带回（likeCount 最高）；单路时间扫描下它会被挤出。
    documents = store.list_for_ranking(scenario="content_feed", limit=10)
    by_id = {str(d["contentId"]): d for d in documents}
    assert "hot-old" in by_id
    assert by_id["hot-old"]["recallPath"] == "hot_recall"
    assert len(documents) <= 10
    # 各路去重：同一 contentId 不重复出现。
    assert len(by_id) == len(documents)
    fresh_paths = {
        d["recallPath"] for d in documents if str(d["contentId"]).startswith("fresh-")
    }
    assert "explore_recall" in fresh_paths


def test_collaborative_point_lookup_respects_scenario_filter(mongo_database) -> None:
    store = MongoCandidateIndexStore(mongo_database)
    store.ensure_indexes()
    _seed(store, content_id="collab-a", age_hours=2.0, sequence=201)
    _seed(store, content_id="collab-b", age_hours=3.0, sequence=202)

    documents = store.list_for_ranking_by_content_ids(
        scenario="content_feed",
        content_ids=("collab-a", "collab-b", "missing-content"),
    )
    ids = {str(d["contentId"]) for d in documents}
    assert ids == {"collab-a", "collab-b"}
    assert all(d["recallPath"] == "collaborative_recall" for d in documents)

    assert (
        store.list_for_ranking_by_content_ids(
            scenario="content_feed",
            content_ids=(),
        )
        == []
    )


def test_multilane_merge_never_exceeds_limit(mongo_database) -> None:
    store = MongoCandidateIndexStore(mongo_database)
    store.ensure_indexes()
    for index in range(30):
        _seed(
            store,
            content_id=f"cap-{index}",
            age_hours=float(index),
            like_count=index * 3,
            sequence=300 + index,
        )
    documents = store.list_for_ranking(scenario="content_feed", limit=12)
    assert len(documents) <= 12
    assert len({str(d["contentId"]) for d in documents}) == len(documents)
