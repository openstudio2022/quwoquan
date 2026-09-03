"""Credential-free transport for professional video acquisition."""
from __future__ import annotations

import ipaddress
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from core.content_library import link_from_library
from content.source.professional_image_network_admission import (
    https_tls_peer,
    resolve_https_admission,
    verified_tls_context,
)

_MAX_VIDEO_BYTES = 512 * 1024 * 1024
_SOURCE_VIDEO_READ_TIMEOUT_SECONDS = 180
_DOWNLOAD_FETCH_RETRY_LIMIT = 1
_RETRY_DELAY_SECONDS = 1
_MIN_VIDEO_BYTES = 8_000
_VIDEO_EXTENSIONS = frozenset({".mp4", ".webm", ".ogv", ".mov"})
_CONTENT_TYPE_EXTENSIONS = {
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/ogg": ".ogv",
    # Wikimedia Commons serves .ogv files with the canonical IANA Ogg
    # container type; media probe + semantic review still gate the content.
    "application/ogg": ".ogv",
    "video/quicktime": ".mov",
    "application/octet-stream": "",
}
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


def redact_sensitive_video_url(value: str) -> str:
    parsed = urllib.parse.urlparse(str(value or ""))
    if parsed.scheme not in {"http", "https"}:
        return str(value or "")
    if parsed.username or parsed.password:
        host = parsed.hostname or ""
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        parsed = parsed._replace(
            netloc=f"{host}:{parsed.port}" if parsed.port is not None else host
        )
    if not parsed.query:
        return urllib.parse.urlunparse(parsed)
    redacted_query = urllib.parse.urlencode([
        (
            key,
            "REDACTED"
            if any(marker in key.casefold() for marker in _SENSITIVE_QUERY_MARKERS)
            else item,
        )
        for key, item in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    ])
    return urllib.parse.urlunparse(parsed._replace(query=redacted_query))


def _validated_https_url(url: str, *, allow_signed_query: bool) -> str:
    parsed = urllib.parse.urlparse(str(url or "").strip())
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("professional video asset URL must use public HTTPS")
    if parsed.username or parsed.password:
        raise ValueError("professional video asset URL must not embed credentials")
    host = parsed.hostname.casefold()
    if host == "localhost" or host.endswith(".local"):
        raise ValueError("professional video asset URL must not target a local host")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("professional video asset URL must not target a private address")
    if not allow_signed_query:
        query_keys = {
            key.casefold()
            for key, _value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        }
        if any(
            marker in key
            for key in query_keys
            for marker in _SENSITIVE_QUERY_MARKERS
        ):
            raise ValueError(
                "public_direct video URL must not carry credential-like query parameters"
            )
    return parsed.geturl()


def _assert_public_resolution(url: str) -> dict[str, object]:
    return resolve_https_admission(url)


def _source_suffix(url: str, content_type: str) -> str:
    declared = Path(urllib.parse.urlparse(url).path).suffix.lower()
    if declared in _VIDEO_EXTENSIONS:
        return declared
    inferred = _CONTENT_TYPE_EXTENSIONS.get(content_type, "")
    if inferred:
        return inferred
    raise ValueError("professional video container is not supported")


class _PublicRedirects(urllib.request.HTTPRedirectHandler):
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


def _fetch_public_video_once(
    url: str,
    destination: Path,
    *,
    supported_api: bool,
) -> str:
    normalized = _validated_https_url(url, allow_signed_query=supported_api)
    _assert_public_resolution(normalized)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=verified_tls_context()),
        _PublicRedirects(allow_signed_query=supported_api),
    )
    request = urllib.request.Request(
        normalized,
        headers={"User-Agent": "quwoquan-data/1.0"},
    )
    timeout = _SOURCE_VIDEO_READ_TIMEOUT_SECONDS
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with opener.open(request, timeout=timeout) as response:
            final_url = _validated_https_url(
                str(response.geturl()),
                allow_signed_query=supported_api,
            )
            admission = _assert_public_resolution(final_url)
            https_tls_peer(
                response,
                requested_url=normalized,
                final_url=final_url,
                admission=admission,
            )
            content_type = str(
                response.headers.get("Content-Type") or ""
            ).split(";", 1)[0].strip().casefold()
            if content_type not in _CONTENT_TYPE_EXTENSIONS:
                raise ValueError(
                    f"professional video response is not video: {content_type}"
                )
            content_length = int(response.headers.get("Content-Length") or 0)
            if content_length > _MAX_VIDEO_BYTES:
                raise ValueError("professional video exceeds maximum acquisition size")
            written = 0
            with destination.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > _MAX_VIDEO_BYTES:
                        raise ValueError(
                            "professional video exceeds maximum acquisition size"
                        )
                    output.write(chunk)
            if written < _MIN_VIDEO_BYTES:
                raise ValueError("professional video payload is empty or truncated")
            return _source_suffix(final_url, content_type)
    except (OSError, TimeoutError, urllib.error.URLError):
        destination.unlink(missing_ok=True)
        raise
    except ValueError:
        destination.unlink(missing_ok=True)
        raise


def fetch_public_video(
    url: str,
    destination: Path,
    *,
    supported_api: bool,
) -> str:
    """Retry transient anonymous fetches within the governed download budget."""
    attempts = _DOWNLOAD_FETCH_RETRY_LIMIT + 1
    for attempt in range(1, attempts + 1):
        try:
            return _fetch_public_video_once(
                url,
                destination,
                supported_api=supported_api,
            )
        except (OSError, TimeoutError, urllib.error.URLError):
            if attempt >= attempts:
                raise
            time.sleep(_RETRY_DELAY_SECONDS * attempt)
    raise RuntimeError("professional video acquisition retry loop exhausted")


def copy_manual_video(relative_ref: str, destination: Path, *, manual_root: Path) -> str:
    relative = Path(str(relative_ref or "").strip())
    if not str(relative) or relative.is_absolute() or ".." in relative.parts:
        raise ValueError("manualFile must be a safe non-empty relative path")
    root = manual_root.resolve()
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("manualFile must not traverse a symlink")
    source = (root / relative).resolve()
    if source != root and root not in source.parents:
        raise ValueError("manualFile escapes the declared manual root")
    if not source.is_file():
        raise FileNotFoundError(source)
    size = source.stat().st_size
    if size < _MIN_VIDEO_BYTES or size > _MAX_VIDEO_BYTES:
        raise ValueError("manual professional video size is outside admission limits")
    suffix = source.suffix.lower()
    if suffix not in _VIDEO_EXTENSIONS:
        raise ValueError("manual professional video container is not supported")
    destination.parent.mkdir(parents=True, exist_ok=True)
    link_from_library(source, destination, kind="media")
    return suffix


__all__ = [
    "copy_manual_video",
    "fetch_public_video",
    "redact_sensitive_video_url",
]
