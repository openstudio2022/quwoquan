"""
Tests for POST /v1/score and GET /health.
Run from service root: PYTHONPATH=. pytest tests/ -v
"""
import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_score_empty_candidates():
    r = client.post(
        "/v1/score",
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
        "/v1/score",
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
        "/v1/score",
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
                {"contentId": "c1", "tags": ["travel"], "likeCount": 1, "viewCount": 10, "ageHours": 1.0},
                {"contentId": "c2", "tags": ["food"], "likeCount": 1, "viewCount": 10, "ageHours": 1.0},
            ],
        },
    )
    assert r.status_code == 200
    scores = {s["contentId"]: s["score"] for s in r.json()["scores"]}
    assert scores["c1"] > scores["c2"]


def test_score_filters_exposed_or_negative():
    r = client.post(
        "/v1/score",
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
                {"contentId": "c1", "tags": ["travel"], "likeCount": 10, "viewCount": 100, "ageHours": 1.0},
                {"contentId": "c2", "tags": ["travel"], "likeCount": 10, "viewCount": 100, "ageHours": 1.0},
                {"contentId": "c3", "tags": ["travel"], "likeCount": 10, "viewCount": 100, "ageHours": 1.0},
            ],
        },
    )
    assert r.status_code == 200
    scores = {s["contentId"]: s["score"] for s in r.json()["scores"]}
    assert scores["c1"] < scores["c3"]
    assert scores["c2"] < scores["c3"]
