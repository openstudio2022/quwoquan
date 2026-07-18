"""Verify bundled fonts manifest, disk assets, and pubspec declarations."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from _common.paths import APP_ROOT, FONTS_ASSETS_DIR, PUBSPEC_PATH
from fonts.manifest import asset_abs, iter_font_entries, load_manifest, sha256_file


def _load_pubspec_text(path: Path | None = None) -> str:
    target = path if path is not None else PUBSPEC_PATH
    return target.read_text(encoding="utf-8")


def _pubspec_font_assets(pubspec_text: str) -> set[str]:
    assets: set[str] = set()
    for match in re.finditer(r"asset:\s*(assets/fonts/[^\s#]+)", pubspec_text):
        assets.add(match.group(1).strip())
    return assets


def verify_fonts(
    *,
    manifest_file: Path | None = None,
    pubspec_file: Path | None = None,
    app_root: Path | None = None,
) -> list[str]:
    root = app_root if app_root is not None else APP_ROOT
    errors: list[str] = []
    try:
        data = load_manifest(manifest_file)
    except (FileNotFoundError, ValueError) as exc:
        return [str(exc)]

    if data.get("schema") != "bundled-fonts-manifest":
        errors.append("manifest schema must be bundled-fonts-manifest")

    pubspec_path = pubspec_file if pubspec_file is not None else root / "pubspec.yaml"
    pubspec_text = _load_pubspec_text(pubspec_path)
    if re.search(r"^\s*google_fonts:", pubspec_text, re.MULTILINE):
        errors.append("pubspec.yaml must not declare google_fonts direct dependency")

    declared_assets = _pubspec_font_assets(pubspec_text)
    families: set[str] = set()

    for entry in iter_font_entries(data):
        family = str(entry.get("family", "")).strip()
        asset_path = str(entry.get("assetPath", "")).strip()
        expected_sha = str(entry.get("sha256", "")).strip()
        if not family or not asset_path:
            errors.append("manifest entry missing family or assetPath")
            continue
        families.add(family)
        disk_path = root / asset_path if app_root else asset_abs(asset_path)
        if not disk_path.is_file():
            errors.append(f"missing font file: {asset_path}")
            continue
        if not expected_sha:
            errors.append(f"missing sha256 in manifest: {asset_path}")
        elif sha256_file(disk_path) != expected_sha:
            errors.append(f"sha256 mismatch: {asset_path}")
        if asset_path not in declared_assets:
            errors.append(f"pubspec missing font asset: {asset_path}")

        license_name = str(entry.get("license", "")).strip()
        if license_name:
            license_dir = disk_path.parent
            if not (license_dir / "OFL.txt").is_file() and not (FONTS_ASSETS_DIR / "OFL.txt").is_file():
                errors.append(f"missing OFL.txt near {asset_path}")

    if not families:
        errors.append("manifest contains no font families")

    return errors


def run_verify(*, manifest_file: Path | None = None, pubspec_file: Path | None = None) -> None:
    errors = verify_fonts(manifest_file=manifest_file, pubspec_file=pubspec_file)
    if errors:
        print("[qwq-app fonts verify] FAIL", flush=True)
        for err in errors:
            print(f"  - {err}", flush=True)
        raise SystemExit(1)
    data = load_manifest(manifest_file)
    count = len(iter_font_entries(data))
    families = len({str(e.get('family')) for e in iter_font_entries(data)})
    print(
        f"[qwq-app fonts verify] OK manifestVersion={data.get('manifestVersion')} "
        f"fonts={count} families={families}"
    )
