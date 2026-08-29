"""Dependency fault injection for RankedRecommendationWindow over real transport.

三个真实故障场景（对齐 streaming-feed-performance OPEN-004 的 fault
injection 要求，feed-fallback-degrade 的失败语义）：

  1. Redis 窗口存储不可达（连接拒绝）→ CreateRankedRecommendationWindow 在
     有界时延内返回 canonical RECOMMENDATION.SYSTEM.ranked_window_failed，
     不无限等待、不伪造成功窗口。
  2. Mongo 存储不可达（server selection 超时）→ 同样的 canonical failure，
     时延受 serverSelectionTimeoutMS 约束。
  3. model 实验桶 100% 且无可用模型 → 打分降级到确定性 rule scorer，
     请求成功且窗口如实落 rule 桶（不失败、不空窗、不声称模型参与）。

故障是真实网络层故障（未监听端口），不是进程内替身。
"""
# spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-004
# spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/feed-fallback-degrade/spec.md#gwt-001
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import socket
import threading
import time

from fastapi import FastAPI
import httpx
from pymongo import MongoClient
from redis import Redis
import uvicorn

from tests.support.service_token import (
    configure_test_auth_environment,
    service_token,
)

configure_test_auth_environment()

from api.score import get_scoring_facade  # noqa: E402
from generated.recommendation.ranked_recommendation_window.api.operations import (  # noqa: E402
    CREATE_RANKED_RECOMMENDATION_WINDOW_PATH,
)
from internal.recommendation.ranked_recommendation_window.adapters.inbound.http.router import (  # noqa: E402
    build_router,
)
from internal.recommendation.ranked_recommendation_window.application.facade import (  # noqa: E402
    Facade,
)
from internal.recommendation.ranked_recommendation_window.domain.discovery_tuning import (  # noqa: E402
    DiscoveryRankingTuning,
)
from internal.recommendation.ranked_recommendation_window.domain.experiment_policy import (  # noqa: E402
    EXPERIMENT_ID,
    ExperimentAssignments,
    ExperimentPolicy,
    PolicyVariant,
)
from internal.recommendation.ranked_recommendation_window.infrastructure.experiment_assignment_publisher import (  # noqa: E402
    RedisExperimentAssignmentPublisher,
)
from internal.recommendation.ranked_recommendation_window.infrastructure.mongo_ranker import (  # noqa: E402
    MongoCandidateRanker,
)
from internal.recommendation.ranked_recommendation_window.infrastructure.redis_store import (  # noqa: E402
    RedisWindowStore,
)
from internal.recommendation.recommendation_candidate_index_view.application.projector import (  # noqa: E402
    CandidateLifecycleSnapshot,
)
from internal.recommendation.recommendation_candidate_index_view.infrastructure.mongo_store import (  # noqa: E402
    MongoCandidateIndexStore,
)
from internal.recommendation.recommendation_exposure_fact.application.appender import (  # noqa: E402
    canonical_snapshot_digest,
)
from internal.recommendation.recommendation_feature_profile_view.infrastructure.mongo_store import (  # noqa: E402
    MongoFeatureProfileStore,
)
from internal.recommendation.recommendation_subject_closure_fact.infrastructure.mongo_store import (  # noqa: E402
    MongoSubjectClosureStore,
)
from security.service_authorization import ServiceTokenVerifier  # noqa: E402
from tests.support.recommendation_mongo import mongo_client, mongo_database  # noqa: E402,F401
from tests.support.recommendation_redis import real_redis  # noqa: E402,F401

FAILED_CODE = "RECOMMENDATION.SYSTEM.ranked_window_failed"
SUBJECT_ID = "persona-fault-injection"
FAULT_BUDGET_SECONDS = 5.0


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _policy(*, model_weight: int, rule_weight: int) -> ExperimentPolicy:
    updated_at = datetime.now(timezone.utc)
    return ExperimentPolicy(
        experiment_id=EXPERIMENT_ID,
        revision=1,
        status="running",
        variants=(
            PolicyVariant("model", model_weight),
            PolicyVariant("rule", rule_weight),
        ),
        starts_at=updated_at - timedelta(minutes=5),
        ends_at=None,
        updated_at=updated_at,
        digest="",
    )


def _seed_candidates(store: MongoCandidateIndexStore, count: int = 3) -> None:
    published_at = datetime.now(timezone.utc) - timedelta(hours=1)
    for index in range(count):
        assert store.apply_source_event(
            event_id=f"fault-injection-post-published-{index}",
            snapshot=CandidateLifecycleSnapshot(
                scenario="content_feed",
                content_id=f"post-fault-{index}",
                content_type="article",
                author_id=f"persona-author-{index}",
                tag_refs=(),
                entity_refs=(),
                published_at=published_at,
                content_vertical=None,
                entity_tag_ids=(),
                source_sequence=index + 1,
                updated_at=published_at + timedelta(seconds=index),
            ),
        )


class _Server:
    def __init__(self, facade: Facade) -> None:
        app = FastAPI()
        app.include_router(
            build_router(
                facade_provider=lambda _request: facade,
                token_verifier=ServiceTokenVerifier.from_env(),
            )
        )
        self._server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", lifespan="off")
        )
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        deadline = time.monotonic() + 15.0
        while not self._server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("uvicorn test server failed to start in time")
            time.sleep(0.01)
        port = self._server.servers[0].sockets[0].getsockname()[1]
        self.client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30.0)

    def close(self) -> None:
        self.client.close()
        self._server.should_exit = True
        self._thread.join(timeout=5.0)


def _headers(idempotency_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {service_token(scopes=['recommendation.ranked_page'])}",
        "Idempotency-Key": idempotency_key,
    }


def _facade(
    *,
    candidates,
    features,
    closures,
    window_store,
    assignment_redis,
    policy: ExperimentPolicy,
) -> Facade:
    assignments = ExperimentAssignments(
        RedisExperimentAssignmentPublisher(assignment_redis)
    )
    assignments.apply_policy(policy)
    return Facade(
        store=window_store,
        ranker=MongoCandidateRanker(
            candidates=candidates,
            feature_profiles=features,
            scoring=get_scoring_facade(),
            experiments=assignments,
            snapshot_digester=canonical_snapshot_digest,
            tuning=DiscoveryRankingTuning.neutral(),
        ),
        subject_closures=closures,
        exclusion_profiles=features,
    )


def test_redis_window_store_unreachable_fails_closed_within_budget(
    mongo_database,
    real_redis,
) -> None:
    candidates = MongoCandidateIndexStore(mongo_database)
    features = MongoFeatureProfileStore(mongo_database)
    closures = MongoSubjectClosureStore(mongo_database)
    for store in (candidates, features, closures):
        store.ensure_indexes()
    _seed_candidates(candidates)

    dead_redis = Redis(
        host="127.0.0.1",
        port=_free_port(),
        socket_connect_timeout=0.5,
        socket_timeout=0.5,
    )
    server = _Server(
        _facade(
            candidates=candidates,
            features=features,
            closures=closures,
            window_store=RedisWindowStore(dead_redis),
            assignment_redis=real_redis,
            policy=_policy(model_weight=0, rule_weight=10_000),
        )
    )
    try:
        started = time.monotonic()
        response = server.client.post(
            CREATE_RANKED_RECOMMENDATION_WINDOW_PATH,
            headers=_headers("fault-redis-001"),
            json={"subjectId": SUBJECT_ID, "scenario": "content_feed", "limit": 2},
        )
        elapsed = time.monotonic() - started
        assert response.status_code == 500
        assert response.json()["detail"]["code"] == FAILED_CODE
        assert elapsed < FAULT_BUDGET_SECONDS
    finally:
        server.close()


def test_mongo_unreachable_fails_closed_within_budget(real_redis) -> None:
    dead_mongo = MongoClient(
        f"mongodb://127.0.0.1:{_free_port()}/",
        serverSelectionTimeoutMS=300,
        connectTimeoutMS=300,
        tz_aware=True,
    )
    dead_database = dead_mongo["quwoquan_recommendation_fault"]
    server = _Server(
        _facade(
            candidates=MongoCandidateIndexStore(dead_database),
            features=MongoFeatureProfileStore(dead_database),
            closures=MongoSubjectClosureStore(dead_database),
            window_store=RedisWindowStore(real_redis),
            assignment_redis=real_redis,
            policy=_policy(model_weight=0, rule_weight=10_000),
        )
    )
    try:
        started = time.monotonic()
        response = server.client.post(
            CREATE_RANKED_RECOMMENDATION_WINDOW_PATH,
            headers=_headers("fault-mongo-001"),
            json={"subjectId": SUBJECT_ID, "scenario": "content_feed", "limit": 2},
        )
        elapsed = time.monotonic() - started
        assert response.status_code == 500
        assert response.json()["detail"]["code"] == FAILED_CODE
        assert elapsed < FAULT_BUDGET_SECONDS
    finally:
        server.close()


def test_model_bucket_without_artifact_degrades_to_rule_over_real_transport(
    mongo_database,
    real_redis,
) -> None:
    candidates = MongoCandidateIndexStore(mongo_database)
    features = MongoFeatureProfileStore(mongo_database)
    closures = MongoSubjectClosureStore(mongo_database)
    for store in (candidates, features, closures):
        store.ensure_indexes()
    _seed_candidates(candidates)

    server = _Server(
        _facade(
            candidates=candidates,
            features=features,
            closures=closures,
            window_store=RedisWindowStore(real_redis),
            assignment_redis=real_redis,
            policy=_policy(model_weight=10_000, rule_weight=0),
        )
    )
    try:
        response = server.client.post(
            CREATE_RANKED_RECOMMENDATION_WINDOW_PATH,
            headers=_headers("fault-model-001"),
            json={"subjectId": SUBJECT_ID, "scenario": "content_feed", "limit": 3},
        )
        assert response.status_code == 200
        payload = response.json()
        # 策略分配仍是 model；无可用模型时实际执行轨道如实降级 rule。
        assert payload["experimentBucket"] == "model"
        assert payload["modelBucket"] == "rule"
        assert payload["modelReleaseId"] is None
        assert payload["items"], "degraded ranking must still deliver candidates"
    finally:
        server.close()
