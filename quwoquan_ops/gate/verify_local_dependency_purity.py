#!/usr/bin/env python3
"""Block hidden build/runtime dependency fetches from supported local workflows."""

from __future__ import annotations

from pathlib import Path
import re
import sys

import yaml


ROOT = Path(__file__).resolve().parents[2]

GATE_REPO = ROOT / "quwoquan_ops/gate/gate_repo.sh"
RUN_SH = ROOT / "quwoquan_app/run.sh"
FLUTTER_TEST_GUARD = ROOT / "quwoquan_app/scripts/env/run_flutter_test_guarded.py"
PUBSPEC = ROOT / "quwoquan_app/pubspec.yaml"
PODFILE_LOCK = ROOT / "quwoquan_app/ios/Podfile.lock"
PODS_MANIFEST_LOCK = ROOT / "quwoquan_app/ios/Pods/Manifest.lock"
PODS_DIR = ROOT / "quwoquan_app/ios/Pods"
ANDROID_ARTIFACTS_DIR = ROOT / "quwoquan_app/vendor/android_artifacts"
FLUTTER_WEBRTC_ANDROID = ROOT / "quwoquan_app/vendor/plugins/flutter_webrtc/android/build.gradle"
LIVEKIT_ANDROID = ROOT / "quwoquan_app/vendor/plugins/livekit_client/android/build.gradle"
APP_ANDROID_BUILD = ROOT / "quwoquan_app/android/app/build.gradle.kts"
FLUTTER_WEBRTC_CMAKE = ROOT / "quwoquan_app/vendor/plugins/flutter_webrtc/third_party/CMakeLists.txt"
LIVEKIT_LINUX_CMAKE = ROOT / "quwoquan_app/vendor/plugins/livekit_client/linux/CMakeLists.txt"
PACKAGE_SWIFT_GLOB = "quwoquan_app/vendor/plugins/**/Package.swift"

REQUIRED_ANDROID_ARTIFACTS = (
    "android-144.7559.01.aar",
    "audioswitch-89582c47c9a04c62f90aa5e57251af4800a62c9a.aar",
    "noise-2.0.0.aar",
)

DISALLOWED_VENDOR_PATTERNS = {
    re.compile(r"file\s*\(\s*DOWNLOAD", re.IGNORECASE): "CMake file(DOWNLOAD)",
    re.compile(r"FetchContent_Declare", re.IGNORECASE): "CMake FetchContent_Declare",
    re.compile(r"https://jitpack\.io", re.IGNORECASE): "JitPack repository",
    re.compile(r"io\.github\.webrtc-sdk:android:144\.7559\.01"): "remote webrtc-sdk Maven coordinate",
    re.compile(r"com\.github\.davidliu:audioswitch:89582c47c9a04c62f90aa5e57251af4800a62c9a"): "remote audioswitch Maven coordinate",
    re.compile(r"io\.livekit:noise:2\.0\.0"): "remote livekit-noise Maven coordinate",
}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _fail(failures: list[str], message: str) -> None:
    failures.append(message)


def _check_contains(
    failures: list[str],
    *,
    path: Path,
    needle: str,
    description: str,
) -> None:
    text = _read_text(path)
    if needle not in text:
        _fail(failures, f"{path.relative_to(ROOT)} must contain {description}: {needle}")


def _check_not_contains(
    failures: list[str],
    *,
    path: Path,
    needle: str,
    description: str,
) -> None:
    text = _read_text(path)
    if needle in text:
        _fail(failures, f"{path.relative_to(ROOT)} must not contain {description}: {needle}")


def _verify_scripts(failures: list[str]) -> None:
    _check_contains(
        failures,
        path=GATE_REPO,
        needle="flutter pub get --offline",
        description="offline Flutter package resolution",
    )
    _check_not_contains(
        failures,
        path=GATE_REPO,
        needle="npm install",
        description="implicit Node dependency installation",
    )
    _check_contains(
        failures,
        path=RUN_SH,
        needle="flutter pub get --offline",
        description="offline Flutter package resolution",
    )
    _check_contains(
        failures,
        path=RUN_SH,
        needle="--no-pub",
        description="flutter run no-pub guard",
    )
    _check_contains(
        failures,
        path=RUN_SH,
        needle="cmp -s \"$PODFILE_LOCK\" \"$PODS_MANIFEST_LOCK\"",
        description="CocoaPods lock drift guard",
    )
    _check_contains(
        failures,
        path=FLUTTER_TEST_GUARD,
        needle='["flutter", "pub", "get", "--offline"]',
        description="offline Flutter test bootstrap",
    )


def _verify_pubspec(failures: list[str]) -> None:
    data = yaml.safe_load(PUBSPEC.read_text(encoding="utf-8"))
    sqlite_source = (
        data.get("hooks", {})
        .get("user_defines", {})
        .get("sqlite3", {})
        .get("source")
    )
    if sqlite_source != "system":
        _fail(
            failures,
            f"{PUBSPEC.relative_to(ROOT)} hooks.user_defines.sqlite3.source must be 'system', got {sqlite_source!r}",
        )

    swiftpm_enabled = (
        data.get("flutter", {})
        .get("config", {})
        .get("enable-swift-package-manager")
    )
    if swiftpm_enabled is not False:
        _fail(
            failures,
            f"{PUBSPEC.relative_to(ROOT)} must keep enable-swift-package-manager=false until all vendored Package.swift dependencies are localized",
        )

    package_swift_paths = sorted(ROOT.glob(PACKAGE_SWIFT_GLOB))
    remote_swiftpm_packages = []
    for path in package_swift_paths:
        text = _read_text(path)
        if ".package(url:" in text:
            remote_swiftpm_packages.append(path.relative_to(ROOT).as_posix())
    if not remote_swiftpm_packages:
        _fail(
            failures,
            "Expected vendored Package.swift files with remote upstream declarations were not found; update verify_local_dependency_purity.py to match the new SwiftPM topology",
        )


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _verify_ios_pods(
    failures: list[str],
    *,
    podfile_lock: Path = PODFILE_LOCK,
    pods_manifest_lock: Path = PODS_MANIFEST_LOCK,
    pods_dir: Path = PODS_DIR,
) -> None:
    if not podfile_lock.exists():
        _fail(failures, f"Missing {_display_path(podfile_lock)}")
        return

    # Podfile.lock is source truth. Pods/ is a local generated projection and is
    # intentionally absent from a clean checkout; validate it only when present.
    if not pods_dir.exists():
        return
    if not pods_manifest_lock.exists():
        _fail(failures, f"Missing {_display_path(pods_manifest_lock)}")
        return
    if podfile_lock.read_text(encoding="utf-8") != pods_manifest_lock.read_text(encoding="utf-8"):
        _fail(
            failures,
            "quwoquan_app/ios/Pods/Manifest.lock must match quwoquan_app/ios/Podfile.lock so local iOS builds never need implicit pod graph repair",
        )
    lock_data = yaml.safe_load(podfile_lock.read_text(encoding="utf-8"))
    trunk_pods = lock_data.get("SPEC REPOS", {}).get("trunk", [])
    for pod_name in trunk_pods:
        pod_dir = pods_dir / pod_name
        if not pod_dir.exists():
            _fail(
                failures,
                f"Missing vendored CocoaPod directory for trunk pod {pod_name!r}: {_display_path(pod_dir)}",
            )


def _verify_android_vendoring(failures: list[str]) -> None:
    for name in REQUIRED_ANDROID_ARTIFACTS:
        artifact = ANDROID_ARTIFACTS_DIR / name
        if not artifact.exists():
            _fail(
                failures,
                f"Missing vendored Android artifact {artifact.relative_to(ROOT)}",
            )

    _check_contains(
        failures,
        path=FLUTTER_WEBRTC_ANDROID,
        needle="vendoredAndroidArtifact('android-144.7559.01.aar')",
        description="vendored WebRTC AAR reference",
    )
    _check_contains(
        failures,
        path=FLUTTER_WEBRTC_ANDROID,
        needle="vendoredAndroidArtifact('audioswitch-89582c47c9a04c62f90aa5e57251af4800a62c9a.aar')",
        description="vendored audioswitch AAR reference",
    )
    _check_contains(
        failures,
        path=LIVEKIT_ANDROID,
        needle='vendoredAndroidArtifact("android-144.7559.01.aar")',
        description="vendored WebRTC AAR reference",
    )
    _check_contains(
        failures,
        path=LIVEKIT_ANDROID,
        needle='vendoredAndroidArtifact("noise-2.0.0.aar")',
        description="vendored livekit-noise AAR reference",
    )
    _check_contains(
        failures,
        path=FLUTTER_WEBRTC_ANDROID,
        needle="compileOnly files(vendoredAndroidArtifact('android-144.7559.01.aar'))",
        description="AGP8-safe compileOnly WebRTC AAR reference",
    )
    _check_contains(
        failures,
        path=LIVEKIT_ANDROID,
        needle='compileOnly files(vendoredAndroidArtifact("android-144.7559.01.aar"))',
        description="AGP8-safe compileOnly WebRTC AAR reference",
    )
    _check_not_contains(
        failures,
        path=FLUTTER_WEBRTC_ANDROID,
        needle="implementation files(vendoredAndroidArtifact('android-144.7559.01.aar'))",
        description="AGP8-unsafe implementation WebRTC AAR reference",
    )
    for artifact in REQUIRED_ANDROID_ARTIFACTS:
        _check_contains(
            failures,
            path=APP_ANDROID_BUILD,
            needle=f'"{artifact}"',
            description="app-level vendored AAR bundle reference",
        )


def _verify_vendor_build_files(failures: list[str]) -> None:
    manifest_paths = [
        path
        for path in ROOT.glob("quwoquan_app/vendor/plugins/**/CMakeLists.txt")
        if "/example/" not in path.as_posix()
    ]
    manifest_paths.extend(
        path
        for path in ROOT.glob("quwoquan_app/vendor/plugins/**/build.gradle")
        if "/example/" not in path.as_posix()
    )
    manifest_paths.extend(
        path
        for path in ROOT.glob("quwoquan_app/vendor/plugins/**/build.gradle.kts")
        if "/example/" not in path.as_posix()
    )
    for path in sorted(set(manifest_paths)):
        text = _read_text(path)
        for pattern, description in DISALLOWED_VENDOR_PATTERNS.items():
            if pattern.search(text):
                _fail(
                    failures,
                    f"{path.relative_to(ROOT)} still contains disallowed {description}",
                )

    _check_contains(
        failures,
        path=FLUTTER_WEBRTC_CMAKE,
        needle="Missing vendored libwebrtc archive",
        description="desktop WebRTC fail-closed message",
    )
    _check_contains(
        failures,
        path=LIVEKIT_LINUX_CMAKE,
        needle="Missing vendored googletest",
        description="Linux plugin test fail-closed message",
    )


def main() -> int:
    failures: list[str] = []
    _verify_scripts(failures)
    _verify_pubspec(failures)
    _verify_ios_pods(failures)
    _verify_android_vendoring(failures)
    _verify_vendor_build_files(failures)

    if failures:
        print("[dependency-purity] FAIL")
        for failure in failures:
            print(f" - {failure}")
        return 1

    print("[dependency-purity] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
