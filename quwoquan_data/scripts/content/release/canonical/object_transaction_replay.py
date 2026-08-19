"""Exact replay of a reviewed object transaction package from library holdings."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.release.canonical.application import (
    apply_object_transaction,
    replay_object_transaction,
)
from content.release.canonical.canonical_inventory import load_or_bootstrap_inventory
from content.release.canonical.media_library_holding import (
    resolve_explicit_media_holding,
)
from content.release.canonical.object_transaction_audit import audit_object_transaction
from content.release.canonical.post_promotion import (
    repair_applied_post_pool_record_drift,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _copy_tree,
    _digest_file,
    _read_json,
    _safe_id,
    _safe_rel,
    _tree_digest,
    _verify_package,
    _write_json,
)


def _restore_package_cas(
    *,
    package_root: Path,
    media_library_root: Path,
) -> None:
    package = _read_json(package_root / "object_transaction_package.json")
    closure = package.get("closure")
    rows = closure.get("casRefs") if isinstance(closure, Mapping) else None
    if not isinstance(rows, list) or not rows:
        raise ObjectTransactionError("DATA.POOL.REPLAY_CAS_CLOSURE_MISSING")
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise ObjectTransactionError("DATA.POOL.REPLAY_CAS_CLOSURE_INVALID")
        destination = package_root / _safe_rel(
            str(raw.get("sourceRef") or ""), label="cas.sourceRef"
        )
        digest = str(raw.get("sha256") or "")
        byte_count = raw.get("bytes")
        if destination.is_file():
            source = destination
        else:
            source = resolve_explicit_media_holding(
                media_library_root,
                sha256=digest,
                expected_bytes=int(byte_count or 0),
            )
        if (
            source.is_symlink()
            or not source.is_file()
            or _digest_file(source) != digest
            or source.stat().st_size != byte_count
        ):
            raise ObjectTransactionError("DATA.POOL.LIBRARY_HOLDING_DRIFT")
        if destination != source:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)


def replay_object_transaction_package(
    *,
    replay_id: str,
    source_package_root: Path,
    media_library_root: Path,
    output_root: Path,
    publish_root: Path,
) -> dict[str, Any]:
    normalized_replay = _safe_id(replay_id, label="replayId")
    source_package = source_package_root.resolve(strict=True)
    library = media_library_root.resolve(strict=True)
    output = output_root.resolve()
    publish = publish_root.resolve()
    if source_package_root.is_symlink() or media_library_root.is_symlink():
        raise ObjectTransactionError("DATA.POOL.REPLAY_SOURCE_SYMLINK")
    source_tree_digest = _tree_digest(source_package)
    source_document = _read_json(source_package / "object_transaction_package.json")
    transaction_id = _safe_id(
        str(source_document.get("transactionId") or ""),
        label="transactionId",
    )
    target = source_document.get("target")
    if not isinstance(target, Mapping):
        raise ObjectTransactionError("DATA.POOL.REPLAY_TARGET_INVALID")
    canonical_object = (
        publish / str(target.get("objectKind") or "") / str(target.get("objectRef") or "")
    )
    source_object = source_package / str(target.get("packageObjectRef") or "object")
    if canonical_object.exists():
        if not canonical_object.is_dir():
            raise ObjectTransactionError("DATA.POOL.REPLAY_TARGET_CONFLICT")
        if target.get("objectKind") in {"posts", "entities"}:
            from content.release.canonical.content_pool_record import (
                pool_payload_digest,
            )

            target_matches = pool_payload_digest(canonical_object) == pool_payload_digest(
                source_object
            )
        else:
            target_matches = _tree_digest(canonical_object) == _tree_digest(source_object)
        if not target_matches:
            raise ObjectTransactionError("DATA.POOL.REPLAY_TARGET_CONFLICT")
    final_root = (
        output
        / "data/local/workspace/object-transaction-replays"
        / normalized_replay
    )
    package_root = final_root / "package"
    if final_root.is_dir():
        binding = _read_json(final_root / "source_binding.json")
        if (
            binding.get("sourcePackageTreeDigest") != source_tree_digest
            or binding.get("transactionId") != transaction_id
            or Path(str(binding.get("mediaLibraryRoot") or "")) != library
        ):
            raise ObjectTransactionError("DATA.POOL.REPLAY_CREATE_ONCE_CONFLICT")
    elif final_root.exists():
        raise ObjectTransactionError("DATA.POOL.REPLAY_INCOMPLETE_OUTPUT")
    else:
        final_root.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(
            tempfile.mkdtemp(prefix=f".{normalized_replay}.", dir=final_root.parent)
        )
        try:
            staged_package = staging / "package"
            _copy_tree(source_package, staged_package)
            _restore_package_cas(
                package_root=staged_package,
                media_library_root=library,
            )
            verified = _verify_package(
                staged_package,
                canonical_root=publish,
                require_target_absent=False,
            )
            if (
                verified["transactionId"] != transaction_id
                or verified["objectClosureDigest"]
                != source_document.get("objectClosureDigest")
                or _tree_digest(source_package) != source_tree_digest
            ):
                raise ObjectTransactionError("DATA.POOL.REPLAY_PACKAGE_DRIFT")
            _write_json(
                staging / "source_binding.json",
                {
                    "schema": "quwoquan_data.object_transaction_replay_source_binding",
                    "replayId": normalized_replay,
                    "transactionId": transaction_id,
                    "sourcePackageRoot": str(source_package),
                    "sourcePackageTreeDigest": source_tree_digest,
                    "verifiedPackageTreeDigest": _tree_digest(staged_package),
                    "mediaLibraryRoot": str(library),
                    "packageSha256": str(verified["packageSha256"]),
                    "objectClosureDigest": str(verified["objectClosureDigest"]),
                },
            )
            staging.replace(final_root)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    run_root = output / "data/local/workspace/object-transactions" / transaction_id
    audit_path = run_root / "audit_report.json"
    apply_path = run_root / "apply_report.json"
    if apply_path.is_file() and audit_path.is_file():
        audit = _read_json(audit_path)
    else:
        audit = audit_object_transaction(
            publish_root=publish,
            output_root=output,
            package_root=package_root,
            transaction_id=transaction_id,
            expected_canonical_merkle=load_or_bootstrap_inventory(publish)["stats"][
                "merkleRoot"
            ],
        )
    rollback_path = run_root / "rollback_report.json"
    if rollback_path.is_file():
        applied = replay_object_transaction(
            publish_root=publish,
            output_root=output,
            transaction_id=transaction_id,
        )
    else:
        applied = apply_object_transaction(
            publish_root=publish,
            output_root=output,
            package_root=package_root,
            transaction_id=transaction_id,
            dry_run_attestation_sha256=str(audit["dryRunAttestationSha256"]),
        )
    if _tree_digest(canonical_object) != _tree_digest(package_root / "object"):
        raise ObjectTransactionError("DATA.POOL.REPLAY_READBACK_DRIFT")
    pool_record_repaired = False
    if target["objectKind"] == "posts":
        pool_record_repaired = repair_applied_post_pool_record_drift(
            package_root=package_root,
            canonical_post=canonical_object,
            canonical_ref=str(target["objectRef"]),
        )
    return {
        "schema": "quwoquan_data.object_transaction_package_replay_result",
        "replayId": normalized_replay,
        "transactionId": transaction_id,
        "status": str(applied["status"]),
        "packageRoot": str(package_root),
        "canonicalObjectRef": (
            f"{target['objectKind']}/{target['objectRef']}"
        ),
        "canonicalObjectSha256": _tree_digest(canonical_object),
        "poolRecordRepaired": pool_record_repaired,
        "idempotent": bool(applied["idempotent"]),
    }


__all__ = ["replay_object_transaction_package"]
