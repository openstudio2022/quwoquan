#!/usr/bin/env python3
"""Build one validated environment/target handoff for Flutter build and run."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from verify_flutter_run_defines import validate_flutter_run_defines


APP_DIR = Path(__file__).resolve().parents[2]
ROOT = APP_DIR.parent
TARGET_ENVIRONMENTS = {
    "alpha-local": "alpha",
    "beta-local": "beta",
    "gamma-local": "gamma",
    "prod-sim": "prod",
    "prod-hosted": "prod",
}
LOCAL_TARGETS = frozenset({"alpha-local", "beta-local", "gamma-local", "prod-sim"})


def runtime_config_digest(environment: str) -> str:
    digest = hashlib.sha256()
    files = (
        ROOT / "quwoquan_app/configs/default/app_runtime.yaml",
        ROOT / f"quwoquan_app/configs/{environment}/app_runtime.yaml",
        ROOT / f"quwoquan_ops/environments/{environment}/runtime.yaml",
    )
    for path in files:
        if not path.is_file():
            raise RuntimeError(f"runtime identity input is missing: {path}")
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def dart_defines_digest(defines: dict[str, Any]) -> str:
    encoded = json.dumps(
        {str(key): str(value).strip() for key, value in defines.items()},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def effective_launch_manifest_digest(manifest: dict[str, Any]) -> str:
    encoded = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", choices=("alpha", "beta", "gamma", "prod"), required=True)
    parser.add_argument("--target", choices=tuple(TARGET_ENVIRONMENTS), required=True)
    parser.add_argument("--launch-mode", required=True)
    parser.add_argument("--app-instance-id", default="")
    parser.add_argument("--app-instance-namespace", default="")
    parser.add_argument("--rollout-mode", default="")
    parser.add_argument("--gateway-base-url", default="")
    parser.add_argument("--legal-base-url", default="")
    parser.add_argument("--media-avatar-base-url", default="")
    parser.add_argument("--media-image-base-url", default="")
    parser.add_argument("--media-video-base-url", default="")
    parser.add_argument("--media-upload-base-url", default="")
    parser.add_argument("--rtc-media-connection-url", default="")
    parser.add_argument("--current-user-id", default="")
    parser.add_argument("--transport-required", action="store_true")
    parser.add_argument("--reverse-expected-ports", default="")
    parser.add_argument("--reverse-actual-ports", default="")
    parser.add_argument("--reverse-receipt-digest", default="")
    parser.add_argument("--consumer-lease-id", default="")
    return parser


def build_handoff(args: argparse.Namespace) -> dict[str, Any]:
    expected_environment = TARGET_ENVIRONMENTS[args.target]
    if args.env != expected_environment:
        raise ValueError(
            f"target {args.target} requires --env {expected_environment}, got {args.env}"
        )
    define_command = [
        "python3",
        "scripts/env/print_app_env_dart_defines.py",
        "--env",
        args.env,
        "--target",
        args.target,
        "--format",
        "json",
        "--launch-mode",
        args.launch_mode,
    ]
    for option, value in (
        ("--app-instance-id", args.app_instance_id),
        ("--app-instance-namespace", args.app_instance_namespace),
        ("--rollout-mode", args.rollout_mode),
        ("--gateway-base-url", args.gateway_base_url),
        ("--legal-base-url", args.legal_base_url),
        ("--media-avatar-base-url", args.media_avatar_base_url),
        ("--media-image-base-url", args.media_image_base_url),
        ("--media-video-base-url", args.media_video_base_url),
        ("--media-upload-base-url", args.media_upload_base_url),
        ("--rtc-media-connection-url", args.rtc_media_connection_url),
        ("--current-user-id", args.current_user_id),
    ):
        if value:
            define_command.extend([option, value])
    result = subprocess.run(
        define_command,
        cwd=APP_DIR,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    defines = json.loads(result.stdout)
    entrypoint = "lib/main_prod.dart"
    defines_digest = dart_defines_digest(defines)
    config_digest = runtime_config_digest(args.env)
    issues = validate_flutter_run_defines(
        defines,
        expected_env=args.env,
        target=args.target,
        entrypoint=entrypoint,
        defines_digest=defines_digest,
        runtime_config_digest=config_digest,
    )
    if issues:
        raise ValueError("; ".join(issues))
    transport_values = {
        "reverseExpectedPorts": args.reverse_expected_ports.strip(),
        "reverseActualPorts": args.reverse_actual_ports.strip(),
        "reverseReceiptDigest": args.reverse_receipt_digest.strip(),
        "consumerLeaseId": args.consumer_lease_id.strip(),
    }
    if args.target == "prod-hosted" and any(transport_values.values()):
        raise ValueError("prod-hosted launcher handoff must not contain local transport")
    if args.transport_required:
        if args.target not in LOCAL_TARGETS:
            raise ValueError("local transport can only be required by a local target")
        missing = [key for key, value in transport_values.items() if not value]
        if missing:
            raise ValueError(
                "local transport handoff is incomplete: " + ", ".join(sorted(missing))
            )
        for key in (
            "reverseReceiptDigest",
            "consumerLeaseId",
        ):
            if re.fullmatch(r"sha256:[0-9a-f]{64}", transport_values[key]) is None:
                raise ValueError(f"{key} must be a sha256 identity")
        expected_ports = _canonical_ports(transport_values["reverseExpectedPorts"])
        actual_ports = _canonical_ports(transport_values["reverseActualPorts"])
        if expected_ports != actual_ports:
            raise ValueError("Android reverse expected/actual ports do not match")
        transport_values["reverseExpectedPorts"] = expected_ports
        transport_values["reverseActualPorts"] = actual_ports
    effective_manifest = {
        "schema": "app-effective-launch-manifest-v1",
        "environment": args.env,
        "target": args.target,
        "entrypoint": entrypoint,
        "launchMode": args.launch_mode,
        "dartDefinesDigest": defines_digest,
        "runtimeConfigDigest": config_digest,
        "recoveryBaseUrl": defines["CLOUD_GATEWAY_BASE_URL"],
        "publicWebBaseUrl": defines["PUBLIC_WEB_BASE_URL"],
        "requiresLocalTransport": args.target in LOCAL_TARGETS,
        "transport": {
            "required": args.transport_required,
            **transport_values,
        },
    }
    effective_digest = effective_launch_manifest_digest(effective_manifest)
    manifest_issues = validate_flutter_run_defines(
        defines,
        expected_env=args.env,
        target=args.target,
        entrypoint=entrypoint,
        defines_digest=defines_digest,
        runtime_config_digest=config_digest,
        effective_launch_manifest=effective_manifest,
        effective_launch_manifest_digest=effective_digest,
        transport_required=args.transport_required,
        reverse_expected_ports=transport_values["reverseExpectedPorts"],
        reverse_actual_ports=transport_values["reverseActualPorts"],
        reverse_receipt_digest=transport_values["reverseReceiptDigest"],
        consumer_lease_id=transport_values["consumerLeaseId"],
    )
    if manifest_issues:
        raise ValueError("; ".join(manifest_issues))
    return {
        **effective_manifest,
        "schema": "app-launcher-handoff-v1",
        "dartDefines": defines,
        "effectiveLaunchManifest": effective_manifest,
        "effectiveLaunchManifestDigest": effective_digest,
    }


def _canonical_ports(raw: str) -> str:
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
    return ",".join(str(value) for value in sorted(values))


def main() -> int:
    args = _parser().parse_args()
    try:
        handoff = build_handoff(args)
    except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"GATE_BLOCK: {exc}")
        return 2
    print(json.dumps(handoff, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
