#!/usr/bin/env python3
"""Build one validated environment/target handoff for Flutter build and run."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from launch_manifest_metadata import (
    LaunchManifestContractError,
    canonical_ports,
    dart_defines_digest,
    effective_launch_manifest_digest,
    is_digest_identity,
    load_launch_manifest_contract,
    runtime_config_digest,
    validate_handoff_against_metadata,
)


APP_DIR = Path(__file__).resolve().parents[2]


def _parser(contract: dict[str, Any]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    environment_choices = contract["schemas"]["app_effective_launch_manifest"][
        "fields"
    ]["environment"]["allowed_values"]
    parser.add_argument("--env", choices=tuple(environment_choices), required=True)
    parser.add_argument(
        "--target", choices=tuple(contract["target_environment"]), required=True
    )
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
    parser.add_argument("--content-release-id", default="")
    parser.add_argument("--content-manifest-digest", default="")
    parser.add_argument("--content-readiness-receipt-digest", default="")
    return parser


def build_handoff(args: argparse.Namespace) -> dict[str, Any]:
    contract = load_launch_manifest_contract()
    expected_environment = contract["target_environment"][args.target]
    local_targets = set(contract["local_transport_targets"])
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
    if not isinstance(defines, dict):
        raise ValueError("canonical Dart defines output must be an object")
    if defines.get("APP_RUNTIME_ENV") != args.env:
        raise ValueError("canonical Dart defines environment does not match metadata")
    effective_schema = contract["schemas"]["app_effective_launch_manifest"]
    handoff_schema = contract["schemas"]["app_launcher_handoff"]
    entrypoint = effective_schema["fields"]["entrypoint"]["const"]
    defines_digest = dart_defines_digest(defines, contract)
    config_digest = runtime_config_digest(
        args.env,
        contract,
        target=args.target,
    )
    transport_values = {
        "reverseExpectedPorts": args.reverse_expected_ports.strip(),
        "reverseActualPorts": args.reverse_actual_ports.strip(),
        "reverseReceiptDigest": args.reverse_receipt_digest.strip(),
        "consumerLeaseId": args.consumer_lease_id.strip(),
    }
    if args.target not in local_targets and any(transport_values.values()):
        raise ValueError("non-local launcher handoff must not contain local transport")
    if args.transport_required:
        if args.target not in local_targets:
            raise ValueError("local transport can only be required by a local target")
        missing = [key for key, value in transport_values.items() if not value]
        if missing:
            raise ValueError(
                "local transport handoff is incomplete: " + ", ".join(sorted(missing))
            )
        for key in ("reverseReceiptDigest", "consumerLeaseId"):
            if not is_digest_identity(transport_values[key], contract):
                raise ValueError(f"{key} must be a canonical digest identity")
        expected_ports = canonical_ports(transport_values["reverseExpectedPorts"])
        actual_ports = canonical_ports(transport_values["reverseActualPorts"])
        if expected_ports != actual_ports:
            raise ValueError("Android reverse expected/actual ports do not match")
        transport_values["reverseExpectedPorts"] = expected_ports
        transport_values["reverseActualPorts"] = actual_ports
    effective_manifest = {
        "schema": effective_schema["schema_value"],
        "environment": args.env,
        "target": args.target,
        "entrypoint": entrypoint,
        "launchMode": args.launch_mode,
        "dartDefinesDigest": defines_digest,
        "runtimeConfigDigest": config_digest,
        "contentReleaseId": args.content_release_id.strip(),
        "contentManifestDigest": args.content_manifest_digest.strip(),
        "contentReadinessReceiptDigest": (
            args.content_readiness_receipt_digest.strip()
        ),
        "recoveryBaseUrl": defines["CLOUD_GATEWAY_BASE_URL"],
        "publicWebBaseUrl": defines["PUBLIC_WEB_BASE_URL"],
        "appDownloadBaseUrl": defines["APP_DOWNLOAD_BASE_URL"],
        "requiresLocalTransport": args.target in local_targets,
        "transport": {
            "required": args.transport_required,
            **transport_values,
        },
    }
    effective_digest = effective_launch_manifest_digest(effective_manifest, contract)
    handoff = {
        **effective_manifest,
        "schema": handoff_schema["schema_value"],
        "dartDefines": defines,
        "effectiveLaunchManifest": effective_manifest,
        "effectiveLaunchManifestDigest": effective_digest,
    }
    contract_issues = validate_handoff_against_metadata(handoff, contract)
    if contract_issues:
        raise ValueError("; ".join(contract_issues))
    return handoff


def main() -> int:
    try:
        contract = load_launch_manifest_contract()
    except LaunchManifestContractError as exc:
        print(f"GATE_BLOCK: {exc}")
        return 2
    args = _parser(contract).parse_args()
    try:
        handoff = build_handoff(args)
    except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"GATE_BLOCK: {exc}")
        return 2
    print(json.dumps(handoff, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
