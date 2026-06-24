#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BUNDLE_PATH = ROOT / "deploy" / "shared" / "gamma_curated_media_bundle.json"
HOME_SHOWCASE_FIXTURE_PATH = (
    ROOT
    / "quwoquan_service"
    / "contracts"
    / "metadata"
    / "content"
    / "test_fixtures"
    / "scenarios"
    / "content_scenarios.lite.json"
)
LOCAL_ROOT_CA = (
    ROOT
    / "state"
    / "local"
    / "alpha_stack"
    / "caddy-data"
    / "caddy"
    / "pki"
    / "authorities"
    / "local"
    / "root.crt"
)
DEFAULT_BASE_URL = "https://localhost:17100"


def _curl_status(url: str, *, range_probe: bool = False) -> str:
    cmd = ["curl", "-fsS", "--cacert", str(LOCAL_ROOT_CA), "-o", "/dev/null", "-w", "%{http_code}"]
    if range_probe:
        cmd.extend(["-H", "Range: bytes=0-1"])
    else:
        cmd.append("-I")
    cmd.append(url)
    result = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        return f"curl-failed:{detail[-1] if detail else result.returncode}"
    return result.stdout.strip()


def _load_media_objects() -> list[dict[str, Any]]:
    data = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
    objects = data.get("mediaObjects")
    if not isinstance(objects, list):
        raise ValueError(f"{BUNDLE_PATH} missing mediaObjects list")
    return [item for item in objects if isinstance(item, dict)]


def _collect_home_showcase_media_refs() -> set[str]:
    data = json.loads(HOME_SHOWCASE_FIXTURE_PATH.read_text(encoding="utf-8"))
    seed_sets = data.get("seedSets")
    if not isinstance(seed_sets, dict):
        raise ValueError(f"{HOME_SHOWCASE_FIXTURE_PATH} missing seedSets")
    showcase = seed_sets.get("home_showcase_core")
    if not isinstance(showcase, dict):
        raise ValueError(f"{HOME_SHOWCASE_FIXTURE_PATH} missing home_showcase_core")
    posts = showcase.get("posts")
    if not isinstance(posts, list):
        raise ValueError(f"{HOME_SHOWCASE_FIXTURE_PATH} missing home_showcase_core.posts")

    refs: set[str] = set()

    def add(value: Any) -> None:
        if not isinstance(value, str):
            return
        object_key = value.strip().lstrip("/")
        if object_key.startswith("media/"):
            refs.add(object_key)

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if key in {
                    "avatarUrl",
                    "authorAvatarUrl",
                    "authorBackgroundUrl",
                    "coverUrl",
                    "thumbnailUrl",
                    "videoUrl",
                    "imageUrl",
                }:
                    add(nested)
                else:
                    walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)
        else:
            add(value)

    for post in posts:
        walk(post)
    return refs


def main() -> int:
    issues: list[str] = []
    if not BUNDLE_PATH.is_file():
        issues.append(f"media bundle missing: {BUNDLE_PATH}")
    if not HOME_SHOWCASE_FIXTURE_PATH.is_file():
        issues.append(f"home showcase fixture missing: {HOME_SHOWCASE_FIXTURE_PATH}")
    if not LOCAL_ROOT_CA.is_file():
        issues.append(f"alpha local root CA missing: {LOCAL_ROOT_CA}")
    if issues:
        print("[verify_alpha_media_fixture_surface] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    base_url = DEFAULT_BASE_URL.rstrip("/")
    checked = 0
    video_checked = 0
    bundle_objects = _load_media_objects()
    object_keys: set[str] = set()
    for item in bundle_objects:
        object_key = str(item.get("objectKey") or "").strip().lstrip("/")
        relative_path = str(item.get("relativePath") or "").strip()
        if not object_key:
            issues.append(f"empty objectKey in {BUNDLE_PATH}")
            continue
        if relative_path and not (ROOT / relative_path).is_file():
            issues.append(f"{object_key} source file missing: {relative_path}")
            continue
        object_keys.add(object_key)

    home_refs = _collect_home_showcase_media_refs()
    object_keys.update(home_refs)

    for object_key in sorted(object_keys):
        checked += 1
        is_video = object_key.startswith("media/video/")
        status = _curl_status(
            f"{base_url}/{object_key}",
            range_probe=is_video,
        )
        expected = "206" if is_video else "200"
        if is_video:
            video_checked += 1
        if status != expected:
            issues.append(
                f"{object_key} expected HTTP {expected}, got {status}: {base_url}/{object_key}"
            )

    if issues:
        print("[verify_alpha_media_fixture_surface] FAIL")
        for issue in issues[:50]:
            print(f"  - {issue}")
        if len(issues) > 50:
            print(f"  - ... {len(issues) - 50} more")
        return 1

    print(
        "[verify_alpha_media_fixture_surface] OK "
        f"checked={checked} homeRefs={len(home_refs)} "
        f"videoRange={video_checked} base={base_url}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
