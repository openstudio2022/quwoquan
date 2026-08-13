"""
API tests for the ModelRelease scoring Reader and GET /health.
Run from services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime: python -m pytest tests/ -v
Requires: pip install fastapi uvicorn pydantic httpx httpx2 pytest
"""
# spec_ref: specs/feature-tree/recommendation-platform/rec-model-service/spec.md#sit-001
# readiness_case: score-candidates-api
# readiness_case: batch-score-candidates-api
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from support.service_token import (
    ServiceAuthorizedTestClient,
    configure_test_auth_environment,
    service_token,
)

configure_test_auth_environment()

from generated.recommendation.recommendation_model_release.api.operations import (
    BATCH_SCORE_RECOMMENDATION_CANDIDATES_PATH,
    SCORE_RECOMMENDATION_CANDIDATES_PATH,
)
from main import app


client = ServiceAuthorizedTestClient(app)
raw_client = TestClient(app)

SCORE_PATH = SCORE_RECOMMENDATION_CANDIDATES_PATH
BATCH_SCORE_PATH = BATCH_SCORE_RECOMMENDATION_CANDIDATES_PATH


class _HealthyConsumer:
    def healthy(self) -> bool:
        return True


def _mark_runtime_ready() -> None:
    app.state.runtime_workload = "full"
    app.state.ranked_window_facade = object()
    app.state.model_release_command_facade = object()
    app.state.model_release_outbox_relay = _HealthyConsumer()
    app.state.model_release_runtime_consumer = _HealthyConsumer()
    app.state.candidate_post_lifecycle_consumer = _HealthyConsumer()
    app.state.candidate_gathering_lifecycle_consumer = _HealthyConsumer()
    app.state.candidate_premium_pool_consumer = _HealthyConsumer()
    app.state.experiment_policy_consumer = _HealthyConsumer()
    app.state.user_account_closed_consumer = _HealthyConsumer()
    app.state.content_behavior_consumer = _HealthyConsumer()
    app.state.feed_page_delivered_consumer = _HealthyConsumer()


def test_health() -> None:
    _mark_runtime_ready()
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_metrics_exposes_http_series() -> None:
    _mark_runtime_ready()
    client.get("/health")
    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.text
    # Canonical series names/labels shared with the Go runtime middleware so the
    # ContractGraph-derived recommendation_contract recording rules resolve.
    assert (
        'http_server_requests_total{'
        'method="GET",route="/health",service="recommendation-service",status="200"}'
    ) in body
    assert "http_server_duration_seconds_bucket" in body
    assert "http_requests_total{" not in body
    assert "http_request_duration_highr_seconds" not in body


def test_score_content_feed_returns_scores() -> None:
    body = {
        "scenario": "content_feed",
        "userId": "u1",
        "sessionId": "s1",
        "candidates": [
            {"contentId": "c1", "contentType": "post", "ageHours": 1.0, "likeCount": 10},
            {"contentId": "c2", "contentType": "video", "ageHours": 24.0, "likeCount": 5},
        ],
    }
    r = client.post(SCORE_PATH, json=body)
    assert r.status_code == 200
    data = r.json()
    assert "scores" in data
    scores = data["scores"]
    assert len(scores) == 2
    content_ids = {s["contentId"] for s in scores}
    assert content_ids == {"c1", "c2"}
    for s in scores:
        assert "score" in s
        assert isinstance(s["score"], (int, float))


def test_score_accepts_entity_refs() -> None:
    body = {
        "scenario": "content_feed",
        "userId": "u1",
        "sessionId": "s1",
        "candidates": [
            {
                "contentId": "c1",
                "contentType": "post",
                "entityRefs": ["entity/地点/景区/九寨沟"],
                "ageHours": 1.0,
            }
        ],
    }
    r = client.post(SCORE_PATH, json=body)
    assert r.status_code == 200
    data = r.json()
    assert len(data["scores"]) == 1
    assert data["scores"][0]["contentId"] == "c1"


def test_score_unsupported_scenario_400() -> None:
    body = {
        "scenario": "unknown_scenario",
        "userId": "u1",
        "sessionId": "s1",
        "candidates": [{"contentId": "c1"}],
    }
    r = client.post(SCORE_PATH, json=body)
    assert r.status_code == 400


def test_score_empty_candidates_returns_empty_scores() -> None:
    body = {"scenario": "content_feed", "userId": "u1", "sessionId": "s1", "candidates": []}
    r = client.post(SCORE_PATH, json=body)
    assert r.status_code == 200
    assert r.json() == {"scores": [], "modelReleaseId": None}


def test_scoring_requires_service_identity_and_scope() -> None:
    body = {"scenario": "content_feed", "userId": "u1", "sessionId": "s1", "candidates": []}
    missing = raw_client.post(SCORE_PATH, json=body)
    assert missing.status_code == 401
    assert missing.json()["detail"]["code"] == "RECOMMENDATION.USER.unauthorized"

    wrong_scope = raw_client.post(
        SCORE_PATH,
        json=body,
        headers={"Authorization": f"Bearer {service_token(scopes=['content.read'])}"},
    )
    assert wrong_scope.status_code == 403
    assert wrong_scope.json()["detail"]["code"] == "RECOMMENDATION.USER.forbidden"


def test_batch_scoring_uses_same_authoritative_reader() -> None:
    request = {"scenario": "content_feed", "userId": "u1", "sessionId": "s1", "candidates": []}
    response = client.post(BATCH_SCORE_PATH, json={"requests": [request, request]})
    assert response.status_code == 200
    assert response.json() == {
        "results": [
            {"scores": [], "modelReleaseId": None},
            {"scores": [], "modelReleaseId": None},
        ]
    }


def test_retired_score_route_is_not_compatible() -> None:
    response = client.post(
        "/score",
        json={"scenario": "content_feed", "userId": "u1", "sessionId": "s1", "candidates": []},
    )
    assert response.status_code == 404


@pytest.mark.parametrize("path", ["/model/reload", "/model/status"])
def test_undocumented_model_lifecycle_routes_do_not_exist(path: str) -> None:
    response = client.post(path) if path.endswith("reload") else client.get(path)
    assert response.status_code == 404
