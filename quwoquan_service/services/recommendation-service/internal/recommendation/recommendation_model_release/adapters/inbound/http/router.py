from __future__ import annotations

import time
from typing import Any, Protocol

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from prometheus_client import Counter, Histogram
from pydantic import ValidationError

from generated.recommendation.recommendation_model_release.api.operations import (
    ACTIVATE_RECOMMENDATION_MODEL_RELEASE_PATH,
    STAGE_RECOMMENDATION_MODEL_RELEASE_PATH,
)
from generated.recommendation.recommendation_model_release.models.request_response import (
    ActivateRecommendationModelReleaseCommand,
    RecommendationModelReleaseCommandResult,
    StageRecommendationModelReleaseCommand,
)
from internal.recommendation.recommendation_model_release.application.command_facade import (
    RecommendationModelReleaseCommandFacade,
)
from internal.recommendation.recommendation_model_release.domain.model import (
    InvalidCommandError,
)
from internal.recommendation.recommendation_model_release.infrastructure.mongo_release_store import (
    ModelReleaseConflictError,
)
from security.service_authorization import AuthorizationFailure, ServiceTokenVerifier


MODEL_RELEASE_SCOPE = "recommendation.model.manage"
UNAUTHORIZED_CODE = "RECOMMENDATION.USER.unauthorized"
FORBIDDEN_CODE = "RECOMMENDATION.USER.forbidden"
INVALID_ARGUMENT_CODE = "RECOMMENDATION.USER.invalid_argument"
CONFLICT_CODE = "RECOMMENDATION.USER.model_release_conflict"
WRITE_FAILED_CODE = "RECOMMENDATION.SYSTEM.model_registry_write_failed"

_command_total = Counter(
    "recommendation_model_release_command",
    "Recommendation model release command outcomes.",
    ["operation", "outcome", "replayed"],
)
_command_duration_seconds = Histogram(
    "recommendation_model_release_command_duration_seconds",
    "Recommendation model release command latency.",
    ["operation", "outcome"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 3.0],
)


class FacadeProvider(Protocol):
    def __call__(self, request: Request) -> RecommendationModelReleaseCommandFacade: ...


def _http_error(status: int, code: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"code": code, "context": {"attributes": {}}},
    )


def build_router(
    *,
    facade_provider: FacadeProvider,
    token_verifier: ServiceTokenVerifier,
) -> APIRouter:
    router = APIRouter()

    def require_model_release_service(request: Request) -> dict[str, Any]:
        try:
            return token_verifier.verify(
                request.headers.get("Authorization"),
                required_scope=MODEL_RELEASE_SCOPE,
            )
        except AuthorizationFailure as failure:
            code = UNAUTHORIZED_CODE if failure.status_code == 401 else FORBIDDEN_CODE
            raise _http_error(failure.status_code, code) from None

    def execute(
        *,
        operation: str,
        callback: Any,
    ) -> RecommendationModelReleaseCommandResult:
        started = time.perf_counter()
        outcome = "failed"
        replayed = "false"
        try:
            result = callback()
            replayed = "true" if result.idempotentReplay else "false"
            outcome = "ok"
            return result
        except (ValidationError, InvalidCommandError, ValueError):
            outcome = "invalid_argument"
            raise _http_error(400, INVALID_ARGUMENT_CODE) from None
        except ModelReleaseConflictError:
            outcome = "conflict"
            raise _http_error(409, CONFLICT_CODE) from None
        except HTTPException:
            raise
        except Exception:
            raise _http_error(500, WRITE_FAILED_CODE) from None
        finally:
            _command_total.labels(
                operation=operation,
                outcome=outcome,
                replayed=replayed,
            ).inc()
            _command_duration_seconds.labels(
                operation=operation,
                outcome=outcome,
            ).observe(time.perf_counter() - started)

    @router.post(
        STAGE_RECOMMENDATION_MODEL_RELEASE_PATH,
        response_model=RecommendationModelReleaseCommandResult,
    )
    def stage_model_release(
        request: Request,
        body: Any = Body(...),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        _principal: dict[str, Any] = Depends(require_model_release_service),
    ) -> RecommendationModelReleaseCommandResult:
        def command() -> RecommendationModelReleaseCommandResult:
            if not isinstance(body, dict) or "idempotencyKey" in body:
                raise InvalidCommandError(
                    "request body must not supply injected fields"
                )
            model = StageRecommendationModelReleaseCommand.model_validate(
                {**body, "idempotencyKey": idempotency_key}
            )
            return facade_provider(request).stage(model)

        return execute(operation="stage", callback=command)

    @router.post(
        ACTIVATE_RECOMMENDATION_MODEL_RELEASE_PATH,
        response_model=RecommendationModelReleaseCommandResult,
    )
    def activate_model_release(
        request: Request,
        body: Any = Body(...),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        _principal: dict[str, Any] = Depends(require_model_release_service),
    ) -> RecommendationModelReleaseCommandResult:
        def command() -> RecommendationModelReleaseCommandResult:
            if not isinstance(body, dict) or "idempotencyKey" in body:
                raise InvalidCommandError(
                    "request body must not supply injected fields"
                )
            model = ActivateRecommendationModelReleaseCommand.model_validate(
                {**body, "idempotencyKey": idempotency_key}
            )
            return facade_provider(request).activate(model)

        return execute(operation="activate", callback=command)

    return router
