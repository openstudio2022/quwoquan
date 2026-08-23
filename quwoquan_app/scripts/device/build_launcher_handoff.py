#!/usr/bin/env python3
"""Build one validated environment/target handoff for Flutter build and run."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.app_identity import (
    build_profile_for_environment,
    launch_policy_for_build_profile,
)
from quwoquan_ops.cli.lib.app_launch_manifest_contract import (
    LaunchManifestContractError,
    build_runtime_config_trust_envelope,
    canonical_ports,
    effective_launch_manifest_digest,
    is_digest_identity,
    load_launch_manifest_contract,
    runtime_config_package_digest,
    runtime_config_trust_envelope_digest,
    validate_handoff_against_metadata,
    validate_runtime_config_package,
)
from quwoquan_ops.cli.lib.app_runtime_config_signing import (
    TRUSTED_PUBLIC_KEYS_FILE_ENV,
    decode_keyring,
)
from quwoquan_ops.cli.lib.local_app_runtime_config_keys import (
    prepare_local_app_runtime_config_signing,
)


APP_DIR = Path(__file__).resolve().parents[2]
TEST_LIVE_LAUNCH_POLICY = "test_live"
PROD_RELEASE_LAUNCH_POLICY = "prod_release"

RuntimeConfigPackageLoader = Callable[[argparse.Namespace], dict[str, Any]]


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
    parser.add_argument(
        "--launch-policy",
        choices=(TEST_LIVE_LAUNCH_POLICY, PROD_RELEASE_LAUNCH_POLICY),
        default="",
    )
    parser.add_argument("--gateway-base-url", default="")
    parser.add_argument("--legal-base-url", default="")
    parser.add_argument("--media-avatar-base-url", default="")
    parser.add_argument("--media-image-base-url", default="")
    parser.add_argument("--media-video-base-url", default="")
    parser.add_argument("--media-upload-base-url", default="")
    parser.add_argument("--rtc-media-connection-url", default="")
    parser.add_argument("--source-git-sha", default="")
    parser.add_argument("--source-tree-digest", default="")
    parser.add_argument("--source-capsule-manifest", default="")
    parser.add_argument("--transport-required", action="store_true")
    parser.add_argument("--reverse-expected-ports", default="")
    parser.add_argument("--reverse-actual-ports", default="")
    parser.add_argument("--reverse-receipt-digest", default="")
    parser.add_argument("--consumer-lease-id", default="")
    parser.add_argument("--runtime-config-trust-output", default="")
    return parser


def _runtime_config_trust_envelope(
    build_profile: str,
) -> dict[str, Any]:
    configured = str(os.environ.get(TRUSTED_PUBLIC_KEYS_FILE_ENV) or "").strip()
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            raise ValueError("App runtime trusted public keyring must be an absolute path")
        absolute = Path(os.path.abspath(path))
        resolved = absolute.resolve()
        for forbidden_root in (
            APP_DIR.parent.resolve(),
            (APP_DIR.parent / ".qwq_output").resolve(),
        ):
            try:
                resolved.relative_to(forbidden_root)
            except ValueError:
                continue
            raise ValueError(
                "App runtime trusted public keyring must stay outside repository "
                "and output roots"
            )
        if absolute.is_symlink() or not absolute.is_file():
            raise ValueError(
                "App runtime trusted public keyring must be a regular non-symlink file"
            )
        if absolute.stat().st_mode & 0o022:
            raise ValueError("App runtime trusted public keyring permissions are unsafe")
        keyring = decode_keyring(absolute.read_bytes())
        return build_runtime_config_trust_envelope(build_profile, keyring)
    if build_profile == "nonprod":
        signing = prepare_local_app_runtime_config_signing(APP_DIR.parent)
        keyring = decode_keyring(signing.trusted_public_keys_path.read_bytes())
    elif build_profile == "prod":
        raise ValueError("Prod App runtime trusted public keyring is required")
    else:
        raise ValueError(f"Unsupported App runtime build profile: {build_profile}")
    return build_runtime_config_trust_envelope(build_profile, keyring)


def materialize_runtime_config_trust_envelope(
    runtime_config_trust_envelope: dict[str, Any],
    raw_output_path: str,
    contract: dict[str, Any],
) -> None:
    output_path = Path(raw_output_path).expanduser()
    if not output_path.is_absolute():
        raise ValueError("Runtime configuration trust output must be an absolute path")
    repository_root = APP_DIR.parent.resolve()
    try:
        output_path.resolve(strict=False).relative_to(repository_root)
    except ValueError:
        pass
    else:
        raise ValueError(
            "Runtime configuration trust output must stay outside the source tree"
        )
    parent = output_path.parent
    if parent.is_symlink() or not parent.is_dir():
        raise ValueError(
            "Runtime configuration trust output parent must be a regular directory"
        )
    if parent.stat().st_mode & 0o077:
        raise ValueError(
            "Runtime configuration trust output parent permissions are unsafe"
        )
    if output_path.is_symlink() or (output_path.exists() and not output_path.is_file()):
        raise ValueError(
            "Runtime configuration trust output must be a regular non-symlink file"
        )
    settings = contract["digest_contract"]["canonical_json"]
    payload = json.dumps(
        runtime_config_trust_envelope,
        ensure_ascii=settings["ensure_ascii"],
        sort_keys=settings["sort_keys"],
        separators=tuple(settings["separators"]),
    ).encode(contract["digest_contract"]["input_encoding"])
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        dir=parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        temporary.replace(output_path)
        directory_descriptor = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def _load_runtime_config_package(args: argparse.Namespace) -> dict[str, Any]:
    package_command = [
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
        "--launch-policy",
        args.launch_policy,
    ]
    for option, value in (
        ("--gateway-base-url", args.gateway_base_url),
        ("--legal-base-url", args.legal_base_url),
        ("--media-avatar-base-url", args.media_avatar_base_url),
        ("--media-image-base-url", args.media_image_base_url),
        ("--media-video-base-url", args.media_video_base_url),
        ("--media-upload-base-url", args.media_upload_base_url),
        ("--rtc-media-connection-url", args.rtc_media_connection_url),
        ("--source-git-sha", args.source_git_sha),
        ("--source-tree-digest", args.source_tree_digest),
        ("--source-capsule-manifest", args.source_capsule_manifest),
    ):
        if value:
            package_command.extend([option, value])
    result = subprocess.run(
        package_command,
        cwd=APP_DIR,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    package = json.loads(result.stdout)
    if not isinstance(package, dict):
        raise ValueError("canonical runtime configuration package must be an object")
    return package


def build_handoff(
    args: argparse.Namespace,
    *,
    runtime_config_package_loader: RuntimeConfigPackageLoader = (
        _load_runtime_config_package
    ),
) -> dict[str, Any]:
    contract = load_launch_manifest_contract()
    expected_environment = contract["target_environment"][args.target]
    local_targets = set(contract["local_transport_targets"])
    if args.env != expected_environment:
        raise ValueError(
            f"target {args.target} requires --env {expected_environment}, got {args.env}"
        )
    build_profile = build_profile_for_environment(args.env)
    expected_policy = launch_policy_for_build_profile(build_profile)
    args.launch_policy = args.launch_policy or expected_policy
    if args.launch_policy != expected_policy:
        raise ValueError(
            f"launch policy {args.launch_policy} is invalid for build profile {build_profile}"
        )
    runtime_config_trust_envelope = _runtime_config_trust_envelope(build_profile)
    runtime_package = runtime_config_package_loader(args)
    package_issues = validate_runtime_config_package(
        runtime_package,
        runtime_config_trust_envelope,
        contract,
    )
    if package_issues:
        raise ValueError("; ".join(package_issues))
    for field, expected in (
        ("environment", args.env),
        ("buildProfile", build_profile),
        ("target", args.target),
        ("launchPolicy", args.launch_policy),
    ):
        if runtime_package.get(field) != expected:
            raise ValueError(
                f"runtime configuration package {field} does not match launcher selection"
            )
    effective_schema = contract["schemas"]["app_effective_launch_manifest"]
    handoff_schema = contract["schemas"]["app_launcher_handoff"]
    entrypoint = effective_schema["fields"]["entrypoint"]["const"]
    package_digest = runtime_config_package_digest(runtime_package, contract)
    trust_envelope_digest = runtime_config_trust_envelope_digest(
        runtime_config_trust_envelope,
        contract,
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
        "buildProfile": build_profile,
        "target": args.target,
        "entrypoint": entrypoint,
        "launchMode": args.launch_mode,
        "launchPolicy": args.launch_policy,
        "runtimeConfigPackageDigest": package_digest,
        "runtimeConfigTrustEnvelopeDigest": trust_envelope_digest,
        "requiresLocalTransport": args.target in local_targets,
        "transport": {
            "required": args.transport_required,
            **transport_values,
        },
    }
    effective_digest = effective_launch_manifest_digest(effective_manifest, contract)
    compile_diagnostics = {"launchMode": args.launch_mode}
    handoff = {
        **effective_manifest,
        "schema": handoff_schema["schema_value"],
        "compileDiagnostics": compile_diagnostics,
        "runtimeConfigPackage": runtime_package,
        "effectiveLaunchManifest": effective_manifest,
        "effectiveLaunchManifestDigest": effective_digest,
    }
    contract_issues = validate_handoff_against_metadata(
        handoff,
        runtime_config_trust_envelope,
        contract,
    )
    if contract_issues:
        raise ValueError("; ".join(contract_issues))
    trust_output = str(getattr(args, "runtime_config_trust_output", "") or "").strip()
    if trust_output:
        materialize_runtime_config_trust_envelope(
            runtime_config_trust_envelope,
            trust_output,
            contract,
        )
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
