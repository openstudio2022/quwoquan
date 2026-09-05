"""Validate and reuse an existing immutable aggregate release."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from content.release.canonical.aggregate_release_closure import existing_refs
from content.release.canonical.aggregate_release_documents import (
    assert_holdings_reachable,
    release_attestation_document,
    release_header_document,
)
from content.release.canonical.environment_release_candidate import EnvironmentReleaseSelection
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
    assert_environment_neutral,
)
from content.release.canonical.release_attestation import ReleaseAttestation
from content.release.canonical.release_header import validate_release_header
from content.release.canonical.release_uat_sample_plan import (
    PLAN_REF as UAT_SAMPLE_PLAN_REF,
)
from content.release.canonical.release_uat_sample_plan import (
    build_release_uat_sample_plan,
    exact_document_sha256,
    validate_release_uat_sample_plan,
)
from content.release.canonical.release_uat_sampling_authority import (
    load_release_uat_sampling_authority,
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


def validate_existing_release_uat_sample_plan(
    *,
    final_root: Path,
    release_id: str,
    milestone: str | None,
    pool_digest: str,
    source_identity_set_digest: str,
    canonical_merkle: str,
    release_contents: Sequence[Mapping[str, object]],
    entity_refs: Sequence[str],
    release_objects_root: Path,
    eligible_population_counts: Mapping[str, int],
    sampling_authority_artifact_root: Path | None = None,
    sampling_authority_binding: Mapping[str, str] | None = None,
) -> str:
    """Strictly recompute and validate the sealed release UAT plan."""
    sample_path = payload_file(final_root, UAT_SAMPLE_PLAN_REF)
    existing_plan = _read_json(sample_path)
    sampling_authority: Mapping[str, Any] | None = None
    if milestone == "M1000":
        if (
            sampling_authority_artifact_root is None
            or sampling_authority_binding is None
        ):
            raise ObjectTransactionError(
                "DATA.RELEASE.UAT_SAMPLE_AUTHORITY_MISSING: M1000 existing release "
                "reuse requires projected authority exact ref+digest"
            )
        sampling_authority = load_release_uat_sampling_authority(
            artifact_root=sampling_authority_artifact_root,
            authority_binding=sampling_authority_binding,
            release_id=release_id,
            release_digest=str(existing_plan.get("releaseDigest") or ""),
        )
    elif (
        sampling_authority_artifact_root is not None
        or sampling_authority_binding is not None
    ):
        raise ObjectTransactionError(
            "DATA.RELEASE.UAT_SAMPLE_AUTHORITY_UNEXPECTED: projected authority "
            "inputs apply only to M1000"
        )
    expected_plan = build_release_uat_sample_plan(
        release_id=release_id,
        milestone=milestone,
        pool_digest=pool_digest,
        source_identity_set_digest=source_identity_set_digest,
        canonical_merkle=canonical_merkle,
        release_contents=release_contents,
        entity_refs=entity_refs,
        release_objects_root=release_objects_root,
        eligible_population_counts=eligible_population_counts,
        sampling_authority=sampling_authority,
    )
    validate_release_uat_sample_plan(
        existing_plan,
        release_contents=release_contents,
        entity_refs=entity_refs,
        release_objects_root=release_objects_root,
        expected_release_id=release_id,
        expected_milestone=milestone,
        expected_selection_evidence=expected_plan["selectionEvidence"],
    )
    if existing_plan != expected_plan:
        raise ObjectTransactionError("existing release UAT sample plan drifted")
    actual_digest = "sha256:" + hashlib.sha256(sample_path.read_bytes()).hexdigest()
    if actual_digest != exact_document_sha256(expected_plan):
        raise ObjectTransactionError(
            "existing release UAT sample plan bytes drifted"
        )
    return actual_digest


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
    environment_selection: EnvironmentReleaseSelection | None,
    release_contents: list[dict[str, object]] | None,
    release_authors: list[dict[str, object]] | None,
    milestone: str | None,
    milestone_targets: Mapping[str, int] | None,
    source_identities: tuple[dict[str, object], ...],
    source_identity_set_digest: str | None,
    sample_source_identity_set_digest: str | None,
    build_release_asset_admission_fn: Callable[..., dict[str, Any]],
    build_release_media_manifest_fn: Callable[..., dict[str, Any]],
    scan_release_contract_fn: Callable[..., dict[str, Any]],
    sampling_authority_artifact_root: Path | None = None,
    sampling_authority_binding: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Recompute every create-once invariant before returning idempotently."""
    entity_refs = set(desired["entities"])
    post_refs = set(desired["posts"])
    creator_refs = list(desired["creators"])
    tag_refs = list(desired["tags"])
    carrier_counts = {
        "homepage": len(entity_refs),
        "article": sum(ref.startswith("article/") for ref in post_refs),
        "image": sum(ref.startswith("image/") for ref in post_refs),
        "video": sum(ref.startswith("video/") for ref in post_refs),
    }
    carrier_counts["total"] = sum(carrier_counts.values())
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
        sample_plan_digest: str | None = None
        if environment_selection is not None and milestone is not None:
            sample_plan_digest = validate_existing_release_uat_sample_plan(
                final_root=final_root,
                release_id=release_id,
                milestone=milestone,
                pool_digest=environment_selection.pool_digest,
                source_identity_set_digest=(sample_source_identity_set_digest or ""),
                canonical_merkle=selected_merkle,
                release_contents=release_contents or [],
                entity_refs=desired["entities"],
                release_objects_root=payload_file(final_root, "objects"),
                eligible_population_counts={
                    **environment_selection.eligible_counts,
                    "homepage": max(
                        int(environment_selection.eligible_counts.get("homepage", 0)),
                        len(desired["entities"]),
                    ),
                },
                sampling_authority_artifact_root=(
                    sampling_authority_artifact_root
                ),
                sampling_authority_binding=sampling_authority_binding,
            )
        elif payload_file(final_root, UAT_SAMPLE_PLAN_REF).exists():
            raise ObjectTransactionError(
                "existing execution release carries UAT sample plan"
            )
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
            selection_scope=(
                environment_selection.selection_scope
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
            sample_plan_ref=(
                UAT_SAMPLE_PLAN_REF if sample_plan_digest is not None else None
            ),
            sample_plan_digest=sample_plan_digest,
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
        if True:
            expected_media_manifest = build_release_media_manifest_fn(
                release_id=release_id,
                post_refs=desired["posts"],
                entity_refs=desired["entities"],
                creator_refs=desired["creators"],
                publish_root=publish_root,
                release_class=release_class,
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
            carrier_counts=carrier_counts,
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
        "counts": carrier_counts,
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
        if environment_selection.milestone is not None:
            result["milestone"] = environment_selection.milestone
            result["milestoneTargets"] = dict(
                environment_selection.milestone_targets or {}
            )
        if sample_plan_digest is not None:
            result["samplePlanRef"] = UAT_SAMPLE_PLAN_REF
            result["samplePlanDigest"] = sample_plan_digest
    return result


__all__ = [
    "reuse_existing_aggregate_release",
    "validate_existing_release_uat_sample_plan",
]
