# spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/filter-catalog-release/spec.md#gwt-004

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

import pytest

from content.filter_catalog import publisher
from content.filter_catalog.environment_import import load_environment_import
from content.filter_catalog.publisher import (
    FilterCatalogHttpResponse,
    FilterCatalogPublishAction,
    FilterCatalogPublishError,
    publish_filter_catalog,
)


REPO_ROOT = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class _Request:
    method: str
    url: str
    headers: dict[str, str]
    body: bytes | None


class _FakeTransport:
    def __init__(self, *, environment: str, rollback_release_id: str = "") -> None:
        self._input = load_environment_import(
            repo_root=REPO_ROOT,
            environment=environment,
        )
        self._rollback_release_id = rollback_release_id
        self.requests: list[_Request] = []

    def request_json(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
    ) -> FilterCatalogHttpResponse:
        self.requests.append(
            _Request(
                method=method,
                url=url,
                headers=headers,
                body=body,
            )
        )
        if method == "POST" and url.endswith(
            self._input.operation_paths["stage"]
        ):
            return FilterCatalogHttpResponse(
                status=200,
                body=self._release_body("staged"),
            )
        if method == "POST" and url.endswith(":activate"):
            return FilterCatalogHttpResponse(
                status=200,
                body=self._release_body("active"),
            )
        if method == "POST" and url.endswith(":rollback"):
            return FilterCatalogHttpResponse(
                status=200,
                body={
                    "releaseId": self._rollback_release_id,
                    "status": "active",
                },
            )
        if method == "GET" and url.endswith(self._input.operation_paths["read"]):
            if self._rollback_release_id:
                return FilterCatalogHttpResponse(
                    status=200,
                    body=self._rollback_active_body(),
                )
            return FilterCatalogHttpResponse(
                status=200,
                body={
                    **self._release_body("active"),
                    "categoryCount": self._input.category_count,
                    "presetCount": self._input.preset_count,
                    "activatedAt": "2026-07-21T00:00:00Z",
                },
            )
        raise AssertionError(f"unexpected transport request: {method} {url}")

    def _release_body(self, status: str) -> dict[str, object]:
        return {
            "releaseId": self._input.release_id,
            "canonicalDigest": self._input.canonical_digest,
            "status": status,
        }

    def _rollback_active_body(self) -> dict[str, object]:
        return {
            "releaseId": self._rollback_release_id,
            "canonicalDigest": "f" * 64,
            "categoryCount": 2,
            "presetCount": 3,
            "status": "active",
            "activatedAt": "2026-07-20T00:00:00Z",
        }


class _UrllibResponse:
    status = 200

    def __enter__(self) -> _UrllibResponse:
        return self

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        return None

    def read(self) -> bytes:
        return b'{"releaseId":"filter-catalog-20260720-001"}'


def test_local_public_tls_publish_bypasses_proxy_and_resolves_loopback():
    response = _UrllibResponse()
    fake_getaddrinfo = mock.Mock(return_value=[("loopback",)])
    proxy_handler = object()
    https_handler = object()
    opener = mock.Mock()
    observed_resolutions: list[object] = []

    def open_request(*args: object, **kwargs: object) -> _UrllibResponse:
        observed_resolutions.extend(
            publisher.socket.getaddrinfo(
                "beta-api.quwoquan-env.test",
                18000,
            )
        )
        return response

    opener.open.side_effect = open_request
    with (
        mock.patch.object(publisher.socket, "getaddrinfo", fake_getaddrinfo),
        mock.patch.object(
            publisher.ssl,
            "_create_unverified_context",
            return_value=object(),
        ),
        mock.patch.object(
            publisher.request,
            "ProxyHandler",
            return_value=proxy_handler,
        ),
        mock.patch.object(
            publisher.request,
            "HTTPSHandler",
            return_value=https_handler,
        ),
        mock.patch.object(
            publisher.request,
            "build_opener",
            return_value=opener,
        ) as build_opener,
        mock.patch.object(publisher.request, "urlopen") as urlopen,
    ):
        result = publisher.UrllibFilterCatalogHttpTransport(
            insecure_local_tls=True,
        ).request_json(
            method="GET",
            url=(
                "https://beta-api.quwoquan-env.test:18000/"
                "content/filter-catalog"
            ),
            headers={},
            body=None,
        )
        assert publisher.socket.getaddrinfo is fake_getaddrinfo

    assert result == FilterCatalogHttpResponse(
        status=200,
        body={"releaseId": "filter-catalog-20260720-001"},
    )
    assert observed_resolutions == [("loopback",)]
    fake_getaddrinfo.assert_any_call("127.0.0.1", 18000)
    build_opener.assert_called_once_with(proxy_handler, https_handler)
    urlopen.assert_not_called()


def test_gamma_publish_uses_metadata_paths_idempotency_and_canonical_payload():
    transport = _FakeTransport(environment="gamma")

    receipt = publish_filter_catalog(
        repo_root=REPO_ROOT,
        environment="gamma",
        base_url="https://gamma-api.quwoquan-env.test:19000",
        action=FilterCatalogPublishAction.stage_and_activate,
        bearer_token="local-service-principal-token",
        transport=transport,
    )

    assert [request.method for request in transport.requests] == [
        "POST",
        "POST",
        "GET",
    ]
    stage, activate, public_read = transport.requests
    assert stage.url.endswith("/internal/content/filter-catalog-releases")
    assert activate.url.endswith(
        "/internal/content/filter-catalog-releases/"
        "filter-catalog-20260720-001:activate"
    )
    assert stage.headers["Idempotency-Key"].endswith(":stage")
    assert activate.headers["Idempotency-Key"].endswith(":activate")
    assert "Authorization" not in public_read.headers
    assert stage.body is not None
    staged_payload = json.loads(stage.body.decode("utf-8"))
    assert staged_payload["releaseId"] == "filter-catalog-20260720-001"
    assert len(staged_payload["categories"]) == 10
    assert len(staged_payload["presets"]) == 85
    assert receipt["passed"] is True
    assert receipt["active"] == {
        "httpStatus": 200,
        "releaseId": "filter-catalog-20260720-001",
        "canonicalDigest": (
            "9ccd581f6ac73b1e8a623b345fc8b646"
            "05fc99b67d2c71017d4f18177cb70a0d"
        ),
        "categoryCount": 10,
        "presetCount": 85,
        "status": "active",
        "activatedAt": "2026-07-21T00:00:00Z",
    }
    assert "local-service-principal-token" not in json.dumps(receipt)


def test_prod_activation_requires_explicit_gray_approval():
    transport = _FakeTransport(environment="prod")

    with pytest.raises(FilterCatalogPublishError, match="gray approval"):
        publish_filter_catalog(
            repo_root=REPO_ROOT,
            environment="prod",
            base_url="https://api.quwoquan.com",
            action=FilterCatalogPublishAction.activate,
            bearer_token="prod-service-principal-token",
            transport=transport,
        )

    assert transport.requests == []


def test_verify_is_public_and_rollback_uses_explicit_target_release():
    verify_transport = _FakeTransport(environment="beta")
    receipt = publish_filter_catalog(
        repo_root=REPO_ROOT,
        environment="beta",
        base_url="https://beta-api.quwoquan-env.test:18000",
        action=FilterCatalogPublishAction.verify,
        transport=verify_transport,
    )
    assert [request.method for request in verify_transport.requests] == ["GET"]
    assert "Authorization" not in verify_transport.requests[0].headers
    assert receipt["active"] is not None

    rollback_transport = _FakeTransport(
        environment="gamma",
        rollback_release_id="filter-catalog-previous",
    )
    rollback_receipt = publish_filter_catalog(
        repo_root=REPO_ROOT,
        environment="gamma",
        base_url="https://gamma-api.quwoquan-env.test:19000",
        action=FilterCatalogPublishAction.rollback,
        bearer_token="local-service-principal-token",
        rollback_release_id="filter-catalog-previous",
        transport=rollback_transport,
    )
    assert rollback_transport.requests[0].url.endswith(
        "/internal/content/filter-catalog-releases/"
        "filter-catalog-previous:rollback"
    )
    assert rollback_receipt["active"] == {
        "httpStatus": 200,
        "releaseId": "filter-catalog-previous",
        "canonicalDigest": "f" * 64,
        "categoryCount": 2,
        "presetCount": 3,
        "status": "active",
        "activatedAt": "2026-07-20T00:00:00Z",
    }
    assert rollback_receipt["releaseId"] == "filter-catalog-previous"
    assert rollback_receipt["canonicalDigest"] == "f" * 64
    assert rollback_receipt["categoryCount"] == 2
    assert rollback_receipt["presetCount"] == 3
