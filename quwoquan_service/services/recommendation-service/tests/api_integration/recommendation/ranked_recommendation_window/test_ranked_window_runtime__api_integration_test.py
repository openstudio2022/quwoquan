"""RankedRecommendationWindow HTTP operations over the real runtime composition.

Drives CreateRankedRecommendationWindow and GetRankedRecommendationPage through the
production router, facade, Redis window store, Mongo candidate/feature/closure stores
and the Redis experiment assignment publisher. No in-memory port substitutes.
"""
# spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-001
# readiness_case: create-ranked-window-api
# readiness_case: get-ranked-page-api
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.support.service_token import (
    configure_test_auth_environment,
    service_token,
)

# api.score and the router's token verifier read auth config at import time.
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
from internal.recommendation.ranked_recommendation_window.domain.experiment_policy import (  # noqa: E402
    EXPERIMENT_ID,
    ExperimentAssignments,
    ExperimentPolicy,
    PolicyVariant,
)
from internal.recommendation.ranked_recommendation_window.infrastructure.experiment_assignment_publisher import (  # noqa: E402
    STREAM as EXPERIMENT_ASSIGNMENT_STREAM,
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
from internal.recommendation.recommendation_subject_closure_fact.domain.fact import (  # noqa: E402
    SubjectClosureFact,
)
from internal.recommendation.recommendation_subject_closure_fact.infrastructure.mongo_store import (  # noqa: E402
    MongoSubjectClosureStore,
)
from security.service_authorization import ServiceTokenVerifier  # noqa: E402
from tests.support.recommendation_mongo import mongo_client, mongo_database  # noqa: E402,F401
from tests.support.recommendation_redis import real_redis  # noqa: E402,F401


CANDIDATE_COUNT = 5
SUBJECT_ID = "persona-ranked-window"
CLOSED_SUBJECT_ID = "account-ranked-window-closed"


def _page_path(window_id: str) -> str:
    return f"/internal/recommendation/ranked-pages/{window_id}"


def _rule_only_policy() -> ExperimentPolicy:
    # The activated policy pins every subject to the rule bucket so the assertions
    # below observe one deterministic ranking without a trained model artifact.
    updated_at = datetime.now(timezone.utc)
    return ExperimentPolicy(
        experiment_id=EXPERIMENT_ID,
        revision=1,
        status="running",
        variants=(
            PolicyVariant("model", 0),
            PolicyVariant("rule", 10_000),
        ),
        starts_at=updated_at - timedelta(minutes=5),
        ends_at=None,
        updated_at=updated_at,
        digest="",
    )


def _seed_candidates(store: MongoCandidateIndexStore) -> None:
    published_at = datetime.now(timezone.utc) - timedelta(hours=1)
    for index in range(CANDIDATE_COUNT):
        assert store.apply_source_event(
            event_id=f"ranked-window-post-published-{index}",
            snapshot=CandidateLifecycleSnapshot(
                scenario="content_feed",
                content_id=f"post-{index}",
                content_type="article",
                author_id=f"persona-author-{index}",
                tag_refs=("Topic/旅行",),
                entity_refs=(),
                published_at=published_at,
                content_vertical="travel",
                entity_tag_ids=(),
                source_sequence=index + 1,
                updated_at=published_at + timedelta(seconds=index),
            ),
        )


class _Runtime:
    def __init__(self, mongo_database, real_redis) -> None:
        self.candidates = MongoCandidateIndexStore(mongo_database)
        self.features = MongoFeatureProfileStore(mongo_database)
        self.closures = MongoSubjectClosureStore(mongo_database)
        for store in (self.candidates, self.features, self.closures):
            store.ensure_indexes()
        self.window_store = RedisWindowStore(real_redis)
        self.assignments = ExperimentAssignments(
            RedisExperimentAssignmentPublisher(real_redis)
        )
        self.assignments.apply_policy(_rule_only_policy())
        facade = Facade(
            store=self.window_store,
            ranker=MongoCandidateRanker(
                candidates=self.candidates,
                feature_profiles=self.features,
                scoring=get_scoring_facade(),
                experiments=self.assignments,
                snapshot_digester=canonical_snapshot_digest,
            ),
            subject_closures=self.closures,
        )
        app = FastAPI()
        app.include_router(
            build_router(
                facade_provider=lambda _request: facade,
                token_verifier=ServiceTokenVerifier.from_env(),
            )
        )
        self.client = TestClient(app)

    def headers(self, idempotency_key: str | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {service_token(scopes=['recommendation.ranked_page'])}"
        }
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        return headers


def test_ranked_window_create_and_continue_over_real_redis_and_mongo(
    mongo_database,
    real_redis,
) -> None:
    runtime = _Runtime(mongo_database, real_redis)
    _seed_candidates(runtime.candidates)
    body = {"subjectId": SUBJECT_ID, "scenario": "content_feed", "limit": 2}

    created = runtime.client.post(
        CREATE_RANKED_RECOMMENDATION_WINDOW_PATH,
        headers=runtime.headers("ranked-window-request-001"),
        json=body,
    )
    assert created.status_code == 200
    payload = created.json()
    window_id = payload["windowId"]
    assert payload["modelBucket"] == "rule"
    assert payload["modelChannel"] is None
    assert payload["modelReleaseId"] is None
    assert payload["nextOrdinal"] == 2
    assert [item["ordinal"] for item in payload["items"]] == [0, 1]
    assert all(item["featureSnapshotDigest"] for item in payload["items"])

    # The bounded window is durable in Redis and the assignment reached the
    # ExperimentAssignmentObserved stream, not just process memory.
    stored = runtime.window_store.get(SUBJECT_ID, window_id)
    assert stored is not None
    assert [item.ordinal for item in stored.items] == list(range(CANDIDATE_COUNT))
    assert real_redis.xlen(EXPERIMENT_ASSIGNMENT_STREAM) >= 1

    replayed = runtime.client.post(
        CREATE_RANKED_RECOMMENDATION_WINDOW_PATH,
        headers=runtime.headers("ranked-window-request-001"),
        json=body,
    )
    assert replayed.status_code == 200
    assert replayed.json() == payload

    continued = runtime.client.get(
        _page_path(window_id),
        headers=runtime.headers(),
        params={"subjectId": SUBJECT_ID, "fromOrdinal": 2, "limit": 2},
    )
    assert continued.status_code == 200
    continued_payload = continued.json()
    assert [item["ordinal"] for item in continued_payload["items"]] == [2, 3]
    assert continued_payload["nextOrdinal"] == 4
    assert continued_payload["rankingSnapshotDigest"] == payload["rankingSnapshotDigest"]
    assert continued_payload["expiresAt"] == payload["expiresAt"]

    tail = runtime.client.get(
        _page_path(window_id),
        headers=runtime.headers(),
        params={"subjectId": SUBJECT_ID, "fromOrdinal": 4, "limit": 20},
    )
    assert tail.status_code == 200
    assert tail.json()["nextOrdinal"] is None

    foreign_subject = runtime.client.get(
        _page_path(window_id),
        headers=runtime.headers(),
        params={"subjectId": "persona-other", "fromOrdinal": 0, "limit": 2},
    )
    assert foreign_subject.status_code == 404
    assert foreign_subject.json()["detail"]["code"] == (
        "RECOMMENDATION.USER.ranked_window_not_found"
    )


def test_ranked_window_rejects_unauthorized_conflict_and_missing_window(
    mongo_database,
    real_redis,
) -> None:
    runtime = _Runtime(mongo_database, real_redis)
    _seed_candidates(runtime.candidates)
    body = {"subjectId": SUBJECT_ID, "scenario": "content_feed", "limit": 2}

    anonymous = runtime.client.post(CREATE_RANKED_RECOMMENDATION_WINDOW_PATH, json=body)
    assert anonymous.status_code == 401
    assert anonymous.json()["detail"]["code"] == (
        "RECOMMENDATION.USER.ranked_window_unauthorized"
    )

    wrong_scope = runtime.client.post(
        CREATE_RANKED_RECOMMENDATION_WINDOW_PATH,
        headers={
            "Authorization": f"Bearer {service_token(scopes=['recommendation.model.score'])}",
            "Idempotency-Key": "ranked-window-request-scope",
        },
        json=body,
    )
    assert wrong_scope.status_code == 403
    assert wrong_scope.json()["detail"]["code"] == (
        "RECOMMENDATION.USER.ranked_window_forbidden"
    )

    missing_key = runtime.client.post(
        CREATE_RANKED_RECOMMENDATION_WINDOW_PATH,
        headers=runtime.headers(),
        json=body,
    )
    assert missing_key.status_code == 400
    assert missing_key.json()["detail"]["code"] == (
        "RECOMMENDATION.USER.ranked_window_invalid_argument"
    )

    assert runtime.client.post(
        CREATE_RANKED_RECOMMENDATION_WINDOW_PATH,
        headers=runtime.headers("ranked-window-request-002"),
        json=body,
    ).status_code == 200
    conflict = runtime.client.post(
        CREATE_RANKED_RECOMMENDATION_WINDOW_PATH,
        headers=runtime.headers("ranked-window-request-002"),
        json={**body, "limit": 3},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == (
        "RECOMMENDATION.USER.ranked_window_conflict"
    )

    expired = runtime.client.get(
        _page_path("00000000-0000-0000-0000-000000000000"),
        headers=runtime.headers(),
        params={"subjectId": SUBJECT_ID},
    )
    assert expired.status_code == 404
    assert expired.json()["detail"]["code"] == (
        "RECOMMENDATION.USER.ranked_window_not_found"
    )


def test_ranked_window_closes_and_erases_windows_for_closed_subject(
    mongo_database,
    real_redis,
) -> None:
    runtime = _Runtime(mongo_database, real_redis)
    _seed_candidates(runtime.candidates)
    body = {"subjectId": CLOSED_SUBJECT_ID, "scenario": "content_feed", "limit": 2}

    created = runtime.client.post(
        CREATE_RANKED_RECOMMENDATION_WINDOW_PATH,
        headers=runtime.headers("ranked-window-request-003"),
        json=body,
    )
    assert created.status_code == 200
    window_id = created.json()["windowId"]

    closed_at = datetime.now(timezone.utc)
    _fact, appended = runtime.closures.append_if_absent(
        SubjectClosureFact(
            account_id=CLOSED_SUBJECT_ID,
            subject_ids=(CLOSED_SUBJECT_ID,),
            source_event_id="user-account-closed-ranked-window",
            source_digest="a" * 64,
            closed_at=closed_at,
            recorded_at=closed_at,
        )
    )
    assert appended

    read_after_closure = runtime.client.get(
        _page_path(window_id),
        headers=runtime.headers(),
        params={"subjectId": CLOSED_SUBJECT_ID},
    )
    assert read_after_closure.status_code == 410
    assert read_after_closure.json()["detail"]["code"] == (
        "RECOMMENDATION.USER.ranked_window_subject_closed"
    )
    assert runtime.window_store.get(CLOSED_SUBJECT_ID, window_id) is None

    create_after_closure = runtime.client.post(
        CREATE_RANKED_RECOMMENDATION_WINDOW_PATH,
        headers=runtime.headers("ranked-window-request-004"),
        json=body,
    )
    assert create_after_closure.status_code == 410
    assert create_after_closure.json()["detail"]["code"] == (
        "RECOMMENDATION.USER.ranked_window_subject_closed"
    )
