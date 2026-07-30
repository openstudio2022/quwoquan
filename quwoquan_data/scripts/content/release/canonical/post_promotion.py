"""Atomically promote every approved post in one execution to canonical publish."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

from core.image_deduplication import perceptual_hash, perceptual_hash_distance
from core.image_safety import NEAR_DUP_HAMMING
from core.io import read_json
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


def _image_identities(
    manifest: Mapping[str, Any],
    *,
    asset_root: Path | None = None,
) -> tuple[tuple[str, str, str], ...]:
    rows: list[tuple[str, str, str]] = []
    image_post = str(manifest.get("contentType") or "").strip() == "image"
    for raw in manifest.get("assets") or []:
        if not isinstance(raw, Mapping):
            continue
        kind = str(raw.get("kind") or "").strip()
        mime = str(raw.get("mimeType") or "").strip().lower()
        if not image_post and kind != "image" and not mime.startswith("image/"):
            continue
        perceptual = str(raw.get("perceptualHash") or "").strip().lower()
        if not perceptual and asset_root is not None:
            object_key = Path(str(raw.get("objectKey") or "").strip())
            if (
                not object_key.parts
                or object_key.is_absolute()
                or ".." in object_key.parts
            ):
                raise ObjectTransactionError(
                    "legacy canonical image objectKey is missing or unsafe"
                )
            asset = asset_root / object_key
            if not asset.is_file():
                raise ObjectTransactionError(
                    f"legacy canonical image asset is missing: {object_key.as_posix()}"
                )
            perceptual = perceptual_hash(asset)
        rows.append(
            (
                str(raw.get("assetId") or "").strip() or "<unnamed-image>",
                str(raw.get("sha256") or "").strip().lower(),
                perceptual,
            )
        )
    return tuple(rows)


def _assert_cross_publish_image_unique(
    *,
    package_root: Path,
    canonical_post: Path,
) -> None:
    """Reject exact or perceptually duplicated images across canonical posts."""

    package_manifest = read_json(package_root / "object/manifest.json")
    if not isinstance(package_manifest, Mapping):
        raise ObjectTransactionError("post transaction manifest must be an object")
    candidates = _image_identities(package_manifest)
    if str(package_manifest.get("contentType") or "").strip() == "image":
        if not candidates or any(not perceptual for _, _, perceptual in candidates):
            raise ObjectTransactionError(
                "commercial image post requires perceptualHash for every image asset"
            )

    accepted: list[tuple[str, str, str, str]] = []
    for manifest_path in sorted((PUBLISH_ROOT / "posts").glob("**/manifest.json")):
        if manifest_path.parent == canonical_post:
            continue
        existing = read_json(manifest_path)
        if not isinstance(existing, Mapping):
            raise ObjectTransactionError(
                f"canonical post manifest must be an object: {manifest_path}"
            )
        existing_ref = manifest_path.parent.relative_to(PUBLISH_ROOT).as_posix()
        accepted.extend(
            (existing_ref, asset_id, digest, perceptual)
            for asset_id, digest, perceptual in _image_identities(
                existing,
                asset_root=PUBLISH_ROOT,
            )
        )

    for index, (asset_id, digest, perceptual) in enumerate(candidates):
        peers = accepted + [
            ("pending-post", peer_id, peer_digest, peer_perceptual)
            for peer_id, peer_digest, peer_perceptual in candidates[:index]
        ]
        for peer_ref, peer_id, peer_digest, peer_perceptual in peers:
            if digest and peer_digest and digest == peer_digest:
                raise ObjectTransactionError(
                    "canonical image identity duplicated by sha256: "
                    f"{asset_id} conflicts with {peer_ref}:{peer_id}"
                )
            if (
                perceptual
                and peer_perceptual
                and perceptual_hash_distance(perceptual, peer_perceptual)
                <= NEAR_DUP_HAMMING
            ):
                raise ObjectTransactionError(
                    "canonical image identity duplicated by perceptualHash: "
                    f"{asset_id} conflicts with {peer_ref}:{peer_id}"
                )


def _qualified_post_refs(execution_id: str) -> tuple[str, ...]:
    from content.execution.post_review_closure import (
        indexed_post_targets,
        load_post_review_closure,
    )

    closure = load_post_review_closure(
        execution_id,
        expected_object_targets=indexed_post_targets(execution_id),
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
    refs = _qualified_post_refs(execution_id)
    for post_ref in refs:
        promote_post_object(execution_id, post_ref)
    write_publish_ref(execution_id, post_refs=refs)
    return refs


__all__ = ["promote_execution_posts", "promote_post_object"]
