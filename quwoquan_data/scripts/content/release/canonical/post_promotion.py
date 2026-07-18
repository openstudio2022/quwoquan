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


def promote_execution_posts(execution_id: str) -> tuple[str, ...]:
    root = execution_root(execution_id)
    refs = _approved_post_refs(root)
    for post_ref in refs:
        transaction_id = (
            f"{execution_id}--post-"
            f"{hashlib.sha256(post_ref.encode('utf-8')).hexdigest()[:12]}"
        )
        package_root = root / "evidence/object-transactions" / transaction_id
        apply_report = (
            OUTPUT_ROOT
            / "data/local/workspace/object-transactions"
            / transaction_id
            / "apply_report.json"
        )
        canonical_post = PUBLISH_ROOT / "posts" / post_ref
        build_post_object_transaction_package(
            execution_root=root,
            object_ref=post_ref,
            transaction_id=transaction_id,
            package_root=package_root,
        )
        if apply_report.is_file() and (canonical_post / "manifest.json").is_file():
            if (
                tree_integrity_stats(canonical_post)["merkleRoot"]
                != tree_integrity_stats(package_root / "object")["merkleRoot"]
            ):
                raise ObjectTransactionError(
                    f"completed post transaction canonical object drift: {post_ref}"
                )
            continue
        audit = audit_object_transaction(
            publish_root=PUBLISH_ROOT,
            output_root=OUTPUT_ROOT,
            package_root=package_root,
            transaction_id=transaction_id,
            expected_canonical_merkle=tree_integrity_stats(PUBLISH_ROOT)["merkleRoot"],
        )
        apply_object_transaction(
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
    write_publish_ref(execution_id, post_refs=refs)
    return refs


__all__ = ["promote_execution_posts"]
