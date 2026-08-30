"""Canonical source-capsule App compiler and immutable artifact-manifest writer."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
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

from quwoquan_app.scripts.tools.flutter_facade.flutter_facade import (
    FacadeError,
    resolved_flutter_identity,
)
from quwoquan_ops.cli.commands.package_app_artifact_helpers import (
    artifact_digest,
    build_provenance_digest,
)
from quwoquan_ops.cli.commands.package_app_artifact_identity import (
    AppArtifactBuildError,
    artifact_filesystem_identity,
    read_android_identity,
    read_ios_identity,
    read_runtime_config_trust_envelope,
    signing_digest,
)
from quwoquan_ops.cli.commands.package_app_artifact_inputs import (
    make_writable as _make_writable,
)
from quwoquan_ops.cli.commands.package_app_artifact_inputs import (
    materialize_protected_inputs as _materialize_protected_inputs,
)
from quwoquan_ops.cli.commands.package_app_artifact_inputs import (
    materialize_runtime_config_inputs as _materialize_runtime_config_inputs,
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
from quwoquan_ops.cli.lib.app_source_capsule import app_source_capsule_roots
from quwoquan_ops.cli.lib.common import load_json_yaml
from quwoquan_ops.cli.lib.package_reuse import (
    dependency_bundle_projection_verify as _dependency_cas,
)
from quwoquan_ops.cli.lib.package_reuse import (
    materialize_dependency_bundle_projection,
    materialize_package_input_capsule,
    replay_ios_dependency_projections,
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
_CAPSULE_ROOTS = app_source_capsule_roots()
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_EMPTY_STATUS_DIGEST = (
    "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
)
# Existing direct tests inspect the producer's digest surface; keep that name as
# a projection of the one canonical helper rather than a second implementation.
_artifact_digest = artifact_digest


def _distribution_classes() -> dict[str, Any]:
    document = load_json_yaml(ARTIFACT_METADATA_PATH)
    classes = document.get("distribution_classes")
    if not isinstance(classes, dict) or not classes:
        raise AppIdentityError("distribution_classes metadata is missing")
    return classes


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


def _run(command: list[str], *, cwd: Path, env: dict[str, str], log_path: Path) -> Any:
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


def _run_build_with_dependency_cas(command: list[str], *, context: tuple[Any, ...]):
    root, source, projection, ios_results = context[:4]
    attempt_dir, cwd, environment, log_path = context[4:]
    expectation = _dependency_cas.prepare_dependency_projection_cas_evidence(
        projection_root=root,
        source_manifest_path=source,
        dependency_projection=projection,
        evidence_path=attempt_dir / "dependency-projection-expectation.json",
        ios_install_results=ios_results,
    )

    def readback(phase: str):
        observed = _dependency_cas.revalidate_dependency_projection_cas(
            projection_root=root,
            evidence_path=expectation.evidence_path,
            expected_digest=expectation.evidence_digest,
            command_environment_owner="production",
            command_environment=environment,
        )
        persisted = _dependency_cas.write_dependency_projection_cas_readback(
            readback=observed,
            evidence_path=attempt_dir / f"dependency-projection-{phase}-readback.json",
        )
        return _dependency_cas.load_dependency_projection_cas_readback(
            evidence_path=persisted.evidence_path,
            expected_digest=persisted.evidence_digest,
            expected_expectation_digest=expectation.evidence_digest,
        )

    prebuild = readback("prebuild")
    build_completed = False
    try:
        _run(
            command,
            cwd=cwd,
            env=environment,
            log_path=log_path,
        )
        build_completed = True
    finally:
        first_error = None if build_completed else sys.exception()
        try:
            postbuild = readback("postbuild")
        except (OSError, TypeError, ValueError) as error:
            if first_error is not None:
                raise AppArtifactBuildError(f"{first_error}; {error}") from first_error
            raise
    return {
        "dependencyProjectionExpectationRef": str(expectation.evidence_path),
        "dependencyProjectionExpectationDigest": expectation.evidence_digest,
        "dependencyProjectionPrebuildReadbackRef": str(prebuild.evidence_path),
        "dependencyProjectionPrebuildReadbackDigest": prebuild.evidence_digest,
        "dependencyProjectionPostbuildReadbackRef": str(postbuild.evidence_path),
        "dependencyProjectionPostbuildReadbackDigest": postbuild.evidence_digest,
    }


def _validate_persisted_dependency_evidence(
    *,
    attempt_dir: Path,
    deleted_projection_root: Path,
    evidence: dict[str, str],
) -> None:
    """Re-open package CAS evidence only after the build projection is gone."""

    expected_refs = {
        "dependencyProjectionExpectationRef": "dependency-projection-expectation.json",
        "dependencyProjectionPrebuildReadbackRef": (
            "dependency-projection-prebuild-readback.json"
        ),
        "dependencyProjectionPostbuildReadbackRef": (
            "dependency-projection-postbuild-readback.json"
        ),
    }
    expected_fields = {
        *expected_refs,
        "dependencyProjectionExpectationDigest",
        "dependencyProjectionPrebuildReadbackDigest",
        "dependencyProjectionPostbuildReadbackDigest",
    }
    if set(evidence) != expected_fields:
        raise AppArtifactBuildError(
            "APP.PACKAGE.dependency_evidence_invalid: persisted fields drifted"
        )
    if deleted_projection_root.exists() or deleted_projection_root.is_symlink():
        raise AppArtifactBuildError(
            "APP.PACKAGE.dependency_projection_cleanup_failed"
        )
    attempt_root = attempt_dir.expanduser().resolve(strict=True)
    paths: dict[str, Path] = {}
    for field, filename in expected_refs.items():
        raw = str(evidence.get(field) or "")
        path = Path(raw).expanduser()
        if (
            not path.is_absolute()
            or path.name != filename
            or path.parent.resolve(strict=True) != attempt_root
        ):
            raise AppArtifactBuildError(
                "APP.PACKAGE.dependency_evidence_invalid: "
                f"{field} is not attempt-scoped"
            )
        paths[field] = path
    expectation = (
        _dependency_cas.load_historical_dependency_projection_cas_evidence(
            evidence_path=paths["dependencyProjectionExpectationRef"],
            expected_digest=evidence["dependencyProjectionExpectationDigest"],
        )
    )
    prebuild = _dependency_cas.load_dependency_projection_cas_readback(
        evidence_path=paths["dependencyProjectionPrebuildReadbackRef"],
        expected_digest=evidence["dependencyProjectionPrebuildReadbackDigest"],
        expected_expectation_digest=expectation.evidence_digest,
    )
    postbuild = _dependency_cas.load_dependency_projection_cas_readback(
        evidence_path=paths["dependencyProjectionPostbuildReadbackRef"],
        expected_digest=evidence["dependencyProjectionPostbuildReadbackDigest"],
        expected_expectation_digest=expectation.evidence_digest,
    )
    expected_projection_root = deleted_projection_root.expanduser().absolute()
    if (
        expectation.projection_root != expected_projection_root
        or prebuild.manifest != postbuild.manifest
        or prebuild.manifest.get("projectionRoot") != str(expected_projection_root)
        or prebuild.manifest.get("sourceManifestDigest")
        != expectation.manifest["source"].get("manifestDigest")
    ):
        raise AppArtifactBuildError(
            "APP.PACKAGE.dependency_evidence_invalid: historical binding drifted"
        )


def _resolve_flutter_identity() -> dict[str, str]:
    try:
        return resolved_flutter_identity(dict(os.environ))
    except FacadeError as error:
        raise AppArtifactBuildError(
            f"APP.PACKAGE.flutter_identity_invalid: {error}"
        ) from error


def _copy_artifact(source: Path, destination: Path) -> Path:
    if destination.exists():
        raise AppArtifactBuildError(f"APP.PACKAGE.output_collision: {destination}")
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
    flutter_executable: str = "flutter",
) -> list[str]:
    return [
        flutter_executable,
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
    flutter_identity = _resolve_flutter_identity()
    flutter_executable = flutter_identity["executable"]
    capsule_root = attempt_dir / "input-capsule"
    capsule = materialize_package_input_capsule(
        _CAPSULE_ROOTS,
        capsule_root=capsule_root,
    )
    log_path = attempt_dir / "compile.log"
    temporary_workspace = tempfile.TemporaryDirectory(
        prefix=f"qwq-app-{build_product_id}-",
        dir=str(attempt_dir.parent),
    )
    try:
        raw_workspace = temporary_workspace.name
        workspace = Path(raw_workspace) / "repo"
        shutil.copytree(capsule_root / "repo", workspace, symlinks=True)
        _make_writable(workspace)
        app_dir = workspace / "quwoquan_app"
        command_env = dict(os.environ)
        for key in (
            "QWQ_APP_RUNTIME_ENV",
            "QWQ_LAUNCH_TARGET",
            "QWQ_APP_LAUNCH_PROVENANCE",
            "QWQ_RUNTIME_CONFIG_SUPPLY_MODE",
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
                "QWQ_REAL_FLUTTER": flutter_executable,
            }
        )
        pod: str | None = None
        pod_results: tuple[tuple[str, Any], ...] = ()
        if platform == "ios":
            try:
                pod = resolve_cocoapods_executable(
                    os.environ.get("QWQ_COCOAPODS_EXECUTABLE", "")
                )
            except AppDependencyToolchainError as error:
                raise AppArtifactBuildError(
                    f"APP.DEPENDENCY.cocoapods_mixed: {error}"
                ) from error
        dependencies = materialize_dependency_bundle_projection(
            manifest_path=capsule_root / "manifest.json",
            projection_root=workspace,
            private_state_root=Path(raw_workspace) / "dependencies",
            platform=platform,
            base_environment=command_env,
            pod_executable=pod,
            replay_ios=False,
        )
        command_env = dependencies.production_environment
        private_dir = Path(raw_workspace) / "protected"
        private_dir.mkdir(mode=0o700)
        runtime_config_trust_envelope_digest_value: str | None = None
        if platform in {"android", "ios"}:
            runtime_config_trust_envelope_digest_value = (
                _materialize_runtime_config_inputs(
                    app_dir=app_dir,
                    build_profile=build_profile,
                    platform=platform,
                    command_env=command_env,
                )
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
            [flutter_executable, "pub", "get", "--offline", "--enforce-lockfile"],
            cwd=app_dir,
            env=command_env,
            log_path=log_path,
        )
        if platform == "ios":
            if pod is None:
                raise AppArtifactBuildError("APP.DEPENDENCY.cocoapods_missing")
            pod_results = replay_ios_dependency_projections(
                dependency_projection=dependencies,
                pod_executable=pod,
            )
            with log_path.open("a", encoding="utf-8") as log:
                for host, result in pod_results:
                    log.write(f"$ [{host}] {' '.join(result.command)}\n")
                    log.write(result.stdout)
                    log.write(result.stderr)
                    log.write("\n[exitCode=0; network=denied]\n")
        dependency_cas = (
            workspace,
            capsule_root / "manifest.json",
            dependencies,
            pod_results,
        )
        dependency_cas += (attempt_dir, app_dir, command_env, log_path)
        mode_flag = f"--{build_mode}"
        entrypoint = "lib/main_prod.dart"
        if platform == "android":
            kind = "appbundle" if artifact_format == "aab" else "apk"
            dependency_evidence = _run_build_with_dependency_cas(
                [
                    flutter_executable,
                    "build",
                    kind,
                    mode_flag,
                    "--flavor",
                    build_profile,
                    "--target",
                    entrypoint,
                    "--no-pub",
                ],
                context=dependency_cas,
            )
            if kind == "appbundle":
                source_artifact = (
                    app_dir
                    / f"build/app/outputs/bundle/{build_profile}Release/app-{build_profile}-release.aab"
                )
                if not source_artifact.is_file():
                    source_artifact = (
                        app_dir / "build/app/outputs/bundle/release/app-release.aab"
                    )
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
                dependency_evidence = _run_build_with_dependency_cas(
                    [
                        flutter_executable,
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
                    context=dependency_cas,
                )
                ipa_files = sorted((app_dir / "build/ios/ipa").glob("*.ipa"))
                if len(ipa_files) != 1:
                    raise AppArtifactBuildError(
                        "APP.PACKAGE.artifact_missing: expected one IPA"
                    )
                artifact = _copy_artifact(ipa_files[0], attempt_dir / ipa_files[0].name)
            elif build_mode == "release":
                dependency_evidence = _run_build_with_dependency_cas(
                    _ios_unsigned_release_command(
                        build_profile=build_profile,
                        entrypoint=entrypoint,
                        flutter_executable=flutter_executable,
                    ),
                    context=dependency_cas,
                )
                artifact = _copy_artifact(
                    app_dir / "build/ios/iphoneos/Runner.app",
                    attempt_dir / f"{build_product_id}.app",
                )
            else:
                dependency_evidence = _run_build_with_dependency_cas(
                    [
                        flutter_executable,
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
                    context=dependency_cas,
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
            dependency_evidence = _run_build_with_dependency_cas(
                [
                    flutter_executable,
                    "build",
                    "web",
                    "--release",
                    "--pwa-strategy=offline-first",
                    f"--output={web_output}",
                    "--target",
                    entrypoint,
                    "--no-pub",
                ],
                context=dependency_cas,
            )
            required_web_outputs = (
                "index.html",
                "main.dart.js",
                "manifest.json",
                "flutter_service_worker.js",
            )
            missing_web_outputs = [
                name
                for name in required_web_outputs
                if not (web_output / name).is_file()
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
        artifact_identity_before = artifact_filesystem_identity(artifact)
        artifact_digest_before = artifact_digest(artifact)
        observed_signing_identity_digest = signing_digest(platform, artifact)
        observed_artifact_digest = artifact_digest(artifact)
        artifact_identity_after = artifact_filesystem_identity(artifact)
        if (
            artifact_identity_before != artifact_identity_after
            or artifact_digest_before != observed_artifact_digest
        ):
            raise AppArtifactBuildError(
                "APP.PACKAGE.artifact_snapshot_drift: "
                "artifact changed while build identity was observed"
            )
        build: dict[str, Any] = {
            "artifactPath": str(artifact),
            "artifactDigest": observed_artifact_digest,
            "artifactFilesystemIdentity": artifact_identity_after,
            "signingIdentityDigest": observed_signing_identity_digest,
            "sourceCapsuleDigest": str(capsule["deploymentInputDigest"]),
            "sourceStatusDigest": str(capsule["workspaceStatusDigest"]),
            "flutterVersion": flutter_identity["flutterVersion"],
            "commandResolutionDigest": flutter_identity["commandResolutionDigest"],
            "dependencyProjectionEvidence": dependency_evidence,
        }
        if runtime_config_trust_envelope_digest_value is not None:
            build["runtimeConfigTrustEnvelopeDigest"] = (
                runtime_config_trust_envelope_digest_value
            )
        temporary_workspace.cleanup()
        _validate_persisted_dependency_evidence(
            attempt_dir=attempt_dir,
            deleted_projection_root=workspace,
            evidence=dependency_evidence,
        )
        return build
    finally:
        temporary_workspace.cleanup()


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
            or build["sourceCapsuleDigest"] != source_start["deploymentInputDigest"]
            or build["sourceStatusDigest"] != source_start["workspaceStatusDigest"]
        ):
            raise AppArtifactBuildError(
                "WORKSPACE.CONCURRENT_WRITER: App source changed during package build"
            )
        if promotable and build["sourceStatusDigest"] != _EMPTY_STATUS_DIGEST:
            raise AppArtifactBuildError(
                "APP.PACKAGE.promotable_dirty_source: source capsule is not a clean checkout"
            )
        observed_artifact_digest = str(build["artifactDigest"])
        observed_signing_identity_digest = str(build["signingIdentityDigest"])
        observed_trust_digest = ""
        if platform in {"android", "ios"}:
            readback = read_runtime_config_trust_envelope(
                artifact_root=attempt_dir,
                artifact=Path(str(build.get("artifactPath") or "")),
                platform=platform,
                artifact_format=artifact_format,
                build_profile=build_profile,
                expected_build_input_digest=str(
                    build.get("runtimeConfigTrustEnvelopeDigest") or ""
                ),
                expected_artifact_digest=observed_artifact_digest,
                expected_artifact_filesystem_identity=build.get(
                    "artifactFilesystemIdentity"
                ),
                expected_signing_identity_digest=observed_signing_identity_digest,
            )
            observed_artifact_digest = readback.artifact_digest
            observed_signing_identity_digest = readback.signing_identity_digest
            observed_trust_digest = readback.runtime_config_trust_envelope_digest
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
            "signingIdentityDigest": observed_signing_identity_digest,
            "sourceGitSha": source_git_sha,
            "sourceTreeDigest": source_tree_digest,
            "buildProvenanceDigest": build_provenance_digest(
                build_product_id=build_product_id,
                source_git_sha=source_git_sha,
                source_tree_digest=source_tree_digest,
                source_capsule_digest=build["sourceCapsuleDigest"],
                artifact_digest=observed_artifact_digest,
                signing_identity_digest=observed_signing_identity_digest,
            ),
            "artifactDigest": observed_artifact_digest,
            "promotable": promotable,
        }
        if platform in {"android", "ios"}:
            if _DIGEST.fullmatch(observed_trust_digest) is None:
                raise AppArtifactBuildError(
                    "APP.PACKAGE.runtime_config_trust_digest_invalid"
                )
            manifest["runtimeConfigTrustEnvelopeDigest"] = observed_trust_digest
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
            "manifestDigest": artifact_digest(manifest_path),
            "artifactPath": build["artifactPath"],
            "artifactDigest": manifest["artifactDigest"],
            "buildProvenanceDigest": manifest["buildProvenanceDigest"],
            "flutterVersion": build["flutterVersion"],
            "commandResolutionDigest": build["commandResolutionDigest"],
            **build["dependencyProjectionEvidence"],
        }
        (attempt_dir / "build-receipt.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (
        OSError,
        TypeError,
        ValueError,
        AppArtifactBuildError,
        subprocess.SubprocessError,
    ) as error:
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
            f"artifactDigest: {manifest['artifactDigest']}",
        ],
        "decision": decision,
        "manifest": manifest,
        "attemptDir": str(attempt_dir),
        **build["dependencyProjectionEvidence"],
    }


def build_product_artifact_segment(*, build_product_id: str, attempt_id: str) -> str:
    if build_product_id not in _BASELINE_BUILD_PRODUCT_IDS:
        raise ValueError("build product id is not in the canonical baseline")
    if not re.fullmatch(r"[0-9a-f-]{36}", attempt_id):
        raise ValueError("attempt id must be a UUID")
    return f"{build_product_id}/{attempt_id}"
