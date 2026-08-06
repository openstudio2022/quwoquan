from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from generated.recommendation.recommendation_model_release.api.operations import (
    BATCH_SCORE_RECOMMENDATION_CANDIDATES_PATH,
    SCORE_RECOMMENDATION_CANDIDATES_PATH,
)
from generated.recommendation.recommendation_model_release.models.request_response import (
    BatchModelScoreRequest,
    BatchModelScoreResponse,
    ModelScoreRequest,
    ModelScoreResponse,
)
from internal.recommendation.recommendation_model_release.application.scoring_facade import (
    RecommendationScoringQueryFacade,
    UnsupportedScenarioError,
)
from security.service_authorization import AuthorizationFailure, ServiceTokenVerifier


INVALID_ARGUMENT_CODE = "RECOMMENDATION.USER.invalid_argument"
SCORING_FAILED_CODE = "RECOMMENDATION.SYSTEM.scoring_failed"


def _http_error(status: int, code: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"code": code, "context": {"attributes": {}}},
    )


def build_scoring_router(
    *,
    facade: RecommendationScoringQueryFacade,
    token_verifier: ServiceTokenVerifier,
    record_request: Callable[[str, str], None],
    observe_duration: Callable[[str, float], None],
) -> APIRouter:
    if facade is None:
        raise ValueError("recommendation scoring facade is required")
    router = APIRouter()

    def require_scoring_service(request: Request) -> dict[str, Any]:
        try:
            return token_verifier.verify(
                request.headers.get("Authorization"),
                required_scope="recommendation.model.score",
            )
        except AuthorizationFailure as failure:
            raise _http_error(failure.status_code, failure.code) from None

    def execute(
        *,
        path: str,
        callback: Callable[[], ModelScoreResponse | BatchModelScoreResponse],
    ) -> ModelScoreResponse | BatchModelScoreResponse:
        started = time.perf_counter()
        try:
            result = callback()
        except UnsupportedScenarioError:
            record_request(path, "400")
            raise _http_error(400, INVALID_ARGUMENT_CODE) from None
        except HTTPException:
            raise
        except Exception:
            record_request(path, "500")
            raise _http_error(500, SCORING_FAILED_CODE) from None
        release_id = getattr(result, "modelReleaseId", None)
        observe_duration(str(release_id or "batch_or_rule"), time.perf_counter() - started)
        record_request(path, "200")
        return result

    @router.post(
        SCORE_RECOMMENDATION_CANDIDATES_PATH,
        response_model=ModelScoreResponse,
    )
    def score(
        body: ModelScoreRequest,
        _principal: dict[str, Any] = Depends(require_scoring_service),
    ) -> ModelScoreResponse:
        return execute(
            path=SCORE_RECOMMENDATION_CANDIDATES_PATH,
            callback=lambda: facade.score(body),
        )

    @router.post(
        BATCH_SCORE_RECOMMENDATION_CANDIDATES_PATH,
        response_model=BatchModelScoreResponse,
    )
    def batch_score(
        body: BatchModelScoreRequest,
        _principal: dict[str, Any] = Depends(require_scoring_service),
    ) -> BatchModelScoreResponse:
        return execute(
            path=BATCH_SCORE_RECOMMENDATION_CANDIDATES_PATH,
            callback=lambda: facade.batch_score(body),
        )

    return router
