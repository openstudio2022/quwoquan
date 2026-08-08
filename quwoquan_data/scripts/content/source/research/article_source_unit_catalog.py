"""Immutable illustrated-article source-unit candidate catalogs.

This module is deliberately offline. It freezes body and media evidence that
has already been acquired from an article source profile admitted by the
version-controlled content source registry. It does not crawl, download,
author content, or start a campaign.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from core.io import read_json
from core.schema import assert_valid

from content.source.research.article_frontier_profile import (
    resolve_article_source_binding,
)

SOURCE_POOL_SHORTFALL = "DATA.SOURCE.POOL_SHORTFALL"
SOURCE_INVALID_EVIDENCE = "DATA.SOURCE.INVALID_EVIDENCE"
SOURCE_CATALOG_CREATE_ONCE_COLLISION = (
    "DATA.SOURCE.CATALOG_CREATE_ONCE_COLLISION"
)
CATALOG_SCHEMA = "quwoquan_data.article_source_unit_candidate_catalog"
ARTICLE_SOURCE_POLICY_REVISION = "article-source-registry-v1"

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_SOURCE_UNIT_REF = re.compile(r"^sources/([^/]+)$")
_CREATOR_PLACEHOLDERS = frozenset(
    {"unknown", "anonymous", "n/a", "none", "未知", "佚名"}
)
_THUMBNAIL_MARKERS = re.compile(
    r"(?:^|[/_.?=&-])(?:thumb(?:nail)?s?|preview|small|medium|"
    r"236x|474x|564x|736x|75x75|140x140|600x600|r_720x480|"
    r"resize|crop)(?:$|[/_.?=&-])",
    re.IGNORECASE,
)


class ArticleSourceUnitCatalogError(ValueError):
    """Typed source-ready article blocker."""

    def __init__(self, code: str, issues: Iterable[object]) -> None:
        normalized = tuple(
            str(issue).strip() for issue in issues if str(issue).strip()
        )
        if not normalized:
            raise ValueError("article source-unit catalog error requires an issue")
        self.code = code
        self.issues = normalized
        super().__init__(f"{code}: " + "; ".join(normalized))


def _canonical_digest(document: Mapping[str, Any]) -> str:
    payload = json.dumps(
        dict(document),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _safe_ref(value: object, *, label: str) -> str:
    text = str(value or "").strip()
    path = Path(text)
    if not text or path.is_absolute() or ".." in path.parts:
        raise ArticleSourceUnitCatalogError(
            SOURCE_INVALID_EVIDENCE,
            [f"{label} must be a non-empty relative reference"],
        )
    return path.as_posix()


def _is_https(value: object) -> bool:
    parsed = urlsplit(str(value or "").strip())
    return parsed.scheme == "https" and bool(parsed.hostname)


def _looks_like_thumbnail(value: object) -> bool:
    normalized = unquote(str(value or "").strip()).casefold()
    return bool(_THUMBNAIL_MARKERS.search(normalized))


def _identity(document: Mapping[str, Any]) -> tuple[str, str, str]:
    values = tuple(
        str(document.get(field) or "").strip()
        for field in ("sourceRevision", "sourceDigest", "entityCatalogDigest")
    )
    if any(not _SHA256.fullmatch(value) for value in values):
        raise ArticleSourceUnitCatalogError(
            SOURCE_INVALID_EVIDENCE,
            ["sourceRevision/sourceDigest/entityCatalogDigest must be sha256"],
        )
    return values


def _candidate_issues(
    candidate: Mapping[str, Any],
    *,
    catalog_identity: tuple[str, str, str],
) -> list[str]:
    candidate_id = str(candidate.get("candidateId") or "<missing-candidate>")
    issues: list[str] = []
    candidate_identity = tuple(
        str(candidate.get(field) or "").strip()
        for field in ("sourceRevision", "sourceDigest", "entityCatalogDigest")
    )
    if candidate_identity != catalog_identity:
        issues.append(f"{candidate_id}: source identity drift")

    source_unit_id = str(candidate.get("sourceUnitId") or "").strip()
    source_unit_ref = str(candidate.get("sourceUnitRef") or "").strip()
    match = _SOURCE_UNIT_REF.fullmatch(source_unit_ref)
    if match is None or match.group(1) != source_unit_id:
        issues.append(f"{candidate_id}: sourceUnitId/sourceUnitRef mismatch")
    try:
        body_ref = _safe_ref(
            candidate.get("bodyEvidenceRef"),
            label=f"{candidate_id}.bodyEvidenceRef",
        )
    except ArticleSourceUnitCatalogError as exc:
        issues.extend(exc.issues)
        body_ref = ""
    if source_unit_ref and body_ref != f"{source_unit_ref}/source.md":
        issues.append(f"{candidate_id}: body evidence escapes source unit")

    source_url = str(candidate.get("sourceUrl") or "").strip()
    try:
        site = resolve_article_source_binding(
            source_url,
            site_id=str(candidate.get("articleSiteId") or ""),
            profile_digest=str(
                candidate.get("sourceDiscoveryProfileDigest") or ""
            ),
        )
    except ValueError as exc:
        issues.append(f"{candidate_id}: {exc}")
        site = None
    if site is not None:
        expected = {
            "sourceKind": str(site.get("category") or "").strip(),
            "platform": str(site.get("platform") or "").strip(),
            "extractor": str(site.get("extractor") or "").strip(),
        }
        profile = site.get("siteCrawlProfile")
        if isinstance(profile, Mapping) and str(
            profile.get("extractor") or ""
        ).strip():
            expected["extractor"] = str(profile["extractor"]).strip()
        for field, expected_value in expected.items():
            if str(candidate.get(field) or "").strip() != expected_value:
                issues.append(
                    f"{candidate_id}: {field} differs from admitted article "
                    f"site profile"
                )
    if candidate.get("policyRevision") != ARTICLE_SOURCE_POLICY_REVISION:
        issues.append(f"{candidate_id}: article source policy revision drift")

    access = candidate.get("accessEvidence")
    if not isinstance(access, Mapping):
        issues.append(f"{candidate_id}: public access evidence is missing")
    else:
        if access.get("anonymousPublicAccess") is not True:
            issues.append(f"{candidate_id}: anonymous public access is not proven")
        for field in (
            "loginRequired",
            "captchaRequired",
            "paywallRequired",
            "drmProtected",
            "accessControlBypass",
        ):
            if access.get(field) is not False:
                issues.append(f"{candidate_id}: {field} must be false")

    if candidate.get("entityRef") != candidate.get("observedEntityRef"):
        issues.append(f"{candidate_id}: entity mismatch")

    assets = candidate.get("assets")
    rows = assets if isinstance(assets, list) else []
    cover_count = 0
    body_count = 0
    asset_ids: set[str] = set()
    content_digests: set[str] = set()
    original_urls: set[str] = set()
    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            issues.append(f"{candidate_id}.assets[{index}]: must be an object")
            continue
        asset_id = str(raw.get("assetId") or "").strip()
        label = f"{candidate_id}.{asset_id or f'asset-{index}'}"
        if asset_id in asset_ids:
            issues.append(f"{label}: duplicate assetId")
        asset_ids.add(asset_id)
        role = str(raw.get("role") or "")
        cover_count += int(role == "cover")
        body_count += int(role == "body")
        if raw.get("sourceUnitId") != source_unit_id or raw.get(
            "sourceUnitRef"
        ) != source_unit_ref:
            issues.append(f"{label}: cross-sourceUnit media is forbidden")
        if not _is_https(raw.get("sourcePageUrl")):
            issues.append(f"{label}: sourcePageUrl must be public HTTPS")

        original_url = str(raw.get("originalAssetUrl") or "").strip()
        if not _is_https(original_url):
            issues.append(f"{label}: originalAssetUrl must be public HTTPS")
        elif _looks_like_thumbnail(original_url):
            issues.append(f"{label}: thumbnail/transformed URL is forbidden")
        if original_url in original_urls:
            issues.append(f"{label}: duplicate originalAssetUrl")
        original_urls.add(original_url)

        creator = str(raw.get("creator") or "").strip()
        if not creator or creator.casefold() in _CREATOR_PLACEHOLDERS:
            issues.append(f"{label}: non-fiction Creator identity is missing")
        if not _is_https(raw.get("termsUrl")):
            issues.append(f"{label}: termsUrl must be public HTTPS")
        if raw.get("generated") is not False:
            issues.append(f"{label}: generated image is forbidden")

        digest = str(raw.get("contentSha256") or "")
        if digest in content_digests:
            issues.append(f"{label}: duplicate contentSha256")
        content_digests.add(digest)
        try:
            asset_ref = _safe_ref(raw.get("assetRef"), label=f"{label}.assetRef")
        except ArticleSourceUnitCatalogError as exc:
            issues.extend(exc.issues)
            asset_ref = ""
        if source_unit_ref and not asset_ref.startswith(f"{source_unit_ref}/assets/"):
            issues.append(f"{label}: assetRef escapes source unit")

        rights_status = str(raw.get("rightsStatus") or "")
        decision = str(raw.get("distributionDecision") or "")
        authorization_required = raw.get("authorizationRequired")
        rights_issues = raw.get("rightsIssues")
        if rights_status in {"unverified", "unknown"}:
            if authorization_required is not True or decision != "research_allowed":
                issues.append(
                    f"{label}: unverified/unknown rights require research_allowed "
                    "and authorizationRequired=true"
                )
            if not isinstance(rights_issues, list) or not rights_issues:
                issues.append(f"{label}: unresolved rightsIssues must be explicit")
        if decision == "commercial_allowed" and (
            rights_status != "verified"
            or not str(raw.get("authorizationProof") or "").strip()
        ):
            issues.append(
                f"{label}: commercial_allowed requires verified rights and proof"
            )

    if cover_count != 1:
        issues.append(f"{candidate_id}: exactly one cover image is required")
    if body_count < 1:
        issues.append(f"{candidate_id}: at least one body image is required")
    return issues


def validate_article_source_unit_catalog(
    catalog: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate one catalog and return deterministic readiness evidence."""

    try:
        assert_valid(
            dict(catalog),
            "source",
            "article_source_unit_candidate_catalog",
            label="article source-unit candidate catalog",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise ArticleSourceUnitCatalogError(
            SOURCE_INVALID_EVIDENCE, [str(exc)]
        ) from exc
    stable = {key: value for key, value in catalog.items() if key != "catalogDigest"}
    if catalog.get("catalogDigest") != _canonical_digest(stable):
        raise ArticleSourceUnitCatalogError(
            SOURCE_INVALID_EVIDENCE, ["catalogDigest mismatch"]
        )
    identity = _identity(catalog)
    candidates = catalog.get("candidates")
    rows = candidates if isinstance(candidates, list) else []
    issues: list[str] = []
    candidate_ids: set[str] = set()
    source_unit_ids: set[str] = set()
    for raw in rows:
        candidate = raw if isinstance(raw, Mapping) else {}
        candidate_id = str(candidate.get("candidateId") or "").strip()
        source_unit_id = str(candidate.get("sourceUnitId") or "").strip()
        if candidate_id in candidate_ids:
            issues.append(f"{candidate_id}: duplicate candidateId")
        candidate_ids.add(candidate_id)
        if source_unit_id in source_unit_ids:
            issues.append(f"{candidate_id}: duplicate sourceUnitId")
        source_unit_ids.add(source_unit_id)
        issues.extend(_candidate_issues(candidate, catalog_identity=identity))
    if issues:
        raise ArticleSourceUnitCatalogError(SOURCE_INVALID_EVIDENCE, issues)

    minimum = int(catalog["minimumCandidateCount"])
    if len(rows) < minimum:
        raise ArticleSourceUnitCatalogError(
            SOURCE_POOL_SHORTFALL,
            [f"article source-ready pool shortfall: required={minimum} actual={len(rows)}"],
        )
    return {
        "catalogId": catalog["catalogId"],
        "catalogVersion": catalog["catalogVersion"],
        "catalogDigest": catalog["catalogDigest"],
        "candidateCount": len(rows),
        "illustratedCandidateCount": len(rows),
        "closedSourceUnitCount": len(source_unit_ids),
        "minimumCandidateCount": minimum,
        "ready": True,
    }


def build_article_source_unit_catalog(
    *,
    catalog_id: str,
    catalog_version: str,
    created_at: str,
    minimum_candidate_count: int,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
    candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a stable catalog after all public evidence has been acquired."""

    ordered = sorted(
        (dict(candidate) for candidate in candidates),
        key=lambda row: (str(row.get("sourceUnitId")), str(row.get("candidateId"))),
    )
    stable: dict[str, Any] = {
        "schema": CATALOG_SCHEMA,
        "catalogId": str(catalog_id).strip(),
        "catalogVersion": str(catalog_version).strip(),
        "policyRevision": ARTICLE_SOURCE_POLICY_REVISION,
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
        "createdAt": created_at,
        "minimumCandidateCount": minimum_candidate_count,
        "candidates": ordered,
    }
    catalog = {**stable, "catalogDigest": _canonical_digest(stable)}
    validate_article_source_unit_catalog(catalog)
    return catalog


def write_create_once_article_source_unit_catalog(
    destination: Path,
    catalog: Mapping[str, Any],
) -> dict[str, Any]:
    """Create one immutable catalog, permitting only byte-equivalent replay."""

    validate_article_source_unit_catalog(catalog)
    body = json.dumps(
        dict(catalog), ensure_ascii=False, sort_keys=True, indent=2
    ).encode("utf-8") + b"\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = ""
    try:
        with tempfile.NamedTemporaryFile(
            "wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError:
            existing = read_json(destination)
            if not isinstance(existing, dict):
                raise ArticleSourceUnitCatalogError(
                    SOURCE_CATALOG_CREATE_ONCE_COLLISION,
                    [f"existing catalog is not an object: {destination}"],
                )
            try:
                validate_article_source_unit_catalog(existing)
            except ArticleSourceUnitCatalogError as exc:
                raise ArticleSourceUnitCatalogError(
                    SOURCE_CATALOG_CREATE_ONCE_COLLISION,
                    [f"existing catalog is invalid: {exc}"],
                ) from exc
            if existing != dict(catalog):
                raise ArticleSourceUnitCatalogError(
                    SOURCE_CATALOG_CREATE_ONCE_COLLISION,
                    [f"article source-unit catalog create-once collision: {destination}"],
                )
            return existing
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)
    return dict(catalog)


__all__ = [
    "ARTICLE_SOURCE_POLICY_REVISION",
    "CATALOG_SCHEMA",
    "SOURCE_CATALOG_CREATE_ONCE_COLLISION",
    "SOURCE_INVALID_EVIDENCE",
    "SOURCE_POOL_SHORTFALL",
    "ArticleSourceUnitCatalogError",
    "build_article_source_unit_catalog",
    "validate_article_source_unit_catalog",
    "write_create_once_article_source_unit_catalog",
]
