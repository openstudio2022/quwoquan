#!/usr/bin/env python3
"""Project one stackctl App result into the immutable candidate shard layout."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.ci.render_release_application_package import (
    _package_digest,
    _sha256_tree,
    render,
)

PAYLOAD_NAMES = {
    "android": "app-release.apk",
    "ios": "quwoquan.app",
    "web": "public-web",
}


def _copy(source: Path, destination: Path) -> None:
    if destination.exists():
        raise ValueError(f"candidate shard destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination, symlinks=True)
    else:
        shutil.copy2(source, destination)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _collect_prod_web(
    *,
    artifact: Path,
    manifest: dict[str, object],
    handoff: dict[str, object],
    bundle_dir: Path,
) -> Path:
    if manifest.get("distributionClass") != "hosted_web" or manifest.get(
        "promotable"
    ) is not True:
        raise ValueError("prod Web candidate is not a promotable hosted_web artifact")
    payload_dir = bundle_dir / "payloads/prod/web"
    _copy(artifact, payload_dir)
    content_digest = _sha256_tree(payload_dir).removeprefix("sha256:")
    public_origin = str(handoff.get("publicWebBaseUrl") or "").strip().rstrip("/")
    if public_origin != "https://quwoquan.com":
        raise ValueError("prod Web launcher handoff does not bind the official origin")
    required = ("index.html", "main.dart.js", "manifest.json", "flutter_service_worker.js")
    missing = [name for name in required if not (payload_dir / name).is_file()]
    if missing:
        raise ValueError("prod Web artifact is incomplete: " + ", ".join(missing))
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


def _collect_prod_android(
    *,
    artifact: Path,
    manifest: dict[str, object],
    official_manifest_path: Path,
    bundle_dir: Path,
) -> Path:
    if manifest.get("distributionClass") != "official_web" or manifest.get(
        "promotable"
    ) is not True:
        raise ValueError("prod Android candidate is not a promotable official_web artifact")
    official = json.loads(official_manifest_path.read_text(encoding="utf-8"))
    if not isinstance(official, dict) or official.get("schema") != "client-app.android.official-release":
        raise ValueError("prod Android official manifest is invalid")
    expected_digest = "sha256:" + str(official.get("apkSHA256") or "")
    if (
        _package_digest(artifact) != expected_digest
        or manifest.get("artifactDigest") != expected_digest
        or manifest.get("signingIdentityDigest")
        != "sha256:" + str(official.get("apkSigningCertificateSHA256") or "")
    ):
        raise ValueError("prod Android official manifest does not bind AppArtifactManifest")
    filename = str(official.get("packagedAPK") or "")
    if not filename or Path(filename).name != filename:
        raise ValueError("prod Android packagedAPK is not a canonical filename")
    _copy(artifact, bundle_dir / "payloads/prod/android" / filename)
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
    environment = str(manifest.get("environment") or "")
    platform = str(manifest.get("platform") or "")
    if platform not in PAYLOAD_NAMES:
        raise ValueError(f"unsupported App shard platform: {platform}")
    attempt_dir = Path(str(result.get("attemptDir") or "")).resolve()
    build_receipt_path = attempt_dir / "build-receipt.json"
    build_receipt = json.loads(build_receipt_path.read_text(encoding="utf-8"))
    artifact = Path(str(build_receipt.get("artifactPath") or "")).resolve()
    manifest_path = Path(str(build_receipt.get("manifestPath") or "")).resolve()
    if manifest_path != (attempt_dir / "manifest.json").resolve():
        raise ValueError("stackctl build receipt escaped its attempt directory")
    evidence_dir = bundle_dir / "evidence" / environment / platform
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
    handoff = json.loads((attempt_dir / "launcher-handoff.json").read_text(encoding="utf-8"))
    special_path: Path | None = None
    if environment == "prod" and platform == "web":
        special_path = _collect_prod_web(
            artifact=artifact,
            manifest=manifest,
            handoff=handoff,
            bundle_dir=bundle_dir,
        )
    elif environment == "prod" and platform == "android":
        if android_release_manifest is None:
            raise ValueError("prod Android shard requires its stackctl official manifest")
        special_path = _collect_prod_android(
            artifact=artifact,
            manifest=manifest,
            official_manifest_path=android_release_manifest,
            bundle_dir=bundle_dir,
        )
    else:
        payload_dir = bundle_dir / "payloads" / environment / platform
        _copy(artifact, payload_dir / PAYLOAD_NAMES[platform])
        package = render(
            environment=environment,
            surface=platform,
            package=payload_dir,
            source_git_sha=str(manifest["sourceGitSha"]),
            source_tree_digest=str(manifest["sourceTreeDigest"]),
            artifact_manifest=manifest,
        )
        package_path = bundle_dir / "application-packages" / f"{environment}--{platform}.json"
        _write_json(package_path, package)
    return {
        "environment": environment,
        "platform": platform,
        "artifactDigest": str(manifest["artifactDigest"]),
        "package": str(special_path or package_path),
    }


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
