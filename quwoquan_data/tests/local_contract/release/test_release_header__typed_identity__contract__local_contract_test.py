# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/spec.md
"""Public release consumers enforce cross-field identity beyond schema shape."""
from __future__ import annotations

from pathlib import Path

import pytest
from content.release.canonical.release_header import (
    ReleaseHeaderError,
    validate_release_header,
)
from content.release.environment.release_runtime import load_release
from core.io import write_json
from core.release_layout import payload_file
from core.source_digest import content_source_revision, current_source_digest

_ENTITY_CATALOG_DIGEST = "sha256:" + "1" * 64


def _header(*, release_id: str, release_kind: str = "content") -> dict[str, object]:
    source = current_source_digest()
    document: dict[str, object] = {
        "schema": "quwoquan_data.release",
        "releaseId": release_id,
        "sourceOwner": "qwq_data",
        "releaseKind": release_kind,
        "releaseClass": "research",
        "productLifecycleState": "research",
        "containsUnverifiedAssets": False,
        "rightsStatusCounts": {
            "verified": 0,
            "unverified": 0,
            "restricted": 0,
            "unknown": 0,
        },
        "authorizationRequiredAssetIds": [],
        "researchAcceptedCount": 0,
        "commercialAcceptedCount": 0,
        "canonicalMerkle": "sha256:" + "2" * 64,
        "executionIds": ["20260805--travel-article--china--scale-001"],
        "sourceDigests": [source.to_document()],
    }
    if release_kind == "content":
        document.update(
            {
                "sourceDigest": source.digest,
                "entityCatalogDigest": _ENTITY_CATALOG_DIGEST,
                "sourceRevision": content_source_revision(
                    source_digest=source.digest,
                    entity_catalog_digest=_ENTITY_CATALOG_DIGEST,
                ),
            }
        )
    else:
        document["executionIds"] = []
    return document


def test_typed_header_rejects_baseline_with_content_source_identity() -> None:
    document = _header(release_id="baseline-typed-001", release_kind="empty_baseline")
    document.update(
        {
            "sourceDigest": "sha256:" + "3" * 64,
            "entityCatalogDigest": _ENTITY_CATALOG_DIGEST,
            "sourceRevision": "sha256:" + "4" * 64,
        }
    )

    with pytest.raises(ReleaseHeaderError, match="must not carry content source identity"):
        validate_release_header(document)


def test_typed_header_rejects_mismatched_content_source_revision() -> None:
    document = _header(release_id="content-typed-001")
    document["sourceRevision"] = "sha256:" + "4" * 64

    with pytest.raises(ReleaseHeaderError, match="sourceRevision does not match"):
        validate_release_header(document)


def test_typed_header_accepts_one_derived_content_identity() -> None:
    document = _header(release_id="content-typed-002")

    assert validate_release_header(document) == document


def test_ship_loader_uses_typed_header_boundary(tmp_path: Path) -> None:
    release_id = "content-typed-003"
    release = tmp_path / release_id
    write_json(
        payload_file(release, "desired_state.json"),
        {
            "schema": "quwoquan_data.release_desired_state",
            "releaseId": release_id,
            "desiredRefs": {
                "creators": [],
                "entities": [],
                "posts": [],
                "tags": [],
            },
        },
    )
    invalid = _header(release_id=release_id)
    invalid["sourceRevision"] = "sha256:" + "4" * 64
    write_json(payload_file(release, "release.json"), invalid)

    with pytest.raises(SystemExit, match="immutable release contract invalid"):
        load_release(tmp_path, release_id)
