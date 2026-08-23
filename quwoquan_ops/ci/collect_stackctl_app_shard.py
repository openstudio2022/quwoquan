#!/usr/bin/env python3
"""Project one stackctl App result into the immutable build-product shard layout."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.render_release_application_package import (
    PAYLOAD_NAMES,
    _package_digest,
    _sha256_tree,
    render,
)
from quwoquan_ops.cli.lib.app_identity import resolve_build_product


def _copy(source: Path, destination: Path) -> None:
    if destination.exists():
        raise ValueError(f"candidate shard destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination, symlinks=True)
    else:
        shutil.copy2(source, destination)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _collect_public_web_manifest(
    *,
    payload_dir: Path,
    manifest: dict[str, Any],
    handoff: dict[str, Any],
    bundle_dir: Path,
) -> Path:
    public_origin = str(handoff.get("publicWebBaseUrl") or "").strip().rstrip("/")
    if public_origin != "https://quwoquan.com":
        raise ValueError("shared Web launcher handoff does not bind the official origin")
    artifact = payload_dir / PAYLOAD_NAMES["web-shared"]
    required = ("index.html", "main.dart.js", "manifest.json", "flutter_service_worker.js")
    missing = [name for name in required if not (artifact / name).is_file()]
    if missing:
        raise ValueError("shared Web artifact is incomplete: " + ", ".join(missing))
    content_digest = _sha256_tree(artifact).removeprefix("sha256:")
    output = bundle_dir / "public-web-manifest.json"
    _write_json(
        output,
        {
            "schema": "client-app.web.official-release",
            "environment": "prod",
            "publicOrigin": public_origin,
            "releaseId": content_digest[:20],
            "contentSHA256": content_digest,
            "noindex": False,
            "spaFallback": "/index.html",
            "htmlContentType": "text/html; charset=utf-8",
            "assetCacheControl": "no-cache, must-revalidate",
            "serviceWorker": "flutter_service_worker.js",
            "sourceGitSha": str(manifest["sourceGitSha"]),
            "sourceTreeDigest": str(manifest["sourceTreeDigest"]),
            "artifactManifest": manifest,
        },
    )
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
    if (
        manifest.get("artifactDigest") != expected_digest
        or manifest.get("signingIdentityDigest")
        != "sha256:" + str(official.get("apkSigningCertificateSHA256") or "")
    ):
        raise ValueError("prod Android official manifest does not bind AppArtifactManifest")
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
) -> dict[str, str]:
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("exitCode") != 0:
        raise ValueError("stackctl App build result is not successful")
    manifest = result.get("manifest")
    if not isinstance(manifest, dict) or manifest.get("schema") != "app-artifact-manifest":
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
        field for field, expected in expected_identity.items() if manifest.get(field) != expected
    ]
    if mismatches:
        raise ValueError(
            f"{build_product_id} stackctl manifest identity mismatch: {', '.join(mismatches)}"
        )

    attempt_dir = Path(str(result.get("attemptDir") or "")).resolve()
    build_receipt_path = attempt_dir / "build-receipt.json"
    build_receipt = json.loads(build_receipt_path.read_text(encoding="utf-8"))
    artifact = Path(str(build_receipt.get("artifactPath") or "")).resolve()
    manifest_path = Path(str(build_receipt.get("manifestPath") or "")).resolve()
    if manifest_path != (attempt_dir / "manifest.json").resolve():
        raise ValueError("stackctl build receipt escaped its attempt directory")

    evidence_dir = bundle_dir / "evidence" / build_product_id
    for source in (
        manifest_path,
        build_receipt_path,
        attempt_dir / "launcher-handoff.json",
        attempt_dir / "sbom.spdx.json",
        attempt_dir / "compile.log",
    ):
        _copy(source, evidence_dir / source.name)
    if _package_digest(artifact) != str(manifest.get("artifactDigest") or ""):
        raise ValueError("stackctl artifact digest does not match AppArtifactManifest")

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
        handoff = json.loads(
            (attempt_dir / "launcher-handoff.json").read_text(encoding="utf-8")
        )
        if not isinstance(handoff, dict):
            raise ValueError("stackctl App launcher handoff is invalid")
        special_paths.append(
            _collect_public_web_manifest(
                payload_dir=payload_dir,
                manifest=manifest,
                handoff=handoff,
                bundle_dir=bundle_dir,
            )
        )
    elif build_product_id == "android-prod-apk":
        if android_release_manifest is None:
            raise ValueError("prod Android product requires its stackctl official manifest")
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
    args = parser.parse_args()
    try:
        value = collect(
            args.result,
            args.bundle_dir,
            android_release_manifest=args.android_release_manifest,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"GATE_BLOCK: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
