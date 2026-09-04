"""Typed runtime validation for the canonical immutable release header.

The repository's compact schema validator intentionally implements only a
bounded JSON-schema subset.  Cross-field release identity invariants therefore
live here and are called by every writer/consumer boundary; schema conditionals
must never be treated as runtime enforcement.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from content.release.canonical.object_source_identity import (
    source_identity_digest,
    source_identity_set,
)
from content.release.canonical.object_transaction_contract import ObjectTransactionError
from content.release.model import ReleaseKind
from core.schema import assert_valid
from core.source_digest import (
    SourceDefinitionSnapshot,
    SourceDigestError,
    content_source_revision,
)
from governance.coverage.distribution import ProductLifecycleState, ReleaseClass


class ReleaseHeaderError(ValueError):
    """The public release header violates a cross-field identity invariant."""


_SOURCE_IDENTITY_FIELDS = (
    "sourceRevision",
    "sourceDigest",
    "entityCatalogDigest",
)
_SOURCE_IDENTITY_SET_FIELDS = ("sourceIdentities", "sourceIdentitySetDigest")


def validate_release_header(
    value: object,
    *,
    label: str = "release header",
) -> dict[str, Any]:
    """Validate schema shape plus lifecycle and source-identity relations."""
    if isinstance(value, Mapping) and any(
        field in value for field in _SOURCE_IDENTITY_FIELDS
    ) and any(field in value for field in _SOURCE_IDENTITY_SET_FIELDS):
        raise ReleaseHeaderError(
            f"{label} scalar and set source identity modes are mutually exclusive"
        )
    if (
        isinstance(value, Mapping)
        and any(field in value for field in _SOURCE_IDENTITY_SET_FIELDS)
        and value.get("selectionScope")
        not in {"target_environment", "explicit_cohort"}
    ):
        raise ReleaseHeaderError(
            f"{label} source identity set requires a pool selection"
        )
    if (
        isinstance(value, Mapping)
        and value.get("releaseKind") == ReleaseKind.EMPTY_BASELINE.value
        and any(
            field in value
            for field in (*_SOURCE_IDENTITY_FIELDS, *_SOURCE_IDENTITY_SET_FIELDS)
        )
    ):
        raise ReleaseHeaderError(
            f"{label} empty baseline must not carry content source identity"
        )
    try:
        assert_valid(value, "release", "release_header", label=label)
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise ReleaseHeaderError(str(exc)) from exc
    if not isinstance(value, Mapping):
        raise ReleaseHeaderError(f"{label} must be an object")
    document = dict(value)
    try:
        release_kind = ReleaseKind(str(document.get("releaseKind") or ""))
        release_class = ReleaseClass(str(document.get("releaseClass") or ""))
        lifecycle = ProductLifecycleState(
            str(document.get("productLifecycleState") or "")
        )
    except ValueError as exc:
        raise ReleaseHeaderError(f"{label} lifecycle identity is invalid") from exc
    if release_class.value != lifecycle.value:
        raise ReleaseHeaderError(
            f"{label} releaseClass must equal productLifecycleState"
        )
    target_environment = document.get("targetEnvironment")
    selection_scope = document.get("selectionScope")
    release_mode = document.get("releaseMode")
    if selection_scope is not None:
        if release_mode != release_class.value:
            raise ReleaseHeaderError(
                f"{label} releaseMode/releaseClass are inconsistent"
            )
        counts = document.get("counts")
        if not isinstance(counts, Mapping) or int(counts.get("total") or 0) != sum(
            int(counts.get(content_type) or 0)
            for content_type in ("article", "image", "video")
        ):
            raise ReleaseHeaderError(f"{label} carrier counts are inconsistent")
        contents = document.get("contents")
        authors = document.get("authors")
        if not isinstance(contents, list) or len(contents) != int(
            counts.get("total") or 0
        ):
            raise ReleaseHeaderError(f"{label} contents do not match counts.total")
        content_ids: set[str] = set()
        post_refs: set[str] = set()
        content_selection_digests: set[str] = set()
        content_modes: set[str] = set()
        for item in contents:
            if not isinstance(item, Mapping):
                raise ReleaseHeaderError(f"{label} content entry is invalid")
            content_id = str(item.get("contentId") or "").strip()
            post_ref = str(item.get("postRef") or "").strip()
            selection_identity_digest = str(
                item.get("selectionIdentityDigest") or ""
            ).strip()
            canonical_object_digest = str(
                item.get("canonicalObjectDigest") or ""
            ).strip()
            content_library_binding_digest = str(
                item.get("contentLibraryBindingDigest") or ""
            ).strip()
            execution_id = str(item.get("executionId") or "").strip()
            source_identity_digest_value = str(
                item.get("sourceIdentityDigest") or ""
            ).strip()
            current_mode = bool(
                selection_identity_digest
                and canonical_object_digest
                and content_library_binding_digest
                and not execution_id
                and not source_identity_digest_value
            )
            previous_shape_mode = bool(
                execution_id
                and source_identity_digest_value
                and not selection_identity_digest
                and not canonical_object_digest
                and not content_library_binding_digest
            )
            version = item.get("version")
            if (
                not content_id
                or not post_ref
                or not (current_mode or previous_shape_mode)
                or (current_mode and not all(
                    value.startswith("sha256:")
                    for value in (
                        selection_identity_digest,
                        canonical_object_digest,
                        content_library_binding_digest,
                    )
                ))
                or (
                    previous_shape_mode
                    and not source_identity_digest_value.startswith("sha256:")
                )
                or not isinstance(version, int)
                or isinstance(version, bool)
                or version < 1
                or content_id in content_ids
                or post_ref in post_refs
            ):
                raise ReleaseHeaderError(f"{label} content entry is invalid")
            content_modes.add(
                "handoff" if current_mode else "previous_shape_audit"
            )
            if current_mode:
                if selection_identity_digest in content_selection_digests:
                    raise ReleaseHeaderError(
                        f"{label} selection identity is duplicated"
                    )
                content_selection_digests.add(selection_identity_digest)
            content_ids.add(content_id)
            post_refs.add(post_ref)
        if len(content_modes) > 1:
            raise ReleaseHeaderError(
                f"{label} content entries mix current handoff and historical audit shapes"
            )
        if not isinstance(authors, list):
            raise ReleaseHeaderError(f"{label} authors must be an array")
        author_ids: set[str] = set()
        for item in authors:
            if not isinstance(item, Mapping):
                raise ReleaseHeaderError(f"{label} author entry is invalid")
            author_id = str(item.get("authorId") or "").strip()
            creator_ref = str(item.get("creatorRef") or "").strip()
            version = item.get("version")
            if (
                not author_id
                or not creator_ref
                or not isinstance(version, int)
                or isinstance(version, bool)
                or version < 1
                or author_id in author_ids
            ):
                raise ReleaseHeaderError(f"{label} author entry is invalid")
            author_ids.add(author_id)
    elif any(
        key in document
        for key in (
            "selectionScope",
            "releaseMode",
            "poolDigest",
            "counts",
            "contents",
            "authors",
            "buildResult",
        )
    ):
        raise ReleaseHeaderError(
            f"{label} pool selection fields require selectionScope"
        )

    authorization_ids = document.get("authorizationRequiredAssetIds")
    if not isinstance(authorization_ids, list):
        raise ReleaseHeaderError(
            f"{label} authorizationRequiredAssetIds must be an array"
        )
    contains_unverified = document.get("containsUnverifiedAssets") is True
    if contains_unverified != bool(authorization_ids):
        raise ReleaseHeaderError(
            f"{label} containsUnverifiedAssets must match authorization-required assets"
        )
    rights_counts = document.get("rightsStatusCounts")
    if not isinstance(rights_counts, Mapping):
        raise ReleaseHeaderError(f"{label} rightsStatusCounts must be an object")
    if release_class is ReleaseClass.COMMERCIAL and (
        contains_unverified
        or authorization_ids
        or any(
            int(rights_counts.get(status) or 0)
            for status in ("unverified", "restricted", "unknown")
        )
    ):
        raise ReleaseHeaderError(
            f"{label} commercial release contains non-verified assets"
        )

    execution_ids = document.get("executionIds")
    if not isinstance(execution_ids, list):
        raise ReleaseHeaderError(f"{label} executionIds must be an array")
    present_identity = {field for field in _SOURCE_IDENTITY_FIELDS if field in document}
    present_identity_set = {
        field for field in _SOURCE_IDENTITY_SET_FIELDS if field in document
    }
    if release_kind is ReleaseKind.EMPTY_BASELINE:
        if "reviewedClosureAdoption" in document:
            raise ReleaseHeaderError(
                f"{label} empty baseline cannot carry adoption provenance"
            )
        if selection_scope is not None:
            raise ReleaseHeaderError(
                f"{label} empty baseline cannot carry a pool selection"
            )
        if present_identity or present_identity_set:
            raise ReleaseHeaderError(
                f"{label} empty baseline must not carry content source identity"
            )
        if (
            execution_ids
            or authorization_ids
            or contains_unverified
            or int(document.get("researchAcceptedCount") or 0)
            or int(document.get("commercialAcceptedCount") or 0)
            or any(int(value or 0) for value in rights_counts.values())
        ):
            raise ReleaseHeaderError(
                f"{label} empty baseline must not carry content admission state"
            )
        return document

    if not execution_ids:
        raise ReleaseHeaderError(f"{label} content release requires executionIds")
    source_documents = document.get("sourceDigests")
    if not isinstance(source_documents, list) or not source_documents:
        raise ReleaseHeaderError(
            f"{label} content release requires sourceDigests"
        )
    try:
        identity_set_mode = bool(present_identity_set)
        frozen_digests = tuple(
            SourceDefinitionSnapshot.from_document(item).digest
            for item in source_documents
        )
        if frozen_digests != tuple(sorted(set(frozen_digests))):
            raise ReleaseHeaderError(
                f"{label} sourceDigests must be sorted and unique"
            )
        if identity_set_mode:
            if present_identity_set != set(_SOURCE_IDENTITY_SET_FIELDS):
                raise ReleaseHeaderError(
                    f"{label} source identity set is incomplete"
                )
            if selection_scope not in {
                "target_environment",
                "explicit_cohort",
            }:
                raise ReleaseHeaderError(
                    f"{label} source identity set requires a pool release"
                )
            raw_identities = document.get("sourceIdentities")
            if not isinstance(raw_identities, list) or not raw_identities:
                raise ReleaseHeaderError(
                    f"{label} sourceIdentities must be an array"
                )
            expanded: list[dict[str, str]] = []
            identity_bindings: set[tuple[str, str]] = set()
            for raw in raw_identities:
                if not isinstance(raw, Mapping):
                    raise ReleaseHeaderError(
                        f"{label} source identity entry is invalid"
                    )
                raw_execution_ids = raw.get("executionIds")
                if not isinstance(raw_execution_ids, list):
                    raise ReleaseHeaderError(
                        f"{label} source identity executionIds are invalid"
                    )
                digest = source_identity_digest(raw)
                for execution_id in raw_execution_ids:
                    normalized_id = str(execution_id or "").strip()
                    expanded.append({
                        "executionId": normalized_id,
                        "sourceRevision": str(raw.get("sourceRevision") or ""),
                        "sourceDigest": str(raw.get("sourceDigest") or ""),
                        "entityCatalogDigest": str(
                            raw.get("entityCatalogDigest") or ""
                        ),
                    })
                    identity_bindings.add((normalized_id, digest))
            expected_identities, expected_set_digest = source_identity_set(expanded)
            if (
                raw_identities != expected_identities
                or document.get("sourceIdentitySetDigest") != expected_set_digest
                or sorted(execution_ids)
                != sorted({row["executionId"] for row in expanded})
                or set(frozen_digests)
                != {str(row["sourceDigest"]) for row in expected_identities}
            ):
                raise ReleaseHeaderError(
                    f"{label} source identity set closure drifted"
                )
            return _validate_reviewed_adoption(document, label=label)
        if present_identity != set(_SOURCE_IDENTITY_FIELDS):
            raise ReleaseHeaderError(
                f"{label} content source identity is incomplete"
            )
        if len(frozen_digests) != 1:
            raise ReleaseHeaderError(
                f"{label} content release requires exactly one sourceDigest"
            )
        frozen_digest = frozen_digests[0]
        source_digest = str(document["sourceDigest"])
        entity_catalog_digest = str(document["entityCatalogDigest"])
        expected_revision = content_source_revision(
            source_digest=source_digest,
            entity_catalog_digest=entity_catalog_digest,
        )
    except ReleaseHeaderError:
        raise
    except (
        KeyError,
        ObjectTransactionError,
        SourceDigestError,
        TypeError,
        ValueError,
    ) as exc:
        raise ReleaseHeaderError(f"{label} content source identity is invalid") from exc
    if source_digest != frozen_digest:
        raise ReleaseHeaderError(
            f"{label} sourceDigest differs from sourceDigests closure"
        )
    if document["sourceRevision"] != expected_revision:
        raise ReleaseHeaderError(
            f"{label} sourceRevision does not match sourceDigest/entityCatalogDigest"
        )
    return _validate_reviewed_adoption(document, label=label)


def _validate_reviewed_adoption(
    document: dict[str, Any],
    *,
    label: str,
) -> dict[str, Any]:
    adoption = document.get("reviewedClosureAdoption")
    migration = document.get("contractMigration")
    if adoption is not None and migration is not None:
        raise ReleaseHeaderError(
            f"{label} adoption and contract migration are mutually exclusive"
        )
    if adoption is not None:
        if not isinstance(adoption, Mapping):
            raise ReleaseHeaderError(f"{label} adoption provenance is invalid")
        source_identity = adoption.get("sourceReleaseIdentity")
        if not isinstance(source_identity, Mapping) or source_identity.get(
            "releaseId"
        ) == document.get("releaseId"):
            raise ReleaseHeaderError(
                f"{label} cannot reuse the collided source releaseId"
            )
    if migration is not None:
        if not isinstance(migration, Mapping):
            raise ReleaseHeaderError(
                f"{label} contract migration provenance is invalid"
            )
        if (
            migration.get("sourceReleaseId") == document.get("releaseId")
            or migration.get("sourceCanonicalMerkle")
            != document.get("canonicalMerkle")
            or migration.get("sourceSamplePlanRef") != "uat/sample_plan.json"
            or document.get("samplePlanRef") != "uat/sample_plan.json"
            or not document.get("samplePlanDigest")
        ):
            raise ReleaseHeaderError(
                f"{label} contract migration provenance drifted"
            )
    return document


__all__ = ["ReleaseHeaderError", "validate_release_header"]
