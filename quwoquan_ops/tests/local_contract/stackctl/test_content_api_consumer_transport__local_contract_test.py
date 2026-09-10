"""公开 consumer 的真实 HTTP 构造边界；全部使用 opener 替身，无现场请求。

spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/
multi-carrier-release/spec.md#gwt-002
"""
from __future__ import annotations

import inspect
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import pytest

from quwoquan_ops.cli.lib import content_api_consumer as subject

BUDGET = 2 * 1024 * 1024


class _Response(BytesIO):
    status = 200

    def __init__(self, raw: bytes):
        super().__init__(raw)
        self.read_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        return super().read(size)


def _opener(monkeypatch, *, raw=b'{"items":[]}', status=200, error=None):
    calls = []
    responses = []
    tls_calls = []
    context = object()

    def tls(**kwargs):
        tls_calls.append(kwargs)
        return context

    class Opener:
        def open(self, request, *, timeout):
            calls.append((request, timeout))
            if error is not None:
                raise error
            response = _Response(raw)
            responses.append(response)
            if status != 200:
                raise HTTPError(request.full_url, status, "fixture", {}, response)
            return response

    def build(*handlers):
        assert handlers[0].proxies == {}
        assert handlers[1]._context is context
        assert isinstance(handlers[2], subject._NoRedirect)
        return Opener()

    monkeypatch.setattr(subject.ssl, "create_default_context", tls)
    monkeypatch.setattr(subject, "build_opener", build)
    return calls, responses, tls_calls


def _request(**overrides):
    kwargs = {
        "api_base": "https://consumer.invalid",
        "ca_file": Path("/fixture/root.crt"),
        "method": "GET",
        "path": "content/feed",
        "page_id": "content.feed.list",
        "query": {"sort": "recommend", "channelId": "recommend", "limit": "20"},
        "release_id": "local-release-authority",
        "release_digest": "local-release-digest",
        "manifest_digest": "local-manifest-digest",
        **overrides,
    }
    inspect.signature(subject._default_http_request).bind(**kwargs)
    return subject._default_http_request(**kwargs)


def _headers(request):
    return {key.lower(): value for key, value in request.header_items()}


def test_public_ca_uses_system_trust_without_local_certificate(monkeypatch):
    calls, _, tls_calls = _opener(monkeypatch)
    _request(ca_file=None)
    assert tls_calls == [{}]
    assert len(calls) == 1


def test_expired_total_deadline_never_opens_transport(monkeypatch):
    calls, _, _ = _opener(monkeypatch)
    with pytest.raises(subject.ContentApiConsumerTransportError, match='deadline'):
        _request(deadline_monotonic=subject.time.monotonic() - 1)
    assert calls == []


def test_smaller_response_budget_is_enforced_at_read(monkeypatch):
    _, responses, _ = _opener(monkeypatch, raw=b'{' + b'x' * 64)
    with pytest.raises(subject.ContentApiConsumerError, match='byte budget'):
        _request(max_response_bytes=16)
    assert responses[0].read_sizes == [17]


def test_total_deadline_stops_slow_chunking():
    ticks = iter([1.0, 1.5, 2.1])
    class SlowBody:
        def read(self, _size):
            return b'x'
    from unittest.mock import patch
    with patch.object(subject.time, 'monotonic', side_effect=lambda: next(ticks)):
        with pytest.raises(subject.ContentApiConsumerTransportError, match='deadline'):
            subject._read_bounded_body(SlowBody(), maximum=100, deadline=2.0)


def test_redirect_handler_rejects_before_following_other_authority():
    with pytest.raises(subject.ContentApiConsumerTransportError, match='redirects'):
        subject._NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.invalid')


def test_default_transport_uses_fresh_anonymous_sessions(monkeypatch):
    calls, responses, tls_calls = _opener(monkeypatch)
    observations = [_request(), _request()]
    sessions = [_headers(request)["x-client-session-id"] for request, _ in calls]
    assert len(set(sessions)) == 2
    assert all(UUID(session).version == 4 for session in sessions)
    assert len({item.request_id for item in observations}) == 2
    assert len({item.trace_id for item in observations}) == 2
    assert all(item.path == "/content/feed" for item in observations)
    assert all(response.read_sizes == [BUDGET + 1] for response in responses)
    assert tls_calls == [{"cafile": "/fixture/root.crt"}] * 2
    for request, timeout in calls:
        headers = _headers(request)
        assert set(headers) == {
            "accept", "x-client-page-id", "x-client-session-id", "x-client-sent-at",
            "x-client-device-platform", "x-client-app-version", "x-request-id", "x-trace-id",
        }
        assert request.get_method() == "GET"
        assert request.data is None
        assert timeout == 12.0
        assert parse_qs(urlsplit(request.full_url).query) == {
            "sort": ["recommend"], "channelId": ["recommend"], "limit": ["20"],
        }
        assert "local-release" not in request.full_url
        assert "local-manifest" not in request.full_url


@pytest.mark.parametrize("session", ["s" * 128, "é" * 64])
def test_explicit_session_is_stable_across_cursor_requests(monkeypatch, session):
    calls, _, _ = _opener(monkeypatch)
    _request(client_session_id=session)
    _request(client_session_id=session, query={"limit": "20", "cursor": "opaque+/="})
    assert [_headers(request)["x-client-session-id"] for request, _ in calls] == [session] * 2
    assert parse_qs(urlsplit(calls[1][0].full_url).query)["cursor"] == ["opaque+/="]


@pytest.mark.parametrize("session", [
    "", " " * 5, "s" * 129, "é" * 65, " leading", "trailing ", "inner space",
    "tab\tsession", "newline\nsession", "carriage\rsession", "null\0session",
    "delete\x7fsession", "control\x85session", "wide\u3000space", "\ud800", 42,
])
def test_invalid_session_is_rejected_before_http_without_echo(monkeypatch, session):
    calls, _, tls_calls = _opener(monkeypatch)
    with pytest.raises(subject.ContentApiConsumerError, match="client_session_id") as exc:
        _request(client_session_id=session)
    assert str(exc.value) == "client_session_id must be 1..128 UTF-8 bytes without whitespace or control characters"
    assert calls == []
    assert tls_calls == []


@pytest.mark.parametrize("field", ["bearer_token", "attestation_token"])
def test_real_signature_rejects_retired_credentials(field):
    assert field not in inspect.signature(subject._default_http_request).parameters
    with pytest.raises(TypeError):
        _request(**{field: "never-send-or-log"})


@pytest.mark.parametrize("status", [200, 503])
@pytest.mark.parametrize("extra", [0, 1])
def test_transport_enforces_response_byte_budget(monkeypatch, status, extra):
    raw = b"{}" + b" " * (BUDGET - 2 + extra)
    calls, responses, _ = _opener(monkeypatch, raw=raw, status=status)
    if extra:
        with pytest.raises(subject.ContentApiConsumerError, match="exceeded byte budget"):
            _request()
    else:
        observation = _request()
        assert observation.status == status
        assert observation.payload == {}
    assert len(calls) == 1
    assert responses[0].read_sizes == [BUDGET + 1]


@pytest.mark.parametrize("raw, message", [
    (b"not-json", "not JSON"), (b"\xff", "not JSON"), (b"[]", "not an object"),
])
def test_transport_rejects_invalid_json_response(monkeypatch, raw, message):
    _opener(monkeypatch, raw=raw)
    with pytest.raises(subject.ContentApiConsumerError, match=message):
        _request()


def test_transport_failure_does_not_echo_upstream_details(monkeypatch):
    _opener(monkeypatch, error=URLError("fixture-secret-never-log"))
    with pytest.raises(subject.ContentApiConsumerTransportError) as exc:
        _request()
    assert "fixture-secret" not in str(exc.value)
    assert "URLError" in str(exc.value)
