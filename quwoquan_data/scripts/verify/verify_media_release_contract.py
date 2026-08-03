#!/usr/bin/env python3
"""Verify the single release-bound media delivery contract."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _release_import_roots() -> tuple[Path, Path, Path]:
    services = ROOT / "quwoquan_service" / "services"
    return (
        services
        / "content-service"
        / "internal"
        / "content"
        / "post"
        / "infrastructure"
        / "releaseimport",
        services
        / "entity-service"
        / "internal"
        / "entity_homepage"
        / "homepage"
        / "infrastructure"
        / "homepageimport",
        services
        / "user-service"
        / "internal"
        / "profile_projection"
        / "creator_runtime_profile"
        / "infrastructure"
        / "releaseimport",
    )


def _required_markers() -> dict[Path, tuple[str, ...]]:
    data = ROOT / "quwoquan_data" / "scripts"
    content_service = ROOT / "quwoquan_service" / "services" / "content-service"
    importer, entity_importer, user_importer = _release_import_roots()
    entity_service = ROOT / "quwoquan_service" / "services" / "entity-service"
    return {
        data / "content" / "release" / "environment" / "handler.py": (
            "_sync_media",
        ),
        data / "content" / "release" / "environment" / "_ship_operations.py": (
            "target.media_delivery_base_url",
            "media_avatar_base_url=target.media_delivery_base_url",
            "media_image_base_url=target.media_delivery_base_url",
            "media_video_base_url=target.media_delivery_base_url",
        ),
        data / "content" / "release" / "environment" / "release_runtime.py": (
            "release_media_public_slices",
            "object_digests=release_media_public_slices(release)",
            "payload_root(release)",
            '"media-sync.json"',
        ),
        data / "content" / "release" / "environment" / "consistency.py": (
            "_cas_issues",
            "asset_ref_path_escape",
            "non_cas_asset_ref",
            "dangling_asset_ref",
            "release_media_issues",
            "release_private_storage_issues",
        ),
        data
        / "content"
        / "release"
        / "environment"
        / "release_media_consistency.py": (
            "release_media_private_key_leak",
            "release_object_private_storage_leak",
            "release_media_public_slice_hash_mismatch",
            "release_media_owner_closure_mismatch",
            "release_media_rights_identity_mismatch",
            "release_media_owner_rights_missing",
        ),
        data / "content" / "release" / "environment" / "importers.py": (
            '"--media-avatar-base-url"',
            '"--media-image-base-url"',
            '"--media-video-base-url"',
        ),
        data / "content" / "release" / "canonical" / "gate.py": (
            "posterAssetId",
            "environment URL field",
        ),
        data / "core" / "media_asset_url.py": (
            "is_cas_media_object_key",
            "is_public_media_slice_key",
            "build_public_media_slice_key",
            "build_release_media_manifest",
            "copy_release_media_objects",
            "quwoquan_data.release_media_manifest",
        ),
        data / "core" / "release_media_binding.py": (
            "bind_release_object_media_assets",
            "_PRIVATE_MEDIA_FIELDS",
        ),
        ROOT / "quwoquan_data" / "schema" / "release" / "media_manifest.schema.json": (
            '"publicSliceKey"',
            '"avatar"',
            '"image"',
            '"video"',
        ),
        importer / "loader.go": (
            "PosterAssetID",
            "validateVideoAssets",
            "LoadReleaseMediaAssets",
            "PublicSliceKey",
            "BindPostAssetURLs",
        ),
        importer / "runtime.go": (
            "media-image-base-url",
            "media-video-base-url",
            "releaseMediaAssets",
            "BindPostAssetURLs",
        ),
        content_service / "cmd" / "import" / "main.go": ("releaseimport.Run()",),
        entity_service / "cmd" / "homepage-import" / "main.go": (
            "LoadReleaseMediaAssets",
            "LoadHomepageProjections",
        ),
        entity_importer / "loader.go": (
            "ResolveReleaseMediaAsset",
            "contains forbidden objectKey",
        ),
        user_importer / "runtime.go": (
            "LoadReleaseMediaAssets",
            "ResolveReleaseMediaAsset",
            "contains forbidden avatar objectKey",
        ),
        ROOT / "quwoquan_service" / "runtime" / "media" / "release_media_asset.go": (
            "ReleaseMediaAsset",
            "ResolveReleaseMediaAsset",
            "RightsSnapshotRefs",
            "MediaDeliveryBases",
            "validateReleaseMediaAssetClosure",
            "validateReleaseRightsBinding",
        ),
        ROOT / "quwoquan_app" / "lib" / "core" / "media" / "asset_url_resolver.dart": (
            "resolveManifestUrls",
            "publicSliceKey",
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
                violations.append(f"{path.relative_to(ROOT)}: missing media contract marker {marker!r}")

    scan_roots = (
        ROOT / "quwoquan_data" / "scripts",
        ROOT / "quwoquan_service" / "services" / "content-service",
        ROOT / "quwoquan_service" / "services" / "entity-service",
        ROOT / "quwoquan_service" / "services" / "user-service",
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
            if "strings.TrimLeft(asset.ObjectKey" in source:
                violations.append(f"{relative}: forbidden mediaBaseURL + private objectKey projection")
            if '"--media-base-url"' in source:
                violations.append(f"{relative}: generic media base URL is retired")

    for base in _release_import_roots():
        for path in sorted(base.rglob("*.go")):
            source = _read(path)
            relative = path.relative_to(ROOT)
            for bypass in (
                "BuildContentMediaPublicSliceKey(",
                "BuildPublicMediaURL(",
            ):
                if bypass in source:
                    violations.append(
                        f"{relative}: release importer bypasses MediaAsset authority via {bypass}"
                    )

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
                if field in source and path.name not in {"gate.py", "media_asset_url.py"}:
                    violations.append(f"{path.relative_to(ROOT)}: canonical layer owns environment field {field}")
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
