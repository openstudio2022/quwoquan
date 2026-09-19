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


def test_health(app_factory):
    app_factory()
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.parametrize("workload", ["content-release", "content-commercial"])
def test_content_slice_health_does_not_claim_experiment_scoring_readiness(
    app_factory, workload
):
    app_factory(workload=workload, scoring_ready=False)

    r = client.get("/health")

    assert r.status_code == 200
    assert r.json() == {"status": "content_release_only"}


def test_health_fails_closed_when_projection_consumer_is_missing(app_factory):
    app_factory()
    app.state.candidate_post_lifecycle_consumer = None
    r = client.get("/health")
    assert r.status_code == 503
    assert r.json()["detail"] == {"status": "not_ready"}


def test_health_fails_closed_when_model_runtime_consumer_is_missing(app_factory):
    app_factory()
    app.state.model_release_runtime_consumer = None
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
                {"contentId": "c1", "contentType": "article", "likeCount": 10, "viewCount": 100, "ageHours": 1.0},
                {"contentId": "c2", "contentType": "article", "likeCount": 5, "viewCount": 50, "ageHours": 12.0},
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
                {"contentId": "c1", "contentType": "article", "tagRefs": ["travel"], "likeCount": 1, "viewCount": 10, "ageHours": 1.0},
                {"contentId": "c2", "contentType": "article", "tagRefs": ["food"], "likeCount": 1, "viewCount": 10, "ageHours": 1.0},
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
                {"contentId": "c1", "contentType": "article", "tagRefs": ["travel"], "likeCount": 10, "viewCount": 100, "ageHours": 1.0},
                {"contentId": "c2", "contentType": "article", "tagRefs": ["travel"], "likeCount": 10, "viewCount": 100, "ageHours": 1.0},
                {"contentId": "c3", "contentType": "article", "tagRefs": ["travel"], "likeCount": 10, "viewCount": 100, "ageHours": 1.0},
            ],
        },
    )
    assert r.status_code == 200
    scores = {s["contentId"]: s["score"] for s in r.json()["scores"]}
    assert scores["c1"] < scores["c3"]
    assert scores["c2"] < scores["c3"]
