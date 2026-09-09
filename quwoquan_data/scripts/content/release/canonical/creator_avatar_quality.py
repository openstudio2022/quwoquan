"""Avatar identity, CAS, readability and quality closure for creators."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path

from core.media_asset_url import sha256_file
from content.release.canonical.post_transaction_sources import read_object_sources
from content.release.canonical.object_transaction_contract import ObjectTransactionError, _safe_rel


_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _object(path: Path) -> Mapping[str, object] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, Mapping) else None


def _avatar_body_readable(root: Path, asset: Mapping[str, object]) -> bool:
    """普通消费只读 creator 包的精确随体字节，不依赖采集库。"""
    try:
        relative = _safe_rel(str(asset.get("path") or ""), label="avatar.path")
        entry = root / relative
        return relative.parts[0] == "media" and not entry.is_symlink() and entry.is_file() and entry.stat().st_size == asset.get("bytes") and sha256_file(entry) == asset.get("sha256")
    except (ObjectTransactionError, OSError, ValueError):
        return False


def creator_avatar_quality_issues(
    publish_root: Path,
    *,
    creator_refs: list[str] | tuple[str, ...] | None = None,
) -> list[dict[str, str]]:
    """Require one readable, identity-bound avatar without usage-scope gates."""

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
            issues.append({"code": "creator_avatar_missing", "ref": creator_ref})
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
        matches = (
            [
                row
                for row in assets or []
                if isinstance(row, Mapping)
                and row.get("assetId") == asset_id
                and row.get("kind") == "avatar"
                and row.get("sha256") == digest
            ]
            if isinstance(assets, list)
            else []
        )
        if len(matches) != 1:
            issues.append(
                {"code": "creator_avatar_asset_ref_missing", "ref": creator_ref}
            )
            continue
        byte_count = matches[0].get("bytes")
        mime_type = str(matches[0].get("mimeType") or "")
        if (
            not isinstance(byte_count, int)
            or isinstance(byte_count, bool)
            or not mime_type.startswith("image/")
            or not _avatar_body_readable(root, matches[0])
        ):
            issues.append({"code": "creator_avatar_cas_invalid", "ref": creator_ref})
            continue
        try:
            sources = read_object_sources(root, profile)
            evidence_matches = [
                row for source in sources if source["ref"] in matches[0].get("sourceRefs", [])
                for row in source["assets"] if row.get("assetId") == asset_id and row.get("sha256") == digest
            ]
        except (ObjectTransactionError, OSError, ValueError):
            evidence_matches = []
        if not evidence_matches:
            issues.append(
                {"code": "creator_avatar_quality_evidence_missing", "ref": creator_ref}
            )
    return issues


__all__ = ["creator_avatar_quality_issues"]
