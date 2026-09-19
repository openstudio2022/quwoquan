from __future__ import annotations

from datetime import datetime
import time
from typing import Any, Protocol

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from prometheus_client import Counter, Histogram
from pydantic import ValidationError

from generated.recommendation.ranked_recommendation_window.api.operations import (
    READ_RECOMMENDATION_RELEASE_READINESS_PATH,
    CREATE_RANKED_RECOMMENDATION_WINDOW_PATH,
    GET_RANKED_RECOMMENDATION_PAGE_PATH,
)
from generated.recommendation.ranked_recommendation_window.models.request_response import (
    ReadRecommendationReleaseReadinessQuery,
    ReleaseQueryReadinessProof,
    CreateRankedRecommendationWindowCommand,
    GetRankedRecommendationPageQuery,
    RankedRecommendationItem,
    RankedRecommendationPage,
)
from internal.recommendation.ranked_recommendation_window.application.facade import (
    Facade,
    IdempotencyConflictError,
    RankedRecommendationPage as DomainPage,
    SubjectClosedError,
)
from security.service_authorization import AuthorizationFailure, ServiceTokenVerifier


RANKED_WINDOW_SCOPE = "recommendation.ranked_page"
UNAUTHORIZED_CODE = "RECOMMENDATION.USER.ranked_window_unauthorized"
FORBIDDEN_CODE = "RECOMMENDATION.USER.ranked_window_forbidden"
INVALID_ARGUMENT_CODE = "RECOMMENDATION.USER.ranked_window_invalid_argument"
NOT_FOUND_CODE = "RECOMMENDATION.USER.ranked_window_not_found"
CONFLICT_CODE = "RECOMMENDATION.USER.ranked_window_conflict"
SUBJECT_CLOSED_CODE = "RECOMMENDATION.USER.ranked_window_subject_closed"
FAILED_CODE = "RECOMMENDATION.SYSTEM.ranked_window_failed"

_create_total = Counter(
    "recommendation_ranked_window_create",
    "Ranked recommendation window create outcomes.",
    ["outcome"],
)
_read_total = Counter(
    "recommendation_ranked_window_read",
    "Ranked recommendation window read outcomes.",
    ["outcome"],
)
_duration_seconds = Histogram(
    "recommendation_ranked_window_duration_seconds",
    "Ranked recommendation window operation latency.",
    ["operation", "outcome"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 0.8, 1.0],
)


class FacadeProvider(Protocol):
    def __call__(self, request: Request) -> Facade: ...


def _http_error(status: int, code: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"code": code, "context": {"attributes": {}}},
    )


def _wire_page(page: DomainPage) -> RankedRecommendationPage:
    return RankedRecommendationPage(
        contentFence=page.content_fence,
        windowId=page.window_id,
        scenario=page.scenario,
        experimentBucket=page.experiment_bucket,
        modelBucket=page.model_bucket,
        modelChannel=page.model_channel,
        modelReleaseId=page.model_release_id,
        policyDigest=page.policy_digest,
        contextDigest=page.context_digest,
        rankingSnapshotDigest=page.ranking_snapshot_digest,
        featureSnapshotAt=datetime.fromisoformat(page.feature_snapshot_at),
        userFeatureSnapshot=page.user_feature_snapshot,
        items=[
            RankedRecommendationItem(
                ordinal=item.ordinal,
                envelope=item.envelope,
                score=item.score,
                featureSnapshotDigest=item.feature_snapshot_digest,
                itemFeatureSnapshot=dict(item.item_feature_snapshot),
            )
            for item in page.items
        ],
        clientPresentationContract=page.client_presentation_contract,
        nextOrdinal=page.next_ordinal,
        expiresAt=datetime.fromisoformat(page.expires_at),
    )


def build_router(
    *,
    facade_provider: FacadeProvider,
    token_verifier: ServiceTokenVerifier,
) -> APIRouter:
    router = APIRouter()

    def require_ranked_window_service(request: Request) -> dict[str, Any]:
        try:
            return token_verifier.verify(
                request.headers.get("Authorization"),
                required_scope=RANKED_WINDOW_SCOPE,
            )
        except AuthorizationFailure as failure:
            code = UNAUTHORIZED_CODE if failure.status_code == 401 else FORBIDDEN_CODE
            raise _http_error(failure.status_code, code) from None

    @router.post(
        CREATE_RANKED_RECOMMENDATION_WINDOW_PATH,
        response_model=RankedRecommendationPage,
    )
    def create_ranked_window(
        request: Request,
        body: Any = Body(...),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        _principal: dict[str, Any] = Depends(require_ranked_window_service),
    ) -> RankedRecommendationPage:
        started = time.perf_counter()
        outcome = "failed"
        try:
            if not isinstance(body, dict) or "idempotencyKey" in body:
                raise ValueError("request body must not supply injected fields")
            command = CreateRankedRecommendationWindowCommand.model_validate(
                {**body, "idempotencyKey": idempotency_key}
            )
            page = facade_provider(request).create_window(
                idempotency_key=command.idempotencyKey,
                subject_id=command.subjectId,
                scenario=command.scenario,
                limit=command.limit,
                content_fence=command.contentFence,
                client_presentation_contract=command.clientPresentationContract,
                viewport_profile=command.viewportProfile,
                device_class=command.deviceClass,
            )
            outcome = "ok"
            return _wire_page(page)
        except (ValidationError, ValueError):
            outcome = "invalid_argument"
            raise _http_error(400, INVALID_ARGUMENT_CODE) from None
        except IdempotencyConflictError:
            outcome = "conflict"
            raise _http_error(409, CONFLICT_CODE) from None
        except SubjectClosedError:
            outcome = "subject_closed"
            raise _http_error(410, SUBJECT_CLOSED_CODE) from None
        except HTTPException:
            raise
        except Exception:
            raise _http_error(500, FAILED_CODE) from None
        finally:
            _create_total.labels(outcome=outcome).inc()
            _duration_seconds.labels(operation="create", outcome=outcome).observe(
                time.perf_counter() - started
            )

    @router.post(
        GET_RANKED_RECOMMENDATION_PAGE_PATH,
        response_model=RankedRecommendationPage,
    )
    def get_ranked_window_page(
        request: Request,
        windowId: str,
        body: Any = Body(...),
        _principal: dict[str, Any] = Depends(require_ranked_window_service),
    ) -> RankedRecommendationPage:
        started = time.perf_counter()
        outcome = "failed"
        try:
            if not isinstance(body, dict) or "windowId" in body:
                raise ValueError("windowId is path-bound only")
            query = GetRankedRecommendationPageQuery.model_validate({**body, "windowId": windowId})
            page = facade_provider(request).read_page(
                subject_id=query.subjectId,
                content_fence=query.contentFence,
                client_presentation_contract=query.clientPresentationContract,
                window_id=query.windowId,
                from_ordinal=query.fromOrdinal if query.fromOrdinal is not None else 0,
                limit=query.limit if query.limit is not None else 20,
            )
            outcome = "ok"
            return _wire_page(page)
        except (ValidationError, ValueError):
            outcome = "invalid_argument"
            raise _http_error(400, INVALID_ARGUMENT_CODE) from None
        except IdempotencyConflictError:
            outcome = "conflict"
            raise _http_error(409, CONFLICT_CODE) from None
        except LookupError:
            outcome = "not_found"
            raise _http_error(404, NOT_FOUND_CODE) from None
        except SubjectClosedError:
            outcome = "subject_closed"
            raise _http_error(410, SUBJECT_CLOSED_CODE) from None
        except HTTPException:
            raise
        except Exception:
            raise _http_error(500, FAILED_CODE) from None
        finally:
            _read_total.labels(outcome=outcome).inc()
            _duration_seconds.labels(operation="read", outcome=outcome).observe(
                time.perf_counter() - started
            )

    @router.post(READ_RECOMMENDATION_RELEASE_READINESS_PATH, response_model=ReleaseQueryReadinessProof)
    def read_release_readiness(request: Request, body: ReadRecommendationReleaseReadinessQuery):
        from internal.recommendation.recommendation_candidate_index_view.application.release_candidate import ReleaseNotReady, ReleaseCandidateError
        try:
            principal = token_verifier.verify(request.headers.get("Authorization"), required_scope="recommendation.release.readiness")
            if principal.get("sub") != "service:content-service":
                raise _http_error(403, FORBIDDEN_CODE)
            return facade_provider(request).read_release_readiness(body)
        except AuthorizationFailure as error:
            raise _http_error(error.status_code, UNAUTHORIZED_CODE if error.status_code == 401 else FORBIDDEN_CODE) from None
        except ReleaseNotReady:
            raise _http_error(409, "RECOMMENDATION.RELEASE.not_ready") from None
        except ReleaseCandidateError:
            raise _http_error(422, "RECOMMENDATION.RELEASE.invalid_candidate") from None
        except HTTPException:
            raise
        except Exception:
            raise _http_error(503, "RECOMMENDATION.RELEASE.unavailable") from None

    return router
