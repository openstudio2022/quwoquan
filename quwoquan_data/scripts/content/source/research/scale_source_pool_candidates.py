"""Deterministic current-wave candidate file assembled from audited projections."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from core.io import read_json
from core.schema import assert_valid, load_schema, validate_strict

from content.source.research.scale_source_pool import (
    SOURCE_POOL_CREATE_ONCE_COLLISION,
    SOURCE_POOL_INVALID,
    ScaleSourcePoolError,
)

CANDIDATES_SCHEMA = "quwoquan_data.scale_source_pool_candidates"
_CARRIERS = ("homepage", "article", "image", "video")


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _fail(issue: str) -> None:
    raise ScaleSourcePoolError(SOURCE_POOL_INVALID, [issue])


def _projection_stable(
    projection: Mapping[str, Any],
    *,
    expected_schema: str,
    label: str,
) -> dict[str, Any]:
    if projection.get("schema") != expected_schema:
        _fail(f"{label} projection schema is invalid")
    stable = {
        key: value for key, value in projection.items() if key != "projectionDigest"
    }
    if projection.get("projectionDigest") != _digest(stable):
        _fail(f"{label} projectionDigest drift")
    return stable


def _identity(document: Mapping[str, Any]) -> tuple[str, str, str]:
    return tuple(
        str(document.get(field) or "")
        for field in ("sourceRevision", "sourceDigest", "entityCatalogDigest")
    )


def _homepage_article_bindings(
    projection: Mapping[str, Any],
) -> list[dict[str, str]]:
    bindings: list[dict[str, str]] = []
    for raw in projection.get("catalogBindings") or []:
        item = dict(raw)
        carrier = str(item.get("carrier") or "")
        bindings.append(
            {
                "kind": f"{carrier}_catalog",
                "ref": str(item.get("catalogRef") or ""),
                "documentDigest": str(item.get("catalogDigest") or ""),
                "fileSha256": str(item.get("catalogFileSha256") or ""),
            }
        )
    return bindings


def _image_video_bindings(
    projection: Mapping[str, Any],
) -> list[dict[str, str]]:
    return [
        {
            "kind": str(item.get("kind") or ""),
            "ref": str(item.get("ref") or ""),
            "documentDigest": str(item.get("documentDigest") or ""),
            "fileSha256": str(item.get("fileSha256") or ""),
        }
        for item in projection.get("inputDocuments") or []
        if isinstance(item, Mapping)
    ]


def _validate_candidates(candidates: Sequence[Mapping[str, Any]]) -> None:
    schema = load_schema("source", "scale_source_pool")
    candidate_schema = schema["$defs"]["candidate"]
    issues: list[str] = []
    for index, candidate in enumerate(candidates):
        issues.extend(
            validate_strict(
                dict(candidate),
                candidate_schema,
                path=f"$.candidates[{index}]",
                _root_schema=schema,
            )
        )
    for label in ("candidateId", "objectRef", "contentSha256"):
        counts = Counter(str(item.get(label) or "") for item in candidates)
        duplicates = sorted(value for value, count in counts.items() if count > 1)
        if duplicates:
            issues.append(f"duplicate cross-carrier {label}: {duplicates}")
    if any(
        candidate.get("entityRef") != candidate.get("observedEntityRef")
        for candidate in candidates
    ):
        issues.append("cross-carrier entity mismatch")
    if issues:
        raise ScaleSourcePoolError(SOURCE_POOL_INVALID, issues)


def build_scale_source_pool_candidates(
    *,
    target_scale: str,
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
    homepage_article_projection: Mapping[str, Any] | None,
    image_video_projection: Mapping[str, Any] | None,
    active_carriers: Sequence[str] = _CARRIERS,
) -> dict[str, Any]:
    """Merge the physical projections required by one carrier-selective wave."""

    active = tuple(str(carrier).strip() for carrier in active_carriers)
    if (
        not active
        or len(active) != len(set(active))
        or any(carrier not in _CARRIERS for carrier in active)
        or active != tuple(carrier for carrier in _CARRIERS if carrier in active)
    ):
        _fail("activeCarriers must be a non-empty canonical carrier subset")
    expected_identity = (source_revision, source_digest, entity_catalog_digest)
    homepage_article: list[Any] = []
    image_video: list[Any] = []
    projection_bindings: list[dict[str, Any]] = []
    if homepage_article_projection is not None:
        _projection_stable(
            homepage_article_projection,
            expected_schema=(
                "quwoquan_data.scale_source_pool_homepage_article_projection"
            ),
            label="homepage/article",
        )
        if _identity(homepage_article_projection) != expected_identity:
            _fail("projection source identity drift")
        raw_rows = homepage_article_projection.get("rows")
        if not isinstance(raw_rows, list):
            _fail("homepage/article projection candidate collection is invalid")
        homepage_article = raw_rows
        projection_bindings.append(
            {
                "kind": "homepage_article",
                "projectionDigest": str(
                    homepage_article_projection["projectionDigest"]
                ),
                "inputBindings": _homepage_article_bindings(
                    homepage_article_projection
                ),
            }
        )
    if image_video_projection is not None:
        _projection_stable(
            image_video_projection,
            expected_schema="quwoquan_data.scale_source_pool_image_video_projection",
            label="image/video",
        )
        if _identity(image_video_projection) != expected_identity:
            _fail("projection source identity drift")
        if image_video_projection.get("targetScale") != target_scale:
            _fail("image/video projection targetScale drift")
        raw_candidates = image_video_projection.get("candidates")
        if not isinstance(raw_candidates, list):
            _fail("image/video projection candidate collection is invalid")
        image_video = raw_candidates
        projection_bindings.append(
            {
                "kind": "image_video",
                "projectionDigest": str(image_video_projection["projectionDigest"]),
                "inputBindings": _image_video_bindings(image_video_projection),
            }
        )
    if not projection_bindings:
        _fail("at least one physical projection is required")
    candidates = [
        dict(item)
        for item in (*homepage_article, *image_video)
        if isinstance(item, Mapping) and str(item.get("carrier") or "") in active
    ]
    if any(not isinstance(item, Mapping) for item in (*homepage_article, *image_video)):
        _fail("projection candidates must be objects")
    candidates.sort(
        key=lambda item: (str(item.get("carrier") or ""), str(item.get("objectRef") or ""))
    )
    _validate_candidates(candidates)
    homepage_article_counts = Counter(
        str(item["carrier"]) for item in homepage_article
    )
    image_video_counts = Counter(str(item["carrier"]) for item in image_video)
    if homepage_article and not set(homepage_article_counts).issubset(
        {"homepage", "article"}
    ):
        _fail("homepage/article projection carrier boundary drift")
    if image_video and not set(image_video_counts).issubset({"image", "video"}):
        _fail("image/video projection carrier boundary drift")
    declared_homepage_article = {
        str(item.get("carrier") or ""): int(item.get("candidateCount") or 0)
        for item in (homepage_article_projection or {}).get("rowCounts") or []
        if isinstance(item, Mapping)
    }
    if homepage_article and declared_homepage_article != dict(
        homepage_article_counts
    ):
        _fail("homepage/article projection rowCounts drift")
    if image_video_projection is not None and int(
        image_video_projection.get("candidateCount") or -1
    ) != len(image_video):
        _fail("image/video projection candidateCount drift")
    counts = Counter(str(item["carrier"]) for item in candidates)
    if any(counts[carrier] < 1 for carrier in active):
        _fail("every active carrier requires at least one physical candidate")
    stable: dict[str, Any] = {
        "schema": CANDIDATES_SCHEMA,
        "targetScale": target_scale,
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
        "activeCarriers": list(active),
        "projectionBindings": projection_bindings,
        "candidateCounts": [
            {"carrier": carrier, "candidateCount": counts[carrier]}
            for carrier in _CARRIERS
        ],
        "candidates": candidates,
    }
    result = {**stable, "candidatesDigest": _digest(stable)}
    validate_scale_source_pool_candidates(result)
    return result


def validate_scale_source_pool_candidates(
    document: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        assert_valid(
            dict(document),
            "source",
            "scale_source_pool_candidates",
            label="scale source-pool candidates",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise ScaleSourcePoolError(SOURCE_POOL_INVALID, [str(exc)]) from exc
    stable = {
        key: value for key, value in document.items() if key != "candidatesDigest"
    }
    if document.get("candidatesDigest") != _digest(stable):
        _fail("candidatesDigest drift")
    candidates = document.get("candidates")
    if not isinstance(candidates, list):
        _fail("candidates must be an array")
    _validate_candidates(candidates)
    expected_identity = _identity(document)
    if any(_identity(candidate) != expected_identity for candidate in candidates):
        _fail("candidate source identity drift")
    counts = Counter(str(item["carrier"]) for item in candidates)
    declared = {
        str(item["carrier"]): int(item["candidateCount"])
        for item in document["candidateCounts"]
    }
    if declared != {carrier: counts[carrier] for carrier in _CARRIERS}:
        _fail("candidateCounts drift")
    active = tuple(str(carrier) for carrier in document["activeCarriers"])
    if active != tuple(carrier for carrier in _CARRIERS if counts[carrier] > 0):
        _fail("activeCarriers drift from physical candidates")
    binding_kinds = [str(item["kind"]) for item in document["projectionBindings"]]
    if len(binding_kinds) != len(set(binding_kinds)):
        _fail("duplicate projection binding kind")
    return dict(document)


def write_create_once_scale_source_pool_candidates(
    destination: Path,
    document: Mapping[str, Any],
) -> dict[str, Any]:
    frozen = validate_scale_source_pool_candidates(document)
    body = json.dumps(
        frozen, ensure_ascii=False, sort_keys=True, indent=2
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
                raise ScaleSourcePoolError(
                    SOURCE_POOL_CREATE_ONCE_COLLISION,
                    [f"existing candidate file is invalid: {destination}"],
                )
            try:
                validate_scale_source_pool_candidates(existing)
            except ScaleSourcePoolError as exc:
                raise ScaleSourcePoolError(
                    SOURCE_POOL_CREATE_ONCE_COLLISION,
                    [f"existing candidate file is invalid: {exc}"],
                ) from exc
            if existing != frozen:
                raise ScaleSourcePoolError(
                    SOURCE_POOL_CREATE_ONCE_COLLISION,
                    [f"source-pool candidate create-once collision: {destination}"],
                )
            return existing
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)
    return frozen


__all__ = [
    "build_scale_source_pool_candidates",
    "validate_scale_source_pool_candidates",
    "write_create_once_scale_source_pool_candidates",
]
