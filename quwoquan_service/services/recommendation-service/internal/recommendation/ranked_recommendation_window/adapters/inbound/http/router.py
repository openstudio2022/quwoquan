from __future__ import annotations

from datetime import datetime
import time
from typing import Any, Protocol

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request
from prometheus_client import Counter, Histogram
from pydantic import ValidationError

from generated.recommendation.ranked_recommendation_window.api.operations import (
    CREATE_RANKED_RECOMMENDATION_WINDOW_PATH,
    GET_RANKED_RECOMMENDATION_PAGE_PATH,
)
from generated.recommendation.ranked_recommendation_window.models.request_response import (
    CreateRankedRecommendationWindowCommand,
    GetRankedRecommendationPageQuery,
    RecommendationObjectCard,
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
        windowId=page.window_id,
        scenario=page.scenario,
        experimentBucket=page.experiment_bucket,
        modelBucket=page.model_bucket,
        modelChannel=page.model_channel,
        modelReleaseId=page.model_release_id,
        policyDigest=page.policy_digest,
        rankingSnapshotDigest=page.ranking_snapshot_digest,
        featureSnapshotAt=datetime.fromisoformat(page.feature_snapshot_at),
        userFeatureSnapshot=page.user_feature_snapshot,
        items=[
            RankedRecommendationItem(
                ordinal=item.ordinal,
                contentId=item.content_id,
                score=item.score,
                featureSnapshotDigest=item.feature_snapshot_digest,
                itemFeatureSnapshot=dict(item.item_feature_snapshot),
            )
            for item in page.items
        ],
        objectCards=[
            RecommendationObjectCard(
                objectKind=card.object_kind,
                objectId=card.object_id,
                title=card.title,
                subtitle=card.subtitle,
                coverUrl=card.cover_url,
                tagRefs=list(card.tag_refs),
                reasonKey=card.reason_key,
                recallPath=card.recall_path,
            )
            for card in page.object_cards
        ],
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

    @router.get(
        GET_RANKED_RECOMMENDATION_PAGE_PATH,
        response_model=RankedRecommendationPage,
    )
    def get_ranked_window_page(
        request: Request,
        windowId: str,
        subjectId: str = Query(...),
        fromOrdinal: int = Query(default=0, ge=0),
        limit: int = Query(default=20, ge=1, le=100),
        _principal: dict[str, Any] = Depends(require_ranked_window_service),
    ) -> RankedRecommendationPage:
        started = time.perf_counter()
        outcome = "failed"
        try:
            query = GetRankedRecommendationPageQuery.model_validate(
                {
                    "subjectId": subjectId,
                    "windowId": windowId,
                    "fromOrdinal": fromOrdinal,
                    "limit": limit,
                }
            )
            page = facade_provider(request).read_page(
                subject_id=query.subjectId,
                window_id=query.windowId,
                from_ordinal=query.fromOrdinal if query.fromOrdinal is not None else 0,
                limit=query.limit if query.limit is not None else 20,
            )
            outcome = "ok"
            return _wire_page(page)
        except (ValidationError, ValueError):
            outcome = "invalid_argument"
            raise _http_error(400, INVALID_ARGUMENT_CODE) from None
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

    return router
