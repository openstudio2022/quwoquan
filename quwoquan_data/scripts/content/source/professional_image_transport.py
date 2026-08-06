"""Credential-free public transport for professional image acquisition."""

from __future__ import annotations

import hashlib
import ipaddress
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from core.runtime_policy import active_runtime_policy

from content.source.image_payload import sniff_image_ext

_SENSITIVE_QUERY_MARKERS = (
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "cookie",
    "password",
    "signature",
    "token",
)


def _is_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return address.is_global and not any(
        (
            address.is_link_local,
            address.is_loopback,
            address.is_multicast,
            address.is_private,
            address.is_reserved,
            address.is_unspecified,
        )
    )


def _validated_https_url(url: str, *, allow_signed_query: bool) -> str:
    """Return one normalized public HTTPS URL or fail before network access."""

    try:
        parsed = urllib.parse.urlparse(str(url or "").strip())
        port = parsed.port
    except ValueError as exc:
        raise ValueError("professional image asset URL is malformed") from exc
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("professional image asset URL must use public HTTPS")
    if parsed.username or parsed.password:
        raise ValueError("professional image asset URL must not embed credentials")
    host = parsed.hostname.casefold().rstrip(".")
    if host == "localhost" or host.endswith((".localhost", ".local")):
        raise ValueError("professional image asset URL must not target a local host")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not _is_public_address(address):
        raise ValueError(
            "professional image asset URL must not target a non-public address"
        )
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("professional image asset URL port is invalid")
    if not allow_signed_query:
        query_keys = {
            key.casefold()
            for key, _value in urllib.parse.parse_qsl(
                parsed.query,
                keep_blank_values=True,
            )
        }
        if any(
            marker in key for key in query_keys for marker in _SENSITIVE_QUERY_MARKERS
        ):
            raise ValueError(
                "public_direct image URL must not carry credential-like query parameters"
            )
    return parsed.geturl()


def _assert_public_resolution(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port or 443
    try:
        addresses = {
            result[4][0]
            for result in socket.getaddrinfo(
                host,
                port,
                type=socket.SOCK_STREAM,
            )
        }
    except socket.gaierror as exc:
        raise ValueError("professional image host DNS resolution failed") from exc
    try:
        non_public = not addresses or any(
            not _is_public_address(ipaddress.ip_address(address))
            for address in addresses
        )
    except ValueError as exc:
        raise ValueError(
            "professional image host returned an invalid DNS address"
        ) from exc
    if non_public:
        raise ValueError("professional image host resolves to a non-public address")


class _PublicImageRedirects(urllib.request.HTTPRedirectHandler):
    """Reapply URL and DNS admission to every redirect hop."""

    def __init__(self, *, allow_signed_query: bool) -> None:
        super().__init__()
        self.allow_signed_query = allow_signed_query

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        target = _validated_https_url(
            str(newurl),
            allow_signed_query=self.allow_signed_query,
        )
        _assert_public_resolution(target)
        return super().redirect_request(req, fp, code, msg, headers, target)


def _fetch_public_image_once(
    url: str,
    *,
    supported_api: bool,
    min_bytes: int,
    max_bytes: int,
) -> dict[str, Any] | None:
    normalized = _validated_https_url(url, allow_signed_query=supported_api)
    _assert_public_resolution(normalized)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _PublicImageRedirects(allow_signed_query=supported_api),
    )
    request = urllib.request.Request(
        normalized,
        headers={"User-Agent": "quwoquan-data/1.0"},
    )
    timeout = active_runtime_policy().page_image_download_timeout_seconds
    with opener.open(request, timeout=timeout) as response:
        final_url = _validated_https_url(
            str(response.geturl()),
            allow_signed_query=supported_api,
        )
        _assert_public_resolution(final_url)
        content_type = (
            str(response.headers.get("Content-Type") or "")
            .split(";", 1)[0]
            .strip()
            .casefold()
        )
        content_length = int(response.headers.get("Content-Length") or 0)
        if content_length > max_bytes:
            raise ValueError("professional image exceeds maximum acquisition size")
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError("professional image exceeds maximum acquisition size")
        if len(body) < min_bytes:
            return None
        ext = sniff_image_ext(body, content_type)
        if ext is None:
            return None
        return {
            "url": final_url,
            "requestedUrl": normalized,
            "normalizedFromUrl": normalized if final_url != normalized else "",
            "bytes": body,
            "ext": ext,
            "contentType": content_type,
            "sha256": hashlib.sha256(body).hexdigest(),
        }


def fetch_public_image(
    url: str,
    *,
    supported_api: bool,
    min_bytes: int,
    max_bytes: int,
) -> dict[str, Any] | None:
    """Fetch one image with governed retries and fail-closed URL admission."""

    policy = active_runtime_policy()
    attempts = policy.download_fetch_retry_limit + 1
    for attempt in range(1, attempts + 1):
        try:
            return _fetch_public_image_once(
                url,
                supported_api=supported_api,
                min_bytes=min_bytes,
                max_bytes=max_bytes,
            )
        except (OSError, TimeoutError, urllib.error.URLError):
            if attempt >= attempts:
                raise
            time.sleep(policy.curl_retry_delay_seconds * attempt)
    raise RuntimeError("professional image acquisition retry loop exhausted")


__all__ = ["fetch_public_image"]
