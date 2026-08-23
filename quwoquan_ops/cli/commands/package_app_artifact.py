"""Canonical build-product App compiler and artifact manifest writer.

``stackctl package --kind app-artifact --build-product-id ...`` is the only
production App build writer. It freezes one read-only source capsule, resolves the
complete producer identity from canonical metadata, builds from a private writable
projection, reads identity back from the result, scans production purity, and writes
one ``app-artifact-manifest`` beside the immutable artifact.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from quwoquan_ops.cli.commands.package_app_artifact_identity import (
    AppArtifactBuildError,
    read_android_identity,
    read_ios_identity,
    signing_digest,
)
from quwoquan_ops.cli.lib.app_dependency_toolchain import (
    AppDependencyToolchainError,
    resolve_cocoapods_executable,
)
from quwoquan_ops.cli.lib.app_identity import (
    ARTIFACT_METADATA_PATH,
    AppIdentityError,
    application_id_for_build_product,
    resolve_app_identity,
    resolve_build_product,
    supported_build_products,
)
from quwoquan_ops.cli.lib.app_launch_manifest_contract import (
    runtime_config_trust_envelope_digest,
    validate_runtime_config_trust_envelope,
)
from quwoquan_ops.cli.lib.common import load_json_yaml
from quwoquan_ops.cli.lib.package_reuse import (
    materialize_package_input_capsule,
    workspace_snapshot,
)
_BASELINE_BUILD_PRODUCT_IDS = (
    "android-nonprod-apk",
    "android-prod-apk",
    "ios-nonprod-app",
    "ios-prod-app",
    "web-shared",
)
_LEGACY_APP_BUILD_ARGUMENTS = (
    ("env", "--env"),
    ("target", "--target"),
    ("app_platform", "--app-platform"),
    ("app_build_mode", "--app-build-mode"),
    ("distribution_class", "--distribution-class"),
    ("artifact_format", "--artifact-format"),
    ("device", "--device"),
    ("service", "--service"),
    ("release_attestation", "--release-attestation"),
    ("rollback_release_attestation", "--rollback-release-attestation"),
)
_REPO_BUILD_TARGET = "app-build-products"


def _service_environment_capsule_roots() -> tuple[str, ...]:
    services_root = _ROOT / "quwoquan_service/services"
    roots = [
        path.relative_to(_ROOT).as_posix()
        for path in sorted(services_root.glob("*/environments"))
        if path.is_dir()
    ]
    platform_environments = (
        _ROOT / "quwoquan_service/control-plane/platform-ops/environments"
    )
    if platform_environments.is_dir():
        roots.append(platform_environments.relative_to(_ROOT).as_posix())
    return tuple(roots)


_CAPSULE_ROOTS = (
    "quwoquan_app",
    "quwoquan_ops",
    "quwoquan_service/contracts/metadata",
    "quwoquan_service/contracts/runtime_errors/packages/dart/quwoquan_runtime_errors",
    *_service_environment_capsule_roots(),
)
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_EMPTY_STATUS_DIGEST = (
    "sha256:e3b0c44298fc1c149afbf4c8996fb924"
    "27ae41e4649b934ca495991b7852b855"
)


def _distribution_classes() -> dict[str, Any]:
    document = load_json_yaml(ARTIFACT_METADATA_PATH)
    classes = document.get("distribution_classes")
    if not isinstance(classes, dict) or not classes:
        raise AppIdentityError("distribution_classes metadata is missing")
    return classes


def _artifact_digest(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_file():
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return "sha256:" + digest.hexdigest()
    if not path.is_dir():
        raise AppArtifactBuildError(f"APP.PACKAGE.artifact_missing: {path}")
    for child in sorted(item for item in path.rglob("*") if item.is_file()):
        relative = child.relative_to(path).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(child.stat().st_size.to_bytes(8, "big"))
        with child.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _scan_artifact(path: Path, platform: str) -> tuple[list[str], dict[str, object]]:
    verifier_path = (
        _ROOT
        / "quwoquan_app/scripts/runtime/architecture/verify_production_release_artifact.py"
    )
    spec = importlib.util.spec_from_file_location(
        "_qwq_production_artifact_verifier", verifier_path
    )
    if spec is None or spec.loader is None:
        raise AppArtifactBuildError("APP.PACKAGE.purity_verifier_missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.scan_artifact(path, platform)


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    log_path: Path,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    with log_path.open("a", encoding="utf-8") as log:
        log.write("$ " + " ".join(command) + "\n")
        log.write(result.stdout)
        log.write(result.stderr)
        log.write(f"\n[exitCode={result.returncode}]\n")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        first = detail[0] if detail else "command failed without output"
        raise AppArtifactBuildError(f"APP.PACKAGE.compile_failed: {first}")
    return result


def _make_writable(root: Path) -> None:
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
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _materialize_runtime_config_inputs(
    *,
    app_dir: Path,
    build_profile: str,
    platform: str,
    command_env: dict[str, str],
) -> str:
    package_path_value = os.environ.get("QWQ_APP_RUNTIME_CONFIG_PACKAGE_PATH", "").strip()
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
    if not trust_path.is_absolute() or trust_path.is_symlink() or not trust_path.is_file():
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
        _write_private(runtime_root / "runtime-config-trust.json", trust_path.read_bytes())
    elif platform == "ios":
        command_env["QWQ_IOS_RUNTIME_CONFIG_TRUST_PATH"] = str(trust_path)
    else:
        raise AppArtifactBuildError(
            "APP.PACKAGE.runtime_config_platform_invalid: trust envelope is mobile-only"
        )
    return trust_digest


def _materialize_protected_inputs(
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
        keystore_b64 = os.environ.get(
            "QWQ_ANDROID_RELEASE_KEYSTORE_B64", ""
        ).strip()
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


def _copy_artifact(source: Path, destination: Path) -> Path:
    if destination.exists():
        raise AppArtifactBuildError(
            f"APP.PACKAGE.output_collision: {destination}"
        )
    if source.is_dir():
        shutil.copytree(source, destination, symlinks=True)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return destination


def _ios_unsigned_release_command(
    *,
    build_profile: str,
    entrypoint: str = "lib/main_prod.dart",
) -> list[str]:
    return [
        "flutter",
        "build",
        "ios",
        "--release",
        "--no-codesign",
        "--flavor",
        build_profile,
        "--target",
        entrypoint,
        "--no-pub",
    ]


def _build_from_capsule(
    *,
    build_product_id: str,
    build_profile: str,
    platform: str,
    build_mode: str,
    artifact_format: str,
    application_id: str,
    attempt_dir: Path,
) -> dict[str, Any]:
    capsule_root = attempt_dir / "input-capsule"
    capsule = materialize_package_input_capsule(
        _CAPSULE_ROOTS,
        capsule_root=capsule_root,
    )
    log_path = attempt_dir / "compile.log"
    with tempfile.TemporaryDirectory(
        prefix=f"qwq-app-{build_product_id}-",
        dir=str(attempt_dir.parent),
    ) as raw_workspace:
        workspace = Path(raw_workspace) / "repo"
        shutil.copytree(capsule_root / "repo", workspace, symlinks=True)
        _make_writable(workspace)
        app_dir = workspace / "quwoquan_app"
        command_env = dict(os.environ)
        for key in (
            "QWQ_APP_RUNTIME_ENV",
            "QWQ_LAUNCH_TARGET",
            "QWQ_APP_LAUNCH_MODE",
            "QWQ_APP_LAUNCH_POLICY",
            "QWQ_DART_DEFINES_DIGEST",
            "QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST",
            "QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST",
            "QWQ_APP_RECOVERY_BASE_URL",
            "QWQ_APP_PUBLIC_WEB_URL",
            "QWQ_APP_DOWNLOAD_BASE_URL",
            "QWQ_LAUNCH_HANDOFF_JSON",
            "DART_DEFINES",
        ):
            command_env.pop(key, None)
        command_env.update(
            {
                "PYTHONDONTWRITEBYTECODE": "1",
                "QWQ_APP_BUILD_CONTEXT": "package-only",
                "QWQ_APP_BUILD_PROFILE": build_profile,
            }
        )
        private_dir = Path(raw_workspace) / "protected"
        private_dir.mkdir(mode=0o700)
        runtime_config_trust_envelope_digest_value: str | None = None
        if platform in {"android", "ios"}:
            runtime_config_trust_envelope_digest_value = _materialize_runtime_config_inputs(
                app_dir=app_dir,
                build_profile=build_profile,
                platform=platform,
                command_env=command_env,
            )
        _materialize_protected_inputs(
            app_dir=app_dir,
            build_profile=build_profile,
            platform=platform,
            build_mode=build_mode,
            artifact_format=artifact_format,
            application_id=application_id,
            command_env=command_env,
            private_dir=private_dir,
        )
        _run(
            ["flutter", "pub", "get", "--offline", "--enforce-lockfile"],
            cwd=app_dir,
            env=command_env,
            log_path=log_path,
        )
        if platform == "ios":
            try:
                pod = resolve_cocoapods_executable(
                    os.environ.get("QWQ_COCOAPODS_EXECUTABLE", "")
                )
            except AppDependencyToolchainError as error:
                raise AppArtifactBuildError(
                    f"APP.DEPENDENCY.cocoapods_mixed: {error}"
                ) from error
            _run(
                [pod, "install", "--deployment"],
                cwd=app_dir / "ios",
                env=command_env,
                log_path=log_path,
            )
        mode_flag = f"--{build_mode}"
        entrypoint = "lib/main_prod.dart"
        if platform == "android":
            # artifactFormat 是显式构建输入（DEC-005）；官网与全部 APK 市场
            # 复用同一 release APK，AAB 只按渠道硬需求单独构建。
            kind = "appbundle" if artifact_format == "aab" else "apk"
            _run(
                [
                    "flutter",
                    "build",
                    kind,
                    mode_flag,
                    "--flavor",
                    build_profile,
                    "--target",
                    entrypoint,
                    "--no-pub",
                ],
                cwd=app_dir,
                env=command_env,
                log_path=log_path,
            )
            if kind == "appbundle":
                source_artifact = (
                    app_dir
                    / f"build/app/outputs/bundle/{build_profile}Release/app-{build_profile}-release.aab"
                )
                if not source_artifact.is_file():
                    source_artifact = app_dir / "build/app/outputs/bundle/release/app-release.aab"
            else:
                source_artifact = (
                    app_dir
                    / f"build/app/outputs/flutter-apk/app-{build_profile}-{build_mode}.apk"
                )
                if not source_artifact.is_file():
                    source_artifact = (
                        app_dir / f"build/app/outputs/flutter-apk/app-{build_mode}.apk"
                    )
            artifact = _copy_artifact(
                source_artifact,
                attempt_dir / f"{build_product_id}{source_artifact.suffix}",
            )
            read_android_identity(artifact, application_id)
        elif platform == "ios":
            if artifact_format == "ipa":
                export_options = command_env["QWQ_IOS_EXPORT_OPTIONS_PLIST"]
                _run(
                    [
                        "flutter",
                        "build",
                        "ipa",
                        mode_flag,
                        "--flavor",
                        build_profile,
                        "--target",
                        entrypoint,
                        "--no-pub",
                        "--export-options-plist",
                        export_options,
                    ],
                    cwd=app_dir,
                    env=command_env,
                    log_path=log_path,
                )
                ipa_files = sorted((app_dir / "build/ios/ipa").glob("*.ipa"))
                if len(ipa_files) != 1:
                    raise AppArtifactBuildError(
                        "APP.PACKAGE.artifact_missing: expected one IPA"
                    )
                artifact = _copy_artifact(
                    ipa_files[0], attempt_dir / ipa_files[0].name
                )
            elif build_mode == "release":
                # Flutter AOT Release/Profile is physical-device only.  Build an
                # unsigned iphoneos .app for compile evidence; simulator launch
                # remains a separate non-promotable Debug gate.
                _run(
                    _ios_unsigned_release_command(
                        build_profile=build_profile,
                        entrypoint=entrypoint,
                    ),
                    cwd=app_dir,
                    env=command_env,
                    log_path=log_path,
                )
                artifact = _copy_artifact(
                    app_dir / "build/ios/iphoneos/Runner.app",
                    attempt_dir / f"{build_product_id}.app",
                )
            else:
                _run(
                    [
                        "flutter",
                        "build",
                        "ios",
                        mode_flag,
                        "--simulator",
                        "--no-codesign",
                        "--flavor",
                        build_profile,
                        "--target",
                        entrypoint,
                        "--no-pub",
                    ],
                    cwd=app_dir,
                    env=command_env,
                    log_path=log_path,
                )
                source_artifact = app_dir / "build/ios/iphonesimulator/Runner.app"
                artifact = _copy_artifact(
                    source_artifact,
                    attempt_dir / f"{build_product_id}.app",
                )
            if artifact.suffix == ".app":
                read_ios_identity(artifact, application_id)
        else:
            web_output = app_dir / "build/web-shared"
            _run(
                [
                    "flutter",
                    "build",
                    "web",
                    "--release",
                    "--pwa-strategy=offline-first",
                    f"--output={web_output}",
                    "--target",
                    entrypoint,
                    "--no-pub",
                ],
                cwd=app_dir,
                env=command_env,
                log_path=log_path,
            )
            required_web_outputs = (
                "index.html",
                "main.dart.js",
                "manifest.json",
                "flutter_service_worker.js",
            )
            missing_web_outputs = [
                name for name in required_web_outputs if not (web_output / name).is_file()
            ]
            if missing_web_outputs:
                raise AppArtifactBuildError(
                    "APP.PACKAGE.artifact_missing: Web output is incomplete: "
                    + ", ".join(missing_web_outputs)
                )
            artifact = _copy_artifact(web_output, attempt_dir / build_product_id)
        findings, sbom = _scan_artifact(artifact, platform)
        if findings:
            raise AppArtifactBuildError(
                "APP.PACKAGE.production_test_dependency_leak: " + findings[0]
            )
        (attempt_dir / "sbom.spdx.json").write_text(
            json.dumps(sbom, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        build: dict[str, Any] = {
            "artifactPath": str(artifact),
            "artifactDigest": _artifact_digest(artifact),
            "signingIdentityDigest": signing_digest(platform, artifact),
            "sourceCapsuleDigest": str(capsule["deploymentInputDigest"]),
            "sourceStatusDigest": str(capsule["workspaceStatusDigest"]),
        }
        if runtime_config_trust_envelope_digest_value is not None:
            build["runtimeConfigTrustEnvelopeDigest"] = (
                runtime_config_trust_envelope_digest_value
            )
        return build


def _version() -> tuple[str, str]:
    value = yaml.safe_load((_ROOT / "quwoquan_app/pubspec.yaml").read_text())
    version = str(value.get("version") or "")
    display, separator, build = version.partition("+")
    return display, build if separator else "1"


def _git_identity() -> tuple[str, str]:
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    tree = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"],
        cwd=_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return revision, "sha1:" + tree


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _build_provenance_digest(
    *,
    build_product_id: str,
    source_git_sha: str,
    source_tree_digest: str,
    source_capsule_digest: str,
    artifact_digest: str,
    signing_identity_digest: str,
) -> str:
    return _canonical_digest(
        {
            "schema": "app-build-provenance",
            "buildProductId": build_product_id,
            "sourceGitSha": source_git_sha,
            "sourceTreeDigest": source_tree_digest,
            "sourceCapsuleDigest": source_capsule_digest,
            "artifactDigest": artifact_digest,
            "signingIdentityDigest": signing_identity_digest,
        }
    )


def command_package_app_artifact(args: argparse.Namespace) -> dict[str, Any]:
    build_product_id = str(getattr(args, "build_product_id", "") or "").strip()
    artifact_path = str(getattr(args, "artifact_path", "") or "").strip()
    blockers: list[str] = []

    canonical_product_ids = tuple(
        product.build_product_id for product in supported_build_products()
    )
    if canonical_product_ids != _BASELINE_BUILD_PRODUCT_IDS:
        blockers.append(
            "APP.PACKAGE.build_product_baseline_invalid: canonical baseline must be exactly "
            + ",".join(_BASELINE_BUILD_PRODUCT_IDS)
        )
    if not build_product_id:
        blockers.append("--build-product-id is required for app-artifact")
    for attribute, flag in _LEGACY_APP_BUILD_ARGUMENTS:
        if str(getattr(args, attribute, "") or "").strip():
            blockers.append(
                f"{flag} is forbidden for app-artifact; use --build-product-id only"
            )
    if artifact_path:
        blockers.append(
            "--artifact-path bypass is forbidden; app-artifact always compiles its source capsule"
        )

    product = None
    if build_product_id:
        try:
            product = resolve_build_product(build_product_id)
        except AppIdentityError as error:
            blockers.append(str(error))

    platform = product.platform if product is not None else ""
    build_profile = product.build_profile if product is not None else ""
    build_mode = product.build_mode if product is not None else ""
    distribution_class = product.distribution_class if product is not None else ""
    artifact_format = product.artifact_format if product is not None else ""
    application_id = ""
    display_name = ""
    identity = None
    declaration = None
    if product is not None:
        try:
            application_id = application_id_for_build_product(build_product_id)
            if platform in {"android", "ios"}:
                identity = resolve_app_identity(
                    platform=platform,
                    build_profile=build_profile,
                    build_mode=build_mode,
                )
                display_name = identity.display_name
            else:
                display_name = "趣我圈 Web"
        except AppIdentityError as error:
            blockers.append(str(error))
        declaration = _distribution_classes().get(distribution_class)
        if not isinstance(declaration, dict):
            blockers.append(
                f"build product {build_product_id} references an unknown distribution class"
            )
            declaration = None
        if (
            identity is not None
            and build_profile == "prod"
            and distribution_class == "store"
            and not identity.registered
        ):
            blockers.append(
                f"APP.PACKAGE.prod_{platform}_identity_unregistered: production "
                f"{platform} application id must be registered before Release compilation"
            )

    promotable = bool(
        declaration
        and declaration.get("promotable")
        and build_mode == "release"
        and not blockers
    )
    decision: dict[str, Any] = {
        "schema": "app-artifact-build-decision",
        "buildProductId": build_product_id,
        "buildProfile": build_profile,
        "platform": platform,
        "buildMode": build_mode,
        "distributionClass": distribution_class,
        "artifactFormat": artifact_format,
        "applicationId": application_id,
        "displayName": display_name,
        "promotable": promotable,
        "blockers": blockers,
    }
    if blockers:
        return {
            "exitCode": 2,
            "summary": f"stackctl app build product blocked for {build_product_id or '<missing>'}",
            "details": blockers,
            "decision": decision,
        }

    import quwoquan_ops.cli.stackctl as _stackctl

    try:
        source_start = workspace_snapshot(deployment_roots=_CAPSULE_ROOTS)
        source_git_sha, source_tree_digest = _git_identity()
        display_version, build_number = _version()
        package_dir = _stackctl.deployment_target_path(
            _REPO_BUILD_TARGET,
            "packages",
            "app",
        )
        attempt_id = str(uuid.uuid4())
        attempt_dir = package_dir / build_product_artifact_segment(
            build_product_id=build_product_id,
            attempt_id=attempt_id,
        )
        attempt_dir.mkdir(parents=True, exist_ok=False)
        build = _build_from_capsule(
            build_product_id=build_product_id,
            build_profile=build_profile,
            platform=platform,
            build_mode=build_mode,
            artifact_format=artifact_format,
            application_id=application_id,
            attempt_dir=attempt_dir,
        )
        source_end = workspace_snapshot(deployment_roots=_CAPSULE_ROOTS)
        end_git_sha, end_tree_digest = _git_identity()
        if (
            source_start != source_end
            or source_git_sha != end_git_sha
            or source_tree_digest != end_tree_digest
            or build["sourceCapsuleDigest"]
            != source_start["deploymentInputDigest"]
            or build["sourceStatusDigest"]
            != source_start["workspaceStatusDigest"]
        ):
            raise AppArtifactBuildError(
                "WORKSPACE.CONCURRENT_WRITER: App source changed during package build"
            )
        if promotable and build["sourceStatusDigest"] != _EMPTY_STATUS_DIGEST:
            raise AppArtifactBuildError(
                "APP.PACKAGE.promotable_dirty_source: source capsule is not a clean checkout"
            )
        manifest = {
            "schema": "app-artifact-manifest",
            "buildProductId": build_product_id,
            "buildProfile": build_profile,
            "platform": platform,
            "buildMode": build_mode,
            "distributionClass": distribution_class,
            "artifactFormat": artifact_format,
            "applicationId": application_id,
            "displayVersion": display_version,
            "buildNumber": build_number,
            "signingIdentityDigest": build["signingIdentityDigest"],
            "sourceGitSha": source_git_sha,
            "sourceTreeDigest": source_tree_digest,
            "buildProvenanceDigest": _build_provenance_digest(
                build_product_id=build_product_id,
                source_git_sha=source_git_sha,
                source_tree_digest=source_tree_digest,
                source_capsule_digest=build["sourceCapsuleDigest"],
                artifact_digest=build["artifactDigest"],
                signing_identity_digest=build["signingIdentityDigest"],
            ),
            "artifactDigest": build["artifactDigest"],
            "promotable": promotable,
        }
        if platform in {"android", "ios"}:
            trust_digest = str(build.get("runtimeConfigTrustEnvelopeDigest") or "")
            if _DIGEST.fullmatch(trust_digest) is None:
                raise AppArtifactBuildError(
                    "APP.PACKAGE.runtime_config_trust_digest_invalid"
                )
            manifest["runtimeConfigTrustEnvelopeDigest"] = trust_digest
        if any(
            _DIGEST.fullmatch(str(manifest[field])) is None
            for field in (
                "signingIdentityDigest",
                "buildProvenanceDigest",
                "artifactDigest",
            )
        ):
            raise AppArtifactBuildError("APP.PACKAGE.manifest_digest_invalid")
        manifest_path = attempt_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        receipt = {
            "schema": "app-artifact-build-receipt",
            "attemptId": attempt_id,
            "buildProductId": build_product_id,
            "sourceCapsuleDigest": build["sourceCapsuleDigest"],
            "sourceStatusDigest": build["sourceStatusDigest"],
            "manifestPath": str(manifest_path),
            "artifactPath": build["artifactPath"],
        }
        (attempt_dir / "build-receipt.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, AppArtifactBuildError, subprocess.SubprocessError) as error:
        return {
            "exitCode": 2,
            "summary": f"stackctl app build product failed for {build_product_id}",
            "details": [str(error)],
            "decision": decision,
        }
    decision.update(manifest)
    return {
        "exitCode": 0,
        "summary": f"stackctl app build product compiled for {build_product_id}",
        "details": [
            f"artifact: {build['artifactPath']}",
            f"manifest: {manifest_path}",
            f"artifactDigest: {build['artifactDigest']}",
        ],
        "decision": decision,
        "manifest": manifest,
        "attemptDir": str(attempt_dir),
    }


def build_product_artifact_segment(
    *,
    build_product_id: str,
    attempt_id: str,
) -> str:
    """Keep immutable attempts partitioned only by canonical build product."""

    if build_product_id not in _BASELINE_BUILD_PRODUCT_IDS:
        raise ValueError("build product id is not in the canonical baseline")
    if not re.fullmatch(r"[0-9a-f-]{36}", attempt_id):
        raise ValueError("attempt id must be a UUID")
    return f"{build_product_id}/{attempt_id}"
