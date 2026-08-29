# spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-001
# readiness_case: create-ranked-window-local
# readiness_case: get-ranked-page-local
from fastapi import FastAPI
from fastapi.testclient import TestClient

from internal.recommendation.ranked_recommendation_window.adapters.inbound.http.router import (
    build_router,
)
from internal.recommendation.ranked_recommendation_window.application.facade import Facade
from internal.recommendation.ranked_recommendation_window.domain.model import (
    RankedCandidate,
    RankingResult,
)
from security.service_authorization import AuthorizationFailure
from datetime import datetime, timezone


class _Store:
    def __init__(self) -> None:
        self.windows = {}

    def create_or_get(self, window):
        return self.windows.setdefault(window.window_id, window)

    def get(self, subject_id, window_id):
        window = self.windows.get(window_id)
        if window is None or window.subject_id != subject_id:
            return None
        return window

    def erase_subject(self, subject_id):
        removed = [
            window_id
            for window_id, window in self.windows.items()
            if window.subject_id == subject_id
        ]
        for window_id in removed:
            del self.windows[window_id]
        return len(removed)


class _Ranker:
    def rank(self, *, subject_id: str, scenario: str, session_id: str, limit: int):
        assert limit == 300
        return RankingResult(
            experiment_bucket="model",
            model_bucket="model",
            model_channel="champion",
            model_release_id="release-001",
            policy_digest="sha256:2f8a57089882835170b77224eb7ef2db78c5d5d26ae4637b210dbe195713f094",
            feature_snapshot_at=datetime(2020, 7, 31, 12, tzinfo=timezone.utc),
            ranking_snapshot_digest="ranking-digest-001",
            user_feature_snapshot={"engagement": 0.7},
            candidates=tuple(
                RankedCandidate(
                    content_id=f"post-{index}",
                    score=float(5 - index),
                    feature_snapshot_digest=f"feature-digest-{index}",
                    item_feature_snapshot={"quality": index / 10},
                )
                for index in range(5)
            ),
        )


class _Verifier:
    def verify(self, authorization, *, required_scope):
        assert required_scope == "recommendation.ranked_page"
        if authorization is None:
            raise AuthorizationFailure(401, "ignored")
        if authorization != "Bearer ranked-window-service":
            raise AuthorizationFailure(403, "ignored")
        return {"sub": "service:content-service"}


class _Closures:
    def __init__(self, closed=()) -> None:
        self.closed = set(closed)

    def exists(self, account_id: str) -> bool:
        return account_id in self.closed


class _ExclusionProfiles:
    def read_for_scoring(self, subject_id: str) -> dict:
        return {}


def _client(*, closed=()) -> TestClient:
    facade = Facade(
        store=_Store(),
        ranker=_Ranker(),
        subject_closures=_Closures(closed),
        exclusion_profiles=_ExclusionProfiles(),
        window_id_factory=lambda _key: "window-001",
    )
    app = FastAPI()
    app.include_router(
        build_router(
            facade_provider=lambda _request: facade,
            token_verifier=_Verifier(),
        )
    )
    return TestClient(app)


def _headers(idempotency_key: str = "request-001") -> dict[str, str]:
    return {
        "Authorization": "Bearer ranked-window-service",
        "Idempotency-Key": idempotency_key,
    }


def test_create_replay_and_continue_ranked_window() -> None:
    client = _client()
    body = {"subjectId": "persona-001", "scenario": "content_feed", "limit": 2}
    created = client.post(
        "/internal/recommendation/ranked-pages",
        headers=_headers(),
        json=body,
    )
    assert created.status_code == 200
    assert [item["contentId"] for item in created.json()["items"]] == ["post-0", "post-1"]
    assert created.json()["nextOrdinal"] == 2
    assert created.json()["modelReleaseId"] == "release-001"
    assert created.json()["items"][0]["featureSnapshotDigest"] == "feature-digest-0"

    replay = client.post(
        "/internal/recommendation/ranked-pages",
        headers=_headers(),
        json=body,
    )
    assert replay.json() == created.json()

    continued = client.get(
        "/internal/recommendation/ranked-pages/window-001",
        headers={"Authorization": "Bearer ranked-window-service"},
        params={"subjectId": "persona-001", "fromOrdinal": 2, "limit": 2},
    )
    assert continued.status_code == 200
    assert [item["ordinal"] for item in continued.json()["items"]] == [2, 3]
    assert continued.json()["nextOrdinal"] == 4

    wrong_subject = client.get(
        "/internal/recommendation/ranked-pages/window-001",
        headers={"Authorization": "Bearer ranked-window-service"},
        params={"subjectId": "persona-other", "fromOrdinal": 2, "limit": 2},
    )
    assert wrong_subject.status_code == 404


def test_ranked_window_rejects_auth_invalid_body_and_idempotency_conflict() -> None:
    client = _client()
    body = {"subjectId": "persona-001", "scenario": "content_feed", "limit": 2}
    unauthorized = client.post("/internal/recommendation/ranked-pages", json=body)
    assert unauthorized.status_code == 401
    assert unauthorized.json()["detail"]["code"].endswith("ranked_window_unauthorized")

    invalid = client.post(
        "/internal/recommendation/ranked-pages",
        headers=_headers(),
        json={**body, "unknown": True},
    )
    assert invalid.status_code == 400
    assert invalid.json()["detail"]["code"].endswith("ranked_window_invalid_argument")

    assert client.post(
        "/internal/recommendation/ranked-pages",
        headers=_headers(),
        json=body,
    ).status_code == 200
    conflict = client.post(
        "/internal/recommendation/ranked-pages",
        headers=_headers(),
        json={**body, "subjectId": "persona-other"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"].endswith("ranked_window_conflict")


def test_ranked_window_returns_terminal_subject_closed_error() -> None:
    client = _client(closed={"account-closed"})
    response = client.post(
        "/internal/recommendation/ranked-pages",
        headers=_headers(),
        json={"subjectId": "account-closed", "scenario": "content_feed", "limit": 2},
    )
    assert response.status_code == 410
    assert response.json()["detail"]["code"].endswith("ranked_window_subject_closed")
