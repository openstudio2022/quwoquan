"""搜推联动端到端：真实 Redis stream + 真实 Mongo 特征投影。

对齐 search-service `searchsignals.StreamPublisher` 的 wire 形状发布信号，
经 SearchSignalConsumer 消费后断言 FeatureProfile 的 searchTermAffinities
可被打分读取、signalId 幂等、click 只推进收据。
"""
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-003
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from internal.recommendation.recommendation_feature_profile_view.adapters.inbound.stream.search_signal_consumer import (
    SEARCH_SIGNAL_STREAM,
    SearchSignalConsumer,
)
from internal.recommendation.recommendation_feature_profile_view.application.projector import (
    Projector,
)
from internal.recommendation.recommendation_feature_profile_view.infrastructure.mongo_store import (
    MongoFeatureProfileStore,
)
from internal.recommendation.recommendation_subject_closure_fact.infrastructure.mongo_store import (
    MongoSubjectClosureStore,
)
from tests.support.recommendation_mongo import mongo_client, mongo_database  # noqa: F401
from tests.support.recommendation_redis import real_redis  # noqa: F401

SUBJECT = "persona-search-signal"


def _publish(redis, *, signal_id: str, signal_type: str = "query", query: str = "成都 周末 徒步") -> None:
    # 字段形状与 search-service searchsignals.StreamValues 完全一致。
    redis.xadd(
        SEARCH_SIGNAL_STREAM,
        {
            "eventType": "SearchRecommendationSignalPublished",
            "signalId": signal_id,
            "signalType": signal_type,
            "searchRequestId": f"req-{signal_id}",
            "sessionId": "session-001",
            "userId": SUBJECT,
            "normalizedQuery": query if signal_type == "query" else "",
            "relatedTerms": '["成都","徒步"]' if signal_type == "query" else "[]",
            "engagedObjectIds": "[]" if signal_type == "query" else '["posts/a/1"]',
            "experimentBucket": "",
            "resultCount": "12",
            "createdAt": datetime.now(timezone.utc).isoformat(),
        },
    )


@pytest.fixture
def runtime(mongo_database, real_redis):
    feature_store = MongoFeatureProfileStore(mongo_database)
    closures = MongoSubjectClosureStore(mongo_database)
    for store in (feature_store, closures):
        store.ensure_indexes()
    consumer = SearchSignalConsumer(
        redis_client=real_redis,
        feature_store=feature_store,
        feature_projector=Projector(feature_store),
        subject_closures=closures,
        consumer="search-signal-api-test",
    )
    return real_redis, feature_store, consumer


def test_query_signal_projects_bounded_term_affinities(runtime) -> None:
    redis, feature_store, consumer = runtime
    _publish(redis, signal_id="signal-api-001")
    assert consumer.process_once() == 1

    profile = feature_store.read_for_scoring(SUBJECT)
    affinities = profile["searchTermAffinities"]
    assert affinities["成都 周末 徒步"] == pytest.approx(1.0)
    assert affinities["成都"] == pytest.approx(1.0)
    assert affinities["徒步"] == pytest.approx(1.0)
    checkpoint = profile["checkpoint"]
    assert checkpoint >= 1

    # signalId 幂等：同一信号重复投递不再改变 profile。
    _publish(redis, signal_id="signal-api-001")
    consumer.process_once()
    replayed = feature_store.read_for_scoring(SUBJECT)
    assert replayed["checkpoint"] == checkpoint
    assert replayed["searchTermAffinities"] == affinities


def test_repeated_terms_accumulate_weight(runtime) -> None:
    redis, feature_store, consumer = runtime
    _publish(redis, signal_id="signal-api-010", query="九寨沟")
    consumer.process_once()
    _publish(redis, signal_id="signal-api-011", query="九寨沟")
    consumer.process_once()

    affinities = feature_store.read_for_scoring(SUBJECT)["searchTermAffinities"]
    assert affinities["九寨沟"] == pytest.approx(2.0)


def test_click_signal_advances_receipt_without_term_projection(runtime) -> None:
    redis, feature_store, consumer = runtime
    before = feature_store.read_for_scoring(SUBJECT)
    _publish(redis, signal_id="signal-api-020", signal_type="click")
    assert consumer.process_once() == 1

    after = feature_store.read_for_scoring(SUBJECT)
    assert after["searchTermAffinities"] == before["searchTermAffinities"]
    assert after["checkpoint"] == before["checkpoint"] + 1
