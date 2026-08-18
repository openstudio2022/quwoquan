"""Atomically promote every approved post in one execution to canonical publish."""
from __future__ import annotations

import hashlib
from pathlib import Path

from core.paths import OUTPUT_ROOT, PUBLISH_ROOT
from core.tree_integrity import tree_integrity_stats
from content.execution.workspace import execution_root, write_publish_ref
from content.release.canonical.application import apply_object_transaction
from content.release.canonical.object_transaction_audit import (
    audit_object_transaction,
    validate_canonical_publish,
)
from content.release.canonical.post_transaction import (
    build_post_object_transaction_package,
)
from content.release.canonical.object_transaction_contract import ObjectTransactionError
from content.release.canonical.object_transaction_lock import (
    canonical_publish_serialized,
)


def _approved_post_refs(root: Path) -> tuple[str, ...]:
    refs: list[str] = []
    posts = root / "posts"
    for attestation_path in sorted(posts.rglob("5.review/attestation.json")):
        from core.io import read_json

        attestation = read_json(attestation_path)
        if not isinstance(attestation, dict) or attestation.get("decision") != "approved":
            continue
        post_root = attestation_path.parent.parent
        if not (post_root / "manifest.json").is_file():
            raise ObjectTransactionError(f"approved post missing manifest: {post_root}")
        refs.append(post_root.relative_to(posts).as_posix())
    if not refs:
        raise ObjectTransactionError("execution has no approved posts for canonical promotion")
    return tuple(refs)


@canonical_publish_serialized
def promote_post_object(execution_id: str, post_ref: str) -> dict[str, str]:
    """Atomically promote one reviewed post and return fenced result evidence."""
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
    from core.io import read_json

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
    if apply_report.is_file() and (canonical_post / "manifest.json").is_file():
        if (
            tree_integrity_stats(canonical_post)["merkleRoot"]
            != tree_integrity_stats(package_root / "object")["merkleRoot"]
        ):
            raise ObjectTransactionError(
                f"completed post transaction canonical object drift: {normalized_ref}"
            )
        applied = read_json(apply_report)
    else:
        audit = audit_object_transaction(
            publish_root=PUBLISH_ROOT,
            output_root=OUTPUT_ROOT,
            package_root=package_root,
            transaction_id=transaction_id,
            expected_canonical_merkle=tree_integrity_stats(PUBLISH_ROOT)["merkleRoot"],
        )
        applied = apply_object_transaction(
            publish_root=PUBLISH_ROOT,
            output_root=OUTPUT_ROOT,
            package_root=package_root,
            transaction_id=transaction_id,
            dry_run_attestation_sha256=str(audit["dryRunAttestationSha256"]),
        )
    closure = validate_canonical_publish(PUBLISH_ROOT)
    if closure["status"] != "passed":
        raise ObjectTransactionError(
            f"canonical publish closure failed: {closure['issues'][:5]}"
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
    root = execution_root(execution_id)
    refs = _approved_post_refs(root)
    for post_ref in refs:
        promote_post_object(execution_id, post_ref)
    write_publish_ref(execution_id, post_refs=refs)
    return refs


__all__ = ["promote_execution_posts", "promote_post_object"]
