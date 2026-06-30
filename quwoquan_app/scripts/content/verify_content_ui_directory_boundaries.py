#!/usr/bin/env python3
"""Verify App-side content UI directory boundaries.

The content UI root (`lib/ui/content/`) is standardized and its internal
layering is pinned (R-CONTENTDIR-001):

1. Single models root — `lib/ui/content/models/` is the ONLY `models/`
   directory under the content domain; no sub-module (entry/reader/...) may
   keep its own `models/`. The entry/reader models were lifted here during
   directory unification.
2. Pageflip engine isolation — `lib/components/pageflip/` (StPageFlip engine,
   platform-agnostic geometry/calculation) may only be consumed by the
   `lib/ui/content/article_reader/` host, the generic media pageflip host
   `lib/components/media/shared/pageflip/`, and tests (host->engine layering,
   see rules 11/12).
3. Render/read layering — `lib/ui/content/article_render/` (markdown render &
   pagination engine) must not depend on `lib/ui/content/article_reader/`
   (the pageflip book reader host); the dependency direction is host->engine
   only.

No loose Dart files may sit directly under the domain root.
"""

from __future__ import annotations

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = REPO_ROOT / "quwoquan_app"
CONTENT_ROOT = APP_ROOT / "lib" / "ui" / "content"
COMPONENTS_ROOT = APP_ROOT / "lib" / "components"

# Internal layering pins (R-CONTENTDIR-001).
MODELS_ROOT = CONTENT_ROOT / "models"
PAGEFLIP_ENGINE_ROOT = COMPONENTS_ROOT / "pageflip"
RETIRED_PAGEFLIP_ENGINE_ROOT = CONTENT_ROOT / "pageflip"
ARTICLE_READER_ROOT = CONTENT_ROOT / "article_reader"
ARTICLE_RENDER_ROOT = CONTENT_ROOT / "article_render"
MEDIA_PAGEFLIP_ROOT = COMPONENTS_ROOT / "media" / "shared" / "pageflip"
MEDIA_IMAGE_BOOK_ROOT = COMPONENTS_ROOT / "media" / "image" / "book"
PAGEFLIP_ENGINE_IMPORT = "package:quwoquan_app/components/pageflip/"
ARTICLE_READER_IMPORT = "package:quwoquan_app/ui/content/article_reader/"
ARTICLE_RENDER_IMPORT = "package:quwoquan_app/ui/content/article_render/"

# The content UI domain root must hold no loose Dart files; everything now
# lives under a typed subdirectory (models/, widgets/, pages/, ...).
PROTECTED_CONTENT_ROOT_FILES: set[str] = set()

RETIRED_PATH_FRAGMENTS = (
    "package:quwoquan_app/ui/content/media_viewer_interaction_bridge.dart",
    "package:quwoquan_app/ui/content/post_read_ui_bundle.dart",
    "package:quwoquan_app/ui/content/post_view_projection.dart",
    "package:quwoquan_app/ui/content/models/content_time_label.dart",
    "package:quwoquan_app/ui/content/widgets/intersection_reason_chip.dart",
    "package:quwoquan_app/ui/content/widgets/record_post_card.dart",
    "package:quwoquan_app/ui/content/article_detail_view.dart",
    "package:quwoquan_app/ui/content/article_flow_layout_engine.dart",
    "package:quwoquan_app/ui/content/article_image_intrinsic_registry.dart",
    "package:quwoquan_app/ui/content/article_pagination_engine.dart",
    "package:quwoquan_app/ui/content/markdown/",
    "package:quwoquan_app/ui/content/reader/",
    "package:quwoquan_app/ui/content/pageflip/",
    "package:quwoquan_app/components/comment_system/comment_detail_surface.dart",
    "package:quwoquan_app/components/comment_system/comment_input_overlay.dart",
    "package:quwoquan_app/components/comment_system/comment_sort_menu.dart",
    "package:quwoquan_app/components/comment_system/comment_thread_view.dart",
    "package:quwoquan_app/components/comment_system/comment_viewer.dart",
    "package:quwoquan_app/components/comment_system/comment_viewer_modal.dart",
    "package:quwoquan_app/components/comment_system/immersive_comment_split_sheet.dart",
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

    for path in dart_files(CONTENT_ROOT):
        if contains(path, "package:quwoquan_app/ui/discovery/"):
            failures.append(f"{rel(path)} imports ui/discovery from ui/content")

    root_dart_files = {
        path.name for path in CONTENT_ROOT.glob("*.dart") if path.is_file()
    }
    unexpected_root_files = root_dart_files - PROTECTED_CONTENT_ROOT_FILES
    for name in sorted(unexpected_root_files):
        failures.append(f"unexpected ui/content root Dart file: {name}")

    # Invariant 1: single models root — only lib/ui/content/models/ may be a
    # `models/` directory under the content domain.
    for models_dir in sorted(
        p for p in CONTENT_ROOT.rglob("models") if p.is_dir()
    ):
        if models_dir != MODELS_ROOT:
            failures.append(
                f"non-canonical models directory: {rel(models_dir)} "
                f"(content 域唯一 models 根应为 {rel(MODELS_ROOT)})"
            )

    # Invariant 2: the generic pageflip engine must live under components/,
    # never under the content UI domain. It may only be consumed by itself, the
    # article_reader host, and the generic media pageflip host in production lib
    # code.
    if RETIRED_PAGEFLIP_ENGINE_ROOT.exists():
        failures.append(
            f"retired pageflip engine root still exists: {rel(RETIRED_PAGEFLIP_ENGINE_ROOT)}"
        )
    for path in dart_files(APP_ROOT / "lib"):
        if path.is_relative_to(PAGEFLIP_ENGINE_ROOT):
            continue
        if path.is_relative_to(ARTICLE_READER_ROOT):
            continue
        if path.is_relative_to(MEDIA_PAGEFLIP_ROOT):
            continue
        if contains(path, PAGEFLIP_ENGINE_IMPORT):
            failures.append(
                f"{rel(path)} imports pageflip engine (components/pageflip) "
                f"outside article_reader or media pageflip host (host->engine layering)"
            )

    # Invariant 3: the article_render markdown/pagination engine must not depend
    # on the article_reader pageflip host (dependency direction is host->engine).
    for path in dart_files(ARTICLE_RENDER_ROOT):
        if contains(path, ARTICLE_READER_IMPORT):
            failures.append(
                f"{rel(path)} (article_render 渲染引擎) imports article_reader 宿主，"
                f"违反 engine<-host 分层方向"
            )

    for path in dart_files(COMPONENTS_ROOT):
        text = path.read_text(encoding="utf-8")
        if path.is_relative_to(PAGEFLIP_ENGINE_ROOT) and "package:quwoquan_app/ui/" in text:
            failures.append(f"{rel(path)} imports ui/** from generic pageflip engine")
        if path.is_relative_to(MEDIA_PAGEFLIP_ROOT):
            for forbidden in (
                "package:quwoquan_app/ui/",
                "package:quwoquan_app/cloud/runtime/generated/content/",
                "package:flutter_riverpod/",
                "package:go_router/",
                "PostBaseDto",
            ):
                if forbidden in text:
                    failures.append(
                        f"{rel(path)} violates media pageflip component boundary with {forbidden}"
                    )
        if path.is_relative_to(MEDIA_IMAGE_BOOK_ROOT):
            for forbidden in (
                "package:quwoquan_app/ui/",
                "package:quwoquan_app/cloud/runtime/generated/content/",
                "package:flutter_riverpod/",
                "package:go_router/",
                "PostBaseDto",
            ):
                if forbidden in text:
                    failures.append(
                        f"{rel(path)} violates image book component boundary with {forbidden}"
                    )
        if "package:quwoquan_app/ui/content/" not in text:
            continue
        if path.is_relative_to(COMPONENTS_ROOT / "content"):
            continue
        failures.append(f"{rel(path)} imports ui/content from generic components")

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
    sys.exit(main())
