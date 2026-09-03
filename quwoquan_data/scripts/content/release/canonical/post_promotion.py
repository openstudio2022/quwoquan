"""Atomically promote every approved post in one execution to canonical publish."""
from __future__ import annotations

import hashlib
from pathlib import Path
from collections.abc import Mapping

from content.execution.workspace import execution_root
from content.release.canonical.application import apply_object_transaction
from content.release.canonical.canonical_inventory import (
    assert_canonical_image_unique,
    assert_canonical_video_unique,
    load_or_bootstrap_inventory,
)
from content.release.canonical.content_pool_record import (
    append_pool_record,
    build_canonical_pool_record,
    is_pool_record_admitted,
    iter_pool_records,
    latest_pool_record,
    pool_payload_digest,
)
from content.release.canonical.object_transaction_audit import audit_object_transaction
from content.release.canonical.object_transaction_contract import ObjectTransactionError
from content.release.canonical.object_transaction_lock import (
    canonical_publish_serialized,
)
from content.release.canonical.post_transaction import (
    build_post_object_transaction_package,
)
from core.io import read_json
from core.paths import OUTPUT_ROOT, PUBLISH_ROOT
from core.tree_integrity import tree_integrity_stats


def repair_applied_post_pool_record_drift(
    *,
    package_root: Path,
    canonical_post: Path,
    canonical_ref: str,
) -> bool:
    """Append one governed readback repair after an exact applied object upgrade."""

    package_object = package_root / "object"
    if pool_payload_digest(package_object) != pool_payload_digest(canonical_post):
        raise ObjectTransactionError(
            f"completed post transaction canonical object drift: {canonical_ref}"
        )
    try:
        record = latest_pool_record(canonical_post, "content")
    except ObjectTransactionError as exc:
        if str(exc) != "DATA.POOL.PAYLOAD_DIGEST_DRIFT":
            raise
        package_records = iter_pool_records(package_object, object_type="content")
        canonical_records = iter_pool_records(canonical_post, object_type="content")
        if canonical_records != package_records or not canonical_records:
            raise ObjectTransactionError(
                "DATA.POOL.PAYLOAD_DIGEST_DRIFT: transaction record lineage drift"
            ) from exc
        repaired = build_canonical_pool_record(
            object_root=canonical_post,
            object_type="content",
            object_ref=canonical_ref,
        )
        append_pool_record(object_root=canonical_post, record=repaired)
        return True
    if not is_pool_record_admitted(record):
        raise ObjectTransactionError("DATA.POOL.OBJECT_NOT_ADMITTED")
    return False


def _assert_cross_publish_image_unique(
    *,
    package_root: Path,
    canonical_post: Path,
) -> None:
    """Reject exact or perceptually duplicated images across canonical posts."""

    package_manifest = read_json(package_root / "object/manifest.json")
    if not isinstance(package_manifest, Mapping):
        raise ObjectTransactionError("post transaction manifest must be an object")
    try:
        excluded = canonical_post.relative_to(PUBLISH_ROOT).as_posix()
    except ValueError as exc:
        raise ObjectTransactionError(
            "canonical post is outside the publish root"
        ) from exc
    assert_canonical_image_unique(
        publish_root=PUBLISH_ROOT,
        manifest=package_manifest,
        excluded_manifest_path=f"{excluded}/manifest.json",
    )


def _assert_cross_publish_video_unique(
    *,
    package_root: Path,
    canonical_post: Path,
) -> None:
    """Reject exact video-content or poster reuse across canonical posts."""

    package_manifest = read_json(package_root / "object/manifest.json")
    if not isinstance(package_manifest, Mapping):
        raise ObjectTransactionError("post transaction manifest must be an object")
    if str(package_manifest.get("contentType") or "").strip() != "video":
        return
    try:
        excluded = canonical_post.relative_to(PUBLISH_ROOT).as_posix()
    except ValueError as exc:
        raise ObjectTransactionError(
            "canonical post is outside the publish root"
        ) from exc
    assert_canonical_video_unique(
        publish_root=PUBLISH_ROOT,
        manifest=package_manifest,
        excluded_manifest_path=f"{excluded}/manifest.json",
    )


@canonical_publish_serialized
def promote_post_object(
    execution_id: str,
    post_ref: str,
) -> dict[str, str]:
    """Atomically promote one explicitly selected, review-approved post."""
    root = execution_root(execution_id)
    normalized_ref = str(post_ref or "").strip().strip("/")
    if normalized_ref.startswith("posts/"):
        normalized_ref = normalized_ref.removeprefix("posts/")
    if len(normalized_ref.split("/")) < 4:
        raise ObjectTransactionError(f"post objectRef is invalid: {post_ref!r}")
    post_root = root / "posts" / normalized_ref
    attestation_path = post_root / "5.review/attestation.json"
    if not attestation_path.is_file() or not (post_root / "manifest.json").is_file():
        raise ObjectTransactionError(
            f"post is not materialized and reviewed: {normalized_ref}"
        )
    attestation = read_json(attestation_path)
    if not isinstance(attestation, dict) or attestation.get("decision") != "approved":
        raise ObjectTransactionError(f"post is not review-approved: {normalized_ref}")
    transaction_id = (
        f"{execution_id}--post-"
        f"{hashlib.sha256(normalized_ref.encode('utf-8')).hexdigest()[:12]}"
    )
    package_root = root / "evidence/object-transactions" / transaction_id
    apply_report = (
        OUTPUT_ROOT
        / "data/local/workspace/object-transactions"
        / transaction_id
        / "apply_report.json"
    )
    canonical_post = PUBLISH_ROOT / "posts" / normalized_ref
    build_post_object_transaction_package(
        execution_root=root,
        object_ref=normalized_ref,
        transaction_id=transaction_id,
        package_root=package_root,
    )
    _assert_cross_publish_video_unique(
        package_root=package_root,
        canonical_post=canonical_post,
    )
    _assert_cross_publish_image_unique(
        package_root=package_root,
        canonical_post=canonical_post,
    )
    canonical_ready = (canonical_post / "manifest.json").is_file()
    if canonical_ready:
        repair_applied_post_pool_record_drift(
            package_root=package_root,
            canonical_post=canonical_post,
            canonical_ref=normalized_ref,
        )
        # Idempotent resume: fleet/publish may have written the canonical object
        # before apply_report landed under OUTPUT_ROOT. Matching merkle is enough.
        applied = (
            read_json(apply_report)
            if apply_report.is_file()
            else {
                "objectClosureDigest": "",
                "idempotent": True,
            }
        )
    else:
        audit = audit_object_transaction(
            publish_root=PUBLISH_ROOT,
            output_root=OUTPUT_ROOT,
            package_root=package_root,
            transaction_id=transaction_id,
            expected_canonical_merkle=load_or_bootstrap_inventory(PUBLISH_ROOT)[
                "stats"
            ]["merkleRoot"],
        )
        applied = apply_object_transaction(
            publish_root=PUBLISH_ROOT,
            output_root=OUTPUT_ROOT,
            package_root=package_root,
            transaction_id=transaction_id,
            dry_run_attestation_sha256=str(audit["dryRunAttestationSha256"]),
        )
    return {
        "transactionId": transaction_id,
        "applyReportRef": apply_report.relative_to(OUTPUT_ROOT).as_posix(),
        "canonicalObjectRef": f"posts/{normalized_ref}",
        "canonicalObjectSha256": str(
            tree_integrity_stats(canonical_post)["merkleRoot"]
        ),
        "objectClosureDigest": str(applied.get("objectClosureDigest") or ""),
        "admissionResult": "replayed" if canonical_ready else "appended",
    }



__all__ = ["promote_post_object", "repair_applied_post_pool_record_drift"]
