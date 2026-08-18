"""System creator avatars must resolve to the content library, never to publish."""

from __future__ import annotations

import pytest
import yaml
from core import paths
from core.content_library import MediaHoldingError, resolve_media_holding
from support.media_fixture import seed_media_holding


def test_system_creator_avatars_resolve_to_content_library_holdings() -> None:
    pool = (
        paths.REPO_ROOT
        / "quwoquan_data"
        / "control_plane"
        / "governance"
        / "creator_pool"
        / "profiles"
        / "system_builtin"
    )
    publish = paths.REPO_ROOT / "quwoquan_data" / "publish"
    checked = 0
    for path in sorted(pool.glob("*.creator.yaml")):
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        avatar = payload.get("avatarAsset")
        if not isinstance(avatar, dict):
            continue
        checked += 1
        sha256 = str(avatar.get("sha256") or "").strip()
        object_key = str(avatar.get("objectKey") or "").strip()
        expected_bytes = avatar.get("bytes")
        assert sha256.startswith("sha256:"), f"{path.name}: avatar must record a digest"
        assert isinstance(expected_bytes, int) and expected_bytes > 0, (
            f"{path.name}: avatar must record its byte count"
        )
        assert sha256.removeprefix("sha256:") in object_key, (
            f"{path.name}: objectKey must be addressed by the avatar digest"
        )
        # The versioned tree records the reference and the library owns the body,
        # so the profile's own object key must not name a file inside publish.
        assert not (publish / object_key).exists(), (
            f"{path.name}: avatar body must not live in canonical publish"
        )

        seed_media_holding(sha256, size=expected_bytes)
        resolved = resolve_media_holding(sha256, expected_bytes=expected_bytes)
        assert resolved.is_file()

        with pytest.raises(MediaHoldingError):
            resolve_media_holding(sha256, expected_bytes=expected_bytes + 1)

    assert checked >= 4, f"expected system avatars, found={checked}"
