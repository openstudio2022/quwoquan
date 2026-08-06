"""Build immutable releases from exact execution publish closures."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.aggregate_release_closure import (
    OBJECT_KINDS,
    copy_tag_snapshot,
    execution_publish_closure,
    existing_refs,
    object_root,
    reference_closure,
)
from content.release.canonical.aggregate_release_documents import (
    release_attestation_document,
    release_header_document,
)
from content.release.canonical.creator_commercial_closure import (
    creator_commercial_closure_issues,
)
from content.release.canonical.object_transaction_audit import (
    validate_publish_invariants,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _copy_tree,
    _now,
    _read_json,
    _safe_id,
    _write_json,
    assert_environment_neutral,
)
from content.release.canonical.object_transaction_lock import (
    canonical_publish_serialized,
)
from content.release.canonical.release_admission import (
    build_release_asset_admission,
)
from content.release.canonical.release_attestation import ReleaseAttestation
from content.release.canonical.release_header import validate_release_header
from content.release.canonical.release_identity_incident import (
    canonical_release_identity_guard,
    release_output_root,
)
from content.release.canonical.reviewed_closure_aggregate import (
    ReviewedClosureSelection,
    copy_reviewed_closure_media,
    revalidate_reviewed_closure_selection,
    reviewed_closure_selection,
)
from content.release.environment.consistency import scan_release_contract
from content.release.model import DataSourceOwner
from core.media_asset_url import (
    build_release_media_manifest,
    copy_release_media_objects,
)
from core.release_layout import (
    attestation_root,
    object_closure_digest,
    payload_digest,
    payload_file,
    payload_root,
)
from core.release_media_binding import bind_release_object_media_assets
from core.schema import assert_valid
from core.source_digest import SourceDigestError, content_source_revision
from governance.coverage.distribution import (
    ProductLifecycleState,
    load_content_distribution_policy,
)


@canonical_publish_serialized
def _build_aggregate_release(
    *,
    publish_root: Path,
    release_root: Path,
    release_id: str,
    execution_ids: list[str],
    source_revision: str,
    entity_catalog_digest: str,
    reviewed_closure_adoption: Mapping[str, Any] | None = None,
    adoption_output_root: Path | None = None,
) -> dict[str, Any]:
    """Create one immutable release from canonical objects bound to execution IDs."""
    release_id = _safe_id(release_id, label="releaseId")
    reviewed_selection: ReviewedClosureSelection | None = None
    if reviewed_closure_adoption is not None:
        reviewed_selection = reviewed_closure_selection(
            release_id=release_id,
            execution_ids=execution_ids,
            source_revision=source_revision,
            entity_catalog_digest=entity_catalog_digest,
            reviewed_closure_adoption=reviewed_closure_adoption,
            output_root=adoption_output_root,
        )
        execution_ids = list(reviewed_selection.execution_ids)
        source_digests = (reviewed_selection.source_digest,)
        desired = reviewed_selection.desired
        object_source_root = reviewed_selection.object_root
    else:
        closures = tuple(
            execution_publish_closure(execution_id, publish_root=publish_root)
            for execution_id in execution_ids
        )
        execution_ids = sorted({closure.execution_id for closure in closures})
        if len(execution_ids) != len(closures):
            raise ObjectTransactionError("aggregate execution IDs are duplicated")
        source_digests = tuple(
            sorted(
                {closure.source_digest for closure in closures},
                key=lambda source_digest: source_digest.digest,
            )
        )
        entity_refs = {ref for closure in closures for ref in closure.entity_refs}
        post_refs = {ref for closure in closures for ref in closure.post_refs}
        if not entity_refs and not post_refs:
            raise ObjectTransactionError("aggregate release has no canonical object")
        canonical_closure = validate_publish_invariants(publish_root)
        if canonical_closure["status"] != "passed":
            raise ObjectTransactionError(
                "aggregate release canonical closure invalid: "
                + "; ".join(
                    f"{item['code']}:{item['ref']}"
                    for item in canonical_closure["issues"][:5]
                )
            )
        creator_refs, tag_refs = reference_closure(
            publish_root,
            entity_refs=entity_refs,
            post_refs=post_refs,
        )
        distribution_policy = load_content_distribution_policy()
        creator_issues = creator_commercial_closure_issues(
            publish_root,
            creator_refs=creator_refs,
            require_commercial_rights=(
                distribution_policy.product_lifecycle_state
                is ProductLifecycleState.COMMERCIAL
            ),
        )
        if creator_issues:
            raise ObjectTransactionError(
                "aggregate release creator commercial closure invalid: "
                + "; ".join(
                    f"{item['code']}:{item['ref']}" for item in creator_issues[:5]
                )
            )
        desired = {
            "creators": creator_refs,
            "entities": sorted(entity_refs),
            "posts": sorted(post_refs),
            "tags": tag_refs,
        }
        object_source_root = publish_root

    if len(source_digests) != 1:
        raise ObjectTransactionError(
            "aggregate release requires one frozen sourceDigest across all lanes"
        )
    source_digest = source_digests[0].digest
    try:
        expected_source_revision = content_source_revision(
            source_digest=source_digest,
            entity_catalog_digest=entity_catalog_digest,
        )
    except SourceDigestError as exc:
        raise ObjectTransactionError(str(exc)) from exc
    if source_revision != expected_source_revision:
        raise ObjectTransactionError(
            "aggregate release sourceRevision drift from "
            "sourceDigest/entityCatalogDigest"
        )
    source_digest_documents = [
        source_digest.to_document() for source_digest in source_digests
    ]
    entity_refs = set(desired["entities"])
    post_refs = set(desired["posts"])
    if not entity_refs and not post_refs:
        raise ObjectTransactionError("aggregate release has no canonical object")
    creator_refs = list(desired["creators"])
    tag_refs = list(desired["tags"])
    distribution_policy = load_content_distribution_policy()
    final_root = release_root / release_id
    if final_root.exists():
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

            asset_admission = _read_json(
                payload_file(final_root, "asset_admission.json")
            )
            assert_valid(
                asset_admission,
                "release",
                "release_asset_admission",
                label=f"release_asset_admission:{release_id}",
            )
            expected_asset_admission = build_release_asset_admission(
                release_id=release_id,
                objects_root=payload_file(final_root, "objects"),
                desired=desired,
                policy=distribution_policy,
            )
            assert_valid(
                expected_asset_admission,
                "release",
                "release_asset_admission",
                label=f"expected_release_asset_admission:{release_id}",
            )
            if asset_admission != expected_asset_admission:
                raise ObjectTransactionError(
                    "existing release asset admission drifted"
                )

            selected_merkle = object_closure_digest(final_root)
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
                release_class=distribution_policy.release_class.value,
                product_lifecycle_state=(
                    distribution_policy.product_lifecycle_state.value
                ),
                reviewed_closure_adoption=reviewed_closure_adoption,
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

            media_manifest = _read_json(
                payload_file(final_root, "media_manifest.json")
            )
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
                if selected_merkle != object_closure_digest(
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
                expected_media_manifest = build_release_media_manifest(
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

            consistency = scan_release_contract(
                expected_desired_state,
                release_root=final_root,
                phase="preflight",
            )
            if consistency["status"] != "passed":
                raise ObjectTransactionError(
                    "existing release consistency closure drifted"
                )
            assert_environment_neutral(final_root)

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
                distribution_policy=distribution_policy,
            )
            if aggregate != expected_attestation:
                raise ObjectTransactionError(
                    "existing release attestation drifted"
                )
        except Exception as exc:
            raise ObjectTransactionError(
                f"aggregate release create-once conflict: {final_root}"
            ) from exc
        return {
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

    final_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{release_id}.", dir=final_root.parent))
    try:
        payload = payload_root(staging)
        for kind in OBJECT_KINDS:
            for ref in desired[kind]:
                source = object_root(object_source_root, kind, ref)
                target = payload / "objects" / kind / ref
                if kind == "tags":
                    copy_tag_snapshot(source, target)
                else:
                    _copy_tree(source, target)
        if reviewed_selection is not None:
            media_manifest = {
                **reviewed_selection.media_manifest,
                "releaseId": release_id,
                "sourceOwner": DataSourceOwner.QWQ_DATA,
            }
            assert_valid(
                media_manifest,
                "release",
                "media_manifest",
                label=f"release_media_manifest:{release_id}",
            )
        else:
            media_manifest = build_release_media_manifest(
                release_id=release_id,
                post_refs=desired["posts"],
                entity_refs=desired["entities"],
                creator_refs=desired["creators"],
                publish_root=publish_root,
            )
            if media_manifest["issues"]:
                raise ObjectTransactionError(
                    "aggregate release media closure invalid: "
                    + "; ".join(
                        str(issue) for issue in media_manifest["issues"][:5]
                    )
                )
            bind_release_object_media_assets(
                objects_root=payload / "objects",
                manifest=media_manifest,
            )
        asset_admission = build_release_asset_admission(
            release_id=release_id,
            objects_root=payload / "objects",
            desired=desired,
            policy=distribution_policy,
        )
        assert_valid(
            asset_admission,
            "release",
            "release_asset_admission",
            label=f"release_asset_admission:{release_id}",
        )
        _write_json(payload / "asset_admission.json", asset_admission)
        selected_merkle = object_closure_digest(staging, create=True)
        if (
            reviewed_selection is not None
            and selected_merkle
            != object_closure_digest(reviewed_selection.source_release_root)
        ):
            raise ObjectTransactionError(
                "reviewed closure adoption object bytes changed during aggregation"
            )
        release_header = release_header_document(
            release_id=release_id,
            execution_ids=execution_ids,
            source_revision=source_revision,
            source_digest=source_digest,
            entity_catalog_digest=entity_catalog_digest,
            source_digest_documents=source_digest_documents,
            asset_admission=asset_admission,
            canonical_merkle=selected_merkle,
            release_class=distribution_policy.release_class.value,
            product_lifecycle_state=(
                distribution_policy.product_lifecycle_state.value
            ),
            reviewed_closure_adoption=reviewed_closure_adoption,
        )
        desired_state = {
            "schema": "quwoquan_data.release_desired_state",
            "releaseId": release_id,
            "desiredRefs": desired,
        }
        validate_release_header(
            release_header,
            label=f"release_header:{release_id}",
        )
        assert_valid(
            desired_state,
            "release",
            "release_desired_state",
            label=f"release_desired_state:{release_id}",
        )
        _write_json(payload / "release.json", release_header)
        _write_json(payload / "desired_state.json", desired_state)
        _write_json(
            payload / "index/objects.json",
            {"schema": "quwoquan_data.release_object_index", **desired},
        )
        _write_json(
            payload / "sample_bundle.json",
            {"schema": "quwoquan_data.release_sample_bundle", **desired},
        )
        if reviewed_selection is not None:
            copy_reviewed_closure_media(
                source_release_root=reviewed_selection.source_release_root,
                target_release_root=staging,
                media_manifest=media_manifest,
            )
        else:
            copy_release_media_objects(
                manifest=media_manifest,
                source_root=publish_root,
                release_root=staging,
            )
        _write_json(payload / "media_manifest.json", media_manifest)
        consistency = scan_release_contract(
            {
                "schema": "quwoquan_data.release_desired_state",
                "releaseId": release_id,
                "desiredRefs": desired,
            },
            release_root=staging,
            phase="preflight",
        )
        if consistency["status"] != "passed":
            raise ObjectTransactionError(
                "aggregate release consistency invalid: "
                + "; ".join(
                    f"{item['code']}:{item['ref']}"
                    for item in consistency["blockingIssues"][:5]
                )
            )
        release_attestation = release_attestation_document(
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
            payload_sha256=payload_digest(staging),
            recorded_at=_now(),
            distribution_policy=distribution_policy,
        )
        assert_valid(
            release_attestation,
            "release",
            "release_attestation",
            label=f"release_attestation:{release_id}",
        )
        _write_json(attestation_root(staging) / "release.json", release_attestation)
        if reviewed_selection is not None:
            revalidate_reviewed_closure_selection(
                reviewed_closure_adoption=reviewed_closure_adoption,
                output_root=adoption_output_root,
                selection=reviewed_selection,
            )
        assert_environment_neutral(staging)
        staging.replace(final_root)
        return {
            "schema": "quwoquan_data.aggregate_release_result",
            "releaseId": release_id,
            "releaseRoot": str(final_root),
            "executionIds": execution_ids,
            "entityCount": len(entity_refs),
            "postCount": len(post_refs),
            "creatorCount": len(creator_refs),
            "canonicalMerkle": selected_merkle,
            "manifestDigest": payload_digest(final_root),
            "idempotent": False,
        }
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def build_aggregate_release(
    *,
    publish_root: Path,
    release_root: Path,
    release_id: str,
    execution_ids: list[str],
    source_revision: str,
    entity_catalog_digest: str,
    reviewed_closure_adoption: Mapping[str, Any] | None = None,
    adoption_output_root: Path | None = None,
) -> dict[str, Any]:
    """Guard the canonical release identity across create-once/reuse."""

    with canonical_release_identity_guard(
        output_root=release_output_root(release_root),
        release_id=release_id,
    ):
        return _build_aggregate_release(
            publish_root=publish_root,
            release_root=release_root,
            release_id=release_id,
            execution_ids=execution_ids,
            source_revision=source_revision,
            entity_catalog_digest=entity_catalog_digest,
            reviewed_closure_adoption=reviewed_closure_adoption,
            adoption_output_root=adoption_output_root,
        )
