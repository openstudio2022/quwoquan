"""Create-once reuse validation for canonical post transaction packages."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.content_pool_record import (
    build_canonical_pool_record,
)
from content.release.canonical.object_transaction_contract import (
    EXPECTED_OBJECT_SCHEMAS,
    ObjectTransactionError,
    _closure_digest,
    _read_json,
    _review_binding,
    _write_json,
)
from core.schema import assert_valid


def reuse_existing_post_package(
    *,
    package_root: Path,
    transaction_id: str,
    execution_id: str,
    input_payload_digest: str,
    canonical_ref: str,
    creator_binding: Mapping[str, Any],
    output_root: Path,
) -> dict[str, Any]:
    existing = _read_json(package_root / "object_transaction_package.json")
    if (
        existing.get("transactionId") == transaction_id
        and existing.get("executionId") == execution_id
        and existing.get("inputPayloadDigest") == input_payload_digest
    ):
        rights_path = package_root / "object/rights.json"
        rights = _read_json(rights_path)
        package_mode = existing.get("publishMediaMode")
        rights_mode = rights.get("publishMediaMode")
        if package_mode is None or rights_mode is None:
            run_root = (
                output_root
                / "data/local/workspace/object-transactions"
                / transaction_id
            )
            packaged_manifest = _read_json(package_root / "object/manifest.json")
            closure = existing.get("closure")
            if (
                (run_root / "audit_report.json").exists()
                or (run_root / "apply_report.json").exists()
                or package_mode not in {None, "text_only"}
                or rights_mode not in {None, "text_only"}
                or existing.get("target", {}).get("objectKind") != "posts"
                or existing.get("target", {}).get("objectRef") != canonical_ref
                or not isinstance(closure, Mapping)
                or closure.get("rightsRef") != "rights.json"
                or closure.get("casRefs") != []
                or packaged_manifest.get("publishMediaMode") != "text_only"
                or packaged_manifest.get("assets") != []
                or rights.get("assets") != []
                or any(
                    packaged_manifest.get(key) != value
                    for key, value in creator_binding.items()
                )
            ):
                raise ObjectTransactionError(
                    "DATA.POOL.IDEMPOTENCY_CONFLICT: "
                    "pre-media-mode package contract drift"
                )
        if rights_mode is None:
            rights = {**rights, "publishMediaMode": "text_only"}
            try:
                assert_valid(
                    rights,
                    "release",
                    "asset_rights_closure",
                    label="object_transaction_asset_rights_closure",
                )
            except (ValueError, FileNotFoundError) as exc:
                raise ObjectTransactionError(str(exc)) from exc
            encoded = (
                json.dumps(rights, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
            temporary = package_root / "object/.rights.json.upgrade"
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, rights_path)
            finally:
                temporary.unlink(missing_ok=True)
        if package_mode is None or rights_mode is None:
            object_root = package_root / "object"
            closure = existing["closure"]
            pool_record_path = object_root / "_pool/versions/1.json"
            pool_record = _read_json(pool_record_path)
            if (
                pool_record.get("objectId") != packaged_manifest.get("contentId")
                or pool_record.get("contentVersion") != packaged_manifest.get("version")
                or pool_record.get("recordSequence") != 1
            ):
                raise ObjectTransactionError(
                    "DATA.POOL.IDEMPOTENCY_CONFLICT: pre-media-mode pool record drift"
                )
            refreshed_pool_record = build_canonical_pool_record(
                object_root=object_root,
                object_type="content",
                object_ref=canonical_ref,
            )
            refreshed_pool_record["recordSequence"] = 1
            if any(
                refreshed_pool_record.get(key) != value
                for key, value in pool_record.items()
                if key not in {"payloadDigest", "canonicalObjectDigest"}
            ):
                raise ObjectTransactionError(
                    "DATA.POOL.IDEMPOTENCY_CONFLICT: pre-media-mode pool record drift"
                )
            _write_json(pool_record_path, refreshed_pool_record)
            review_binding = _review_binding(object_root, existing)
            existing = {
                **existing,
                "publishMediaMode": "text_only",
                "objectClosureDigest": _closure_digest(
                    object_root=object_root,
                    object_kind="posts",
                    object_ref=canonical_ref,
                    target_schema=EXPECTED_OBJECT_SCHEMAS["posts"],
                    source_policy_revision=str(
                        existing.get("sourcePolicyRevision") or ""
                    ),
                    closure=closure,
                    cas_rows=[],
                    review=review_binding,
                ),
            }
            try:
                assert_valid(
                    existing,
                    "release",
                    "object_transaction_package",
                    label="object_transaction_package",
                )
            except (ValueError, FileNotFoundError) as exc:
                raise ObjectTransactionError(str(exc)) from exc
            encoded = (
                json.dumps(existing, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n"
            ).encode("utf-8")
            package_path = package_root / "object_transaction_package.json"
            temporary = package_root / ".object_transaction_package.json.upgrade"
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, package_path)
            finally:
                temporary.unlink(missing_ok=True)
        return existing
    raise ObjectTransactionError(
        "DATA.POOL.IDEMPOTENCY_CONFLICT: "
        f"sourceTaskId={execution_id} objectId={canonical_ref} payloadDigest drift"
    )


__all__ = ["reuse_existing_post_package"]
