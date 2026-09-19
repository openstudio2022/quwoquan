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
    build_runtime_config_trust_envelope,
    runtime_config_trust_envelope_digest,
    validate_runtime_config_trust_envelope,
)
from quwoquan_ops.cli.lib.app_runtime_config_signing import decode_keyring
from quwoquan_ops.cli.lib.local_app_runtime_config_keys import prepare_local_app_runtime_config_signing


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



def materialize_runtime_config_inputs(
    *,
    app_dir: Path,
    build_profile: str,
    platform: str,
    command_env: dict[str, str],
    local_alpha_android: bool = False,
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
    if not trust_path_value and local_alpha_android:
        if build_profile != "nonprod" or platform != "android":
            raise AppArtifactBuildError("APP.PACKAGE.local_runtime_config_trust_scope_invalid")
        try:
            signing = prepare_local_app_runtime_config_signing(Path(__file__).resolve().parents[3])
            keyring = decode_keyring(signing.trusted_public_keys_path.read_bytes())
            envelope = build_runtime_config_trust_envelope("nonprod", keyring)
        except (OSError, TypeError, UnicodeError, ValueError) as error:
            raise AppArtifactBuildError(f"APP.PACKAGE.local_runtime_config_trust_unavailable: {error}") from error
        trust_path = app_dir.parent / ".qwq-private" / "runtime-config-trust.json"
        _write_private(trust_path, (json.dumps(envelope, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8"))
    else:
        if not trust_path_value:
            raise AppArtifactBuildError("APP.PACKAGE.runtime_config_trust_missing: formal build-profile trust envelope is required")
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
        asset_root = app_dir.parent.parent / ".qwq-private" / "runtime-config-assets"
        runtime_root = asset_root / "qwq_runtime"
        _write_private(
            runtime_root / "runtime-config-trust.json", trust_path.read_bytes()
        )
        command_env["QWQ_ANDROID_RUNTIME_CONFIG_ASSET_ROOT"] = str(asset_root)
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
    local_alpha_android: bool = False,
) -> None:
    if platform == "android" and build_mode == "release":
        if local_alpha_android:
            if build_profile != "nonprod" or artifact_format != "apk":
                raise AppArtifactBuildError("APP.PACKAGE.local_android_signing_scope_invalid")
            debug_keystore = Path.home() / ".android" / "debug.keystore"
            if debug_keystore.is_symlink() or not debug_keystore.is_file():
                raise AppArtifactBuildError(
                    "APP.PACKAGE.local_android_signing_missing: canonical debug keystore"
                )
            command_env.update(
                {
                    "QWQ_ANDROID_RELEASE_KEYSTORE_PATH": str(debug_keystore),
                    "QWQ_ANDROID_RELEASE_STORE_PASSWORD": "android",
                    "QWQ_ANDROID_RELEASE_KEY_ALIAS": "androiddebugkey",
                    "QWQ_ANDROID_RELEASE_KEY_PASSWORD": "android",
                }
            )
            return
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
