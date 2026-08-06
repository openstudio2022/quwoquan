"""Typed runtime validation for the canonical immutable release header.

The repository's compact schema validator intentionally implements only a
bounded JSON-schema subset.  Cross-field release identity invariants therefore
live here and are called by every writer/consumer boundary; schema conditionals
must never be treated as runtime enforcement.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from content.release.model import ReleaseKind
from core.schema import assert_valid
from core.source_digest import (
    SourceDigest,
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


def validate_release_header(
    value: object,
    *,
    label: str = "release header",
) -> dict[str, Any]:
    """Validate schema shape plus lifecycle and source-identity relations."""
    if (
        isinstance(value, Mapping)
        and value.get("releaseKind") == ReleaseKind.EMPTY_BASELINE.value
        and any(field in value for field in _SOURCE_IDENTITY_FIELDS)
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
    if release_kind is ReleaseKind.EMPTY_BASELINE:
        if "reviewedClosureAdoption" in document:
            raise ReleaseHeaderError(
                f"{label} empty baseline cannot carry adoption provenance"
            )
        if present_identity:
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

    if present_identity != set(_SOURCE_IDENTITY_FIELDS):
        raise ReleaseHeaderError(f"{label} content source identity is incomplete")
    if not execution_ids:
        raise ReleaseHeaderError(f"{label} content release requires executionIds")
    source_documents = document.get("sourceDigests")
    if not isinstance(source_documents, list) or len(source_documents) != 1:
        raise ReleaseHeaderError(
            f"{label} content release requires exactly one sourceDigest"
        )
    try:
        frozen_digest = SourceDigest.from_document(source_documents[0]).digest
        source_digest = str(document["sourceDigest"])
        entity_catalog_digest = str(document["entityCatalogDigest"])
        expected_revision = content_source_revision(
            source_digest=source_digest,
            entity_catalog_digest=entity_catalog_digest,
        )
    except (KeyError, SourceDigestError, TypeError, ValueError) as exc:
        raise ReleaseHeaderError(f"{label} content source identity is invalid") from exc
    if source_digest != frozen_digest:
        raise ReleaseHeaderError(
            f"{label} sourceDigest differs from sourceDigests closure"
        )
    if document["sourceRevision"] != expected_revision:
        raise ReleaseHeaderError(
            f"{label} sourceRevision does not match sourceDigest/entityCatalogDigest"
        )
    adoption = document.get("reviewedClosureAdoption")
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
    return document


__all__ = ["ReleaseHeaderError", "validate_release_header"]
