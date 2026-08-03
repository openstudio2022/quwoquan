# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-003
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from internal.recommendation.recommendation_feature_profile_view.adapters.inbound.http.router import (
    FEATURE_PROFILE_READ_SCOPE,
    build_router,
)
from internal.recommendation.recommendation_feature_profile_view.application.author_impact_reader import (
    AuthorImpactEvidence,
    AuthorImpactEvidencePage,
    AuthorImpactItem,
    AuthorImpactSummary,
    Reader,
)
from internal.recommendation.recommendation_feature_profile_view.application.intersection_reader import (
    IntersectionSupplySnapshot,
    ObjectIntersectionSnapshot,
    Reader as IntersectionReader,
    SubjectIntersectionSnapshot,
)
from security.service_authorization import AuthorizationFailure


class _Store:
    def __init__(self) -> None:
        self.summary_args: tuple[str, int] | None = None
        self.evidence_args: tuple[str, str, str | None, int] | None = None

    def read_author_impact(self, author_id: str, limit: int) -> AuthorImpactSummary:
        self.summary_args = (author_id, limit)
        return AuthorImpactSummary(
            author_id=author_id,
            total=1,
            items=(
                AuthorImpactItem(
                    impact_id="impact-001",
                    help_type="decision",
                    action="content_depth",
                    intersection_dimension="content",
                    tag_ref="Topic/travel",
                    source="behavior",
                    count=2,
                    updated_at=datetime(2026, 8, 2, 12, tzinfo=timezone.utc),
                    representative_content_id="post-001",
                ),
            ),
        )

    def read_author_impact_evidence(
        self,
        author_id: str,
        impact_id: str,
        cursor: str | None,
        limit: int,
    ) -> AuthorImpactEvidencePage:
        self.evidence_args = (author_id, impact_id, cursor, limit)
        return AuthorImpactEvidencePage(
            impact_id=impact_id,
            total_count=1,
            items=(
                AuthorImpactEvidence(
                    evidence_id="event-001",
                    impact_id=impact_id,
                    content_id="post-001",
                    content_type="post",
                    help_type="decision",
                    action="content_depth",
                    intersection_dimension="content",
                    occurred_at=datetime(2026, 8, 2, 12, tzinfo=timezone.utc),
                ),
            ),
            next_cursor="next-opaque-cursor",
            has_more=True,
        )

    def read_subject_intersections(
        self, subject_id: str, intersection_class: str, channel: str
    ) -> SubjectIntersectionSnapshot:
        raise AssertionError("author-impact test must not read intersections")

    def read_object_intersections(
        self, subject_id: str, object_type: str, object_id: str
    ) -> ObjectIntersectionSnapshot:
        raise AssertionError("author-impact test must not read intersections")

    def read_intersection_supply(self, supply_key: str) -> IntersectionSupplySnapshot:
        raise AssertionError("author-impact test must not read intersection supply")


class _Verifier:
    def verify(self, authorization: str | None, *, required_scope: str):
        assert required_scope == FEATURE_PROFILE_READ_SCOPE
        if authorization is None:
            raise AuthorizationFailure(401, "ignored")
        if authorization != "Bearer content-service":
            raise AuthorizationFailure(403, "ignored")
        return {"sub": "service:content-service"}


class _NoopMaterializer:
    pass


class _OpenSubjects:
    def exists(self, _subject_id: str) -> bool:
        return False


def _client() -> tuple[TestClient, _Store]:
    store = _Store()
    reader = Reader(store)
    intersection_reader = IntersectionReader(
        store,
        _NoopMaterializer(),
        _OpenSubjects(),
    )
    app = FastAPI()
    app.include_router(
        build_router(
            reader_provider=lambda _request: reader,
            intersection_reader_provider=lambda _request: intersection_reader,
            token_verifier=_Verifier(),
        )
    )
    return TestClient(app), store


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer content-service"}


def test_author_impact_http_uses_typed_summary_and_evidence_contracts() -> None:
    client, store = _client()

    summary = client.get(
        "/internal/recommendation/authors/author-001/impact",
        headers=_headers(),
        params={"limit": "7"},
    )
    assert summary.status_code == 200
    assert summary.json()["items"][0]["representativeContentId"] == "post-001"
    assert store.summary_args == ("author-001", 7)

    evidence = client.get(
        "/internal/recommendation/authors/author-001/impact/impact-001/evidence",
        headers=_headers(),
        params={"cursor": "opaque-cursor", "limit": "20"},
    )
    assert evidence.status_code == 200
    assert evidence.json()["nextCursor"] == "next-opaque-cursor"
    assert store.evidence_args == (
        "author-001",
        "impact-001",
        "opaque-cursor",
        20,
    )


def test_author_impact_http_fails_closed_for_identity_and_query_errors() -> None:
    client, store = _client()

    unauthorized = client.get(
        "/internal/recommendation/authors/author-001/impact"
    )
    assert unauthorized.status_code == 401
    assert unauthorized.json()["detail"]["code"].endswith(
        "feature_profile_unauthorized"
    )

    forbidden = client.get(
        "/internal/recommendation/authors/author-001/impact",
        headers={"Authorization": "Bearer another-service"},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"]["code"].endswith(
        "feature_profile_forbidden"
    )

    invalid = client.get(
        "/internal/recommendation/authors/author-001/impact?limit=1&limit=2",
        headers=_headers(),
    )
    assert invalid.status_code == 400
    assert invalid.json()["detail"]["code"].endswith(
        "feature_profile_invalid_argument"
    )
    assert store.summary_args is None

    non_numeric = client.get(
        "/internal/recommendation/authors/author-001/impact",
        headers=_headers(),
        params={"limit": "many"},
    )
    assert non_numeric.status_code == 400
    assert non_numeric.json()["detail"]["code"].endswith(
        "feature_profile_invalid_argument"
    )
