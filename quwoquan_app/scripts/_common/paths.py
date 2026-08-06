"""Path truth sources for qwq-app CLI and nested App scripts."""

from __future__ import annotations

from pathlib import Path


def locate_scripts_root(start: Path | None = None) -> Path:
    """Return ``quwoquan_app/scripts`` by walking ancestors from ``start``.

    Nested verifiers must call this (or import ``SCRIPTS_ROOT`` after putting
    scripts on ``sys.path``) instead of hard-coding ``Path(__file__).parents[N]``.
    """

    here = (start or Path(__file__)).resolve()
    for parent in [here, *here.parents]:
        if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file():
            return parent
    raise RuntimeError(f"unable to locate quwoquan_app/scripts from {here}")


SCRIPTS_ROOT = locate_scripts_root(Path(__file__))
APP_ROOT = SCRIPTS_ROOT.parent
REPO_ROOT = APP_ROOT.parent

MANIFEST_PATH = APP_ROOT / "assets" / "fonts" / "bundled_fonts_manifest.yaml"
PUBSPEC_PATH = APP_ROOT / "pubspec.yaml"
WEB_DIR = APP_ROOT / "web"
LIB_DIR = APP_ROOT / "lib"
FONTS_ASSETS_DIR = APP_ROOT / "assets" / "fonts"

GITHUB_FONTS_RAW = "https://raw.githubusercontent.com/google/fonts/master"
