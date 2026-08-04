"""recommendation-service composition root."""

from collections.abc import Mapping
from contextlib import asynccontextmanager
import os
import time
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from prometheus_client import Counter, Histogram, make_asgi_app
from pymongo import MongoClient
from redis import Redis
from redis.cluster import RedisCluster

from api.capacity import refresh_capacity_metrics
from api.metrics import refresh_rec_model_loaded_gauges
from runtime_contract import bootstrap_runtime_contract_or_die


runtime_config = bootstrap_runtime_contract_or_die()

from api.score import get_scoring_facade, router as score_router  # noqa: E402
from internal.recommendation.recommendation_candidate_index_view.adapters.inbound.stream.post_lifecycle_consumer import (  # noqa: E402
    PostLifecycleConsumer as CandidatePostLifecycleConsumer,
)
from internal.recommendation.recommendation_candidate_index_view.adapters.inbound.stream.persona_relationship_consumer import (  # noqa: E402
    PersonaRelationshipConsumer as CandidatePersonaRelationshipConsumer,
)
from internal.recommendation.recommendation_candidate_index_view.adapters.inbound.stream.premium_pool_consumer import (  # noqa: E402
    PremiumPoolConsumer,
)
from internal.recommendation.recommendation_candidate_index_view.adapters.inbound.stream.user_account_restriction_consumer import (  # noqa: E402
    UserAccountRestrictionConsumer,
)
from internal.recommendation.recommendation_candidate_index_view.infrastructure.mongo_store import (  # noqa: E402
    MongoCandidateIndexStore,
)
from internal.recommendation.recommendation_feature_profile_view.infrastructure.mongo_store import (  # noqa: E402
    MongoFeatureProfileStore,
)
from internal.recommendation.recommendation_feature_profile_view.application.author_impact_reader import (  # noqa: E402
    Reader as AuthorImpactReader,
)
from internal.recommendation.recommendation_feature_profile_view.application.intersection_reader import (  # noqa: E402
    Reader as IntersectionReader,
)
from internal.recommendation.recommendation_feature_profile_view.application.intersection_projector import (  # noqa: E402
    Projector as IntersectionProjector,
)
from internal.recommendation.recommendation_feature_profile_view.application.intersection_materializer import (  # noqa: E402
    Materializer as IntersectionMaterializer,
)
from internal.recommendation.recommendation_feature_profile_view.application.intersection_event_projector import (  # noqa: E402
    IntersectionEventProjector,
)
from internal.recommendation.recommendation_feature_profile_view.adapters.inbound.http.router import (  # noqa: E402
    build_router as build_feature_profile_router,
)
from internal.recommendation.recommendation_feature_profile_view.application.projector import (  # noqa: E402
    Projector as FeatureProfileProjector,
)
from internal.recommendation.recommendation_feature_profile_view.adapters.inbound.fact_projector import (  # noqa: E402
    FactProjectionAdapter,
)
from internal.recommendation.recommendation_feature_profile_view.adapters.inbound.stream.tag_feedback_consumer import (  # noqa: E402
    TagFeedbackConsumer,
)
from internal.recommendation.recommendation_feature_profile_view.adapters.inbound.stream.persona_relationship_consumer import (  # noqa: E402
    PersonaRelationshipConsumer as FeaturePersonaRelationshipConsumer,
)
from internal.recommendation.recommendation_feature_profile_view.adapters.inbound.stream.circle_membership_consumer import (  # noqa: E402
    CircleMembershipConsumer as FeatureCircleMembershipConsumer,
)
from internal.recommendation.recommendation_feature_profile_view.adapters.inbound.stream.content_behavior_consumer import (  # noqa: E402
    ContentBehaviorConsumer as FeatureContentBehaviorConsumer,
)
from internal.recommendation.recommendation_feature_profile_view.adapters.inbound.stream.post_lifecycle_consumer import (  # noqa: E402
    PostLifecycleConsumer as FeaturePostLifecycleConsumer,
)
from internal.recommendation.recommendation_exposure_fact.infrastructure.mongo_store import (  # noqa: E402
    MongoExposureFactStore,
)
from internal.recommendation.recommendation_exposure_fact.adapters.inbound.stream.feed_page_delivered_consumer import (  # noqa: E402
    FeedPageDeliveredConsumer,
)
from internal.recommendation.recommendation_exposure_fact.application.appender import (  # noqa: E402
    canonical_snapshot_digest,
)
from internal.recommendation.recommendation_feedback_fact.adapters.inbound.stream.content_behavior_consumer import (  # noqa: E402
    ContentBehaviorConsumer as FeedbackContentBehaviorConsumer,
)
from internal.recommendation.recommendation_feedback_fact.infrastructure.mongo_store import (  # noqa: E402
    MongoRecommendationFeedbackFactStore,
)
from internal.recommendation.recommendation_model_release.adapters.inbound.http.router import (  # noqa: E402
    build_router as build_model_release_router,
)
from internal.recommendation.recommendation_model_release.application.command_facade import (  # noqa: E402
    RecommendationModelReleaseCommandFacade,
)
from internal.recommendation.recommendation_model_release.infrastructure.mongo_release_store import (  # noqa: E402
    MongoRecommendationModelReleaseStore,
)
from internal.recommendation.recommendation_subject_closure_fact.adapters.inbound.stream.user_account_closed_consumer import (  # noqa: E402
    UserAccountClosedConsumer,
)
from internal.recommendation.recommendation_subject_closure_fact.infrastructure.mongo_store import (  # noqa: E402
    MongoSubjectClosureStore,
)
from internal.recommendation.ranked_recommendation_window.adapters.inbound.http.router import (  # noqa: E402
    build_router as build_ranked_window_router,
)
from internal.recommendation.ranked_recommendation_window.adapters.inbound.config.content_release_policy import (  # noqa: E402
    load_content_release_policy,
)
from internal.recommendation.ranked_recommendation_window.adapters.inbound.stream.experiment_policy_consumer import (  # noqa: E402
    ExperimentPolicyConsumer,
)
from internal.recommendation.ranked_recommendation_window.application.facade import (  # noqa: E402
    Facade as RankedWindowFacade,
)
from internal.recommendation.ranked_recommendation_window.domain.experiment_policy import (  # noqa: E402
    EXPERIMENT_ID as RECOMMENDATION_EXPERIMENT_ID,
    ExperimentAssignments,
)
from internal.recommendation.ranked_recommendation_window.infrastructure.experiment_assignment_publisher import (  # noqa: E402
    RedisExperimentAssignmentPublisher,
)
from internal.recommendation.ranked_recommendation_window.infrastructure.mongo_experiment_policy_store import (  # noqa: E402
    MongoExperimentPolicyStore,
)
from internal.recommendation.ranked_recommendation_window.infrastructure.mongo_ranker import (  # noqa: E402
    MongoCandidateRanker,
)
from internal.recommendation.ranked_recommendation_window.infrastructure.redis_store import (  # noqa: E402
    RedisWindowStore,
)
from security.service_authorization import ServiceTokenVerifier  # noqa: E402


http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests served by recommendation-service.",
    ["handler", "method", "status"],
)

http_request_duration_highr_seconds = Histogram(
    "http_request_duration_highr_seconds",
    "HTTP request latency with high-resolution buckets.",
    ["handler", "method", "status"],
    buckets=[0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"missing required recommendation runtime config: {name}")
    return value


def _redis_scene_config(scene: str) -> dict:
    redis_config = runtime_config.get("redis", {})
    scene_config = redis_config.get(scene, {}) if isinstance(redis_config, dict) else {}
    if not isinstance(scene_config, dict):
        raise RuntimeError(f"runtime redis.{scene} config must be a mapping")
    return scene_config


def _ranked_window_store_config() -> dict[str, int]:
    config = runtime_config.get("ranked_window")
    if not isinstance(config, Mapping):
        raise RuntimeError("runtime ranked_window config must be a mapping")
    bindings = {
        "quota_shard_count": "quota_shard_count",
        "maximum_live_records_per_shard": "maximum_live_records_per_shard",
        "maximum_live_bytes_per_shard": "maximum_live_bytes_per_shard",
    }
    resolved: dict[str, int] = {}
    for runtime_key, constructor_key in bindings.items():
        value = config.get(runtime_key)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise RuntimeError(
                f"runtime ranked_window.{runtime_key} must be a positive integer"
            )
        resolved[constructor_key] = value
    return resolved


def _host_port(address: str) -> tuple[str, int]:
    normalized = address.strip()
    if not normalized:
        raise RuntimeError("redis.rec address is required")
    if "://" in normalized:
        parsed = urlparse(normalized)
        if not parsed.hostname or parsed.port is None:
            raise RuntimeError("redis.rec address must contain host and port")
        return parsed.hostname, parsed.port
    host, separator, raw_port = normalized.rpartition(":")
    if not separator or not host or not raw_port.isdigit():
        raise RuntimeError("redis.rec address must use host:port")
    return host, int(raw_port)


def _build_redis_client(scene: str):
    config = _redis_scene_config(scene)
    mode = str(config.get("mode") or "standalone").strip()
    addresses = config.get("addrs") or []
    if not isinstance(addresses, list):
        raise RuntimeError("redis.rec.addrs must be a list")
    primary = str(config.get("addr") or "").strip()
    if not primary and addresses:
        primary = str(addresses[0])
    host, port = _host_port(primary)
    password = os.getenv(
        f"RECOMMENDATION_REDIS_{scene.upper()}_PASSWORD",
        "",
    ).strip() or None
    tls = bool(config.get("tls", False))
    connect_timeout = max(int(config.get("pool", {}).get("dial_timeout_ms", 500)), 1) / 1000.0
    read_timeout = max(int(config.get("pool", {}).get("read_timeout_ms", 100)), 1) / 1000.0
    if mode == "cluster":
        if int(config.get("db", 0)) != 0:
            raise RuntimeError(f"redis.{scene} cluster mode requires db=0")
        return RedisCluster(
            host=host,
            port=port,
            password=password,
            ssl=tls,
            socket_connect_timeout=connect_timeout,
            socket_timeout=read_timeout,
        )
    if mode != "standalone":
        raise RuntimeError(f"unsupported redis.{scene} mode: {mode}")
    return Redis(
        host=host,
        port=port,
        db=int(config.get("db", 0)),
        password=password,
        ssl=tls,
        socket_connect_timeout=connect_timeout,
        socket_timeout=read_timeout,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    refresh_rec_model_loaded_gauges()
    refresh_capacity_metrics()
    mongodb_database = os.getenv("MONGODB_DATABASE", "quwoquan_recommendation").strip()
    if mongodb_database != "quwoquan_recommendation":
        raise RuntimeError(
            "recommendation-service MONGODB_DATABASE must be quwoquan_recommendation"
        )
    mongo_client = MongoClient(
        _required_env("MONGODB_URI"),
        serverSelectionTimeoutMS=3000,
        tz_aware=True,
    )
    general_redis_client = _build_redis_client("general")
    recommendation_redis_client = _build_redis_client("rec")
    post_lifecycle_consumer = None
    premium_pool_consumer = None
    user_account_closed_consumer = None
    user_account_restriction_consumer = None
    persona_relationship_consumer = None
    content_behavior_consumer = None
    feature_persona_relationship_consumer = None
    feature_circle_membership_consumer = None
    feature_content_behavior_consumer = None
    feature_post_lifecycle_consumer = None
    tag_feedback_consumer = None
    feed_page_delivered_consumer = None
    experiment_policy_consumer = None
    try:
        mongo_client.admin.command("ping")
        general_redis_client.ping()
        recommendation_redis_client.ping()
        database = mongo_client[mongodb_database]
        model_release_store = MongoRecommendationModelReleaseStore(database)
        candidate_store = MongoCandidateIndexStore(database)
        feature_store = MongoFeatureProfileStore(database)
        subject_closure_store = MongoSubjectClosureStore(database)
        exposure_store = MongoExposureFactStore(database)
        feedback_store = MongoRecommendationFeedbackFactStore(database)
        model_release_store.ensure_indexes()
        candidate_store.ensure_indexes()
        feature_store.ensure_indexes()
        subject_closure_store.ensure_indexes()
        exposure_store.ensure_indexes()
        feedback_store.ensure_indexes()
        feature_projector = FactProjectionAdapter(FeatureProfileProjector(feature_store))
        intersection_materializer = IntersectionMaterializer(
            evidence=feature_store,
            projector=IntersectionProjector(feature_store),
        )
        intersection_event_projector = IntersectionEventProjector(
            store=feature_store,
            materializer=intersection_materializer,
            subject_closures=subject_closure_store,
        )
        app.state.author_impact_reader = AuthorImpactReader(feature_store)
        app.state.intersection_reader = IntersectionReader(
            feature_store,
            intersection_materializer,
            subject_closure_store,
        )
        app.state.model_release_command_facade = (
            RecommendationModelReleaseCommandFacade(model_release_store)
        )
        experiment_policy_store = MongoExperimentPolicyStore(database)
        experiment_policy_store.ensure_indexes()
        experiment_assignments = ExperimentAssignments(
            RedisExperimentAssignmentPublisher(general_redis_client)
        )
        runtime_workload = os.getenv("QWQ_WORKLOAD", "full").strip().lower()
        content_slice_workload = runtime_workload in {
            "content-release",
            "content-commercial",
        }
        restored_policy = experiment_policy_store.load(RECOMMENDATION_EXPERIMENT_ID)
        if restored_policy is None and content_slice_workload:
            restored_policy = experiment_policy_store.apply(
                load_content_release_policy(
                    os.getenv(
                        "RECOMMENDATION_POLICY_FILE",
                        "/etc/qwq-rec-policy/policy.yaml",
                    )
                )
            )
        if restored_policy is not None:
            experiment_assignments.apply_policy(restored_policy)
        experiment_policy_consumer = ExperimentPolicyConsumer(
            redis_client=general_redis_client,
            store=experiment_policy_store,
            assignments=experiment_assignments,
            consumer=os.getenv(
                "SERVICE_INSTANCE_ID", "recommendation-experiment-policy"
            ),
        )
        experiment_policy_consumer.process_once()
        experiment_ready = experiment_assignments.healthy()
        app.state.runtime_workload = runtime_workload if content_slice_workload else "full"
        if not experiment_ready and not content_slice_workload:
            raise RuntimeError(
                "recommendation-service requires active rec_model_vs_rule ExperimentPolicyActivated"
            )
        window_store = RedisWindowStore(
            recommendation_redis_client,
            **_ranked_window_store_config(),
        )
        if experiment_ready:
            experiment_policy_consumer.start()
            app.state.experiment_policy_consumer = experiment_policy_consumer
            app.state.ranked_window_facade = RankedWindowFacade(
                store=window_store,
                ranker=MongoCandidateRanker(
                    candidates=candidate_store,
                    feature_profiles=feature_store,
                    scoring=get_scoring_facade(),
                    experiments=experiment_assignments,
                    snapshot_digester=canonical_snapshot_digest,
                ),
                subject_closures=subject_closure_store,
            )
        post_lifecycle_consumer = CandidatePostLifecycleConsumer(
            redis_client=general_redis_client,
            projection=candidate_store,
            subject_closures=subject_closure_store,
            consumer=os.getenv("SERVICE_INSTANCE_ID", "recommendation-candidate-projection"),
        )
        post_lifecycle_consumer.start()
        app.state.candidate_post_lifecycle_consumer = post_lifecycle_consumer
        premium_pool_consumer = PremiumPoolConsumer(
            redis_client=general_redis_client,
            store=candidate_store,
            consumer=os.getenv(
                "SERVICE_INSTANCE_ID", "recommendation-candidate-premium"
            ),
        )
        premium_pool_consumer.start()
        app.state.candidate_premium_pool_consumer = premium_pool_consumer
        user_account_closed_consumer = UserAccountClosedConsumer(
            redis_client=general_redis_client,
            store=subject_closure_store,
            erasers=(
                candidate_store,
                feedback_store,
                exposure_store,
                feature_store,
                window_store,
            ),
            consumer=os.getenv("SERVICE_INSTANCE_ID", "recommendation-subject-closure"),
        )
        user_account_closed_consumer.start()
        app.state.user_account_closed_consumer = user_account_closed_consumer
        user_account_restriction_consumer = UserAccountRestrictionConsumer(
            redis_client=general_redis_client,
            projection=candidate_store,
            subject_closures=subject_closure_store,
            consumer=os.getenv(
                "SERVICE_INSTANCE_ID", "recommendation-candidate-restriction"
            ),
        )
        user_account_restriction_consumer.start()
        app.state.user_account_restriction_consumer = (
            user_account_restriction_consumer
        )
        persona_relationship_consumer = CandidatePersonaRelationshipConsumer(
            redis_client=general_redis_client,
            projection=candidate_store,
            consumer=os.getenv(
                "SERVICE_INSTANCE_ID",
                "recommendation-candidate-persona-relationship",
            ),
        )
        persona_relationship_consumer.start()
        app.state.persona_relationship_consumer = persona_relationship_consumer
        feed_page_delivered_consumer = FeedPageDeliveredConsumer(
            redis_client=general_redis_client,
            exposure_store=exposure_store,
            subject_closures=subject_closure_store,
            feature_projector=feature_projector,
            consumer=os.getenv("SERVICE_INSTANCE_ID", "recommendation-exposure-fact"),
        )
        feed_page_delivered_consumer.start()
        app.state.feed_page_delivered_consumer = feed_page_delivered_consumer
        content_behavior_consumer = FeedbackContentBehaviorConsumer(
            redis_client=general_redis_client,
            feedback_store=feedback_store,
            exposure_store=exposure_store,
            subject_closures=subject_closure_store,
            feature_projector=feature_projector,
            consumer=os.getenv("SERVICE_INSTANCE_ID", "recommendation-feedback-fact"),
        )
        content_behavior_consumer.start()
        app.state.content_behavior_consumer = content_behavior_consumer
        feature_persona_relationship_consumer = FeaturePersonaRelationshipConsumer(
            redis_client=general_redis_client,
            feature_store=feature_store,
            projector=intersection_event_projector,
            consumer=os.getenv(
                "SERVICE_INSTANCE_ID", "recommendation-feature-persona-relationship"
            ),
        )
        feature_persona_relationship_consumer.start()
        app.state.feature_persona_relationship_consumer = (
            feature_persona_relationship_consumer
        )
        feature_circle_membership_consumer = FeatureCircleMembershipConsumer(
            redis_client=general_redis_client,
            feature_store=feature_store,
            projector=intersection_event_projector,
            consumer=os.getenv(
                "SERVICE_INSTANCE_ID", "recommendation-feature-circle-membership"
            ),
        )
        feature_circle_membership_consumer.start()
        app.state.feature_circle_membership_consumer = feature_circle_membership_consumer
        feature_content_behavior_consumer = FeatureContentBehaviorConsumer(
            redis_client=general_redis_client,
            feature_store=feature_store,
            projector=intersection_event_projector,
            consumer=os.getenv(
                "SERVICE_INSTANCE_ID", "recommendation-feature-content-behavior"
            ),
        )
        feature_content_behavior_consumer.start()
        app.state.feature_content_behavior_consumer = feature_content_behavior_consumer
        feature_post_lifecycle_consumer = FeaturePostLifecycleConsumer(
            redis_client=general_redis_client,
            feature_store=feature_store,
            projector=intersection_event_projector,
            consumer=os.getenv(
                "SERVICE_INSTANCE_ID", "recommendation-feature-post-lifecycle"
            ),
        )
        feature_post_lifecycle_consumer.start()
        app.state.feature_post_lifecycle_consumer = feature_post_lifecycle_consumer
        tag_feedback_consumer = TagFeedbackConsumer(
            redis_client=general_redis_client,
            feature_store=feature_store,
            feature_projector=feature_projector,
            subject_closures=subject_closure_store,
            consumer=os.getenv(
                "SERVICE_INSTANCE_ID", "recommendation-feature-tag-feedback"
            ),
        )
        tag_feedback_consumer.start()
        app.state.tag_feedback_consumer = tag_feedback_consumer
        yield
    finally:
        if feature_post_lifecycle_consumer is not None:
            feature_post_lifecycle_consumer.stop()
        if feature_content_behavior_consumer is not None:
            feature_content_behavior_consumer.stop()
        if feature_circle_membership_consumer is not None:
            feature_circle_membership_consumer.stop()
        if feature_persona_relationship_consumer is not None:
            feature_persona_relationship_consumer.stop()
        if user_account_restriction_consumer is not None:
            user_account_restriction_consumer.stop()
        if persona_relationship_consumer is not None:
            persona_relationship_consumer.stop()
        if experiment_policy_consumer is not None:
            experiment_policy_consumer.stop()
        if content_behavior_consumer is not None:
            content_behavior_consumer.stop()
        if tag_feedback_consumer is not None:
            tag_feedback_consumer.stop()
        if feed_page_delivered_consumer is not None:
            feed_page_delivered_consumer.stop()
        if user_account_closed_consumer is not None:
            user_account_closed_consumer.stop()
        if post_lifecycle_consumer is not None:
            post_lifecycle_consumer.stop()
        if premium_pool_consumer is not None:
            premium_pool_consumer.stop()
        recommendation_redis_client.close()
        general_redis_client.close()
        mongo_client.close()


app = FastAPI(
    title="quwoquan recommendation-service",
    lifespan=lifespan,
    description="Recommendation model scoring through the ModelRelease Reader contract.",
)


def _ranked_window_facade(request: Request) -> RankedWindowFacade:
    facade = getattr(request.app.state, "ranked_window_facade", None)
    if facade is None:
        raise RuntimeError("ranked recommendation window runtime is not initialized")
    return facade


def _model_release_command_facade(
    request: Request,
) -> RecommendationModelReleaseCommandFacade:
    facade = getattr(request.app.state, "model_release_command_facade", None)
    if facade is None:
        raise RuntimeError("recommendation model release runtime is not initialized")
    return facade


def _author_impact_reader(request: Request) -> AuthorImpactReader:
    reader = getattr(request.app.state, "author_impact_reader", None)
    if reader is None:
        raise RuntimeError("recommendation author impact reader is not initialized")
    return reader


def _intersection_reader(request: Request) -> IntersectionReader:
    reader = getattr(request.app.state, "intersection_reader", None)
    if reader is None:
        raise RuntimeError("recommendation intersection reader is not initialized")
    return reader


def _handler_label(request: Request) -> str:
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    if route_path:
        return str(route_path)
    return request.url.path or "unknown"


@app.middleware("http")
async def observe_http(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        handler = _handler_label(request)
        elapsed = time.perf_counter() - started
        http_requests_total.labels(
            handler=handler,
            method=request.method,
            status="5xx",
        ).inc()
        http_request_duration_highr_seconds.labels(
            handler=handler,
            method=request.method,
            status="5xx",
        ).observe(elapsed)
        raise

    handler = _handler_label(request)
    status_group = f"{response.status_code // 100}xx"
    elapsed = time.perf_counter() - started
    http_requests_total.labels(
        handler=handler,
        method=request.method,
        status=status_group,
    ).inc()
    http_request_duration_highr_seconds.labels(
        handler=handler,
        method=request.method,
        status=status_group,
    ).observe(elapsed)
    return response


app.include_router(score_router)
app.include_router(
    build_model_release_router(
        facade_provider=_model_release_command_facade,
        token_verifier=ServiceTokenVerifier.from_env(),
    )
)
app.include_router(
    build_feature_profile_router(
        reader_provider=_author_impact_reader,
        intersection_reader_provider=_intersection_reader,
        token_verifier=ServiceTokenVerifier.from_env(),
    )
)
app.include_router(
    build_ranked_window_router(
        facade_provider=_ranked_window_facade,
        token_verifier=ServiceTokenVerifier.from_env(),
    )
)
app.mount("/metrics", make_asgi_app())
