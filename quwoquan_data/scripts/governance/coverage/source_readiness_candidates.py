"""Candidate normalization and encyclopedia resolvers for source readiness."""
from __future__ import annotations

import json
import re
import unicodedata
import urllib.parse
from pathlib import Path
from typing import Any

from content.source.research import network_io
from content.source.research.baidu_baike import resolve_baidu_baike_page
from content.source.research.baike_com import resolve_toutiao_baike_page
from content.source.research.text_match import (
    _geo_context_matches,
    _wiki_resolved_title_matches_entity,
)
from governance.coverage.coverage_merge import (
    _candidate_locations,
    _type_evidence,
    normalize_name,
)
from governance.coverage.coverage_runtime import now_iso
from governance.coverage.admin_entity_catalog import (
    ADMIN_ENTITY_TYPE,
    ADMIN_ENTITY_TYPE_TAG_REF,
    admin_entity_candidates,
)
from governance.coverage.master_list import (
    iter_master_leaves,
    load_master_list_file,
    master_list_files,
)


SOURCE_INVALID_TARGET = "DATA.SOURCE.INVALID_TARGET"
_ENTITY_REF_RE = re.compile(
    r"^/entity/([^/\s]+)/([^/\s]+)/(\S(?:[^/]*\S)?)$"
)


class SourceReadinessTargetError(ValueError):
    """Typed fail-closed error for exact canonical source-ready targets."""

    code = SOURCE_INVALID_TARGET

    def __init__(self, issues: list[str] | tuple[str, ...]) -> None:
        normalized = tuple(str(issue).strip() for issue in issues if str(issue).strip())
        if not normalized:
            raise ValueError("source-readiness target error requires an issue")
        self.issues = normalized
        super().__init__(f"{self.code}: " + "; ".join(normalized))


def _normalize_required_entity_refs(
    required_entity_refs: list[str] | tuple[str, ...],
) -> tuple[str, ...]:
    normalized: list[str] = []
    malformed: list[str] = []
    for raw in required_entity_refs:
        value = unicodedata.normalize("NFKC", str(raw)).strip()
        if not _ENTITY_REF_RE.fullmatch(value):
            malformed.append(repr(str(raw)))
            continue
        normalized.append(value)
    if malformed:
        raise SourceReadinessTargetError(
            [f"malformed required entity refs: {malformed}"]
        )
    duplicates = sorted(
        {ref for ref in normalized if normalized.count(ref) > 1}
    )
    if duplicates:
        raise SourceReadinessTargetError(
            [f"duplicate required entity refs: {duplicates}"]
        )
    return tuple(normalized)


def canonical_source_ready_name(candidate: dict[str, Any]) -> str:
    """Return the normalized canonical candidate name used by entity refs."""

    name = unicodedata.normalize(
        "NFKC",
        str(candidate.get("canonicalName") or candidate.get("name") or ""),
    ).strip()
    if not name or "/" in name:
        raise ValueError("source-ready canonical name is empty or contains '/'")
    return name


def canonical_source_ready_entity_ref(
    candidate: dict[str, Any],
    *,
    entity_type: str | None = None,
) -> str:
    """Derive one canonical entity ref from governed name and type evidence."""

    resolved_type = entity_type
    if resolved_type is None:
        classified = _source_ready_type_evidence(candidate)
        if classified is None:
            raise ValueError("source-ready candidate has no governed type evidence")
        resolved_type = classified[0]
    normalized_type = unicodedata.normalize("NFKC", str(resolved_type)).strip()
    parts = normalized_type.split("/")
    if len(parts) != 2 or any(not part or any(ch.isspace() for ch in part) for part in parts):
        raise ValueError("source-ready entity type must contain two non-empty segments")
    return f"/entity/{parts[0]}/{parts[1]}/{canonical_source_ready_name(candidate)}"


def resolve_required_master_candidates(
    required_entity_refs: list[str] | tuple[str, ...],
    *,
    provinces: list[str],
) -> tuple[tuple[str, ...], list[dict[str, Any]]]:
    """Resolve ordered exact refs from the canonical nationwide master view.

    The full scan is repository-local and performs no provider I/O.  It is used
    to distinguish a missing ref from a real ref outside the requested province
    set and to reject globally ambiguous canonical refs before a run directory
    can be created.
    """

    normalized_refs = _normalize_required_entity_refs(required_entity_refs)
    if not normalized_refs:
        return (), []
    wanted_refs = set(normalized_refs)
    matches: dict[str, list[dict[str, Any]]] = {
        ref: [] for ref in normalized_refs
    }
    for candidate in _master_candidates([]):
        classified = _source_ready_type_evidence(candidate)
        if classified is None:
            continue
        try:
            entity_ref = canonical_source_ready_entity_ref(
                candidate,
                entity_type=classified[0],
            )
        except ValueError:
            continue
        if entity_ref not in wanted_refs:
            continue
        matches[entity_ref].append(
            {
                **candidate,
                "canonicalName": canonical_source_ready_name(candidate),
                "entityType": classified[0],
                "canonicalEntityRef": entity_ref,
                "typeTagRefs": classified[1],
            }
        )

    selected_provinces = set(provinces)
    issues: list[str] = []
    resolved: list[dict[str, Any]] = []
    for entity_ref in normalized_refs:
        candidates = matches[entity_ref]
        if not candidates:
            issues.append(f"missing canonical master ref: {entity_ref}")
            continue
        if len(candidates) > 1:
            locations = sorted(
                {
                    "/".join(
                        str(candidate.get(field) or "")
                        for field in ("province", "city", "district")
                    )
                    for candidate in candidates
                }
            )
            issues.append(
                f"ambiguous canonical master ref: {entity_ref} -> {locations}"
            )
            continue
        candidate = candidates[0]
        province = str(candidate.get("province") or "")
        if province not in selected_provinces:
            issues.append(
                f"canonical master ref is outside selected provinces: "
                f"{entity_ref} -> {province}"
            )
            continue
        resolved.append(candidate)
    if issues:
        raise SourceReadinessTargetError(issues)
    return normalized_refs, resolved


def _read_candidates(paths: list[Path]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    candidate = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"候选 NDJSON 无效: {path}:{line_number}"
                    ) from exc
                if not isinstance(candidate, dict):
                    raise ValueError(f"候选必须是 object: {path}:{line_number}")
                candidates.append(candidate)
    return candidates


def _master_candidates(provinces: list[str]) -> list[dict[str, Any]]:
    # 全国行政实体与川浙等旅游 POI 共享候选入口，但保持不同 source/canonical
    # identity；行政实体直接消费 pca + taxonomy，不写入 POI master-list YAML。
    candidates: list[dict[str, Any]] = admin_entity_candidates(provinces=provinces)
    for path in master_list_files(provinces=provinces):
        data = load_master_list_file(path)
        province = str(data.get("province") or path.parent.name)
        city = str(data.get("city") or path.stem)
        for district, leaf in iter_master_leaves(data):
            candidates.append(
                {
                    "name": str(
                        leaf.get("name") or leaf.get("canonicalName") or ""
                    ),
                    "canonicalName": str(
                        leaf.get("canonicalName") or leaf.get("name") or ""
                    ),
                    "province": province,
                    "city": city,
                    "district": district,
                    "source": "master_list",
                    "identityRefs": dict(leaf.get("identityRefs") or {}),
                    "coordinates": dict(leaf.get("coordinates") or {}),
                    "typeTagRefs": list(leaf.get("typeTagRefs") or []),
                }
            )
    return candidates


def _readiness_key(candidate: dict[str, Any]) -> str:
    canonical_identity = str(candidate.get("canonicalIdentity") or "").strip()
    if canonical_identity:
        return canonical_identity
    name = normalize_name(
        str(candidate.get("canonicalName") or candidate.get("name") or "")
    )
    location = "|".join(
        str(candidate.get(field) or "").strip()
        for field in ("province", "city", "district")
    )
    if not name or not all(location.split("|")):
        return ""
    return f"name_location:{name}|{location}"


def _candidate_score(candidate: dict[str, Any]) -> tuple[int, int, int]:
    identity = candidate.get("identityRefs")
    coordinates = candidate.get("coordinates")
    return (
        int(isinstance(identity, dict) and any(identity.values())),
        int(isinstance(coordinates, dict) and bool(coordinates)),
        len(candidate.get("typeTagRefs") or []),
    )


def _source_ready_type_evidence(
    candidate: dict[str, Any],
) -> tuple[str, list[str]] | None:
    if candidate.get("candidateKind") == "admin_region":
        entity_type = str(candidate.get("entityType") or "").strip()
        type_refs = [
            str(ref).strip()
            for ref in candidate.get("typeTagRefs") or []
            if str(ref).strip()
        ]
        if (
            entity_type == ADMIN_ENTITY_TYPE
            and ADMIN_ENTITY_TYPE_TAG_REF in type_refs
        ):
            return entity_type, type_refs
        return None
    return _type_evidence(
        [candidate],
        str(candidate.get("name") or ""),
    )


def _dedupe_candidates(
    candidates: list[dict[str, Any]],
    *,
    provinces: list[str],
) -> list[dict[str, Any]]:
    wanted = set(provinces)
    selected: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        if str(candidate.get("province") or "") not in wanted:
            continue
        expanded = [candidate]
        if not candidate.get("city") or not candidate.get("district"):
            expanded = [
                {
                    **candidate,
                    "province": province,
                    "city": city,
                    "district": district,
                    "geoTagRef": geo_ref,
                }
                for province, city, district, geo_ref in _candidate_locations(
                    [candidate],
                    country="中国",
                )
                if province in wanted
            ]
        for item in expanded:
            classified = _source_ready_type_evidence(item)
            if classified is None:
                continue
            item = {
                **item,
                "typeTagRefs": classified[1],
            }
            key = _readiness_key(item)
            if not key:
                continue
            current = selected.get(key)
            if current is None or _candidate_score(item) > _candidate_score(current):
                selected[key] = item
    return sorted(
        selected.values(),
        key=lambda item: (
            str(item.get("province") or ""),
            str(item.get("city") or ""),
            str(item.get("district") or ""),
            str(item.get("name") or ""),
        ),
    )


def _geo_terms(candidate: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(candidate.get(field) or "").strip()
        for field in ("province", "city", "district")
        if str(candidate.get(field) or "").strip()
    )


def _wikipedia_evidence(candidate: dict[str, Any]) -> dict[str, Any] | None:
    name = str(candidate.get("name") or "").strip()
    if not name:
        return None
    existing_extract = str(candidate.get("extract") or "").strip()
    if (
        candidate.get("source") == "wiki_category"
        and existing_extract
        and _geo_context_matches(
            " ".join((name, existing_extract)),
            _geo_terms(candidate),
        )
    ):
        return {
            "sourceKind": "wikipedia",
            "extractor": "wikipedia_api",
            "canonicalUrl": (
                "https://zh.wikipedia.org/wiki/"
                + urllib.parse.quote(name.replace(" ", "_"))
            ),
            "resolvedTitle": name,
            "matchConfidence": 1.0,
        }
    response = network_io.wiki_api(
        "zh.wikipedia.org",
        {
            "action": "query",
            "titles": name,
            "prop": "extracts",
            "explaintext": "1",
            "redirects": "1",
            "format": "json",
        },
    )
    for page in ((response.get("query") or {}).get("pages") or {}).values():
        if not isinstance(page, dict) or int(page.get("pageid") or -1) <= 0:
            continue
        title = str(page.get("title") or "").strip()
        extract = str(page.get("extract") or "").strip()
        if (
            not extract
            or not _wiki_resolved_title_matches_entity(title, name)
            or not _geo_context_matches(
                " ".join((name, title, extract)),
                _geo_terms(candidate),
            )
        ):
            continue
        return {
            "sourceKind": "wikipedia",
            "extractor": "wikipedia_api",
            "canonicalUrl": (
                "https://zh.wikipedia.org/wiki/"
                + urllib.parse.quote(title.replace(" ", "_"))
            ),
            "resolvedTitle": title,
            "matchConfidence": 0.95,
        }
    return None


def _baike_evidence(
    candidate: dict[str, Any],
    *,
    source: str,
) -> dict[str, Any] | None:
    name = str(candidate.get("name") or "").strip()
    terms = _geo_terms(candidate)
    resolution = (
        resolve_baidu_baike_page(name, geo_context_terms=terms)
        if source == "baidu_baike"
        else resolve_toutiao_baike_page(name, geo_context_terms=terms)
    )
    if resolution is None:
        return None
    return {
        "sourceKind": source,
        "extractor": (
            "baidu_baike_html"
            if source == "baidu_baike"
            else "toutiao_baike_html"
        ),
        "canonicalUrl": resolution.url,
        "resolvedTitle": resolution.title,
        "matchConfidence": resolution.match_confidence,
    }


def _qualify_candidate(
    candidate: dict[str, Any],
    *,
    sources: tuple[str, ...],
) -> dict[str, Any]:
    evidence: dict[str, Any] | None = None
    attempts: list[str] = []
    for source in sources:
        attempts.append(source)
        evidence = (
            _wikipedia_evidence(candidate)
            if source == "wikipedia"
            else _baike_evidence(candidate, source=source)
        )
        if evidence is not None:
            break
    return {
        "schema": "quwoquan_data.source_ready_candidate",
        "identityKey": _readiness_key(candidate),
        "candidate": candidate,
        "attemptedSources": attempts,
        "qualified": evidence is not None,
        **({"evidence": evidence} if evidence is not None else {}),
        "qualifiedAt": now_iso(),
    }


__all__ = [
    "_dedupe_candidates",
    "_master_candidates",
    "_qualify_candidate",
    "_read_candidates",
    "_readiness_key",
    "_source_ready_type_evidence",
    "_wikipedia_evidence",
]
