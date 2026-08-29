#!/usr/bin/env python3
"""Project one stackctl App result into the immutable build-product shard layout."""

from __future__ import annotations

import argparse
import json
import shutil
import stat
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.render_release_application_package import (
    PAYLOAD_NAMES,
    render,
)
from quwoquan_ops.cli.commands.package_app_artifact_helpers import (
    artifact_digest,
    validate_app_artifact_build_receipt,
)
from quwoquan_ops.cli.lib.app_identity import resolve_build_product
from quwoquan_ops.cli.lib.web_official_release import (
    WebOfficialReleaseError,
    validate_web_official_artifact,
)

_WEB_RELEASE_FIELDS = frozenset(
    {
        "schema",
        "environment",
        "publicOrigin",
        "releaseId",
        "contentSHA256",
        "noindex",
        "spaFallback",
        "htmlContentType",
        "assetCacheControl",
        "serviceWorker",
    }
)


def _copy(source: Path, destination: Path) -> None:
    if destination.exists():
        raise ValueError(f"candidate shard destination already exists: {destination}")
    try:
        metadata = source.lstat()
    except OSError as error:
        raise ValueError(f"candidate shard source is unavailable: {source}") from error
    if not stat.S_ISDIR(metadata.st_mode) and (
        not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
    ):
        raise ValueError(f"candidate shard source is linked or unsafe: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if stat.S_ISDIR(metadata.st_mode):
        shutil.copytree(source, destination, symlinks=True)
    else:
        shutil.copy2(source, destination)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_public_web_manifest(
    *,
    artifact: Path,
    manifest: dict[str, Any],
    official_manifest_path: Path,
) -> dict[str, Any]:
    if official_manifest_path.is_symlink() or not official_manifest_path.is_file():
        raise ValueError("shared Web official manifest is unavailable or unsafe")
    official = json.loads(official_manifest_path.read_text(encoding="utf-8"))
    if not isinstance(official, dict) or set(official) != _WEB_RELEASE_FIELDS:
        raise ValueError("shared Web official manifest fields are not canonical")
    try:
        validate_web_official_artifact(artifact)
    except (OSError, TypeError, ValueError, WebOfficialReleaseError) as error:
        raise ValueError(f"shared Web artifact is not official: {error}") from error
    content_digest = artifact_digest(artifact).removeprefix("sha256:")
    expected = {
        "schema": "client-app.web.official-release",
        "environment": "prod",
        "publicOrigin": "https://quwoquan.com",
        "releaseId": content_digest[:20],
        "contentSHA256": content_digest,
        "noindex": False,
        "spaFallback": "/index.html",
        "htmlContentType": "text/html; charset=utf-8",
        "assetCacheControl": "no-cache, must-revalidate",
        "serviceWorker": "flutter_service_worker.js",
    }
    if (
        official != expected
        or manifest.get("artifactDigest") != "sha256:" + content_digest
    ):
        raise ValueError(
            "shared Web official manifest does not bind AppArtifactManifest"
        )
    return {
        **official,
        "sourceGitSha": str(manifest["sourceGitSha"]),
        "sourceTreeDigest": str(manifest["sourceTreeDigest"]),
        "artifactManifest": manifest,
    }


def _collect_public_web_manifest(
    *,
    official: dict[str, Any],
    bundle_dir: Path,
) -> Path:
    output = bundle_dir / "public-web-manifest.json"
    _write_json(output, official)
    return output


def _collect_android_official_manifest(
    *,
    manifest: dict[str, Any],
    official_manifest_path: Path,
    bundle_dir: Path,
) -> Path:
    official = json.loads(official_manifest_path.read_text(encoding="utf-8"))
    if (
        not isinstance(official, dict)
        or official.get("schema") != "client-app.android.official-release"
    ):
        raise ValueError("prod Android official manifest is invalid")
    expected_digest = "sha256:" + str(official.get("apkSHA256") or "")
    if manifest.get("artifactDigest") != expected_digest or manifest.get(
        "signingIdentityDigest"
    ) != "sha256:" + str(official.get("apkSigningCertificateSHA256") or ""):
        raise ValueError(
            "prod Android official manifest does not bind AppArtifactManifest"
        )
    filename = str(official.get("packagedAPK") or "")
    if not filename or Path(filename).name != filename:
        raise ValueError("prod Android packagedAPK is not a canonical filename")
    official.update(
        {
            "sourceGitSha": str(manifest["sourceGitSha"]),
            "sourceTreeDigest": str(manifest["sourceTreeDigest"]),
            "artifactManifest": manifest,
        }
    )
    output = bundle_dir / "android-release-manifest.json"
    _write_json(output, official)
    return output


def collect(
    result_path: Path,
    bundle_dir: Path,
    *,
    android_release_manifest: Path | None = None,
    web_release_manifest: Path | None = None,
) -> dict[str, str]:
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("exitCode") != 0:
        raise ValueError("stackctl App build result is not successful")
    manifest = result.get("manifest")
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != "app-artifact-manifest"
    ):
        raise ValueError("stackctl App result manifest is invalid")
    build_product_id = str(manifest.get("buildProductId") or "")
    product = resolve_build_product(build_product_id)
    expected_identity = {
        "buildProfile": product.build_profile,
        "platform": product.platform,
        "buildMode": product.build_mode,
        "artifactFormat": product.artifact_format,
        "distributionClass": product.distribution_class,
    }
    mismatches = [
        field
        for field, expected in expected_identity.items()
        if manifest.get(field) != expected
    ]
    if mismatches:
        raise ValueError(
            f"{build_product_id} stackctl manifest identity mismatch: {', '.join(mismatches)}"
        )

    validated = validate_app_artifact_build_receipt(
        attempt_dir=Path(str(result.get("attemptDir") or "")),
        expected_build_product_id=build_product_id,
        expected_manifest=manifest,
    )
    attempt_dir = validated.attempt_dir
    artifact = validated.artifact_path
    manifest_path = validated.manifest_path
    build_receipt_path = validated.receipt_path
    web_special: dict[str, Any] | None = None
    if build_product_id == "web-shared":
        if web_release_manifest is None:
            raise ValueError(
                "shared Web product requires its stackctl official manifest"
            )
        web_special = _load_public_web_manifest(
            artifact=artifact,
            manifest=manifest,
            official_manifest_path=web_release_manifest,
        )
    elif build_product_id == "android-prod-apk" and android_release_manifest is None:
        raise ValueError("prod Android product requires its stackctl official manifest")

    evidence_dir = bundle_dir / "evidence" / build_product_id
    for source in (
        manifest_path,
        build_receipt_path,
        attempt_dir / "sbom.spdx.json",
        attempt_dir / "compile.log",
        *validated.dependency_evidence,
    ):
        _copy(source, evidence_dir / source.name)

    payload_dir = bundle_dir / "payloads" / build_product_id
    _copy(artifact, payload_dir / PAYLOAD_NAMES[build_product_id])
    package = render(
        build_product_id=build_product_id,
        package=payload_dir,
        source_git_sha=str(manifest["sourceGitSha"]),
        source_tree_digest=str(manifest["sourceTreeDigest"]),
        artifact_manifest=manifest,
    )
    package_path = bundle_dir / "application-packages" / f"{build_product_id}.json"
    _write_json(package_path, package)

    special_paths: list[Path] = []
    if build_product_id == "web-shared":
        if web_special is None:
            raise ValueError("shared Web official manifest was not validated")
        special_paths.append(
            _collect_public_web_manifest(
                official=web_special,
                bundle_dir=bundle_dir,
            )
        )
    elif build_product_id == "android-prod-apk":
        if android_release_manifest is None:
            raise ValueError("prod Android official manifest was not validated")
        special_paths.append(
            _collect_android_official_manifest(
                manifest=manifest,
                official_manifest_path=android_release_manifest,
                bundle_dir=bundle_dir,
            )
        )

    value = {
        "buildProductId": build_product_id,
        "artifactDigest": str(manifest["artifactDigest"]),
        "package": str(package_path),
    }
    if special_paths:
        value["specialEvidence"] = ",".join(str(path) for path in special_paths)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--bundle-dir", required=True, type=Path)
    parser.add_argument("--android-release-manifest", type=Path)
    parser.add_argument("--web-release-manifest", type=Path)
    args = parser.parse_args()
    try:
        value = collect(
            args.result,
            args.bundle_dir,
            android_release_manifest=args.android_release_manifest,
            web_release_manifest=args.web_release_manifest,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"GATE_BLOCK: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
