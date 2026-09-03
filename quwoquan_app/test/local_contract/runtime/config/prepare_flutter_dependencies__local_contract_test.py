"""Canonical launch dependency projection is private and replayed before build."""

# spec_ref: specs/feature-tree/runtime/runtime-config/design.md#dec-003

from __future__ import annotations

import os
import shlex
from pathlib import Path
from types import SimpleNamespace

import pytest

from quwoquan_app.scripts.device import prepare_flutter_dependencies as prepare
from quwoquan_ops.cli.lib.app_dependency_toolchain import (
    ResolvedCocoaPodsIdentity,
    cocoapods_environment,
)
from quwoquan_ops.cli.lib.package_reuse.ios_pod_identity import CocoaPodsIdentity
from quwoquan_app.scripts.device import verify_flutter_dependencies as verify


def test_pub_get_is_offline_locked_and_does_not_resolve_examples(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def run(command, **kwargs):
        calls.append((list(command), dict(kwargs)))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(prepare.subprocess, "run", run)
    package_root = tmp_path / "quwoquan_app/test_host/patrol"
    environment = {"PUB_CACHE": "/private/patrol-pub"}

    prepare._run_pub_get(
        flutter="/canonical/flutter",
        package_root=package_root,
        environment=environment,
    )

    assert calls[0][0] == [
        "/canonical/flutter",
        "pub",
        "get",
        "--offline",
        "--enforce-lockfile",
        "--no-example",
    ]
    assert calls[0][1]["cwd"] == package_root
    assert calls[0][1]["env"] == environment


def test_projected_pub_gets_include_patrol_only_when_explicitly_requested(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Path, dict[str, str]]] = []

    def pub_get(*, package_root, environment, **_kwargs):
        calls.append((package_root, dict(environment)))

    monkeypatch.setattr(prepare, "_run_pub_get", pub_get)
    projection = SimpleNamespace(
        production_environment={"HOST": "production"},
        patrol_environment={"HOST": "patrol"},
    )

    prepare._run_projected_pub_gets(
        flutter="/canonical/flutter",
        projection_root=tmp_path,
        dependency_projection=projection,
        include_patrol=False,
    )
    assert calls == [
        (tmp_path / "quwoquan_app", {"HOST": "production"}),
    ]

    calls.clear()
    prepare._run_projected_pub_gets(
        flutter="/canonical/flutter",
        projection_root=tmp_path,
        dependency_projection=projection,
        include_patrol=True,
    )
    assert calls == [
        (tmp_path / "quwoquan_app", {"HOST": "production"}),
        (tmp_path / "quwoquan_app/test_host/patrol", {"HOST": "patrol"}),
    ]


@pytest.mark.parametrize(
    ("platform", "removed_relpaths", "preserved_relpaths"),
    [
        (
            "ios",
            ("android/local.properties",),
            (
                "ios/Flutter/Generated.xcconfig",
                "ios/Flutter/flutter_export_environment.sh",
            ),
        ),
        (
            "android",
            (
                "ios/Flutter/Generated.xcconfig",
                "ios/Flutter/flutter_export_environment.sh",
            ),
            ("android/local.properties",),
        ),
    ],
)
def test_prune_cross_platform_generated_tooling_removes_only_non_target_hosts(
    tmp_path: Path,
    platform: str,
    removed_relpaths: tuple[str, ...],
    preserved_relpaths: tuple[str, ...],
) -> None:
    hosts = (
        tmp_path / "quwoquan_app",
        tmp_path / "quwoquan_app/test_host/patrol",
    )
    for host in hosts:
        for relative_path in (*removed_relpaths, *preserved_relpaths):
            generated = host / relative_path
            generated.parent.mkdir(parents=True, exist_ok=True)
            generated.write_text(f"generated:{relative_path}", encoding="utf-8")

    prepare._prune_cross_platform_generated_tooling(
        projection_root=tmp_path,
        platform=platform,
        include_patrol=True,
    )

    for host in hosts:
        for relative_path in removed_relpaths:
            assert not (host / relative_path).exists()
        for relative_path in preserved_relpaths:
            assert (host / relative_path).read_text(encoding="utf-8") == (
                f"generated:{relative_path}"
            )


@pytest.mark.parametrize("platform", ["ios", "android"])
@pytest.mark.parametrize("include_patrol", [False, True])
def test_prune_cross_platform_generated_tooling_is_idempotent_when_absent(
    tmp_path: Path,
    platform: str,
    include_patrol: bool,
) -> None:
    for _ in range(2):
        prepare._prune_cross_platform_generated_tooling(
            projection_root=tmp_path,
            platform=platform,
            include_patrol=include_patrol,
        )


@pytest.mark.parametrize(
    ("platform", "relative_path"),
    [
        ("ios", "android/local.properties"),
        ("android", "ios/Flutter/Generated.xcconfig"),
    ],
)
@pytest.mark.parametrize("node_kind", ["symlink", "directory"])
def test_prune_cross_platform_generated_tooling_rejects_non_regular_nodes(
    tmp_path: Path,
    platform: str,
    relative_path: str,
    node_kind: str,
) -> None:
    generated = tmp_path / "quwoquan_app" / relative_path
    generated.parent.mkdir(parents=True, exist_ok=True)
    sentinel = tmp_path / "sentinel"
    sentinel.write_text("must remain", encoding="utf-8")
    if node_kind == "symlink":
        generated.symlink_to(sentinel)
    else:
        generated.mkdir()

    with pytest.raises(
        ValueError,
        match="APP\\.DEPENDENCY\\.cross_platform_generated_tooling_unsafe",
    ):
        prepare._prune_cross_platform_generated_tooling(
            projection_root=tmp_path,
            platform=platform,
            include_patrol=False,
        )

    assert sentinel.read_text(encoding="utf-8") == "must remain"
    assert generated.is_symlink() if node_kind == "symlink" else generated.is_dir()


def test_prune_cross_platform_generated_tooling_rejects_symlinked_parent(
    tmp_path: Path,
) -> None:
    external = tmp_path / "external"
    external.mkdir()
    sentinel = external / "local.properties"
    sentinel.write_text("must remain", encoding="utf-8")
    package_root = tmp_path / "quwoquan_app"
    package_root.mkdir()
    (package_root / "android").symlink_to(external, target_is_directory=True)

    with pytest.raises(
        ValueError,
        match="APP\\.DEPENDENCY\\.cross_platform_generated_tooling_unsafe",
    ):
        prepare._prune_cross_platform_generated_tooling(
            projection_root=tmp_path,
            platform="ios",
            include_patrol=False,
        )

    assert sentinel.read_text(encoding="utf-8") == "must remain"


def test_run_sh_requests_patrol_projection_only_for_canonical_uat_actor() -> None:
    repo_root = Path(__file__).resolve().parents[5]
    source = (repo_root / "quwoquan_app/run.sh").read_text(encoding="utf-8")
    branch_start = source.index('DEPENDENCY_PATROL_ARGUMENT=""')
    invocation_end = source.index(')"; then', branch_start)
    dependency_block = source[branch_start:invocation_end]

    assert (
        'if [[ "${QWQ_CANONICAL_LAUNCH_ACTOR:-}" == "app-content-uat" ]]'
        in dependency_block
    )
    assert 'DEPENDENCY_PATROL_ARGUMENT="--include-patrol"' in dependency_block
    assert (
        '${DEPENDENCY_PATROL_ARGUMENT:+"$DEPENDENCY_PATROL_ARGUMENT"}'
        in dependency_block
    )


def _pod_identity(executable: Path) -> ResolvedCocoaPodsIdentity:
    return ResolvedCocoaPodsIdentity(
        physical=CocoaPodsIdentity(
            executable=executable,
            version="1.16.2",
            executable_digest="sha256:" + "1" * 64,
            runtime_environment_digest="sha256:" + "2" * 64,
            command_resolution_digest="sha256:" + "3" * 64,
        ),
        binding_seal="sha256:" + "4" * 64,
    )


def test_cocoapods_environment_prepends_exact_directory_and_deduplicates(
    tmp_path: Path,
) -> None:
    pod = tmp_path / "exact/bin/pod"
    pod.parent.mkdir(parents=True)
    pod.write_text("#!/bin/sh\n", encoding="utf-8")
    pod.chmod(0o755)
    identity = _pod_identity(pod)

    environment = cocoapods_environment(
        identity,
        base={"PATH": os.pathsep.join(("/hostile", str(pod.parent), "/usr/bin"))},
    )

    assert environment["PATH"].split(os.pathsep) == [
        str(pod.parent),
        "/hostile",
        "/usr/bin",
    ]
    for key, value in identity.as_environment().items():
        assert environment[key] == value


def test_shell_exports_include_complete_cocoapods_binding_and_final_path(
    tmp_path: Path,
) -> None:
    pod = tmp_path / "exact/bin/pod"
    pod.parent.mkdir(parents=True)
    pod.write_text("#!/bin/sh\n", encoding="utf-8")
    pod.chmod(0o755)
    identity = _pod_identity(pod)
    environment = cocoapods_environment(identity, base={"PATH": "/usr/bin"})

    parsed: dict[str, str] = {}
    for line in prepare._shell_exports(environment).splitlines():
        if line.startswith("export "):
            key, value = line[len("export ") :].split("=", 1)
            parsed[key] = shlex.split(value)[0]

    assert {key: parsed[key] for key in identity.as_environment()} == (
        identity.as_environment()
    )
    assert parsed["PATH"].split(os.pathsep)[0] == str(pod.parent)


def test_shell_exports_only_dependency_controls_and_removes_proxies() -> None:
    exports = prepare._shell_exports(
        {
            "PUB_CACHE": "/private/pub",
            "GRADLE_USER_HOME": "/private/gradle",
            "SECRET": "must-not-leak",
        }
    )

    assert exports.startswith("unset ALL_PROXY all_proxy HTTP_PROXY")
    assert "export PUB_CACHE=/private/pub" in exports
    assert "export GRADLE_USER_HOME=/private/gradle" in exports
    assert "SECRET" not in exports
    assert "must-not-leak" not in exports


def test_ios_shell_exports_preserve_complete_private_cocoapods_environment() -> None:
    environment = {
        "PUB_CACHE": "/private/pub",
        "FLUTTER_SWIFT_PACKAGE_MANAGER": "false",
        "CP_HOME_DIR": "/private/pods/home",
        "CP_CACHE_DIR": "/private/pods/cache",
        "COCOAPODS_HOME": "/private/pods/home",
        "HOME": "/private/pods/user-home",
        "XDG_CONFIG_HOME": "/private/pods/user-home/.config",
        "XDG_CACHE_HOME": "/private/pods/user-home/.cache",
        "COCOAPODS_DISABLE_STATS": "true",
        "COCOAPODS_SKIP_UPDATE_MESSAGE": "true",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }

    exports = prepare._shell_exports(environment)

    for key, value in environment.items():
        assert f"export {key}={value}" in exports


def test_ios_uat_main_projects_both_pub_hosts_then_replays_both_pod_hosts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # 宿主终端投影可能携带 QWQ_*（CocoaPods/Flutter 身份），必须隔离，
    # 否则 main() 会走 environment-identity 分支与 fixture 身份冲突。
    for key in list(os.environ):
        if key.startswith("QWQ_"):
            monkeypatch.delenv(key, raising=False)
    order: list[str] = []
    monkeypatch.setattr(prepare, "_platform", lambda _device: "ios")
    pod = tmp_path / "canonical/pod"
    pod.parent.mkdir(parents=True)
    pod.write_text("fixture", encoding="utf-8")
    pod.chmod(0o755)
    pod_identity = _pod_identity(pod)
    environment = cocoapods_environment(
        pod_identity,
        base={
            "PUB_CACHE": str(tmp_path / "pub"),
            "FLUTTER_SWIFT_PACKAGE_MANAGER": "false",
            "PATH": "/usr/bin",
        },
    )
    dependency_projection = SimpleNamespace(
        production_environment=environment,
        patrol_environment=cocoapods_environment(
            pod_identity,
            base={
                "PUB_CACHE": str(tmp_path / "patrol-pub"),
                "FLUTTER_SWIFT_PACKAGE_MANAGER": "false",
                "PATH": "/usr/bin",
            },
        ),
    )
    monkeypatch.setattr(
        prepare,
        "resolve_cocoapods_identity",
        lambda _pod, search_path=None: pod_identity,
    )
    flutter = tmp_path / "canonical/flutter"
    flutter.parent.mkdir(parents=True, exist_ok=True)
    flutter.write_text("fixture", encoding="utf-8")

    def materialize(**kwargs):
        assert kwargs["include_patrol"] is True
        assert kwargs["replay_ios"] is False
        order.append("project")
        return dependency_projection

    def pub_get(**kwargs):
        package_root = kwargs["package_root"]
        order.append(
            "pub-patrol" if package_root.name == "patrol" else "pub-production"
        )

    def prune(**kwargs):
        assert kwargs == {
            "projection_root": tmp_path / "repo",
            "platform": "ios",
            "include_patrol": True,
        }
        order.append("prune")

    def pod_replay(**_kwargs):
        order.append("pod")
        return ()

    def assert_cocoapods_only(_root):
        order.append("spm")

    expectation = SimpleNamespace(
        evidence_path=tmp_path / "private/dependency-projection-expectation.json",
        evidence_digest="sha256:" + "1" * 64,
    )
    observed_components = {"productionPub": {"treeDigest": "captured"}}
    prepared_evidence = SimpleNamespace(
        expectation=expectation,
        observed_components=observed_components,
    )
    prebuild_readback = SimpleNamespace()
    prebuild_evidence = SimpleNamespace(
        evidence_path=tmp_path / "private/dependency-projection-prebuild-readback.json",
        evidence_digest="sha256:" + "2" * 64,
    )

    def prepare_evidence(**_kwargs):
        assert _kwargs["dependency_projection"] is dependency_projection
        assert dependency_projection.patrol_environment is not None
        order.append("expectation")
        return prepared_evidence

    def initial_readback(**kwargs):
        assert kwargs["expectation"] is expectation
        assert kwargs["observed_components"] is observed_components
        order.append("readback")
        return prebuild_readback

    def write_readback(**_kwargs):
        order.append("write")
        return prebuild_evidence

    def load_readback(**_kwargs):
        order.append("load")
        return prebuild_evidence

    monkeypatch.setattr(
        prepare, "materialize_dependency_bundle_projection", materialize
    )
    monkeypatch.setattr(prepare, "_run_pub_get", pub_get)
    monkeypatch.setattr(prepare, "_prune_cross_platform_generated_tooling", prune)
    monkeypatch.setattr(prepare, "replay_ios_dependency_projections", pod_replay)
    monkeypatch.setattr(
        prepare,
        "_assert_cocoapods_only_ios_project",
        assert_cocoapods_only,
    )
    monkeypatch.setattr(
        prepare,
        "prepare_dependency_projection_cas_evidence_with_observed_components",
        prepare_evidence,
    )
    monkeypatch.setattr(prepare, "readback_from_expectation", initial_readback)
    monkeypatch.setattr(
        prepare,
        "write_dependency_projection_cas_readback",
        write_readback,
    )
    monkeypatch.setattr(
        prepare,
        "load_dependency_projection_cas_readback",
        load_readback,
    )

    result = prepare.main(
        [
            "--source-capsule-manifest",
            str(tmp_path / "capsule/manifest.json"),
            "--projection-root",
            str(tmp_path / "repo"),
            "--private-state-root",
            str(tmp_path / "private"),
            "--device",
            "ios-fixture",
            "--flutter",
            str(flutter),
            "--pod",
            str(pod),
            "--include-patrol",
        ]
    )

    assert result == 0
    assert order == [
        "project",
        "pub-production",
        "pub-patrol",
        "pod",
        "spm",
        "prune",
        "expectation",
        "readback",
        "write",
        "load",
    ]
    stdout = capsys.readouterr().out
    assert "export FLUTTER_SWIFT_PACKAGE_MANAGER=false" in stdout
    assert f"export QWQ_COCOAPODS_EXECUTABLE={pod}" in stdout
    assert "export QWQ_COCOAPODS_BINDING_SEAL=sha256:" in stdout
    assert f"export PATH={pod.parent}" in stdout
    assert (
        "export QWQ_DEPENDENCY_PROJECTION_EXPECTATION_DIGEST="
        + expectation.evidence_digest
        in stdout
    )
    assert (
        "export QWQ_DEPENDENCY_PROJECTION_PREBUILD_READBACK_DIGEST="
        + prebuild_evidence.evidence_digest
        in stdout
    )


def test_ios_project_rejects_generated_spm_residue(tmp_path: Path) -> None:
    project = tmp_path / "quwoquan_app/ios/Runner.xcodeproj/project.pbxproj"
    project.parent.mkdir(parents=True)
    project.write_text("// CocoaPods only\n", encoding="utf-8")

    prepare._assert_cocoapods_only_ios_project(tmp_path)

    project.write_text("XCLocalSwiftPackageReference\n", encoding="utf-8")
    with pytest.raises(ValueError, match="flutter_spm_residue_forbidden"):
        prepare._assert_cocoapods_only_ios_project(tmp_path)


@pytest.mark.parametrize("phase", ["prebuild", "postbuild"])
def test_command_verifier_revalidates_persists_and_reloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    phase: str,
) -> None:
    calls: list[str] = []
    readback = SimpleNamespace()
    evidence = SimpleNamespace(
        evidence_path=tmp_path / "postbuild.json",
        evidence_digest="sha256:" + "3" * 64,
        manifest={"schema": "readback"},
    )

    def revalidate(**kwargs):
        calls.append("revalidate")
        assert kwargs["command_environment_owner"] == "production"
        assert isinstance(kwargs["command_environment"], dict)
        return readback

    def write(**kwargs):
        calls.append("write")
        assert kwargs["readback"] is readback
        return evidence

    def load(**kwargs):
        calls.append("load")
        assert kwargs["expected_expectation_digest"] == "sha256:" + "1" * 64
        return evidence

    monkeypatch.setattr(verify, "revalidate_dependency_projection_cas", revalidate)
    monkeypatch.setattr(verify, "write_dependency_projection_cas_readback", write)
    monkeypatch.setattr(verify, "load_dependency_projection_cas_readback", load)

    result = verify.main(
        [
            "--projection-root",
            str(tmp_path / "projection"),
            "--expectation",
            str(tmp_path / "expectation.json"),
            "--expectation-digest",
            "sha256:" + "1" * 64,
            "--readback-output",
            str(evidence.evidence_path),
            "--phase",
            phase,
        ]
    )

    assert result == 0
    assert calls == ["revalidate", "write", "load"]
    output = capsys.readouterr().out
    assert str(evidence.evidence_path) in output
    assert evidence.evidence_digest in output
    assert f"QWQ_DEPENDENCY_PROJECTION_{phase.upper()}_READBACK_REF" in output
    assert f"QWQ_DEPENDENCY_PROJECTION_{phase.upper()}_READBACK_DIGEST" in output
