"""本地环境 JSON HTTP 传输层（逐字搬移）。

``request_local_environment_json`` / ``request_local_environment_public_json``
是测试的 patch 锚点；会话编排模块经 ``_pkg.`` 消费它们。
"""

from __future__ import annotations

import json
import ssl
from typing import Any
from urllib import error, request
from urllib.parse import urlparse

from ..local_target_handoff import target_for_hostname
from ..public_domain_tls import root_certificate_path
from .models import LocalAcceptanceSession, LocalEnvironmentHTTPError


def request_local_environment_json(
    base_url: str,
    *,
    path: str,
    session: LocalAcceptanceSession,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 12.0,
) -> dict[str, Any]:
    """Call a local environment JSON endpoint using bearer auth without logging it."""

    normalized_path = path if path.startswith("/") else "/" + path
    payload = (
        json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    )
    request_headers = {
        "Accept": "application/json",
        "Authorization": session.authorization_header(),
        "X-Client-Session-Id": "local-acceptance-" + session.owner_id[-12:],
    }
    for name, value in (headers or {}).items():
        if name.lower() == "authorization":
            raise ValueError("local environment request headers cannot override Authorization")
        request_headers[name] = value
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
    status, response = _trusted_json_request(
        method=method,
        url=base_url.rstrip("/") + normalized_path,
        body=payload,
        headers=request_headers,
        timeout_seconds=timeout_seconds,
    )
    if status < 200 or status >= 300:
        raise LocalEnvironmentHTTPError(method=method, path=normalized_path, status=status)
    return response


def request_local_environment_public_json(
    base_url: str,
    *,
    path: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 12.0,
) -> dict[str, Any]:
    """Call a public local-environment JSON endpoint without forged identity."""

    normalized_path = path if path.startswith("/") else "/" + path
    payload = (
        json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    )
    request_headers = {"Accept": "application/json"}
    for name, value in (headers or {}).items():
        if name.lower() in {"authorization", "x-client-user-id"}:
            raise ValueError("public local environment request cannot inject identity")
        request_headers[name] = value
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
    status, response = _trusted_json_request(
        method=method,
        url=base_url.rstrip("/") + normalized_path,
        body=payload,
        headers=request_headers,
        timeout_seconds=timeout_seconds,
    )
    if status < 200 or status >= 300:
        raise LocalEnvironmentHTTPError(
            method=method, path=normalized_path, status=status
        )
    return response


def _trusted_json_request(
    *,
    method: str,
    url: str,
    body: bytes | None,
    headers: dict[str, str],
    timeout_seconds: float,
) -> tuple[int, dict[str, Any]]:
    target_host = urlparse(url).hostname
    if not target_host:
        raise ValueError("local environment request URL has no hostname")
    target_name = target_for_hostname(target_host)
    if target_name is None:
        raise ValueError("local environment request URL is not a canonical local target")
    ca_file = root_certificate_path(target_name)
    if not ca_file.is_file() or ca_file.is_symlink():
        raise RuntimeError("local environment request root certificate is unavailable")
    context = ssl.create_default_context(cafile=str(ca_file))
    req = request.Request(url, data=body, headers=headers, method=method)
    opener = request.build_opener(
        request.ProxyHandler({}),
        request.HTTPSHandler(context=context),
    )
    try:
        with opener.open(
            req,
            timeout=max(1.0, timeout_seconds),
        ) as response:
            status = int(response.status)
            raw = response.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"local environment request transport failed: {type(exc).__name__}") from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"local environment request {method} returned non-JSON HTTP {status}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"local environment request {method} returned non-object JSON HTTP {status}")
    return status, parsed
