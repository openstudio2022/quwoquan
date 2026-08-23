#!/usr/bin/env python3
"""Block hidden build/runtime fetches and App dependency-lock drift.

Trigger: App pub/plugin/Pod locks, CocoaPods invocation, launcher or CI builds.
Block: cross-lock mismatch, mixed CocoaPods executable/runtime, or implicit fetch.
Repair: perform one explicit dependency transaction, commit its locks, then consume
them with offline/enforce-lockfile and ``pod install --deployment`` only.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.app_dependency_toolchain import (
    AppDependencyToolchainError,
    resolve_cocoapods_executable,
)

GATE_REPO = ROOT / "quwoquan_ops/gate/gate_repo.sh"
RUN_SH = ROOT / "quwoquan_app/run.sh"
FLUTTER_TEST_GUARD = ROOT / "quwoquan_app/scripts/env/run_flutter_test_guarded.py"
PUBSPEC = ROOT / "quwoquan_app/pubspec.yaml"
PUBSPEC_LOCK = ROOT / "quwoquan_app/pubspec.lock"
PODFILE_LOCK = ROOT / "quwoquan_app/ios/Podfile.lock"
PODS_MANIFEST_LOCK = ROOT / "quwoquan_app/ios/Pods/Manifest.lock"
PODS_DIR = ROOT / "quwoquan_app/ios/Pods"
IOS_PLUGIN_ROOT = ROOT / "quwoquan_app/ios/.symlinks/plugins"
ANDROID_ARTIFACTS_DIR = ROOT / "quwoquan_app/vendor/android_artifacts"
FLUTTER_WEBRTC_ANDROID = ROOT / "quwoquan_app/vendor/plugins/flutter_webrtc/android/build.gradle"
LIVEKIT_ANDROID = ROOT / "quwoquan_app/vendor/plugins/livekit_client/android/build.gradle"
APP_ANDROID_BUILD = ROOT / "quwoquan_app/android/app/build.gradle.kts"
FLUTTER_WEBRTC_CMAKE = ROOT / "quwoquan_app/vendor/plugins/flutter_webrtc/third_party/CMakeLists.txt"
LIVEKIT_LINUX_CMAKE = ROOT / "quwoquan_app/vendor/plugins/livekit_client/linux/CMakeLists.txt"
PACKAGE_SWIFT_GLOB = "quwoquan_app/vendor/plugins/**/Package.swift"

PRODUCTION_TEST_MARKERS = (
    "patrol",
    "integration_test",
    "PatrolJUnitRunner",
    "RunnerUITests",
)

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
        needle='["flutter", "pub", "get", "--offline", "--enforce-lockfile"]',
        description="locked offline Flutter test bootstrap",
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


def _pod_version(lock_data: dict[object, object], pod_name: str) -> str:
    prefix = f"{pod_name} ("
    for declaration in lock_data.get("PODS", []):
        value = next(iter(declaration), "") if isinstance(declaration, dict) else declaration
        text = str(value)
        if text.startswith(prefix) and text.endswith(")"):
            return text[len(prefix) : -1]
    return ""


def _verify_ios_cross_lock(
    failures: list[str],
    *,
    pubspec_lock: Path = PUBSPEC_LOCK,
    podfile_lock: Path = PODFILE_LOCK,
    pods_manifest_lock: Path = PODS_MANIFEST_LOCK,
    plugin_root: Path = IOS_PLUGIN_ROOT,
) -> None:
    missing = [path for path in (pubspec_lock, podfile_lock) if not path.is_file()]
    if missing:
        for path in missing:
            _fail(failures, f"APP.DEPENDENCY.lock_drift: missing {_display_path(path)}")
        return
    pub_lock = yaml.safe_load(pubspec_lock.read_text(encoding="utf-8")) or {}
    pod_lock = yaml.safe_load(podfile_lock.read_text(encoding="utf-8")) or {}
    packages = pub_lock.get("packages") or {}
    # pubspec.lock 与 Podfile.lock 都受版本控制，两者的一致性在任何 checkout 上都可
    # 判定，始终强制。ios/.symlinks/plugins 是 pub get 生成且 gitignore 的：它证明
    # 磁盘上真正被链接的插件版本，只在已 bootstrap 的环境里存在，因此作为「存在即
    # 校验」的第三证人。否则这条判据在干净 Linux checkout 上结构上无法通过，只能靠
    # 整条跳过来收场，那等于把它变成空转。
    plugin_tree_present = plugin_root.is_dir()
    for plugin in ("firebase_core", "firebase_messaging"):
        declared = str((packages.get(plugin) or {}).get("version") or "").strip()
        locked_pod = _pod_version(pod_lock, plugin)
        projected_pubspec = plugin_root / plugin / "pubspec.yaml"
        projected = ""
        if projected_pubspec.is_file():
            projected = str(
                (yaml.safe_load(projected_pubspec.read_text(encoding="utf-8")) or {}).get(
                    "version", ""
                )
            ).strip()
        drifted = not declared or declared != locked_pod
        if plugin_tree_present and declared != projected:
            drifted = True
        if drifted:
            _fail(
                failures,
                "APP.DEPENDENCY.lock_drift: "
                f"{plugin} pub={declared or '<missing>'} "
                f"plugin={projected or '<not-materialized>'} "
                f"pod={locked_pod or '<missing>'}",
            )

    firebase_version_file = plugin_root / "firebase_core/ios/firebase_sdk_version.rb"
    expected_firebase = ""
    if firebase_version_file.is_file():
        match = re.search(
            r"firebase_sdk_version!\(\).*?['\"]([^'\"]+)['\"]",
            firebase_version_file.read_text(encoding="utf-8"),
            re.DOTALL,
        )
        expected_firebase = match.group(1) if match else ""
    # 期望值只写在被链接插件里，没有受版本控制的副本；树不在时改判 Podfile.lock 内部
    # 自洽（两个 Firebase pod 必须同版本且非空），这部分同样在任何 checkout 上可判定。
    firebase_pods = {
        pod_name: _pod_version(pod_lock, pod_name)
        for pod_name in ("Firebase/CoreOnly", "Firebase/Messaging")
    }
    for pod_name, actual in firebase_pods.items():
        if not actual or (expected_firebase and actual != expected_firebase):
            _fail(
                failures,
                "APP.DEPENDENCY.lock_drift: "
                f"{pod_name} plugin={expected_firebase or '<not-materialized>'} "
                f"pod={actual or '<missing>'}",
            )
    if len(set(firebase_pods.values())) > 1:
        _fail(
            failures,
            "APP.DEPENDENCY.lock_drift: Firebase pods disagree: "
            + ", ".join(
                f"{name}={version or '<missing>'}" for name, version in firebase_pods.items()
            ),
        )
    if pods_manifest_lock.exists() and (
        podfile_lock.read_bytes() != pods_manifest_lock.read_bytes()
    ):
        _fail(
            failures,
            "APP.DEPENDENCY.lock_drift: Pods/Manifest.lock differs from Podfile.lock",
        )


def _verify_cocoapods_toolchain(
    failures: list[str],
    *,
    pod_executable: str = "",
) -> None:
    # 这条判据禁的是 wrapper 与 runtime 版本漂移，而「机器上没装 CocoaPods」不构成漂移。
    # CocoaPods 只存在于 macOS，Linux 上不可能有 pod，缺席即判失败会让判据在那里结构上
    # 无法通过。处理方式与同文件的 Pods/ 一致：缺席不校验，存在才校验。调用方显式声明了
    # 路径就必须成立——那是承诺有 CocoaPods，声明却不可用仍然是漂移。
    if not pod_executable.strip() and not shutil.which("pod"):
        return
    try:
        resolve_cocoapods_executable(pod_executable)
    except AppDependencyToolchainError as error:
        _fail(
            failures,
            f"APP.DEPENDENCY.cocoapods_mixed: {error}",
        )


def _verify_production_test_dependency_purity(
    failures: list[str],
    *,
    app_dir: Path = ROOT / "quwoquan_app",
) -> None:
    """Keep native test runners in the isolated host and enumerate every UAT."""

    def leak(path: Path, marker: str) -> None:
        _fail(
            failures,
            "APP.PACKAGE.production_test_dependency_leak: "
            f"{_display_path(path)} contains {marker}",
        )

    production_pubspec = app_dir / "pubspec.yaml"
    if not production_pubspec.is_file():
        leak(production_pubspec, "missing production pubspec")
        return
    decoded = yaml.safe_load(production_pubspec.read_text(encoding="utf-8")) or {}
    for section in ("dependencies", "dev_dependencies", "dependency_overrides"):
        entries = decoded.get(section) or {}
        for dependency in ("patrol", "integration_test"):
            if dependency in entries:
                leak(production_pubspec, f"{section}.{dependency}")

    # 插件图同样是 pub get 生成且 gitignore 的。上面的 pubspec 判据已在受版本控制的
    # 面上禁掉 patrol/integration_test，插件图是「磁盘上真的没链进去」的第二证人：
    # 存在即校验，缺席不放水成通过——否则这条判据在干净 checkout 上无法成立，只能
    # 靠整条跳过收场。
    plugin_graph = app_dir / ".flutter-plugins-dependencies"
    if plugin_graph.is_file():
        try:
            graph = json.loads(plugin_graph.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            leak(plugin_graph, "invalid generated plugin graph")
        else:
            plugin_names = {
                str(plugin.get("name") or "")
                for plugins in (graph.get("plugins") or {}).values()
                for plugin in plugins
                if isinstance(plugin, dict)
            }
            for dependency in ("patrol", "integration_test"):
                if dependency in plugin_names:
                    leak(plugin_graph, dependency)

    source_paths = (
        app_dir / "ios/Podfile",
        app_dir / "ios/Podfile.lock",
        app_dir / "ios/Runner.xcodeproj/project.pbxproj",
        app_dir / "ios/Runner/GeneratedPluginRegistrant.m",
        app_dir / "android/app/build.gradle.kts",
        app_dir
        / "android/app/src/main/java/com/quwoquan/quwoquan_app/StartupEagerPluginRegistry.java",
    )
    source_paths += tuple(sorted((app_dir / "ios/Flutter").glob("*.xcconfig")))
    if (app_dir / "ios/Pods/Manifest.lock").is_file():
        source_paths += (app_dir / "ios/Pods/Manifest.lock",)
    for path in source_paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in PRODUCTION_TEST_MARKERS:
            if marker in text:
                leak(path, marker)

    host_dir = app_dir / "test_host/patrol"
    host_pubspec = host_dir / "pubspec.yaml"
    host_graph = host_dir / ".flutter-plugins-dependencies"
    for path, markers in (
        (host_pubspec, ("patrol:", "integration_test:")),
        (
            host_dir / "android/app/build.gradle.kts",
            ("pl.leancode.patrol.PatrolJUnitRunner",),
        ),
        (
            host_dir / "ios/RunnerUITests/RunnerUITests.m",
            ("PATROL_INTEGRATION_TEST_IOS_RUNNER",),
        ),
    ):
        if not path.is_file():
            leak(path, "missing isolated Patrol host owner")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in markers:
            if marker not in text:
                leak(path, f"missing isolated host marker {marker}")
    # host 的 pubspec / gradle / RunnerUITests 判据都在受版本控制的面上且始终强制；
    # 插件图只在已 bootstrap 的环境里补证「patrol 确实链在隔离宿主里」。
    if host_graph.is_file():
        graph_text = host_graph.read_text(encoding="utf-8", errors="replace")
        for marker in ('"name":"patrol"', '"name":"integration_test"'):
            if marker not in graph_text:
                leak(host_graph, f"missing {marker}")

    canonical_uat_root = app_dir / "test/user_acceptance"
    canonical_uats = tuple(sorted(canonical_uat_root.rglob("*_test.dart")))
    if not canonical_uats:
        leak(canonical_uat_root, "no canonical UAT discovered")
    canonical_targets = tuple(
        path.relative_to(app_dir).as_posix() for path in canonical_uats
    )
    wrapper_targets = tuple(
        "test/patrol/qwq_environment_smoke_"
        + hashlib.sha256(target.encode("utf-8")).hexdigest()[:16]
        + "_test.dart"
        for target in canonical_targets
    )
    if len(set(wrapper_targets)) != len(canonical_targets):
        leak(canonical_uat_root, "canonical UAT wrapper target collision")
    copied_uats = tuple(sorted((host_dir / "test").rglob("*_user_acceptance_test.dart")))
    for copied in copied_uats:
        leak(copied, "canonical UAT copy in test host")
    wrapper_source = (
        ROOT
        / "quwoquan_ops/cli/smoke/environment_patrol_smoke/wrapper.py"
    )
    if app_dir != ROOT / "quwoquan_app":
        wrapper_source = app_dir / "test_host_wrapper.py"
    if not wrapper_source.is_file():
        leak(wrapper_source, "missing canonical UAT wrapper")
    else:
        wrapper_text = wrapper_source.read_text(encoding="utf-8")
        for marker in (
            'root_parts = ("test", "user_acceptance")',
            "APP_DIR / normalized",
            "PATROL_HOST_DIR / PATROL_TEST_DIRECTORY",
            "def _canonical_patrol_uat_targets()",
            'canonical_root.rglob("*_test.dart")',
        ):
            if marker not in wrapper_text:
                leak(wrapper_source, f"coverage enumeration missing {marker}")


def _verify_uat_static_analysis_coverage(
    failures: list[str],
    *,
    app_dir: Path = ROOT / "quwoquan_app",
    gate_script: Path = ROOT / "quwoquan_ops/gate/gate_repo.sh",
) -> None:
    """Prove the main-App exclusion never silently drops a canonical UAT.

    生产 pubspec 不含 patrol，因此 canonical UAT 与 Patrol support 只能在
    test host 的 package context 下静态分析。主 App 的排除因此必须与 test host
    的分析集合严格互补：每一个 canonical UAT 都要经 test/canonical symlink
    落进 test host 的分析根，否则排除就是假绿。
    """

    def uncovered(path: Path, reason: str) -> None:
        _fail(
            failures,
            "APP.PACKAGE.uat_static_analysis_uncovered: "
            f"{_display_path(path)} {reason}",
        )

    canonical_uat_root = app_dir / "test/user_acceptance"
    patrol_support_root = app_dir / "test/support/runtime/patrol"
    host_dir = app_dir / "test_host/patrol"
    canonical_link = host_dir / "test/canonical"

    production_options = app_dir / "analysis_options.yaml"
    if not production_options.is_file():
        uncovered(production_options, "is missing")
        return
    production_excludes = (
        (yaml.safe_load(production_options.read_text(encoding="utf-8")) or {})
        .get("analyzer", {})
        .get("exclude")
        or []
    )
    for required_exclude in (
        "test/user_acceptance/**",
        "test/support/runtime/patrol/**",
    ):
        if required_exclude not in production_excludes:
            uncovered(
                production_options,
                f"must exclude {required_exclude} from the main-App analysis",
            )
    excluded_test_prefixes = tuple(
        sorted(
            {
                _excluded_test_prefix(str(pattern))
                for pattern in production_excludes
                if str(pattern).startswith("test/")
            }
        )
    )

    # canonical UAT 只允许被 symlink 引用；复制会立刻产生第二个真相源。
    if not canonical_link.is_symlink():
        uncovered(canonical_link, "must be a symlink to the main App test tree")
        return
    if canonical_link.resolve() != (app_dir / "test").resolve():
        uncovered(canonical_link, "must resolve to the main App test tree")
        return

    host_options = host_dir / "analysis_options.yaml"
    if host_options.is_file():
        host_excludes = (
            (yaml.safe_load(host_options.read_text(encoding="utf-8")) or {})
            .get("analyzer", {})
            .get("exclude")
            or []
        )
        for host_exclude in host_excludes:
            if str(host_exclude).startswith("test/canonical"):
                uncovered(host_options, f"must not exclude {host_exclude}")

    if not gate_script.is_file():
        uncovered(gate_script, "is missing")
        return
    # 覆盖面只能从 test host 真实的 analyze 参数表派生：全文 substring 匹配会让
    # 一行注释就满足判据。
    analyzed_prefixes = _test_host_analysis_prefixes(
        gate_script.read_text(encoding="utf-8")
    )
    for analysis_root in ("user_acceptance", "support/runtime/patrol"):
        if not _prefix_is_analyzed(analysis_root, analyzed_prefixes):
            uncovered(
                gate_script,
                f"must analyze test/canonical/{analysis_root} in the test host",
            )

    # 主 App 每一条 test/** 排除都必须有等价证人。硬编码白名单挡不住第三条新增
    # 排除，集合互补才挡得住。
    for prefix in excluded_test_prefixes:
        if not _prefix_is_analyzed(prefix, analyzed_prefixes):
            uncovered(
                production_options,
                f"excludes test/{prefix}/** from the main-App analysis with no "
                "matching test host analysis root",
            )

    covered_sources = tuple(
        sorted(canonical_uat_root.rglob("*_test.dart"))
    ) + tuple(sorted(patrol_support_root.rglob("*.dart")))
    if not covered_sources:
        uncovered(canonical_uat_root, "exposes no canonical UAT to analyze")
    for source in covered_sources:
        relative = source.relative_to(app_dir / "test").as_posix()
        if not _prefix_is_analyzed(relative, analyzed_prefixes):
            uncovered(source, "is not reachable from the test host analysis root")


def _excluded_test_prefix(pattern: str) -> str:
    """Return the ``test/``-relative directory an analyzer exclude covers."""

    prefix = pattern[len("test/") :]
    for suffix in ("/**", "/*", "/**/*"):
        if prefix.endswith(suffix):
            prefix = prefix[: -len(suffix)]
            break
    return prefix.rstrip("/")


def _test_host_analysis_prefixes(gate_text: str) -> tuple[str, ...]:
    """Return the ``test/``-relative roots the test host actually analyzes."""

    match = re.search(
        r"test_host/patrol\s+&&\s+flutter\s+analyze\s+"
        r"((?:[^\n\\]*\\\n)*[^\n)]*)",
        gate_text,
    )
    if match is None:
        return ()
    try:
        arguments = shlex.split(match.group(1).replace("\\\n", " "))
    except ValueError:
        return ()
    prefixes: list[str] = []
    for argument in arguments:
        if argument == "test/canonical":
            prefixes.append("")
        elif argument.startswith("test/canonical/"):
            prefixes.append(argument[len("test/canonical/") :].rstrip("/"))
    return tuple(prefixes)


def _prefix_is_analyzed(relative: str, analyzed_prefixes: tuple[str, ...]) -> bool:
    return any(
        prefix == "" or relative == prefix or relative.startswith(f"{prefix}/")
        for prefix in analyzed_prefixes
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
    _verify_ios_cross_lock(failures)
    _verify_cocoapods_toolchain(
        failures,
        pod_executable=os.environ.get("QWQ_COCOAPODS_EXECUTABLE", ""),
    )
    _verify_production_test_dependency_purity(failures)
    _verify_uat_static_analysis_coverage(failures)
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
