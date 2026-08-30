"""Small, decodable media payloads for contract tests."""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path

import yaml
from core.content_library import MEDIA_KIND, admit_library_bytes, library_cas_path
from core.paths import CONTROL_PLANE_CREATOR_POOL_ROOT


_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/"
    "iZk9HQAAAABJRU5ErkJggg=="
)


def tiny_png_bytes() -> bytes:
    return _TINY_PNG


def admit_media_body(body: bytes, *, library_root: Path | None = None) -> str:
    """Give the library a media body a test owns, and return the digest to cite.

    The preferred way for a test to satisfy a media reference: the digest comes
    from the bytes, so the reference and the holding cannot disagree.
    """

    admit_library_bytes(body, kind=MEDIA_KIND, library_root=library_root)
    return "sha256:" + hashlib.sha256(body).hexdigest()


def seed_media_holding(
    sha256: str,
    *,
    size: int,
    library_root: Path | None = None,
) -> Path:
    """Place the bytes one canonical media reference claims into the library.

    Canonical objects record media by digest and the library owns the bodies, so
    a test that exercises a consumer of those references has to stand the holding
    up first. Writing the entry directly is what lets a test honour a digest that
    was frozen elsewhere — admission would demand the original bytes, which no
    longer live anywhere the test tree can reach.
    """

    entry = library_cas_path(MEDIA_KIND, sha256, library_root=library_root)
    if entry.is_file() and entry.stat().st_size == size:
        return entry
    if size < len(_TINY_PNG):
        raise ValueError(f"media holding is too small to carry a decodable body: {size}")
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_bytes(_TINY_PNG + b"\0" * (size - len(_TINY_PNG)))
    return entry


def seed_system_creator_avatar_holding(creator_profile_id: str) -> str:
    """Stand up the avatar holding one system creator profile already cites.

    These digests are frozen in the creator pool and the bodies belong to the
    library, so a test that projects such a creator has to make the library hold
    them first. Returns the digest the profile records.
    """

    profiles = CONTROL_PLANE_CREATOR_POOL_ROOT / "profiles"
    for path in sorted(profiles.rglob("*.creator.yaml")):
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if (
            not isinstance(payload, dict)
            or str(payload.get("creatorProfileId") or "") != creator_profile_id
        ):
            continue
        avatar = payload.get("avatarAsset")
        if not isinstance(avatar, dict):
            raise ValueError(f"creator profile has no avatarAsset: {creator_profile_id}")
        sha256 = str(avatar.get("sha256") or "")
        size = avatar.get("bytes")
        if not sha256 or not isinstance(size, int):
            raise ValueError(f"creator avatarAsset is not addressable: {creator_profile_id}")
        seed_media_holding(sha256, size=size)
        return sha256
    raise ValueError(f"creator profile not found: {creator_profile_id}")
