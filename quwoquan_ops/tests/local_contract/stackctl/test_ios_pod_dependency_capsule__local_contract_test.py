from __future__ import annotations

import os
from pathlib import Path

import pytest

from quwoquan_ops.cli.lib.package_reuse.ios_pod_capsule import (
    IOS_POD_CAPSULE_SCHEMA,
    SUPPORTED_COCOAPODS_VERSION,
    build_verified_ios_pod_snapshot,
    inspect_cocoapods_executable,
)
from quwoquan_ops.cli.lib.package_reuse.ios_pod_inputs import (
    IOS_POD_DEPENDENCY_DIRECTORIES,
    IOS_POD_DEPENDENCY_LOGICAL_PATHS,
    IOS_POD_PATROL_HOST,
    IOS_POD_PRODUCTION_HOST,
)
from quwoquan_ops.cli.lib.package_reuse.ios_pod_projection import (
    cocoapods_network_denied_command,
    isolated_cocoapods_environment,
    materialize_ios_pod_projection,
    run_offline_cocoapods_install,
)
from quwoquan_ops.cli.lib.package_reuse.ios_pod_store import (
    load_ios_pod_capsule_bytes,
    load_verified_ios_pod_capsule,
    write_ios_pod_capsule,
)

# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001.t9

_UPSTREAM_DEPENDENCY_DIGEST = "sha256:" + "1" * 64


@pytest.fixture(autouse=True)
def _restore_tmp_permissions_for_pytest_cleanup(tmp_path: Path):
    yield
    for path in sorted(
        tmp_path.rglob("*"), key=lambda item: len(item.parts), reverse=True
    ):
        if not path.is_symlink():
            path.chmod(0o755 if path.is_dir() else 0o644)
    tmp_path.chmod(0o755)


def _pod_executable(root: Path, *, marker: str = "first") -> Path:
    executable = root / "pod"
    executable.write_text(
        "#!/bin/sh\n"
        'SELF="$(cd "$(dirname "$0")" && pwd -P)/$(basename "$0")"\n'
        'case "${1:-}" in\n'
        f"  --version) printf '%s\\n' '{SUPPORTED_COCOAPODS_VERSION}' ;;\n"
        "  env) printf '### Stack\nCocoaPods : %s\nRuby : 3.3.0\nRubyGems : 3.5.0\n### Plugins\ncocoapods-deintegrate : 1.0.5\nExecutable Path: %s\n' "
        f"'{SUPPORTED_COCOAPODS_VERSION}' \"$SELF\" ;;\n"
        f"  install) printf '%s\\n' '{marker}'; "
        f"if [ '{marker}' = 'mutate-pods' ]; then "
        "printf '// drift\\n' >> Pods/Framework/Versions/A/Headers/Example.h; fi; "
        f"if [ '{marker}' = 'project-once' ] && "
        '[ ! -f "$CP_HOME_DIR/projected" ]; then '
        "printf '// projected\\n' >> Pods/Pods.xcodeproj/project.pbxproj; "
        ': > "$CP_HOME_DIR/projected"; fi; '
        f"if [ '{marker}' = 'xcode-user-state' ]; then "
        "mkdir -p Pods/Pods.xcodeproj/xcuserdata/tester.xcuserdatad; "
        "printf '%s\\n' 'ephemeral' > Pods/Pods.xcodeproj/xcuserdata/"
        "tester.xcuserdatad/xcschememanagement.plist; fi; "
        f"if [ '{marker}' = 'project-always' ]; then "
        "printf '// projected again\\n' >> Pods/Pods.xcodeproj/project.pbxproj; fi; "
        f"if [ '{marker}' = 'project-leak' ]; then "
        "printf '// /outside/online/root/file\\n' >> "
        "Pods/Pods.xcodeproj/project.pbxproj; fi; "
        f"if [ '{marker}' = 'project-generic-segment' ] && "
        '[ ! -f "$CP_HOME_DIR/generic-segment" ]; then '
        "printf '// dependencies is not a path\\n' >> "
        "Pods/Pods.xcodeproj/project.pbxproj; "
        ': > "$CP_HOME_DIR/generic-segment"; fi; '
        f"if [ '{marker}' = 'project-flutter-toolchain' ] && "
        '[ ! -f "$CP_HOME_DIR/flutter-toolchain" ]; then '
        "printf '// %s/bin/cache/artifacts/engine/ios/Flutter.xcframework\\n' "
        '"$FLUTTER_ROOT" >> Pods/Pods.xcodeproj/project.pbxproj; '
        ': > "$CP_HOME_DIR/flutter-toolchain"; fi ;;\n'
        "  *) exit 64 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def _private_install(
    root: Path, lock: bytes = b"PODS:\n  - Example (1.0)\n"
) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    podfile_lock = root / "Podfile.lock"
    podfile_lock.write_bytes(lock)
    podfile = root / "Podfile"
    podfile.write_text("platform :ios, '16.0'\n", encoding="utf-8")
    podspec = root / "vendor/plugins/local/ios/local.podspec"
    podspec.parent.mkdir(parents=True)
    podspec.write_text("Pod::Spec.new { |s| s.name = 'local' }\n", encoding="utf-8")
    pods = root / "private-install/Pods"
    home = root / "private-install/cp-home"
    cache = root / "private-install/cp-cache"
    (pods / "Framework/Versions/A/Headers").mkdir(parents=True)
    (pods / "Framework/Versions/A/Headers/Example.h").write_text(
        "void example(void);\n", encoding="utf-8"
    )
    (pods / "Framework/Versions/Current").symlink_to("A")
    (pods / "Framework/Headers").symlink_to("Versions/Current/Headers")
    (pods / "Manifest.lock").write_bytes(lock)
    project = pods / "Pods.xcodeproj/project.pbxproj"
    project.parent.mkdir(parents=True)
    project.write_text(
        "// !$*UTF8*$!\n"
        "{\n"
        "  archiveVersion = 1;\n"
        "  classes = {};\n"
        "  objectVersion = 56;\n"
        "  objects = {};\n"
        "  rootObject = 000000000000000000000000;\n"
        "}\n",
        encoding="utf-8",
    )
    (home / "repos/trunk").mkdir(parents=True)
    (home / "repos/trunk/all_pods_versions.txt").write_text(
        "Example/1.0\n", encoding="utf-8"
    )
    (cache / "Pods/Release/Example/1.0").mkdir(parents=True)
    (cache / "Pods/Release/Example/1.0/archive.json").write_text(
        '{"checksum":"exact"}\n', encoding="utf-8"
    )
    return {
        "lock": podfile_lock,
        "pods": pods,
        "home": home,
        "cache": cache,
        "podfile": podfile,
        "podspec": podspec,
    }


def _resolution_inputs(paths: dict[str, Path]) -> dict[str, Path]:
    return {
        "quwoquan_app/ios/Podfile": paths["podfile"],
        "quwoquan_app/vendor/plugins/local/ios/local.podspec": paths["podspec"],
    }


def _snapshot(root: Path, *, marker: str = "first"):
    paths = _private_install(root)
    pod = _pod_executable(root, marker=marker)
    snapshot = build_verified_ios_pod_snapshot(
        podfile_lock=paths["lock"],
        pods_root=paths["pods"],
        cp_home_dir=paths["home"],
        cp_cache_dir=paths["cache"],
        pod_executable=pod,
        resolution_inputs=_resolution_inputs(paths),
        upstream_dependency_digest=_UPSTREAM_DEPENDENCY_DIGEST,
    )
    return paths, pod, snapshot


def test_exact_capsule_roundtrip_and_private_projection(tmp_path: Path) -> None:
    paths, pod, snapshot = _snapshot(tmp_path)
    assert snapshot.manifest["schema"] == IOS_POD_CAPSULE_SCHEMA
    assert snapshot.manifest["nativeDependencyMode"] == "cocoapods"
    assert snapshot.manifest["cocoaPods"]["version"] == "1.16.2"
    assert snapshot.manifest["cocoaPods"]["runtimeEnvironmentDigest"].startswith(
        "sha256:"
    )
    symlinks = {
        entry["path"]: entry["target"]
        for entry in snapshot.manifest["entries"]
        if entry["kind"] == "symlink"
    }
    assert symlinks["pods/Framework/Versions/Current"] == "A"
    assert symlinks["pods/Framework/Headers"] == "Versions/Current/Headers"

    capsule = write_ios_pod_capsule(snapshot, tmp_path / "capsule")
    loaded = load_verified_ios_pod_capsule(
        snapshot_root=capsule,
        expected_podfile_lock=paths["lock"],
        pod_executable=pod,
        resolution_inputs=_resolution_inputs(paths),
        upstream_dependency_digest=_UPSTREAM_DEPENDENCY_DIGEST,
    )
    assert loaded.manifest == snapshot.manifest
    assert (capsule / "pods/Framework/Headers").is_symlink()
    assert not (capsule / "pods/Manifest.lock").stat().st_mode & 0o222

    ios_root = tmp_path / "workspace/quwoquan_app/ios"
    ios_root.mkdir(parents=True)
    (ios_root / "Podfile.lock").write_bytes(snapshot.lock_bytes)
    projection = materialize_ios_pod_projection(
        snapshot_root=capsule,
        ios_root=ios_root,
        private_state_root=tmp_path / "private-cocoapods",
        pod_executable=pod,
        resolution_inputs=_resolution_inputs(paths),
        upstream_dependency_digest=_UPSTREAM_DEPENDENCY_DIGEST,
    )
    assert projection.pods_root == ios_root / "Pods"
    assert (projection.pods_root / "Framework/Headers").resolve().is_dir()
    proxy_keys = {
        "ALL_PROXY",
        "all_proxy",
        "HTTP_PROXY",
        "http_proxy",
        "HTTPS_PROXY",
        "https_proxy",
        "NO_PROXY",
        "no_proxy",
    }
    environment = isolated_cocoapods_environment(
        base={
            "PATH": os.environ["PATH"],
            **dict.fromkeys(proxy_keys, "secret-proxy"),
            "FLUTTER_SWIFT_PACKAGE_MANAGER": "true",
        },
        projection=projection,
    )
    assert environment["CP_HOME_DIR"] == str(projection.cp_home_dir)
    assert environment["CP_CACHE_DIR"] == str(projection.cp_cache_dir)
    private_environment_directories = {
        "HOME": projection.private_home,
        "XDG_CONFIG_HOME": projection.private_home / ".config",
        "XDG_CACHE_HOME": projection.private_home / ".cache",
    }
    for key, expected in private_environment_directories.items():
        exported = Path(environment[key])
        assert exported == expected
        assert exported.is_dir()
        assert not exported.is_symlink()
        assert exported.stat().st_mode & 0o777 == 0o700
    assert proxy_keys.isdisjoint(environment)
    assert environment["FLUTTER_SWIFT_PACKAGE_MANAGER"] == "false"


def test_package_readback_is_tool_independent_and_host_typed(tmp_path: Path) -> None:
    paths, pod, snapshot = _snapshot(tmp_path)
    capsule = write_ios_pod_capsule(snapshot, tmp_path / "capsule")
    pod.unlink()

    loaded = load_ios_pod_capsule_bytes(
        snapshot_root=capsule,
        expected_podfile_lock=paths["lock"],
        resolution_inputs=_resolution_inputs(paths),
        upstream_dependency_digest=_UPSTREAM_DEPENDENCY_DIGEST,
        dependency_host=IOS_POD_PRODUCTION_HOST,
    )

    assert loaded.cocoa_pods.executable is None
    assert loaded.manifest == snapshot.manifest
    assert IOS_POD_DEPENDENCY_LOGICAL_PATHS == {
        "production": "dependency:production-ios-cocoapods-v2",
        "patrol": "dependency:patrol-host-ios-cocoapods-v2",
    }
    assert (
        IOS_POD_DEPENDENCY_DIRECTORIES[IOS_POD_PRODUCTION_HOST]
        != (IOS_POD_DEPENDENCY_DIRECTORIES[IOS_POD_PATROL_HOST])
    )
    with pytest.raises(ValueError, match="dependency host drifted"):
        load_ios_pod_capsule_bytes(
            snapshot_root=capsule,
            expected_podfile_lock=paths["lock"],
            resolution_inputs=_resolution_inputs(paths),
            upstream_dependency_digest=_UPSTREAM_DEPENDENCY_DIGEST,
            dependency_host=IOS_POD_PATROL_HOST,
        )


def test_materialize_accepts_run_and_package_private_state_layouts(
    tmp_path: Path,
) -> None:
    paths, pod, snapshot = _snapshot(tmp_path / "producer")
    capsule = write_ios_pod_capsule(snapshot, tmp_path / "capsule")
    layouts = (
        (
            tmp_path / "run-layout/quwoquan_app/ios",
            tmp_path
            / "run-layout/quwoquan_app/.dart_tool/qwq_ios_cocoapods_dependency/production",
            tmp_path / "run-layout/quwoquan_app",
        ),
        (
            tmp_path / "package-layout/repo/quwoquan_app/ios",
            tmp_path / "package-layout/dependencies/production",
            tmp_path / "package-layout",
        ),
    )
    for ios_root, private_state, expected_root in layouts:
        ios_root.mkdir(parents=True)
        (ios_root / "Podfile.lock").write_bytes(snapshot.lock_bytes)
        projection = materialize_ios_pod_projection(
            snapshot_root=capsule,
            ios_root=ios_root,
            private_state_root=private_state,
            pod_executable=pod,
            resolution_inputs=_resolution_inputs(paths),
            upstream_dependency_digest=_UPSTREAM_DEPENDENCY_DIGEST,
        )
        assert projection.projection_root == expected_root.resolve()
        assert projection.pods_root == ios_root / "Pods"


def test_package_readback_rejects_writable_capsule_bytes(tmp_path: Path) -> None:
    paths, _pod, snapshot = _snapshot(tmp_path)
    capsule = write_ios_pod_capsule(snapshot, tmp_path / "capsule")
    changed = capsule / "pods/Framework/Versions/A/Headers/Example.h"
    changed.chmod(0o644)

    with pytest.raises(ValueError, match="writable bytes"):
        load_ios_pod_capsule_bytes(
            snapshot_root=capsule,
            expected_podfile_lock=paths["lock"],
            resolution_inputs=_resolution_inputs(paths),
            upstream_dependency_digest=_UPSTREAM_DEPENDENCY_DIGEST,
        )


def test_symlink_target_must_remain_inside_component(tmp_path: Path) -> None:
    paths = _private_install(tmp_path)
    (paths["pods"] / "escape").symlink_to("../../outside")
    with pytest.raises(ValueError, match="symlink escapes capsule"):
        build_verified_ios_pod_snapshot(
            podfile_lock=paths["lock"],
            pods_root=paths["pods"],
            cp_home_dir=paths["home"],
            cp_cache_dir=paths["cache"],
            pod_executable=_pod_executable(tmp_path),
            resolution_inputs=_resolution_inputs(paths),
            upstream_dependency_digest=_UPSTREAM_DEPENDENCY_DIGEST,
        )


def test_hardlink_and_special_node_are_rejected(tmp_path: Path) -> None:
    hardlink_root = tmp_path / "hardlink"
    paths = _private_install(hardlink_root)
    source = paths["cache"] / "Pods/Release/Example/1.0/archive.json"
    os.link(source, source.with_name("duplicate.json"))
    with pytest.raises(ValueError, match="unique regular file"):
        build_verified_ios_pod_snapshot(
            podfile_lock=paths["lock"],
            pods_root=paths["pods"],
            cp_home_dir=paths["home"],
            cp_cache_dir=paths["cache"],
            pod_executable=_pod_executable(hardlink_root),
            resolution_inputs=_resolution_inputs(paths),
            upstream_dependency_digest=_UPSTREAM_DEPENDENCY_DIGEST,
        )

    special_root = tmp_path / "special"
    paths = _private_install(special_root)
    os.mkfifo(paths["home"] / "unexpected.fifo")
    with pytest.raises(ValueError, match="special node"):
        build_verified_ios_pod_snapshot(
            podfile_lock=paths["lock"],
            pods_root=paths["pods"],
            cp_home_dir=paths["home"],
            cp_cache_dir=paths["cache"],
            pod_executable=_pod_executable(special_root),
            resolution_inputs=_resolution_inputs(paths),
            upstream_dependency_digest=_UPSTREAM_DEPENDENCY_DIGEST,
        )


def test_lock_tool_and_capsule_extra_byte_drift_fail_closed(tmp_path: Path) -> None:
    paths, pod, snapshot = _snapshot(tmp_path)
    capsule = write_ios_pod_capsule(snapshot, tmp_path / "capsule")
    paths["lock"].write_bytes(b"PODS:\n  - Changed (2.0)\n")
    with pytest.raises(ValueError, match="stale for current Podfile.lock"):
        load_verified_ios_pod_capsule(
            snapshot_root=capsule,
            expected_podfile_lock=paths["lock"],
            pod_executable=pod,
            resolution_inputs=_resolution_inputs(paths),
            upstream_dependency_digest=_UPSTREAM_DEPENDENCY_DIGEST,
        )
    paths["lock"].write_bytes(snapshot.lock_bytes)

    _pod_executable(tmp_path, marker="changed-tool-bytes")
    with pytest.raises(ValueError, match="CocoaPods tool identity drifted"):
        load_verified_ios_pod_capsule(
            snapshot_root=capsule,
            expected_podfile_lock=paths["lock"],
            pod_executable=pod,
            resolution_inputs=_resolution_inputs(paths),
            upstream_dependency_digest=_UPSTREAM_DEPENDENCY_DIGEST,
        )

    _pod_executable(tmp_path)
    paths["podfile"].write_text("platform :ios, '17.0'\n", encoding="utf-8")
    with pytest.raises(ValueError, match="resolution input"):
        load_verified_ios_pod_capsule(
            snapshot_root=capsule,
            expected_podfile_lock=paths["lock"],
            pod_executable=pod,
            resolution_inputs=_resolution_inputs(paths),
            upstream_dependency_digest=_UPSTREAM_DEPENDENCY_DIGEST,
        )
    paths["podfile"].write_text("platform :ios, '16.0'\n", encoding="utf-8")
    paths["podspec"].write_text(
        "Pod::Spec.new { |s| s.name = 'changed' }\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="resolution input"):
        load_verified_ios_pod_capsule(
            snapshot_root=capsule,
            expected_podfile_lock=paths["lock"],
            pod_executable=pod,
            resolution_inputs=_resolution_inputs(paths),
            upstream_dependency_digest=_UPSTREAM_DEPENDENCY_DIGEST,
        )
    paths["podspec"].write_text(
        "Pod::Spec.new { |s| s.name = 'local' }\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="resolution input"):
        load_verified_ios_pod_capsule(
            snapshot_root=capsule,
            expected_podfile_lock=paths["lock"],
            pod_executable=pod,
            resolution_inputs=_resolution_inputs(paths),
            upstream_dependency_digest="sha256:" + "2" * 64,
        )
    capsule.chmod(0o755)
    (capsule / "undeclared").write_text("drift", encoding="utf-8")
    with pytest.raises(ValueError, match="undeclared top-level bytes"):
        load_verified_ios_pod_capsule(
            snapshot_root=capsule,
            expected_podfile_lock=paths["lock"],
            pod_executable=pod,
            resolution_inputs=_resolution_inputs(paths),
            upstream_dependency_digest=_UPSTREAM_DEPENDENCY_DIGEST,
        )


def test_cocoapods_must_self_report_the_same_executable(tmp_path: Path) -> None:
    pod = _pod_executable(tmp_path)
    content = pod.read_text(encoding="utf-8").replace(
        'SELF="$(cd "$(dirname "$0")" && pwd -P)/$(basename "$0")"',
        "SELF='/different/pod'",
    )
    pod.write_text(content, encoding="utf-8")
    pod.chmod(0o755)
    with pytest.raises(ValueError, match="reported CocoaPods executable is invalid"):
        inspect_cocoapods_executable(pod)


def test_manifest_tool_identity_is_portable_across_executable_paths(
    tmp_path: Path,
) -> None:
    paths, pod, snapshot = _snapshot(tmp_path / "producer")
    assert "executablePath" not in snapshot.manifest["cocoaPods"]
    capsule = write_ios_pod_capsule(snapshot, tmp_path / "capsule")
    relocated = tmp_path / "consumer/bin/pod"
    relocated.parent.mkdir(parents=True)
    relocated.write_bytes(pod.read_bytes())
    relocated.chmod(0o755)
    loaded = load_verified_ios_pod_capsule(
        snapshot_root=capsule,
        expected_podfile_lock=paths["lock"],
        pod_executable=relocated,
        resolution_inputs=_resolution_inputs(paths),
        upstream_dependency_digest=_UPSTREAM_DEPENDENCY_DIGEST,
    )
    assert loaded.manifest == snapshot.manifest
    assert loaded.cocoa_pods.executable == relocated.resolve()


def test_install_command_is_network_denied_and_never_updates_repos(
    tmp_path: Path,
) -> None:
    _paths, pod, snapshot = _snapshot(tmp_path, marker="project-once")
    capsule = write_ios_pod_capsule(snapshot, tmp_path / "capsule")
    ios_root = tmp_path / "workspace/quwoquan_app/ios"
    ios_root.mkdir(parents=True)
    (ios_root / "Podfile.lock").write_bytes(snapshot.lock_bytes)
    projection = materialize_ios_pod_projection(
        snapshot_root=capsule,
        ios_root=ios_root,
        private_state_root=tmp_path / "private-cocoapods",
        pod_executable=pod,
        resolution_inputs=_resolution_inputs(_paths),
        upstream_dependency_digest=_UPSTREAM_DEPENDENCY_DIGEST,
    )
    command = cocoapods_network_denied_command(pod)
    assert command[0] == "/usr/bin/sandbox-exec"
    assert "(deny network*)" in command[2]
    assert command[-3:] == ["install", "--deployment", "--no-repo-update"]

    result = run_offline_cocoapods_install(
        projection=projection,
        pod_executable=pod,
        base_environment={"PATH": os.environ["PATH"], "HTTP_PROXY": "ignored"},
    )
    assert result.command == tuple(command)
    assert result.second_command == tuple(command)
    assert result.first_exit_code == result.second_exit_code == 0
    assert result.stdout.strip() == "project-once"
    assert result.second_stdout.strip() == "project-once"
    assert result.output_snapshot.lock_bytes == snapshot.lock_bytes
    assert result.seed_project_digest != result.projected_project_digest
    assert result.converged_tree_digest.startswith("sha256:")
    assert result.evidence_manifest["seedProjectDigest"] == (result.seed_project_digest)
    assert result.evidence_manifest["projectedProjectDigest"] == (
        result.projected_project_digest
    )
    assert result.evidence_manifest["convergedTreeDigest"] == (
        result.converged_tree_digest
    )
    assert [
        attempt["exitCode"] for attempt in result.evidence_manifest["attempts"]
    ] == [
        0,
        0,
    ]


def test_offline_install_ignores_generated_xcode_user_state(
    tmp_path: Path,
) -> None:
    paths, pod, snapshot = _snapshot(tmp_path, marker="xcode-user-state")
    capsule = write_ios_pod_capsule(snapshot, tmp_path / "capsule")
    ios_root = tmp_path / "workspace/quwoquan_app/ios"
    ios_root.mkdir(parents=True)
    (ios_root / "Podfile.lock").write_bytes(snapshot.lock_bytes)
    projection = materialize_ios_pod_projection(
        snapshot_root=capsule,
        ios_root=ios_root,
        private_state_root=tmp_path / "private-cocoapods",
        pod_executable=pod,
        resolution_inputs=_resolution_inputs(paths),
        upstream_dependency_digest=_UPSTREAM_DEPENDENCY_DIGEST,
    )

    result = run_offline_cocoapods_install(
        projection=projection,
        pod_executable=pod,
        base_environment={"PATH": os.environ["PATH"]},
    )

    assert result.first_exit_code == result.second_exit_code == 0
    assert (
        projection.pods_root
        / "Pods.xcodeproj/xcuserdata/tester.xcuserdatad/xcschememanagement.plist"
    ).is_file()


def test_offline_install_rejects_pods_output_drift_even_when_lock_is_same(
    tmp_path: Path,
) -> None:
    paths, pod, snapshot = _snapshot(tmp_path, marker="mutate-pods")
    capsule = write_ios_pod_capsule(snapshot, tmp_path / "capsule")
    ios_root = tmp_path / "workspace/quwoquan_app/ios"
    ios_root.mkdir(parents=True)
    (ios_root / "Podfile.lock").write_bytes(snapshot.lock_bytes)
    projection = materialize_ios_pod_projection(
        snapshot_root=capsule,
        ios_root=ios_root,
        private_state_root=tmp_path / "private-cocoapods",
        pod_executable=pod,
        resolution_inputs=_resolution_inputs(paths),
        upstream_dependency_digest=_UPSTREAM_DEPENDENCY_DIGEST,
    )
    with pytest.raises(ValueError, match="changed sealed Pods payload outside"):
        run_offline_cocoapods_install(
            projection=projection,
            pod_executable=pod,
            base_environment={"PATH": os.environ["PATH"]},
        )


def test_offline_install_rejects_project_that_never_converges(
    tmp_path: Path,
) -> None:
    paths, pod, snapshot = _snapshot(tmp_path, marker="project-always")
    capsule = write_ios_pod_capsule(snapshot, tmp_path / "capsule")
    ios_root = tmp_path / "workspace/quwoquan_app/ios"
    ios_root.mkdir(parents=True)
    (ios_root / "Podfile.lock").write_bytes(snapshot.lock_bytes)
    projection = materialize_ios_pod_projection(
        snapshot_root=capsule,
        ios_root=ios_root,
        private_state_root=tmp_path / "private-cocoapods",
        pod_executable=pod,
        resolution_inputs=_resolution_inputs(paths),
        upstream_dependency_digest=_UPSTREAM_DEPENDENCY_DIGEST,
    )
    with pytest.raises(ValueError, match="did not converge exact Pods component"):
        run_offline_cocoapods_install(
            projection=projection,
            pod_executable=pod,
            base_environment={"PATH": os.environ["PATH"]},
        )


def test_offline_install_does_not_treat_generic_seed_segment_as_path_leak(
    tmp_path: Path,
) -> None:
    paths, pod, snapshot = _snapshot(tmp_path, marker="project-generic-segment")
    capsule = write_ios_pod_capsule(snapshot, tmp_path / "dependencies/capsule")
    ios_root = tmp_path / "workspace/quwoquan_app/ios"
    ios_root.mkdir(parents=True)
    (ios_root / "Podfile.lock").write_bytes(snapshot.lock_bytes)
    projection = materialize_ios_pod_projection(
        snapshot_root=capsule,
        ios_root=ios_root,
        private_state_root=tmp_path / "private-cocoapods",
        pod_executable=pod,
        resolution_inputs=_resolution_inputs(paths),
        upstream_dependency_digest=_UPSTREAM_DEPENDENCY_DIGEST,
    )

    result = run_offline_cocoapods_install(
        projection=projection,
        pod_executable=pod,
        base_environment={"PATH": os.environ["PATH"]},
    )

    assert result.first_exit_code == result.second_exit_code == 0


def test_offline_install_allows_explicit_flutter_toolchain_root(
    tmp_path: Path,
) -> None:
    paths, pod, snapshot = _snapshot(tmp_path, marker="project-flutter-toolchain")
    capsule = write_ios_pod_capsule(snapshot, tmp_path / "dependencies/capsule")
    ios_root = tmp_path / "workspace/quwoquan_app/ios"
    ios_root.mkdir(parents=True)
    (ios_root / "Podfile.lock").write_bytes(snapshot.lock_bytes)
    flutter = tmp_path / "toolchain/flutter/bin/flutter"
    flutter.parent.mkdir(parents=True)
    flutter.write_text("#!/bin/sh\n", encoding="utf-8")
    flutter.chmod(0o755)
    projection = materialize_ios_pod_projection(
        snapshot_root=capsule,
        ios_root=ios_root,
        private_state_root=tmp_path / "private-cocoapods",
        pod_executable=pod,
        resolution_inputs=_resolution_inputs(paths),
        upstream_dependency_digest=_UPSTREAM_DEPENDENCY_DIGEST,
    )

    result = run_offline_cocoapods_install(
        projection=projection,
        pod_executable=pod,
        base_environment={
            "PATH": os.environ["PATH"],
            "QWQ_REAL_FLUTTER": str(flutter),
            "FLUTTER_ROOT": str(flutter.parent.parent),
        },
    )

    assert result.first_exit_code == result.second_exit_code == 0


def test_offline_install_rejects_external_project_path(tmp_path: Path) -> None:
    paths, pod, snapshot = _snapshot(tmp_path, marker="project-leak")
    capsule = write_ios_pod_capsule(snapshot, tmp_path / "capsule")
    ios_root = tmp_path / "workspace/quwoquan_app/ios"
    ios_root.mkdir(parents=True)
    (ios_root / "Podfile.lock").write_bytes(snapshot.lock_bytes)
    projection = materialize_ios_pod_projection(
        snapshot_root=capsule,
        ios_root=ios_root,
        private_state_root=tmp_path / "private-cocoapods",
        pod_executable=pod,
        resolution_inputs=_resolution_inputs(paths),
        upstream_dependency_digest=_UPSTREAM_DEPENDENCY_DIGEST,
    )
    with pytest.raises(ValueError, match="external absolute path"):
        run_offline_cocoapods_install(
            projection=projection,
            pod_executable=pod,
            base_environment={"PATH": os.environ["PATH"]},
        )
