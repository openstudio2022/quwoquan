# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/spec.md
"""Public release consumers enforce cross-field identity beyond schema shape."""
from __future__ import annotations

from pathlib import Path

import pytest
from content.release.canonical.object_source_identity import (
    source_identity_digest,
    source_identity_set,
)
from content.release.canonical.release_header import (
    ReleaseHeaderError,
    validate_release_header,
)
from content.release.environment.release_runtime import load_release
from core.io import write_json
from core.release_layout import payload_file
from core.source_digest import (
    content_source_revision,
    current_source_definition_snapshot,
)

_ENTITY_CATALOG_DIGEST = "sha256:" + "1" * 64


def _header(*, release_id: str, release_kind: str = "content") -> dict[str, object]:
    source = current_source_definition_snapshot()
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


def test_typed_header_rejects_execution_bundle_inputs_as_source_identity() -> None:
    document = _header(release_id="content-typed-execution-inputs-001")
    document["sourceDigests"][0]["inputs"] = ["quwoquan_data/scripts"]

    with pytest.raises(ReleaseHeaderError, match="source-definition inputs|必须等于"):
        validate_release_header(document)


def _target_environment_identity_set_header() -> dict[str, object]:
    document = _header(release_id="content-alpha-identity-set-001")
    execution_id = str(document["executionIds"][0])
    identity = {
        "executionId": execution_id,
        "sourceRevision": str(document.pop("sourceRevision")),
        "sourceDigest": str(document.pop("sourceDigest")),
        "entityCatalogDigest": str(document.pop("entityCatalogDigest")),
    }
    identities, identity_set_digest = source_identity_set([identity])
    document.update(
        {
            "selectionScope": "target_environment",
            "targetEnvironment": "alpha",
            "releaseMode": "research",
            "poolDigest": "sha256:" + "3" * 64,
            "counts": {"article": 1, "image": 0, "video": 0, "total": 1},
            "contents": [
                {
                    "contentId": "content-alpha-001",
                    "version": 1,
                    "postRef": "article/alpha-work/1",
                    "executionId": execution_id,
                    "sourceIdentityDigest": source_identity_digest(identity),
                }
            ],
            "authors": [],
            "buildResult": "completed",
            "sourceIdentities": identities,
            "sourceIdentitySetDigest": identity_set_digest,
        }
    )
    return document


def test_typed_header_accepts_research_target_environment_identity_set() -> None:
    document = _target_environment_identity_set_header()

    assert validate_release_header(document) == document


def test_typed_header_rejects_scalar_and_set_identity_together() -> None:
    document = _target_environment_identity_set_header()
    source_digest = str(document["sourceDigests"][0]["digest"])
    document.update(
        {
            "sourceDigest": source_digest,
            "entityCatalogDigest": _ENTITY_CATALOG_DIGEST,
            "sourceRevision": content_source_revision(
                source_digest=source_digest,
                entity_catalog_digest=_ENTITY_CATALOG_DIGEST,
            ),
        }
    )

    with pytest.raises(ReleaseHeaderError, match="mutually exclusive"):
        validate_release_header(document)


def test_typed_header_accepts_commercial_target_environment_identity_set() -> None:
    document = _target_environment_identity_set_header()
    document.update(
        {
            "releaseClass": "commercial",
            "productLifecycleState": "commercial",
            "releaseMode": "commercial",
        }
    )

    assert validate_release_header(document) == document


def test_typed_header_rejects_identity_set_outside_pool_release() -> None:
    document = _target_environment_identity_set_header()
    for key in (
            "selectionScope",
            "targetEnvironment",
            "releaseMode",
        "poolDigest",
        "counts",
        "contents",
        "authors",
        "buildResult",
    ):
        document.pop(key)

    with pytest.raises(ReleaseHeaderError, match="pool selection"):
        validate_release_header(document)


def test_typed_header_accepts_environment_neutral_exact_m100_research_cohort() -> None:
    document = _header(release_id="content-m100-001")
    execution_id = str(document["executionIds"][0])
    identity = {
        "executionId": execution_id,
        "sourceRevision": str(document.pop("sourceRevision")),
        "sourceDigest": str(document.pop("sourceDigest")),
        "entityCatalogDigest": str(document.pop("entityCatalogDigest")),
    }
    identities, identity_set_digest = source_identity_set([identity])
    identity_digest = source_identity_digest(identity)
    contents = [
        {
            "contentId": f"content-{index}",
            "version": 1,
            "postRef": f"{content_type}/work-{index}/1",
            "executionId": execution_id,
            "sourceIdentityDigest": identity_digest,
        }
        for content_type, start, count in (
            ("article", 0, 100),
            ("image", 100, 100),
            ("video", 200, 10),
        )
        for index in range(start, start + count)
    ]
    document.update({
        "selectionScope": "milestone",
        "milestone": "M100",
        "milestoneTargets": {
            "homepage": 100,
            "article": 100,
            "image": 100,
            "video": 10,
        },
        "releaseMode": "research",
        "poolDigest": "sha256:" + "3" * 64,
        "counts": {"article": 100, "image": 100, "video": 10, "total": 210},
        "contents": contents,
        "authors": [],
        "buildResult": "completed",
        "sourceIdentities": identities,
        "sourceIdentitySetDigest": identity_set_digest,
    })

    assert validate_release_header(document) == document


def test_milestone_header_preserves_two_execution_identities_and_rejects_drift() -> None:
    document = _header(release_id="content-m100-cross-identity")
    first_execution = str(document["executionIds"][0])
    first_identity = {
        "executionId": first_execution,
        "sourceRevision": str(document.pop("sourceRevision")),
        "sourceDigest": str(document.pop("sourceDigest")),
        "entityCatalogDigest": str(document.pop("entityCatalogDigest")),
    }
    second_digest = "sha256:" + "9" * 64
    second_execution = "20260806--travel-image--china--scale-002"
    second_identity = {
        "executionId": second_execution,
        "sourceRevision": content_source_revision(
            source_digest=second_digest,
            entity_catalog_digest=_ENTITY_CATALOG_DIGEST,
        ),
        "sourceDigest": second_digest,
        "entityCatalogDigest": _ENTITY_CATALOG_DIGEST,
    }
    identities, identity_set_digest = source_identity_set(
        [first_identity, second_identity]
    )
    identity_digests = {
        first_execution: source_identity_digest(first_identity),
        second_execution: source_identity_digest(second_identity),
    }
    contents = []
    for content_type, start, count in (
        ("article", 0, 100),
        ("image", 100, 100),
        ("video", 200, 10),
    ):
        for index in range(start, start + count):
            execution_id = first_execution if index % 2 == 0 else second_execution
            contents.append(
                {
                    "contentId": f"cross-content-{index}",
                    "version": 1,
                    "postRef": f"{content_type}/cross-work-{index}/1",
                    "executionId": execution_id,
                    "sourceIdentityDigest": identity_digests[execution_id],
                }
            )
    source_documents = list(document["sourceDigests"])
    source_documents.append(
        {**source_documents[0], "digest": second_digest}
    )
    document.update(
        {
            "executionIds": sorted([first_execution, second_execution]),
            "sourceDigests": sorted(
                source_documents, key=lambda row: str(row["digest"])
            ),
            "selectionScope": "milestone",
        "milestone": "M100",
            "milestoneTargets": {
                "homepage": 100,
                "article": 100,
                "image": 100,
                "video": 10,
            },
            "releaseMode": "research",
            "poolDigest": "sha256:" + "3" * 64,
            "counts": {"article": 100, "image": 100, "video": 10, "total": 210},
            "contents": contents,
            "authors": [],
            "buildResult": "completed",
            "sourceIdentities": identities,
            "sourceIdentitySetDigest": identity_set_digest,
        }
    )

    assert validate_release_header(document) == document
    document["contents"][0]["sourceIdentityDigest"] = "sha256:" + "f" * 64
    with pytest.raises(ReleaseHeaderError, match="closure drifted"):
        validate_release_header(document)


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
