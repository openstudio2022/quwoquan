# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-028.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-028.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-028.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-028.t4
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-028.t5
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-028.t6
"""Search delivery verification must use canonical targets and safe receipts."""
from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from types import SimpleNamespace
from urllib.error import URLError

import pytest
from content.release.environment import _ship_consumer_verification as ship_subject
from content.release.environment import post_api_projection_verification as subject
from content.release.environment import public_api_client as client_subject
from content.release.environment.post_api_media_verification import (
    PostApiVerificationError,
)
from core.paths import REPO_ROOT
from core.schema import assert_valid


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


def _logical_request() -> client_subject.PublicApiRequestIdentity:
    return client_subject.PublicApiRequestIdentity(
        page_id="search.global",
        request_id="DATA.search.global.request-a",
        trace_id="DATA.session.search.global.trace-a",
    )


def _retryable_response(
    *,
    code: str = "GATEWAY.MIDDLEWARE.upstream_unavailable",
    status: int = 503,
    after_seconds: int = 1,
    retry_after_seconds: int | None = None,
) -> client_subject.PublicApiResponse:
    return client_subject.PublicApiResponse(
        status=status,
        payload={
            "code": code,
            "recovery": {
                "action": "retry",
                "afterSeconds": after_seconds,
                "disruptionLevel": "snackbar",
            },
        },
        operation=_operation(status=status),
        headers={
            "Retry-After": str(
                after_seconds
                if retry_after_seconds is None
                else retry_after_seconds
            )
        },
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
        def new_request_identity(
            self,
            *,
            page_id: str,
        ) -> client_subject.PublicApiRequestIdentity:
            assert page_id == "search.global"
            return _logical_request()

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
    assert calls[0]["request_identity"] == _logical_request()
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
        new_request_identity=lambda **_kwargs: _logical_request(),
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


def test_search_retry_policy_is_loaded_from_canonical_operation_contract() -> None:
    policy = subject._search_retry_policy()

    assert policy.retry_mode == "idempotent"
    assert policy.max_attempts == 2
    assert policy.timeout_ms == 1500
    assert {
        (row.code, row.http_status, row.recovery_after_seconds)
        for row in policy.retryable_errors
    } >= {
        ("SEARCH.MIDDLEWARE.unavailable", 503, 5),
        ("GATEWAY.MIDDLEWARE.upstream_unavailable", 503, 1),
        ("GATEWAY.MIDDLEWARE.upstream_timeout", 504, 1),
    }
    assert policy.total_timeout_ms(attempt_limit=2) == 8000


def test_search_receipt_attempt_bound_tracks_canonical_operation_contract() -> None:
    schema = json.loads(
        (
            REPO_ROOT
            / "quwoquan_data/schema/release/post_api_verification.schema.json"
        ).read_text(encoding="utf-8")
    )
    attempts = schema["properties"]["searchQueries"]["items"]["properties"][
        "attempts"
    ]

    assert attempts["maxItems"] == subject._search_retry_policy().max_attempts


def test_search_retry_reuses_logical_identity_and_retains_both_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(subject, "_sleep_seconds", lambda _seconds: None)
    identity = _logical_request()
    responses = [
        _retryable_response(),
        client_subject.PublicApiResponse(
            status=200,
            payload={"hits": [{"objectId": "post-a"}]},
            operation=_operation(status=200),
        ),
    ]
    calls: list[dict[str, object]] = []

    class _Client:
        def new_request_identity(
            self,
            *,
            page_id: str,
        ) -> client_subject.PublicApiRequestIdentity:
            assert page_id == "search.global"
            return identity

        def post_json(self, path: str, **kwargs: object):
            calls.append({"path": path, **kwargs})
            return responses.pop(0)

    result = subject._search_hits(
        _Client(),  # type: ignore[arg-type]
        query="title",
        object_types=["content.post"],
        object_id="post-a",
    )

    assert len(calls) == 2
    assert [call["request_identity"] for call in calls] == [identity, identity]
    assert [row["attempt"] for row in result["attempts"]] == [1, 2]
    assert [row["operation"]["status"] for row in result["attempts"]] == [503, 200]
    assert [row["canonicalErrorCode"] for row in result["attempts"]] == [
        "GATEWAY.MIDDLEWARE.upstream_unavailable",
        "none",
    ]
    assert [row["recoveryAfterSeconds"] for row in result["attempts"]] == [1, 0]
    assert [row["retryAfterSeconds"] for row in result["attempts"]] == [1, 0]
    assert {row["operation"]["requestId"] for row in result["attempts"]} == {
        "DATA.search.global.request-a"
    }
    assert "request" not in result


def test_search_gateway_timeout_honors_retry_after_and_per_attempt_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = {"now": 0.0}
    sleeps: list[float] = []
    timeouts: list[float] = []
    responses = [
        _retryable_response(
            code="GATEWAY.MIDDLEWARE.upstream_timeout",
            status=504,
            after_seconds=1,
        ),
        client_subject.PublicApiResponse(
            status=200,
            payload={"hits": [{"objectId": "post-a"}]},
            operation=_operation(status=200),
        ),
    ]

    def _sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr(subject, "_monotonic_seconds", lambda: clock["now"])
    monkeypatch.setattr(subject, "_sleep_seconds", _sleep)

    class _Client:
        def new_request_identity(self, *, page_id: str):
            return _logical_request()

        def post_json(self, *_args: object, **kwargs: object):
            timeouts.append(float(kwargs["timeout_seconds"]))
            clock["now"] += 1.4 if len(timeouts) == 1 else 0.01
            return responses.pop(0)

    result = subject._search_hits(
        _Client(),  # type: ignore[arg-type]
        query="title",
        object_types=["content.post"],
        object_id="post-a",
    )

    assert [row["operation"]["status"] for row in result["attempts"]] == [504, 200]
    assert sleeps == [1]
    assert timeouts == [1.5, 1.5]


def test_real_search_httptest_wire_retries_through_public_api_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = subprocess.Popen(
        [
            "go",
            "run",
            "./services/search-service/tests/local_contract/search/"
            "search_index_view/testdata/search_retry_wire_server",
        ],
        cwd=REPO_ROOT / "quwoquan_service",
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert server.stdout is not None
        handshake_line = server.stdout.readline()
        if not handshake_line:
            assert server.stderr is not None
            pytest.fail("Search httptest server failed: " + server.stderr.read())
        handshake = json.loads(handshake_line)
        client = client_subject.PublicApiClient(
            base_url=handshake["baseUrl"],
            ssl_cafile=handshake["caFile"],
            session_id="real-wire-session",
        )
        monkeypatch.setattr(subject, "_sleep_seconds", lambda _seconds: None)

        result = subject._search_hits(
            client,
            query="title",
            object_types=["content.post"],
            content_types=["article"],
            object_id="post-a",
        )

        assert [row["operation"]["status"] for row in result["attempts"]] == [
            503,
            200,
        ]
        assert result["attempts"][0]["canonicalErrorCode"] == (
            "SEARCH.MIDDLEWARE.unavailable"
        )
        assert result["attempts"][0]["recoveryAfterSeconds"] == 5
        assert result["attempts"][0]["retryAfterSeconds"] == 5
        assert len(
            {row["operation"]["requestId"] for row in result["attempts"]}
        ) == 1
        assert len(
            {row["operation"]["traceId"] for row in result["attempts"]}
        ) == 1
    finally:
        if server.stdin is not None:
            try:
                server.stdin.write("\n")
                server.stdin.flush()
                server.stdin.close()
            except BrokenPipeError:
                pass
        try:
            return_code = server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.terminate()
            return_code = server.wait(timeout=10)
        if return_code != 0:
            assert server.stderr is not None
            pytest.fail("Search httptest server exited nonzero: " + server.stderr.read())


def test_search_absolute_deadline_stops_before_out_of_budget_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = {"now": 0.0}
    calls = 0
    monkeypatch.setattr(subject, "_monotonic_seconds", lambda: clock["now"])
    monkeypatch.setattr(
        subject,
        "_sleep_seconds",
        lambda _seconds: pytest.fail("out-of-budget retry must not sleep"),
    )

    class _Client:
        def new_request_identity(self, *, page_id: str):
            return _logical_request()

        def post_json(self, *_args: object, **_kwargs: object):
            nonlocal calls
            calls += 1
            clock["now"] = 7.5
            return _retryable_response()

    with pytest.raises(subject.SearchProjectionVerificationError) as captured:
        subject._search_hits(
            _Client(),  # type: ignore[arg-type]
            query="title",
            object_types=["content.post"],
            object_id="post-a",
        )

    assert calls == 1
    assert len(captured.value.operation_attempts) == 1


def test_search_rejects_late_second_attempt_success_and_keeps_first_blocker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = {"now": 0.0}
    calls = 0

    def _sleep(seconds: float) -> None:
        clock["now"] += seconds

    monkeypatch.setattr(subject, "_monotonic_seconds", lambda: clock["now"])
    monkeypatch.setattr(subject, "_sleep_seconds", _sleep)

    class _Client:
        def new_request_identity(self, *, page_id: str):
            return _logical_request()

        def post_json(self, *_args: object, **_kwargs: object):
            nonlocal calls
            calls += 1
            if calls == 1:
                clock["now"] = 1.0
                return _retryable_response()
            clock["now"] = 8.01
            return client_subject.PublicApiResponse(
                status=200,
                payload={"hits": [{"objectId": "post-a"}]},
                operation=_operation(status=200),
            )

    with pytest.raises(subject.SearchProjectionVerificationError) as captured:
        subject._search_hits(
            _Client(),  # type: ignore[arg-type]
            query="title",
            object_types=["content.post"],
            object_id="post-a",
        )

    assert calls == 2
    assert [
        row["operation"]["status"] for row in captured.value.operation_attempts
    ] == [503, 200]
    assert "canonicalErrorCode=GATEWAY.MIDDLEWARE.upstream_unavailable" in str(
        captured.value
    )
    assert "outcome=deadline_exhausted" not in str(captured.value)


@pytest.mark.parametrize(
    "second_outcome",
    ["transport", "invalid_json", "request_identity_drift"],
)
def test_search_second_attempt_failure_keeps_first_blocker_and_attempt_receipt(
    second_outcome: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    monkeypatch.setattr(subject, "_sleep_seconds", lambda _seconds: None)

    class _Client:
        def new_request_identity(self, *, page_id: str):
            return _logical_request()

        def post_json(self, *_args: object, **_kwargs: object):
            nonlocal calls
            calls += 1
            if calls == 1:
                return _retryable_response()
            if second_outcome in {"transport", "invalid_json"}:
                raise client_subject.PublicApiClientError(
                    "public API request failed: " + second_outcome
                )
            return client_subject.PublicApiResponse(
                status=200,
                payload={"hits": [{"objectId": "post-a"}]},
                operation=client_subject.PublicApiOperationEvidence(
                    path="/search",
                    page_id="search.global",
                    status=200,
                    request_id="DATA.search.global.drifted",
                    trace_id="DATA.session.search.global.drifted",
                    started_at="2026-08-11T00:00:00.000Z",
                    ended_at="2026-08-11T00:00:00.010Z",
                    duration_ms=10,
                ),
            )

    with pytest.raises(subject.SearchProjectionVerificationError) as captured:
        subject._search_hits(
            _Client(),  # type: ignore[arg-type]
            query="title",
            object_types=["content.post"],
            object_id="post-a",
        )

    assert calls == 2
    assert len(captured.value.operation_attempts) == 1
    assert captured.value.operation_attempts[0]["canonicalErrorCode"] == (
        "GATEWAY.MIDDLEWARE.upstream_unavailable"
    )
    assert "canonicalErrorCode=GATEWAY.MIDDLEWARE.upstream_unavailable" in str(
        captured.value
    )


def test_search_exhaustion_keeps_the_first_typed_blocker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(subject, "_sleep_seconds", lambda _seconds: None)
    responses = [
        _retryable_response(code="GATEWAY.MIDDLEWARE.upstream_unavailable"),
        _retryable_response(code="SEARCH.MIDDLEWARE.unavailable"),
    ]
    calls = 0

    class _Client:
        def new_request_identity(
            self,
            *,
            page_id: str,
        ) -> client_subject.PublicApiRequestIdentity:
            return _logical_request()

        def post_json(self, *_args: object, **_kwargs: object):
            nonlocal calls
            calls += 1
            return responses.pop(0)

    with pytest.raises(PostApiVerificationError) as captured:
        subject._search_hits(
            _Client(),  # type: ignore[arg-type]
            query="title",
            object_types=["content.post"],
            object_id="post-a",
        )

    assert calls == 2
    message = str(captured.value)
    assert "canonicalErrorCode=GATEWAY.MIDDLEWARE.upstream_unavailable" in message
    assert "SEARCH.MIDDLEWARE.unavailable" not in message
    assert "requestId=DATA.search.global.request-a" in message
    assert isinstance(captured.value, subject.SearchProjectionVerificationError)
    assert [row["operation"]["status"] for row in captured.value.operation_attempts] == [
        503,
        503,
    ]
    assert [row["canonicalErrorCode"] for row in captured.value.operation_attempts] == [
        "GATEWAY.MIDDLEWARE.upstream_unavailable",
        "SEARCH.MIDDLEWARE.unavailable",
    ]
    assert {
        row["operation"]["requestId"]
        for row in captured.value.operation_attempts
    } == {"DATA.search.global.request-a"}
    assert {
        row["operation"]["traceId"]
        for row in captured.value.operation_attempts
    } == {"DATA.session.search.global.trace-a"}
    assert [
        row["operation"]["durationMs"]
        for row in captured.value.operation_attempts
    ] == [10, 10]


@pytest.mark.parametrize(
    ("status", "payload"),
    [
        (
            503,
            {
                "code": "GATEWAY.MIDDLEWARE.upstream_unavailable",
                "recovery": {"action": "surface"},
            },
        ),
        (
            400,
            {
                "code": "SEARCH.USER.invalid_argument",
                "recovery": {"action": "surface"},
            },
        ),
        (
            500,
            {
                "code": "GATEWAY.SYSTEM.unknown_failure",
                "recovery": {"action": "retry", "afterSeconds": 0},
            },
        ),
        (200, {"hits": []}),
    ],
)
def test_search_does_not_retry_non_retryable_results(
    status: int,
    payload: dict[str, object],
) -> None:
    calls = 0

    class _Client:
        def new_request_identity(
            self,
            *,
            page_id: str,
        ) -> client_subject.PublicApiRequestIdentity:
            return _logical_request()

        def post_json(self, *_args: object, **_kwargs: object):
            nonlocal calls
            calls += 1
            return client_subject.PublicApiResponse(
                status=status,
                payload=payload,
                operation=_operation(status=status),
            )

    with pytest.raises(PostApiVerificationError):
        subject._search_hits(
            _Client(),  # type: ignore[arg-type]
            query="title",
            object_types=["content.post"],
            object_id="post-a",
        )

    assert calls == 1


def test_search_does_not_retry_when_retry_after_drifts_from_body() -> None:
    calls = 0

    class _Client:
        def new_request_identity(self, *, page_id: str):
            return _logical_request()

        def post_json(self, *_args: object, **_kwargs: object):
            nonlocal calls
            calls += 1
            return _retryable_response(retry_after_seconds=2)

    with pytest.raises(subject.SearchProjectionVerificationError) as captured:
        subject._search_hits(
            _Client(),  # type: ignore[arg-type]
            query="title",
            object_types=["content.post"],
            object_id="post-a",
        )

    assert calls == 1
    assert captured.value.operation_attempts[0]["recoveryAfterSeconds"] == 1
    assert captured.value.operation_attempts[0]["retryAfterSeconds"] == 2


def test_search_does_not_retry_when_operation_contract_is_not_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    non_idempotent_policy = replace(
        subject._search_retry_policy(),
        retry_mode="none",
    )
    monkeypatch.setattr(
        subject,
        "_search_retry_policy",
        lambda: non_idempotent_policy,
    )

    class _Client:
        def new_request_identity(
            self,
            *,
            page_id: str,
        ) -> client_subject.PublicApiRequestIdentity:
            return _logical_request()

        def post_json(self, *_args: object, **_kwargs: object):
            nonlocal calls
            calls += 1
            return _retryable_response()

    with pytest.raises(PostApiVerificationError):
        subject._search_hits(
            _Client(),  # type: ignore[arg-type]
            query="title",
            object_types=["content.post"],
            object_id="post-a",
        )

    assert calls == 1


def test_search_does_not_retry_untyped_transport_failure() -> None:
    calls = 0

    class _Client:
        def new_request_identity(
            self,
            *,
            page_id: str,
        ) -> client_subject.PublicApiRequestIdentity:
            return _logical_request()

        def post_json(self, *_args: object, **_kwargs: object):
            nonlocal calls
            calls += 1
            raise client_subject.PublicApiClientError(
                "public API request failed: status=transport_error"
            )

    with pytest.raises(client_subject.PublicApiClientError):
        subject._search_hits(
            _Client(),  # type: ignore[arg-type]
            query="title",
            object_types=["content.post"],
            object_id="post-a",
        )

    assert calls == 1


def test_public_api_repeated_attempts_share_headers_and_operation_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[object] = []
    request_timeouts: list[float] = []

    class _Response:
        status = 200
        headers = {"Retry-After": "1"}

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"hits":[]}'

    class _Opener:
        def open(self, request: object, **kwargs: object) -> _Response:
            requests.append(request)
            request_timeouts.append(float(kwargs["timeout"]))
            return _Response()

    monkeypatch.setattr(client_subject.PublicApiClient, "_opener", lambda _self: _Opener())
    client = client_subject.PublicApiClient(
        base_url="https://api.example.test",
        session_id="session-a",
    )
    identity = client.new_request_identity(page_id="search.global")
    responses = [
        client.post_json(
            "search",
            page_id="search.global",
            body={"query": "title", "ids": ["post-a"]},
            request_identity=identity,
            timeout_seconds=1.5,
        )
        for _ in range(2)
    ]

    headers = [
        {key.lower(): value for key, value in request.header_items()}  # type: ignore[attr-defined]
        for request in requests
    ]
    assert [row["x-request-id"] for row in headers] == [identity.request_id] * 2
    assert [row["x-trace-id"] for row in headers] == [identity.trace_id] * 2
    assert [response.operation.request_id for response in responses] == [
        identity.request_id,
        identity.request_id,
    ]
    assert [response.operation.trace_id for response in responses] == [
        identity.trace_id,
        identity.trace_id,
    ]
    assert [response.headers["Retry-After"] for response in responses] == ["1", "1"]
    assert request_timeouts == [1.5, 1.5]


def test_public_api_rejects_cross_operation_identity_reuse() -> None:
    client = client_subject.PublicApiClient(
        base_url="https://api.example.test",
        session_id="session-a",
    )
    identity = client.new_request_identity(page_id="search.global")

    with pytest.raises(
        client_subject.PublicApiClientError,
        match="pageId mismatch",
    ):
        client.post_json(
            "content/media/a/original:access",
            page_id="content.media.original_access",
            body={"mediaId": "a", "purpose": "view"},
            request_identity=identity,
        )


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


def test_public_media_failure_and_receipt_omit_signed_url_and_transport_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Opener:
        def open(self, *_args: object, **_kwargs: object) -> object:
            raise URLError("transport-secret signed-query-secret")

    monkeypatch.setattr(client_subject.PublicApiClient, "_opener", lambda _self: _Opener())
    client = client_subject.PublicApiClient(
        base_url="https://api.example.test",
        session_id="session-a",
    )
    signed_url = (
        "https://private-media.example.test/media/private-object-secret.mp4"
        "?X-Amz-Signature=signed-query-secret&token=url-token-secret"
    )

    with pytest.raises(client_subject.PublicApiClientError) as captured:
        client.get_bytes(signed_url)

    message = str(captured.value)
    receipt = ship_subject._failure_receipt_error(captured.value)
    for evidence in (message, receipt):
        assert "hostClass=dns" in evidence
        assert "pathHash=sha256:" in evidence
        assert "private-media.example.test" not in evidence
        assert "private-object-secret" not in evidence
        assert "X-Amz-Signature" not in evidence
        assert "signed-query-secret" not in evidence
        assert "url-token-secret" not in evidence
        assert "transport-secret" not in evidence


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


def test_failed_receipt_retains_bounded_search_attempt_evidence() -> None:
    attempts = [
        {
            "attempt": index,
            "canonicalErrorCode": code,
            "recoveryAction": "retry",
            "recoveryAfterSeconds": after_seconds,
            "retryAfterSeconds": after_seconds,
            "operation": _operation(status=status).as_payload(),
        }
        for index, code, status, after_seconds in (
            (1, "GATEWAY.MIDDLEWARE.upstream_unavailable", 503, 1),
            (2, "SEARCH.MIDDLEWARE.unavailable", 503, 5),
        )
    ]
    error = subject.SearchProjectionVerificationError(
        "canonicalErrorCode=GATEWAY.MIDDLEWARE.upstream_unavailable",
        operation_attempts=attempts,
    )

    evidence = ship_subject._failure_receipt_evidence(error)
    payload = {
        "schema": "quwoquan_data.environment_release_result",
        "environment": "alpha",
        "releaseId": "release-a",
        "releaseClass": "commercial",
        "productLifecycleState": "commercial",
        "containsUnverifiedAssets": False,
        "manifestDigest": "sha256:" + "a" * 64,
        "runId": "verify-a",
        "status": "failed",
        "failedStage": "post_api_verification",
        "error": str(error),
        **evidence,
    }

    assert_valid(
        payload,
        "release",
        "environment_release_result",
        label="failed Search readiness result",
    )
    assert [
        row["operation"]["status"] for row in payload["operationAttempts"]
    ] == [503, 503]
    assert payload["error"].endswith("upstream_unavailable")
