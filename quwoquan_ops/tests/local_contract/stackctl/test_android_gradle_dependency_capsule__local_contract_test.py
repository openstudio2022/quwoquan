"""Android Gradle dependencies use an exact private offline closure."""

# spec_ref: specs/feature-tree/runtime/runtime-config/design.md#dec-003

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from quwoquan_ops.cli.lib.package_reuse import android_gradle_store as gradle_store
from quwoquan_ops.cli.lib.package_reuse.android_gradle_capsule import (
    ANDROID_GRADLE_CAPSULE_MANIFEST,
    ANDROID_GRADLE_CAPSULE_TREE,
    ANDROID_GRADLE_LOGICAL_PATH,
    build_android_gradle_snapshot,
    digest_bytes,
    load_android_gradle_snapshot,
)
from quwoquan_ops.cli.lib.package_reuse.android_gradle_projection import (
    materialize_capsule_android_gradle_home,
    private_gradle_environment,
)
from quwoquan_ops.cli.lib.package_reuse.android_gradle_store import (
    GradleInvocation,
    canonical_android_uat_gradle_invocations,
    copy_android_gradle_snapshot,
    materialize_flutter_gradle_wrappers,
    run_gradle_invocations,
    seal_android_gradle_home,
    synchronize_android_gradle_dependencies,
    write_android_gradle_capsule,
)


def _wrapper(project: Path, archive: bytes = b"gradle distribution") -> Path:
    root = project / "quwoquan_app/android"
    wrapper = root / "gradle/wrapper"
    wrapper.mkdir(parents=True)
    checksum = hashlib.sha256(archive).hexdigest()
    (wrapper / "gradle-wrapper.properties").write_text(
        "distributionBase=GRADLE_USER_HOME\n"
        "distributionPath=wrapper/dists\n"
        "zipStoreBase=GRADLE_USER_HOME\n"
        "zipStorePath=wrapper/dists\n"
        "distributionUrl=https\\://services.gradle.org/distributions/gradle-8.14-bin.zip\n"
        f"distributionSha256Sum={checksum}\n",
        encoding="utf-8",
    )
    (wrapper / "gradle-wrapper.jar").write_bytes(b"wrapper jar")
    gradlew = root / "gradlew"
    gradlew.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$*|$GRADLE_USER_HOME\"\n", encoding="utf-8"
    )
    gradlew.chmod(0o755)
    (root / "gradlew.bat").write_text("@echo off\r\n", encoding="utf-8")
    return root


def _flutter_wrapper_sdk(tmp_path: Path) -> tuple[Path, dict[str, tuple[bytes, int]]]:
    flutter = tmp_path / "flutter-sdk/bin/flutter"
    flutter.parent.mkdir(parents=True)
    flutter.write_bytes(b"#!/bin/sh\n")
    flutter.chmod(0o755)
    artifacts = {
        "gradlew": (b"#!/bin/sh\n# sdk wrapper\n", 0o755),
        "gradlew.bat": (b"@echo off\r\nREM sdk wrapper\r\n", 0o644),
        "gradle/wrapper/gradle-wrapper.jar": (b"sdk wrapper jar", 0o644),
    }
    artifact_root = flutter.parent / "cache/artifacts/gradle_wrapper"
    for relative, (content, mode) in artifacts.items():
        target = artifact_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        target.chmod(mode)
    return flutter, artifacts


def _wrapper_properties(
    root: Path, *, version: str, archive: bytes
) -> tuple[Path, bytes]:
    wrapper = root / "gradle/wrapper"
    wrapper.mkdir(parents=True)
    encoded = (
        "distributionBase=GRADLE_USER_HOME\n"
        f"distributionUrl=https\\://services.gradle.org/distributions/gradle-{version}-bin.zip\n"
        f"distributionSha256Sum={hashlib.sha256(archive).hexdigest()}\n"
    ).encode()
    properties = wrapper / "gradle-wrapper.properties"
    properties.write_bytes(encoded)
    return properties, encoded


def _raw_home(tmp_path: Path, archive: bytes = b"gradle distribution") -> Path:
    home = tmp_path / "raw-home"
    distribution = home / "wrapper/dists/gradle-8.14-bin/fixture"
    distribution.mkdir(parents=True)
    (distribution / "gradle-8.14-bin.zip").write_bytes(archive)
    (distribution / "gradle-8.14-bin.zip.ok").write_bytes(b"")
    (distribution / "gradle-8.14/bin").mkdir(parents=True)
    executable = distribution / "gradle-8.14/bin/gradle"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    workers_api = (
        distribution
        / "gradle-8.14/docs/javadoc/org/gradle/workers/ClassLoaderWorkerSpec.html"
    )
    workers_api.parent.mkdir(parents=True)
    workers_api.write_text("official distribution content", encoding="utf-8")
    # Gradle's files-2.1 directory form elides SHA-1 leading zeroes.
    artifact = b"verified plugin artifact 79"
    artifact_sha1 = hashlib.sha1(artifact, usedforsecurity=False).hexdigest()
    assert artifact_sha1.startswith("00")
    artifact_path = (
        home
        / "caches/modules-2/files-2.1/com.example/plugin/1.2.3"
        / artifact_sha1.lstrip("0")
        / "plugin-1.2.3.jar"
    )
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(artifact)
    metadata = home / "caches/modules-2/metadata-2.107/descriptors.bin"
    metadata.parent.mkdir(parents=True)
    metadata.write_bytes(b"resolution metadata")
    (home / "daemon/8.14").mkdir(parents=True)
    (home / "daemon/8.14/daemon.log").write_text("not a dependency", encoding="utf-8")
    return home


def _sealed(tmp_path: Path) -> tuple[Path, Path, Path, object]:
    project = tmp_path / "project"
    gradle_root = _wrapper(project)
    raw = _raw_home(tmp_path)
    sealed = tmp_path / "sealed"
    snapshot = seal_android_gradle_home(
        project_root=project,
        gradle_user_home=raw,
        destination=sealed,
        gradle_roots=[gradle_root],
    )
    return project, gradle_root, sealed, snapshot


def test_flutter_sdk_materializes_both_private_wrappers_and_preserves_properties(
    tmp_path: Path,
) -> None:
    project = tmp_path / "private-projection"
    production = project / "quwoquan_app/android"
    patrol = project / "quwoquan_app/test_host/patrol/android"
    production_properties, production_bytes = _wrapper_properties(
        production, version="8.14", archive=b"production distribution"
    )
    patrol_properties, patrol_bytes = _wrapper_properties(
        patrol, version="8.12.1", archive=b"patrol distribution"
    )
    flutter, artifacts = _flutter_wrapper_sdk(tmp_path)

    identities = materialize_flutter_gradle_wrappers(
        project_root=project,
        gradle_roots=[production, patrol],
        flutter_executable=flutter,
    )

    assert [item["root"] for item in identities] == [
        "quwoquan_app/android",
        "quwoquan_app/test_host/patrol/android",
    ]
    assert identities[0]["distributionUrl"].endswith("gradle-8.14-bin.zip")
    assert identities[1]["distributionUrl"].endswith("gradle-8.12.1-bin.zip")
    assert identities[0]["distributionSha256"] != identities[1][
        "distributionSha256"
    ]
    assert production_properties.read_bytes() == production_bytes
    assert patrol_properties.read_bytes() == patrol_bytes
    for gradle_root in (production, patrol):
        for relative, expected in artifacts.items():
            target = gradle_root / relative
            assert target.read_bytes() == expected[0]
            assert stat.S_IMODE(target.stat().st_mode) == expected[1]


@pytest.mark.parametrize("unsafe", ["symlink", "drift", "sdk-missing"])
def test_flutter_wrapper_materialization_fails_closed_without_overwrite(
    tmp_path: Path, unsafe: str
) -> None:
    project = tmp_path / "private-projection"
    production = project / "quwoquan_app/android"
    patrol = project / "quwoquan_app/test_host/patrol/android"
    _wrapper_properties(production, version="8.14", archive=b"production")
    _wrapper_properties(patrol, version="8.12.1", archive=b"patrol")
    flutter, artifacts = _flutter_wrapper_sdk(tmp_path)
    existing = production / "gradlew"
    if unsafe == "symlink":
        existing.symlink_to(flutter)
    elif unsafe == "drift":
        existing.write_bytes(b"project-local wrapper drift")
        existing.chmod(0o755)
    else:
        (
            flutter.parent
            / "cache/artifacts/gradle_wrapper/gradle/wrapper/gradle-wrapper.jar"
        ).unlink()

    with pytest.raises(ValueError, match="wrapper|Wrapper"):
        materialize_flutter_gradle_wrappers(
            project_root=project,
            gradle_roots=[production, patrol],
            flutter_executable=flutter,
        )

    assert not (patrol / "gradlew").exists()
    assert not (patrol / "gradlew.bat").exists()
    assert not (patrol / "gradle/wrapper/gradle-wrapper.jar").exists()
    if unsafe == "drift":
        assert existing.read_bytes() == b"project-local wrapper drift"
    if unsafe != "sdk-missing":
        sdk_batch = artifacts["gradlew.bat"]
        assert (
            flutter.parent / "cache/artifacts/gradle_wrapper/gradlew.bat"
        ).read_bytes() == sdk_batch[0]


def test_seal_binds_wrapper_maven_artifacts_lock_and_verification_metadata(
    tmp_path: Path,
) -> None:
    project, _gradle_root, sealed, snapshot = _sealed(tmp_path)

    assert snapshot.manifest["componentCount"] == 1
    assert snapshot.manifest["artifactCount"] == 1
    assert snapshot.manifest["wrappers"][0]["root"] == "quwoquan_app/android"
    assert any(
        item.relative.endswith("org/gradle/workers/ClassLoaderWorkerSpec.html")
        for item in snapshot.files
    )
    assert not (sealed / "home/daemon").exists()
    resolution = json.loads(
        (sealed / "metadata/resolution-lock.json").read_text(encoding="utf-8")
    )
    verification = json.loads(
        (sealed / "metadata/verification-metadata.json").read_text(encoding="utf-8")
    )
    assert resolution["components"] == ["com.example:plugin:1.2.3"]
    assert verification["artifacts"][0]["sha256"].startswith("sha256:")
    build_android_gradle_snapshot(
        project_root=project,
        tree_root=sealed,
        gradle_roots=[project / "quwoquan_app/android"],
    )


def test_sealed_tree_rejects_extra_bytes_and_artifact_drift(tmp_path: Path) -> None:
    project, gradle_root, sealed, _snapshot = _sealed(tmp_path)
    metadata = sealed / "metadata"
    sealed.chmod(0o755)
    metadata.chmod(0o755)
    (metadata / "injected.bin").write_bytes(b"unexpected")
    with pytest.raises(ValueError, match="unmanifested bytes"):
        build_android_gradle_snapshot(
            project_root=project,
            tree_root=sealed,
            gradle_roots=[gradle_root],
        )
    (metadata / "injected.bin").unlink()
    artifact = next((sealed / "home/caches/modules-2/files-2.1").rglob("*.jar"))
    artifact.chmod(0o644)
    artifact.write_bytes(b"drift")
    with pytest.raises(ValueError, match="sha1 directory drifted"):
        build_android_gradle_snapshot(
            project_root=project,
            tree_root=sealed,
            gradle_roots=[gradle_root],
        )


@pytest.mark.parametrize("unsafe", ["symlink", "hardlink"])
def test_sync_rejects_linked_dependency_nodes(tmp_path: Path, unsafe: str) -> None:
    project = tmp_path / "project"
    gradle_root = _wrapper(project)
    raw = _raw_home(tmp_path)
    artifact = next((raw / "caches/modules-2/files-2.1").rglob("*.jar"))
    replacement = artifact.with_suffix(".unsafe")
    if unsafe == "symlink":
        replacement.symlink_to(artifact)
    else:
        os.link(artifact, replacement)
    with pytest.raises(ValueError, match="symlink, hardlink or special"):
        seal_android_gradle_home(
            project_root=project,
            gradle_user_home=raw,
            destination=tmp_path / "sealed",
            gradle_roots=[gradle_root],
        )


def test_projection_is_private_forced_offline_and_has_no_global_fallback(
    tmp_path: Path,
) -> None:
    project, _gradle_root, _sealed_root, snapshot = _sealed(tmp_path)
    projection = tmp_path / "projection"
    shutil.copytree(project, projection)
    home = copy_android_gradle_snapshot(
        snapshot,
        projection / "dependency",
        project_root=projection,
        gradle_roots=[projection / "quwoquan_app/android"],
    )
    environment = private_gradle_environment(
        gradle_user_home=home,
        base={"GRADLE_HOME": "/untrusted", "PATH": os.environ["PATH"]},
    )
    assert environment["GRADLE_USER_HOME"] == str(home)
    assert "GRADLE_HOME" not in environment
    assert "startParameter.offline = true" in (
        home / "init.d/qwq-offline.gradle"
    ).read_text(encoding="utf-8")
    result = run_gradle_invocations(
        project_root=projection,
        gradle_user_home=home,
        invocations=[
            GradleInvocation(
                gradle_root=projection / "quwoquan_app/android",
                tasks=("clean", "assembleNonprodDebug"),
            )
        ],
        offline=True,
        environment=environment,
    )[0]
    assert "--offline clean assembleNonprodDebug" in result.stdout
    with pytest.raises(ValueError, match="global cache fallback"):
        private_gradle_environment(
            gradle_user_home=Path.home() / ".gradle",
            base={},
        )


@pytest.mark.parametrize(
    "failure_output",
    [
        "javax.net.ssl.SSLHandshakeException: Remote host terminated the handshake",
        "java.net.SocketException: Connection reset",
        "java.net.SocketTimeoutException: Read timed out",
        "Received status code 408 from server",
        "Received status code 429 from server",
        "Received status code 503 from server",
        "curl: (22) The requested URL returned error: 503",
        (
            "Verification of Gradle distribution failed! Actual checksum: "
            "'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'"
        ),
    ],
)
def test_online_invocation_retries_only_transient_network_failure_in_same_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_output: str,
) -> None:
    project = tmp_path / "project"
    gradle_root = _wrapper(project)
    home = tmp_path / "online-home"
    home.mkdir()
    commands: list[list[str]] = []
    homes: list[str] = []
    backoffs: list[float] = []

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        homes.append(str(environment["GRADLE_USER_HOME"]))
        marker = Path(homes[-1]) / "first-attempt-byte"
        if len(commands) == 1:
            marker.write_text("retained", encoding="utf-8")
            raise subprocess.CalledProcessError(1, command, output=failure_output)
        assert marker.read_text(encoding="utf-8") == "retained"
        return subprocess.CompletedProcess(command, 0, stdout="recovered")

    monkeypatch.setattr(gradle_store, "run_managed_subprocess", fake_run)
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.package_reuse.android_gradle_store.time.sleep",
        backoffs.append,
    )
    result = run_gradle_invocations(
        project_root=project,
        gradle_user_home=home,
        invocations=[
            GradleInvocation(gradle_root=gradle_root, tasks=("dependencies",))
        ],
        offline=False,
        environment={},
    )

    assert "result=transient_failure" in result[0].stdout
    assert "result=success" in result[0].stdout
    assert "recovered" not in result[0].stdout
    assert len(commands) == 2
    assert homes == [str(home), str(home)]
    assert all("--refresh-dependencies" not in command for command in commands)
    assert backoffs == [1.0]


@pytest.mark.parametrize(
    "failure_output",
    [
        "Received status code 404 from server",
        "curl: (22) The requested URL returned error: 404",
        "SSLHandshakeException: PKIX path building failed",
        "SSL_connect: certificate verify failed",
        (
            "Verification of Gradle distribution failed! Actual checksum: "
            "'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'"
        ),
        "Plugin with id 'com.android.application' not found",
    ],
)
def test_online_invocation_does_not_retry_deterministic_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_output: str,
) -> None:
    project = tmp_path / "project"
    gradle_root = _wrapper(project)
    home = tmp_path / "online-home"
    home.mkdir()
    failure = subprocess.CalledProcessError(
        1,
        [str(gradle_root / "gradlew")],
        output=failure_output,
    )
    calls = 0

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        raise failure

    monkeypatch.setattr(gradle_store, "run_managed_subprocess", fake_run)
    with pytest.raises(subprocess.CalledProcessError) as caught:
        run_gradle_invocations(
            project_root=project,
            gradle_user_home=home,
            invocations=[GradleInvocation(gradle_root, ("dependencies",))],
            offline=False,
            environment={},
        )
    assert caught.value is failure
    assert calls == 1


def test_online_invocation_transient_then_deterministic_raises_current_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    gradle_root = _wrapper(project)
    home = tmp_path / "online-home"
    home.mkdir()
    failures = [
        subprocess.CalledProcessError(
            1,
            [str(gradle_root / "gradlew")],
            output="SSLHandshakeException: EOF transient-first",
        ),
        subprocess.CalledProcessError(
            1,
            [str(gradle_root / "gradlew")],
            output="Received status code 404 deterministic-second",
        ),
    ]
    current_failures = failures.copy()
    backoffs: list[float] = []

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise current_failures.pop(0)

    monkeypatch.setattr(gradle_store, "run_managed_subprocess", fake_run)
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.package_reuse.android_gradle_store.time.sleep",
        backoffs.append,
    )
    with pytest.raises(subprocess.CalledProcessError) as caught:
        run_gradle_invocations(
            project_root=project,
            gradle_user_home=home,
            invocations=[GradleInvocation(gradle_root, ("dependencies",))],
            offline=False,
            environment={},
        )

    assert caught.value is failures[1]
    assert current_failures == []
    assert backoffs == [1.0]


def test_online_invocation_exhaustion_raises_first_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    gradle_root = _wrapper(project)
    home = tmp_path / "online-home"
    home.mkdir()
    failures = [
        subprocess.CalledProcessError(
            index,
            [str(gradle_root / "gradlew")],
            output=f"SSLHandshakeException: EOF attempt {index}",
        )
        for index in (1, 2, 3)
    ]

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise failures.pop(0)

    first_failure = failures[0]
    monkeypatch.setattr(gradle_store, "run_managed_subprocess", fake_run)
    backoffs: list[float] = []
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.package_reuse.android_gradle_store.time.sleep",
        backoffs.append,
    )
    with pytest.raises(subprocess.CalledProcessError) as caught:
        run_gradle_invocations(
            project_root=project,
            gradle_user_home=home,
            invocations=[GradleInvocation(gradle_root, ("dependencies",))],
            offline=False,
            environment={},
        )
    assert caught.value is first_failure
    assert failures == []
    assert backoffs == [1.0, 2.0]


def test_online_invocation_caps_process_timeout_and_total_deadline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    gradle_root = _wrapper(project)
    home = tmp_path / "online-home"
    home.mkdir()
    clock = [0.0]
    timeouts: list[float] = []
    backoffs: list[float] = []
    failures: list[subprocess.CalledProcessError] = []

    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.package_reuse.android_gradle_store._GRADLE_PROCESS_TIMEOUT_SECONDS",
        4,
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.package_reuse.android_gradle_store._GRADLE_INVOCATION_DEADLINE_SECONDS",
        10,
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.package_reuse.android_gradle_store.time.monotonic",
        lambda: clock[0],
    )

    def fake_sleep(seconds: float) -> None:
        backoffs.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.package_reuse.android_gradle_store.time.sleep",
        fake_sleep,
    )

    def fake_run(*_args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        timeouts.append(float(kwargs["timeout"]))
        clock[0] += 6
        failure = subprocess.CalledProcessError(
            1,
            [str(gradle_root / "gradlew")],
            output="SSLHandshakeException: EOF",
        )
        failures.append(failure)
        raise failure

    monkeypatch.setattr(gradle_store, "run_managed_subprocess", fake_run)
    with pytest.raises(subprocess.CalledProcessError) as caught:
        run_gradle_invocations(
            project_root=project,
            gradle_user_home=home,
            invocations=[GradleInvocation(gradle_root, ("dependencies",))],
            offline=False,
            environment={},
        )
    assert caught.value is failures[0]
    assert timeouts == [4.0, 3.0]
    assert backoffs == [1.0]


def test_process_timeout_retries_within_the_bounded_canonical_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    gradle_root = _wrapper(project)
    home = tmp_path / "online-home"
    home.mkdir()
    calls = 0

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        raise subprocess.TimeoutExpired(command, timeout=kwargs["timeout"])

    monkeypatch.setattr(gradle_store, "run_managed_subprocess", fake_run)
    with pytest.raises(subprocess.CalledProcessError) as caught:
        run_gradle_invocations(
            project_root=project,
            gradle_user_home=home,
            invocations=[GradleInvocation(gradle_root, ("dependencies",))],
            offline=False,
            environment={},
        )
    assert caught.value.returncode == 124
    assert "bounded timeout" in str(caught.value.output)
    assert calls == 3


def test_offline_invocation_never_retries_network_shaped_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    gradle_root = _wrapper(project)
    home = tmp_path / "offline-home"
    home.mkdir()
    commands: list[list[str]] = []
    failure = subprocess.CalledProcessError(
        1,
        [str(gradle_root / "gradlew")],
        output="SSLHandshakeException: EOF",
    )

    def fake_run(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        raise failure

    monkeypatch.setattr(gradle_store, "run_managed_subprocess", fake_run)
    with pytest.raises(subprocess.CalledProcessError) as caught:
        run_gradle_invocations(
            project_root=project,
            gradle_user_home=home,
            invocations=[GradleInvocation(gradle_root, ("dependencies",))],
            offline=True,
            environment={},
        )
    assert caught.value is failure
    assert len(commands) == 1
    assert "--offline" in commands[0]


def test_capsule_projection_rejects_manifest_or_tree_drift(tmp_path: Path) -> None:
    project, _gradle_root, sealed, snapshot = _sealed(tmp_path)
    capsule = tmp_path / "capsule"
    shutil.copytree(project, capsule / "repo")
    (capsule / "repo/quwoquan_app/android/gradlew").unlink()
    (capsule / "repo/quwoquan_app/android/gradlew.bat").unlink()
    (capsule / "repo/quwoquan_app/android/gradle/wrapper/gradle-wrapper.jar").unlink()
    shutil.copytree(sealed, capsule / ANDROID_GRADLE_CAPSULE_TREE)
    manifest_path = capsule / ANDROID_GRADLE_CAPSULE_MANIFEST
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(snapshot.encoded_manifest)
    entry = {
        "logicalPath": ANDROID_GRADLE_LOGICAL_PATH,
        "capsulePath": ANDROID_GRADLE_CAPSULE_MANIFEST.as_posix(),
        "digest": digest_bytes(snapshot.encoded_manifest),
        "size": len(snapshot.encoded_manifest),
    }
    projection = tmp_path / "projection"
    shutil.copytree(capsule / "repo", projection)
    with pytest.raises(ValueError, match="wrapper .* unavailable"):
        run_gradle_invocations(
            project_root=projection,
            gradle_user_home=tmp_path / "unused-home",
            invocations=[
                GradleInvocation(
                    gradle_root=projection / "quwoquan_app/android",
                    tasks=("dependencies",),
                )
            ],
            offline=True,
        )
    home = materialize_capsule_android_gradle_home(
        capsule_root=capsule,
        manifest_entries=[entry],
        projection_root=projection,
    )
    assert home.is_dir()
    assert (projection / "quwoquan_app/android/gradlew").is_file()
    assert (projection / "quwoquan_app/android/gradlew.bat").is_file()
    assert (
        projection / "quwoquan_app/android/gradle/wrapper/gradle-wrapper.jar"
    ).is_file()
    manifest_path.chmod(0o644)
    manifest_path.write_bytes(snapshot.encoded_manifest + b"\n")
    with pytest.raises(ValueError, match="manifest identity drifted"):
        materialize_capsule_android_gradle_home(
            capsule_root=capsule,
            manifest_entries=[entry],
            projection_root=tmp_path / "other-projection",
        )


def test_explicit_sync_uses_fresh_online_home_then_exact_offline_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "project"
    gradle_root = _wrapper(project)
    raw_fixture = _raw_home(tmp_path)
    calls: list[bool] = []

    def fake_run(**kwargs: object) -> list[object]:
        offline = bool(kwargs["offline"])
        calls.append(offline)
        home = Path(str(kwargs["gradle_user_home"]))
        if not offline:
            shutil.copytree(raw_fixture, home, dirs_exist_ok=True)
        return []

    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.package_reuse.android_gradle_store.run_gradle_invocations",
        fake_run,
    )
    result = synchronize_android_gradle_dependencies(
        project_root=project,
        online_home=tmp_path / "online",
        sealed_tree=tmp_path / "sealed",
        replay_tree=tmp_path / "replay",
        gradle_roots=[gradle_root],
        invocations=[
            GradleInvocation(gradle_root=gradle_root, tasks=("dependencies",))
        ],
    )
    assert calls == [False, True]
    assert result.snapshot.manifest["artifactCount"] == 1
    assert (tmp_path / "replay/home/init.d/qwq-offline.gradle").is_file()


def test_package_capsule_writer_is_fresh_read_only_and_cas_verified(
    tmp_path: Path,
) -> None:
    project, gradle_root, _sealed_root, snapshot = _sealed(tmp_path)
    capsule = tmp_path / "capsule"
    tree = capsule / ANDROID_GRADLE_CAPSULE_TREE
    manifest = capsule / ANDROID_GRADLE_CAPSULE_MANIFEST
    write_android_gradle_capsule(
        snapshot,
        destination_tree=tree,
        manifest_path=manifest,
        project_root=project,
        gradle_roots=[gradle_root],
    )
    assert manifest.read_bytes() == snapshot.encoded_manifest
    assert manifest.stat().st_mode & 0o777 == 0o444
    assert tree.stat().st_mode & 0o777 == 0o555
    assert all(path.stat().st_mode & 0o222 == 0 for path in tree.rglob("*"))
    with pytest.raises(ValueError, match="must be fresh"):
        write_android_gradle_capsule(
            snapshot,
            destination_tree=tree,
            manifest_path=manifest,
            project_root=project,
            gradle_roots=[gradle_root],
        )


def test_canonical_uat_sync_covers_production_patrol_and_instrumentation(
    tmp_path: Path,
) -> None:
    invocations = canonical_android_uat_gradle_invocations(tmp_path)
    assert invocations == (
        GradleInvocation(
            gradle_root=tmp_path / "quwoquan_app/android",
            tasks=(
                ":app:assembleNonprodDebug",
                ":app:assembleNonprodDebugAndroidTest",
            ),
        ),
        GradleInvocation(
            gradle_root=tmp_path / "quwoquan_app/test_host/patrol/android",
            tasks=(":app:assembleDebug", ":app:assembleDebugAndroidTest"),
        ),
    )


def test_managed_snapshot_loader_rejects_noncanonical_or_stale_manifest(
    tmp_path: Path,
) -> None:
    project, gradle_root, sealed, snapshot = _sealed(tmp_path)
    manifest = tmp_path / "manifest.json"
    manifest.write_bytes(snapshot.encoded_manifest)
    loaded = load_android_gradle_snapshot(
        project_root=project,
        tree_root=sealed,
        manifest_path=manifest,
        gradle_roots=[gradle_root],
    )
    assert loaded.manifest == snapshot.manifest
    manifest.write_bytes(snapshot.encoded_manifest + b"\n")
    with pytest.raises(ValueError, match="not canonical"):
        load_android_gradle_snapshot(
            project_root=project,
            tree_root=sealed,
            manifest_path=manifest,
            gradle_roots=[gradle_root],
        )
