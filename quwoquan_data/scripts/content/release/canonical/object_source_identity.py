"""Freeze and validate the original source identity of canonical objects."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
    _safe_rel,
)
from core.source_digest import (
    ExecutionBundleIdentity,
    SourceDefinitionSnapshot,
    SourceDigestError,
    content_source_revision,
)

_SHA256_PREFIX = "sha256:"
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTITY_FIELDS = (
    "sourceRevision",
    "sourceDigest",
    "entityCatalogDigest",
)


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _SHA256_PREFIX + hashlib.sha256(encoded).hexdigest()


def source_identity_digest(identity: Mapping[str, Any]) -> str:
    values = {
        field: str(identity.get(field) or "").strip()
        for field in _IDENTITY_FIELDS
    }
    if any(not _SHA256.fullmatch(value) for value in values.values()):
        raise ObjectTransactionError("DATA.POOL.SOURCE_IDENTITY_INVALID")
    return _canonical_digest(
        {"schema": "quwoquan_data.object_source_identity", **values}
    )


def freeze_execution_source_identity(
    *,
    execution_root: Path,
    execution_manifest: Mapping[str, Any],
) -> dict[str, str]:
    execution_id = str(execution_manifest.get("executionId") or "").strip()
    try:
        source_digest = SourceDefinitionSnapshot.from_document(
            execution_manifest.get("sourceDigest")
        )
        ExecutionBundleIdentity.from_document(
            execution_manifest.get("executionBundle")
        )
    except SourceDigestError as exc:
        raise ObjectTransactionError(
            f"{execution_id}: execution manifest lacks a valid frozen sourceDigest"
        ) from exc
    target_ref = _safe_rel(
        str(execution_manifest.get("targetSetRef") or ""),
        label="executionManifest.targetSetRef",
    )
    target_path = execution_root / target_ref
    if target_path.is_symlink() or not target_path.is_file():
        raise ObjectTransactionError(
            f"DATA.POOL.SOURCE_IDENTITY_INVALID: target set missing: {target_ref}"
        )
    target_set = _read_json(target_path)
    expected_target_digest = str(
        execution_manifest.get("targetSetDigest") or ""
    ).strip()
    actual_target_digest = _canonical_digest(target_set).removeprefix(_SHA256_PREFIX)
    if actual_target_digest != expected_target_digest:
        raise ObjectTransactionError(
            f"DATA.POOL.SOURCE_IDENTITY_DRIFT: targetSetDigest: {execution_id}"
        )
    entity_catalog_digest = str(
        target_set.get("entityCatalogDigest") or ""
    ).strip()
    if str(target_set.get("executionId") or "").strip() != execution_id:
        raise ObjectTransactionError(
            f"DATA.POOL.SOURCE_IDENTITY_DRIFT: targetSet executionId: {execution_id}"
        )
    try:
        source_revision = content_source_revision(
            source_digest=source_digest.digest,
            entity_catalog_digest=entity_catalog_digest,
        )
    except SourceDigestError as exc:
        raise ObjectTransactionError(
            f"DATA.POOL.SOURCE_IDENTITY_INVALID: {execution_id}: {exc}"
        ) from exc
    identity = {
        "executionId": execution_id,
        "sourceRevision": source_revision,
        "sourceDigest": source_digest.digest,
        "entityCatalogDigest": entity_catalog_digest,
    }
    identity["identityDigest"] = source_identity_digest(identity)
    return identity


def validate_object_source_identity(
    manifest: Mapping[str, Any],
) -> dict[str, str]:
    raw = manifest.get("sourceIdentity")
    if not isinstance(raw, Mapping):
        raise ObjectTransactionError("DATA.POOL.SOURCE_IDENTITY_MISSING")
    required = {*_IDENTITY_FIELDS, "executionId", "identityDigest"}
    if set(raw) != required:
        raise ObjectTransactionError("DATA.POOL.SOURCE_IDENTITY_INVALID")
    identity = {field: str(raw.get(field) or "").strip() for field in required}
    if identity["executionId"] != str(manifest.get("executionId") or "").strip():
        raise ObjectTransactionError("DATA.POOL.SOURCE_IDENTITY_DRIFT: executionId")
    try:
        frozen_digest = SourceDefinitionSnapshot.from_document(
            manifest.get("sourceDigest")
        ).digest
        expected_revision = content_source_revision(
            source_digest=identity["sourceDigest"],
            entity_catalog_digest=identity["entityCatalogDigest"],
        )
    except SourceDigestError as exc:
        raise ObjectTransactionError("DATA.POOL.SOURCE_IDENTITY_INVALID") from exc
    if (
        frozen_digest != identity["sourceDigest"]
        or expected_revision != identity["sourceRevision"]
        or source_identity_digest(identity) != identity["identityDigest"]
    ):
        raise ObjectTransactionError("DATA.POOL.SOURCE_IDENTITY_DRIFT")
    return identity


def source_identity_set(
    identities: Sequence[Mapping[str, str]],
) -> tuple[list[dict[str, object]], str]:
    executions: dict[str, str] = {}
    grouped: dict[tuple[str, ...], set[str]] = {}
    for raw in identities:
        identity_digest = source_identity_digest(raw)
        execution_id = str(raw.get("executionId") or "").strip()
        if not execution_id:
            raise ObjectTransactionError("DATA.POOL.SOURCE_IDENTITY_INVALID")
        previous = executions.get(execution_id)
        if previous is not None and previous != identity_digest:
            raise ObjectTransactionError(
                f"DATA.POOL.SOURCE_IDENTITY_DRIFT: executionId={execution_id}"
            )
        executions[execution_id] = identity_digest
        key = tuple(str(raw[field]) for field in _IDENTITY_FIELDS)
        grouped.setdefault(key, set()).add(execution_id)
    if not grouped:
        raise ObjectTransactionError("DATA.POOL.SOURCE_IDENTITY_MISSING")
    rows: list[dict[str, object]] = []
    for key, execution_ids in sorted(grouped.items()):
        rows.append(
            {
                "sourceRevision": key[0],
                "sourceDigest": key[1],
                "entityCatalogDigest": key[2],
                "executionIds": sorted(execution_ids),
            }
        )
    set_digest = _canonical_digest(
        {"schema": "quwoquan_data.source_identity_set", "sourceIdentities": rows}
    )
    return rows, set_digest


__all__ = [
    "freeze_execution_source_identity",
    "source_identity_digest",
    "source_identity_set",
    "validate_object_source_identity",
]
