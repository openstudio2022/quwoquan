"""System creator profiles with avatarAsset must have matching publish CAS bytes."""

from __future__ import annotations

from pathlib import Path

import yaml

from core import paths


def test_system_creator_avatar_cas_has_publish_bytes() -> None:
    pool = (
        paths.REPO_ROOT
        / "quwoquan_data"
        / "control_plane"
        / "governance"
        / "creator_pool"
        / "profiles"
        / "system_builtin"
    )
    # Read the tracked baseline publish tree, not the pytest-isolated PUBLISH_ROOT.
    publish = paths.REPO_ROOT / "quwoquan_data" / "publish"
    missing: list[str] = []
    checked = 0
    for path in sorted(pool.glob("*.creator.yaml")):
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        avatar = payload.get("avatarAsset")
        if not isinstance(avatar, dict):
            continue
        checked += 1
        object_key = str(avatar.get("objectKey") or "").strip()
        expected_bytes = avatar.get("bytes")
        physical = publish / object_key
        if (
            not object_key
            or not physical.is_file()
            or not isinstance(expected_bytes, int)
            or physical.stat().st_size != expected_bytes
        ):
            missing.append(f"{path.name}:{object_key}")
    assert checked >= 4, f"expected system avatars, found={checked}"
    assert not missing, "system creator avatar CAS missing: " + ", ".join(missing)
