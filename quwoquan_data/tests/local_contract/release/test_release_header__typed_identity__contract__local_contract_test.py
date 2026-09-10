# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/spec.md
"""Public release consumers enforce cross-field identity beyond schema shape."""
from __future__ import annotations

import pytest
from content.release.canonical.object_source_identity import (
    source_identity_digest,
    source_identity_set,
)
from content.release.canonical.release_header import (
    ReleaseHeaderError,
    validate_release_header,
)
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
        "containsUnverifiedAssets": False,
        "rightsStatusCounts": {
            "verified": 0,
            "unverified": 0,
            "restricted": 0,
            "unknown": 0,
        },
        "authorizationRequiredAssetIds": [],
        "acceptedCount": 0,
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


@pytest.mark.parametrize("field", ["researchAcceptedCount", "commercialAcceptedCount"])
def test_typed_header_rejects_retired_count_even_beside_new_count(field: str) -> None:
    document = _header(release_id="retired-count-001")
    document[field] = 0
    with pytest.raises(ReleaseHeaderError):
        validate_release_header(document)


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

    with pytest.raises(ReleaseHeaderError, match="source-definition inputs|必须等于|content source identity is invalid"):
        validate_release_header(document)


def _explicit_cohort_identity_set_header() -> dict[str, object]:
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
            "poolDigest": "sha256:" + "3" * 64,
            "counts": {"homepage": 0, "article": 1, "image": 0, "video": 0, "total": 1},
            "contents": [
                {
                    "contentId": "content-alpha-001",
                    "version": 1,
                    "postRef": "article/alpha-work/1",
                    "selectionIdentityDigest": "sha256:" + "7" * 64,
                    "canonicalObjectDigest": "sha256:" + "8" * 64,
                    "contentLibraryBindingDigest": "sha256:" + "9" * 64,
                }
            ],
            "authors": [],
            "buildResult": "completed",
            "sourceIdentities": identities,
            "sourceIdentitySetDigest": identity_set_digest,
        }
    )
    return document


def test_typed_header_accepts_research_explicit_cohort_identity_set() -> None:
    document = _explicit_cohort_identity_set_header()

    assert validate_release_header(document) == document


def test_typed_header_milestone_counts_must_reach_but_may_exceed_targets() -> None:
    """spec_ref: multi-carrier-release/REQ-008 — 达标判据是计数不低于里程碑目标。"""
    document = _explicit_cohort_identity_set_header()
    content = dict(document["contents"][0])
    post_refs = ["article/alpha-work/1", "article/alpha-work/2", "image/alpha-work/1", "video/alpha-work/1"]
    document["contents"] = [
        {
            **content,
            "contentId": f"content-alpha-{index:03d}",
            "postRef": post_ref,
            "selectionIdentityDigest": "sha256:" + str(index) * 64,
            "canonicalObjectDigest": "sha256:" + str(index + 4) * 64,
        }
        for index, post_ref in enumerate(post_refs, start=1)
    ]
    # M1 目标 1/1/1/1；article 实际 2 篇超过目标，仍达标。
    document.update({"milestone": "M1", "milestoneTargets": {"homepage": 1, "article": 1, "image": 1, "video": 1}})
    document["counts"] = {"homepage": 1, "article": 2, "image": 1, "video": 1, "total": 5}
    assert validate_release_header(document) == document

    document["contents"] = document["contents"][:3]
    document["counts"] = {"homepage": 1, "article": 2, "image": 1, "video": 0, "total": 4}
    with pytest.raises(ReleaseHeaderError, match="fall short"):
        validate_release_header(document)


def test_typed_header_rejects_scalar_and_set_identity_together() -> None:
    document = _explicit_cohort_identity_set_header()
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


@pytest.mark.parametrize("field", ("releaseClass", "productLifecycleState", "readinessPhase"))
def test_typed_header_rejects_removed_category_fields(field: str) -> None:
    """spec_ref: multi-carrier-release/REQ-002 — 现役闭集不消费历史类别。"""
    document = _explicit_cohort_identity_set_header()
    document[field] = "production"
    with pytest.raises(ReleaseHeaderError):
        validate_release_header(document)


def test_typed_header_rejects_identity_set_outside_pool_release() -> None:
    document = _explicit_cohort_identity_set_header()
    for key in (
        "poolDigest",
        "counts",
        "contents",
        "authors",
        "buildResult",
    ):
        document.pop(key)

    with pytest.raises(ReleaseHeaderError, match="pool release"):
        validate_release_header(document)


@pytest.mark.parametrize(
    "forbidden_field",
    (
        "targetEnvironment",
        "selectionScope",
        "releaseMode",
        "samplePlanRef",
        "samplePlanDigest",
        "contractMigration",
    ),
)
def test_typed_header_rejects_consumer_fields(forbidden_field: str) -> None:
    document = _explicit_cohort_identity_set_header()
    document[forbidden_field] = (
        {"reasonCode": "consumer"}
        if forbidden_field == "contractMigration"
        else "consumer"
    )

    with pytest.raises(ReleaseHeaderError):
        validate_release_header(document)
