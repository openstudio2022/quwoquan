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
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.environment_topology import (
    ENVIRONMENT_CANONICAL_TARGET,
    get_target,
    load_environment_topology,
)


DEFINE_KEYS = {
    "appRuntimeEnv": "APP_RUNTIME_ENV",
    "appRolloutMode": "APP_ROLLOUT_MODE",
    "gatewayBaseUrl": "CLOUD_GATEWAY_BASE_URL",
    "legalBaseUrl": "APP_LEGAL_BASE_URL",
    "publicWebBaseUrl": "PUBLIC_WEB_BASE_URL",
    "appDownloadBaseUrl": "APP_DOWNLOAD_BASE_URL",
    "realtimeBaseUrl": "REALTIME_CONNECTION_URL",
    "mediaAvatarCdnBaseUrl": "MEDIA_AVATAR_CDN_BASE_URL",
    "mediaImageCdnBaseUrl": "MEDIA_IMAGE_CDN_BASE_URL",
    "mediaVideoCdnBaseUrl": "MEDIA_VIDEO_CDN_BASE_URL",
    "mediaUploadBaseUrl": "MEDIA_UPLOAD_BASE_URL",
    "rtcMediaConnectionUrl": "RTC_MEDIA_CONNECTION_URL",
    "currentUserId": "APP_CURRENT_USER_ID",
    "appInstanceId": "APP_INSTANCE_ID",
    "appInstanceNamespace": "APP_INSTANCE_NAMESPACE",
    "launchMode": "QWQ_APP_LAUNCH_MODE",
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
    gateway_override = args.gateway_base_url or os.environ.get("LOCAL_GAMMA_GATEWAY_BASE_URL", "")
    legal_override = args.legal_base_url or os.environ.get("APP_LEGAL_BASE_URL", "")
    overrides = {
        "gatewayBaseUrl": gateway_override,
        "legalBaseUrl": legal_override,
        "mediaAvatarCdnBaseUrl": args.media_avatar_base_url
        or os.environ.get("LOCAL_GAMMA_MEDIA_AVATAR_BASE_URL", ""),
        "mediaImageCdnBaseUrl": args.media_image_base_url
        or os.environ.get("LOCAL_GAMMA_MEDIA_IMAGE_BASE_URL", ""),
        "mediaVideoCdnBaseUrl": args.media_video_base_url
        or os.environ.get("LOCAL_GAMMA_MEDIA_VIDEO_BASE_URL", ""),
        "mediaUploadBaseUrl": args.media_upload_base_url
        or os.environ.get("LOCAL_GAMMA_MEDIA_UPLOAD_BASE_URL", ""),
        "rtcMediaConnectionUrl": args.rtc_media_connection_url
        or os.environ.get("LOCAL_GAMMA_RTC_MEDIA_CONNECTION_URL", ""),
        "currentUserId": args.current_user_id,
        "appInstanceId": args.app_instance_id,
        "appInstanceNamespace": args.app_instance_namespace,
        "launchMode": args.launch_mode or os.environ.get("QWQ_APP_LAUNCH_MODE", ""),
        "appRolloutMode": args.rollout_mode or os.environ.get("APP_ROLLOUT_MODE", ""),
    }
    url_keys = {
        "gatewayBaseUrl",
        "publicWebBaseUrl",
        "appDownloadBaseUrl",
        "legalBaseUrl",
        "mediaAvatarCdnBaseUrl",
        "mediaImageCdnBaseUrl",
        "mediaVideoCdnBaseUrl",
        "mediaUploadBaseUrl",
        "rtcMediaConnectionUrl",
    }
    for key, value in overrides.items():
        if value:
            normalized = value.rstrip("/") if key in url_keys else value
            if key in url_keys and normalized != values.get(key, ""):
                raise SystemExit(
                    f"{key} override must equal canonical topology projection: "
                    f"{normalized!r} != {values.get(key, '')!r}"
                )
            values[key] = normalized
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", default="gamma")
    parser.add_argument("--target", default="")
    parser.add_argument("--format", choices=["args", "shell", "json"], default="args")
    parser.add_argument("--gateway-base-url", default="")
    parser.add_argument("--legal-base-url", default="")
    parser.add_argument("--media-avatar-base-url", default="")
    parser.add_argument("--media-image-base-url", default="")
    parser.add_argument("--media-video-base-url", default="")
    parser.add_argument("--media-upload-base-url", default="")
    parser.add_argument("--rtc-media-connection-url", default="")
    parser.add_argument("--current-user-id", default="")
    parser.add_argument("--app-instance-id", default="")
    parser.add_argument("--app-instance-namespace", default="")
    parser.add_argument("--launch-mode", default="")
    parser.add_argument("--rollout-mode", default="")
    args = parser.parse_args()

    cfg = ROOT / "quwoquan_app" / "configs" / args.env / "app_runtime.yaml"
    if not cfg.exists():
        raise SystemExit(f"app runtime config not found: {cfg}")
    values = parse_runtime_yaml(cfg)
    target_name = args.target or ENVIRONMENT_CANONICAL_TARGET[args.env]
    target = get_target(load_environment_topology(), target_name)
    if target.get("env") != args.env:
        raise SystemExit(
            f"target {target_name!r} does not belong to environment {args.env!r}"
        )
    public_bases = target["publicBases"]
    values.update(
        {
            "gatewayBaseUrl": public_bases["api"],
            "legalBaseUrl": public_bases["legal"],
            "publicWebBaseUrl": public_bases["publicWeb"],
            "appDownloadBaseUrl": public_bases["appDownload"],
            "realtimeBaseUrl": public_bases["realtime"],
            "mediaAvatarCdnBaseUrl": public_bases["mediaAvatar"],
            "mediaImageCdnBaseUrl": public_bases["mediaImage"],
            "mediaVideoCdnBaseUrl": public_bases["mediaVideo"],
            "mediaUploadBaseUrl": public_bases["mediaUpload"],
            "rtcMediaConnectionUrl": public_bases["rtc"],
        }
    )
    values = apply_overrides(values, args)
    required_endpoint_keys = (
        "gatewayBaseUrl",
        "legalBaseUrl",
        "publicWebBaseUrl",
        "appDownloadBaseUrl",
        "realtimeBaseUrl",
        "mediaAvatarCdnBaseUrl",
        "mediaImageCdnBaseUrl",
        "mediaVideoCdnBaseUrl",
        "mediaUploadBaseUrl",
        "rtcMediaConnectionUrl",
    )
    missing = [key for key in required_endpoint_keys if not values.get(key, "").strip()]
    if missing:
        raise SystemExit(
            "app runtime config is missing explicit endpoint values: "
            + ", ".join(missing)
        )
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
