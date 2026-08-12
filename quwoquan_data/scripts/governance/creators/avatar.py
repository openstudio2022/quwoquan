"""Materialize one creator avatar from canonical publish quality evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from core.image_variants import build_center_square_cover_derivative
from core.media_asset_url import is_cas_media_object_key
from core.paths import CONTROL_PLANE_CREATOR_POOL_ROOT, PUBLISH_ROOT
from core.schema import assert_valid
from governance.creators.avatar_materialization import (
    CreatorAvatarError,
    persist_creator_avatar,
)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CreatorAvatarError(f"JSON unreadable: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CreatorAvatarError(f"JSON root must be an object: {path}")
    return value


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _safe_id(value: str, *, label: str) -> str:
    normalized = str(value or "").strip()
    if (
        not normalized
        or normalized in {".", ".."}
        or "/" in normalized
        or "\\" in normalized
    ):
        raise CreatorAvatarError(f"invalid {label}: {value!r}")
    return normalized


def _safe_relative(value: str, *, label: str) -> Path:
    normalized = str(value or "").strip().strip("/")
    relative = Path(normalized)
    if (
        not normalized
        or relative.is_absolute()
        or ".." in relative.parts
        or any(part in {"", "."} for part in relative.parts)
    ):
        raise CreatorAvatarError(f"unsafe {label}: {value!r}")
    return relative


def _profile_path(creator_ref: str) -> Path:
    matches: list[Path] = []
    profiles = CONTROL_PLANE_CREATOR_POOL_ROOT / "profiles"
    for path in sorted(profiles.rglob("*.creator.yaml")):
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise CreatorAvatarError(
                f"creator profile unreadable: {path}: {exc}"
            ) from exc
        if (
            isinstance(value, Mapping)
            and str(value.get("creatorProfileId") or "") == creator_ref
        ):
            matches.append(path)
    if len(matches) != 1:
        raise CreatorAvatarError(
            f"creator profile must resolve exactly once: {creator_ref}: found={len(matches)}"
        )
    return matches[0]


def _source_root(source_object_ref: str) -> tuple[Path, Path]:
    relative = _safe_relative(source_object_ref, label="source-object-ref")
    if len(relative.parts) < 2 or relative.parts[0] not in {"entities", "posts"}:
        raise CreatorAvatarError(
            "source-object-ref must identify a canonical entities/** or posts/** object"
        )
    root = PUBLISH_ROOT / relative
    if not root.is_dir() or root.is_symlink():
        raise CreatorAvatarError(
            f"canonical source object missing: {relative.as_posix()}"
        )
    return root, relative


def _source_asset(
    source_root: Path,
    *,
    source_asset_id: str,
) -> tuple[dict[str, Any], Path, bytes, str]:
    refs_paths = [
        path
        for path in (source_root / "asset.refs.json", source_root / "assets.refs.json")
        if path.is_file()
    ]
    if len(refs_paths) != 1:
        raise CreatorAvatarError(
            "source object must own exactly one asset refs document"
        )
    assets = _read_json(refs_paths[0]).get("assets")
    matches = (
        [
            row
            for row in assets or []
            if isinstance(row, dict)
            and str(row.get("assetId") or "") == source_asset_id
        ]
        if isinstance(assets, list)
        else []
    )
    if len(matches) != 1:
        raise CreatorAvatarError(
            f"source asset must resolve exactly once: {source_asset_id}: found={len(matches)}"
        )
    row = dict(matches[0])
    digest = str(row.get("sha256") or "")
    object_key = str(row.get("objectKey") or "")
    byte_count = row.get("bytes")
    if (
        not is_cas_media_object_key(object_key)
        or not digest.startswith("sha256:")
        or not isinstance(byte_count, int)
        or isinstance(byte_count, bool)
        or byte_count <= 0
    ):
        raise CreatorAvatarError("source asset does not bind canonical CAS identity")
    physical = PUBLISH_ROOT / _safe_relative(object_key, label="source objectKey")
    if physical.is_symlink() or not physical.is_file():
        raise CreatorAvatarError(f"source CAS bytes missing: {object_key}")
    body = physical.read_bytes()
    if len(body) != byte_count or _sha256_bytes(body) != digest:
        raise CreatorAvatarError(f"source CAS bytes drifted: {object_key}")
    return row, physical, body, object_key


def _source_evidence(
    source_root: Path,
    *,
    source_asset_id: str,
    source_digest: str,
) -> tuple[dict[str, Any], Path, bytes, str]:
    matches: list[tuple[dict[str, Any], Path]] = []
    for path in sorted((source_root / "rights_snapshots").glob("*.json")):
        document = _read_json(path)
        source_asset = document.get("sourceAsset")
        if (
            str(document.get("assetId") or "") == source_asset_id
            and isinstance(source_asset, Mapping)
            and str(source_asset.get("sha256") or "") == source_digest
        ):
            matches.append((document, path))
    if len(matches) != 1:
        raise CreatorAvatarError(
            f"source evidence must resolve exactly once: {source_asset_id}: "
            f"found={len(matches)}"
        )
    document, path = matches[0]
    body = path.read_bytes()
    try:
        relative = path.relative_to(PUBLISH_ROOT).as_posix()
    except ValueError as exc:
        raise CreatorAvatarError(
            "source evidence is outside canonical publish"
        ) from exc
    return document, path, body, relative


def _source_asset_evidence(
    document: Mapping[str, object],
    *,
    source_asset_id: str,
    source_digest: str,
) -> Mapping[str, object]:
    if str(document.get("schema") or "") != "quwoquan_data.asset_rights_snapshot":
        raise CreatorAvatarError("source evidence schema is invalid")
    source_asset = document.get("sourceAsset")
    if not isinstance(source_asset, Mapping):
        raise CreatorAvatarError("source evidence is missing sourceAsset")
    if (
        str(document.get("assetId") or "") != source_asset_id
        or str(source_asset.get("sha256") or "") != source_digest
    ):
        raise CreatorAvatarError("source evidence identity drift")
    return source_asset


def _quality_evidence_document(
    *,
    asset_id: str,
    derivative: Mapping[str, object],
    source_evidence_ref: str,
    source_evidence_body: bytes,
) -> dict[str, object]:
    digest = str(derivative["sha256"])
    digest_hex = digest.removeprefix("sha256:")
    snapshot_digest = _sha256_bytes(source_evidence_body)
    return {
        "schema": "quwoquan_data.creator_avatar_quality_evidence",
        "assetId": asset_id,
        "manifestAsset": {"assetId": asset_id, "sha256": digest},
        "processResult": "completed",
        "qualityResult": "passed",
        "checks": {
            "format": "passed",
            "readable": "passed",
            "clarity": "passed",
            "safety": "passed",
        },
        "sourceEvidence": {
            "ref": source_evidence_ref,
            "sha256": snapshot_digest,
        },
        "asset": {
            "ref": f"cas/{digest_hex}.webp",
            "sha256": digest,
            "bytes": derivative["byteSize"],
            "mimeType": derivative["mimeType"],
            "width": derivative["width"],
            "height": derivative["height"],
        },
    }


def materialize_creator_avatar(
    *,
    creator_ref: str,
    source_object_ref: str,
    source_asset_id: str,
    confirm_non_identifiable_person: bool,
) -> dict[str, object]:
    """Derive, attest and project one creator avatar through canonical seams."""

    creator_ref = _safe_id(creator_ref, label="creator-ref")
    source_asset_id = _safe_id(source_asset_id, label="source-asset-id")
    if not confirm_non_identifiable_person:
        raise CreatorAvatarError(
            "--confirm-non-identifiable-person is required for avatar safety closure"
        )
    profile_path = _profile_path(creator_ref)
    source_root, source_relative = _source_root(source_object_ref)
    source_row, _, source_body, source_object_key = _source_asset(
        source_root,
        source_asset_id=source_asset_id,
    )
    source_digest = str(source_row["sha256"])
    source_evidence, _, source_evidence_body, source_evidence_ref = _source_evidence(
        source_root,
        source_asset_id=source_asset_id,
        source_digest=source_digest,
    )
    source_asset_evidence = _source_asset_evidence(
        source_evidence,
        source_asset_id=source_asset_id,
        source_digest=source_digest,
    )
    if source_asset_evidence.get("bytes") != len(source_body):
        raise CreatorAvatarError("source evidence byte identity drift")
    derivative = build_center_square_cover_derivative(source_body)
    if derivative is None:
        raise CreatorAvatarError(
            "source image cannot produce the canonical center-square cover without upscale"
        )
    digest = str(derivative["sha256"])
    digest_hex = digest.removeprefix("sha256:")
    asset_id = f"creator-avatar-{creator_ref}-{digest_hex[:16]}"
    object_key = (
        f"media/objects/sha256/{digest_hex[:2]}/{digest_hex[2:4]}/{digest_hex}.webp"
    )
    quality_evidence = _quality_evidence_document(
        asset_id=asset_id,
        derivative=derivative,
        source_evidence_ref=source_evidence_ref,
        source_evidence_body=source_evidence_body,
    )
    try:
        assert_valid(
            quality_evidence,
            "release",
            "creator_avatar_quality_evidence",
            label=f"creator avatar quality evidence {creator_ref}",
        )
    except (FileNotFoundError, ValueError) as exc:
        raise CreatorAvatarError(str(exc)) from exc
    evidence_ref = f"evidence/avatar_quality/{creator_ref}/{digest_hex}.json"
    avatar_asset = {
        "assetId": asset_id,
        "kind": "avatar",
        "sha256": digest,
        "objectKey": object_key,
        "bytes": int(derivative["byteSize"]),
        "mimeType": str(derivative["mimeType"]),
        "evidenceRef": evidence_ref,
    }
    created = persist_creator_avatar(
        creator_ref=creator_ref,
        profile_path=profile_path,
        publish_root=PUBLISH_ROOT,
        creator_pool_root=CONTROL_PLANE_CREATOR_POOL_ROOT,
        object_key=object_key,
        derivative_body=derivative["bytes"],
        evidence_ref=evidence_ref,
        evidence_document=quality_evidence,
        avatar_asset=avatar_asset,
    )

    return {
        "schema": "quwoquan_data.creator_avatar_materialization",
        "creatorRef": creator_ref,
        "sourceObjectRef": source_relative.as_posix(),
        "sourceAssetId": source_asset_id,
        "sourceSha256": source_digest,
        "sourceObjectKey": source_object_key,
        "sourceEvidenceRef": source_evidence_ref,
        "assetId": asset_id,
        "sha256": digest,
        "objectKey": object_key,
        "evidenceRef": evidence_ref,
        "cropBox": derivative["cropBox"],
        "sourceDimensions": [
            derivative["sourceWidth"],
            derivative["sourceHeight"],
        ],
        "dimensions": [derivative["width"], derivative["height"]],
        "mimeType": derivative["mimeType"],
        "policyVersion": derivative["policyVersion"],
        "created": created,
        "idempotent": not any(created.values()),
    }


__all__ = [
    "CreatorAvatarError",
    "materialize_creator_avatar",
]
