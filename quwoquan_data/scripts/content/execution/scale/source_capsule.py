"""Pre-campaign create-once source/runtime capsule for governed worker hosts."""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.io import read_json
from core.schema import assert_valid


def _digest(value: Mapping[str, Any]) -> str:
    body = json.dumps(
        dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def build_governed_host_source_capsule(
    *,
    capsule_id: str,
    source_revision: str,
    source_digest: Mapping[str, Any],
    entity_catalog_digest: str,
    executor_bundle_ref: str,
    executor_bundle_digest: str,
    executor_bundle_file_sha256: str,
) -> dict[str, Any]:
    """Bind pre-campaign source inputs to one physical executor bundle receipt."""

    stable = {
        "schema": "quwoquan_data.governed_host_source_capsule",
        "capsuleId": str(capsule_id or "").strip(),
        "sourceRevision": str(source_revision or "").strip(),
        "sourceDigest": dict(source_digest),
        "entityCatalogDigest": str(entity_catalog_digest or "").strip(),
        "executorBundle": {
            "ref": str(executor_bundle_ref or "").strip(),
            "digest": str(executor_bundle_digest or "").strip(),
            "fileSha256": str(executor_bundle_file_sha256 or "").strip(),
        },
    }
    document = {**stable, "capsuleDigest": _digest(stable)}
    assert_valid(
        document,
        "execution",
        "governed_host_source_capsule",
        label=f"governed host source capsule:{capsule_id}",
    )
    return document


def write_governed_host_source_capsule_create_once(
    path: Path, document: Mapping[str, Any]
) -> dict[str, Any]:
    payload = dict(document)
    assert_valid(payload, "execution", "governed_host_source_capsule")
    stable = {key: value for key, value in payload.items() if key != "capsuleDigest"}
    if payload.get("capsuleDigest") != _digest(stable):
        raise ValueError("governed host source capsule digest drift")
    encoded = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if read_json(path) != payload:
            raise ValueError("governed host source capsule create-once collision") from None
        return payload
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    return payload


__all__ = [
    "build_governed_host_source_capsule",
    "write_governed_host_source_capsule_create_once",
]
