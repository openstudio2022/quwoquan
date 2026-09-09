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
    _digest_file,
)
from core.content_library import MediaHoldingError, resolve_media_holding
from core.io import write_json
from core.media_asset_url import is_cas_media_object_key
from core.paths import CONTROL_PLANE_CREATOR_POOL_ROOT

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _creator_profile_path(creator_ref: str, *, creator_pool_root: Path) -> Path:
    matches: list[Path] = []
    for path in sorted((creator_pool_root / "profiles").rglob("*.creator.yaml")):
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
    *,
    creator_pool_root: Path,
    publish_root: Path | None,
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
    # A generation being bootstrapped resolves against the tree it is building
    # instead, because its bodies were admitted from an explicitly named library
    # that the ambient one knows nothing about.
    if publish_root is None:
        try:
            resolve_media_holding(sha256, expected_bytes=byte_count)
        except (MediaHoldingError, ValueError) as exc:
            raise ObjectTransactionError(
                "creator avatarAsset body is not reachable in the content library"
            ) from exc
    else:
        body = publish_root / _safe_rel(object_key, label="avatarAsset.objectKey")
        if (
            body.is_symlink()
            or not body.is_file()
            or body.stat().st_size != byte_count
        ):
            raise ObjectTransactionError(
                "creator avatarAsset body is not reachable in the generation tree"
            )
    evidence_source = creator_pool_root / evidence_ref
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


def _carry_avatar_source(*, target: Path, asset_ref: dict[str, object], evidence_source: Path, publish_root: Path | None) -> dict[str, object]:
    """把现有头像字节及原权利证据随体转录，不生成许可或新审核。"""
    from core.schema import assert_valid

    key = str(asset_ref["objectKey"])
    body = (publish_root / key) if publish_root is not None else resolve_media_holding(str(asset_ref["sha256"]))
    relative = Path("media") / ("avatar" + Path(key).suffix)
    destination = target / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(body, destination)
    if _digest_file(destination) != asset_ref["sha256"] or destination.stat().st_size != asset_ref["bytes"]:
        raise ObjectTransactionError("DATA.PUBLISH.CARRIED_MEDIA_DRIFT: creator avatar")
    original = json.loads(evidence_source.read_bytes())
    rights = original.get("commercialRights")
    if not isinstance(rights, Mapping):
        raise ObjectTransactionError("DATA.PUBLISH.SOURCE_EVIDENCE_INVALID: creator avatar")
    source_ref = "sources/avatar/source.json"
    source_root = target / "sources/avatar"
    source_root.mkdir(parents=True, exist_ok=True)
    evidence = source_root / "evidence.json"
    shutil.copy2(evidence_source, evidence)
    source = {
        "schema": "quwoquan_data.publish_source", "sourceId": "avatar",
        "sourceUrl": str(rights.get("canonicalFilePage") or rights.get("source") or ""),
        "sourceUseMode": str(rights.get("sourceUseMode") or ""),
        "fetchedAt": str(rights.get("fetchedAt") or ""),
        "metadata": dict(original),
        "assets": [{**dict(rights), "assetId": asset_ref["assetId"], "sha256": asset_ref["sha256"], "bytes": asset_ref["bytes"]}],
        "evidence": [{"path": "evidence.json", "sha256": _digest_file(evidence), "bytes": evidence.stat().st_size, "kind": "acquisition_receipt"}],
    }
    assert_valid(source, "publish", "source")
    write_json(source_root / "source.json", source)
    return {key: value for key, value in asset_ref.items() if key != "objectKey"} | {"path": relative.as_posix(), "sourceRefs": [source_ref]}


def project_creator_object(
    creator_ref: str,
    target: Path,
    *,
    publish_root: Path | None = None,
    creator_pool_root: Path | None = None,
) -> Path:
    """Write the immutable consumer projection for one referenced creator.

    Both roots default to the repository's own control plane and content library.
    A generation bootstrap names them explicitly instead, so one projection writer
    serves the ambient tree and an isolated generation without either inheriting
    the other's holdings.
    """

    creator_ref = _safe_id(creator_ref, label="creatorRef")
    pool_root = (
        Path(creator_pool_root)
        if creator_pool_root is not None
        else CONTROL_PLANE_CREATOR_POOL_ROOT
    )
    source = _creator_profile_path(creator_ref, creator_pool_root=pool_root)
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
    avatar_projection = _avatar_asset_projection(
        payload,
        creator_pool_root=pool_root,
        publish_root=Path(publish_root) if publish_root is not None else None,
    )
    asset_refs: list[dict[str, object]] = []
    if avatar_projection is not None:
        avatar_asset, asset_ref, evidence_source = avatar_projection
        carried = _carry_avatar_source(
            target=target, asset_ref=asset_ref, evidence_source=evidence_source,
            publish_root=Path(publish_root) if publish_root is not None else None,
        )
        profile["avatarAsset"] = avatar_asset
        profile["sourceRefs"] = list(carried["sourceRefs"])
        asset_refs.append(carried)
    profile["assets"] = asset_refs
    write_json(target / "profile.json", profile)
    write_json(target / "assets.refs.json", {"assets": asset_refs})
    (target / "works.refs.ndjson").write_text("", encoding="utf-8")
    return target


__all__ = ["project_creator_object"]
