#!/usr/bin/env python3
"""按 ChatMockData conv_grid_N 成员列表重生成群合成头像 PNG（与生产 render-group-avatar 同布局）。"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SERVICE_ROOT = ROOT / "quwoquan_service"
MEDIA_ROOT = (
    SERVICE_ROOT
    / "contracts"
    / "metadata"
    / "_shared"
    / "test_fixtures"
    / "media"
    / "media"
)
RENDER_PKG = "./cmd/render-group-avatar"

_FALLBACK_POOL = [
    "avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png",
    "avatar/s/archived-avatar/user/fixture_user_friend/v1/avatar.png",
    "avatar/s/archived-avatar/user/fixture_user_photo/v1/avatar.png",
    "avatar/s/archived-avatar/user/fixture_user_travel/v1/avatar.png",
    "avatar/s/archived-avatar/user/fixture_user_article/v1/avatar.png",
]


def _stable_mock_avatar_index(object_key: str) -> int:
    digest = hashlib.sha256(object_key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % len(_FALLBACK_POOL)


def _resolve_mock_avatar_path(object_key: str) -> Path:
    normalized = object_key.lstrip("/")
    if normalized.startswith("media/avatar/s/mock/"):
        fallback = _FALLBACK_POOL[_stable_mock_avatar_index(normalized)]
        candidate = MEDIA_ROOT / fallback
        if candidate.is_file():
            return candidate
    direct = MEDIA_ROOT / normalized.removeprefix("media/")
    if direct.is_file():
        return direct
    raise FileNotFoundError(f"avatar fixture missing for {object_key}")


def _grid_member_user_ids(count: int) -> list[str]:
    user_ids: list[str] = ["user_001"]
    for index in range(2, count + 1):
        user_ids.append(f"grid_{count}_member_{index}")
    return user_ids


def _avatar_object_key(user_id: str) -> str:
    return f"media/avatar/s/mock/user/{user_id}/v1/avatar.png"


def render_conv_grid(n: int) -> Path:
    member_ids = _grid_member_user_ids(n)[:9]
    input_paths = [_resolve_mock_avatar_path(_avatar_object_key(user_id)) for user_id in member_ids]
    output_key = f"media/avatar/s/archived-avatar/conversation/conv_grid_{n}/v1/mock.png"
    output_path = MEDIA_ROOT / output_key.removeprefix("media/")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["go", "run", RENDER_PKG, str(output_path), *[str(path) for path in input_paths]]
    subprocess.run(cmd, cwd=SERVICE_ROOT, check=True)
    return output_path


def main() -> int:
    hashes: dict[int, str] = {}
    for n in range(1, 17):
        output = render_conv_grid(n)
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        hashes[n] = digest
        print(f"conv_grid_{n}: {output.relative_to(ROOT)} sha256={digest[:12]}...")
    unique = len(set(hashes.values()))
    if unique < 3:
        print("FAIL: conv_grid composites are not sufficiently distinct", file=sys.stderr)
        return 1
    print(f"OK: regenerated conv_grid_1..16 ({unique} unique composites)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
