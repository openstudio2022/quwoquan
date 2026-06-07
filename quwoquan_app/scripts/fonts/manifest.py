"""Load and persist bundled_fonts_manifest.yaml."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

from _common.paths import APP_ROOT, MANIFEST_PATH


def manifest_path(custom: Path | None = None) -> Path:
    return custom if custom is not None else MANIFEST_PATH


def load_manifest(path: Path | None = None) -> dict[str, Any]:
    target = manifest_path(path)
    if not target.is_file():
        raise FileNotFoundError(f"missing manifest: {target}")
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"invalid manifest root in {target}")
    return data


def save_manifest(data: dict[str, Any], path: Path | None = None) -> Path:
    target = manifest_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return target


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def asset_abs(relative: str) -> Path:
    return APP_ROOT / relative


def iter_font_entries(data: dict[str, Any]) -> list[dict[str, Any]]:
    fonts = data.get("fonts")
    if not isinstance(fonts, list):
        raise ValueError("manifest fonts must be a list")
    return [entry for entry in fonts if isinstance(entry, dict)]
