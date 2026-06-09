"""Path truth sources for qwq-app CLI."""

from __future__ import annotations

from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = SCRIPTS_ROOT.parent
REPO_ROOT = APP_ROOT.parent

MANIFEST_PATH = APP_ROOT / "assets" / "fonts" / "bundled_fonts_manifest.yaml"
PUBSPEC_PATH = APP_ROOT / "pubspec.yaml"
WEB_DIR = APP_ROOT / "web"
LIB_DIR = APP_ROOT / "lib"
FONTS_ASSETS_DIR = APP_ROOT / "assets" / "fonts"

GITHUB_FONTS_RAW = "https://raw.githubusercontent.com/google/fonts/master"
