"""Canonical four-environment App compiler and artifact manifest writer.

``stackctl package --kind app-artifact`` is the only production App build writer.
It freezes one read-only source capsule, builds from a private writable projection,
reads identity back from the result, scans production purity, and writes one
``app-artifact-manifest`` beside the immutable artifact.
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
    resolve_app_identity,
)
from quwoquan_ops.cli.lib.common import load_json_yaml
from quwoquan_ops.cli.lib.package_reuse import (
    materialize_package_input_capsule,
    workspace_snapshot,
)
from quwoquan_ops.cli.lib.web_official_release import (
    WebOfficialReleaseError,
    package_web_official_release,
)

_DEVICE_BOUND_CLASSES = frozenset({"registered_device"})
_PLATFORMS = frozenset({"android", "ios", "web"})


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


def _materialize_protected_inputs(
    *,
    app_dir: Path,
    environment: str,
    platform: str,
    build_mode: str,
    distribution_class: str,
    command_env: dict[str, str],
    private_dir: Path,
) -> None:
    if platform == "android" and build_mode == "release":
        firebase_key = f"QWQ_ANDROID_{environment.upper()}_GOOGLE_SERVICES_JSON"
        firebase_json = os.environ.get(firebase_key, "").strip()
        if not firebase_json:
            raise AppArtifactBuildError(
                f"APP.PACKAGE.protected_input_missing: {firebase_key}"
            )
        _write_private(
            app_dir / "android/app/google-services.json",
            firebase_json.encode("utf-8"),
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
    if platform == "ios" and distribution_class in {
        "registered_device",
        "store",
    }:
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


def _handoff(
    *,
    app_dir: Path,
    environment: str,
    target: str,
    command_env: dict[str, str],
    log_path: Path,
) -> dict[str, Any]:
    policy = "prod_release" if environment == "prod" else "test_live"
    result = _run(
        [
            sys.executable,
            "scripts/device/build_launcher_handoff.py",
            "--env",
            environment,
            "--target",
            target,
            "--launch-mode",
            "release_package",
            "--launch-policy",
            policy,
        ],
        cwd=app_dir,
        env=command_env,
        log_path=log_path,
    )
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise AppArtifactBuildError(
            "APP.PACKAGE.launch_handoff_invalid: builder output is not JSON"
        ) from error
    if not isinstance(value, dict):
        raise AppArtifactBuildError(
            "APP.PACKAGE.launch_handoff_invalid: handoff must be an object"
        )
    return value


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
    environment: str,
    entrypoint: str,
    defines: list[str],
) -> list[str]:
    return [
        "flutter",
        "build",
        "ios",
        "--release",
        "--no-codesign",
        "--flavor",
        environment,
        "--target",
        entrypoint,
        "--no-pub",
        *defines,
    ]


def _build_from_capsule(
    *,
    environment: str,
    target: str,
    platform: str,
    build_mode: str,
    distribution_class: str,
    application_id: str,
    attempt_dir: Path,
) -> dict[str, Any]:
    capsule_root = attempt_dir / "input-capsule"
    capsule = materialize_package_input_capsule(
        _CAPSULE_ROOTS,
        capsule_root=capsule_root,
    )
    log_path = attempt_dir / "compile.log"
    web_release: dict[str, object] | None = None
    with tempfile.TemporaryDirectory(
        prefix=f"qwq-app-{environment}-{platform}-",
        dir=str(attempt_dir.parent),
    ) as raw_workspace:
        workspace = Path(raw_workspace) / "repo"
        shutil.copytree(capsule_root / "repo", workspace, symlinks=True)
        _make_writable(workspace)
        app_dir = workspace / "quwoquan_app"
        command_env = dict(os.environ)
        command_env.update(
            {
                "PYTHONDONTWRITEBYTECODE": "1",
                "QWQ_APP_RUNTIME_ENV": environment,
                "QWQ_APP_BUILD_CONTEXT": "package-only",
                "QWQ_LAUNCH_TARGET": target,
            }
        )
        private_dir = Path(raw_workspace) / "protected"
        private_dir.mkdir(mode=0o700)
        _materialize_protected_inputs(
            app_dir=app_dir,
            environment=environment,
            platform=platform,
            build_mode=build_mode,
            distribution_class=distribution_class,
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
        handoff = _handoff(
            app_dir=app_dir,
            environment=environment,
            target=target,
            command_env=command_env,
            log_path=log_path,
        )
        (attempt_dir / "launcher-handoff.json").write_text(
            json.dumps(handoff, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        command_env.update(
            {
                "QWQ_DART_DEFINES_DIGEST": str(handoff["dartDefinesDigest"]),
                "QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST": str(
                    handoff["runtimeConfigDigest"]
                ),
                "QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST": str(
                    handoff["effectiveLaunchManifestDigest"]
                ),
                "QWQ_APP_RECOVERY_BASE_URL": str(handoff["recoveryBaseUrl"]),
                "QWQ_APP_PUBLIC_WEB_URL": str(handoff["publicWebBaseUrl"]),
                "QWQ_APP_DOWNLOAD_BASE_URL": str(handoff["appDownloadBaseUrl"]),
            }
        )
        defines = [
            f"--dart-define={key}={value}"
            for key, value in sorted(handoff["dartDefines"].items())
        ]
        mode_flag = f"--{build_mode}"
        entrypoint = str(handoff["entrypoint"])
        if platform == "android":
            kind = "appbundle" if distribution_class == "store" else "apk"
            _run(
                [
                    "flutter",
                    "build",
                    kind,
                    mode_flag,
                    "--flavor",
                    environment,
                    "--target",
                    entrypoint,
                    "--no-pub",
                    *defines,
                ],
                cwd=app_dir,
                env=command_env,
                log_path=log_path,
            )
            if kind == "appbundle":
                source_artifact = app_dir / "build/app/outputs/bundle/release/app-release.aab"
            else:
                source_artifact = (
                    app_dir
                    / f"build/app/outputs/flutter-apk/app-{environment}-{build_mode}.apk"
                )
                if not source_artifact.is_file():
                    source_artifact = (
                        app_dir / f"build/app/outputs/flutter-apk/app-{build_mode}.apk"
                    )
            artifact = _copy_artifact(
                source_artifact,
                attempt_dir / f"quwoquan-{environment}-{build_mode}{source_artifact.suffix}",
            )
            read_android_identity(artifact, application_id)
        elif platform == "ios":
            if distribution_class in {"registered_device", "store"}:
                export_options = command_env["QWQ_IOS_EXPORT_OPTIONS_PLIST"]
                _run(
                    [
                        "flutter",
                        "build",
                        "ipa",
                        mode_flag,
                        "--flavor",
                        environment,
                        "--target",
                        entrypoint,
                        "--no-pub",
                        "--export-options-plist",
                        export_options,
                        *defines,
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
                        environment=environment,
                        entrypoint=entrypoint,
                        defines=defines,
                    ),
                    cwd=app_dir,
                    env=command_env,
                    log_path=log_path,
                )
                artifact = _copy_artifact(
                    app_dir / "build/ios/iphoneos/Runner.app",
                    attempt_dir / f"quwoquan-{environment}-{build_mode}.app",
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
                        environment,
                        "--target",
                        entrypoint,
                        "--no-pub",
                        *defines,
                    ],
                    cwd=app_dir,
                    env=command_env,
                    log_path=log_path,
                )
                source_artifact = app_dir / "build/ios/iphonesimulator/Runner.app"
                artifact = _copy_artifact(
                    source_artifact,
                    attempt_dir / f"quwoquan-{environment}-{build_mode}.app",
                )
            if artifact.suffix == ".app":
                read_ios_identity(artifact, application_id)
        else:
            # Web 只有一个编译实现：package_web_official_release。它负责 PWA
            # 策略、构建校验、noindex 与内容寻址的 immutable release；这里只把
            # 冻结 capsule 交给它编译一次，再对同一 release 写 AppArtifactManifest。
            if build_mode != "release":
                raise AppArtifactBuildError(
                    "APP.PACKAGE.build_mode_invalid: hosted Web artifacts are "
                    f"release-only, got {build_mode}"
                )
            try:
                web_release = package_web_official_release(
                    repo_root=workspace,
                    environment=environment,
                    target=target,
                    package_root=attempt_dir / "web",
                    public_origin=str(handoff["publicWebBaseUrl"]),
                )
            except WebOfficialReleaseError as error:
                raise AppArtifactBuildError(
                    f"APP.PACKAGE.compile_failed: {error}"
                ) from error
            artifact = Path(str(web_release["releasePath"]))
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
            "launchManifestDigest": str(handoff["effectiveLaunchManifestDigest"]),
            "signingIdentityDigest": signing_digest(platform, artifact),
            "sourceCapsuleDigest": str(capsule["deploymentInputDigest"]),
            "sourceStatusDigest": str(capsule["workspaceStatusDigest"]),
        }
        if web_release is not None:
            # AppArtifactManifest 不接受额外字段，Web release 的 exact 身份落回执，
            # 让两条入口指向同一 immutable release 时可被逐项核对。
            build["webRelease"] = {
                "releaseId": str(web_release["releaseId"]),
                "contentSHA256": str(web_release["contentSHA256"]),
                "manifestSHA256": str(web_release["manifestSHA256"]),
                "manifestPath": str(web_release["manifestPath"]),
                "activePath": str(web_release["activePath"]),
                "publicOrigin": str(web_release["publicOrigin"]),
            }
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


def command_package_app_artifact(args: argparse.Namespace) -> dict[str, Any]:
    env_name = str(getattr(args, "env", "") or "").strip()
    target_name = str(getattr(args, "target", "") or "").strip()
    platform = str(getattr(args, "app_platform", "") or "").strip()
    build_mode = str(getattr(args, "app_build_mode", "") or "").strip()
    distribution_class = str(
        getattr(args, "distribution_class", "") or ""
    ).strip()
    device = str(getattr(args, "device", "") or "").strip()
    artifact_path = str(getattr(args, "artifact_path", "") or "").strip()

    blockers: list[str] = []
    if artifact_path:
        blockers.append(
            "--artifact-path bypass is forbidden; app-artifact always compiles its source capsule"
        )
    if platform not in _PLATFORMS:
        blockers.append("--app-platform must be android|ios|web")
    classes = _distribution_classes()
    declaration = classes.get(distribution_class)
    if not isinstance(declaration, dict):
        blockers.append(
            f"--distribution-class must be one of: {', '.join(sorted(classes))}"
        )
        declaration = None
    if declaration is not None:
        if platform not in (declaration.get("platforms") or []):
            blockers.append(
                f"platform={platform} is not allowed for distributionClass={distribution_class}"
            )
        platform_build_modes = declaration.get("platform_build_modes") or {}
        allowed_build_modes = (
            platform_build_modes.get(platform)
            if isinstance(platform_build_modes, dict)
            else None
        ) or declaration.get("build_modes") or []
        if build_mode not in allowed_build_modes:
            blockers.append(
                f"buildMode={build_mode} is not allowed for distributionClass={distribution_class}"
            )
    if platform == "ios" and distribution_class == "simulator" and build_mode != "debug":
        blockers.append(
            "APP.PACKAGE.ios_simulator_debug_only: Flutter iOS simulator does not support "
            "AOT profile/release builds"
        )
    expected_target = (
        f"{env_name}-local"
        if env_name in {"alpha", "beta", "gamma"}
        else "prod-sim"
        if distribution_class == "simulator"
        else "prod-hosted"
    )
    target_name = target_name or expected_target
    if target_name != expected_target:
        blockers.append(
            "target/distribution mismatch: "
            f"expected={expected_target} actual={target_name}"
        )
    if distribution_class in _DEVICE_BOUND_CLASSES and not device:
        blockers.append("--device is required for registered_device distribution")

    identity = None
    if platform in {"android", "ios"}:
        try:
            identity = resolve_app_identity(
                platform=platform,
                environment=env_name,
                build_mode=build_mode,
            )
        except AppIdentityError as error:
            blockers.append(str(error))
    if (
        identity is not None
        and platform == "ios"
        and env_name == "prod"
        and build_mode == "release"
        and not identity.registered
    ):
        blockers.append(
            "APP.PACKAGE.prod_ios_identity_unregistered: production iOS application id "
            "must be registered before Release compilation"
        )
    elif identity is not None and distribution_class == "store" and not identity.registered:
        blockers.append(
            f"{platform} store distribution requires a registered production application id"
        )
    application_id = identity.application_id if identity else f"web.{env_name}"
    promotable = bool(
        declaration
        and declaration.get("promotable")
        and build_mode == "release"
        and not blockers
    )
    decision: dict[str, Any] = {
        "schema": "app-artifact-build-decision",
        "environment": env_name,
        "target": target_name,
        "platform": platform,
        "buildMode": build_mode,
        "distributionClass": distribution_class,
        "device": device,
        "applicationId": application_id,
        "displayName": identity.display_name if identity else "趣我圈 Web",
        "promotable": promotable,
        "blockers": blockers,
    }
    if blockers:
        return {
            "exitCode": 2,
            "summary": (
                f"stackctl app artifact blocked for {env_name}/{platform}/"
                f"{build_mode}/{distribution_class}"
            ),
            "details": blockers,
            "decision": decision,
        }

    import quwoquan_ops.cli.stackctl as _stackctl

    try:
        source_start = workspace_snapshot(deployment_roots=_CAPSULE_ROOTS)
        source_git_sha, source_tree_digest = _git_identity()
        display_version, build_number = _version()
        package_dir = _stackctl.deployment_target_path(
            target_name,
            "packages",
            "app",
        )
        attempt_id = str(uuid.uuid4())
        attempt_dir = package_dir / environment_artifact_segment(
            environment=env_name,
            platform=platform,
            build_mode=build_mode,
            attempt_id=attempt_id,
        )
        attempt_dir.mkdir(parents=True, exist_ok=False)
        build = _build_from_capsule(
            environment=env_name,
            target=target_name,
            platform=platform,
            build_mode=build_mode,
            distribution_class=distribution_class,
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
            "environment": env_name,
            "platform": platform,
            "buildMode": build_mode,
            "distributionClass": distribution_class,
            "applicationId": application_id,
            "displayVersion": display_version,
            "buildNumber": build_number,
            "signingIdentityDigest": build["signingIdentityDigest"],
            "sourceGitSha": source_git_sha,
            "sourceTreeDigest": source_tree_digest,
            "artifactDigest": build["artifactDigest"],
            "launchManifestDigest": build["launchManifestDigest"],
            "promotable": promotable,
        }
        if any(
            _DIGEST.fullmatch(str(manifest[field])) is None
            for field in (
                "signingIdentityDigest",
                "artifactDigest",
                "launchManifestDigest",
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
            "target": target_name,
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
            "summary": f"stackctl app artifact build failed for {env_name}/{platform}",
            "details": [str(error)],
            "decision": decision,
        }
    decision.update(manifest)
    return {
        "exitCode": 0,
        "summary": (
            f"stackctl app artifact compiled for {env_name}/{platform}/"
            f"{build_mode}/{distribution_class}"
        ),
        "details": [
            f"artifact: {build['artifactPath']}",
            f"manifest: {manifest_path}",
            f"artifactDigest: {build['artifactDigest']}",
        ],
        "decision": decision,
        "manifest": manifest,
        "attemptDir": str(attempt_dir),
    }


def environment_artifact_segment(
    *,
    environment: str,
    platform: str,
    build_mode: str,
    attempt_id: str,
) -> str:
    """Keep four environments and platforms physically non-interchangeable."""

    if not re.fullmatch(r"[0-9a-f-]{36}", attempt_id):
        raise ValueError("attempt id must be a UUID")
    return f"{environment}/{platform}/{build_mode}/{attempt_id}"
