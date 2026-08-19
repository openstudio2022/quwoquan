"""Validate and reuse an existing immutable aggregate release."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.aggregate_release_closure import existing_refs
from content.release.canonical.aggregate_release_documents import (
    assert_holdings_reachable,
    release_attestation_document,
    release_header_document,
)
from content.release.canonical.environment_release_selection import (
    EnvironmentReleaseSelection,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
    assert_environment_neutral,
)
from content.release.canonical.release_attestation import ReleaseAttestation
from content.release.canonical.release_header import validate_release_header
from content.release.canonical.reviewed_closure_aggregate import (
    ReviewedClosureSelection,
    revalidate_reviewed_closure_selection,
)
from content.release.model import DataSourceOwner
from core.release_layout import (
    attestation_root,
    objects_merkle,
    payload_digest,
    payload_file,
)
from core.schema import assert_valid
from core.source_digest import SourceDefinitionSnapshot


def reuse_existing_aggregate_release(
    *,
    publish_root: Path,
    final_root: Path,
    release_id: str,
    execution_ids: list[str],
    source_revision: str | None,
    source_digest: str | None,
    entity_catalog_digest: str | None,
    source_digest_documents: list[dict[str, object]],
    source_digests: tuple[SourceDefinitionSnapshot, ...],
    desired: dict[str, list[str]],
    release_class: str,
    reviewed_closure_adoption: Mapping[str, Any] | None,
    adoption_output_root: Path | None,
    reviewed_selection: ReviewedClosureSelection | None,
    environment_selection: EnvironmentReleaseSelection | None,
    release_contents: list[dict[str, object]] | None,
    release_authors: list[dict[str, object]] | None,
    milestone: str | None,
    milestone_targets: Mapping[str, int] | None,
    source_identities: tuple[dict[str, object], ...],
    source_identity_set_digest: str | None,
    build_release_asset_admission_fn: Callable[..., dict[str, Any]],
    build_release_media_manifest_fn: Callable[..., dict[str, Any]],
    scan_release_contract_fn: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """Recompute every create-once invariant before returning idempotently."""
    entity_refs = set(desired["entities"])
    post_refs = set(desired["posts"])
    creator_refs = list(desired["creators"])
    tag_refs = list(desired["tags"])
    try:
        desired_state = _read_json(payload_file(final_root, "desired_state.json"))
        expected_desired_state = {
            "schema": "quwoquan_data.release_desired_state",
            "releaseId": release_id,
            "desiredRefs": desired,
        }
        assert_valid(
            desired_state,
            "release",
            "release_desired_state",
            label=f"release_desired_state:{release_id}",
        )
        if desired_state != expected_desired_state or existing_refs(
            final_root
        ) != desired:
            raise ObjectTransactionError("existing release desired state drifted")

        asset_admission = _read_json(payload_file(final_root, "asset_admission.json"))
        assert_valid(
            asset_admission,
            "release",
            "release_asset_admission",
            label=f"release_asset_admission:{release_id}",
        )
        expected_asset_admission = build_release_asset_admission_fn(
            release_id=release_id,
            objects_root=payload_file(final_root, "objects"),
            desired=desired,
            release_class=release_class,
        )
        assert_valid(
            expected_asset_admission,
            "release",
            "release_asset_admission",
            label=f"expected_release_asset_admission:{release_id}",
        )
        if asset_admission != expected_asset_admission:
            raise ObjectTransactionError("existing release asset admission drifted")

        selected_merkle = objects_merkle(final_root)
        header = _read_json(payload_file(final_root, "release.json"))
        validate_release_header(header, label=f"release_header:{release_id}")
        expected_header = release_header_document(
            release_id=release_id,
            execution_ids=execution_ids,
            source_revision=source_revision,
            source_digest=source_digest,
            entity_catalog_digest=entity_catalog_digest,
            source_digest_documents=source_digest_documents,
            asset_admission=asset_admission,
            canonical_merkle=selected_merkle,
            release_class=release_class,
            product_lifecycle_state=release_class,
            reviewed_closure_adoption=reviewed_closure_adoption,
            selection_scope=(
                environment_selection.selection_scope
                if environment_selection is not None
                else None
            ),
            target_environment=(
                environment_selection.environment
                if environment_selection is not None
                else None
            ),
            release_mode=(
                environment_selection.release_mode
                if environment_selection is not None
                else None
            ),
            pool_digest=(
                environment_selection.pool_digest
                if environment_selection is not None
                else None
            ),
            counts=(
                environment_selection.counts
                if environment_selection is not None
                else None
            ),
            contents=release_contents,
            authors=release_authors,
            milestone=milestone,
            milestone_targets=milestone_targets,
            source_identities=(
                list(source_identities) if source_identities else None
            ),
            source_identity_set_digest=source_identity_set_digest,
        )
        if header != expected_header:
            raise ObjectTransactionError("existing release header drifted")

        expected_index = {
            "schema": "quwoquan_data.release_object_index",
            **desired,
        }
        expected_sample = {
            "schema": "quwoquan_data.release_sample_bundle",
            **desired,
        }
        if _read_json(payload_file(final_root, "index/objects.json")) != (
            expected_index
        ) or _read_json(payload_file(final_root, "sample_bundle.json")) != (
            expected_sample
        ):
            raise ObjectTransactionError(
                "existing release index/sample closure drifted"
            )

        media_manifest = _read_json(payload_file(final_root, "media_manifest.json"))
        if reviewed_selection is not None:
            expected_media_manifest = {
                **reviewed_selection.media_manifest,
                "releaseId": release_id,
                "sourceOwner": DataSourceOwner.QWQ_DATA,
            }
            if media_manifest != expected_media_manifest:
                raise ObjectTransactionError(
                    "existing reviewed closure media manifest drifted"
                )
            if selected_merkle != objects_merkle(
                reviewed_selection.source_release_root
            ):
                raise ObjectTransactionError(
                    "existing reviewed closure object bytes drifted"
                )
            revalidate_reviewed_closure_selection(
                reviewed_closure_adoption=reviewed_closure_adoption,
                output_root=adoption_output_root,
                selection=reviewed_selection,
            )
        else:
            expected_media_manifest = build_release_media_manifest_fn(
                release_id=release_id,
                post_refs=desired["posts"],
                entity_refs=desired["entities"],
                creator_refs=desired["creators"],
                publish_root=publish_root,
            )
            if (
                expected_media_manifest["issues"]
                or media_manifest != expected_media_manifest
            ):
                raise ObjectTransactionError(
                    "existing release media manifest drifted"
                )
        assert_valid(
            media_manifest,
            "release",
            "media_manifest",
            label=f"release_media_manifest:{release_id}",
        )

        consistency = scan_release_contract_fn(
            expected_desired_state,
            release_root=final_root,
            phase="preflight",
        )
        if consistency["status"] != "passed":
            raise ObjectTransactionError(
                "existing release consistency closure drifted"
            )
        assert_environment_neutral(final_root)
        # Reusing a sealed release still has to prove its holdings are reachable:
        # the library may have reclaimed entries since the release was cut.
        assert_holdings_reachable(final_root, release_id)

        aggregate = _read_json(attestation_root(final_root) / "release.json")
        assert_valid(
            aggregate,
            "release",
            "release_attestation",
            label=f"release_attestation:{release_id}",
        )
        typed_attestation = ReleaseAttestation.from_document(aggregate)
        expected_attestation = release_attestation_document(
            release_id=release_id,
            execution_ids=execution_ids,
            source_revision=source_revision,
            source_digest=source_digest,
            entity_catalog_digest=entity_catalog_digest,
            source_digests=source_digests,
            asset_admission=asset_admission,
            canonical_merkle=selected_merkle,
            entity_count=len(entity_refs),
            post_count=len(post_refs),
            creator_count=len(creator_refs),
            tag_count=len(tag_refs),
            payload_sha256=payload_digest(final_root),
            recorded_at=typed_attestation.recorded_at,
            release_class=release_class,
            source_identities=source_identities,
            source_identity_set_digest=source_identity_set_digest,
        )
        if aggregate != expected_attestation:
            raise ObjectTransactionError("existing release attestation drifted")
    except Exception as exc:
        raise ObjectTransactionError(
            f"aggregate release create-once conflict: {final_root}"
        ) from exc
    result = {
        "schema": "quwoquan_data.aggregate_release_result",
        "releaseId": release_id,
        "releaseRoot": str(final_root),
        "executionIds": execution_ids,
        "entityCount": len(entity_refs),
        "postCount": len(post_refs),
        "creatorCount": len(creator_refs),
        "canonicalMerkle": selected_merkle,
        "manifestDigest": payload_digest(final_root),
        "idempotent": True,
    }
    if environment_selection is not None:
        result.update({
            "selectionScope": environment_selection.selection_scope,
            "releaseMode": environment_selection.release_mode,
            "poolDigest": environment_selection.pool_digest,
            "poolEligibleCount": environment_selection.eligible_count,
            "counts": environment_selection.counts,
        })
        if environment_selection.environment is not None:
            result["targetEnvironment"] = environment_selection.environment
        if environment_selection.milestone is not None:
            result["milestone"] = environment_selection.milestone
            result["milestoneTargets"] = dict(
                environment_selection.milestone_targets or {}
            )
    return result


__all__ = ["reuse_existing_aggregate_release"]
