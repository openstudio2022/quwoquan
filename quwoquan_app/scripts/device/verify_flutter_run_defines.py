#!/usr/bin/env python3
"""Validate the compile-time package before invoking ``flutter run``.

``String.fromEnvironment`` is frozen into the Dart kernel. This check therefore
belongs before Flutter builds or installs the app, rather than in the first
Flutter frame after an invalid kernel has already been produced.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from urllib.parse import urlparse


ENVIRONMENTS = frozenset({"alpha", "beta", "gamma", "prod"})
TARGET_ENVIRONMENTS = {
    "alpha-local": "alpha",
    "beta-local": "beta",
    "gamma-local": "gamma",
    "prod-sim": "prod",
    "prod-hosted": "prod",
}
REQUIRED_DEFINE_KEYS = frozenset(
    {
        "APP_RUNTIME_ENV",
        "CLOUD_GATEWAY_BASE_URL",
        "APP_LEGAL_BASE_URL",
        "PUBLIC_WEB_BASE_URL",
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
    target: str = "",
    entrypoint: str = "",
    defines_digest: str = "",
    runtime_config_digest: str = "",
    effective_launch_manifest: Mapping[str, object] | None = None,
    effective_launch_manifest_digest: str = "",
    transport_required: bool = False,
    reverse_expected_ports: str = "",
    reverse_actual_ports: str = "",
    reverse_receipt_digest: str = "",
    consumer_lease_id: str = "",
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
    if target:
        target_environment = TARGET_ENVIRONMENTS.get(target)
        if target_environment is None:
            issues.append(f"unsupported launch target {target}")
        elif runtime_env and target_environment != runtime_env:
            issues.append(
                f"target {target} requires APP_RUNTIME_ENV={target_environment}"
            )
    expected_entrypoint = "lib/main_prod.dart"
    if entrypoint and entrypoint != expected_entrypoint:
        issues.append(
            f"entrypoint {entrypoint} does not match {runtime_env or '<missing>'} "
            f"runner {expected_entrypoint}"
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
    canonical_digest = hashlib.sha256(
        json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if defines_digest and defines_digest != f"sha256:{canonical_digest}":
        issues.append("dart define digest does not match the selected package")
    if runtime_config_digest and not (
        runtime_config_digest.startswith("sha256:")
        and len(runtime_config_digest) == len("sha256:") + 64
    ):
        issues.append("runtime config digest must be a sha256 identity")
    if effective_launch_manifest is not None or effective_launch_manifest_digest:
        if effective_launch_manifest is None:
            issues.append("effective launch manifest is missing")
        else:
            encoded_manifest = json.dumps(
                effective_launch_manifest,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            expected_manifest_digest = (
                "sha256:" + hashlib.sha256(encoded_manifest).hexdigest()
            )
            if effective_launch_manifest_digest != expected_manifest_digest:
                issues.append("effective launch manifest digest does not match")
            expected_values = {
                "schema": "app-effective-launch-manifest",
                "environment": runtime_env,
                "target": target,
                "entrypoint": entrypoint,
                "dartDefinesDigest": defines_digest,
                "runtimeConfigDigest": runtime_config_digest,
            }
            for key, expected in expected_values.items():
                if effective_launch_manifest.get(key) != expected:
                    issues.append(
                        f"effective launch manifest {key} does not match"
                    )
    transport_values = {
        "reverse receipt digest": reverse_receipt_digest.strip(),
        "consumer lease ID": consumer_lease_id.strip(),
    }
    if target == "prod-hosted" and (
        any(transport_values.values())
        or reverse_expected_ports.strip()
        or reverse_actual_ports.strip()
    ):
        issues.append("prod-hosted package must not contain local transport evidence")
    if transport_required:
        if target not in TARGET_ENVIRONMENTS or target == "prod-hosted":
            issues.append("local transport evidence requires a local launch target")
        for label, value in transport_values.items():
            if re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
                issues.append(f"{label} must be a sha256 identity")
        try:
            expected_ports = _canonical_ports(reverse_expected_ports)
            actual_ports = _canonical_ports(reverse_actual_ports)
            if expected_ports != actual_ports:
                issues.append("Android reverse expected/actual ports do not match")
        except ValueError as error:
            issues.append(str(error))
    return issues


def _canonical_ports(raw: str) -> tuple[int, ...]:
    values: set[int] = set()
    for value in raw.split(","):
        normalized = value.strip()
        if not normalized:
            continue
        if not normalized.isdigit() or int(normalized) <= 0 or int(normalized) > 65535:
            raise ValueError(f"invalid Android reverse port: {normalized}")
        values.add(int(normalized))
    if not values:
        raise ValueError("Android reverse ports are empty")
    return tuple(sorted(values))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", default="")
    parser.add_argument("--platform", choices=("android", "ios", "web"), default="")
    parser.add_argument("--target", choices=tuple(TARGET_ENVIRONMENTS), default="")
    parser.add_argument("--entrypoint", default="")
    parser.add_argument("--defines-digest", default="")
    parser.add_argument("--runtime-config-digest", default="")
    parser.add_argument("--effective-launch-manifest-json", default="")
    parser.add_argument("--effective-launch-manifest-digest", default="")
    parser.add_argument("--transport-required", action="store_true")
    parser.add_argument("--reverse-expected-ports", default="")
    parser.add_argument("--reverse-actual-ports", default="")
    parser.add_argument("--reverse-receipt-digest", default="")
    parser.add_argument("--consumer-lease-id", default="")
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
    effective_manifest: Mapping[str, object] | None = None
    if args.effective_launch_manifest_json:
        try:
            decoded_manifest = json.loads(args.effective_launch_manifest_json)
        except json.JSONDecodeError as exc:
            print(
                f"FAIL: --effective-launch-manifest-json is not valid JSON: {exc}",
                file=sys.stderr,
            )
            return 2
        if not isinstance(decoded_manifest, dict):
            print(
                "FAIL: --effective-launch-manifest-json must contain an object.",
                file=sys.stderr,
            )
            return 2
        effective_manifest = decoded_manifest
    issues = validate_flutter_run_defines(
        defines,
        expected_env=args.env.strip(),
        platform=args.platform,
        target=args.target,
        entrypoint=args.entrypoint,
        defines_digest=args.defines_digest,
        runtime_config_digest=args.runtime_config_digest,
        effective_launch_manifest=effective_manifest,
        effective_launch_manifest_digest=args.effective_launch_manifest_digest,
        transport_required=args.transport_required,
        reverse_expected_ports=args.reverse_expected_ports,
        reverse_actual_ports=args.reverse_actual_ports,
        reverse_receipt_digest=args.reverse_receipt_digest,
        consumer_lease_id=args.consumer_lease_id,
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
            "bash quwoquan_app/run.sh -d <device-id>",
            file=sys.stderr,
        )
        return 2

    print(
        json.dumps(
            {
                "status": "passed",
                "environment": defines["APP_RUNTIME_ENV"],
                "target": args.target or None,
                "entrypoint": args.entrypoint or None,
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
