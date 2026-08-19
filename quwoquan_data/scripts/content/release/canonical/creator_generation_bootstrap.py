"""Atomically bootstrap admitted Creator projections into an empty generation."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import yaml

from content.release.canonical.content_pool_record import append_pool_record
from content.release.canonical.creator_projection import project_creator_object
from content.release.canonical.media_library_holding import (
    resolve_explicit_media_holding,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _digest_file,
    _safe_id,
    _tree_digest,
    _write_json,
)
from content.release.canonical.pool_backfill_canonical import build_pool_record


def bootstrap_creator_generation(
    *,
    generation_id: str,
    creator_refs: tuple[str, ...],
    creator_pool_root: Path,
    media_library_root: Path,
    publish_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    normalized_generation = _safe_id(generation_id, label="generationId")
    if not creator_refs or len(set(creator_refs)) != len(creator_refs):
        raise ObjectTransactionError("DATA.POOL.CREATOR_BOOTSTRAP_REFS_INVALID")
    creator_pool = creator_pool_root.resolve(strict=True)
    library = media_library_root.resolve(strict=True)
    publish = publish_root.resolve()
    output = output_root.resolve()
    if publish.exists():
        raise ObjectTransactionError("DATA.POOL.CREATOR_BOOTSTRAP_TARGET_EXISTS")
    publish.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{publish.name}.", dir=publish.parent))
    try:
        creators_root = staging / "creators"
        media_rows: list[dict[str, object]] = []
        for raw_ref in creator_refs:
            creator_ref = _safe_id(raw_ref, label="creatorRef")
            matches = [
                path
                for path in sorted((creator_pool / "profiles").rglob("*.creator.yaml"))
                if isinstance(
                    payload := yaml.safe_load(path.read_text(encoding="utf-8")),
                    dict,
                )
                and payload.get("creatorProfileId") == creator_ref
            ]
            if len(matches) != 1:
                raise ObjectTransactionError(
                    f"DATA.POOL.CREATOR_PROFILE_INVALID: {creator_ref}"
                )
            profile_path = matches[0]
            profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
            avatar = profile.get("avatarAsset") if isinstance(profile, dict) else None
            if isinstance(avatar, dict):
                entry = resolve_explicit_media_holding(
                    library,
                    sha256=str(avatar.get("sha256") or ""),
                    expected_bytes=int(avatar.get("bytes") or 0),
                )
                object_key = str(avatar.get("objectKey") or "")
                target = staging / object_key
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(entry, target)
                media_rows.append(
                    {
                        "creatorRef": creator_ref,
                        "objectKey": object_key,
                        "sha256": str(avatar["sha256"]),
                        "bytes": int(avatar["bytes"]),
                    }
                )
            target_creator = creators_root / creator_ref
            project_creator_object(
                creator_ref,
                target_creator,
                publish_root=staging,
                creator_pool_root=creator_pool,
            )
            admission = profile.get("admission")
            if not isinstance(admission, dict):
                raise ObjectTransactionError(
                    f"DATA.POOL.CREATOR_ADMISSION_INVALID: {creator_ref}"
                )
            append_pool_record(
                object_root=target_creator,
                record=build_pool_record(
                    object_type="author",
                    object_id=str(profile.get("authorId") or ""),
                    object_ref=creator_ref,
                    record_sequence=1,
                    content_version=int(profile.get("version") or 0),
                    process_result=str(admission.get("processResult") or ""),
                    quality_result=str(admission.get("qualityResult") or ""),
                    eligibility_result="passed",
                    usage_scope=None,
                    evidence_ref=str(admission.get("evidenceRef") or ""),
                    evidence_digest=str(admission.get("evidenceDigest") or ""),
                    payload_digest=_digest_file(profile_path),
                ),
            )
        receipt_root = (
            output
            / "data/local/workspace/canonical-generations"
            / normalized_generation
        )
        receipt_path = receipt_root / "creator_bootstrap.json"
        if receipt_path.exists():
            raise ObjectTransactionError(
                "DATA.POOL.CREATOR_BOOTSTRAP_RECEIPT_CONFLICT"
            )
        receipt = {
            "schema": "quwoquan_data.creator_generation_bootstrap",
            "generationId": normalized_generation,
            "publishRoot": str(publish),
            "creatorPoolRoot": str(creator_pool),
            "mediaLibraryRoot": str(library),
            "creatorRefs": list(creator_refs),
            "media": media_rows,
            "generationTreeDigest": _tree_digest(staging),
        }
        receipt_root.mkdir(parents=True, exist_ok=True)
        _write_json(receipt_path, receipt)
        os.replace(staging, publish)
        return {
            "schema": "quwoquan_data.creator_generation_bootstrap_result",
            "generationId": normalized_generation,
            "status": "created",
            "publishRoot": str(publish),
            "creatorRefs": list(creator_refs),
            "generationTreeDigest": _tree_digest(publish),
            "receiptRef": str(receipt_path),
        }
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


__all__ = ["bootstrap_creator_generation"]
