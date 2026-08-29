from __future__ import annotations

# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
import tempfile
from pathlib import Path

from quwoquan_ops.cli.lib.app_dependency_toolchain import (
    resolve_cocoapods_executable,
)
from quwoquan_ops.gate import verify_local_dependency_purity as purity
from quwoquan_ops.gate.verify_local_dependency_purity import (
    _verify_cocoapods_toolchain,
    _verify_ios_cross_lock,
    _verify_ios_pods,
    _verify_launcher_dependency_helper,
    _verify_locked_offline_flutter_pub_get,
    _verify_production_test_dependency_purity,
    _verify_test_host_cross_lock,
    _verify_uat_static_analysis_coverage,
)

LOCK = """PODS:\n  - DemoPod (1.0.0)\nSPEC REPOS:\n  trunk:\n    - DemoPod\n"""


def test_parameterized_flutter_pub_get_is_semantically_locked_offline() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        launcher = Path(tmp) / "run.sh"
        launcher.write_text(
            'if ! "$QWQ_REAL_FLUTTER" pub get --offline '
            "--enforce-lockfile; then\n  exit 1\nfi\n",
            encoding="utf-8",
        )
        failures: list[str] = []

        _verify_locked_offline_flutter_pub_get(failures, path=launcher)

        assert failures == []


def test_flutter_pub_get_rejects_either_missing_lock_flag() -> None:
    scripts = (
        '"$QWQ_REAL_FLUTTER" pub get --enforce-lockfile\n',
        '"$QWQ_REAL_FLUTTER" pub get --offline\n',
        'echo "flutter pub get --offline --enforce-lockfile"\n',
    )
    with tempfile.TemporaryDirectory() as tmp:
        launcher = Path(tmp) / "run.sh"
        for script in scripts:
            launcher.write_text(script, encoding="utf-8")
            failures: list[str] = []

            _verify_locked_offline_flutter_pub_get(failures, path=launcher)

            assert len(failures) == 1
            assert "--offline" in failures[0]
            assert "--enforce-lockfile" in failures[0]


def test_flutter_pub_get_checker_ignores_unrelated_complex_bash() -> None:
    script = (
        'if ! patrol_target_output="$(\n'
        "  python3 wrapper.py\n"
        ')"; then\n'
        "  exit 1\n"
        "fi\n"
        "flutter pub get --offline --enforce-lockfile\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        gate = Path(tmp) / "gate_repo.sh"
        gate.write_text(script, encoding="utf-8")
        failures: list[str] = []

        count = _verify_locked_offline_flutter_pub_get(failures, path=gate)

    assert count == 1
    assert failures == []


def test_flutter_pub_get_candidate_with_unmatched_quote_fails_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        gate = Path(tmp) / "gate_repo.sh"
        gate.write_text(
            'flutter pub get --offline --enforce-lockfile "\n',
            encoding="utf-8",
        )
        failures: list[str] = []

        count = _verify_locked_offline_flutter_pub_get(failures, path=gate)

    assert count == 0
    assert failures == [
        f"{gate} shell syntax cannot be parsed for Flutter pub-get verification"
    ]


def test_repository_gate_has_three_complete_locked_offline_pub_get_commands() -> None:
    failures: list[str] = []

    count = _verify_locked_offline_flutter_pub_get(
        failures,
        path=purity.GATE_REPO,
    )

    assert count == 3
    assert failures == []


def test_real_dependency_purity_script_gate_invokes_complete_pub_get_checker(
    monkeypatch,
) -> None:
    checked: list[Path] = []
    monkeypatch.setattr(
        purity,
        "_verify_locked_offline_flutter_pub_get",
        lambda _failures, *, path: checked.append(path) or 0,
    )
    monkeypatch.setattr(purity, "_check_not_contains", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        purity,
        "_verify_launcher_dependency_helper",
        lambda _failures: None,
    )
    monkeypatch.setattr(purity, "_check_contains", lambda *_args, **_kwargs: None)

    purity._verify_scripts([])

    assert checked == [purity.GATE_REPO]


def test_launcher_follows_dual_host_locked_offline_prepare_helper() -> None:
    failures: list[str] = []

    _verify_launcher_dependency_helper(failures)

    assert failures == []


def test_launcher_helper_rejects_missing_lock_flag_or_patrol_host() -> None:
    repository = Path(__file__).resolve().parents[4]
    launcher_source = (repository / "quwoquan_app/run.sh").read_text(encoding="utf-8")
    helper_source = (
        repository / "quwoquan_app/scripts/device/prepare_flutter_dependencies.py"
    ).read_text(encoding="utf-8")
    mutations = (
        ('        "--offline",\n', ""),
        ('        "--enforce-lockfile",\n', ""),
        ("environment=patrol_environment", "environment=production_environment"),
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        launcher = root / "run.sh"
        helper = root / "prepare_flutter_dependencies.py"
        launcher.write_text(launcher_source, encoding="utf-8")
        for old, new in mutations:
            helper.write_text(helper_source.replace(old, new, 1), encoding="utf-8")
            failures: list[str] = []

            _verify_launcher_dependency_helper(
                failures,
                launcher=launcher,
                helper=helper,
            )

            assert failures
            assert failures[0].startswith("APP.DEPENDENCY.launcher_helper_invalid:")


def test_launcher_helper_ignores_unexecuted_locked_pub_get_decoy() -> None:
    repository = Path(__file__).resolve().parents[4]
    launcher_source = (repository / "quwoquan_app/run.sh").read_text(encoding="utf-8")
    helper_source = (
        repository / "quwoquan_app/scripts/device/prepare_flutter_dependencies.py"
    ).read_text(encoding="utf-8")
    helper_source = helper_source.replace('        "--offline",\n', "", 1)
    helper_source = helper_source.replace(
        "    command = [\n",
        '    decoy = [flutter, "pub", "get", "--offline", "--enforce-lockfile"]\n'
        "    command = [\n",
        1,
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        launcher = root / "run.sh"
        helper = root / "prepare_flutter_dependencies.py"
        launcher.write_text(launcher_source, encoding="utf-8")
        helper.write_text(helper_source, encoding="utf-8")
        failures: list[str] = []

        _verify_launcher_dependency_helper(
            failures,
            launcher=launcher,
            helper=helper,
        )

    assert any("locked offline pub replay missing" in failure for failure in failures)


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


def _write_test_host_cross_lock(
    root: Path,
    *,
    production_firebase_core: str,
    host_firebase_core: str,
) -> None:
    (root / "pubspec.lock").write_text(
        "packages:\n"
        "  firebase_core:\n    version: 4.12.1\n"
        "  firebase_messaging:\n    version: 16.4.3\n",
        encoding="utf-8",
    )
    (root / "Podfile.lock").write_text(
        "PODS:\n"
        f"  - firebase_core ({production_firebase_core})\n"
        "  - firebase_messaging (16.4.3)\n"
        "  - QWQVendorAlipaySDK (15.8.40.1)\n"
        "  - libwebp (1.5.0)\n",
        encoding="utf-8",
    )
    (root / "TestHostPodfile.lock").write_text(
        "PODS:\n"
        f"  - firebase_core ({host_firebase_core})\n"
        "  - firebase_messaging (16.4.3)\n"
        "  - patrol (0.0.1)\n"
        "  - integration_test (0.0.1)\n"
        "  - libwebp (1.6.0)\n",
        encoding="utf-8",
    )


def test_test_host_cross_lock_rejects_plugin_pod_drift() -> None:
    """UAT test host 锁到与生产不同的插件 pod 版本必须在真实编译前失败。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_test_host_cross_lock(
            root,
            production_firebase_core="4.12.1",
            host_firebase_core="4.13.0",
        )
        failures: list[str] = []
        _verify_test_host_cross_lock(
            failures,
            pubspec_lock=root / "pubspec.lock",
            podfile_lock=root / "Podfile.lock",
            test_host_podfile_lock=root / "TestHostPodfile.lock",
        )
        assert failures == [
            (
                "APP.DEPENDENCY.lock_drift: firebase_core "
                "production=4.12.1 test_host=4.13.0"
            )
        ]


def test_test_host_cross_lock_accepts_aligned_plugins_with_side_only_pods() -> None:
    """只约束 pubspec 派生插件：test-only pod、vendored SDK 与间接原生 pod
    只存在于一侧或版本浮动，不构成漂移。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_test_host_cross_lock(
            root,
            production_firebase_core="4.12.1",
            host_firebase_core="4.12.1",
        )
        failures: list[str] = []
        _verify_test_host_cross_lock(
            failures,
            pubspec_lock=root / "pubspec.lock",
            podfile_lock=root / "Podfile.lock",
            test_host_podfile_lock=root / "TestHostPodfile.lock",
        )
        assert failures == []


def test_test_host_cross_lock_ignores_live_generated_manifest_projection() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_test_host_cross_lock(
            root,
            production_firebase_core="4.12.1",
            host_firebase_core="4.12.1",
        )
        (root / "Manifest.lock").write_text(
            "PODS:\n  - stale (0.0.1)\n", encoding="utf-8"
        )
        failures: list[str] = []
        _verify_test_host_cross_lock(
            failures,
            pubspec_lock=root / "pubspec.lock",
            podfile_lock=root / "Podfile.lock",
            test_host_podfile_lock=root / "TestHostPodfile.lock",
        )
        assert failures == []


def test_test_host_cross_lock_reports_missing_locks() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        failures: list[str] = []
        _verify_test_host_cross_lock(
            failures,
            pubspec_lock=root / "pubspec.lock",
            podfile_lock=root / "Podfile.lock",
            test_host_podfile_lock=root / "TestHostPodfile.lock",
        )
        assert len(failures) == 3
        assert all("lock_drift: missing" in failure for failure in failures)


def test_repository_test_host_lock_is_aligned_with_production() -> None:
    """仓库当前状态必须满足该判据，否则 iOS UAT 构建在 pod 解析处失败。"""
    failures: list[str] = []
    _verify_test_host_cross_lock(failures)
    assert failures == []


GRAPH_ABSENCE_FAILURES = (
    "missing generated plugin graph",
    "missing isolated host plugin graph",
)


def _graph_with(*plugin_names: str) -> str:
    plugins = ",".join(f'{{"name":"{name}"}}' for name in plugin_names)
    return '{"plugins":{"ios":[' + plugins + "]}}"


def test_plugin_graphs_absent_on_clean_checkout_are_not_reported_as_leaks() -> None:
    """.flutter-plugins-dependencies 由 pub get 生成且 gitignore，缺席不是泄漏。"""
    with tempfile.TemporaryDirectory() as tmp:
        app_dir = Path(tmp)
        (app_dir / "pubspec.yaml").write_text("name: quwoquan_app\n", encoding="utf-8")
        failures: list[str] = []
        _verify_production_test_dependency_purity(failures, app_dir=app_dir)
        assert not [
            failure
            for failure in failures
            if any(marker in failure for marker in GRAPH_ABSENCE_FAILURES)
        ]


def test_materialized_plugin_graph_still_rejects_patrol_in_production() -> None:
    """图一旦存在就必须校验：patrol 链进生产 App 仍要被判为泄漏。"""
    with tempfile.TemporaryDirectory() as tmp:
        app_dir = Path(tmp)
        (app_dir / "pubspec.yaml").write_text("name: quwoquan_app\n", encoding="utf-8")
        (app_dir / ".flutter-plugins-dependencies").write_text(
            _graph_with("patrol"), encoding="utf-8"
        )
        failures: list[str] = []
        _verify_production_test_dependency_purity(failures, app_dir=app_dir)
        assert [
            failure
            for failure in failures
            if ".flutter-plugins-dependencies contains patrol" in failure
        ]


def test_materialized_host_graph_still_requires_patrol_in_isolated_host() -> None:
    """隔离宿主的图一旦存在，就必须证明 patrol 真的链在宿主里。"""
    with tempfile.TemporaryDirectory() as tmp:
        app_dir = Path(tmp)
        (app_dir / "pubspec.yaml").write_text("name: quwoquan_app\n", encoding="utf-8")
        host_dir = app_dir / "test_host/patrol"
        host_dir.mkdir(parents=True)
        (host_dir / ".flutter-plugins-dependencies").write_text(
            _graph_with("integration_test"), encoding="utf-8"
        )
        failures: list[str] = []
        _verify_production_test_dependency_purity(failures, app_dir=app_dir)
        assert [failure for failure in failures if 'missing "name":"patrol"' in failure]


def _write_tracked_locks_only(
    root: Path,
    *,
    pub_version: str,
    pod_version: str,
    messaging_pod: str = "12.15.0",
) -> None:
    """只写两份受版本控制的锁，不铺 ios/.symlinks/plugins。"""

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
        f"  - Firebase/Messaging ({messaging_pod})\n",
        encoding="utf-8",
    )


def test_cross_lock_holds_without_materialized_plugin_tree() -> None:
    """ios/.symlinks 由 pub get 生成且 gitignore，干净 checkout 上缺席不算漂移。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_tracked_locks_only(root, pub_version="4.12.1", pod_version="4.12.1")
        failures: list[str] = []
        _verify_ios_cross_lock(
            failures,
            pubspec_lock=root / "pubspec.lock",
            podfile_lock=root / "Podfile.lock",
            pods_manifest_lock=root / "Manifest.lock",
            plugin_root=root / "plugins",
        )
        assert failures == []


def test_cross_lock_still_rejects_drift_without_materialized_plugin_tree() -> None:
    """插件树缺席不得降级成放行：两份受版本控制的锁自己就足以判定漂移。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_tracked_locks_only(root, pub_version="4.12.1", pod_version="4.13.0")
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
                "plugin=<not-materialized> pod=4.13.0"
            )
        ]


def test_cross_lock_rejects_disagreeing_firebase_pods_without_plugin_tree() -> None:
    """Firebase 期望版本只写在被链接插件里；树缺席时仍要求 Podfile.lock 内部自洽。"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_tracked_locks_only(
            root,
            pub_version="4.12.1",
            pod_version="4.12.1",
            messaging_pod="12.14.0",
        )
        failures: list[str] = []
        _verify_ios_cross_lock(
            failures,
            pubspec_lock=root / "pubspec.lock",
            podfile_lock=root / "Podfile.lock",
            pods_manifest_lock=root / "Manifest.lock",
            plugin_root=root / "plugins",
        )
        assert any("Firebase pods disagree" in failure for failure in failures)


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

    assert resolve_cocoapods_executable("/usr/local/bin/pod") == str(runtime.resolve())


def _stub_pod_inspection(monkeypatch, version: str) -> None:
    class Result:
        returncode = 0

        def __init__(self, stdout: str) -> None:
            self.stdout = stdout

    results = iter(
        [
            Result(f"{version}\n"),
            Result("Executable Path: /opt/pod/libexec/bin/pod\n"),
        ]
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.app_dependency_toolchain.subprocess.run",
        lambda *_args, **_kwargs: next(results),
    )


def test_cocoapods_is_not_applicable_without_any_installed_pod(monkeypatch) -> None:
    """CocoaPods 只存在于 macOS，Linux 上缺席不构成版本漂移。"""

    monkeypatch.setattr("shutil.which", lambda _name: None)
    failures: list[str] = []

    _verify_cocoapods_toolchain(failures)

    assert failures == []


def test_cocoapods_still_rejects_declared_but_unusable_executable(
    monkeypatch,
) -> None:
    """显式声明就是承诺有 CocoaPods，声明却不可用仍然是漂移。"""

    monkeypatch.setattr("shutil.which", lambda _name: None)
    _stub_pod_inspection(monkeypatch, "1.15.2")
    failures: list[str] = []

    _verify_cocoapods_toolchain(failures, pod_executable="/usr/local/bin/pod")

    assert failures and failures[0].startswith("APP.DEPENDENCY.cocoapods_mixed:")


def test_cocoapods_still_rejects_drift_discovered_on_path(monkeypatch) -> None:
    """装了 CocoaPods 就必须判：缺席豁免不能顺带放过 PATH 上的漂移版本。"""

    monkeypatch.setattr("shutil.which", lambda _name: "/usr/local/bin/pod")
    _stub_pod_inspection(monkeypatch, "1.15.2")
    failures: list[str] = []

    _verify_cocoapods_toolchain(failures)

    assert failures and failures[0].startswith("APP.DEPENDENCY.cocoapods_mixed:")


def _write_production_purity_fixture(root: Path, *, leaked: bool) -> Path:
    app = root / "quwoquan_app"
    (app / "ios/Runner.xcodeproj").mkdir(parents=True)
    (app / "ios/Runner").mkdir(parents=True)
    (app / "ios/Flutter").mkdir(parents=True)
    (app / "android/app/src/main/java/com/quwoquan/quwoquan_app").mkdir(parents=True)
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


def _write_uat_analysis_coverage_fixture(root: Path) -> tuple[Path, Path]:
    app = root / "quwoquan_app"
    (app / "test/user_acceptance/journeys/startup").mkdir(parents=True)
    (app / "test/support/runtime/patrol").mkdir(parents=True)
    (app / "test_host/patrol/test").mkdir(parents=True)
    (app / "test/user_acceptance/journeys/startup/startup_test.dart").write_text(
        "void main() {}\n", encoding="utf-8"
    )
    (app / "test/support/runtime/patrol/patrol_test_support.dart").write_text(
        "void support() {}\n", encoding="utf-8"
    )
    (app / "analysis_options.yaml").write_text(
        "analyzer:\n"
        "  exclude:\n"
        "    - test/user_acceptance/**\n"
        "    - test/support/runtime/patrol/**\n",
        encoding="utf-8",
    )
    (app / "test_host/patrol/test/canonical").symlink_to(
        Path("../../../test"), target_is_directory=True
    )
    gate = root / "gate_repo.sh"
    gate.write_text(
        "(cd quwoquan_app/test_host/patrol && flutter analyze \\\n"
        "  lib test/patrol test/canonical/user_acceptance "
        "test/canonical/support/runtime/patrol)\n",
        encoding="utf-8",
    )
    return app, gate


def test_uat_analysis_coverage_accepts_symlinked_test_host_analysis() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app, gate = _write_uat_analysis_coverage_fixture(Path(tmp))
        failures: list[str] = []
        _verify_uat_static_analysis_coverage(failures, app_dir=app, gate_script=gate)
        assert failures == []


def test_uat_analysis_coverage_rejects_exclusion_without_test_host_analysis() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app, gate = _write_uat_analysis_coverage_fixture(Path(tmp))
        gate.write_text("flutter analyze lib test\n", encoding="utf-8")
        failures: list[str] = []
        _verify_uat_static_analysis_coverage(failures, app_dir=app, gate_script=gate)
        assert [
            failure
            for failure in failures
            if failure.startswith("APP.PACKAGE.uat_static_analysis_uncovered:")
            and "test/canonical/user_acceptance" in failure
        ]


def test_uat_analysis_coverage_rejects_copied_canonical_uat() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app, gate = _write_uat_analysis_coverage_fixture(Path(tmp))
        canonical_link = app / "test_host/patrol/test/canonical"
        canonical_link.unlink()
        (canonical_link / "user_acceptance/journeys/startup").mkdir(parents=True)
        (
            canonical_link / "user_acceptance/journeys/startup/startup_test.dart"
        ).write_text("void main() {}\n", encoding="utf-8")
        failures: list[str] = []
        _verify_uat_static_analysis_coverage(failures, app_dir=app, gate_script=gate)
        assert [
            failure
            for failure in failures
            if failure.startswith("APP.PACKAGE.uat_static_analysis_uncovered:")
            and "must be a symlink" in failure
        ]


def test_uat_analysis_coverage_rejects_unexcluded_main_app_analysis() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app, gate = _write_uat_analysis_coverage_fixture(Path(tmp))
        (app / "analysis_options.yaml").write_text(
            "analyzer:\n  exclude:\n    - build/**\n", encoding="utf-8"
        )
        failures: list[str] = []
        _verify_uat_static_analysis_coverage(failures, app_dir=app, gate_script=gate)
        assert [
            failure
            for failure in failures
            if failure.startswith("APP.PACKAGE.uat_static_analysis_uncovered:")
            and "test/user_acceptance/**" in failure
        ]


def test_uat_analysis_coverage_rejects_a_new_exclude_without_a_witness() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app, gate = _write_uat_analysis_coverage_fixture(Path(tmp))
        (app / "analysis_options.yaml").write_text(
            "analyzer:\n"
            "  exclude:\n"
            "    - test/user_acceptance/**\n"
            "    - test/support/runtime/patrol/**\n"
            "    - test/support/runtime/device/**\n",
            encoding="utf-8",
        )
        failures: list[str] = []
        _verify_uat_static_analysis_coverage(failures, app_dir=app, gate_script=gate)
        assert [
            failure
            for failure in failures
            if failure.startswith("APP.PACKAGE.uat_static_analysis_uncovered:")
            and "test/support/runtime/device/**" in failure
        ]


def test_uat_analysis_coverage_rejects_a_commented_out_analysis_root() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app, gate = _write_uat_analysis_coverage_fixture(Path(tmp))
        gate.write_text(
            "# test/canonical/user_acceptance test/canonical/support/runtime/patrol\n"
            "(cd quwoquan_app/test_host/patrol && flutter analyze lib test/patrol)\n",
            encoding="utf-8",
        )
        failures: list[str] = []
        _verify_uat_static_analysis_coverage(failures, app_dir=app, gate_script=gate)
        assert [
            failure
            for failure in failures
            if failure.startswith("APP.PACKAGE.uat_static_analysis_uncovered:")
            and "test/canonical/user_acceptance" in failure
        ]


def test_uat_analysis_coverage_rejects_a_complete_commented_command() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app, gate = _write_uat_analysis_coverage_fixture(Path(tmp))
        gate.write_text(
            "# (cd quwoquan_app/test_host/patrol && flutter analyze lib test/patrol "
            "test/canonical/user_acceptance test/canonical/support/runtime/patrol)\n"
            "(cd quwoquan_app/test_host/patrol && flutter analyze lib test/patrol)\n",
            encoding="utf-8",
        )
        failures: list[str] = []
        _verify_uat_static_analysis_coverage(failures, app_dir=app, gate_script=gate)
        assert [
            failure
            for failure in failures
            if failure.startswith("APP.PACKAGE.uat_static_analysis_uncovered:")
            and "test/canonical/user_acceptance" in failure
        ]


def test_uat_analysis_coverage_rejects_test_host_excluding_canonical_tree() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app, gate = _write_uat_analysis_coverage_fixture(Path(tmp))
        (app / "test_host/patrol/analysis_options.yaml").write_text(
            "analyzer:\n  exclude:\n    - test/canonical/**\n", encoding="utf-8"
        )
        failures: list[str] = []
        _verify_uat_static_analysis_coverage(failures, app_dir=app, gate_script=gate)
        assert [
            failure
            for failure in failures
            if failure.startswith("APP.PACKAGE.uat_static_analysis_uncovered:")
            and "must not exclude test/canonical/**" in failure
        ]
