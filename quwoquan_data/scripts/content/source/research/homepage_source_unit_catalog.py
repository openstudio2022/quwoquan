"""Immutable source-ready catalogs for entity homepage candidates.

Narrative evidence remains on the governed three-encyclopedia closed set.
Structured facts use their separate field-level official/government evidence
policy. This module only validates already-acquired public evidence and never
performs network I/O or starts a campaign.
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

from core.baike_source_contract import (
    HOMEPAGE_SOURCE_POLICY_REVISION,
    PRIMARY_AUTHORITY_SOURCE_KINDS,
    source_identity_matches_contract,
    source_url_matches_contract,
)
from core.content_source_registry import (
    STRUCTURED_FACTS_FIELDS,
    STRUCTURED_FACTS_SOURCE_CLASSES,
    resolve_source_class,
)
from core.io import read_json
from core.schema import assert_valid


SOURCE_POOL_SHORTFALL = "DATA.SOURCE.POOL_SHORTFALL"
SOURCE_INVALID_EVIDENCE = "DATA.SOURCE.INVALID_EVIDENCE"
SOURCE_CATALOG_CREATE_ONCE_COLLISION = (
    "DATA.SOURCE.CATALOG_CREATE_ONCE_COLLISION"
)
CATALOG_SCHEMA = "quwoquan_data.homepage_source_unit_candidate_catalog"

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_CREATOR_PLACEHOLDERS = frozenset(
    {"unknown", "anonymous", "n/a", "none", "未知", "佚名"}
)
_THUMBNAIL_MARKERS = re.compile(
    r"(?:^|[/_.?=&-])(?:thumb(?:nail)?s?|preview|small|medium|"
    r"236x|474x|564x|736x|75x75|140x140|600x600|r_720x480|"
    r"resize|crop)(?:$|[/_.?=&-])",
    re.IGNORECASE,
)


class HomepageSourceUnitCatalogError(ValueError):
    """Typed source-ready homepage blocker."""

    def __init__(self, code: str, issues: Iterable[object]) -> None:
        normalized = tuple(
            str(issue).strip() for issue in issues if str(issue).strip()
        )
        if not normalized:
            raise ValueError("homepage source-unit catalog error requires an issue")
        self.code = code
        self.issues = normalized
        super().__init__(f"{code}: " + "; ".join(normalized))


def _canonical_digest(document: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(document),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _safe_ref(value: object, *, label: str) -> str:
    text = str(value or "").strip()
    path = Path(text)
    if not text or path.is_absolute() or ".." in path.parts:
        raise HomepageSourceUnitCatalogError(
            SOURCE_INVALID_EVIDENCE,
            [f"{label} must be a non-empty relative reference"],
        )
    return path.as_posix()


def _is_https(value: object) -> bool:
    parsed = urlsplit(str(value or "").strip())
    return parsed.scheme == "https" and bool(parsed.hostname)


def _looks_like_thumbnail(value: object) -> bool:
    return bool(
        _THUMBNAIL_MARKERS.search(unquote(str(value or "")).casefold())
    )


def _identity(document: Mapping[str, Any]) -> tuple[str, str, str]:
    values = tuple(
        str(document.get(field) or "").strip()
        for field in ("sourceRevision", "sourceDigest", "entityCatalogDigest")
    )
    if any(not _SHA256.fullmatch(value) for value in values):
        raise HomepageSourceUnitCatalogError(
            SOURCE_INVALID_EVIDENCE,
            ["sourceRevision/sourceDigest/entityCatalogDigest must be sha256"],
        )
    return values


def _access_issues(
    evidence: object,
    *,
    label: str,
) -> list[str]:
    if not isinstance(evidence, Mapping):
        return [f"{label}: public access evidence is missing"]
    issues: list[str] = []
    if evidence.get("anonymousPublicAccess") is not True:
        issues.append(f"{label}: anonymous public access is not proven")
    for field in (
        "loginRequired",
        "captchaRequired",
        "paywallRequired",
        "drmProtected",
        "accessControlBypass",
    ):
        if evidence.get(field) is not False:
            issues.append(f"{label}: {field} must be false")
    return issues


def _hero_issues(
    hero: Mapping[str, Any],
    *,
    candidate_id: str,
    entity_ref: str,
) -> list[str]:
    label = f"{candidate_id}.hero"
    issues = _access_issues(hero.get("accessEvidence"), label=label)
    if hero.get("entityRef") != entity_ref or hero.get(
        "observedEntityRef"
    ) != entity_ref:
        issues.append(f"{label}: cross-entity media is forbidden")
    original_url = str(hero.get("originalAssetUrl") or "").strip()
    if not _is_https(original_url):
        issues.append(f"{label}: originalAssetUrl must be public HTTPS")
    elif _looks_like_thumbnail(original_url):
        issues.append(f"{label}: thumbnail/transformed URL is forbidden")
    creator = str(hero.get("creator") or "").strip()
    if not creator or creator.casefold() in _CREATOR_PLACEHOLDERS:
        issues.append(f"{label}: non-fiction Creator identity is missing")
    if not _is_https(hero.get("sourcePageUrl")):
        issues.append(f"{label}: sourcePageUrl must be public HTTPS")
    if not _is_https(hero.get("termsUrl")):
        issues.append(f"{label}: termsUrl must be public HTTPS")
    if hero.get("generated") is not False:
        issues.append(f"{label}: generated image is forbidden")
    rights_status = str(hero.get("rightsStatus") or "")
    decision = str(hero.get("distributionDecision") or "")
    if rights_status in {"unverified", "unknown"}:
        if hero.get("authorizationRequired") is not True or decision != "research_allowed":
            issues.append(
                f"{label}: unresolved rights require research_allowed and "
                "authorizationRequired=true"
            )
        if not hero.get("rightsIssues"):
            issues.append(f"{label}: unresolved rightsIssues must be explicit")
    if decision == "commercial_allowed" and (
        rights_status != "verified"
        or not str(hero.get("authorizationProof") or "").strip()
    ):
        issues.append(
            f"{label}: commercial_allowed requires verified rights and proof"
        )
    try:
        _safe_ref(hero.get("assetRef"), label=f"{label}.assetRef")
        _safe_ref(hero.get("sourceUnitRef"), label=f"{label}.sourceUnitRef")
    except HomepageSourceUnitCatalogError as exc:
        issues.extend(exc.issues)
    return issues


def _fact_source_semantic_issues(
    candidate: Mapping[str, Any],
    *,
    candidate_id: str,
) -> list[str]:
    structured = candidate.get("structuredFacts")
    structured = structured if isinstance(structured, Mapping) else {}
    populated_fields = {
        field for field in STRUCTURED_FACTS_FIELDS if field in structured
    }
    issues: list[str] = []
    if not populated_fields:
        issues.append(f"{candidate_id}: at least one structured fact is required")
    raw_sources = structured.get("factSources")
    fact_sources = raw_sources if isinstance(raw_sources, list) else []
    source_keys: set[tuple[str, str, str]] = set()
    source_by_field_id: dict[tuple[str, str], Mapping[str, Any]] = {}
    for index, raw in enumerate(fact_sources):
        source = raw if isinstance(raw, Mapping) else {}
        field = str(source.get("field") or "")
        source_id = str(source.get("sourceId") or "")
        source_url = str(source.get("sourceUrl") or "")
        source_class = str(source.get("sourceClass") or "")
        label = f"{candidate_id}.factSources[{index}]"
        key = (field, source_id, source_url)
        if key in source_keys:
            issues.append(f"{label}: duplicate field/source evidence")
        source_keys.add(key)
        source_by_field_id[(field, source_id)] = source
        if field not in populated_fields:
            issues.append(f"{label}: source refers to an unpopulated fact field")
        if source_class not in STRUCTURED_FACTS_SOURCE_CLASSES:
            issues.append(f"{label}: sourceClass is outside structured-facts policy")
        if source_class == "encyclopedia":
            if source_id not in PRIMARY_AUTHORITY_SOURCE_KINDS or not source_url_matches_contract(
                source_id, source_url
            ):
                issues.append(f"{label}: encyclopedia source identity is invalid")
        elif resolve_source_class(source_id=source_id) != source_class:
            issues.append(f"{label}: sourceId/sourceClass drift from registry")
    for field in sorted(populated_fields):
        if not any(key[0] == field for key in source_keys):
            issues.append(f"{candidate_id}: {field} lacks field-level factSources")

    raw_evidence = candidate.get("factEvidence")
    evidence_rows = raw_evidence if isinstance(raw_evidence, list) else []
    evidence_keys: set[tuple[str, str, str]] = set()
    for index, raw in enumerate(evidence_rows):
        evidence = raw if isinstance(raw, Mapping) else {}
        key = (
            str(evidence.get("field") or ""),
            str(evidence.get("sourceId") or ""),
            str(evidence.get("sourceUrl") or ""),
        )
        label = f"{candidate_id}.factEvidence[{index}]"
        if key in evidence_keys:
            issues.append(f"{label}: duplicate fact evidence")
        evidence_keys.add(key)
        issues.extend(_access_issues(evidence.get("accessEvidence"), label=label))
        try:
            _safe_ref(evidence.get("evidenceRef"), label=f"{label}.evidenceRef")
        except HomepageSourceUnitCatalogError as exc:
            issues.extend(exc.issues)
    missing_evidence = sorted(source_keys - evidence_keys)
    extra_evidence = sorted(evidence_keys - source_keys)
    if missing_evidence:
        issues.append(
            f"{candidate_id}: factSources lack immutable factEvidence: {missing_evidence}"
        )
    if extra_evidence:
        issues.append(
            f"{candidate_id}: factEvidence is not bound to factSources: {extra_evidence}"
        )

    expected_conflicts: set[tuple[str, str, str]] = set()
    for (field, preferred_id), source in source_by_field_id.items():
        for conflicting_id in source.get("conflictsWithSourceIds") or []:
            expected_conflicts.add((field, preferred_id, str(conflicting_id)))
    conflict_rows = candidate.get("factConflicts")
    conflicts = conflict_rows if isinstance(conflict_rows, list) else []
    observed_conflicts: set[tuple[str, str, str]] = set()
    for index, raw in enumerate(conflicts):
        conflict = raw if isinstance(raw, Mapping) else {}
        key = (
            str(conflict.get("field") or ""),
            str(conflict.get("preferredSourceId") or ""),
            str(conflict.get("conflictingSourceId") or ""),
        )
        label = f"{candidate_id}.factConflicts[{index}]"
        if key in observed_conflicts:
            issues.append(f"{label}: duplicate conflict record")
        observed_conflicts.add(key)
        preferred = source_by_field_id.get((key[0], key[1]))
        conflicting = source_by_field_id.get((key[0], key[2]))
        if preferred is None or conflicting is None:
            issues.append(f"{label}: conflict source is absent from factSources")
        elif preferred.get("sourceClass") not in {
            "official_site",
            "government_tourism",
        }:
            issues.append(f"{label}: preferred conflict source must be official")
    if observed_conflicts != expected_conflicts:
        issues.append(
            f"{candidate_id}: conflictsWithSourceIds/factConflicts mismatch"
        )
    return issues


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
    entity_ref = str(candidate.get("entityRef") or "")
    if entity_ref != candidate.get("observedEntityRef"):
        issues.append(f"{candidate_id}: entity mismatch")
    primary = candidate.get("primarySource")
    primary = primary if isinstance(primary, Mapping) else {}
    if not source_identity_matches_contract(
        source_kind=str(primary.get("sourceKind") or ""),
        url=str(primary.get("sourceUrl") or ""),
        extractor=str(primary.get("extractor") or ""),
        policy_revision=str(primary.get("policyRevision") or ""),
    ):
        issues.append(
            f"{candidate_id}: narrative source is outside the governed "
            "three-encyclopedia closed set"
        )
    issues.extend(
        _access_issues(primary.get("accessEvidence"), label=f"{candidate_id}.primarySource")
    )
    try:
        source_unit_ref = _safe_ref(
            primary.get("sourceUnitRef"),
            label=f"{candidate_id}.primarySource.sourceUnitRef",
        )
        body_ref = _safe_ref(
            primary.get("bodyEvidenceRef"),
            label=f"{candidate_id}.primarySource.bodyEvidenceRef",
        )
        if body_ref != f"{source_unit_ref}/source.md":
            issues.append(f"{candidate_id}: body evidence escapes source unit")
    except HomepageSourceUnitCatalogError as exc:
        issues.extend(exc.issues)
    hero = candidate.get("hero")
    hero = hero if isinstance(hero, Mapping) else {}
    issues.extend(_hero_issues(hero, candidate_id=candidate_id, entity_ref=entity_ref))
    issues.extend(_fact_source_semantic_issues(candidate, candidate_id=candidate_id))
    return issues


def validate_homepage_source_unit_catalog(
    catalog: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate one catalog and return its exact source-ready counts."""

    try:
        assert_valid(
            dict(catalog),
            "source",
            "homepage_source_unit_candidate_catalog",
            label="homepage source-unit candidate catalog",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise HomepageSourceUnitCatalogError(
            SOURCE_INVALID_EVIDENCE, [str(exc)]
        ) from exc
    stable = {key: value for key, value in catalog.items() if key != "catalogDigest"}
    if catalog.get("catalogDigest") != _canonical_digest(stable):
        raise HomepageSourceUnitCatalogError(
            SOURCE_INVALID_EVIDENCE, ["catalogDigest mismatch"]
        )
    identity = _identity(catalog)
    candidates = catalog.get("candidates")
    rows = candidates if isinstance(candidates, list) else []
    candidate_ids: set[str] = set()
    entity_refs: set[str] = set()
    issues: list[str] = []
    for raw in rows:
        candidate = raw if isinstance(raw, Mapping) else {}
        candidate_id = str(candidate.get("candidateId") or "")
        entity_ref = str(candidate.get("entityRef") or "")
        if candidate_id in candidate_ids:
            issues.append(f"{candidate_id}: duplicate candidateId")
        candidate_ids.add(candidate_id)
        if entity_ref in entity_refs:
            issues.append(f"{candidate_id}: duplicate entityRef")
        entity_refs.add(entity_ref)
        issues.extend(_candidate_issues(candidate, catalog_identity=identity))
    if issues:
        raise HomepageSourceUnitCatalogError(SOURCE_INVALID_EVIDENCE, issues)
    minimum = int(catalog["minimumCandidateCount"])
    if len(rows) < minimum:
        raise HomepageSourceUnitCatalogError(
            SOURCE_POOL_SHORTFALL,
            [f"homepage source-ready pool shortfall: required={minimum} actual={len(rows)}"],
        )
    return {
        "catalogId": catalog["catalogId"],
        "catalogDigest": catalog["catalogDigest"],
        "candidateCount": len(rows),
        "heroReadyCount": len(rows),
        "structuredFactsReadyCount": len(rows),
        "minimumCandidateCount": minimum,
        "ready": True,
    }


def build_homepage_source_unit_catalog(
    *,
    catalog_id: str,
    created_at: str,
    minimum_candidate_count: int,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
    candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a deterministic catalog from already-acquired evidence."""

    ordered = sorted(
        (dict(candidate) for candidate in candidates),
        key=lambda row: (str(row.get("entityRef")), str(row.get("candidateId"))),
    )
    stable: dict[str, Any] = {
        "schema": CATALOG_SCHEMA,
        "catalogId": str(catalog_id).strip(),
        "policyRevision": HOMEPAGE_SOURCE_POLICY_REVISION,
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
        "createdAt": created_at,
        "minimumCandidateCount": minimum_candidate_count,
        "candidates": ordered,
    }
    catalog = {**stable, "catalogDigest": _canonical_digest(stable)}
    validate_homepage_source_unit_catalog(catalog)
    return catalog


def write_create_once_homepage_source_unit_catalog(
    destination: Path,
    catalog: Mapping[str, Any],
) -> dict[str, Any]:
    """Persist one catalog without permitting identity or byte replacement."""

    validate_homepage_source_unit_catalog(catalog)
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
                raise HomepageSourceUnitCatalogError(
                    SOURCE_CATALOG_CREATE_ONCE_COLLISION,
                    [f"existing catalog is not an object: {destination}"],
                )
            try:
                validate_homepage_source_unit_catalog(existing)
            except HomepageSourceUnitCatalogError as exc:
                raise HomepageSourceUnitCatalogError(
                    SOURCE_CATALOG_CREATE_ONCE_COLLISION,
                    [f"existing catalog is invalid: {exc}"],
                ) from exc
            if existing != dict(catalog):
                raise HomepageSourceUnitCatalogError(
                    SOURCE_CATALOG_CREATE_ONCE_COLLISION,
                    [f"homepage source-unit catalog create-once collision: {destination}"],
                )
            return existing
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)
    return dict(catalog)


__all__ = [
    "CATALOG_SCHEMA",
    "HomepageSourceUnitCatalogError",
    "SOURCE_CATALOG_CREATE_ONCE_COLLISION",
    "SOURCE_INVALID_EVIDENCE",
    "SOURCE_POOL_SHORTFALL",
    "build_homepage_source_unit_catalog",
    "validate_homepage_source_unit_catalog",
    "write_create_once_homepage_source_unit_catalog",
]
