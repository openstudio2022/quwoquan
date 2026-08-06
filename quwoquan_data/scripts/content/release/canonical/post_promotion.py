"""Atomically promote every approved post in one execution to canonical publish."""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path

from content.execution.workspace import execution_root, write_publish_ref
from content.release.canonical.application import apply_object_transaction
from content.release.canonical.canonical_inventory import (
    assert_canonical_image_unique,
    load_or_bootstrap_inventory,
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


def _qualified_post_refs(execution_id: str) -> tuple[str, ...]:
    from content.execution.post_review_closure import (
        indexed_post_targets,
        load_post_review_closure,
    )

    closure = load_post_review_closure(
        execution_id,
        expected_object_targets=indexed_post_targets(execution_id),
        require_quota_milestone=False,
    )
    refs = tuple(
        publish_ref.removeprefix("posts/")
        for publish_ref in closure.qualified_publish_refs
    )
    if not refs:
        raise ObjectTransactionError(
            "post review closure has no qualified posts for canonical promotion"
        )
    return refs


@canonical_publish_serialized
def promote_post_object(execution_id: str, post_ref: str) -> dict[str, str]:
    """Atomically promote one reviewed post and return fenced result evidence."""
    root = execution_root(execution_id)
    normalized_ref = str(post_ref or "").strip().strip("/")
    if normalized_ref.startswith("posts/"):
        normalized_ref = normalized_ref.removeprefix("posts/")
    if len(normalized_ref.split("/")) < 4:
        raise ObjectTransactionError(f"post objectRef is invalid: {post_ref!r}")
    if normalized_ref not in set(_qualified_post_refs(execution_id)):
        raise ObjectTransactionError(
            f"post is discarded by the post review closure: {normalized_ref}"
        )
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
    _assert_cross_publish_image_unique(
        package_root=package_root,
        canonical_post=canonical_post,
    )
    package_merkle = tree_integrity_stats(package_root / "object")["merkleRoot"]
    canonical_ready = (canonical_post / "manifest.json").is_file()
    if canonical_ready:
        canonical_merkle = tree_integrity_stats(canonical_post)["merkleRoot"]
        if canonical_merkle != package_merkle:
            raise ObjectTransactionError(
                f"completed post transaction canonical object drift: {normalized_ref}"
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
    }


def promote_execution_posts(execution_id: str) -> tuple[str, ...]:
    from content.execution.spec_contract import approved_quota

    refs = _qualified_post_refs(execution_id)
    promoted: list[str] = []
    failures: list[str] = []
    for post_ref in refs:
        canonical_post = PUBLISH_ROOT / "posts" / post_ref
        try:
            promote_post_object(execution_id, post_ref)
            promoted.append(post_ref)
        except ObjectTransactionError as exc:
            # A single non-promotable qualified ref must not unwind peers that
            # already landed in canonical publish and already satisfy quota.
            if (canonical_post / "manifest.json").is_file():
                promoted.append(post_ref)
                continue
            failures.append(f"{post_ref}: {exc}")
    required = approved_quota(execution_id)
    if len(promoted) < required:
        raise ObjectTransactionError(
            "canonical post promotion below quota: "
            f"promoted={len(promoted)} required={required}; "
            + "; ".join(failures[:5])
        )
    write_publish_ref(execution_id, post_refs=promoted)
    return tuple(promoted)


__all__ = ["promote_execution_posts", "promote_post_object"]
