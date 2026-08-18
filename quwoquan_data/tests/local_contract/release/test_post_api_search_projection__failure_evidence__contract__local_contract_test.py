"""Search delivery verification must use canonical targets and safe receipts."""
from __future__ import annotations

from types import SimpleNamespace
from urllib.error import URLError

import pytest

from content.release.environment import _ship_consumer_verification as ship_subject
from content.release.environment import post_api_projection_verification as subject
from content.release.environment import public_api_client as client_subject
from content.release.environment.post_api_media_verification import (
    PostApiVerificationError,
)


def _operation(*, status: int) -> client_subject.PublicApiOperationEvidence:
    return client_subject.PublicApiOperationEvidence(
        path="/search",
        page_id="search.global",
        status=status,
        request_id="DATA.search.global.request-a",
        trace_id="DATA.session.search.global.trace-a",
        started_at="2026-08-11T00:00:00.000Z",
        ended_at="2026-08-11T00:00:00.010Z",
        duration_ms=10,
    )


@pytest.mark.parametrize(
    "content_type",
    ["article", "image", "video"],
)
def test_search_content_type_is_single_track(content_type: str) -> None:
    assert subject._search_content_type(content_type) == content_type


def test_search_request_uses_canonical_session_header_contract() -> None:
    calls: list[dict[str, object]] = []

    class _Client:
        def post_json(self, path: str, **kwargs: object):
            calls.append({"path": path, **kwargs})
            object_id = str((kwargs["body"]["ids"] or [""])[0])  # type: ignore[index]
            return client_subject.PublicApiResponse(
                status=200,
                payload={"hits": [{"objectId": object_id}]},
                operation=_operation(status=200),
            )

    subject._search_hits(
        _Client(),  # type: ignore[arg-type]
        query="公开标题",
        object_types=["content.post"],
        content_types=["image"],
        object_id="post-image-a",
    )

    assert calls[0]["session_header_name"] == "X-Session-Id"
    assert calls[0]["body"] == {
        "query": "公开标题",
        "mode": "result",
        "objectTypes": ["content.post"],
        "contentTypes": ["image"],
        "ids": ["post-image-a"],
        "limit": 20,
    }


@pytest.mark.parametrize(
    ("status", "payload", "expected_outcome", "expected_code"),
    [
        (
            400,
            {"code": "SEARCH.USER.invalid_argument", "message": "bad secret body"},
            "http_error",
            "SEARCH.USER.invalid_argument",
        ),
        (
            503,
            {"code": "SEARCH.MIDDLEWARE.unavailable", "message": "token=secret"},
            "http_error",
            "SEARCH.MIDDLEWARE.unavailable",
        ),
        (200, {"hits": []}, "empty", "none"),
    ],
)
def test_search_failure_is_bounded_structured_and_redacted(
    status: int,
    payload: dict[str, object],
    expected_outcome: str,
    expected_code: str,
) -> None:
    secret_query = "sensitive-query-never-persist"
    secret_object_id = "sensitive-object-id-never-persist"
    client = SimpleNamespace(
        post_json=lambda *_args, **_kwargs: client_subject.PublicApiResponse(
            status=status,
            payload=payload,
            operation=_operation(status=status),
        )
    )

    with pytest.raises(PostApiVerificationError) as captured:
        subject._search_hits(
            client,
            query=secret_query,
            object_types=["content.post"],
            content_types=["image"],
            object_id=secret_object_id,
        )

    message = str(captured.value)
    assert f"outcome={expected_outcome}" in message
    assert f"status={status}" in message
    assert f"canonicalErrorCode={expected_code}" in message
    assert "requestId=DATA.search.global.request-a" in message
    assert "traceId=DATA.session.search.global.trace-a" in message
    assert "objectTypes=content.post" in message
    assert "idsCount=1" in message
    assert secret_query not in message
    assert secret_object_id not in message
    assert "bad secret body" not in message
    assert "token=secret" not in message
    assert len(message) <= 768


def test_public_api_timeout_evidence_omits_url_body_and_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Opener:
        def open(self, *_args: object, **_kwargs: object) -> object:
            raise URLError("timeout Bearer top-secret transport-body")

    client = client_subject.PublicApiClient(
        base_url="https://api.example.test",
        bearer_token="top-secret-bearer",
        session_id="session-a",
    )
    monkeypatch.setattr(client_subject.PublicApiClient, "_opener", lambda _self: _Opener())

    with pytest.raises(client_subject.PublicApiClientError) as captured:
        client.post_json(
            "search",
            page_id="search.global",
            body={"query": "private-query", "ids": ["private-post"]},
            session_header_name="X-Session-Id",
        )

    message = str(captured.value)
    assert "canonicalErrorCode=none" in message
    assert "requestId=DATA.search.global." in message
    assert "traceId=DATA.session-a.search.global." in message
    assert "cause=URLError" in message
    assert "private-query" not in message
    assert "private-post" not in message
    assert "top-secret" not in message


def test_search_request_emits_one_session_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[object] = []

    class _Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"hits":[]}'

    class _Opener:
        def open(self, request: object, **_kwargs: object) -> _Response:
            requests.append(request)
            return _Response()

    monkeypatch.setattr(client_subject.PublicApiClient, "_opener", lambda _self: _Opener())
    client = client_subject.PublicApiClient(
        base_url="https://api.example.test",
        session_id="session-a",
    )
    client.post_json(
        "search",
        page_id="search.global",
        body={"query": "title", "ids": ["post-a"]},
        session_header_name="X-Session-Id",
    )

    headers = {key.lower(): value for key, value in requests[0].header_items()}  # type: ignore[attr-defined]
    assert headers["x-session-id"] == "session-a"
    assert "x-client-session-id" not in headers


def test_failed_receipt_error_keeps_trace_and_redacts_sensitive_values() -> None:
    error = PostApiVerificationError(
        "outcome=http_error status=400 "
        "canonicalErrorCode=SEARCH.USER.invalid_argument "
        "requestId=request-a traceId=trace-a "
        "authorization=Bearer bearer-secret token=token-secret "
        'body={"query":"private-query"}'
    )

    message = ship_subject._failure_receipt_error(error)

    assert "canonicalErrorCode=SEARCH.USER.invalid_argument" in message
    assert "requestId=request-a" in message
    assert "traceId=trace-a" in message
    assert "bearer-secret" not in message
    assert "token-secret" not in message
    assert "private-query" not in message
    assert len(message) <= 1024
