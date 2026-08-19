"""Typed immutable release header and attestation projections."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from content.release.canonical.object_transaction_contract import (
    RELEASE_SCHEMA,
    ObjectTransactionError,
)
from content.release.canonical.release_attestation import ReleaseAttestation
from content.release.canonical.release_header import validate_release_header
from content.release.model import DataSourceOwner, ReleaseKind
from governance.coverage.distribution import ProductLifecycleState, ReleaseClass
from core.schema import assert_valid
from core.source_digest import SourceDefinitionSnapshot


def release_desired_state_document(
    *,
    release_id: str,
    desired: Mapping[str, list[str]],
) -> dict[str, object]:
    document: dict[str, object] = {
        "schema": "quwoquan_data.release_desired_state",
        "releaseId": release_id,
        "desiredRefs": dict(desired),
    }
    assert_valid(
        document,
        "release",
        "release_desired_state",
        label=f"release_desired_state:{release_id}",
    )
    return document


def release_header_document(
    *,
    release_id: str,
    execution_ids: list[str],
    source_revision: str | None,
    source_digest: str | None,
    entity_catalog_digest: str | None,
    source_digest_documents: list[dict[str, object]],
    asset_admission: Mapping[str, Any],
    canonical_merkle: str,
    release_class: str,
    product_lifecycle_state: str,
    reviewed_closure_adoption: Mapping[str, Any] | None,
    selection_scope: str | None = None,
    target_environment: str | None = None,
    release_mode: str | None = None,
    pool_digest: str | None = None,
    counts: Mapping[str, int] | None = None,
    contents: list[dict[str, object]] | None = None,
    authors: list[dict[str, object]] | None = None,
    milestone: str | None = None,
    milestone_targets: Mapping[str, int] | None = None,
    source_identities: list[dict[str, object]] | None = None,
    source_identity_set_digest: str | None = None,
) -> dict[str, Any]:
    scalar_values = (source_revision, source_digest, entity_catalog_digest)
    scalar_mode = all(value is not None for value in scalar_values)
    if any(value is not None for value in scalar_values) and not scalar_mode:
        raise ObjectTransactionError(
            "DATA.RELEASE.SOURCE_IDENTITY_INCOMPLETE: scalar identity"
        )
    identity_set_mode = (
        source_identities is not None or source_identity_set_digest is not None
    )
    if scalar_mode == identity_set_mode:
        raise ObjectTransactionError(
            "DATA.RELEASE.SOURCE_IDENTITY_MODE_INVALID: scalar and set modes "
            "must be mutually exclusive"
        )
    if identity_set_mode and (
        not source_identities or source_identity_set_digest is None
    ):
        raise ObjectTransactionError(
            "DATA.RELEASE.SOURCE_IDENTITY_INCOMPLETE: identity set"
        )
    document: dict[str, Any] = {
        "schema": RELEASE_SCHEMA,
        "releaseId": release_id,
        "sourceOwner": DataSourceOwner.QWQ_DATA,
        "releaseKind": ReleaseKind.CONTENT,
        "releaseClass": release_class,
        "productLifecycleState": product_lifecycle_state,
        "containsUnverifiedAssets": asset_admission["containsUnverifiedAssets"],
        "rightsStatusCounts": asset_admission["rightsStatusCounts"],
        "authorizationRequiredAssetIds": asset_admission[
            "authorizationRequiredAssetIds"
        ],
        "researchAcceptedCount": asset_admission["researchAcceptedCount"],
        "commercialAcceptedCount": asset_admission["commercialAcceptedCount"],
        "canonicalMerkle": canonical_merkle,
        "executionIds": execution_ids,
        "sourceDigests": source_digest_documents,
    }
    if scalar_mode:
        document.update(
            {
                "sourceRevision": source_revision,
                "sourceDigest": source_digest,
                "entityCatalogDigest": entity_catalog_digest,
            }
        )
    if identity_set_mode:
        assert source_identities is not None
        document["sourceIdentities"] = list(source_identities)
        document["sourceIdentitySetDigest"] = source_identity_set_digest
    if reviewed_closure_adoption is not None:
        document["reviewedClosureAdoption"] = dict(reviewed_closure_adoption)
    if pool_digest is not None:
        document.update(
            {
                "selectionScope": selection_scope,
                "releaseMode": release_mode,
                "poolDigest": pool_digest,
                "counts": dict(counts or {}),
                "contents": list(contents or []),
                "authors": list(authors or []),
                "buildResult": "completed",
            }
        )
        if target_environment is not None:
            document["targetEnvironment"] = target_environment
        if milestone is not None:
            document["milestone"] = milestone
            document["milestoneTargets"] = dict(milestone_targets or {})
    validate_release_header(document, label=f"release_header:{release_id}")
    return document


def release_attestation_document(
    *,
    release_id: str,
    execution_ids: list[str],
    source_revision: str | None,
    source_digest: str | None,
    entity_catalog_digest: str | None,
    source_digests: tuple[SourceDefinitionSnapshot, ...],
    asset_admission: Mapping[str, Any],
    canonical_merkle: str,
    entity_count: int,
    post_count: int,
    creator_count: int,
    tag_count: int,
    payload_sha256: str,
    recorded_at: str,
    release_class: str,
    source_identities: tuple[dict[str, object], ...] = (),
    source_identity_set_digest: str | None = None,
) -> dict[str, object]:
    return ReleaseAttestation(
        release_id=release_id,
        source_owner=DataSourceOwner.QWQ_DATA,
        release_kind=ReleaseKind.CONTENT,
        release_class=ReleaseClass(release_class),
        product_lifecycle_state=ProductLifecycleState(release_class),
        contains_unverified_assets=bool(
            asset_admission["containsUnverifiedAssets"]
        ),
        rights_status_counts=dict(asset_admission["rightsStatusCounts"]),
        authorization_required_asset_ids=tuple(
            asset_admission["authorizationRequiredAssetIds"]
        ),
        research_accepted_count=int(asset_admission["researchAcceptedCount"]),
        commercial_accepted_count=int(asset_admission["commercialAcceptedCount"]),
        execution_ids=tuple(execution_ids),
        entity_count=entity_count,
        post_count=post_count,
        creator_count=creator_count,
        tag_count=tag_count,
        canonical_merkle=canonical_merkle,
        source_revision=source_revision,
        source_digest=source_digest,
        entity_catalog_digest=entity_catalog_digest,
        source_digests=source_digests,
        payload_sha256=payload_sha256,
        recorded_at=recorded_at,
        source_identities=source_identities,
        source_identity_set_digest=source_identity_set_digest,
    ).to_document()


__all__ = [
    "release_attestation_document",
    "release_desired_state_document",
    "release_header_document",
]
