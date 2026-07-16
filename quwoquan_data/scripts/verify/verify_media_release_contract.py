#!/usr/bin/env python3
"""Static media release contract guard."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


violations: list[str] = []
for base in (
    ROOT / "quwoquan_data" / "scripts",
    ROOT / "quwoquan_service" / "services" / "content-service",
    ROOT / "quwoquan_app" / "lib",
):
    for path in sorted(base.rglob("*")):
        if path.suffix not in {".py", ".go", ".dart"}:
            continue
        text = read(path)
        if re.search(r"https://(?:cdn|origin)\.example", text):
            violations.append(f"{path.relative_to(ROOT)}: forbidden stub media domain")

required = {
    ROOT / "quwoquan_data" / "scripts" / "ship" / "handler.py": [
        "_load_release",
        "_release_media_object_keys",
        "object_keys=_release_media_object_keys(release)",
        '"media-sync.json"',
        '"data-release"',
    ],
    ROOT / "quwoquan_data" / "scripts" / "ship" / "consistency.py": [
        "_cas_issues",
        "asset_ref_path_escape",
        "non_cas_asset_ref",
        "dangling_asset_ref",
    ],
    ROOT / "quwoquan_data" / "scripts" / "core" / "media_asset_url.py": [
        "is_cas_media_object_key",
        "materialize_release_media",
        "quwoquan_data.release_media_manifest/1",
    ],
    ROOT / "quwoquan_service" / "services" / "content-service" / "cmd" / "import" / "loader.go": [
        "ArticleAssetManifest",
        "AssetManifest",
    ],
    ROOT / "quwoquan_app" / "lib" / "core" / "media" / "asset_url_resolver.dart": [
        "resolveManifestUrls",
        "objectKey",
    ],
}

for path, needles in required.items():
    text = read(path) if path.is_file() else ""
    for needle in needles:
        if needle not in text:
            violations.append(f"{path.relative_to(ROOT)}: missing required media contract marker {needle!r}")

for path in (
    ROOT / "quwoquan_data" / "scripts" / "ship" / "handler.py",
    ROOT / "quwoquan_data" / "scripts" / "ship" / "consistency.py",
    ROOT / "quwoquan_data" / "scripts" / "core" / "media_asset_url.py",
):
    text = read(path)
    for legacy in ("env_releases", "sample_bundles", "media/library", "libraryPath", "cdnUrl"):
        if legacy in text:
            violations.append(f"{path.relative_to(ROOT)}: legacy media path/field {legacy!r} is forbidden")

https_only_files = [
    ROOT / "quwoquan_app" / "lib" / "cloud" / "runtime" / "cloud_runtime_config.dart",
    ROOT / "quwoquan_app" / "test" / "core" / "media" / "content_media_url_test.dart",
    ROOT / "quwoquan_app" / "test" / "core" / "media" / "avatar_image_url_test.dart",
    ROOT
    / "quwoquan_app"
    / "test"
    / "ui"
    / "content"
    / "post"
    / "contract"
    / "post_view_projection_contract_test.dart",
]
for path in https_only_files:
    text = read(path) if path.is_file() else ""
    if "http://" in text:
        violations.append(f"{path.relative_to(ROOT)}: local media/runtime URLs must use https://")

if violations:
    print("[media-release-contract] FAIL")
    for violation in violations:
        print(f"  - {violation}")
    sys.exit(2)

print("[media-release-contract] OK")
