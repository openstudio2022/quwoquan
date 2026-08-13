# spec_ref: specs/feature-tree/recommendation-platform/rec-model-service/spec.md#sit-001
"""model release 生命周期与评分 HTTP 错误码合约。

contracts/recommendation/recommendation_model_release/errors.yaml 声明的
写路径错误码逐一由真实负例触发,断言 HTTP 响应携带完整 canonical code:
registry compare-and-swap 冲突 -> 409、registry 写失败 -> 500、评分运行时
失败 -> 500。
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from generated.recommendation.recommendation_model_release.api.operations import (
    ACTIVATE_RECOMMENDATION_MODEL_RELEASE_PATH,
    SCORE_RECOMMENDATION_CANDIDATES_PATH,
)
from internal.recommendation.recommendation_model_release.adapters.inbound.http.router import (
    build_router,
)
from internal.recommendation.recommendation_model_release.adapters.inbound.http.scoring_router import (
    build_scoring_router,
)
from internal.recommendation.recommendation_model_release.application.scoring_facade import (
    RecommendationScoringQueryFacade,
)
from internal.recommendation.recommendation_model_release.infrastructure.mongo_release_store import (
    ModelReleaseConflictError,
)

CONFLICT_CODE = "RECOMMENDATION.USER.model_release_conflict"
WRITE_FAILED_CODE = "RECOMMENDATION.SYSTEM.model_registry_write_failed"
SCORING_FAILED_CODE = "RECOMMENDATION.SYSTEM.scoring_failed"


class _ManageTokenVerifier:
    def verify(self, authorization, *, required_scope):
        assert authorization == "Bearer local-contract"
        assert required_scope == "recommendation.model.manage"
        return {"sub": "service:local-contract"}


class _ScoreTokenVerifier:
    def verify(self, authorization, *, required_scope):
        assert authorization == "Bearer local-contract"
        assert required_scope == "recommendation.model.score"
        return {"sub": "service:local-contract"}


class _ConflictingFacade:
    """registry compare-and-swap 失败:期望的当前激活发布已被并发替换。"""

    def activate(self, _command):
        raise ModelReleaseConflictError(
            "expectedActiveReleaseId no longer matches the active release"
        )


class _UnavailableRegistryFacade:
    """registry 存储不可用:激活写入以基础设施异常失败。"""

    def activate(self, _command):
        raise RuntimeError("model release registry write unavailable")


class _BrokenRuntimeRegistry:
    """模型运行时解析失败:评分请求无法完成。"""

    def resolve(self, _scenario, _release):
        raise RuntimeError("model runtime resolution failed")

    def supported_scenarios(self) -> tuple[str, ...]:
        return ("content_feed",)


def _release_client(facade) -> TestClient:
    app = FastAPI()
    app.include_router(
        build_router(
            facade_provider=lambda _request: facade,
            token_verifier=_ManageTokenVerifier(),
        )
    )
    return TestClient(app)


def _activate(client: TestClient):
    return client.post(
        ACTIVATE_RECOMMENDATION_MODEL_RELEASE_PATH,
        headers={
            "Authorization": "Bearer local-contract",
            "Idempotency-Key": "idem-activate-001",
        },
        json={
            "releaseId": "release-001",
            "scenario": "content_feed",
            "expectedActiveReleaseId": "release-000",
        },
    )


def test_activate_cas_conflict_emits_the_declared_conflict_code() -> None:
    response = _activate(_release_client(_ConflictingFacade()))
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == CONFLICT_CODE


def test_registry_outage_emits_the_declared_write_failed_code() -> None:
    response = _activate(_release_client(_UnavailableRegistryFacade()))
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == WRITE_FAILED_CODE


def test_scoring_runtime_failure_emits_the_declared_scoring_failed_code() -> None:
    facade = RecommendationScoringQueryFacade(
        _BrokenRuntimeRegistry(), lambda _request, _kind, invoke: invoke()
    )
    app = FastAPI()
    app.include_router(
        build_scoring_router(
            facade=facade,
            token_verifier=_ScoreTokenVerifier(),
            record_request=lambda _path, _outcome: None,
            observe_duration=lambda _release, _duration: None,
        )
    )
    response = TestClient(app).post(
        SCORE_RECOMMENDATION_CANDIDATES_PATH,
        headers={"Authorization": "Bearer local-contract"},
        json={
            "scenario": "content_feed",
            "userId": "persona-001",
            "sessionId": "session-001",
            "candidates": [{"contentId": "post-001"}],
        },
    )
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == SCORING_FAILED_CODE
