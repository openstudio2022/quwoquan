"""Typed public API adapter shared by environment release verification."""
from __future__ import annotations

import ipaddress
import json
import socket
import ssl
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

from core.runtime_policy import active_runtime_policy


class PublicApiClientError(ValueError):
    """A public environment API request could not produce a JSON response."""


@dataclass(frozen=True)
class PublicApiResponse:
    status: int
    payload: Mapping[str, Any]


@contextmanager
def _temporary_host_resolution(url: str, resolve_host: str):
    expected_host = urlparse(url).hostname or ""
    if not resolve_host or not expected_host:
        yield
        return
    original_getaddrinfo = socket.getaddrinfo

    def getaddrinfo(host: str | bytes | None, *args: Any, **kwargs: Any) -> Any:
        if host == expected_host:
            return original_getaddrinfo(resolve_host, *args, **kwargs)
        return original_getaddrinfo(host, *args, **kwargs)

    socket.getaddrinfo = getaddrinfo
    try:
        yield
    finally:
        socket.getaddrinfo = original_getaddrinfo


@dataclass(frozen=True)
class PublicApiClient:
    base_url: str
    insecure_tls: bool
    resolve_host: str = ""

    def __post_init__(self) -> None:
        if not self.base_url.startswith(("http://", "https://")):
            raise PublicApiClientError("public API base URL must be http(s)")
        if self.resolve_host:
            try:
                ipaddress.ip_address(self.resolve_host)
            except ValueError as exc:
                raise PublicApiClientError("public API resolve host must be an IP address") from exc

    def get_json(
        self,
        path: str,
        *,
        query: Mapping[str, str] | None = None,
    ) -> PublicApiResponse:
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        if query:
            url = f"{url}?{urlencode(query)}"
        context = ssl._create_unverified_context() if self.insecure_tls else None  # noqa: SLF001
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "X-Client-Page-Id": "entity.homepage.introduction",
            },
            method="GET",
        )
        handlers = [ProxyHandler({})]
        if context is not None:
            handlers.append(HTTPSHandler(context=context))
        opener = build_opener(*handlers)
        try:
            with _temporary_host_resolution(url, self.resolve_host):
                with opener.open(
                    request,
                    timeout=active_runtime_policy().api_request_timeout_seconds,
                ) as response:  # noqa: S310
                    status = int(response.status)
                    raw = response.read()
        except HTTPError as exc:
            status = int(exc.code)
            raw = exc.read()
        except (URLError, OSError) as exc:
            raise PublicApiClientError(f"GET {url} failed: {exc}") from exc
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PublicApiClientError(f"GET {url} returned invalid JSON") from exc
        if not isinstance(payload, Mapping):
            raise PublicApiClientError(f"GET {url} returned a non-object JSON payload")
        return PublicApiResponse(status=status, payload=payload)


__all__ = ["PublicApiClient", "PublicApiClientError", "PublicApiResponse"]
