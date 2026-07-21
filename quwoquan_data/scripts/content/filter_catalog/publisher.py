"""FilterCatalogRelease 受信发布面的环境导入与公开读取复核。"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
from pathlib import Path
import socket
import ssl
from typing import Protocol
from urllib import error, request
from urllib.parse import quote, urlsplit

from content.filter_catalog.environment_import import (
    FilterCatalogEnvironmentImport,
    load_environment_import,
)
from content.filter_catalog.codec import canonical_json_bytes
from content.filter_catalog.contract import CatalogContractError


PUBLISH_REQUEST_TIMEOUT_SECONDS = 3.0
_LOCAL_TLS_HOST_SUFFIX = ".quwoquan-env.test"
_LOCAL_TLS_HOSTS = {"localhost", "127.0.0.1", "::1"}


class FilterCatalogPublishAction(StrEnum):
    stage = "stage"
    activate = "activate"
    stage_and_activate = "stage-and-activate"
    verify = "verify"
    rollback = "rollback"


@dataclass(frozen=True)
class FilterCatalogHttpResponse:
    status: int
    body: dict[str, object]


class FilterCatalogHttpTransport(Protocol):
    def request_json(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
    ) -> FilterCatalogHttpResponse: ...


class FilterCatalogPublishError(CatalogContractError):
    """不携带 token 或目录正文的发布面失败。"""


class UrllibFilterCatalogHttpTransport:
    def __init__(self, *, insecure_local_tls: bool) -> None:
        self._insecure_local_tls = insecure_local_tls

    def request_json(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
    ) -> FilterCatalogHttpResponse:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        context = (
            ssl._create_unverified_context()
            if self._insecure_local_tls
            else ssl.create_default_context()
        )
        original_getaddrinfo = socket.getaddrinfo
        if self._insecure_local_tls and host.endswith(_LOCAL_TLS_HOST_SUFFIX):
            socket.getaddrinfo = _loopback_getaddrinfo(original_getaddrinfo)
        try:
            response_request = request.Request(
                url,
                data=body,
                headers=headers,
                method=method,
            )
            try:
                with request.urlopen(
                    response_request,
                    timeout=PUBLISH_REQUEST_TIMEOUT_SECONDS,
                    context=context,
                ) as response:
                    return FilterCatalogHttpResponse(
                        status=response.status,
                        body=_decode_json_object(response.read(), response.status),
                    )
            except error.HTTPError as exc:
                _raise_http_error(exc)
        except error.URLError as exc:
            raise FilterCatalogPublishError(
                f"FilterCatalogRelease publish request unavailable: {exc.reason}"
            ) from exc
        finally:
            socket.getaddrinfo = original_getaddrinfo


def publish_filter_catalog(
    *,
    repo_root: Path,
    environment: str,
    base_url: str,
    action: FilterCatalogPublishAction,
    bearer_token: str | None = None,
    rollback_release_id: str = "",
    allow_gray_activation: bool = False,
    insecure_local_tls: bool = False,
    transport: FilterCatalogHttpTransport | None = None,
) -> dict[str, object]:
    """执行可重放 Stage/Activate/Rollback 或只读 active release 复核。"""
    environment_input = load_environment_import(
        repo_root=repo_root,
        environment=environment,
    )
    normalized_base_url = _normalize_base_url(
        base_url,
        insecure_local_tls=insecure_local_tls,
    )
    _validate_action(
        environment_input=environment_input,
        action=action,
        bearer_token=bearer_token,
        rollback_release_id=rollback_release_id,
        allow_gray_activation=allow_gray_activation,
    )
    client = transport or UrllibFilterCatalogHttpTransport(
        insecure_local_tls=insecure_local_tls,
    )
    receipts: list[dict[str, object]] = []

    if action in {
        FilterCatalogPublishAction.stage,
        FilterCatalogPublishAction.stage_and_activate,
    }:
        staged = _mutate(
            client=client,
            base_url=normalized_base_url,
            path=environment_input.operation_paths["stage"],
            idempotency_key=_idempotency_key(environment_input, "stage"),
            bearer_token=_required_token(bearer_token),
            body=canonical_json_bytes(environment_input.stage_payload()),
        )
        _assert_release_response(
            staged,
            environment_input=environment_input,
            allowed_statuses={"staged", "active"},
            operation="stage",
        )
        receipts.append(_receipt("stage", staged))

    if action in {
        FilterCatalogPublishAction.activate,
        FilterCatalogPublishAction.stage_and_activate,
    }:
        activated = _mutate(
            client=client,
            base_url=normalized_base_url,
            path=_release_path(
                environment_input.operation_paths["activate"],
                environment_input.release_id,
            ),
            idempotency_key=_idempotency_key(environment_input, "activate"),
            bearer_token=_required_token(bearer_token),
            body=None,
        )
        _assert_release_response(
            activated,
            environment_input=environment_input,
            allowed_statuses={"active"},
            operation="activate",
        )
        receipts.append(_receipt("activate", activated))

    expected_release_id = environment_input.release_id
    if action is FilterCatalogPublishAction.rollback:
        expected_release_id = rollback_release_id.strip()
        rolled_back = _mutate(
            client=client,
            base_url=normalized_base_url,
            path=_release_path(
                environment_input.operation_paths["rollback"],
                expected_release_id,
            ),
            idempotency_key=_idempotency_key(
                environment_input,
                "rollback-" + expected_release_id,
            ),
            bearer_token=_required_token(bearer_token),
            body=None,
        )
        _assert_rollback_response(
            rolled_back,
            expected_release_id=expected_release_id,
        )
        receipts.append(_receipt("rollback", rolled_back))

    active: dict[str, object] | None = None
    if action is not FilterCatalogPublishAction.stage:
        active_response = _read_active(
            client=client,
            base_url=normalized_base_url,
            path=environment_input.operation_paths["read"],
        )
        if action is FilterCatalogPublishAction.rollback:
            _assert_active_release_id(
                active_response,
                expected_release_id=expected_release_id,
            )
        else:
            _assert_active_snapshot(
                active_response,
                environment_input=environment_input,
            )
        active = _active_evidence(active_response)

    requested_catalog = {
        "releaseId": environment_input.release_id,
        "canonicalDigest": environment_input.canonical_digest,
        "categoryCount": environment_input.category_count,
        "presetCount": environment_input.preset_count,
    }
    effective_catalog = active or requested_catalog
    return {
        "schema": "quwoquan_data.filter_catalog_publish_receipt",
        "passed": True,
        "environment": environment_input.environment,
        "action": action.value,
        "manifestRef": environment_input.manifest_ref,
        "canonicalArtifactRef": environment_input.canonical_artifact_ref,
        "requestedCatalog": requested_catalog,
        "releaseId": effective_catalog["releaseId"],
        "canonicalDigest": effective_catalog["canonicalDigest"],
        "categoryCount": effective_catalog["categoryCount"],
        "presetCount": effective_catalog["presetCount"],
        "receipts": receipts,
        "active": active,
    }


def _validate_action(
    *,
    environment_input: FilterCatalogEnvironmentImport,
    action: FilterCatalogPublishAction,
    bearer_token: str | None,
    rollback_release_id: str,
    allow_gray_activation: bool,
) -> None:
    mutating_actions = {
        FilterCatalogPublishAction.stage,
        FilterCatalogPublishAction.activate,
        FilterCatalogPublishAction.stage_and_activate,
        FilterCatalogPublishAction.rollback,
    }
    if action in mutating_actions:
        _required_token(bearer_token)
    if action is FilterCatalogPublishAction.rollback and not rollback_release_id.strip():
        raise FilterCatalogPublishError(
            "RollbackFilterCatalogRelease requires rollback_release_id"
        )
    if (
        environment_input.activation_policy == "stage_then_gray_activate"
        and action
        in {
            FilterCatalogPublishAction.activate,
            FilterCatalogPublishAction.stage_and_activate,
        }
        and not allow_gray_activation
    ):
        raise FilterCatalogPublishError(
            "production FilterCatalogRelease activation requires explicit gray approval"
        )


def _normalize_base_url(value: str, *, insecure_local_tls: bool) -> str:
    normalized = value.strip()
    parsed = urlsplit(normalized)
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme not in {"http", "https"}
        or not host
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise FilterCatalogPublishError(
            "FilterCatalogRelease publish base URL must be an absolute origin"
        )
    is_local_host = host in _LOCAL_TLS_HOSTS or host.endswith(_LOCAL_TLS_HOST_SUFFIX)
    if parsed.scheme == "http" and not is_local_host:
        raise FilterCatalogPublishError(
            "FilterCatalogRelease publish requires HTTPS outside local targets"
        )
    if insecure_local_tls and not is_local_host:
        raise FilterCatalogPublishError(
            "insecure local TLS is restricted to declared local environment hosts"
        )
    return normalized.rstrip("/")


def _required_token(value: str | None) -> str:
    token = (value or "").strip()
    if not token:
        raise FilterCatalogPublishError(
            "FilterCatalogRelease publish bearer token is required for mutations"
        )
    return token


def _mutate(
    *,
    client: FilterCatalogHttpTransport,
    base_url: str,
    path: str,
    idempotency_key: str,
    bearer_token: str,
    body: bytes | None,
) -> FilterCatalogHttpResponse:
    headers = {
        "Accept": "application/json",
        "Authorization": "Bearer " + bearer_token,
        "Idempotency-Key": idempotency_key,
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    return client.request_json(
        method="POST",
        url=base_url + path,
        headers=headers,
        body=body,
    )


def _read_active(
    *,
    client: FilterCatalogHttpTransport,
    base_url: str,
    path: str,
) -> FilterCatalogHttpResponse:
    return client.request_json(
        method="GET",
        url=base_url + path,
        headers={"Accept": "application/json"},
        body=None,
    )


def _release_path(template: str, release_id: str) -> str:
    path = template.replace(
        "{releaseId}",
        quote(release_id, safe="-._~"),
    )
    if "{" in path or "}" in path:
        raise FilterCatalogPublishError(
            "FilterCatalogRelease metadata path has unresolved parameters"
        )
    return path


def _idempotency_key(
    environment_input: FilterCatalogEnvironmentImport,
    operation: str,
) -> str:
    return f"{environment_input.idempotency_key}:{operation}"


def _assert_release_response(
    response: FilterCatalogHttpResponse,
    *,
    environment_input: FilterCatalogEnvironmentImport,
    allowed_statuses: set[str],
    operation: str,
) -> None:
    if response.status != 200:
        raise FilterCatalogPublishError(
            f"FilterCatalogRelease {operation} returned HTTP {response.status}"
        )
    body = response.body
    if (
        body.get("releaseId") != environment_input.release_id
        or body.get("canonicalDigest") != environment_input.canonical_digest
        or body.get("status") not in allowed_statuses
    ):
        raise FilterCatalogPublishError(
            f"FilterCatalogRelease {operation} response does not match canonical input"
        )


def _assert_rollback_response(
    response: FilterCatalogHttpResponse,
    *,
    expected_release_id: str,
) -> None:
    if (
        response.status != 200
        or response.body.get("releaseId") != expected_release_id
        or response.body.get("status") != "active"
    ):
        raise FilterCatalogPublishError(
            "RollbackFilterCatalogRelease response does not activate requested release"
        )


def _assert_active_snapshot(
    response: FilterCatalogHttpResponse,
    *,
    environment_input: FilterCatalogEnvironmentImport,
) -> None:
    _assert_active_release_id(
        response,
        expected_release_id=environment_input.release_id,
    )
    body = response.body
    if (
        body.get("canonicalDigest") != environment_input.canonical_digest
        or body.get("categoryCount") != environment_input.category_count
        or body.get("presetCount") != environment_input.preset_count
    ):
        raise FilterCatalogPublishError(
            "GetActiveFilterCatalog response does not match canonical release evidence"
        )


def _assert_active_release_id(
    response: FilterCatalogHttpResponse,
    *,
    expected_release_id: str,
) -> None:
    if (
        response.status != 200
        or response.body.get("releaseId") != expected_release_id
        or response.body.get("status") != "active"
    ):
        raise FilterCatalogPublishError(
            "GetActiveFilterCatalog response does not expose requested active release"
        )


def _receipt(operation: str, response: FilterCatalogHttpResponse) -> dict[str, object]:
    return {
        "operation": operation,
        "httpStatus": response.status,
        "releaseId": response.body.get("releaseId"),
        "status": response.body.get("status"),
    }


def _active_evidence(response: FilterCatalogHttpResponse) -> dict[str, object]:
    body = response.body
    return {
        "httpStatus": response.status,
        "releaseId": body.get("releaseId"),
        "canonicalDigest": body.get("canonicalDigest"),
        "categoryCount": body.get("categoryCount"),
        "presetCount": body.get("presetCount"),
        "status": body.get("status"),
        "activatedAt": body.get("activatedAt"),
    }


def _decode_json_object(raw: bytes, status: int) -> dict[str, object]:
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FilterCatalogPublishError(
            f"FilterCatalogRelease response HTTP {status} is not a JSON object"
        ) from exc
    if not isinstance(decoded, dict):
        raise FilterCatalogPublishError(
            f"FilterCatalogRelease response HTTP {status} is not a JSON object"
        )
    return decoded


def _raise_http_error(exc: error.HTTPError) -> None:
    try:
        body = _decode_json_object(exc.read(), exc.code)
    except FilterCatalogPublishError:
        raise FilterCatalogPublishError(
            f"FilterCatalogRelease request failed with HTTP {exc.code}"
        ) from exc
    code = _error_code(body)
    suffix = f" ({code})" if code else ""
    raise FilterCatalogPublishError(
        f"FilterCatalogRelease request failed with HTTP {exc.code}{suffix}"
    ) from exc


def _error_code(body: dict[str, object]) -> str:
    direct = body.get("code")
    if isinstance(direct, str):
        return direct
    nested = body.get("error")
    if isinstance(nested, dict):
        nested_code = nested.get("code")
        if isinstance(nested_code, str):
            return nested_code
    return ""


def _loopback_getaddrinfo(original: object):
    def getaddrinfo(host: object, *args: object, **kwargs: object):
        if isinstance(host, str) and host.endswith(_LOCAL_TLS_HOST_SUFFIX):
            host = "127.0.0.1"
        return original(host, *args, **kwargs)  # type: ignore[operator]

    return getaddrinfo
