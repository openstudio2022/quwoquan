"""Project one referenced creator profile into a canonical consumer object."""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Mapping
from pathlib import Path

import yaml
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _safe_id,
    _safe_rel,
)
from core.content_library import MediaHoldingError, resolve_media_holding
from core.io import write_json
from core.media_asset_url import is_cas_media_object_key
from core.paths import CONTROL_PLANE_CREATOR_POOL_ROOT

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _creator_profile_path(creator_ref: str) -> Path:
    matches: list[Path] = []
    for path in sorted(
        (CONTROL_PLANE_CREATOR_POOL_ROOT / "profiles").rglob("*.creator.yaml")
    ):
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ObjectTransactionError(
                f"creator profile unreadable: {path}: {exc}"
            ) from exc
        if (
            isinstance(payload, dict)
            and str(payload.get("creatorProfileId") or "") == creator_ref
        ):
            matches.append(path)
    if len(matches) != 1:
        raise ObjectTransactionError(
            f"creator profile must resolve exactly once: {creator_ref}: found={len(matches)}"
        )
    return matches[0]


def _avatar_asset_projection(
    payload: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, object], Path] | None:
    raw = payload.get("avatarAsset")
    if raw is None:
        return None
    expected_fields = {
        "assetId",
        "kind",
        "sha256",
        "objectKey",
        "bytes",
        "mimeType",
        "evidenceRef",
    }
    if not isinstance(raw, Mapping) or set(raw) != expected_fields:
        raise ObjectTransactionError(
            "creator avatarAsset must bind identity, private CAS, bytes, MIME and quality evidence"
        )
    asset_id = str(raw.get("assetId") or "").strip()
    kind = str(raw.get("kind") or "").strip()
    sha256 = str(raw.get("sha256") or "").strip()
    object_key = str(raw.get("objectKey") or "").strip()
    byte_count = raw.get("bytes")
    mime_type = str(raw.get("mimeType") or "").strip()
    evidence_ref = _safe_rel(
        str(raw.get("evidenceRef") or ""),
        label="avatarAsset.evidenceRef",
    )
    if (
        not asset_id
        or kind != "avatar"
        or not _SHA256_RE.fullmatch(sha256)
        or not is_cas_media_object_key(object_key)
        or not isinstance(byte_count, int)
        or isinstance(byte_count, bool)
        or byte_count <= 0
        or not mime_type.startswith("image/")
    ):
        raise ObjectTransactionError(
            "creator avatarAsset requires traceable canonical image CAS metadata"
        )
    digest = sha256.removeprefix("sha256:")
    if digest not in Path(object_key).name:
        raise ObjectTransactionError(
            "creator avatarAsset objectKey does not bind sha256"
        )
    # The library is content-addressed and verifies a body against its digest at
    # admission, so reaching the entry at this digest is the identity check;
    # re-hashing it here would only re-derive the address it was found under.
    try:
        resolve_media_holding(sha256, expected_bytes=byte_count)
    except (MediaHoldingError, ValueError) as exc:
        raise ObjectTransactionError(
            "creator avatarAsset body is not reachable in the content library"
        ) from exc
    evidence_source = CONTROL_PLANE_CREATOR_POOL_ROOT / evidence_ref
    try:
        evidence = json.loads(evidence_source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ObjectTransactionError(
            f"creator avatarAsset quality evidence unreadable: {evidence_source}"
        ) from exc
    manifest_asset = (
        evidence.get("manifestAsset") if isinstance(evidence, Mapping) else None
    )
    if (
        not isinstance(manifest_asset, Mapping)
        or str(manifest_asset.get("assetId") or "") != asset_id
        or str(manifest_asset.get("sha256") or "") != sha256
    ):
        raise ObjectTransactionError(
            "creator avatarAsset quality evidence identity drift"
        )
    profile_ref = {"assetId": asset_id, "kind": kind, "sha256": sha256}
    asset_ref = {
        **profile_ref,
        "objectKey": object_key,
        "bytes": byte_count,
        "mimeType": mime_type,
    }
    return profile_ref, asset_ref, evidence_source


def project_creator_object(creator_ref: str, target: Path) -> Path:
    """Write the immutable consumer projection for one referenced creator."""
    creator_ref = _safe_id(creator_ref, label="creatorRef")
    source = _creator_profile_path(creator_ref)
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ObjectTransactionError(f"creator profile is invalid: {creator_ref}")
    version = payload.get("version")
    admission = payload.get("admission")
    if (
        str(payload.get("status") or "") != "active"
        or not isinstance(version, int)
        or isinstance(version, bool)
        or version < 1
        or not isinstance(admission, Mapping)
        or admission.get("processResult") != "completed"
        or admission.get("qualityResult") != "passed"
        or not str(admission.get("evidenceRef") or "").strip()
        or not _SHA256_RE.fullmatch(
            str(admission.get("evidenceDigest") or "").strip()
        )
        or "usageScope" in admission
    ):
        raise ObjectTransactionError(f"creator profile is not active: {creator_ref}")
    target.mkdir(parents=True, exist_ok=True)
    tag_refs = sorted(
        {
            str(item).strip()
            for item in payload.get("publicProfileTagRefs") or []
            if str(item).strip()
        }
    )
    write_json(
        target / "_creator.json",
        {
            "schema": "quwoquan_data.creator_object",
            "creatorId": creator_ref,
            "profileRef": "profile.json",
            "assetsRef": "assets.refs.json",
            "worksRefsRef": "works.refs.ndjson",
            "tagRefs": tag_refs,
            "entityRefs": [],
        },
    )
    profile: dict[str, object] = {
        "schema": "quwoquan_data.creator_profile",
        "creatorId": creator_ref,
        "userId": str(payload.get("authorId") or ""),
        "authorId": str(payload.get("authorId") or ""),
        "version": version,
        "admission": dict(admission),
        "status": "active",
        "personaId": str(
            payload.get("personaId") or payload.get("authorId") or ""
        ),
        "displayName": str(payload.get("displayName") or ""),
        "userHandle": str(payload.get("userHandle") or ""),
        "headline": str(payload.get("headline") or ""),
        "bio": str(payload.get("bio") or ""),
        "creatorArchetype": str(payload.get("creatorArchetype") or ""),
        "publicProfileTagRefs": tag_refs,
        "disclosure": dict(payload.get("disclosure") or {}),
    }
    avatar_projection = _avatar_asset_projection(payload)
    asset_refs: list[dict[str, object]] = []
    if avatar_projection is not None:
        avatar_asset, asset_ref, evidence_source = avatar_projection
        profile["avatarAsset"] = avatar_asset
        asset_refs.append(asset_ref)
        rights_root = target / "rights_snapshots"
        rights_root.mkdir(parents=True, exist_ok=True)
        # Media closure keeps one owner-bound evidence file in its existing
        # internal folder. Avatar eligibility is already decided by identity,
        # readability and quality; this file is never interpreted as a
        # Research/Commercial scope.
        shutil.copy2(evidence_source, rights_root / evidence_source.name)
    write_json(target / "profile.json", profile)
    write_json(target / "assets.refs.json", {"assets": asset_refs})
    (target / "works.refs.ndjson").write_text("", encoding="utf-8")
    return target


__all__ = ["project_creator_object"]
