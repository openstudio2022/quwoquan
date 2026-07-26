#!/usr/bin/env python3
"""从 alpha seed manifest 生成不可变、内容寻址的 Dart fixture bundle。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
METADATA = ROOT / "quwoquan_service" / "contracts" / "metadata"
MANIFEST = METADATA / "_shared/test_fixtures/app_alpha_seed_manifest.json"
DEFAULT_OUTPUT = (
    ROOT
    / "quwoquan_app"
    / "packages"
    / "quwoquan_cloud_mock"
    / "lib"
    / "src"
    / "generated"
    / "alpha_fixture_bundle.g.dart"
)


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def dart_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True).replace("$", r"\$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def _resolve_workspace_file(relative: str, *, label: str) -> Path:
    candidate = (ROOT / relative).resolve()
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} must stay inside the workspace: {relative}") from exc
    if not candidate.is_file():
        raise ValueError(f"{label} is missing: {relative}")
    return candidate


def _validate_media_canary(
    manifest: dict[str, object],
    *,
    content_source: dict[str, object],
) -> None:
    media_canary = manifest.get("mediaCanary")
    if not isinstance(media_canary, dict):
        raise ValueError("mediaCanary is required for the alpha fixture bundle")
    profile_ref = str(media_canary.get("profileRef", "")).strip()
    profile_path = _resolve_workspace_file(profile_ref, label="mediaCanary.profileRef")
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    if not isinstance(profile, dict):
        raise ValueError("mediaCanary profile must be a YAML object")
    if not str(profile.get("profileId", "")).strip():
        raise ValueError("mediaCanary profileId is required")
    if not str(profile.get("processorProfile", "")).strip():
        raise ValueError("mediaCanary processorProfile is required")

    profile_assets = profile.get("assets")
    if not isinstance(profile_assets, list):
        raise ValueError("mediaCanary profile assets are required")
    assets_by_id = {
        str(asset.get("assetId", "")).strip(): asset
        for asset in profile_assets
        if isinstance(asset, dict) and str(asset.get("assetId", "")).strip()
    }
    for state_key, expected_status in (
        ("readyAssetIds", "ready"),
        ("rejectionAssetIds", "rejected"),
    ):
        asset_ids = media_canary.get(state_key)
        if not isinstance(asset_ids, list) or not asset_ids:
            raise ValueError(f"mediaCanary.{state_key} is required")
        for asset_id in asset_ids:
            descriptor = assets_by_id.get(str(asset_id).strip())
            if descriptor is None:
                raise ValueError(
                    f"mediaCanary asset is absent from profile: {asset_id}"
                )
            if str(descriptor.get("expectedProcessingStatus", "")).strip() != expected_status:
                raise ValueError(
                    f"mediaCanary asset status mismatch: {asset_id} must be {expected_status}"
                )

    seed_sets = content_source.get("seedSets")
    if not isinstance(seed_sets, dict):
        raise ValueError("content fixture seedSets are required")
    core = seed_sets.get("content_discovery_core")
    posts = core.get("posts") if isinstance(core, dict) else None
    if not isinstance(posts, list):
        raise ValueError("content fixture discovery posts are required")
    canary_posts = [
        post
        for post in posts
        if isinstance(post, dict) and post.get("postId") == "v1"
    ]
    if len(canary_posts) != 1:
        raise ValueError("mediaCanary requires exactly one v1 video post")
    canary = canary_posts[0]
    asset_id = str(canary.get("mediaAssetId", "")).strip()
    descriptor = assets_by_id.get(asset_id)
    if descriptor is None:
        raise ValueError("v1 mediaAssetId is absent from mediaCanary profile")
    if canary.get("contentType") != "video":
        raise ValueError("v1 mediaCanary post must be a video")
    if canary.get("durationMs") != descriptor.get("durationMs"):
        raise ValueError("v1 mediaCanary duration does not match its profile")
    if canary.get("mediaAssetVersion") != descriptor.get("assetVersion"):
        raise ValueError("v1 mediaCanary asset version does not match its profile")
    prefix = str(descriptor.get("publicSlicePrefix", "")).strip().rstrip("/")
    for key in (
        "videoUrl",
        "coverUrl",
        "thumbnailUrl",
        "previewTrackManifestUrl",
    ):
        if not str(canary.get(key, "")).startswith(f"{prefix}/"):
            raise ValueError(f"v1 mediaCanary {key} must use its public slice")


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    manifest_bytes = MANIFEST.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("environment") != "alpha":
        raise ValueError("alpha fixture bundle 只能消费 environment=alpha manifest")

    assets: list[dict[str, object]] = []
    seen_domains: set[str] = set()
    content_source: dict[str, object] | None = None
    for seed in manifest.get("seedRefs", []):
        domain = str(seed.get("domain", "")).strip()
        relative = str(seed.get("fixturePath", "")).strip()
        refs = seed.get("refs")
        if not domain or domain in seen_domains:
            raise ValueError(f"fixture domain 缺失或重复: {domain!r}")
        if not relative or not isinstance(refs, list) or not refs:
            raise ValueError(f"{domain}: fixturePath/refs 不完整")
        source = (ROOT / relative).resolve()
        source.relative_to(ROOT.resolve())
        payload = source.read_bytes()
        source_json = json.loads(payload)
        if not isinstance(source_json, dict):
            raise ValueError(f"{domain}: fixture root must be a JSON object")
        if domain == "content":
            content_source = source_json
        seen_domains.add(domain)
        assets.append(
            {
                "domain": domain,
                "sourcePath": relative,
                "sourceSha256": sha256(payload),
                "sourceJson": payload.decode("utf-8"),
                "refs": [str(item) for item in refs],
            }
        )
    if content_source is None:
        raise ValueError("alpha fixture bundle requires the content seed")
    _validate_media_canary(manifest, content_source=content_source)

    release_assets: list[dict[str, object]] = []
    seen_object_ids: set[str] = set()
    for release_input in manifest.get("releaseInputs", []):
        object_id = str(release_input.get("objectId", "")).strip()
        manifest_relative = str(
            release_input.get("manifestPath", "")
        ).strip()
        if not object_id or object_id in seen_object_ids:
            raise ValueError(f"releaseInputs objectId 缺失或重复: {object_id!r}")
        if not manifest_relative:
            raise ValueError(f"{object_id}: manifestPath 缺失")
        environment_manifest_path = (ROOT / manifest_relative).resolve()
        environment_manifest_path.relative_to(ROOT.resolve())
        environment_manifest = json.loads(
            environment_manifest_path.read_text(encoding="utf-8")
        )
        canonical_relative = str(
            environment_manifest.get("canonicalArtifactRef", "")
        ).strip()
        if not canonical_relative:
            raise ValueError(f"{object_id}: canonicalArtifactRef 缺失")
        canonical_path = (ROOT / canonical_relative).resolve()
        canonical_path.relative_to(ROOT.resolve())
        canonical_payload = canonical_path.read_bytes()
        canonical = json.loads(canonical_payload)
        if (
            canonical.get("releaseId") != environment_manifest.get("releaseId")
            or canonical.get("canonicalDigest")
            != environment_manifest.get("canonicalDigest")
        ):
            raise ValueError(f"{object_id}: 环境清单与 canonical release 漂移")
        seen_object_ids.add(object_id)
        release_assets.append(
            {
                "domain": object_id,
                "sourcePath": canonical_relative,
                "sourceSha256": sha256(canonical_payload),
                "sourceJson": canonical_payload.decode("utf-8"),
                "refs": [str(canonical.get("releaseId", ""))],
            }
        )

    lines = [
        "// Code generated by build_alpha_fixture_bundle.py. DO NOT EDIT.",
        f"// Source manifest SHA256: {sha256(manifest_bytes)}",
        "",
        "final class AlphaFixtureAsset {",
        "  const AlphaFixtureAsset({",
        "    required this.domain,",
        "    required this.sourcePath,",
        "    required this.sourceSha256,",
        "    required this.sourceJson,",
        "    required this.refs,",
        "  });",
        "",
        "  final String domain;",
        "  final String sourcePath;",
        "  final String sourceSha256;",
        "  final String sourceJson;",
        "  final List<String> refs;",
        "}",
        "",
        "final class AlphaFixtureBundle {",
        "  const AlphaFixtureBundle({",
        "    required this.manifestSha256,",
        "    required this.assets,",
        "    required this.releaseAssets,",
        "  });",
        "",
        "  final String manifestSha256;",
        "  final Map<String, AlphaFixtureAsset> assets;",
        "  final Map<String, AlphaFixtureAsset> releaseAssets;",
        "}",
        "",
        "const alphaFixtureBundle = AlphaFixtureBundle(",
        f"  manifestSha256: {dart_string(sha256(manifest_bytes))},",
        "  assets: <String, AlphaFixtureAsset>{",
    ]
    for asset in sorted(assets, key=lambda item: str(item["domain"])):
        domain = str(asset["domain"])
        lines.extend(
            [
                f"    {dart_string(domain)}: AlphaFixtureAsset(",
                f"      domain: {dart_string(domain)},",
                f"      sourcePath: {dart_string(str(asset['sourcePath']))},",
                "      sourceSha256: "
                f"{dart_string(str(asset['sourceSha256']))},",
                f"      sourceJson: {dart_string(str(asset['sourceJson']))},",
                "      refs: <String>[",
            ]
        )
        for ref in asset["refs"]:
            lines.append(f"        {dart_string(str(ref))},")
        lines.extend(["      ],", "    ),"])
    lines.extend(["  },", "  releaseAssets: <String, AlphaFixtureAsset>{"])
    for asset in sorted(release_assets, key=lambda item: str(item["domain"])):
        domain = str(asset["domain"])
        lines.extend(
            [
                f"    {dart_string(domain)}: AlphaFixtureAsset(",
                f"      domain: {dart_string(domain)},",
                f"      sourcePath: {dart_string(str(asset['sourcePath']))},",
                "      sourceSha256: "
                f"{dart_string(str(asset['sourceSha256']))},",
                f"      sourceJson: {dart_string(str(asset['sourceJson']))},",
                "      refs: <String>[",
            ]
        )
        for ref in asset["refs"]:
            lines.append(f"        {dart_string(str(ref))},")
        lines.extend(["      ],", "    ),"])
    lines.extend(["  },", ");", ""])

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    print(
        "generated alpha fixture bundle: "
        f"{output} (domains={len(assets)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
