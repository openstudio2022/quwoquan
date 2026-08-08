"""Bind one video acquisition item to immutable popular-catalog evidence."""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

POPULAR_COUNT_FIELDS = (
    "playCount", "likeCount", "commentCount", "shareCount", "favoriteCount"
)
POPULAR_BINDING_FIELDS = (
    "popularCandidateId", "popularCatalogRef", "popularCatalogDigest",
    "popularCatalogFileSha256",
)


def _manual_file_sha256(manual_root: Path, ref: object) -> str:
    relative = Path(str(ref or "").strip())
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError("popular-video manualFile must be a safe relative reference")
    path = manual_root.resolve()
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("popular-video manualFile must not traverse a symlink")
    if not path.is_file():
        raise ValueError(f"popular-video manualFile is missing: {relative.as_posix()}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def resolve_popular_candidate_binding(
    item: Mapping[str, Any],
    *,
    catalog_root: Path,
    manual_root: Path | None,
    expected_identity: tuple[str, str, str],
    catalog_cache: dict[tuple[str, str, str], dict[str, Any]],
) -> dict[str, Any] | None:
    """Return the exact catalog candidate after physical bytes verification."""
    from content.source.professional_video_popular_catalog import (
        load_professional_video_popular_candidate_catalog,
    )

    values = tuple(str(item.get(field) or "").strip() for field in POPULAR_BINDING_FIELDS)
    if not any(values):
        return None
    if not all(values):
        raise ValueError(
            f"{item['assetId']}: popular candidate/catalog binding is incomplete"
        )
    candidate_id, catalog_ref, catalog_digest, catalog_sha = values
    cache_key = (catalog_ref, catalog_digest, catalog_sha)
    catalog = catalog_cache.get(cache_key)
    if catalog is None:
        catalog = load_professional_video_popular_candidate_catalog(
            catalog_ref,
            root=catalog_root,
            expected_catalog_digest=catalog_digest,
            expected_file_sha256=catalog_sha,
            expected_identity=expected_identity,
        )
        catalog_cache[cache_key] = catalog
    matches = [
        dict(row) for row in catalog["candidates"]
        if str(row["candidateId"]) == candidate_id
    ]
    if len(matches) != 1:
        raise ValueError(
            f"{item['assetId']}: popular-video candidate binding is missing or ambiguous"
        )
    candidate = matches[0]
    signals = item["popularitySignals"]
    scalar_pairs = (
        ("provider", "provider"), ("entityId", "entityId"),
        ("observedEntityId", "observedEntityId"), ("sourceUrl", "sourcePageUrl"),
        ("title", "title"), ("creator", "creator"),
    )
    if any(
        str(item[left]).strip() != str(candidate[right]).strip()
        for left, right in scalar_pairs
    ):
        raise ValueError(f"{item['assetId']}: popular-video catalog metadata drift")
    expected_signals = {
        **{field: candidate["popularity"][field] for field in POPULAR_COUNT_FIELDS},
        "observedAt": candidate["observedAt"],
        "provider": candidate["provider"],
        "topic": candidate["topic"],
        "timeBucket": candidate["timeBucket"],
    }
    if any(signals.get(field) != value for field, value in expected_signals.items()):
        raise ValueError(f"{item['assetId']}: popular-video observed popularity drift")
    if (
        item["acquisitionPath"] != "manual_file"
        or candidate.get("manualFileProvided") is not True
        or str(item["manualFile"]) != str(candidate.get("manualFileRef") or "")
        or manual_root is None
        or _manual_file_sha256(manual_root, item["manualFile"])
        != candidate.get("manualFileSha256")
    ):
        raise ValueError(f"{item['assetId']}: popular-video manual bytes binding drift")
    return candidate


__all__ = [
    "POPULAR_BINDING_FIELDS",
    "POPULAR_COUNT_FIELDS",
    "resolve_popular_candidate_binding",
]
