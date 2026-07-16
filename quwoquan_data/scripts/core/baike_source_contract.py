"""百科扩源契约的 registry 投影。

sourceScreen、Local Cursor SDK source bridge 与 downloader 必须消费同一映射；
本模块不得维护来源枚举副本，只能投影 content_source_registry.yaml。
"""
from __future__ import annotations

from fnmatch import fnmatch
from typing import Final
from urllib.parse import urlsplit

from core.content_source_registry import load_content_source_registry


def _homepage_policy() -> dict:
    registry = load_content_source_registry()
    return dict(((registry.get("lanePolicies") or {}).get("homepage") or {}))


def _primary_rows() -> list[dict]:
    return [
        dict(row)
        for row in (_homepage_policy().get("primarySources") or [])
        if isinstance(row, dict)
    ]


_ROWS: Final[list[dict]] = _primary_rows()
HOMEPAGE_SOURCE_POLICY_REVISION: Final[str] = str(
    _homepage_policy().get("homepageSourcePolicyRevision") or ""
)
SOURCE_PRIORITY: Final[tuple[str, ...]] = tuple(
    str(row.get("sourceKind") or "")
    for row in sorted(_ROWS, key=lambda row: int(row.get("probeOrder") or 0))
)
SOURCE_EXTRACTORS: Final[dict[str, str]] = {
    str(row.get("sourceKind") or ""): str(row.get("extractor") or "")
    for row in _ROWS
}
SOURCE_USE_MODES: Final[dict[str, str]] = {
    str(row.get("sourceKind") or ""): str(row.get("sourceUseMode") or "")
    for row in _ROWS
}
SOURCE_LICENSE_METADATA: Final[dict[str, dict[str, str]]] = {
    str(row.get("sourceKind") or ""): {
        key: str(row.get(key) or "")
        for key in ("license", "termsUrl", "licenseSnapshot")
        if str(row.get(key) or "")
    }
    for row in _ROWS
}
SOURCE_AUTHORITY_RANKS: Final[dict[str, int]] = {
    str(row.get("sourceKind") or ""): int(row.get("authorityRank") or 0)
    for row in _ROWS
}
SOURCE_HOSTS: Final[dict[str, frozenset[str]]] = {
    str(row.get("sourceKind") or ""): frozenset(
        str(host).casefold() for host in (row.get("hosts") or []) if str(host)
    )
    for row in _ROWS
}
SOURCE_URL_PATTERNS: Final[dict[str, tuple[str, ...]]] = {
    str(row.get("sourceKind") or ""): tuple(
        str(pattern) for pattern in (row.get("urlPatterns") or []) if str(pattern)
    )
    for row in _ROWS
}
PRIMARY_AUTHORITY_SOURCE_KINDS: Final[frozenset[str]] = frozenset(SOURCE_PRIORITY)
SOURCE_AUTHORITY_ROLES: Final[dict[str, str]] = {
    kind: "primary" for kind in SOURCE_PRIORITY
}
ENCYCLOPEDIA_SOURCE_KINDS: Final[frozenset[str]] = PRIMARY_AUTHORITY_SOURCE_KINDS


def source_url_matches_contract(source_kind: str, url: str) -> bool:
    """最终 URL 必须同时命中 HTTPS、host allowlist 与 registry URL pattern。"""
    parsed = urlsplit(str(url or ""))
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    if parsed.hostname.casefold() not in SOURCE_HOSTS.get(source_kind, frozenset()):
        return False
    return any(fnmatch(url, pattern) for pattern in SOURCE_URL_PATTERNS.get(source_kind, ()))


def source_identity_matches_contract(
    *,
    source_kind: str,
    url: str,
    extractor: str,
    policy_revision: str,
) -> bool:
    """校验主页百科来源的完整显式身份，禁止 host 猜测与 generic extractor 旁路。"""
    kind = str(source_kind or "").strip()
    return (
        str(policy_revision or "").strip() == HOMEPAGE_SOURCE_POLICY_REVISION
        and kind in PRIMARY_AUTHORITY_SOURCE_KINDS
        and str(extractor or "").strip() == SOURCE_EXTRACTORS.get(kind)
        and source_url_matches_contract(kind, url)
    )


def source_contract_issues(supported_extractors: set[str] | frozenset[str]) -> list[str]:
    """返回 bridge/sourceScreen 与 downloader extractor 的漂移问题。"""
    issues = [
        f"{kind}: extractor {extractor!r} is not supported by downloader"
        for kind, extractor in SOURCE_EXTRACTORS.items()
        if extractor not in supported_extractors
    ]
    if HOMEPAGE_SOURCE_POLICY_REVISION != "encyclopedia-primary-v2":
        issues.append("homepage source policy revision must be encyclopedia-primary-v2")
    if len(SOURCE_PRIORITY) != 4 or len(set(SOURCE_PRIORITY)) != 4:
        issues.append("homepage primary source closed set must contain four unique source kinds")
    if SOURCE_AUTHORITY_RANKS.get("sogou_baike") != SOURCE_AUTHORITY_RANKS.get("toutiao_baike"):
        issues.append("sogou_baike and toutiao_baike must share authorityRank")
    for kind in SOURCE_PRIORITY:
        if not SOURCE_HOSTS.get(kind):
            issues.append(f"{kind}: hosts missing")
        if not SOURCE_URL_PATTERNS.get(kind):
            issues.append(f"{kind}: urlPatterns missing")
        if SOURCE_EXTRACTORS.get(kind) == "generic_html":
            issues.append(f"{kind}: homepage primary must not use generic_html extractor")
    return issues


__all__ = [
    "ENCYCLOPEDIA_SOURCE_KINDS",
    "HOMEPAGE_SOURCE_POLICY_REVISION",
    "PRIMARY_AUTHORITY_SOURCE_KINDS",
    "SOURCE_AUTHORITY_ROLES",
    "SOURCE_AUTHORITY_RANKS",
    "SOURCE_EXTRACTORS",
    "SOURCE_LICENSE_METADATA",
    "SOURCE_HOSTS",
    "SOURCE_PRIORITY",
    "SOURCE_URL_PATTERNS",
    "SOURCE_USE_MODES",
    "source_contract_issues",
    "source_identity_matches_contract",
    "source_url_matches_contract",
]
