from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from internal.recommendation.recommendation_model_release.adapters.inbound.http.router import (
    build_router,
)
from internal.recommendation.recommendation_model_release.application.command_facade import (
    RecommendationModelReleaseCommandFacade,
)
from internal.recommendation.recommendation_model_release.domain.model import (
    CommandResult,
)
from security.service_authorization import AuthorizationFailure


class _Verifier:
    def verify(self, authorization, *, required_scope):
        assert required_scope == "recommendation.model.manage"
        if authorization is None:
            raise AuthorizationFailure(401, "ignored")
        if authorization != "Bearer model-release-manager":
            raise AuthorizationFailure(403, "ignored")
        return {"sub": "service:release-controller"}


class _Store:
    def __init__(self) -> None:
        self.staged = {}
        self.active = {}

    def stage(self, command):
        self.staged[command.release_id] = command
        return CommandResult(
            release_id=command.release_id,
            scenario=command.scenario,
            status="staged",
            version=1,
            active_release_id=self.active.get(command.scenario),
        )

    def activate(self, command):
        if self.active.get(command.scenario) != command.expected_active_release_id:
            raise AssertionError("test command must use exact active release")
        assert command.release_id in self.staged
        self.active[command.scenario] = command.release_id
        return CommandResult(
            release_id=command.release_id,
            scenario=command.scenario,
            status="active",
            version=2,
            active_release_id=command.release_id,
        )


def _client() -> TestClient:
    facade = RecommendationModelReleaseCommandFacade(_Store())
    app = FastAPI()
    app.include_router(
        build_router(
            facade_provider=lambda _request: facade,
            token_verifier=_Verifier(),
        )
    )
    return TestClient(app)


def _headers(key: str) -> dict[str, str]:
    return {
        "Authorization": "Bearer model-release-manager",
        "Idempotency-Key": key,
    }


def _stage_body(release_id: str) -> dict:
    return {
        "releaseId": release_id,
        "scenario": "content_feed",
        "modelDigest": "a" * 64,
        "featureContractDigest": "b" * 64,
        "artifactUri": f"s3://quwoquan-models/models/content_feed/{release_id}/model.txt",
        "verificationDigest": "c" * 64,
        "evaluationMetrics": {"auc": 0.91},
    }


def test_stage_and_rollback_use_generated_single_track_contracts() -> None:
    client = _client()
    first = client.post(
        "/internal/recommendation/model-releases:stage",
        headers=_headers("stage-first"),
        json=_stage_body("release-first"),
    )
    assert first.status_code == 200
    assert first.json()["status"] == "staged"

    activated = client.post(
        "/internal/recommendation/model-releases:activate",
        headers=_headers("activate-first"),
        json={
            "releaseId": "release-first",
            "scenario": "content_feed",
            "expectedActiveReleaseId": None,
        },
    )
    assert activated.status_code == 200

    assert client.post(
        "/internal/recommendation/model-releases:stage",
        headers=_headers("stage-previous"),
        json=_stage_body("release-previous"),
    ).status_code == 200
    rollback = client.post(
        "/internal/recommendation/model-releases:activate",
        headers=_headers("activate-previous"),
        json={
            "releaseId": "release-previous",
            "scenario": "content_feed",
            "expectedActiveReleaseId": "release-first",
        },
    )
    assert rollback.status_code == 200
    assert rollback.json()["activeReleaseId"] == "release-previous"


def test_command_adapter_fails_closed_for_auth_header_injection_and_digest() -> None:
    client = _client()
    assert client.post(
        "/internal/recommendation/model-releases:stage",
        json=_stage_body("release-first"),
    ).status_code == 401

    injected = client.post(
        "/internal/recommendation/model-releases:stage",
        headers=_headers("stage-first"),
        json={**_stage_body("release-first"), "idempotencyKey": "body-key"},
    )
    assert injected.status_code == 400

    invalid = client.post(
        "/internal/recommendation/model-releases:stage",
        headers=_headers("stage-invalid"),
        json={**_stage_body("release-first"), "modelDigest": "not-a-digest"},
    )
    assert invalid.status_code == 400
