"""
Tests for the ModelRelease scoring Reader and GET /health.
Run from service root: PYTHONPATH=. pytest tests/ -v
"""
import pytest

from support.service_token import ServiceAuthorizedTestClient, configure_test_auth_environment

configure_test_auth_environment()

from generated.recommendation.recommendation_model_release.api.operations import (
    SCORE_RECOMMENDATION_CANDIDATES_PATH,
)
from main import app

client = ServiceAuthorizedTestClient(app)

SCORE_PATH = SCORE_RECOMMENDATION_CANDIDATES_PATH


class _HealthyConsumer:
    def healthy(self) -> bool:
        return True


def _mark_runtime_ready() -> None:
    app.state.runtime_workload = "full"
    app.state.ranked_window_facade = object()
    app.state.candidate_post_lifecycle_consumer = _HealthyConsumer()
    app.state.user_account_closed_consumer = _HealthyConsumer()
    app.state.content_behavior_consumer = _HealthyConsumer()
    app.state.feed_page_delivered_consumer = _HealthyConsumer()


def test_health():
    _mark_runtime_ready()
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_content_release_health_does_not_claim_experiment_scoring_readiness():
    _mark_runtime_ready()
    app.state.runtime_workload = "content-release"
    app.state.ranked_window_facade = None
    app.state.experiment_policy_consumer = None

    r = client.get("/health")

    assert r.status_code == 200
    assert r.json() == {"status": "content_release_only"}


def test_health_fails_closed_when_projection_consumer_is_missing():
    app.state.candidate_post_lifecycle_consumer = None
    r = client.get("/health")
    assert r.status_code == 503
    assert r.json()["detail"] == {"status": "not_ready"}


def test_score_empty_candidates():
    r = client.post(
        SCORE_PATH,
        json={
            "scenario": "content_feed",
            "userId": "u1",
            "sessionId": "s1",
            "candidates": [],
        },
    )
    assert r.status_code == 200
    assert r.json()["scores"] == []


def test_score_content_feed():
    r = client.post(
        SCORE_PATH,
        json={
            "scenario": "content_feed",
            "userId": "u1",
            "sessionId": "s1",
            "candidates": [
                {"contentId": "c1", "likeCount": 10, "viewCount": 100, "ageHours": 1.0},
                {"contentId": "c2", "likeCount": 5, "viewCount": 50, "ageHours": 12.0},
            ],
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert "scores" in data
    assert len(data["scores"]) == 2
    content_ids = {s["contentId"] for s in data["scores"]}
    assert content_ids == {"c1", "c2"}
    for s in data["scores"]:
        assert "score" in s and isinstance(s["score"], (int, float))


def test_score_uses_session_signals_tag_boost():
    r = client.post(
        SCORE_PATH,
        json={
            "scenario": "content_feed",
            "userId": "u1",
            "sessionId": "s1",
            "sessionSignals": {
                "tagWeights": {"travel": 10.0},
                "exposedIds": [],
                "negativeIds": [],
            },
            "candidates": [
                {"contentId": "c1", "tagRefs": ["travel"], "likeCount": 1, "viewCount": 10, "ageHours": 1.0},
                {"contentId": "c2", "tagRefs": ["food"], "likeCount": 1, "viewCount": 10, "ageHours": 1.0},
            ],
        },
    )
    assert r.status_code == 200
    scores = {s["contentId"]: s["score"] for s in r.json()["scores"]}
    assert scores["c1"] > scores["c2"]


def test_score_filters_exposed_or_negative():
    r = client.post(
        SCORE_PATH,
        json={
            "scenario": "content_feed",
            "userId": "u1",
            "sessionId": "s1",
            "sessionSignals": {
                "tagWeights": {"travel": 5.0},
                "exposedIds": ["c1"],
                "negativeIds": ["c2"],
            },
            "candidates": [
                {"contentId": "c1", "tagRefs": ["travel"], "likeCount": 10, "viewCount": 100, "ageHours": 1.0},
                {"contentId": "c2", "tagRefs": ["travel"], "likeCount": 10, "viewCount": 100, "ageHours": 1.0},
                {"contentId": "c3", "tagRefs": ["travel"], "likeCount": 10, "viewCount": 100, "ageHours": 1.0},
            ],
        },
    )
    assert r.status_code == 200
    scores = {s["contentId"]: s["score"] for s in r.json()["scores"]}
    assert scores["c1"] < scores["c3"]
    assert scores["c2"] < scores["c3"]
