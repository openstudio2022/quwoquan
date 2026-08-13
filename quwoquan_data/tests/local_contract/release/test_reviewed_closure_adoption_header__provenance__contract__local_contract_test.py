# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-003
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-003.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-003.t2
"""A new release keeps one active source and immutable adoption provenance."""

from __future__ import annotations

import copy

import pytest
from content.release.canonical.release_header import (
    ReleaseHeaderError,
    validate_release_header,
)
from core.source_digest import SourceDigest, content_source_revision

_TARGET_DIGEST = "sha256:" + "a" * 64
_CATALOG_DIGEST = "sha256:" + "b" * 64


def _binding(source_release_id: str) -> dict[str, object]:
    return {
        "adoptionId": "reviewed-closure-adoption-header-001",
        "sourceReleaseIdentity": {
            "releaseId": source_release_id,
            "payloadSha256": "sha256:" + "c" * 64,
            "canonicalMerkle": "sha256:" + "d" * 64,
            "attestationFileSha256": "sha256:" + "e" * 64,
        },
        "adoptionRef": {
            "ref": "data/local/reviewed-closure-adoptions/a/adoption_ref.json",
            "fileSha256": "sha256:" + "f" * 64,
            "adoptionRefDigest": "sha256:" + "1" * 64,
        },
        "adoptionReceipt": {
            "ref": "data/local/reviewed-closure-adoptions/a/adoption_receipt.json",
            "fileSha256": "sha256:" + "2" * 64,
            "receiptDigest": "sha256:" + "3" * 64,
        },
    }


def _header(*, release_id: str, release_kind: str = "content") -> dict[str, object]:
    document: dict[str, object] = {
        "schema": "quwoquan_data.release",
        "releaseId": release_id,
        "sourceOwner": "qwq_data",
        "releaseKind": release_kind,
        "releaseClass": "research",
        "productLifecycleState": "research",
        "containsUnverifiedAssets": False,
        "rightsStatusCounts": {
            "verified": 1,
            "unverified": 0,
            "restricted": 0,
            "unknown": 0,
        },
        "authorizationRequiredAssetIds": [],
        "researchAcceptedCount": 1,
        "commercialAcceptedCount": 0,
        "canonicalMerkle": "sha256:" + "4" * 64,
        "executionIds": ["20260805--travel-homepage-adoption--china--pilot-031"],
        "sourceDigests": [SourceDigest(_TARGET_DIGEST).to_document()],
        "sourceRevision": content_source_revision(
            source_digest=_TARGET_DIGEST,
            entity_catalog_digest=_CATALOG_DIGEST,
        ),
        "sourceDigest": _TARGET_DIGEST,
        "entityCatalogDigest": _CATALOG_DIGEST,
        "reviewedClosureAdoption": _binding("identity-collided-source-001"),
    }
    if release_kind == "empty_baseline":
        document["executionIds"] = []
        document.pop("sourceRevision")
        document.pop("sourceDigest")
        document.pop("entityCatalogDigest")
    return document


def test_header_accepts_provenance_without_expanding_active_source_set() -> None:
    document = _header(release_id="new-adopted-release-001")

    validated = validate_release_header(document)

    assert len(validated["sourceDigests"]) == 1
    assert validated["sourceDigest"] == _TARGET_DIGEST
    assert (
        validated["reviewedClosureAdoption"]["sourceReleaseIdentity"]["releaseId"]
        == "identity-collided-source-001"
    )


def test_header_rejects_reuse_of_collided_source_release_id() -> None:
    document = _header(release_id="new-adopted-release-001")
    adoption = copy.deepcopy(document["reviewedClosureAdoption"])
    adoption["sourceReleaseIdentity"]["releaseId"] = document["releaseId"]
    document["reviewedClosureAdoption"] = adoption

    with pytest.raises(ReleaseHeaderError, match="cannot reuse"):
        validate_release_header(document)


def test_empty_baseline_rejects_adoption_provenance() -> None:
    document = _header(
        release_id="new-adopted-baseline-001",
        release_kind="empty_baseline",
    )

    with pytest.raises(ReleaseHeaderError, match="cannot carry adoption provenance"):
        validate_release_header(document)
