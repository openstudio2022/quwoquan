#!/usr/bin/env python3
"""Verify the single release-bound media delivery contract."""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _required_markers() -> dict[Path, tuple[str, ...]]:
    data = ROOT / "quwoquan_data" / "scripts"
    importer = ROOT / "quwoquan_service" / "services" / "content-service" / "cmd" / "import"
    return {
        data / "content" / "release" / "environment" / "handler.py": (
            "_release_media_object_keys",
            "object_keys=_release_media_object_keys(release)",
            "payload_root(release)",
            '"media-sync.json"',
            "target.media_base_url",
        ),
        data / "content" / "release" / "environment" / "consistency.py": (
            "_cas_issues",
            "asset_ref_path_escape",
            "non_cas_asset_ref",
            "dangling_asset_ref",
        ),
        data / "content" / "release" / "environment" / "importers.py": (
            "media_base_url",
            '"--media-base-url"',
        ),
        data / "content" / "release" / "canonical" / "gate.py": (
            "posterAssetId",
            "environment URL field",
        ),
        data / "core" / "media_asset_url.py": (
            "is_cas_media_object_key",
            "build_release_media_manifest",
            "copy_release_media_objects",
            "quwoquan_data.release_media_manifest",
        ),
        importer / "loader.go": (
            "PosterAssetID",
            "validateVideoAssets",
            "BindPostAssetURLs",
        ),
        importer / "main.go": (
            "media-base-url",
            "BindPostAssetURLs",
        ),
        ROOT / "quwoquan_app" / "lib" / "core" / "media" / "asset_url_resolver.dart": (
            "resolveManifestUrls",
            "objectKey",
        ),
    }


def _contract_violations() -> list[str]:
    violations: list[str] = []
    for path, markers in _required_markers().items():
        if not path.is_file():
            violations.append(f"{path.relative_to(ROOT)}: required contract owner missing")
            continue
        source = _read(path)
        for marker in markers:
            if marker not in source:
                violations.append(
                    f"{path.relative_to(ROOT)}: missing media contract marker {marker!r}"
                )

    scan_roots = (
        ROOT / "quwoquan_data" / "scripts",
        ROOT / "quwoquan_service" / "services" / "content-service",
        ROOT / "quwoquan_app" / "lib",
    )
    for base in scan_roots:
        for path in sorted(base.rglob("*")):
            if path.suffix not in {".py", ".go", ".dart"}:
                continue
            if path == Path(__file__).resolve():
                continue
            if "tests" in path.parts or path.name.endswith(("_test.go", "_test.dart", "_test.py")):
                continue
            source = _read(path)
            relative = path.relative_to(ROOT)
            if re.search(r"https://(?:cdn|origin)\.example", source):
                violations.append(f"{relative}: forbidden stub media domain")
            if "quwoquan_data/scripts/ship" in source or "scripts.ship" in source:
                violations.append(f"{relative}: retired media ship path")

    canonical_roots = (
        ROOT / "quwoquan_data" / "scripts" / "content" / "release" / "canonical",
        ROOT / "quwoquan_data" / "scripts" / "core" / "media_asset_url.py",
    )
    for root in canonical_roots:
        paths = (root,) if root.is_file() else sorted(root.rglob("*.py"))
        for path in paths:
            if path.name in {"gate.py", "object_transaction_audit.py"}:
                continue
            source = _read(path)
            for field in ('"cdnUrl"', '"thumbnailUrl"', '"coverUrl"', '"videoUrl"'):
                if field in source and path.name != "gate.py":
                    violations.append(
                        f"{path.relative_to(ROOT)}: canonical layer owns environment field {field}"
                    )
    return violations


def main() -> int:
    violations = _contract_violations()
    if violations:
        print("[verify_media_release_contract] FAIL")
        for violation in violations:
            print(f"  - {violation}")
        return 2
    print("[verify_media_release_contract] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
