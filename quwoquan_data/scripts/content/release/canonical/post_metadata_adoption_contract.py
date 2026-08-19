"""Fail-closed contract for forward-only reviewed Post metadata adoption."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.execution.runtime_contract import canonical_sha256, file_sha256
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
    _safe_rel,
)
from core.schema import assert_valid

ADOPTION_SCHEMA = "quwoquan_data.post_metadata_adoption"


class PostMetadataAdoptionError(ObjectTransactionError):
    """Source review evidence or deterministic successor failed closed."""


ALLOWED_CHANGES = (
    "manifest.generator",
    "manifest.version",
    "provenance.final.generator",
    "poolRecord",
)
ZERO_INVOCATIONS = {
    "acquisition": 0,
    "semantic": 0,
    "author": 0,
    "review": 0,
}


def adoption_digest(document: Mapping[str, Any]) -> str:
    stable = {key: value for key, value in document.items() if key != "receiptDigest"}
    return canonical_sha256(stable)


def validate_adoption_receipt(
    value: object,
    *,
    object_root: Path | None = None,
) -> dict[str, Any]:
    try:
        assert_valid(
            value,
            "release",
            "post_metadata_adoption",
            label="post_metadata_adoption",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise ObjectTransactionError(str(exc)) from exc
    if not isinstance(value, Mapping):
        raise ObjectTransactionError("DATA.POOL.METADATA_ADOPTION_INVALID")
    document = dict(value)
    if document.get("receiptDigest") != adoption_digest(document):
        raise ObjectTransactionError("DATA.POOL.METADATA_ADOPTION_DIGEST_DRIFT")
    source = document["source"]
    target = document["target"]
    if (
        source["contentId"] != target["contentId"]
        or target["contentVersion"] != source["contentVersion"] + 1
        or source["objectRef"].rsplit("/", 1)[0]
        != target["objectRef"].rsplit("/", 1)[0]
        or int(source["objectRef"].rsplit("/", 1)[1]) != source["contentVersion"]
        or int(target["objectRef"].rsplit("/", 1)[1]) != target["contentVersion"]
    ):
        raise ObjectTransactionError("DATA.POOL.METADATA_ADOPTION_IDENTITY_DRIFT")
    if object_root is not None:
        manifest_path = object_root / "manifest.json"
        provenance_path = object_root / "provenance.json"
        if (
            not manifest_path.is_file()
            or not provenance_path.is_file()
            or file_sha256(manifest_path) != target["manifestSha256"]
            or file_sha256(provenance_path) != target["provenanceFileSha256"]
            or canonical_sha256(_read_json(provenance_path))
            != target["provenanceCanonicalSha256"]
        ):
            raise ObjectTransactionError("DATA.POOL.METADATA_ADOPTION_TARGET_DRIFT")
    return document


def validate_adoption_delta(
    value: Mapping[str, Any],
    *,
    source_object_ref: str,
    target_object_ref: str,
) -> None:
    source_prefix = f"posts/{source_object_ref.rstrip('/')}/"
    target_prefix = f"posts/{target_object_ref.rstrip('/')}/"
    if value.get("targetPrefix") != target_prefix.rstrip("/"):
        raise ObjectTransactionError("DATA.POOL.METADATA_ADOPTION_DELTA_TARGET_DRIFT")
    entries = value.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ObjectTransactionError("DATA.POOL.METADATA_ADOPTION_DELTA_EMPTY")
    for raw in entries:
        if not isinstance(raw, Mapping):
            raise ObjectTransactionError("DATA.POOL.METADATA_ADOPTION_DELTA_INVALID")
        destination = str(raw.get("destination") or "")
        operation = str(raw.get("operation") or "")
        if operation != "create":
            raise ObjectTransactionError(
                "DATA.POOL.METADATA_ADOPTION_DELTA_NOT_FORWARD_ONLY"
            )
        if destination.startswith(source_prefix):
            raise ObjectTransactionError(
                "DATA.POOL.METADATA_ADOPTION_SOURCE_MUTATION_FORBIDDEN"
            )
        if destination.startswith("posts/") and not destination.startswith(
            target_prefix
        ):
            raise ObjectTransactionError(
                "DATA.POOL.METADATA_ADOPTION_CROSS_POST_MUTATION_FORBIDDEN"
            )


def metadata_adoption_binding(
    *,
    package_root: Path,
    object_root: Path,
    package: Mapping[str, Any],
) -> dict[str, str] | None:
    raw = package.get("metadataAdoption")
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ObjectTransactionError("DATA.POOL.METADATA_ADOPTION_INVALID")
    ref = _safe_rel(str(raw.get("ref") or ""), label="metadataAdoption.ref")
    path = object_root / ref
    if not path.is_file() or path.is_symlink():
        raise ObjectTransactionError("DATA.POOL.METADATA_ADOPTION_MISSING")
    receipt = validate_adoption_receipt(_read_json(path), object_root=object_root)
    binding = {
        "ref": ref.as_posix(),
        "sha256": file_sha256(path),
        "receiptDigest": str(receipt["receiptDigest"]),
    }
    if dict(raw) != binding:
        raise ObjectTransactionError("DATA.POOL.METADATA_ADOPTION_BINDING_DRIFT")
    try:
        path.relative_to(package_root)
    except ValueError as exc:
        raise ObjectTransactionError("DATA.POOL.METADATA_ADOPTION_PATH_ESCAPE") from exc
    return binding


__all__ = [
    "ADOPTION_SCHEMA",
    "ALLOWED_CHANGES",
    "PostMetadataAdoptionError",
    "ZERO_INVOCATIONS",
    "adoption_digest",
    "metadata_adoption_binding",
    "validate_adoption_delta",
    "validate_adoption_receipt",
]
