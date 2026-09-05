"""Internal immutable aggregate release assembler."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from content.release.canonical.aggregate_release_closure import (
    OBJECT_KINDS,
    copy_release_tag_snapshot,
    object_root,
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
from content.release.canonical.release_consistency import scan_release_contract
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

@canonical_publish_serialized
def _build_aggregate_release(
    *,
    publish_root: Path,
    release_root: Path,
    release_id: str,
    release_class: str,
    cohort: dict[str, object],
) -> dict[str, Any]:
    """Create one immutable release from canonical objects bound to execution IDs."""
    release_id = _safe_id(release_id, label="releaseId")
    release_mode = str(release_class or "").strip()
    if release_mode not in {"research", "commercial"}:
        raise ObjectTransactionError(f"DATA.RELEASE.CLASS_INVALID: {release_mode!r}")
    if not cohort:
        raise ObjectTransactionError(
            "DATA.RELEASE.COHORT_REQUIRED: pool release requires --cohort-file"
        )
    pool_preparation = prepare_pool_release(
        publish_root=publish_root,
        cohort=cohort,
        release_class=release_class,
    )
    pool_excluded = pool_preparation.excluded
    cohort_selection = pool_preparation.environment_selection
    execution_ids = pool_preparation.execution_ids
    source_digests = pool_preparation.source_digests
    source_identities = pool_preparation.source_identities
    source_identity_set_digest = pool_preparation.source_identity_set_digest
    entity_catalog_digest = pool_preparation.entity_catalog_digest
    source_revision = pool_preparation.source_revision
    desired = pool_preparation.desired
    object_source_root = publish_root


    source_digest: str | None = None
    source_digest_documents = [
        source_digest.to_document() for source_digest in source_digests
    ]
    entity_refs = set(desired["entities"])
    post_refs = set(desired["posts"])
    carrier_counts = {
        "homepage": len(entity_refs),
        "article": sum(ref.startswith("article/") for ref in post_refs),
        "image": sum(ref.startswith("image/") for ref in post_refs),
        "video": sum(ref.startswith("video/") for ref in post_refs),
    }
    carrier_counts["total"] = sum(carrier_counts.values())
    if not entity_refs and not post_refs:
        raise ObjectTransactionError("aggregate release has no canonical object")
    creator_refs = list(desired["creators"])
    tag_refs = list(desired["tags"])
    release_contents = build_release_contents(cohort_selection)
    release_authors = build_release_authors(
        object_source_root,
        creator_refs=creator_refs,
        strict_admission=True,
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
            cohort_selection=cohort_selection,
            release_contents=release_contents,
            release_authors=release_authors,
            milestone=cohort_selection.milestone,
            milestone_targets=cohort_selection.milestone_targets,
            source_identities=source_identities,
            source_identity_set_digest=source_identity_set_digest,
            build_release_asset_admission_fn=build_release_asset_admission,
            build_release_media_manifest_fn=build_release_media_manifest,
            scan_release_contract_fn=scan_release_contract,
        )
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
                    copy_release_tag_snapshot(
                        publish_root,
                        tag_ref=ref,
                        target=target,
                        control_plane_taxonomy_root=CONTROL_PLANE_TAXONOMY_ROOT,
                    )
                else:
                    _copy_tree(source, target)
        media_manifest = build_release_media_manifest(
            release_id=release_id,
            post_refs=desired["posts"],
            entity_refs=desired["entities"],
            creator_refs=desired["creators"],
            publish_root=publish_root,
            release_class=release_mode,
        )
        if media_manifest["issues"]:
            raise ObjectTransactionError(
                "aggregate release media closure invalid: "
                + "; ".join(str(issue) for issue in media_manifest["issues"][:5])
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
            pool_digest=cohort_selection.pool_digest,
            counts=carrier_counts,
            contents=release_contents,
            authors=release_authors,
            milestone=cohort_selection.milestone,
            milestone_targets=cohort_selection.milestone_targets,
            source_identities=list(source_identities),
            source_identity_set_digest=source_identity_set_digest,
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
            carrier_counts=carrier_counts,
            entity_count=len(entity_refs),
            post_count=len(post_refs),
            creator_count=len(creator_refs),
            tag_count=len(tag_refs),
            payload_sha256=payload_digest(staging),
            recorded_at=_now(),
            release_class=release_mode,
            source_identities=source_identities,
            source_identity_set_digest=(
                source_identity_set_digest
            ),
        )
        assert_valid(
            release_attestation,
            "release",
            "release_attestation",
            label=f"release_attestation:{release_id}",
        )
        _write_json(attestation_root(staging) / "release.json", release_attestation)
        assert_environment_neutral(staging)
        staging.replace(final_root)
        return aggregate_release_result(
            release_id=release_id,
            release_root=str(final_root),
            execution_ids=execution_ids,
            entity_count=len(entity_refs),
            post_count=len(post_refs),
            creator_count=len(creator_refs),
            carrier_counts=carrier_counts,
            canonical_merkle=selected_merkle,
            manifest_digest=payload_digest(final_root),
            cohort_selection=cohort_selection,
            excluded=pool_excluded,
        )
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


__all__ = ["_build_aggregate_release"]
