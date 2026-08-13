# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-003
"""feature profile Reader HTTP 错误码合约。

contracts/recommendation/recommendation_feature_profile_view/errors.yaml 声明的
五个错误码逐一由真实负例触发,断言 HTTP 响应携带完整 canonical code:
身份缺失 -> 401、scope 不符 -> 403、非法参数 -> 400、主体已关闭 -> 410、
投影存储不可用 -> 500。
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from internal.recommendation.recommendation_feature_profile_view.adapters.inbound.http.router import (
    FEATURE_PROFILE_READ_SCOPE,
    build_router,
)
from internal.recommendation.recommendation_feature_profile_view.application.author_impact_reader import (
    Reader,
)
from internal.recommendation.recommendation_feature_profile_view.application.intersection_reader import (
    Reader as IntersectionReader,
)
from security.service_authorization import AuthorizationFailure

UNAUTHORIZED_CODE = "RECOMMENDATION.USER.feature_profile_unauthorized"
FORBIDDEN_CODE = "RECOMMENDATION.USER.feature_profile_forbidden"
INVALID_ARGUMENT_CODE = "RECOMMENDATION.USER.feature_profile_invalid_argument"
SUBJECT_CLOSED_CODE = "RECOMMENDATION.USER.feature_profile_subject_closed"
READ_FAILED_CODE = "RECOMMENDATION.SYSTEM.feature_profile_read_failed"

AUTHOR_IMPACT_PATH = "/internal/recommendation/authors/author-001/impact"
SUBJECT_INTERSECTIONS_PATH = (
    "/internal/recommendation/subjects/persona-closed/intersections"
)


class _UnavailableStore:
    """投影存储不可用:任何读都以基础设施异常失败。"""

    def read_author_impact(self, _author_id: str, _limit: int):
        raise RuntimeError("feature profile projection store unavailable")


class _UnusedIntersectionStore:
    def subject_intersection_evidence_digest(self, _subject_id: str) -> str:
        raise AssertionError("closed subject must be fenced before any store read")


class _NoopMaterializer:
    def rebuild_subject(self, **_kwargs) -> None:
        raise AssertionError("closed subject must be fenced before rebuild")


class _ClosedSubjects:
    def exists(self, _subject_id: str) -> bool:
        return True


class _OpenSubjects:
    def exists(self, _subject_id: str) -> bool:
        return False


class _Verifier:
    def verify(self, authorization: str | None, *, required_scope: str):
        assert required_scope == FEATURE_PROFILE_READ_SCOPE
        if authorization is None:
            raise AuthorizationFailure(401, "ignored")
        if authorization != "Bearer content-service":
            raise AuthorizationFailure(403, "ignored")
        return {"sub": "service:content-service"}


def _client(*, subject_closures) -> TestClient:
    app = FastAPI()
    app.include_router(
        build_router(
            reader_provider=lambda _request: Reader(_UnavailableStore()),
            intersection_reader_provider=lambda _request: IntersectionReader(
                _UnusedIntersectionStore(),
                _NoopMaterializer(),
                subject_closures,
            ),
            token_verifier=_Verifier(),
        )
    )
    return TestClient(app)


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer content-service"}


def test_identity_negatives_emit_the_declared_unauthorized_and_forbidden_codes() -> None:
    client = _client(subject_closures=_OpenSubjects())

    unauthorized = client.get(AUTHOR_IMPACT_PATH)
    assert unauthorized.status_code == 401
    assert unauthorized.json()["detail"]["code"] == UNAUTHORIZED_CODE

    forbidden = client.get(
        AUTHOR_IMPACT_PATH,
        headers={"Authorization": "Bearer another-service"},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"]["code"] == FORBIDDEN_CODE


def test_invalid_query_emits_the_declared_invalid_argument_code() -> None:
    client = _client(subject_closures=_OpenSubjects())

    invalid = client.get(
        AUTHOR_IMPACT_PATH,
        headers=_headers(),
        params={"limit": "many"},
    )
    assert invalid.status_code == 400
    assert invalid.json()["detail"]["code"] == INVALID_ARGUMENT_CODE


def test_closed_subject_emits_the_declared_subject_closed_code() -> None:
    client = _client(subject_closures=_ClosedSubjects())

    closed = client.get(
        SUBJECT_INTERSECTIONS_PATH,
        headers=_headers(),
        params={"intersectionClass": "fact"},
    )
    assert closed.status_code == 410
    assert closed.json()["detail"]["code"] == SUBJECT_CLOSED_CODE


def test_store_outage_emits_the_declared_read_failed_code() -> None:
    client = _client(subject_closures=_OpenSubjects())

    failed = client.get(AUTHOR_IMPACT_PATH, headers=_headers())
    assert failed.status_code == 500
    assert failed.json()["detail"]["code"] == READ_FAILED_CODE
