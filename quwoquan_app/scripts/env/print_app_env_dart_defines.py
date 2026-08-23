#!/usr/bin/env python3
"""Print one signed App runtime configuration package as canonical JSON."""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timedelta, timezone
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.app_launch_manifest_contract import (  # noqa: E402
    build_runtime_config_trust_envelope,
    load_launch_manifest_contract,
    runtime_config_payload_digest,
    validate_runtime_config_package,
)
from quwoquan_ops.cli.lib.app_identity import (  # noqa: E402
    build_profile_for_environment,
    launch_policy_for_build_profile,
)
from quwoquan_ops.cli.lib.app_runtime_config_signing import (  # noqa: E402
    canonical_signed_payload,
    resolve_signing_material,
    sign_payload,
    validate_signing_material,
)
from quwoquan_ops.cli.lib.environment_topology import (  # noqa: E402
    get_target,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.local_app_runtime_config_keys import (  # noqa: E402
    prepare_local_app_runtime_config_signing,
)
from quwoquan_ops.cli.lib.output_paths import (  # noqa: E402
    app_deployment_package_dir,
    deployment_target_for_env,
)

SOURCE_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
SOURCE_TREE_DIGEST = re.compile(r"^(?:sha1:[0-9a-f]{40}|sha256:[0-9a-f]{64})$")


def test_live_runtime_values(environment: str, target_name: str) -> dict[str, str]:
    target = get_target(load_environment_topology(), target_name)
    if target.get("env") != environment or environment not in {"alpha", "beta", "gamma"}:
        raise SystemExit("test_live target/environment selection is invalid")
    public_bases = target.get("publicBases")
    if not isinstance(public_bases, dict):
        raise SystemExit("test_live target has no canonical publicBases")
    mapping = {
        "gatewayBaseUrl": "api",
        "legalBaseUrl": "legal",
        "publicWebBaseUrl": "publicWeb",
        "appDownloadBaseUrl": "appDownload",
        "realtimeBaseUrl": "realtime",
        "mediaAvatarCdnBaseUrl": "mediaAvatar",
        "mediaImageCdnBaseUrl": "mediaImage",
        "mediaVideoCdnBaseUrl": "mediaVideo",
        "mediaUploadBaseUrl": "mediaUpload",
        "rtcMediaConnectionUrl": "rtc",
    }
    values = {
        "appRuntimeEnv": environment,
        **{key: str(public_bases.get(source) or "") for key, source in mapping.items()},
    }
    expected_host = f"{environment}.quwoquan.com"
    for key in mapping:
        value = values[key]
        hostname = (urlparse(value).hostname or "").lower()
        if hostname != expected_host and not hostname.endswith(f".{expected_host}"):
            raise SystemExit(
                f"test_live {key} must remain inside {environment} topology"
            )
    return values


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
        "gatewayBaseUrl": args.gateway_base_url,
        "legalBaseUrl": args.legal_base_url,
        "mediaAvatarCdnBaseUrl": args.media_avatar_base_url,
        "mediaImageCdnBaseUrl": args.media_image_base_url,
        "mediaVideoCdnBaseUrl": args.media_video_base_url,
        "mediaUploadBaseUrl": args.media_upload_base_url,
        "rtcMediaConnectionUrl": args.rtc_media_connection_url,
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


def _source_identity(
    *,
    source_git_sha: str,
    source_tree_digest: str,
    source_capsule_manifest: str,
) -> tuple[str, str]:
    git_sha = source_git_sha.strip()
    tree_digest = source_tree_digest.strip()
    capsule_value = source_capsule_manifest.strip() or str(
        os.environ.get("QWQ_PACKAGE_SOURCE_CAPSULE_MANIFEST") or ""
    ).strip()
    if capsule_value:
        capsule_path = Path(capsule_value).expanduser()
        if not capsule_path.is_absolute() or not capsule_path.is_file():
            raise ValueError("source capsule manifest must be an existing absolute path")
        from quwoquan_ops.cli.lib.package_reuse.input_capsule import (
            verify_package_input_capsule,
        )

        capsule = verify_package_input_capsule(capsule_path.parent)
        if capsule_path.resolve() != (capsule_path.parent / "manifest.json").resolve():
            raise ValueError("source capsule manifest must be the canonical manifest.json")
        capsule_git_sha = str(capsule.get("sourceRevision") or "").strip()
        capsule_tree_digest = str(
            capsule.get("deploymentInputDigest") or ""
        ).strip()
        if git_sha and git_sha != capsule_git_sha:
            raise ValueError("sourceGitSha disagrees with source capsule")
        if tree_digest and tree_digest != capsule_tree_digest:
            raise ValueError("sourceTreeDigest disagrees with source capsule")
        git_sha = capsule_git_sha
        tree_digest = capsule_tree_digest
    if not git_sha:
        git_sha = str(os.environ.get("QWQ_PACKAGE_SOURCE_REVISION") or "").strip()
    if not tree_digest:
        tree_digest = str(os.environ.get("QWQ_PACKAGE_SOURCE_TREE_DIGEST") or "").strip()
    revision_result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    tree_result = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    audited_git_sha = revision_result.stdout.strip()
    audited_tree_digest = "sha1:" + tree_result.stdout.strip()
    if not git_sha and not tree_digest:
        git_sha = audited_git_sha
        tree_digest = audited_tree_digest
    if SOURCE_GIT_SHA.fullmatch(git_sha) is None:
        raise ValueError("sourceGitSha must come from an audited Git identity")
    if SOURCE_TREE_DIGEST.fullmatch(tree_digest) is None:
        raise ValueError(
            "sourceTreeDigest must come from a source capsule or audited Git identity"
        )
    if not capsule_value and (
        revision_result.returncode != 0
        or tree_result.returncode != 0
        or git_sha != audited_git_sha
        or tree_digest != audited_tree_digest
    ):
        raise ValueError("explicit source identity disagrees with audited Git identity")
    return git_sha, tree_digest


def _rfc3339(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def build_runtime_config_package(
    *,
    environment: str,
    target: str,
    launch_policy: str,
    values: dict[str, str],
    source_git_sha: str,
    source_tree_digest: str,
    signing: Any,
    issued_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    contract = load_launch_manifest_contract()
    build_profile = build_profile_for_environment(environment)
    expected_policy = launch_policy_for_build_profile(build_profile)
    if launch_policy != expected_policy:
        raise ValueError(
            f"launchPolicy {launch_policy} is invalid for buildProfile {build_profile}"
        )
    if contract["target_environment"].get(target) != environment:
        raise ValueError(f"target {target} does not belong to {environment}")
    declared_runtime_keys = tuple(contract["runtime_value_keys"])
    runtime = {key: str(values.get(key) or "").strip() for key in declared_runtime_keys}
    missing = [key for key, value in runtime.items() if not value]
    if missing:
        raise ValueError(
            "app runtime config is missing explicit values: " + ", ".join(missing)
        )
    if runtime["appRuntimeEnv"] != environment:
        raise ValueError("runtime appRuntimeEnv does not match package environment")
    issued = issued_at or datetime.now(timezone.utc)
    expires = expires_at or (
        issued
        + timedelta(
            seconds=int(contract["runtime_config_package"]["max_lifetime_seconds"])
        )
    )
    private_bytes, _, keyring = validate_signing_material(ROOT, signing)
    package: dict[str, Any] = {
        "schema": contract["schemas"]["runtime_config_package"]["schema_value"],
        "schemaVersion": contract["runtime_config_package"]["schema_version"],
        "environment": environment,
        "buildProfile": build_profile,
        "target": target,
        "launchPolicy": launch_policy,
        "issuedAt": _rfc3339(issued),
        "expiresAt": _rfc3339(expires),
        "sourceGitSha": source_git_sha,
        "sourceTreeDigest": source_tree_digest,
        "runtime": runtime,
        "payloadDigest": "",
        "signatureAlgorithm": "ed25519",
        "signatureKeyId": signing.key_id,
        "trustedPublicKeys": keyring,
        "signature": "",
    }
    package["payloadDigest"] = runtime_config_payload_digest(package, contract)
    package["signature"] = base64.b64encode(
        sign_payload(private_bytes, canonical_signed_payload(package))
    ).decode("ascii")
    runtime_config_trust_envelope = build_runtime_config_trust_envelope(
        build_profile,
        keyring,
        contract,
    )
    issues = validate_runtime_config_package(
        package,
        runtime_config_trust_envelope,
        contract,
        now=issued,
    )
    if issues:
        raise ValueError("; ".join(issues))
    return package


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", default="gamma")
    parser.add_argument("--target", default="")
    parser.add_argument("--format", choices=["args", "shell", "json"], default="json")
    parser.add_argument("--gateway-base-url", default="")
    parser.add_argument("--legal-base-url", default="")
    parser.add_argument("--media-avatar-base-url", default="")
    parser.add_argument("--media-image-base-url", default="")
    parser.add_argument("--media-video-base-url", default="")
    parser.add_argument("--media-upload-base-url", default="")
    parser.add_argument("--rtc-media-connection-url", default="")
    parser.add_argument("--launch-mode", default="")
    parser.add_argument(
        "--launch-policy",
        choices=("test_live", "prod_release"),
        default="",
    )
    parser.add_argument("--source-git-sha", default="")
    parser.add_argument("--source-tree-digest", default="")
    parser.add_argument("--source-capsule-manifest", default="")
    args = parser.parse_args()

    if args.format in {"args", "shell"}:
        print(
            "GATE_BLOCK: endpoint Dart define output is retired; request --format=json",
            file=sys.stderr,
        )
        return 2
    target_name = args.target or deployment_target_for_env(args.env)
    args.launch_policy = args.launch_policy or (
        "prod_release" if args.env == "prod" else "test_live"
    )
    if args.launch_policy == "test_live":
        values = test_live_runtime_values(args.env, target_name)
    else:
        package_dir = app_deployment_package_dir(args.env, target=target_name)
        cfg = package_dir / "app_runtime.yaml"
        if not cfg.exists():
            raise SystemExit(
                "packaged app runtime config not found; run stackctl package first: "
                f"{cfg}"
            )
        package_report_path = package_dir / "report.json"
        if not package_report_path.is_file():
            raise SystemExit(f"packaged app runtime report not found: {package_report_path}")
        package_report = json.loads(package_report_path.read_text(encoding="utf-8"))
        if (
            package_report.get("status") != "packaged"
            or package_report.get("env") != args.env
            or package_report.get("target") != target_name
        ):
            raise SystemExit(
                f"packaged app runtime identity mismatch: {args.env}/{target_name}"
            )
        values = parse_runtime_yaml(cfg)
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
    try:
        source_git_sha, source_tree_digest = _source_identity(
            source_git_sha=args.source_git_sha,
            source_tree_digest=args.source_tree_digest,
            source_capsule_manifest=args.source_capsule_manifest,
        )
        if args.env in {"alpha", "beta", "gamma"} and not any(
            os.environ.get(key)
            for key in (
                "QWQ_APP_RUNTIME_CONFIG_SIGNING_KEY_ID",
                "QWQ_APP_RUNTIME_CONFIG_SIGNING_PRIVATE_KEY_FILE",
                "QWQ_APP_RUNTIME_CONFIG_TRUSTED_PUBLIC_KEYS_FILE",
            )
        ):
            signing = prepare_local_app_runtime_config_signing(ROOT)
        else:
            signing = resolve_signing_material(ROOT)
        package = build_runtime_config_package(
            environment=args.env,
            target=target_name,
            launch_policy=args.launch_policy,
            values=values,
            source_git_sha=source_git_sha,
            source_tree_digest=source_tree_digest,
            signing=signing,
        )
    except (KeyError, OSError, RuntimeError, ValueError) as exc:
        print(f"GATE_BLOCK: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(package, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
