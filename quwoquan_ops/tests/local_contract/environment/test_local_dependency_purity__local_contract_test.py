from __future__ import annotations

import tempfile
from pathlib import Path

from quwoquan_ops.cli.lib.app_dependency_toolchain import (
    resolve_cocoapods_executable,
)
from quwoquan_ops.gate.verify_local_dependency_purity import (
    _verify_cocoapods_toolchain,
    _verify_ios_cross_lock,
    _verify_ios_pods,
    _verify_production_test_dependency_purity,
)

LOCK = """PODS:\n  - DemoPod (1.0.0)\nSPEC REPOS:\n  trunk:\n    - DemoPod\n"""


def test_clean_checkout_uses_podfile_lock_without_requiring_generated_pods() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        podfile_lock = root / "Podfile.lock"
        podfile_lock.write_text(LOCK, encoding="utf-8")
        failures: list[str] = []

        _verify_ios_pods(
            failures,
            podfile_lock=podfile_lock,
            pods_manifest_lock=root / "Pods/Manifest.lock",
            pods_dir=root / "Pods",
        )

        assert failures == []


def test_materialized_pods_require_matching_manifest_and_trunk_directories() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        pods_dir = root / "Pods"
        pods_dir.mkdir()
        podfile_lock = root / "Podfile.lock"
        podfile_lock.write_text(LOCK, encoding="utf-8")
        failures: list[str] = []

        _verify_ios_pods(
            failures,
            podfile_lock=podfile_lock,
            pods_manifest_lock=pods_dir / "Manifest.lock",
            pods_dir=pods_dir,
        )

        assert any("Manifest.lock" in failure for failure in failures)

        (pods_dir / "Manifest.lock").write_text(LOCK, encoding="utf-8")
        failures.clear()
        _verify_ios_pods(
            failures,
            podfile_lock=podfile_lock,
            pods_manifest_lock=pods_dir / "Manifest.lock",
            pods_dir=pods_dir,
        )
        assert any("DemoPod" in failure for failure in failures)

        (pods_dir / "DemoPod").mkdir()
        failures.clear()
        _verify_ios_pods(
            failures,
            podfile_lock=podfile_lock,
            pods_manifest_lock=pods_dir / "Manifest.lock",
            pods_dir=pods_dir,
        )
        assert failures == []


def _write_cross_lock(root: Path, *, pub_version: str, pod_version: str) -> None:
    (root / "plugins/firebase_core/ios").mkdir(parents=True)
    (root / "plugins/firebase_messaging").mkdir(parents=True)
    (root / "plugins/firebase_core/pubspec.yaml").write_text(
        f"name: firebase_core\nversion: {pub_version}\n", encoding="utf-8"
    )
    (root / "plugins/firebase_messaging/pubspec.yaml").write_text(
        "name: firebase_messaging\nversion: 16.4.3\n", encoding="utf-8"
    )
    (root / "plugins/firebase_core/ios/firebase_sdk_version.rb").write_text(
        "def firebase_sdk_version!()\n  '12.15.0'\nend\n", encoding="utf-8"
    )
    (root / "pubspec.lock").write_text(
        "packages:\n"
        f"  firebase_core:\n    version: {pub_version}\n"
        "  firebase_messaging:\n    version: 16.4.3\n",
        encoding="utf-8",
    )
    (root / "Podfile.lock").write_text(
        "PODS:\n"
        f"  - firebase_core ({pod_version})\n"
        "  - firebase_messaging (16.4.3)\n"
        "  - Firebase/CoreOnly (12.15.0)\n"
        "  - Firebase/Messaging (12.15.0)\n",
        encoding="utf-8",
    )


def test_cross_lock_rejects_dart_plugin_and_pod_drift() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_cross_lock(root, pub_version="4.12.1", pod_version="4.13.0")
        failures: list[str] = []
        _verify_ios_cross_lock(
            failures,
            pubspec_lock=root / "pubspec.lock",
            podfile_lock=root / "Podfile.lock",
            pods_manifest_lock=root / "Manifest.lock",
            plugin_root=root / "plugins",
        )
        assert failures == [
            (
                "APP.DEPENDENCY.lock_drift: firebase_core pub=4.12.1 "
                "plugin=4.12.1 pod=4.13.0"
            )
        ]


def test_cross_lock_accepts_one_exact_graph() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_cross_lock(root, pub_version="4.12.1", pod_version="4.12.1")
        failures: list[str] = []
        _verify_ios_cross_lock(
            failures,
            pubspec_lock=root / "pubspec.lock",
            podfile_lock=root / "Podfile.lock",
            pods_manifest_lock=root / "Manifest.lock",
            plugin_root=root / "plugins",
        )
        assert failures == []


def test_cocoapods_rejects_mixed_executable_and_runtime(monkeypatch) -> None:
    class Result:
        returncode = 0

        def __init__(self, stdout: str) -> None:
            self.stdout = stdout

    results = iter(
        [
            Result("1.16.2\n"),
            Result(
                "Executable Path: "
                "/opt/homebrew/Cellar/cocoapods/1.15.2_1/libexec/bin/pod\n"
            ),
            Result("1.15.2\n"),
            Result(
                "Executable Path: "
                "/opt/homebrew/Cellar/cocoapods/1.15.2_1/libexec/bin/pod\n"
            ),
        ]
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.app_dependency_toolchain.subprocess.run",
        lambda *_args, **_kwargs: next(results),
    )
    failures: list[str] = []
    _verify_cocoapods_toolchain(failures, pod_executable="/usr/local/bin/pod")
    assert failures and failures[0].startswith("APP.DEPENDENCY.cocoapods_mixed:")


def test_cocoapods_wrapper_normalizes_to_self_reported_runtime(
    monkeypatch,
    tmp_path: Path,
) -> None:
    class Result:
        returncode = 0

        def __init__(self, stdout: str) -> None:
            self.stdout = stdout

    runtime = tmp_path / "libexec/bin/pod"
    runtime.parent.mkdir(parents=True)
    runtime.write_text("#!/bin/sh\n", encoding="utf-8")
    results = iter(
        [
            Result("1.16.2\n"),
            Result(f"Executable Path: {runtime}\n"),
            Result("1.16.2\n"),
            Result(f"Executable Path: {runtime}\n"),
        ]
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.app_dependency_toolchain.subprocess.run",
        lambda *_args, **_kwargs: next(results),
    )

    assert resolve_cocoapods_executable("/usr/local/bin/pod") == str(
        runtime.resolve()
    )


def _write_production_purity_fixture(root: Path, *, leaked: bool) -> Path:
    app = root / "quwoquan_app"
    (app / "ios/Runner.xcodeproj").mkdir(parents=True)
    (app / "ios/Runner").mkdir(parents=True)
    (app / "ios/Flutter").mkdir(parents=True)
    (app / "android/app/src/main/java/com/quwoquan/quwoquan_app").mkdir(
        parents=True
    )
    (app / "test/user_acceptance/journeys/startup").mkdir(parents=True)
    (app / "test_host/patrol/android/app").mkdir(parents=True)
    (app / "test_host/patrol/ios/RunnerUITests").mkdir(parents=True)
    (app / "test_host/patrol/test/patrol").mkdir(parents=True)
    production_test_dependency = "  patrol: ^4.5.0\n" if leaked else ""
    (app / "pubspec.yaml").write_text(
        "name: app\ndev_dependencies:\n" + production_test_dependency,
        encoding="utf-8",
    )
    (app / ".flutter-plugins-dependencies").write_text(
        '{"plugins":{"ios":[]}}\n', encoding="utf-8"
    )
    for relative in (
        "ios/Podfile",
        "ios/Podfile.lock",
        "ios/Runner.xcodeproj/project.pbxproj",
        "ios/Runner/GeneratedPluginRegistrant.m",
        "android/app/build.gradle.kts",
        "android/app/src/main/java/com/quwoquan/quwoquan_app/StartupEagerPluginRegistry.java",
    ):
        (app / relative).write_text("production\n", encoding="utf-8")
    (app / "test/user_acceptance/journeys/startup/startup_test.dart").write_text(
        "void main() {}\n", encoding="utf-8"
    )
    (app / "test_host/patrol/pubspec.yaml").write_text(
        "dev_dependencies:\n  patrol: any\n  integration_test:\n    sdk: flutter\n",
        encoding="utf-8",
    )
    (app / "test_host/patrol/.flutter-plugins-dependencies").write_text(
        '{"plugins":{"ios":[{"name":"patrol"},{"name":"integration_test"}]}}\n',
        encoding="utf-8",
    )
    (app / "test_host/patrol/android/app/build.gradle.kts").write_text(
        'runner = "pl.leancode.patrol.PatrolJUnitRunner"\n', encoding="utf-8"
    )
    (app / "test_host/patrol/ios/RunnerUITests/RunnerUITests.m").write_text(
        "PATROL_INTEGRATION_TEST_IOS_RUNNER(RunnerUITests)\n", encoding="utf-8"
    )
    (app / "test_host_wrapper.py").write_text(
        'root_parts = ("test", "user_acceptance")\n'
        "target = APP_DIR / normalized\n"
        "directory = PATROL_HOST_DIR / PATROL_TEST_DIRECTORY\n"
        "def _canonical_patrol_uat_targets():\n"
        '    canonical_root.rglob("*_test.dart")\n',
        encoding="utf-8",
    )
    return app


def test_production_purity_rejects_test_dependency_leak() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app = _write_production_purity_fixture(Path(tmp), leaked=True)
        failures: list[str] = []
        _verify_production_test_dependency_purity(failures, app_dir=app)
        assert any(
            failure.startswith("APP.PACKAGE.production_test_dependency_leak:")
            and "dev_dependencies.patrol" in failure
            for failure in failures
        )


def test_production_purity_accepts_isolated_host_and_enumerated_uat() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app = _write_production_purity_fixture(Path(tmp), leaked=False)
        failures: list[str] = []
        _verify_production_test_dependency_purity(failures, app_dir=app)
        assert failures == []
