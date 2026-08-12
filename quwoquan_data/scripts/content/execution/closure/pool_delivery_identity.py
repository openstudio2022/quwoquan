"""Create-once post identity reservations for pool-delivery intents."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.io import read_json
from core.paths import DATA_LOCAL_ROOT
from core.schema import assert_valid

from content.execution.identity import validate_execution_id
from content.release.canonical.content_pool_record import plan_content_pool_identity

_RESERVATION_DIR = "workspace/pool-delivery-version-reservations"
_RESERVATION_SCHEMA = "quwoquan_data.pool_delivery_version_reservation"


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _reservation_root(root: Path | None) -> Path:
    return root.resolve() if root is not None else DATA_LOCAL_ROOT / _RESERVATION_DIR


def _reservation_path(
    execution_id: str,
    content_object_dir: str,
    *,
    reservation_root: Path | None,
) -> Path:
    key = hashlib.sha256(
        f"{execution_id}|{content_object_dir}".encode("utf-8")
    ).hexdigest()
    return _reservation_root(reservation_root) / f"{key}.json"


def load_reserved_post_identity(
    execution_id: str,
    canonical_ref: str,
    *,
    reservation_root: Path | None = None,
) -> dict[str, Any]:
    relative = f"posts/{str(canonical_ref or '').strip().strip('/')}"
    return load_post_identity_reservation(
        validate_execution_id(execution_id),
        relative,
        reservation_root=reservation_root,
    )


def load_post_identity_reservation(
    execution_id: str,
    content_object_dir: str,
    *,
    reservation_root: Path | None,
) -> dict[str, Any]:
    path = _reservation_path(
        execution_id,
        content_object_dir,
        reservation_root=reservation_root,
    )
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise TypeError("pool delivery version reservation must be an object")
    assert_valid(
        payload,
        "execution",
        "pool_delivery_version_reservation",
        label=f"pool delivery version reservation:{execution_id}",
    )
    stable = {key: value for key, value in payload.items() if key != "reservationId"}
    if payload["reservationId"] != _digest(stable):
        raise ValueError("pool delivery version reservation digest mismatch")
    return payload


def reserve_post_identity(
    execution_id: str,
    *,
    carrier: str,
    object_ref: str,
    content_object_dir: str,
    object_dir: Path,
    publish_root: Path,
    reservation_root: Path | None,
) -> dict[str, Any]:
    path = _reservation_path(
        execution_id,
        content_object_dir,
        reservation_root=reservation_root,
    )
    if path.is_file():
        return load_post_identity_reservation(
            execution_id,
            content_object_dir,
            reservation_root=reservation_root,
        )
    manifest_path = object_dir / "manifest.json"
    manifest = read_json(manifest_path)
    if not isinstance(manifest, Mapping):
        raise TypeError("pool delivery manifest must be an object")
    canonical_ref = content_object_dir.removeprefix("posts/")
    planned = plan_content_pool_identity(
        source_manifest=manifest,
        canonical_ref=canonical_ref,
        publish_root=publish_root,
    )
    reserved_versions: list[int] = []
    for candidate in sorted(_reservation_root(reservation_root).glob("*.json")):
        row = read_json(candidate)
        if (
            isinstance(row, Mapping)
            and row.get("contentId") == planned["contentId"]
            and isinstance(row.get("version"), int)
        ):
            reserved_versions.append(int(row["version"]))
    version = int(planned["version"])
    if manifest.get("version") is None and reserved_versions:
        version = max(version, max(reserved_versions) + 1)
    if version in reserved_versions:
        raise ValueError("DATA.POOL.VERSION_CONFLICT: reserved content version exists")
    stable = {
        "schema": _RESERVATION_SCHEMA,
        "executionId": execution_id,
        "carrier": carrier,
        "objectRef": object_ref,
        "contentObjectDir": content_object_dir,
        "canonicalRef": canonical_ref,
        "contentId": planned["contentId"],
        "version": version,
        "sourceManifestSha256": _file_digest(manifest_path),
    }
    reservation = {"reservationId": _digest(stable), **stable}
    assert_valid(
        reservation,
        "execution",
        "pool_delivery_version_reservation",
        label=f"pool delivery version reservation:{execution_id}/{object_ref}",
    )
    encoded = (
        json.dumps(reservation, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        if path.read_bytes() != encoded:
            raise ValueError(
                "DATA.POOL.IDEMPOTENCY_CONFLICT: version reservation drift"
            ) from exc
        return reservation
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    return reservation


__all__ = [
    "load_post_identity_reservation",
    "load_reserved_post_identity",
    "reserve_post_identity",
]
