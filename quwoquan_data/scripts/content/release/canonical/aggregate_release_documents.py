"""Typed immutable release header and attestation projections."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from content.release.canonical.object_transaction_contract import RELEASE_SCHEMA
from content.release.canonical.release_attestation import ReleaseAttestation
from content.release.model import DataSourceOwner, ReleaseKind
from core.source_digest import SourceDigest


def release_header_document(
    *,
    release_id: str,
    execution_ids: list[str],
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
    source_digest_documents: list[dict[str, object]],
    asset_admission: Mapping[str, Any],
    canonical_merkle: str,
    release_class: str,
    product_lifecycle_state: str,
    reviewed_closure_adoption: Mapping[str, Any] | None,
) -> dict[str, Any]:
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
        "sourceRevision": source_revision,
        "sourceDigest": source_digest,
        "entityCatalogDigest": entity_catalog_digest,
        "sourceDigests": source_digest_documents,
    }
    if reviewed_closure_adoption is not None:
        document["reviewedClosureAdoption"] = dict(reviewed_closure_adoption)
    return document


def release_attestation_document(
    *,
    release_id: str,
    execution_ids: list[str],
    source_revision: str,
    source_digest: str,
    entity_catalog_digest: str,
    source_digests: tuple[SourceDigest, ...],
    asset_admission: Mapping[str, Any],
    canonical_merkle: str,
    entity_count: int,
    post_count: int,
    creator_count: int,
    tag_count: int,
    payload_sha256: str,
    recorded_at: str,
    distribution_policy: Any,
) -> dict[str, object]:
    return ReleaseAttestation(
        release_id=release_id,
        source_owner=DataSourceOwner.QWQ_DATA,
        release_kind=ReleaseKind.CONTENT,
        release_class=distribution_policy.release_class,
        product_lifecycle_state=distribution_policy.product_lifecycle_state,
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
    ).to_document()


__all__ = ["release_attestation_document", "release_header_document"]
