#!/usr/bin/env python3
"""Validate the compile-time package before invoking ``flutter run``.

``String.fromEnvironment`` is frozen into the Dart kernel. This check therefore
belongs before Flutter builds or installs the app, rather than in the first
Flutter frame after an invalid kernel has already been produced.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from urllib.parse import urlparse


ENVIRONMENTS = frozenset({"alpha", "beta", "gamma", "prod"})
REQUIRED_DEFINE_KEYS = frozenset(
    {
        "APP_RUNTIME_ENV",
        "CLOUD_GATEWAY_BASE_URL",
        "APP_LEGAL_BASE_URL",
        "MEDIA_AVATAR_CDN_BASE_URL",
        "MEDIA_IMAGE_CDN_BASE_URL",
        "MEDIA_VIDEO_CDN_BASE_URL",
        "MEDIA_UPLOAD_BASE_URL",
        "RTC_MEDIA_CONNECTION_URL",
    }
)
ENDPOINT_DEFINE_KEYS = frozenset(
    REQUIRED_DEFINE_KEYS
    - {"APP_RUNTIME_ENV", "RTC_MEDIA_CONNECTION_URL"}
)
WEBSOCKET_ENDPOINT_DEFINE_KEYS = frozenset({"RTC_MEDIA_CONNECTION_URL"})


def parse_dart_define_args(args: Sequence[str]) -> dict[str, str]:
    """Extract ``KEY=VALUE`` entries from Flutter-style define arguments."""

    defines: dict[str, str] = {}
    for argument in args:
        prefix = "--dart-define="
        raw = argument.removeprefix(prefix)
        key, separator, value = raw.partition("=")
        if separator and key:
            defines[key] = value
    return defines


def validate_flutter_run_defines(
    defines: Mapping[str, object],
    *,
    expected_env: str = "",
    platform: str = "",
) -> list[str]:
    """Return actionable preflight failures for a Flutter compile package."""

    normalized = {
        str(key): str(value).strip()
        for key, value in defines.items()
    }
    issues: list[str] = []
    runtime_env = normalized.get("APP_RUNTIME_ENV", "")
    if not runtime_env:
        issues.append("missing APP_RUNTIME_ENV")
    elif runtime_env not in ENVIRONMENTS:
        issues.append(
            "APP_RUNTIME_ENV must be one of alpha|beta|gamma|prod"
        )
    if expected_env and runtime_env != expected_env:
        issues.append(
            f"APP_RUNTIME_ENV={runtime_env or '<missing>'} "
            f"does not match selected environment {expected_env}"
        )

    for key in sorted(REQUIRED_DEFINE_KEYS - {"APP_RUNTIME_ENV"}):
        value = normalized.get(key, "")
        if not value:
            issues.append(f"missing {key}")
            continue
        if key in ENDPOINT_DEFINE_KEYS:
            parsed = urlparse(value)
            if (
                parsed.scheme.lower() != "https"
                or not parsed.hostname
                or parsed.query
                or parsed.fragment
            ):
                issues.append(f"{key} must be an HTTPS origin without query/fragment")
        if key in WEBSOCKET_ENDPOINT_DEFINE_KEYS:
            parsed = urlparse(value)
            if (
                parsed.scheme.lower() != "wss"
                or not parsed.hostname
                or parsed.query
                or parsed.fragment
            ):
                issues.append(f"{key} must be a WSS origin without query/fragment")

    if platform and platform not in {"android", "ios", "web"}:
        issues.append(f"unsupported launch platform {platform}")
    return issues


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", default="")
    parser.add_argument("--platform", choices=("android", "ios", "web"), default="")
    parser.add_argument("--defines-json", default="")
    parser.add_argument(
        "--define",
        "--dart-define",
        dest="define",
        action="append",
        default=[],
        help="Pass a Flutter-style --dart-define=KEY=VALUE entry.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    defines: dict[str, object] = {}
    if args.defines_json:
        try:
            decoded = json.loads(args.defines_json)
        except json.JSONDecodeError as exc:
            print(f"FAIL: --defines-json is not valid JSON: {exc}", file=sys.stderr)
            return 2
        if not isinstance(decoded, dict):
            print("FAIL: --defines-json must contain an object.", file=sys.stderr)
            return 2
        defines.update(decoded)
    defines.update(parse_dart_define_args(args.define))
    issues = validate_flutter_run_defines(
        defines,
        expected_env=args.env.strip(),
        platform=args.platform,
    )
    if issues:
        selected_env = args.env.strip() or "<unknown>"
        print(
            "FAIL: Flutter CLI environment package is incomplete before "
            "flutter build/run.",
            file=sys.stderr,
        )
        print(f"Selected environment: {selected_env}", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        print(
            "Use the canonical launcher: "
            "bash quwoquan_app/scripts/device/start_app_instance.sh "
            "--env <alpha|beta|gamma|prod> --device-id <device-id>",
            file=sys.stderr,
        )
        return 2

    print(
        json.dumps(
            {
                "status": "passed",
                "environment": defines["APP_RUNTIME_ENV"],
                "platform": args.platform or None,
                "verifiedDefineKeys": sorted(REQUIRED_DEFINE_KEYS),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
