"""
API tests for POST /v1/score and GET /health.
Run from services/rec-model-service: python -m pytest tests/ -v
Requires: pip install fastapi uvicorn pydantic httpx pytest
"""
from __future__ import annotations

import sys
from pathlib import Path

# Run from rec-model-service root so app, api, models, generated are on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_health() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


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
    r = client.post("/v1/score", json=body)
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
    r = client.post("/v1/score", json=body)
    assert r.status_code == 200
    data = r.json()
    assert len(data["scores"]) == 1
    assert data["scores"][0]["contentId"] == "c1"


def test_reload_endpoint_returns_versions() -> None:
    r = client.post("/v1/model/reload")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "reloaded"
    assert isinstance(data.get("versions"), dict)
    assert data["versions"]


def test_score_unsupported_scenario_400() -> None:
    body = {
        "scenario": "unknown_scenario",
        "userId": "u1",
        "sessionId": "s1",
        "candidates": [{"contentId": "c1"}],
    }
    r = client.post("/v1/score", json=body)
    assert r.status_code == 400


def test_score_empty_candidates_returns_empty_scores() -> None:
    body = {"scenario": "content_feed", "userId": "u1", "sessionId": "s1", "candidates": []}
    r = client.post("/v1/score", json=body)
    assert r.status_code == 200
    assert r.json() == {"scores": []}
