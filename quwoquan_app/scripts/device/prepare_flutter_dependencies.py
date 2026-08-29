"""Project one package-capsule dependency generation for a Flutter launch."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.app_dependency_toolchain import (
    AppDependencyToolchainError,
    resolve_cocoapods_executable,
)
from quwoquan_ops.cli.lib.dev_up import detect_device_kind, find_device
from quwoquan_ops.cli.lib.package_reuse import (
    materialize_dependency_bundle_projection,
    replay_ios_dependency_projections,
)
from quwoquan_ops.cli.lib.package_reuse.dependency_bundle_projection_verify import (
    load_dependency_projection_cas_readback,
    prepare_dependency_projection_cas_evidence,
    revalidate_dependency_projection_cas,
    write_dependency_projection_cas_readback,
)

_EXPORTED_KEYS = (
    "PUB_CACHE",
    "GRADLE_USER_HOME",
    "FLUTTER_SWIFT_PACKAGE_MANAGER",
    "CP_HOME_DIR",
    "CP_CACHE_DIR",
    "COCOAPODS_HOME",
    "HOME",
    "XDG_CONFIG_HOME",
    "XDG_CACHE_HOME",
    "COCOAPODS_DISABLE_STATS",
    "COCOAPODS_SKIP_UPDATE_MESSAGE",
    "GIT_CONFIG_GLOBAL",
    "GIT_CONFIG_NOSYSTEM",
    "GIT_TERMINAL_PROMPT",
)
_PROXY_KEYS = (
    "ALL_PROXY",
    "all_proxy",
    "HTTP_PROXY",
    "http_proxy",
    "HTTPS_PROXY",
    "https_proxy",
    "NO_PROXY",
    "no_proxy",
)
_DEPENDENCY_EVIDENCE_EXPORT_KEYS = (
    "QWQ_DEPENDENCY_PROJECTION_EXPECTATION_REF",
    "QWQ_DEPENDENCY_PROJECTION_EXPECTATION_DIGEST",
    "QWQ_DEPENDENCY_PROJECTION_PREBUILD_READBACK_REF",
    "QWQ_DEPENDENCY_PROJECTION_PREBUILD_READBACK_DIGEST",
)
_FORBIDDEN_IOS_SPM_TOKENS = (
    "FlutterGeneratedPluginSwiftPackage",
    "XCLocalSwiftPackageReference",
    "XCSwiftPackageProductDependency",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-capsule-manifest", required=True)
    parser.add_argument("--projection-root", required=True)
    parser.add_argument("--private-state-root", required=True)
    parser.add_argument("--device", required=True)
    parser.add_argument("--flutter", required=True)
    parser.add_argument("--pod", default="")
    parser.add_argument("--include-patrol", action="store_true")
    return parser


def _platform(device_id: str) -> str:
    device = find_device(device_id, include_desktop=False)
    if device is None:
        raise ValueError("APP.LAUNCH.device_unavailable: dependency target is absent")
    kind = detect_device_kind(
        device_id,
        target_platform=str(device.get("targetPlatform") or ""),
        emulator=bool(device.get("emulator", False)),
    )
    if kind.startswith("android"):
        return "android"
    if kind.startswith("ios"):
        return "ios"
    raise ValueError(
        "APP.LAUNCH.platform_unsupported: dependency target is unsupported"
    )


def _run_pub_get(
    *, flutter: str, package_root: Path, environment: Mapping[str, str]
) -> None:
    command = [
        flutter,
        "pub",
        "get",
        "--offline",
        "--enforce-lockfile",
        "--no-example",
    ]
    result = subprocess.run(
        command,
        cwd=package_root,
        env=dict(environment),
        check=False,
        capture_output=True,
        text=True,
        timeout=900,
    )
    if result.returncode != 0:
        detail = "\n".join((result.stdout + result.stderr).splitlines()[-20:])
        raise ValueError(
            "APP.DEPENDENCY.pub_offline_replay_failed"
            + (f": {detail}" if detail else "")
        )


def _run_projected_pub_gets(
    *,
    flutter: str,
    projection_root: Path,
    dependency_projection: object,
    include_patrol: bool,
) -> None:
    production_environment = getattr(
        dependency_projection,
        "production_environment",
        None,
    )
    if not isinstance(production_environment, Mapping):
        raise TypeError(
            "APP.DEPENDENCY.projection_failed: production environment is missing"
        )
    _run_pub_get(
        flutter=flutter,
        package_root=projection_root / "quwoquan_app",
        environment=production_environment,
    )
    if not include_patrol:
        return
    patrol_environment = getattr(dependency_projection, "patrol_environment", None)
    if not isinstance(patrol_environment, Mapping):
        raise TypeError(
            "APP.DEPENDENCY.projection_failed: patrol environment is missing"
        )
    _run_pub_get(
        flutter=flutter,
        package_root=projection_root / "quwoquan_app/test_host/patrol",
        environment=patrol_environment,
    )


def _shell_exports(
    environment: Mapping[str, str],
    *,
    dependency_evidence: Mapping[str, str] | None = None,
) -> str:
    lines = [f"unset {' '.join(_PROXY_KEYS)}"]
    for key in _EXPORTED_KEYS:
        value = str(environment.get(key) or "")
        if value:
            lines.append(f"export {key}={shlex.quote(value)}")
        else:
            lines.append(f"unset {key}")
    if dependency_evidence is not None:
        evidence = dependency_evidence
        if set(evidence) != set(_DEPENDENCY_EVIDENCE_EXPORT_KEYS):
            raise ValueError(
                "APP.DEPENDENCY.projection_expectation_invalid: export fields"
            )
        for key in _DEPENDENCY_EVIDENCE_EXPORT_KEYS:
            value = str(evidence.get(key) or "")
            if not value:
                raise ValueError(
                    f"APP.DEPENDENCY.projection_expectation_invalid: missing {key}"
                )
            lines.append(f"export {key}={shlex.quote(value)}")
    return "\n".join(lines)


def _assert_cocoapods_only_ios_project(projection_root: Path) -> None:
    project = projection_root / "quwoquan_app/ios/Runner.xcodeproj/project.pbxproj"
    if project.is_symlink() or not project.is_file():
        raise ValueError(
            "APP.DEPENDENCY.flutter_spm_residue_forbidden: "
            "production Runner project is unavailable"
        )
    source = project.read_text(encoding="utf-8")
    residue = next(
        (token for token in _FORBIDDEN_IOS_SPM_TOKENS if token in source), ""
    )
    if residue:
        raise ValueError(
            "APP.DEPENDENCY.flutter_spm_residue_forbidden: "
            f"production Runner still contains {residue}"
        )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        platform = _platform(args.device)
        pod: str | None = None
        if platform == "ios":
            pod = resolve_cocoapods_executable(args.pod)
        dependency_projection = materialize_dependency_bundle_projection(
            manifest_path=Path(args.source_capsule_manifest),
            projection_root=Path(args.projection_root),
            private_state_root=Path(args.private_state_root),
            platform=platform,
            base_environment=dict(os.environ),
            pod_executable=pod,
            include_patrol=args.include_patrol,
            replay_ios=False,
        )
        _run_projected_pub_gets(
            flutter=args.flutter,
            projection_root=Path(args.projection_root),
            dependency_projection=dependency_projection,
            include_patrol=args.include_patrol,
        )
        ios_install_results = None
        if platform == "ios":
            if pod is None:
                raise ValueError("APP.DEPENDENCY.cocoapods_missing")
            ios_install_results = replay_ios_dependency_projections(
                dependency_projection=dependency_projection,
                pod_executable=pod,
            )
            _assert_cocoapods_only_ios_project(Path(args.projection_root))
        private_state_root = Path(args.private_state_root).expanduser().absolute()
        expectation = prepare_dependency_projection_cas_evidence(
            projection_root=Path(args.projection_root),
            source_manifest_path=Path(args.source_capsule_manifest),
            dependency_projection=dependency_projection,
            evidence_path=private_state_root / "dependency-projection-expectation.json",
            ios_install_results=ios_install_results,
        )
        prebuild_readback = revalidate_dependency_projection_cas(
            projection_root=Path(args.projection_root),
            evidence_path=expectation.evidence_path,
            expected_digest=expectation.evidence_digest,
            command_environment_owner="production",
            command_environment=dependency_projection.production_environment,
        )
        prebuild_evidence = write_dependency_projection_cas_readback(
            readback=prebuild_readback,
            evidence_path=private_state_root
            / "dependency-projection-prebuild-readback.json",
        )
        load_dependency_projection_cas_readback(
            evidence_path=prebuild_evidence.evidence_path,
            expected_digest=prebuild_evidence.evidence_digest,
            expected_expectation_digest=expectation.evidence_digest,
        )
        print(
            _shell_exports(
                dependency_projection.production_environment,
                dependency_evidence={
                    "QWQ_DEPENDENCY_PROJECTION_EXPECTATION_REF": str(
                        expectation.evidence_path
                    ),
                    "QWQ_DEPENDENCY_PROJECTION_EXPECTATION_DIGEST": (
                        expectation.evidence_digest
                    ),
                    "QWQ_DEPENDENCY_PROJECTION_PREBUILD_READBACK_REF": str(
                        prebuild_evidence.evidence_path
                    ),
                    "QWQ_DEPENDENCY_PROJECTION_PREBUILD_READBACK_DIGEST": (
                        prebuild_evidence.evidence_digest
                    ),
                },
            )
        )
        return 0
    except (
        AppDependencyToolchainError,
        OSError,
        subprocess.SubprocessError,
        TypeError,
        ValueError,
    ) as error:
        detail = str(error) or type(error).__name__
        if not detail.startswith(("APP.DEPENDENCY", "APP.LAUNCH")):
            detail = f"APP.DEPENDENCY.projection_failed: {detail}"
        print(detail, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
