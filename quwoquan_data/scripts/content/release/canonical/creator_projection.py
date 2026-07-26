"""Project one referenced creator profile into a canonical consumer object."""
from __future__ import annotations

from pathlib import Path

import yaml

from core.io import write_json
from core.paths import CONTROL_PLANE_CREATOR_POOL_ROOT
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _safe_id,
)


def _creator_profile_path(creator_ref: str) -> Path:
    matches: list[Path] = []
    for path in sorted(
        (CONTROL_PLANE_CREATOR_POOL_ROOT / "profiles").rglob("*.creator.yaml")
    ):
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ObjectTransactionError(f"creator profile unreadable: {path}: {exc}") from exc
        if isinstance(payload, dict) and str(payload.get("creatorProfileId") or "") == creator_ref:
            matches.append(path)
    if len(matches) != 1:
        raise ObjectTransactionError(
            f"creator profile must resolve exactly once: {creator_ref}: found={len(matches)}"
        )
    return matches[0]


def project_creator_object(creator_ref: str, target: Path) -> Path:
    """Write the immutable consumer projection for one referenced creator."""
    creator_ref = _safe_id(creator_ref, label="creatorRef")
    source = _creator_profile_path(creator_ref)
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or str(payload.get("status") or "") != "active":
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
    write_json(
        target / "profile.json",
        {
            "schema": "quwoquan_data.creator_profile",
            "creatorId": creator_ref,
            "userId": str(payload.get("authorId") or ""),
            "authorId": str(payload.get("authorId") or ""),
            "subAccountId": str(payload.get("subAccountId") or payload.get("authorId") or ""),
            "displayName": str(payload.get("displayName") or ""),
            "userHandle": str(payload.get("userHandle") or ""),
            "avatarObjectKey": str(payload.get("avatarObjectKey") or ""),
            "headline": str(payload.get("headline") or ""),
            "bio": str(payload.get("bio") or ""),
            "creatorArchetype": str(payload.get("creatorArchetype") or ""),
            "publicProfileTagRefs": tag_refs,
            "disclosure": dict(payload.get("disclosure") or {}),
        },
    )
    write_json(target / "assets.refs.json", {"assets": []})
    (target / "works.refs.ndjson").write_text("", encoding="utf-8")
    return target


__all__ = ["project_creator_object"]
