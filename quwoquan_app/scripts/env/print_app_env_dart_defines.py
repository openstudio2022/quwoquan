#!/usr/bin/env python3
"""Print Dart defines for an app runtime env package.

The app runtime YAML is the audited package artifact, while Flutter reads
compile-time --dart-define values. This helper keeps local gamma mirror, T3
and T4 runners on the same endpoint set.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


DEFINE_KEYS = {
    "appRuntimeEnv": "APP_RUNTIME_ENV",
    "appDataSource": "APP_DATA_SOURCE",
    "gatewayBaseUrl": "CLOUD_GATEWAY_BASE_URL",
    "mediaAvatarCdnBaseUrl": "MEDIA_AVATAR_CDN_BASE_URL",
    "mediaImageCdnBaseUrl": "MEDIA_IMAGE_CDN_BASE_URL",
    "mediaVideoCdnBaseUrl": "MEDIA_VIDEO_CDN_BASE_URL",
    "mediaUploadBaseUrl": "MEDIA_UPLOAD_BASE_URL",
    "contractFixtureProfile": "CONTRACT_FIXTURE_PROFILE",
    "currentUserId": "APP_CURRENT_USER_ID",
    "appInstanceId": "APP_INSTANCE_ID",
    "appInstanceNamespace": "APP_INSTANCE_NAMESPACE",
}


def parse_runtime_yaml(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    in_runtime = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if indent == 0:
            in_runtime = stripped == "runtime:"
            continue
        if not in_runtime or indent != 2 or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def apply_overrides(values: dict[str, str], args: argparse.Namespace) -> dict[str, str]:
    overrides = {
        "gatewayBaseUrl": args.gateway_base_url or os.environ.get("LOCAL_GAMMA_GATEWAY_BASE_URL", ""),
        "mediaAvatarCdnBaseUrl": args.media_avatar_base_url
        or args.media_base_url
        or os.environ.get("LOCAL_GAMMA_MEDIA_AVATAR_BASE_URL", ""),
        "mediaImageCdnBaseUrl": args.media_image_base_url
        or args.media_base_url
        or os.environ.get("LOCAL_GAMMA_MEDIA_IMAGE_BASE_URL", ""),
        "mediaVideoCdnBaseUrl": args.media_video_base_url
        or args.media_base_url
        or os.environ.get("LOCAL_GAMMA_MEDIA_VIDEO_BASE_URL", ""),
        "mediaUploadBaseUrl": args.media_upload_base_url
        or args.media_base_url
        or os.environ.get("LOCAL_GAMMA_MEDIA_UPLOAD_BASE_URL", ""),
        "contractFixtureProfile": args.contract_fixture_profile
        or os.environ.get("CONTRACT_FIXTURE_PROFILE", ""),
        "currentUserId": args.current_user_id,
        "appInstanceId": args.app_instance_id,
        "appInstanceNamespace": args.app_instance_namespace,
    }
    url_keys = {
        "gatewayBaseUrl",
        "mediaAvatarCdnBaseUrl",
        "mediaImageCdnBaseUrl",
        "mediaVideoCdnBaseUrl",
        "mediaUploadBaseUrl",
    }
    for key, value in overrides.items():
        if value:
            values[key] = value.rstrip("/") if key in url_keys else value
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", default="gamma")
    parser.add_argument("--format", choices=["args", "shell", "json"], default="args")
    parser.add_argument("--gateway-base-url", default="")
    parser.add_argument("--media-base-url", default="")
    parser.add_argument("--media-avatar-base-url", default="")
    parser.add_argument("--media-image-base-url", default="")
    parser.add_argument("--media-video-base-url", default="")
    parser.add_argument("--media-upload-base-url", default="")
    parser.add_argument("--contract-fixture-profile", default="")
    parser.add_argument("--current-user-id", default="")
    parser.add_argument("--app-instance-id", default="")
    parser.add_argument("--app-instance-namespace", default="")
    args = parser.parse_args()

    cfg = ROOT / "quwoquan_app" / "configs" / args.env / "app_runtime.yaml"
    if not cfg.exists():
        raise SystemExit(f"app runtime config not found: {cfg}")
    values = apply_overrides(parse_runtime_yaml(cfg), args)
    defines = {
        define_key: values[source_key]
        for source_key, define_key in DEFINE_KEYS.items()
        if values.get(source_key, "") != ""
    }

    if args.format == "json":
        print(json.dumps(defines, ensure_ascii=False, indent=2))
    elif args.format == "shell":
        for key, value in defines.items():
            print(f'export {key}="{value}"')
    else:
        for key, value in defines.items():
            print(f"--dart-define={key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
