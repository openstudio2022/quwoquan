"""Derive exact legacy receipt migrations for publish-intermediate cleanup."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.asset_review_adoption import (
    build_independent_asset_review_binding,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _digest_bytes,
    _digest_file,
    _execution_id,
    _files,
    _json_bytes,
    _read_json,
    _safe_rel,
)
from content.source.independent_asset_review import (
    IndependentAssetReviewError,
    assert_asset_review_accepted,
)
from core.schema import assert_valid


def cleanup_receipt_files(
    root: Path,
    *,
    relative_to: Path,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in _files(root):
        relative = path.relative_to(root)
        if (
            len(relative.parts) != 2
            or relative.parts[0] != "receipts"
            or relative.suffix != ".json"
        ):
            raise ObjectTransactionError(
                f"legacy asset_reviews contains unsupported evidence: {path}"
            )
        rows.append(
            {
                "ref": path.relative_to(relative_to).as_posix(),
                "sha256": _digest_file(path),
                "bytes": path.stat().st_size,
            }
        )
    if not rows:
        raise ObjectTransactionError(f"legacy asset_reviews has no receipts: {root}")
    return rows


def _source_task_id(manifest: Mapping[str, Any]) -> str:
    source_task_id = _execution_id(str(manifest.get("sourceTaskId") or ""))
    execution_id = str(manifest.get("executionId") or "").strip()
    if execution_id and _execution_id(execution_id) != source_task_id:
        raise ObjectTransactionError("canonical object execution/sourceTaskId drift")
    return source_task_id


def _external_receipt_ref(*, source_task_id: str, review_id: str) -> Path:
    return (
        Path("data/tasks")
        / source_task_id
        / "evidence/asset_reviews/receipts"
        / f"{review_id}.json"
    )


def _migration(
    *,
    binding: Mapping[str, Any],
    object_root: Path,
    publish_root: Path,
    output_root: Path,
    source_task_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    review_id = str(binding.get("reviewId") or "")
    old_ref = _safe_rel(str(binding.get("receiptRef") or ""), label="receiptRef")
    if (
        len(old_ref.parts) != 3
        or old_ref.parts[:2] != ("asset_reviews", "receipts")
        or old_ref.name != f"{review_id}.json"
    ):
        raise ObjectTransactionError("legacy asset review receiptRef is not object-local")
    local_path = object_root / old_ref
    external_ref = _external_receipt_ref(
        source_task_id=source_task_id,
        review_id=review_id,
    )
    external_path = output_root / external_ref
    if (
        not local_path.is_file()
        or local_path.is_symlink()
        or not external_path.is_file()
        or external_path.is_symlink()
    ):
        raise ObjectTransactionError(
            f"GATE_BLOCK external review receipt is missing: {external_ref}"
        )
    local_bytes = local_path.read_bytes()
    if local_bytes != external_path.read_bytes():
        raise ObjectTransactionError(
            f"external review receipt bytes collision: {external_ref}"
        )
    file_sha = _digest_bytes(local_bytes)
    receipt = _read_json(external_path)
    try:
        assert_asset_review_accepted(
            receipt,
            content_sha256=str(binding.get("contentSha256") or ""),
            source_digest=str(binding.get("sourceDigest") or ""),
            asset_id=str(binding.get("acquisitionAssetId") or ""),
        )
    except (IndependentAssetReviewError, ValueError) as exc:
        raise ObjectTransactionError(str(exc)) from exc
    expected_old = build_independent_asset_review_binding(
        receipt,
        receipt_ref=old_ref.as_posix(),
        receipt_file_sha256=file_sha,
    )
    if dict(binding) != expected_old:
        raise ObjectTransactionError("legacy independent review binding drift")
    migrated = build_independent_asset_review_binding(
        receipt,
        receipt_ref=external_ref.as_posix(),
        receipt_file_sha256=file_sha,
    )
    return migrated, {
        "reviewId": review_id,
        "localRef": local_path.relative_to(publish_root).as_posix(),
        "externalRef": external_ref.as_posix(),
        "receiptDigest": str(receipt["receiptDigest"]),
        "receiptFileSha256": file_sha,
        "bytes": len(local_bytes),
    }


def _candidate(
    *,
    review_root: Path,
    publish_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    object_root = review_root.parent
    object_ref = object_root.relative_to(publish_root)
    if not object_ref.parts or object_ref.parts[0] not in {
        "creators",
        "entities",
        "posts",
    }:
        raise ObjectTransactionError(
            f"legacy asset_reviews is outside canonical objects: {object_ref}"
        )
    manifest_path = object_root / "manifest.json"
    rights_path = object_root / "rights.json"
    manifest = _read_json(manifest_path)
    rights = _read_json(rights_path)
    source_task_id = _source_task_id(manifest)
    source_digest = manifest.get("sourceDigest")
    source_digest = source_digest if isinstance(source_digest, Mapping) else {}
    migrated_assets: list[dict[str, Any]] = []
    migrations: list[dict[str, Any]] = []
    for raw_asset in rights.get("assets") or []:
        if not isinstance(raw_asset, Mapping):
            raise ObjectTransactionError("canonical rights asset is invalid")
        asset = dict(raw_asset)
        binding = asset.get("independentAssetReview")
        if isinstance(binding, Mapping):
            if binding.get("sourceDigest") != source_digest.get("digest"):
                raise ObjectTransactionError("review/manifest sourceDigest drift")
            migrated, row = _migration(
                binding=binding,
                object_root=object_root,
                publish_root=publish_root,
                output_root=output_root,
                source_task_id=source_task_id,
            )
            asset["independentAssetReview"] = migrated
            migrations.append(row)
        migrated_assets.append(asset)
    if not migrations:
        raise ObjectTransactionError(f"legacy review bindings are missing: {object_ref}")
    observed_files = cleanup_receipt_files(review_root, relative_to=publish_root)
    observed_refs = {str(row["ref"]) for row in observed_files}
    migration_refs = {str(row["localRef"]) for row in migrations}
    if observed_refs != migration_refs or len(migrations) != len(migration_refs):
        raise ObjectTransactionError("legacy review receipt/reference closure drift")
    after_rights = {**rights, "assets": migrated_assets}
    try:
        assert_valid(
            after_rights,
            "release",
            "asset_rights_closure",
            label="migrated asset rights closure",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise ObjectTransactionError(str(exc)) from exc
    after_bytes = _json_bytes(after_rights)
    return {
        "ref": review_root.relative_to(publish_root).as_posix(),
        "objectRef": object_ref.as_posix(),
        "sourceTaskId": source_task_id,
        "manifestRef": manifest_path.relative_to(publish_root).as_posix(),
        "rightsRef": rights_path.relative_to(publish_root).as_posix(),
        "beforeRightsSha256": _digest_file(rights_path),
        "beforeRightsBytes": rights_path.stat().st_size,
        "afterRightsSha256": _digest_bytes(after_bytes),
        "afterRightsBytes": len(after_bytes),
        "afterRights": after_rights,
        "receiptMigrations": migrations,
        "fileCount": len(observed_files),
        "bytes": sum(int(row["bytes"]) for row in observed_files),
    }


def cleanup_candidates(
    publish_root: Path,
    output_root: Path,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for root in sorted(publish_root.rglob("asset_reviews")):
        if root.is_symlink() or not root.is_dir():
            raise ObjectTransactionError(f"legacy asset_reviews is invalid: {root}")
        rows.append(
            _candidate(
                review_root=root,
                publish_root=publish_root,
                output_root=output_root,
            )
        )
    return rows


def cleanup_delta_entries(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        rows.append(
            {
                "operation": "replace",
                "destination": candidate["rightsRef"],
                "beforeSha256": candidate["beforeRightsSha256"],
                "beforeBytes": candidate["beforeRightsBytes"],
                "sha256": candidate["afterRightsSha256"],
                "bytes": candidate["afterRightsBytes"],
            }
        )
        rows.extend(
            {
                "operation": "delete",
                "destination": migration["localRef"],
                "beforeSha256": migration["receiptFileSha256"],
                "beforeBytes": migration["bytes"],
            }
            for migration in candidate["receiptMigrations"]
        )
    return sorted(rows, key=lambda row: str(row["destination"]))


__all__ = [
    "cleanup_candidates",
    "cleanup_delta_entries",
    "cleanup_receipt_files",
]
