"""App 可见来源 URL 的 canonical HTTPS 安全门。"""
from __future__ import annotations

import ipaddress
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from core.baike_source_contract import source_url_matches_contract


_PRIVATE_HOSTS = {"localhost", "localhost.localdomain"}
_SENSITIVE_QUERY_MARKERS = (
    "token",
    "signature",
    "session",
    "cookie",
    "credential",
    "auth",
    "expires",
    "x-amz-",
)
_TRACKING_QUERY_MARKERS = ("utm_", "spm", "from", "ref", "source", "campaign")


def _host_is_public(host: str) -> bool:
    normalized = host.strip().lower().rstrip(".")
    if not normalized or normalized in _PRIVATE_HOSTS or normalized.endswith(".local"):
        return False
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return True
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
    )


def normalize_public_source_url(url: str, *, source_kind: str) -> str:
    parsed = urlsplit(str(url or "").strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme.lower() != "https" or not _host_is_public(host):
        raise ValueError("public source URL must be canonical public HTTPS")
    if parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("public source URL must not contain credentials or custom port")
    safe_query: list[tuple[str, str]] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        marker = key.lower()
        if any(part in marker for part in _SENSITIVE_QUERY_MARKERS):
            raise ValueError(f"public source URL contains sensitive query field: {key}")
        if any(marker == part or marker.startswith(part) for part in _TRACKING_QUERY_MARKERS):
            continue
        safe_query.append((key, value))
    canonical = urlunsplit(
        ("https", host, parsed.path or "/", urlencode(sorted(safe_query)), "")
    )
    if not source_url_matches_contract(source_kind, canonical):
        raise ValueError(f"public source URL does not match sourceKind={source_kind}")
    return canonical
