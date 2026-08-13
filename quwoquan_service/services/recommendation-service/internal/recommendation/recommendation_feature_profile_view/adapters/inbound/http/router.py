from __future__ import annotations

import re
import time
from typing import Any, Protocol

from fastapi import APIRouter, Depends, HTTPException, Request
from prometheus_client import Counter, Histogram

from generated.recommendation.recommendation_feature_profile_view.api.operations import (
    GET_RECOMMENDATION_FLYWHEEL_FUNNEL_PATH,
    GET_RECOMMENDATION_GATHERING_SOCIAL_PROOF_PATH,
    GET_RECOMMENDATION_INTERSECTION_SUPPLY_PATH,
    GET_RECOMMENDATION_AUTHOR_IMPACT_PATH,
    LIST_RECOMMENDATION_OBJECT_INTERSECTIONS_PATH,
    LIST_RECOMMENDATION_AUTHOR_IMPACT_EVIDENCE_PATH,
    LIST_RECOMMENDATION_SUBJECT_INTERSECTIONS_PATH,
)
from generated.recommendation.recommendation_feature_profile_view.models.request_response import (
    GetRecommendationIntersectionSupplyQuery,
    GetRecommendationAuthorImpactQuery,
    IntersectionReason,
    ListRecommendationObjectIntersectionsQuery,
    ListRecommendationAuthorImpactEvidenceQuery,
    ListRecommendationSubjectIntersectionsQuery,
    RecommendationIntersectionReasonSlice,
    RecommendationIntersectionSupply,
    RecommendationObjectIntersectionReasonSlice,
    RecommendationAuthorImpactEvidence,
    RecommendationAuthorImpactEvidencePage,
    RecommendationAuthorImpactItem,
    RecommendationAuthorImpactSummary,
    RecommendationGatheringSocialProofSummary,
    RecommendationFlywheelFunnelSnapshot,
)
from internal.recommendation.recommendation_feature_profile_view.application.author_impact_reader import (
    AuthorImpactEvidencePage as DomainEvidencePage,
    AuthorImpactSummary as DomainSummary,
    Reader,
)
from internal.recommendation.recommendation_feature_profile_view.application.intersection_reader import (
    Reader as IntersectionReader,
    SubjectClosedError,
)
from security.service_authorization import AuthorizationFailure, ServiceTokenVerifier


FEATURE_PROFILE_READ_SCOPE = "recommendation.feature_profile.read"
UNAUTHORIZED_CODE = "RECOMMENDATION.USER.feature_profile_unauthorized"
FORBIDDEN_CODE = "RECOMMENDATION.USER.feature_profile_forbidden"
INVALID_ARGUMENT_CODE = "RECOMMENDATION.USER.feature_profile_invalid_argument"
SUBJECT_CLOSED_CODE = "RECOMMENDATION.USER.feature_profile_subject_closed"
READ_FAILED_CODE = "RECOMMENDATION.SYSTEM.feature_profile_read_failed"

_read_total = Counter(
    "recommendation_author_impact_reader",
    "Recommendation author impact reader outcomes.",
    ["operation", "outcome"],
)
_read_duration_seconds = Histogram(
    "recommendation_author_impact_reader_duration_seconds",
    "Recommendation author impact reader latency.",
    ["operation", "outcome"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.5],
)


class ReaderProvider(Protocol):
    def __call__(self, request: Request) -> Reader: ...


class IntersectionReaderProvider(Protocol):
    def __call__(self, request: Request) -> IntersectionReader: ...


def _http_error(status: int, code: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"code": code, "context": {"attributes": {}}},
    )


def _required_query_instant(request: Request, name: str):
    """必填 ISO-8601 时间参数；缺失或非法即 invalid_argument。"""
    from datetime import datetime

    raw = (_single_query_value(request, name) or "").strip()
    if not raw:
        raise ValueError(f"query {name} is required")
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"query {name} must be timezone-aware")
    return parsed


def _single_query_value(request: Request, name: str) -> str | None:
    values = request.query_params.getlist(name)
    if len(values) > 1:
        raise ValueError(f"duplicate query parameter: {name}")
    if not values:
        return None
    value = values[0].strip()
    if not value:
        raise ValueError(f"empty query parameter: {name}")
    return value


def _bounded_query_int(
    request: Request,
    name: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = _single_query_value(request, name)
    if raw is None:
        return default
    if re.fullmatch(r"[0-9]+", raw) is None:
        raise ValueError(f"invalid integer query parameter: {name}")
    value = int(raw)
    if value < minimum or value > maximum:
        raise ValueError(f"out-of-range query parameter: {name}")
    return value


def _wire_summary(summary: DomainSummary) -> RecommendationAuthorImpactSummary:
    return RecommendationAuthorImpactSummary(
        authorId=summary.author_id,
        total=summary.total,
        items=[
            RecommendationAuthorImpactItem(
                impactId=item.impact_id,
                helpType=item.help_type,
                action=item.action,
                intersectionDimension=item.intersection_dimension or None,
                tagRef=item.tag_ref or None,
                source=item.source,
                count=item.count,
                updatedAt=item.updated_at,
                representativeContentId=item.representative_content_id or None,
            )
            for item in summary.items
        ],
    )


def _wire_evidence_page(
    page: DomainEvidencePage,
) -> RecommendationAuthorImpactEvidencePage:
    return RecommendationAuthorImpactEvidencePage(
        impactId=page.impact_id,
        totalCount=page.total_count,
        items=[
            RecommendationAuthorImpactEvidence(
                evidenceId=item.evidence_id,
                impactId=item.impact_id,
                contentId=item.content_id,
                contentType=item.content_type or None,
                helpType=item.help_type,
                action=item.action,
                intersectionDimension=item.intersection_dimension or None,
                occurredAt=item.occurred_at,
            )
            for item in page.items
        ],
        nextCursor=page.next_cursor,
        hasMore=page.has_more,
    )


def build_router(
    *,
    reader_provider: ReaderProvider,
    intersection_reader_provider: IntersectionReaderProvider,
    token_verifier: ServiceTokenVerifier,
) -> APIRouter:
    router = APIRouter()

    def require_feature_profile_reader(request: Request) -> dict[str, Any]:
        try:
            return token_verifier.verify(
                request.headers.get("Authorization"),
                required_scope=FEATURE_PROFILE_READ_SCOPE,
            )
        except AuthorizationFailure as failure:
            code = UNAUTHORIZED_CODE if failure.status_code == 401 else FORBIDDEN_CODE
            raise _http_error(failure.status_code, code) from None

    @router.get(
        LIST_RECOMMENDATION_SUBJECT_INTERSECTIONS_PATH,
        response_model=RecommendationIntersectionReasonSlice,
    )
    def list_subject_intersections(
        request: Request,
        subjectId: str,
        _principal: dict[str, Any] = Depends(require_feature_profile_reader),
    ) -> RecommendationIntersectionReasonSlice:
        started = time.perf_counter()
        outcome = "failed"
        try:
            query = ListRecommendationSubjectIntersectionsQuery(
                subjectId=subjectId,
                intersectionClass=_single_query_value(request, "intersectionClass"),
                channel=_single_query_value(request, "channel"),
            )
            snapshot = intersection_reader_provider(request).list_subject_intersections(
                subject_id=query.subjectId,
                intersection_class=query.intersectionClass,
                channel=query.channel,
            )
            outcome = "ok"
            return RecommendationIntersectionReasonSlice(
                subjectId=snapshot.subject_id,
                intersectionClass=snapshot.intersection_class,
                channel=snapshot.channel or None,
                reasons=[IntersectionReason.model_validate(reason) for reason in snapshot.reasons],
                generatedAt=snapshot.generated_at,
            )
        except ValueError:
            outcome = "invalid_argument"
            raise _http_error(400, INVALID_ARGUMENT_CODE) from None
        except SubjectClosedError:
            outcome = "subject_closed"
            raise _http_error(410, SUBJECT_CLOSED_CODE) from None
        except HTTPException:
            raise
        except Exception:
            raise _http_error(500, READ_FAILED_CODE) from None
        finally:
            _read_total.labels(operation="subject_intersections", outcome=outcome).inc()
            _read_duration_seconds.labels(
                operation="subject_intersections", outcome=outcome
            ).observe(time.perf_counter() - started)

    @router.get(
        LIST_RECOMMENDATION_OBJECT_INTERSECTIONS_PATH,
        response_model=RecommendationObjectIntersectionReasonSlice,
    )
    def list_object_intersections(
        request: Request,
        subjectId: str,
        objectType: str,
        objectId: str,
        _principal: dict[str, Any] = Depends(require_feature_profile_reader),
    ) -> RecommendationObjectIntersectionReasonSlice:
        started = time.perf_counter()
        outcome = "failed"
        try:
            query = ListRecommendationObjectIntersectionsQuery(
                subjectId=subjectId,
                objectType=objectType,
                objectId=objectId,
            )
            snapshot = intersection_reader_provider(request).list_object_intersections(
                subject_id=query.subjectId,
                object_type=query.objectType,
                object_id=query.objectId,
            )
            outcome = "ok"
            return RecommendationObjectIntersectionReasonSlice(
                subjectId=snapshot.subject_id,
                objectType=snapshot.object_type,
                objectId=snapshot.object_id,
                reasons=[IntersectionReason.model_validate(reason) for reason in snapshot.reasons],
                generatedAt=snapshot.generated_at,
            )
        except ValueError:
            outcome = "invalid_argument"
            raise _http_error(400, INVALID_ARGUMENT_CODE) from None
        except SubjectClosedError:
            outcome = "subject_closed"
            raise _http_error(410, SUBJECT_CLOSED_CODE) from None
        except HTTPException:
            raise
        except Exception:
            raise _http_error(500, READ_FAILED_CODE) from None
        finally:
            _read_total.labels(operation="object_intersections", outcome=outcome).inc()
            _read_duration_seconds.labels(
                operation="object_intersections", outcome=outcome
            ).observe(time.perf_counter() - started)

    @router.get(
        GET_RECOMMENDATION_FLYWHEEL_FUNNEL_PATH,
        response_model=RecommendationFlywheelFunnelSnapshot,
    )
    def get_flywheel_funnel(
        request: Request,
        _principal: dict[str, Any] = Depends(require_feature_profile_reader),
    ) -> RecommendationFlywheelFunnelSnapshot:
        started = time.perf_counter()
        outcome = "failed"
        try:
            window_from = _required_query_instant(request, "windowFrom")
            window_to = _required_query_instant(request, "windowTo")
            counts = intersection_reader_provider(request).get_flywheel_funnel(
                window_from=window_from,
                window_to=window_to,
                source_object_kind=_single_query_value(request, "sourceObjectKind")
                or "",
                source_object_id=_single_query_value(request, "sourceObjectId")
                or "",
                capacity_tier=_single_query_value(request, "capacityTier") or "",
                tag_ref=_single_query_value(request, "tagRef") or "",
            )
            outcome = "ok"
            return RecommendationFlywheelFunnelSnapshot(
                windowFrom=window_from,
                windowTo=window_to,
                wishlistedPersonaCount=int(counts["wishlistedPersonaCount"]),
                wishlistToJoinedCount=int(counts["wishlistToJoinedCount"]),
                publishedCount=int(counts["publishedCount"]),
                formedCount=int(counts["formedCount"]),
                experiencedCount=int(counts["experiencedCount"]),
                facilitationNotifiedCount=int(counts["facilitationNotifiedCount"]),
                creatorRepublishedCount=int(counts["creatorRepublishedCount"]),
                truncated=bool(counts["truncated"]),
            )
        except ValueError:
            outcome = "invalid_argument"
            raise _http_error(400, INVALID_ARGUMENT_CODE) from None
        except HTTPException:
            raise
        except Exception:
            raise _http_error(500, READ_FAILED_CODE) from None
        finally:
            _read_total.labels(operation="flywheel_funnel", outcome=outcome).inc()
            _read_duration_seconds.labels(
                operation="flywheel_funnel", outcome=outcome
            ).observe(time.perf_counter() - started)

    @router.get(
        GET_RECOMMENDATION_GATHERING_SOCIAL_PROOF_PATH,
        response_model=RecommendationGatheringSocialProofSummary,
    )
    def get_gathering_social_proof(
        request: Request,
        anchorKind: str,
        objectId: str,
        _principal: dict[str, Any] = Depends(require_feature_profile_reader),
    ) -> RecommendationGatheringSocialProofSummary:
        started = time.perf_counter()
        outcome = "failed"
        try:
            counts = intersection_reader_provider(request).get_gathering_social_proof(
                anchor_kind=anchorKind,
                object_id=objectId,
            )
            outcome = "ok"
            return RecommendationGatheringSocialProofSummary(
                anchorKind=anchorKind.strip(),
                objectId=objectId.strip(),
                publishedCount=int(counts.get("publishedCount", 0)),
                formedCount=int(counts.get("formedCount", 0)),
                experiencedCount=int(counts.get("experiencedCount", 0)),
            )
        except ValueError:
            outcome = "invalid_argument"
            raise _http_error(400, INVALID_ARGUMENT_CODE) from None
        except HTTPException:
            raise
        except Exception:
            raise _http_error(500, READ_FAILED_CODE) from None
        finally:
            _read_total.labels(
                operation="gathering_social_proof", outcome=outcome
            ).inc()
            _read_duration_seconds.labels(
                operation="gathering_social_proof", outcome=outcome
            ).observe(time.perf_counter() - started)

    @router.get(
        GET_RECOMMENDATION_INTERSECTION_SUPPLY_PATH,
        response_model=RecommendationIntersectionSupply,
    )
    def get_intersection_supply(
        request: Request,
        supplyKey: str,
        _principal: dict[str, Any] = Depends(require_feature_profile_reader),
    ) -> RecommendationIntersectionSupply:
        started = time.perf_counter()
        outcome = "failed"
        try:
            query = GetRecommendationIntersectionSupplyQuery(supplyKey=supplyKey)
            snapshot = intersection_reader_provider(request).get_supply(
                supply_key=query.supplyKey
            )
            outcome = "ok"
            return RecommendationIntersectionSupply(
                supplyKey=snapshot.supply_key,
                distinctObjectCount=snapshot.distinct_object_count,
                computedAt=snapshot.computed_at,
            )
        except ValueError:
            outcome = "invalid_argument"
            raise _http_error(400, INVALID_ARGUMENT_CODE) from None
        except HTTPException:
            raise
        except Exception:
            raise _http_error(500, READ_FAILED_CODE) from None
        finally:
            _read_total.labels(operation="intersection_supply", outcome=outcome).inc()
            _read_duration_seconds.labels(
                operation="intersection_supply", outcome=outcome
            ).observe(time.perf_counter() - started)

    @router.get(
        GET_RECOMMENDATION_AUTHOR_IMPACT_PATH,
        response_model=RecommendationAuthorImpactSummary,
    )
    def get_author_impact(
        request: Request,
        authorId: str,
        _principal: dict[str, Any] = Depends(require_feature_profile_reader),
    ) -> RecommendationAuthorImpactSummary:
        started = time.perf_counter()
        outcome = "failed"
        try:
            limit = _bounded_query_int(
                request,
                "limit",
                default=12,
                minimum=1,
                maximum=50,
            )
            query = GetRecommendationAuthorImpactQuery(
                authorId=authorId,
                limit=limit,
            )
            summary = reader_provider(request).get_author_impact(
                author_id=query.authorId,
                limit=query.limit or 12,
            )
            outcome = "ok"
            return _wire_summary(summary)
        except ValueError:
            outcome = "invalid_argument"
            raise _http_error(400, INVALID_ARGUMENT_CODE) from None
        except HTTPException:
            raise
        except Exception:
            raise _http_error(500, READ_FAILED_CODE) from None
        finally:
            _read_total.labels(operation="summary", outcome=outcome).inc()
            _read_duration_seconds.labels(
                operation="summary",
                outcome=outcome,
            ).observe(time.perf_counter() - started)

    @router.get(
        LIST_RECOMMENDATION_AUTHOR_IMPACT_EVIDENCE_PATH,
        response_model=RecommendationAuthorImpactEvidencePage,
    )
    def list_author_impact_evidence(
        request: Request,
        authorId: str,
        impactId: str,
        _principal: dict[str, Any] = Depends(require_feature_profile_reader),
    ) -> RecommendationAuthorImpactEvidencePage:
        started = time.perf_counter()
        outcome = "failed"
        try:
            cursor = _single_query_value(request, "cursor")
            if cursor is not None and len(cursor) > 2048:
                raise ValueError("cursor exceeds the contract maximum")
            limit = _bounded_query_int(
                request,
                "limit",
                default=20,
                minimum=1,
                maximum=50,
            )
            query = ListRecommendationAuthorImpactEvidenceQuery(
                authorId=authorId,
                impactId=impactId,
                cursor=cursor,
                limit=limit,
            )
            page = reader_provider(request).list_author_impact_evidence(
                author_id=query.authorId,
                impact_id=query.impactId,
                cursor=query.cursor,
                limit=query.limit or 20,
            )
            outcome = "ok"
            return _wire_evidence_page(page)
        except ValueError:
            outcome = "invalid_argument"
            raise _http_error(400, INVALID_ARGUMENT_CODE) from None
        except HTTPException:
            raise
        except Exception:
            raise _http_error(500, READ_FAILED_CODE) from None
        finally:
            _read_total.labels(operation="evidence", outcome=outcome).inc()
            _read_duration_seconds.labels(
                operation="evidence",
                outcome=outcome,
            ).observe(time.perf_counter() - started)

    return router
