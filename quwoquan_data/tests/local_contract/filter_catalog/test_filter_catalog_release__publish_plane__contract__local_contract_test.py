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
from quwoquan_ops.cli.lib.environment_topology import (
    ENVIRONMENT_CANONICAL_TARGET,
    get_target,
    load_environment_topology,
)


REPO_ROOT = Path(__file__).resolve().parents[4]


def _api_base(environment: str) -> str:
    return str(
        get_target(
            load_environment_topology(),
            ENVIRONMENT_CANONICAL_TARGET[environment],
        )["publicBases"]["api"]
    )


@dataclass(frozen=True)
class _Request:
    method: str
    url: str
    headers: dict[str, str]
    body: bytes | None


class _FakeTransport:
    def __init__(
        self,
        *,
        environment: str,
        rollback_release_id: str = "",
        active_matches: bool = True,
    ) -> None:
        self._input = load_environment_import(
            repo_root=REPO_ROOT,
            environment=environment,
        )
        self._rollback_release_id = rollback_release_id
        self._active_matches = active_matches
        self._active_read_count = 0
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
            should_match = self._active_matches or self._active_read_count > 0
            self._active_read_count += 1
            return FilterCatalogHttpResponse(
                status=200,
                body={
                    **self._release_body("active"),
                    "canonicalDigest": (
                        self._input.canonical_digest
                        if should_match
                        else "0" * 64
                    ),
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


def test_public_tls_publish_uses_system_trust_context():
    response = _UrllibResponse()
    system_context = object()
    with (
        mock.patch.object(
            publisher.ssl,
            "create_default_context",
            return_value=system_context,
        ) as create_default_context,
        mock.patch.object(
            publisher.request,
            "urlopen",
            return_value=response,
        ) as urlopen,
    ):
        result = publisher.UrllibFilterCatalogHttpTransport().request_json(
            method="GET",
            url="https://api.example.invalid/content/filter-catalog",
            headers={},
            body=None,
        )

    assert result == FilterCatalogHttpResponse(
        status=200,
        body={"releaseId": "filter-catalog-20260720-001"},
    )
    create_default_context.assert_called_once_with()
    assert urlopen.call_args.kwargs["context"] is system_context


def test_gamma_publish_uses_metadata_paths_idempotency_and_canonical_payload():
    transport = _FakeTransport(environment="gamma", active_matches=False)

    receipt = publish_filter_catalog(
        repo_root=REPO_ROOT,
        environment="gamma",
        base_url=_api_base("gamma"),
        action=FilterCatalogPublishAction.stage_and_activate,
        bearer_token="local-service-principal-token",
        transport=transport,
    )

    assert [request.method for request in transport.requests] == [
        "GET",
        "POST",
        "POST",
        "GET",
    ]
    initial_read, stage, activate, public_read = transport.requests
    assert initial_read.url == f"{_api_base('gamma')}/content/filter-catalog"
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
            base_url=_api_base("prod"),
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
        base_url=_api_base("beta"),
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
        base_url=_api_base("gamma"),
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
