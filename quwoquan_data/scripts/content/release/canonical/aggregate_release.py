"""Build immutable releases from exact execution publish closures."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.aggregate_release_closure import (
    OBJECT_KINDS,
    copy_release_tag_snapshot,
    copy_tag_snapshot,
    execution_publish_closure,
    object_root,
    reference_closure,
)
from content.release.canonical.aggregate_release_documents import (
    release_attestation_document,
    release_desired_state_document,
    release_header_document,
)
from content.release.canonical.aggregate_release_existing import (
    reuse_existing_aggregate_release,
)
from content.release.canonical.aggregate_release_pool import (
    prepare_pool_release,
)
from content.release.canonical.aggregate_release_pool import (
    release_authors as build_release_authors,
)
from content.release.canonical.aggregate_release_pool import (
    release_contents as build_release_contents,
)
from content.release.canonical.aggregate_release_result import (
    aggregate_release_result,
)
from content.release.canonical.creator_avatar_quality import (
    creator_avatar_quality_issues,
)
from content.release.canonical.environment_release_selection import (
    EnvironmentReleaseSelection,
    select_environment_release_posts,
)
from content.release.canonical.object_transaction_audit import (
    validate_publish_invariants,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _copy_tree,
    _now,
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
from core.paths import CONTROL_PLANE_TAXONOMY_ROOT
from core.release_layout import (
    attestation_root,
    objects_merkle,
    payload_digest,
    payload_root,
)
from core.release_media_binding import bind_release_object_media_assets
from core.schema import assert_valid
from core.source_digest import (
    SourceDigestError,
    content_source_revision,
)


@canonical_publish_serialized
def _build_aggregate_release(
    *,
    publish_root: Path,
    release_root: Path,
    release_id: str,
    execution_ids: list[str],
    source_revision: str | None,
    entity_catalog_digest: str | None,
    reviewed_closure_adoption: Mapping[str, Any] | None = None,
    adoption_output_root: Path | None = None,
    target_environment: str | None = None,
    milestone: str | None = None,
    release_class: str,
    pool_wide: bool = False,
) -> dict[str, Any]:
    """Create one immutable release from canonical objects bound to execution IDs."""
    release_id = _safe_id(release_id, label="releaseId")
    release_mode = str(release_class or "").strip()
    if release_mode not in {"research", "commercial"}:
        raise ObjectTransactionError(f"DATA.RELEASE.CLASS_INVALID: {release_mode!r}")
    reviewed_selection: ReviewedClosureSelection | None = None
    environment_selection: EnvironmentReleaseSelection | None = None
    source_identities: tuple[dict[str, object], ...] = ()
    source_identity_set_digest: str | None = None
    pool_excluded: tuple[dict[str, str], ...] = ()
    if pool_wide:
        if reviewed_closure_adoption is not None:
            raise ObjectTransactionError(
                "pool release cannot be combined with reviewed-closure adoption"
            )
        if (target_environment is None) == (milestone is None):
            raise ObjectTransactionError(
                "DATA.RELEASE.SELECTION_INVALID: pool release requires exactly one "
                "target environment or milestone"
            )
        pool_preparation = prepare_pool_release(
            publish_root=publish_root,
            target_environment=target_environment,
            milestone=milestone,
            release_class=release_class,
        )
        pool_excluded = pool_preparation.excluded
        environment_selection = pool_preparation.environment_selection
        execution_ids = pool_preparation.execution_ids
        source_digests = pool_preparation.source_digests
        source_identities = pool_preparation.source_identities
        source_identity_set_digest = (
            pool_preparation.source_identity_set_digest
        )
        entity_catalog_digest = pool_preparation.entity_catalog_digest
        source_revision = pool_preparation.source_revision
        desired = pool_preparation.desired
        object_source_root = publish_root
    elif reviewed_closure_adoption is not None:
        if target_environment is not None:
            raise ObjectTransactionError(
                "environment selection cannot be combined with reviewed-closure adoption"
            )
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
        if target_environment is not None:
            environment_selection = select_environment_release_posts(
                publish_root=publish_root,
                post_refs=sorted(post_refs),
                environment=target_environment,
                release_class=release_mode,
            )
            post_refs = set(environment_selection.post_refs)
        creator_refs, tag_refs = reference_closure(
            publish_root,
            entity_refs=entity_refs,
            post_refs=post_refs,
        )
        creator_issues = creator_avatar_quality_issues(
            publish_root,
            creator_refs=creator_refs,
        )
        if creator_issues:
            raise ObjectTransactionError(
                "aggregate release creator avatar quality closure invalid: "
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

    source_identity_set_mode = bool(pool_wide)
    if source_identity_set_mode:
        if (
            environment_selection is None
            or not source_identities
            or source_identity_set_digest is None
        ):
            raise ObjectTransactionError(
                "DATA.POOL.SOURCE_IDENTITY_MISSING: pool release"
            )
        source_digest: str | None = None
    else:
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
        except (SourceDigestError, TypeError) as exc:
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
    release_contents = build_release_contents(environment_selection)
    release_authors = (
        build_release_authors(
            object_source_root,
            creator_refs=creator_refs,
            strict_admission=pool_wide,
        )
        if environment_selection is not None
        else None
    )
    final_root = release_root / release_id
    if final_root.exists():
        existing = reuse_existing_aggregate_release(
            publish_root=publish_root,
            final_root=final_root,
            release_id=release_id,
            execution_ids=execution_ids,
            source_revision=source_revision,
            source_digest=source_digest,
            entity_catalog_digest=entity_catalog_digest,
            source_digest_documents=source_digest_documents,
            source_digests=source_digests,
            desired=desired,
            release_class=release_mode,
            reviewed_closure_adoption=reviewed_closure_adoption,
            adoption_output_root=adoption_output_root,
            reviewed_selection=reviewed_selection,
            environment_selection=environment_selection,
            release_contents=release_contents,
            release_authors=release_authors,
            milestone=(
                environment_selection.milestone
                if environment_selection is not None
                else None
            ),
            milestone_targets=(
                environment_selection.milestone_targets
                if environment_selection is not None
                else None
            ),
            source_identities=source_identities,
            source_identity_set_digest=source_identity_set_digest,
            build_release_asset_admission_fn=build_release_asset_admission,
            build_release_media_manifest_fn=build_release_media_manifest,
            scan_release_contract_fn=scan_release_contract,
        )
        if pool_wide:
            existing["excluded"] = list(pool_excluded)
            existing["excludedCount"] = len(pool_excluded)
        return existing

    final_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{release_id}.", dir=final_root.parent))
    try:
        payload = payload_root(staging)
        for kind in OBJECT_KINDS:
            for ref in desired[kind]:
                source = object_root(object_source_root, kind, ref)
                target = payload / "objects" / kind / ref
                if kind == "tags":
                    if pool_wide:
                        copy_release_tag_snapshot(
                            publish_root,
                            tag_ref=ref,
                            target=target,
                            control_plane_taxonomy_root=(CONTROL_PLANE_TAXONOMY_ROOT),
                        )
                    else:
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
            release_class=release_mode,
        )
        assert_valid(
            asset_admission,
            "release",
            "release_asset_admission",
            label=f"release_asset_admission:{release_id}",
        )
        _write_json(payload / "asset_admission.json", asset_admission)
        selected_merkle = objects_merkle(staging, create=True)
        if (
            reviewed_selection is not None
            and selected_merkle
            != objects_merkle(reviewed_selection.source_release_root)
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
            release_class=release_mode,
            product_lifecycle_state=release_mode,
            reviewed_closure_adoption=reviewed_closure_adoption,
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
            milestone=(
                environment_selection.milestone
                if environment_selection is not None
                else None
            ),
            milestone_targets=(
                environment_selection.milestone_targets
                if environment_selection is not None
                else None
            ),
            source_identities=(
                list(source_identities) if source_identity_set_mode else None
            ),
            source_identity_set_digest=(
                source_identity_set_digest if source_identity_set_mode else None
            ),
        )
        desired_state = release_desired_state_document(
            release_id=release_id,
            desired=desired,
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
            release_class=release_mode,
            source_identities=(
                source_identities if source_identity_set_mode else ()
            ),
            source_identity_set_digest=(
                source_identity_set_digest if source_identity_set_mode else None
            ),
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
        return aggregate_release_result(
            release_id=release_id,
            release_root=str(final_root),
            execution_ids=execution_ids,
            entity_count=len(entity_refs),
            post_count=len(post_refs),
            creator_count=len(creator_refs),
            canonical_merkle=selected_merkle,
            manifest_digest=payload_digest(final_root),
            environment_selection=environment_selection,
            excluded=pool_excluded,
            pool_wide=pool_wide,
        )
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
    release_class: str,
    reviewed_closure_adoption: Mapping[str, Any] | None = None,
    adoption_output_root: Path | None = None,
    target_environment: str | None = None,
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
            release_class=release_class,
            reviewed_closure_adoption=reviewed_closure_adoption,
            adoption_output_root=adoption_output_root,
            target_environment=target_environment,
        )


def build_pool_release(
    *,
    publish_root: Path,
    release_root: Path,
    release_id: str,
    target_environment: str | None = None,
    milestone: str | None = None,
    release_class: str,
) -> dict[str, Any]:
    """Build one immutable environment release from the whole admitted pool."""

    with canonical_release_identity_guard(
        output_root=release_output_root(release_root),
        release_id=release_id,
    ):
        return _build_aggregate_release(
            publish_root=publish_root,
            release_root=release_root,
            release_id=release_id,
            execution_ids=[],
            source_revision="",
            entity_catalog_digest="",
            target_environment=target_environment,
            milestone=milestone,
            release_class=release_class,
            pool_wide=True,
        )


__all__ = ["build_aggregate_release", "build_pool_release"]
