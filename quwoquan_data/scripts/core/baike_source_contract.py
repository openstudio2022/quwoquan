"""百科扩源契约的 registry 投影。

sourceScreen、Local Cursor SDK source bridge 与 downloader 必须消费同一映射；
本模块不得维护来源枚举副本，只能投影 content_source_registry.yaml。
"""
from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class EncyclopediaCanonicalResolutionPolicy:
    base_url: str
    candidate_limit: int
    require_geo_context_for_alias: bool
    canonical_confidence: float
    alias_confidence: float


@dataclass(frozen=True, slots=True)
class BaiduBaikeApiPolicy:
    base_url: str
    candidate_limit: int
    require_geo_context_for_alias: bool
    canonical_confidence: float
    alias_confidence: float
    fixed_query: tuple[tuple[str, str], ...]


def _canonical_resolution_policy(source_kind: str) -> EncyclopediaCanonicalResolutionPolicy:
    row = next(
        (
            item
            for item in _primary_rows()
            if str(item.get("sourceKind") or "") == source_kind
        ),
        None,
    )
    if row is None:
        raise ValueError(f"{source_kind} primary source contract is missing")
    raw = row.get("canonicalResolution")
    if not isinstance(raw, dict):
        raise ValueError(f"{source_kind}.canonicalResolution must be a mapping")
    base_url = str(raw.get("baseUrl") or "").strip()
    if not base_url.startswith("https://www.baike.com/wiki/"):
        raise ValueError(f"{source_kind}.canonicalResolution.baseUrl is invalid")
    candidate_limit = raw.get("candidateLimit")
    if (
        not isinstance(candidate_limit, int)
        or isinstance(candidate_limit, bool)
        or candidate_limit < 1
    ):
        raise ValueError(
            f"{source_kind}.canonicalResolution.candidateLimit must be positive"
        )
    require_geo = raw.get("requireGeoContextForAlias")
    if not isinstance(require_geo, bool):
        raise ValueError(
            f"{source_kind}.canonicalResolution.requireGeoContextForAlias must be boolean"
        )
    canonical_confidence = raw.get("canonicalConfidence")
    alias_confidence = raw.get("aliasConfidence")
    for field, value in (
        ("canonicalConfidence", canonical_confidence),
        ("aliasConfidence", alias_confidence),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not 0 < float(value) <= 1
        ):
            raise ValueError(
                f"{source_kind}.canonicalResolution.{field} must be within (0, 1]"
            )
    return EncyclopediaCanonicalResolutionPolicy(
        base_url=base_url,
        candidate_limit=candidate_limit,
        require_geo_context_for_alias=require_geo,
        canonical_confidence=float(canonical_confidence),
        alias_confidence=float(alias_confidence),
    )


def _baidu_api_policy() -> BaiduBaikeApiPolicy:
    row = next(
        (
            item
            for item in _primary_rows()
            if str(item.get("sourceKind") or "") == "baidu_baike"
        ),
        None,
    )
    if row is None:
        raise ValueError("baidu_baike primary source contract is missing")
    raw = row.get("canonicalResolution")
    if not isinstance(raw, dict):
        raise ValueError("baidu_baike.canonicalResolution must be a mapping")
    base_url = str(raw.get("baseUrl") or "").strip()
    expected = "https://baike.baidu.com/api/openapi/BaikeLemmaCardApi"
    if base_url != expected:
        raise ValueError("baidu_baike.canonicalResolution.baseUrl is invalid")
    candidate_limit = raw.get("candidateLimit")
    if isinstance(candidate_limit, bool) or not isinstance(candidate_limit, int) or candidate_limit < 1:
        raise ValueError("baidu_baike.canonicalResolution.candidateLimit must be positive")
    require_geo = raw.get("requireGeoContextForAlias")
    if not isinstance(require_geo, bool):
        raise ValueError("baidu_baike.canonicalResolution.requireGeoContextForAlias must be boolean")
    canonical_confidence = raw.get("canonicalConfidence")
    alias_confidence = raw.get("aliasConfidence")
    for field, value in (
        ("canonicalConfidence", canonical_confidence),
        ("aliasConfidence", alias_confidence),
    ):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < float(value) <= 1:
            raise ValueError(f"baidu_baike.canonicalResolution.{field} must be within (0, 1]")
    fixed_query = raw.get("fixedQuery")
    if not isinstance(fixed_query, dict) or not fixed_query:
        raise ValueError("baidu_baike.canonicalResolution.fixedQuery must be a non-empty mapping")
    normalized_query = tuple(
        sorted((str(key), str(value)) for key, value in fixed_query.items() if str(key) and str(value))
    )
    if len(normalized_query) != len(fixed_query):
        raise ValueError("baidu_baike.canonicalResolution.fixedQuery contains empty values")
    return BaiduBaikeApiPolicy(
        base_url=base_url,
        candidate_limit=candidate_limit,
        require_geo_context_for_alias=require_geo,
        canonical_confidence=float(canonical_confidence),
        alias_confidence=float(alias_confidence),
        fixed_query=normalized_query,
    )


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
TOUTIAO_BAIKE_CANONICAL_RESOLUTION: Final[EncyclopediaCanonicalResolutionPolicy] = (
    _canonical_resolution_policy("toutiao_baike")
)
BAIDU_BAIKE_API_POLICY: Final[BaiduBaikeApiPolicy] = _baidu_api_policy()


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
    if HOMEPAGE_SOURCE_POLICY_REVISION != "encyclopedia-primary":
        issues.append("homepage source policy revision must be encyclopedia-primary")
    if len(SOURCE_PRIORITY) != 3 or len(set(SOURCE_PRIORITY)) != 3:
        issues.append("homepage primary source closed set must contain three unique source kinds")
    try:
        _canonical_resolution_policy("toutiao_baike")
    except ValueError as exc:
        issues.append(str(exc))
    try:
        _baidu_api_policy()
    except ValueError as exc:
        issues.append(str(exc))
    for kind in SOURCE_PRIORITY:
        if not SOURCE_HOSTS.get(kind):
            issues.append(f"{kind}: hosts missing")
        if not SOURCE_URL_PATTERNS.get(kind):
            issues.append(f"{kind}: urlPatterns missing")
        if SOURCE_EXTRACTORS.get(kind) == "generic_html":
            issues.append(f"{kind}: homepage primary must not use generic_html extractor")
    return issues


__all__ = [
    "BAIDU_BAIKE_API_POLICY",
    "BaiduBaikeApiPolicy",
    "ENCYCLOPEDIA_SOURCE_KINDS",
    "EncyclopediaCanonicalResolutionPolicy",
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
    "TOUTIAO_BAIKE_CANONICAL_RESOLUTION",
    "source_contract_issues",
    "source_identity_matches_contract",
    "source_url_matches_contract",
]
