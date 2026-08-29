"""Protected and runtime-config input materialization for AppArtifact builds.

角色：lib。owner 为 quwoquan_ops/cli/commands/package_app_artifact.py。
"""

from __future__ import annotations

import base64
import json
import os
import re
import stat
from pathlib import Path

from quwoquan_ops.cli.commands.package_app_artifact_identity import (
    AppArtifactBuildError,
)
from quwoquan_ops.cli.lib.app_launch_manifest_contract import (
    runtime_config_trust_envelope_digest,
    validate_runtime_config_trust_envelope,
)


def make_writable(root: Path) -> None:
    for path in (root, *root.rglob("*")):
        if path.is_symlink():
            continue
        mode = path.stat().st_mode
        if path.is_dir():
            path.chmod(mode | stat.S_IWUSR | stat.S_IXUSR)
        else:
            path.chmod(mode | stat.S_IWUSR)


def _write_private(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    path.chmod(0o600)


def _decode_secret(value: str, *, label: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except ValueError as error:
        raise AppArtifactBuildError(
            f"APP.PACKAGE.protected_input_invalid: {label} is not base64"
        ) from error


def _validated_google_services_bytes(
    *,
    raw: str,
    expected_application_id: str,
    label: str,
) -> bytes:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise AppArtifactBuildError(
            f"APP.PACKAGE.protected_input_invalid: {label} is not JSON"
        ) from error
    clients = payload.get("client") if isinstance(payload, dict) else None
    if not isinstance(clients, list):
        raise AppArtifactBuildError(
            f"APP.PACKAGE.protected_input_invalid: {label}.client is missing"
        )
    package_names = {
        str(android_info.get("package_name") or "").strip()
        for client in clients
        if isinstance(client, dict)
        for client_info in [client.get("client_info")]
        if isinstance(client_info, dict)
        for android_info in [client_info.get("android_client_info")]
        if isinstance(android_info, dict)
    }
    if package_names != {expected_application_id}:
        raise AppArtifactBuildError(
            "APP.PACKAGE.provider_identity_mismatch: "
            f"{label} package_name must be exactly {expected_application_id}"
        )
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def materialize_runtime_config_inputs(
    *,
    app_dir: Path,
    build_profile: str,
    platform: str,
    command_env: dict[str, str],
) -> str:
    package_path_value = os.environ.get(
        "QWQ_APP_RUNTIME_CONFIG_PACKAGE_PATH", ""
    ).strip()
    if package_path_value:
        raise AppArtifactBuildError(
            "APP.PACKAGE.runtime_config_package_forbidden: target runtime package must be "
            "activated after installation and cannot enter AppArtifact"
        )
    trust_path_value = os.environ.get("QWQ_APP_RUNTIME_CONFIG_TRUST_PATH", "").strip()
    if not trust_path_value:
        raise AppArtifactBuildError(
            "APP.PACKAGE.runtime_config_trust_missing: build-profile trust envelope is required"
        )
    trust_path = Path(trust_path_value).expanduser()
    if (
        not trust_path.is_absolute()
        or trust_path.is_symlink()
        or not trust_path.is_file()
    ):
        raise AppArtifactBuildError(
            "APP.PACKAGE.runtime_config_input_invalid: trust envelope must be an absolute "
            "regular non-symlink file"
        )
    if trust_path.stat().st_size <= 0 or trust_path.stat().st_size > 1024 * 1024:
        raise AppArtifactBuildError(
            "APP.PACKAGE.runtime_config_input_invalid: trust envelope size is invalid"
        )
    try:
        trust = json.loads(trust_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AppArtifactBuildError(
            "APP.PACKAGE.runtime_config_input_invalid: trust envelope is malformed"
        ) from error
    if not isinstance(trust, dict):
        raise AppArtifactBuildError(
            "APP.PACKAGE.runtime_config_input_invalid: trust envelope must be an object"
        )
    issues = validate_runtime_config_trust_envelope(trust)
    if issues:
        raise AppArtifactBuildError(
            "APP.PACKAGE.runtime_config_trust_invalid: " + "; ".join(issues)
        )
    if trust.get("buildProfile") != build_profile:
        raise AppArtifactBuildError(
            "APP.PACKAGE.runtime_config_profile_mismatch: trust envelope buildProfile "
            "must match the build product"
        )
    serialized_trust = json.dumps(trust, ensure_ascii=False, separators=(",", ":"))
    if re.search(r"private[_-]?key", serialized_trust, flags=re.IGNORECASE):
        raise AppArtifactBuildError(
            "APP.PACKAGE.private_key_forbidden: private signing material cannot enter App output"
        )
    trust_digest = runtime_config_trust_envelope_digest(trust)
    if platform == "android":
        runtime_root = app_dir / "android/app/src/main/assets/qwq_runtime"
        _write_private(
            runtime_root / "runtime-config-trust.json", trust_path.read_bytes()
        )
    elif platform == "ios":
        command_env["QWQ_IOS_RUNTIME_CONFIG_TRUST_PATH"] = str(trust_path)
    else:
        raise AppArtifactBuildError(
            "APP.PACKAGE.runtime_config_platform_invalid: trust envelope is mobile-only"
        )
    return trust_digest


def materialize_protected_inputs(
    *,
    app_dir: Path,
    build_profile: str,
    platform: str,
    build_mode: str,
    artifact_format: str,
    application_id: str,
    command_env: dict[str, str],
    private_dir: Path,
) -> None:
    if platform == "android" and build_mode == "release":
        firebase_key = f"QWQ_ANDROID_{build_profile.upper()}_GOOGLE_SERVICES_JSON"
        firebase_json = os.environ.get(firebase_key, "").strip()
        if not firebase_json:
            raise AppArtifactBuildError(
                f"APP.PACKAGE.protected_input_missing: {firebase_key}"
            )
        _write_private(
            app_dir / "android/app/google-services.json",
            _validated_google_services_bytes(
                raw=firebase_json,
                expected_application_id=application_id,
                label=firebase_key,
            ),
        )
        keystore_b64 = os.environ.get("QWQ_ANDROID_RELEASE_KEYSTORE_B64", "").strip()
        required = {
            "QWQ_ANDROID_RELEASE_KEYSTORE_B64": keystore_b64,
            "QWQ_ANDROID_RELEASE_STORE_PASSWORD": os.environ.get(
                "QWQ_ANDROID_RELEASE_STORE_PASSWORD", ""
            ).strip(),
            "QWQ_ANDROID_RELEASE_KEY_ALIAS": os.environ.get(
                "QWQ_ANDROID_RELEASE_KEY_ALIAS", ""
            ).strip(),
            "QWQ_ANDROID_RELEASE_KEY_PASSWORD": os.environ.get(
                "QWQ_ANDROID_RELEASE_KEY_PASSWORD", ""
            ).strip(),
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            raise AppArtifactBuildError(
                "APP.PACKAGE.protected_input_missing: " + ",".join(missing)
            )
        keystore = private_dir / "android-release.jks"
        _write_private(
            keystore,
            _decode_secret(keystore_b64, label="Android release keystore"),
        )
        command_env.update(
            {
                "QWQ_ANDROID_RELEASE_KEYSTORE_PATH": str(keystore),
                "QWQ_ANDROID_RELEASE_STORE_PASSWORD": required[
                    "QWQ_ANDROID_RELEASE_STORE_PASSWORD"
                ],
                "QWQ_ANDROID_RELEASE_KEY_ALIAS": required[
                    "QWQ_ANDROID_RELEASE_KEY_ALIAS"
                ],
                "QWQ_ANDROID_RELEASE_KEY_PASSWORD": required[
                    "QWQ_ANDROID_RELEASE_KEY_PASSWORD"
                ],
            }
        )
    if platform == "ios" and artifact_format == "ipa":
        export_options = os.environ.get("QWQ_IOS_EXPORT_OPTIONS_PLIST_B64", "").strip()
        if not export_options:
            raise AppArtifactBuildError(
                "APP.PACKAGE.protected_input_missing: QWQ_IOS_EXPORT_OPTIONS_PLIST_B64"
            )
        export_path = private_dir / "ExportOptions.plist"
        _write_private(
            export_path,
            _decode_secret(export_options, label="iOS export options"),
        )
        command_env["QWQ_IOS_EXPORT_OPTIONS_PLIST"] = str(export_path)
