"""Commercial avatar/CAS/rights closure for release-selected creators."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path

from content.release.canonical.creator_avatar_rights import (
    creator_avatar_rights_issue,
)
from core.media_asset_url import is_cas_media_object_key, sha256_file


_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _object(path: Path) -> Mapping[str, object] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, Mapping) else None


def creator_commercial_closure_issues(
    publish_root: Path,
    *,
    creator_refs: list[str] | tuple[str, ...] | None = None,
) -> list[dict[str, str]]:
    """Require every selected public creator to bind one traceable avatar."""

    creators_root = publish_root / "creators"
    selected = (
        sorted(set(creator_refs))
        if creator_refs is not None
        else sorted(path.parent.name for path in creators_root.glob("*/_creator.json"))
    )
    issues: list[dict[str, str]] = []
    for creator_ref in selected:
        root = creators_root / creator_ref
        profile = _object(root / "profile.json")
        assets_document = _object(root / "assets.refs.json")
        avatar = profile.get("avatarAsset") if profile else None
        if not isinstance(avatar, Mapping):
            issues.append(
                {"code": "creator_avatar_missing", "ref": creator_ref}
            )
            continue
        asset_id = str(avatar.get("assetId") or "")
        digest = str(avatar.get("sha256") or "")
        if (
            not asset_id
            or avatar.get("kind") != "avatar"
            or not _SHA256_RE.fullmatch(digest)
        ):
            issues.append(
                {"code": "creator_avatar_identity_invalid", "ref": creator_ref}
            )
            continue
        assets = assets_document.get("assets") if assets_document else None
        matches = [
            row
            for row in assets or []
            if isinstance(row, Mapping)
            and row.get("assetId") == asset_id
            and row.get("kind") == "avatar"
            and row.get("sha256") == digest
        ] if isinstance(assets, list) else []
        if len(matches) != 1:
            issues.append(
                {"code": "creator_avatar_asset_ref_missing", "ref": creator_ref}
            )
            continue
        object_key = str(matches[0].get("objectKey") or "")
        byte_count = matches[0].get("bytes")
        mime_type = str(matches[0].get("mimeType") or "")
        physical = publish_root / object_key
        if (
            not is_cas_media_object_key(object_key)
            or not physical.is_file()
            or sha256_file(physical) != digest
            or not isinstance(byte_count, int)
            or isinstance(byte_count, bool)
            or physical.stat().st_size != byte_count
            or not mime_type.startswith("image/")
        ):
            issues.append(
                {"code": "creator_avatar_cas_invalid", "ref": creator_ref}
            )
            continue
        rights_matches: list[Mapping[str, object]] = []
        for path in sorted((root / "rights_snapshots").glob("*.json")):
            rights = _object(path)
            manifest_asset = rights.get("manifestAsset") if rights else None
            if (
                isinstance(manifest_asset, Mapping)
                and manifest_asset.get("assetId") == asset_id
                and manifest_asset.get("sha256") == digest
            ):
                rights_matches.append(rights)
        if len(rights_matches) != 1:
            issues.append(
                {"code": "creator_avatar_rights_missing", "ref": creator_ref}
            )
            continue
        rights_issue = creator_avatar_rights_issue(
            rights_matches[0],
            asset_id=asset_id,
            sha256=digest,
            object_key=object_key,
            byte_count=byte_count,
            mime_type=mime_type,
        )
        if rights_issue:
            issues.append({"code": rights_issue, "ref": creator_ref})
    return issues


__all__ = ["creator_commercial_closure_issues"]
