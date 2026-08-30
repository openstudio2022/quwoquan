from __future__ import annotations

# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
import tempfile

import pytest
from pathlib import Path

from quwoquan_ops.cli.lib.app_dependency_toolchain import (
    AppDependencyToolchainError,
    cocoapods_environment,
    cocoapods_identity_from_environment,
    resolve_cocoapods_executable,
    resolve_cocoapods_identity,
    validate_cocoapods_child_environment,
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


def _write_pod(
    path: Path,
    *,
    version: str = "1.16.2",
    runtime: Path | None = None,
) -> None:
    reported = runtime or path
    script = f"""#!/bin/sh
if [ "$1" = "--version" ]; then
  printf '%s\n' {version!r}
  exit 0
fi
if [ "$1" = "env" ]; then
  cat <<'EOF'
### Stack
CocoaPods : {version}
Ruby : 3.3.0
RubyGems : 3.5.0
### Plugins
cocoapods-deintegrate : 1.0.5
Executable Path: {reported}
EOF
  exit 0
fi
exit 2
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)


def test_cocoapods_resolver_returns_complete_physical_identity_and_seal(
    tmp_path: Path,
) -> None:
    pod = tmp_path / "exact/bin/pod"
    _write_pod(pod)

    identity = resolve_cocoapods_identity(pod, search_path=str(pod.parent))

    assert identity.executable == pod.resolve()
    assert identity.version == "1.16.2"
    assert identity.executable_digest.startswith("sha256:")
    assert identity.runtime_environment_digest.startswith("sha256:")
    assert identity.command_resolution_digest.startswith("sha256:")
    assert identity.binding_seal.startswith("sha256:")
    resolved_again = resolve_cocoapods_identity(
        pod,
        search_path=str(pod.parent),
    )
    assert resolved_again.executable == pod.resolve()
    assert resolved_again.as_dict() == identity.as_dict()


def test_cocoapods_resolver_rejects_missing_and_hostile_path(
    monkeypatch,
    tmp_path: Path,
) -> None:
    hostile = tmp_path / "hostile/pod"
    exact = tmp_path / "exact/pod"
    _write_pod(hostile, version="1.15.2")
    _write_pod(exact)

    with pytest.raises(AppDependencyToolchainError, match="cocoapods_missing"):
        resolve_cocoapods_identity(search_path=str(tmp_path / "empty"))
    with pytest.raises(AppDependencyToolchainError, match="cocoapods_mixed"):
        resolve_cocoapods_identity(exact, search_path=str(hostile.parent))


def test_cocoapods_stored_environment_validates_seal_without_live_probe(
    monkeypatch,
    tmp_path: Path,
) -> None:
    pod = tmp_path / "exact/bin/pod"
    _write_pod(pod)
    identity = resolve_cocoapods_identity(pod, search_path=str(pod.parent))
    environment = identity.as_environment()

    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.app_dependency_toolchain._inspect",
        lambda _executable: (_ for _ in ()).throw(AssertionError("live inspect")),
    )

    stored = cocoapods_identity_from_environment(
        environment,
        inspect_physical=False,
    )
    assert stored.as_environment() == environment

    drifted = dict(environment)
    drifted["QWQ_COCOAPODS_BINDING_SEAL"] = "sha256:" + "0" * 64
    with pytest.raises(AppDependencyToolchainError, match="cocoapods_mixed"):
        cocoapods_identity_from_environment(
            drifted,
            inspect_physical=False,
        )


def test_cocoapods_environment_rejects_mixed_digest_and_seal(
    tmp_path: Path,
) -> None:
    pod = tmp_path / "exact/bin/pod"
    _write_pod(pod)
    identity = resolve_cocoapods_identity(pod, search_path=str(pod.parent))
    environment = cocoapods_environment(identity, base={"PATH": str(pod.parent)})

    for key in (
        "QWQ_COCOAPODS_EXECUTABLE_DIGEST",
        "QWQ_COCOAPODS_RUNTIME_ENVIRONMENT_DIGEST",
        "QWQ_COCOAPODS_COMMAND_RESOLUTION_DIGEST",
        "QWQ_COCOAPODS_BINDING_SEAL",
    ):
        mixed = dict(environment)
        mixed[key] = "sha256:" + "9" * 64
        with pytest.raises(AppDependencyToolchainError, match="cocoapods_mixed"):
            cocoapods_identity_from_environment(mixed)


def test_cocoapods_child_environment_rejects_hostile_path_then_accepts_prepend(
    tmp_path: Path,
) -> None:
    hostile = tmp_path / "hostile/pod"
    exact = tmp_path / "exact/pod"
    _write_pod(hostile, version="1.15.2")
    _write_pod(exact)
    identity = resolve_cocoapods_identity(exact, search_path=str(exact.parent))
    hostile_environment = {
        **identity.as_environment(),
        "PATH": str(hostile.parent),
    }

    with pytest.raises(AppDependencyToolchainError, match="cocoapods_mixed"):
        validate_cocoapods_child_environment(hostile_environment)

    sealed = cocoapods_environment(identity, base=hostile_environment)
    observed, child = validate_cocoapods_child_environment(sealed)
    assert observed.as_dict() == identity.as_dict()
    assert child["PATH"].split(":")[0] == str(exact.parent)


def test_cocoapods_is_not_applicable_without_any_installed_pod(monkeypatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _name, **_kwargs: None)
    failures: list[str] = []

    _verify_cocoapods_toolchain(failures)

    assert failures == []


def test_cocoapods_still_rejects_declared_but_unusable_executable(
    tmp_path: Path,
) -> None:
    failures: list[str] = []

    _verify_cocoapods_toolchain(
        failures,
        pod_executable=str(tmp_path / "missing/pod"),
    )

    assert failures and failures[0].startswith("APP.DEPENDENCY.cocoapods_mixed:")


def test_cocoapods_still_rejects_drift_discovered_on_path(
    monkeypatch,
    tmp_path: Path,
) -> None:
    pod = tmp_path / "pod"
    _write_pod(pod, version="1.15.2")
    monkeypatch.setattr("shutil.which", lambda _name, **_kwargs: str(pod))
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
