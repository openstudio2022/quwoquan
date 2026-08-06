#!/usr/bin/env python3
"""Verify the canonical App content presentation boundaries.

The generic pageflip engine lives in ``lib/design_system/pageflip``.  Its
business hosts live in canonical object presentation layers.  Retired
``lib/ui/content`` and ``lib/components`` paths are negative guards only; they
must never become a second positive scan root.
"""

from __future__ import annotations

import sys
from pathlib import Path

import sys
from pathlib import Path

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import APP_ROOT, REPO_ROOT, SCRIPTS_ROOT

LEGACY_CONTENT_ROOT = APP_ROOT / "lib" / "ui" / "content"
CONTENT_ROOT = APP_ROOT / "lib" / "service" / "content_service"
COMPONENTS_ROOT = APP_ROOT / "lib" / "components"

# Internal layering pins (R-CONTENTDIR-001).
PAGEFLIP_ENGINE_ROOT = APP_ROOT / "lib" / "design_system" / "pageflip"
RETIRED_PAGEFLIP_ENGINE_ROOTS = (
    COMPONENTS_ROOT / "pageflip",
    LEGACY_CONTENT_ROOT / "pageflip",
)
ARTICLE_READER_ROOT = (
    CONTENT_ROOT / "content" / "post" / "presentation" / "article_reader"
)
CANONICAL_MEDIA_PAGEFLIP_ROOT = (
    CONTENT_ROOT / "media" / "media_asset" / "presentation"
)
PAGEFLIP_ENGINE_IMPORT = "package:quwoquan_app/design_system/pageflip/"

# Only truly retired import fragments. Live content_service production paths
# must never appear here.
RETIRED_PATH_FRAGMENTS = (
    "package:quwoquan_app/service/content_service/media/media_asset/application/media_viewer_interaction_bridge.dart",
    "package:quwoquan_app/ui/content/models/content_time_label.dart",
    "package:quwoquan_app/ui/content/widgets/intersection_reason_chip.dart",
    "package:quwoquan_app/ui/content/widgets/record_post_card.dart",
    "package:quwoquan_app/ui/content/markdown/",
    "package:quwoquan_app/ui/content/reader/",
    "package:quwoquan_app/ui/content/pageflip/",
    "package:quwoquan_app/ui/content/article_render/",
    "package:quwoquan_app/components/comment_system/comment_sort_menu.dart",
)


def dart_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.dart") if path.is_file())


def rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def contains(path: Path, needle: str) -> bool:
    return needle in path.read_text(encoding="utf-8")


def main() -> int:
    failures: list[str] = []

    if not CONTENT_ROOT.is_dir():
        failures.append(f"canonical content service root missing: {rel(CONTENT_ROOT)}")

    # Canonical positive scope: every content object layer.  Legacy roots are
    # retirement guards, not an alternate tree that can make this gate green.
    for path in dart_files(CONTENT_ROOT):
        text = path.read_text(encoding="utf-8")
        for retired_prefix in (
            "package:quwoquan_app/ui/",
            "package:quwoquan_app/components/",
        ):
            if retired_prefix in text:
                failures.append(
                    f"{rel(path)} imports retired App root {retired_prefix}"
                )

    for retired_root in (LEGACY_CONTENT_ROOT, COMPONENTS_ROOT):
        if dart_files(retired_root):
            failures.append(
                f"retired content/component root still owns Dart files: {rel(retired_root)}"
            )

    # Canonical object layers are domain/application/adapters/presentation;
    # a generic `models/` bucket would reintroduce the retired horizontal tree.
    for models_dir in sorted(
        path for path in CONTENT_ROOT.rglob("models") if path.is_dir()
    ):
        failures.append(f"non-canonical content models bucket: {rel(models_dir)}")

    # Invariant 2: the generic pageflip engine has one design-system owner.  It
    # may only be consumed by itself, the article reader host, and the generic
    # media pageflip host in production code.
    for retired_root in RETIRED_PAGEFLIP_ENGINE_ROOTS:
        if retired_root.exists():
            failures.append(
                f"retired pageflip engine root still exists: {rel(retired_root)}"
            )
    for path in dart_files(APP_ROOT / "lib"):
        if path.is_relative_to(PAGEFLIP_ENGINE_ROOT):
            continue
        if path.is_relative_to(ARTICLE_READER_ROOT):
            continue
        if path.is_relative_to(CANONICAL_MEDIA_PAGEFLIP_ROOT):
            continue
        if contains(path, PAGEFLIP_ENGINE_IMPORT):
            failures.append(
                f"{rel(path)} imports pageflip engine (design_system/pageflip) "
                f"outside article_reader or media pageflip host (host->engine layering)"
            )

    for path in dart_files(APP_ROOT / "lib") + dart_files(APP_ROOT / "test"):
        text = path.read_text(encoding="utf-8")
        for fragment in RETIRED_PATH_FRAGMENTS:
            if fragment in text:
                failures.append(f"{rel(path)} still imports retired path {fragment}")

    if failures:
        print("content UI boundary check failed:")
        for item in failures:
            print(f"- {item}")
        return 1

    print("content UI boundary check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
