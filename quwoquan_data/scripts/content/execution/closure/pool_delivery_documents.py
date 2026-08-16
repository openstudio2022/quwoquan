"""Identity document projection for pool delivery."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.io import read_json


def _file_digest(path: Path) -> str:
    from content.execution.closure.pool_delivery import _file_digest as implementation

    return implementation(path)


def identity_documents(
    *,
    carrier: str,
    object_ref: str,
    object_dir: Path,
    reserved_identity: Mapping[str, Any] | None,
) -> tuple[str, str | None, int, str | None, Mapping[str, Any], Mapping[str, Any]]:
    manifest = read_json(object_dir / "manifest.json")
    if not isinstance(manifest, Mapping):
        raise TypeError("pool delivery manifest must be an object")
    if carrier == "homepage":
        entity = read_json(object_dir / "_entity.json")
        if not isinstance(entity, Mapping):
            raise TypeError("pool delivery homepage entity must be an object")
        expected_ref = str(entity.get("entityRef") or "").strip()
        if expected_ref != object_ref:
            raise ValueError("pool delivery homepage objectRef drift")
        return object_ref, None, 1, None, entity, manifest
    if str(manifest.get("contentType") or "").strip() != carrier:
        raise ValueError("pool delivery post carrier drift")
    if not isinstance(reserved_identity, Mapping):
        raise TypeError("pool delivery post identity reservation is missing")
    content_id = str(reserved_identity.get("contentId") or "").strip()
    version = reserved_identity.get("version")
    if (
        not content_id
        or isinstance(version, bool)
        or not isinstance(version, int)
        or version < 1
    ):
        raise ValueError("pool delivery post contentId/version is invalid")
    reservation_id = str(reserved_identity.get("reservationId") or "").strip()
    if not reservation_id.startswith("sha256:"):
        raise ValueError("pool delivery post identity reservation is invalid")
    if reserved_identity.get("sourceManifestSha256") != _file_digest(
        object_dir / "manifest.json"
    ):
        raise ValueError(
            "DATA.POOL.IDEMPOTENCY_CONFLICT: "
            "pool delivery post identity reservation input drift"
        )
    return content_id, content_id, version, reservation_id, manifest, manifest


__all__ = ["identity_documents"]
