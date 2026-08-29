"""Commands cannot mutate a projected dependency CAS without typed failure."""

# spec_ref: specs/feature-tree/runtime/runtime-config/design.md#dec-003

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from quwoquan_ops.cli.lib.package_reuse import (
    patrol_command_envelope as envelope_contract,
)
from quwoquan_ops.cli.lib.package_reuse.android_gradle_capsule import (
    ANDROID_GRADLE_PROJECTION_RELATIVE,
)
from quwoquan_ops.cli.lib.package_reuse.android_gradle_store import (
    copy_android_gradle_snapshot,
    seal_android_gradle_home,
)
from quwoquan_ops.cli.lib.package_reuse.dependency_bundle_projection_verify import (
    DEPENDENCY_PROJECTION_CAS_BLOCKER,
    DEPENDENCY_PROJECTION_EVIDENCE_BLOCKER,
    load_dependency_projection_cas_evidence,
    load_dependency_projection_cas_readback,
    prepare_dependency_projection_cas_evidence,
    revalidate_dependency_projection_cas,
    write_dependency_projection_cas_readback,
)
from quwoquan_ops.cli.lib.package_reuse.dependency_projection_contract import (
    COMPONENT_LOGICAL_PATHS,
)
from quwoquan_ops.cli.lib.package_reuse.dependency_projection_prepare import scan_pods
from quwoquan_ops.cli.lib.package_reuse.ios_pod_inputs import (
    IOS_POD_PATROL_HOST,
    IOS_POD_PRODUCTION_HOST,
)
from quwoquan_ops.cli.lib.package_reuse.patrol_pub_cache import (
    PATROL_HOST_RELATIVE,
    PATROL_PUB_PROJECTION_RELATIVE,
)
from quwoquan_ops.cli.lib.package_reuse.pub_cache_capsule import (
    PUB_CACHE_PROJECTION_RELATIVE,
)


@pytest.fixture(autouse=True)
def _restore_tmp_permissions(tmp_path: Path):
    yield
    for current, directories, files in os.walk(
        tmp_path, topdown=False, followlinks=False
    ):
        root = Path(current)
        for name in files:
            path = root / name
            if not path.is_symlink():
                path.chmod(0o600)
        for name in directories:
            path = root / name
            if not path.is_symlink():
                path.chmod(0o700)
        root.chmod(0o700)


def _source_manifest(tmp_path: Path, components: set[str]) -> Path:
    capsule = tmp_path / "capsule"
    capsule.mkdir(exist_ok=True)
    manifest = capsule / "manifest.json"
    entries = [
        {
            "logicalPath": COMPONENT_LOGICAL_PATHS[component],
            "digest": "sha256:" + f"{index + 1:x}" * 64,
            "size": index + 1,
        }
        for index, component in enumerate(sorted(components))
    ]
    manifest.write_text(
        json.dumps(
            {
                "baselineId": "sha256:" + "a" * 64,
                "inputDigest": "sha256:" + "b" * 64,
                "inputCount": len(entries),
                "entries": entries,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return manifest


def _hosted_lock(name: str, version: str, archive_sha: str) -> str:
    return (
        "packages:\n"
        f"  {name}:\n"
        "    dependency: direct main\n"
        "    description:\n"
        f"      name: {name}\n"
        f"      sha256: {archive_sha}\n"
        "      url: https://pub.flutter-io.cn\n"
        "    source: hosted\n"
        f"    version: {version}\n"
    )


def _pub(root: Path, *, patrol: bool = False) -> tuple[Path, Path, Path]:
    name = "patrol_only" if patrol else "production_only"
    version = "2.0.0" if patrol else "1.0.0"
    archive_sha = ("d" if patrol else "c") * 64
    host = root / PATROL_HOST_RELATIVE if patrol else root / "quwoquan_app"
    host.mkdir(parents=True, exist_ok=True)
    lock = host / "pubspec.lock"
    lock.write_text(_hosted_lock(name, version, archive_sha), encoding="utf-8")
    cache = root / (
        PATROL_PUB_PROJECTION_RELATIVE if patrol else PUB_CACHE_PROJECTION_RELATIVE
    )
    package = cache / f"hosted/pub.flutter-io.cn/{name}-{version}"
    package.mkdir(parents=True)
    payload = package / "lib.dart"
    payload.write_text(f"const value = '{name}';\n", encoding="utf-8")
    hash_path = cache / f"hosted-hashes/pub.flutter-io.cn/{name}-{version}.sha256"
    hash_path.parent.mkdir(parents=True)
    hash_path.write_text(archive_sha + "\n", encoding="ascii")
    return cache, lock, payload


def _environment(cache: Path, *, gradle_home: Path | None = None) -> dict[str, str]:
    values = {
        "PATH": "/usr/bin:/bin",
        "PUB_CACHE": str(cache),
        "HOME": str(cache.parent / "command-home"),
        "XDG_CONFIG_HOME": str(cache.parent / "command-xdg-config"),
        "XDG_CACHE_HOME": str(cache.parent / "command-xdg-cache"),
        "FLUTTER_SWIFT_PACKAGE_MANAGER": "false",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }
    if gradle_home is not None:
        values["GRADLE_USER_HOME"] = str(gradle_home)
    return values


def _projection(
    production_cache: Path,
    *,
    patrol_cache: Path | None = None,
    android_home: Path | None = None,
    ios_projections: tuple[tuple[str, object], ...] = (),
    ios_results: tuple[tuple[str, object], ...] = (),
) -> SimpleNamespace:
    return SimpleNamespace(
        production_pub_cache=production_cache,
        patrol_pub_cache=patrol_cache,
        android_gradle_home=android_home,
        ios_projections=ios_projections,
        pod_install_results=ios_results,
        production_environment=_environment(
            production_cache,
            gradle_home=android_home,
        ),
        patrol_environment=(
            _environment(patrol_cache, gradle_home=android_home)
            if patrol_cache is not None
            else None
        ),
    )


def _prepare(*, root: Path, source: Path, projection: SimpleNamespace):
    evidence_parent = root.parent / "private-evidence"
    evidence_parent.mkdir(exist_ok=True)
    return prepare_dependency_projection_cas_evidence(
        projection_root=root,
        source_manifest_path=source,
        dependency_projection=projection,
        evidence_path=evidence_parent / "expected.json",
    )


def test_pub_expectation_is_private_and_reloads_without_projection_object(
    tmp_path: Path,
) -> None:
    root = tmp_path / "projection"
    cache, _lock, _payload = _pub(root)
    projection = _projection(cache)
    source = _source_manifest(tmp_path, {"productionPub"})
    expected = _prepare(root=root, source=source, projection=projection)

    assert expected.evidence_path.stat().st_mode & 0o777 == 0o600
    loaded = load_dependency_projection_cas_evidence(
        projection_root=root,
        evidence_path=expected.evidence_path,
        expected_digest=expected.evidence_digest,
    )
    assert loaded.manifest == expected.manifest

    (cache / "active_roots/aa").mkdir(parents=True)
    (cache / "active_roots/aa/root").write_text("runtime only\n", encoding="utf-8")
    (cache / "README.md").write_text("runtime only\n", encoding="utf-8")
    readback = revalidate_dependency_projection_cas(
        projection_root=root,
        evidence_path=expected.evidence_path,
        expected_digest=expected.evidence_digest,
        command_environment_owner="production",
        command_environment=projection.production_environment,
    )
    assert set(readback.manifest["components"]) == {"productionPub"}
    assert (
        readback.encoded_manifest
        == json.dumps(
            readback.manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )
    persisted = write_dependency_projection_cas_readback(
        readback=readback,
        evidence_path=expected.evidence_path.with_name("readback.json"),
    )
    assert persisted.evidence_path.stat().st_mode & 0o777 == 0o600
    loaded_readback = load_dependency_projection_cas_readback(
        evidence_path=persisted.evidence_path,
        expected_digest=persisted.evidence_digest,
        expected_expectation_digest=expected.evidence_digest,
    )
    assert loaded_readback.manifest == readback.manifest


@pytest.mark.parametrize("mutation", ["package", "lock", "extra", "linked"])
def test_pub_node_or_lock_mutation_is_typed(tmp_path: Path, mutation: str) -> None:
    root = tmp_path / "projection"
    cache, lock, payload = _pub(root)
    projection = _projection(cache)
    expected = _prepare(
        root=root,
        source=_source_manifest(tmp_path, {"productionPub"}),
        projection=projection,
    )
    if mutation == "package":
        payload.write_text("drift\n", encoding="utf-8")
    elif mutation == "lock":
        lock.write_text(lock.read_text() + "# drift\n", encoding="utf-8")
    elif mutation == "extra":
        injected = cache / "hosted/pub.flutter-io.cn/injected-1.0.0/file"
        injected.parent.mkdir(parents=True)
        injected.write_text("drift\n", encoding="utf-8")
    else:
        payload.unlink()
        payload.symlink_to(lock)
    with pytest.raises(ValueError, match=DEPENDENCY_PROJECTION_CAS_BLOCKER):
        revalidate_dependency_projection_cas(
            projection_root=root,
            evidence_path=expected.evidence_path,
            expected_digest=expected.evidence_digest,
        )


def _pods(root: Path, host: str) -> tuple[SimpleNamespace, bytes]:
    ios = root / (
        "quwoquan_app/ios"
        if host == IOS_POD_PRODUCTION_HOST
        else "quwoquan_app/test_host/patrol/ios"
    )
    pods = ios / "Pods"
    (pods / "Pods.xcodeproj").mkdir(parents=True)
    lock = f"PODS:\n  - {host} (1.0)\n".encode()
    (ios / "Podfile.lock").write_bytes(lock)
    (pods / "Manifest.lock").write_bytes(lock)
    (pods / "Pods.xcodeproj/project.pbxproj").write_text(
        "archiveVersion = 1; objects = {}; rootObject = 0;\n",
        encoding="utf-8",
    )
    (pods / "Headers").mkdir()
    (pods / "Headers/example.h").write_text("void example(void);\n", encoding="utf-8")
    return SimpleNamespace(ios_root=ios, pods_root=pods), lock


def _ios_result(projection: SimpleNamespace, lock: bytes, component: str):
    identity = scan_pods(
        projection.pods_root,
        projection.ios_root / "Podfile.lock",
        component=component,
    )
    return SimpleNamespace(
        converged_tree_digest=identity["treeDigest"],
        output_snapshot=SimpleNamespace(lock_bytes=lock),
    )


@pytest.mark.parametrize("mutation", ["pods", "lock"])
def test_dual_ios_converged_pods_and_locks_revalidate_then_fail_on_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    root = tmp_path / "projection"
    production_cache, _lock, _payload = _pub(root)
    patrol_cache, _patrol_lock, _patrol_payload = _pub(root, patrol=True)
    production_ios, production_ios_lock = _pods(root, IOS_POD_PRODUCTION_HOST)
    patrol_ios, patrol_ios_lock = _pods(root, IOS_POD_PATROL_HOST)
    ios_projections = (
        (IOS_POD_PRODUCTION_HOST, production_ios),
        (IOS_POD_PATROL_HOST, patrol_ios),
    )
    ios_results = (
        (
            IOS_POD_PRODUCTION_HOST,
            _ios_result(production_ios, production_ios_lock, "productionIosPods"),
        ),
        (
            IOS_POD_PATROL_HOST,
            _ios_result(patrol_ios, patrol_ios_lock, "patrolIosPods"),
        ),
    )
    projection = _projection(
        production_cache,
        patrol_cache=patrol_cache,
        ios_projections=ios_projections,
        ios_results=ios_results,
    )
    monkeypatch.setattr(
        envelope_contract,
        "resolved_flutter_identity",
        lambda _environment: {
            "executable": str(root / "toolchain/flutter/bin/flutter"),
            "flutterVersion": "3.47.0",
            "commandResolutionDigest": "sha256:" + "f" * 64,
        },
    )
    expected = _prepare(
        root=root,
        source=_source_manifest(
            tmp_path,
            {
                "productionPub",
                "patrolPub",
                "productionIosPods",
                "patrolIosPods",
            },
        ),
        projection=projection,
    )
    command_environment = envelope_contract.rebuild_patrol_command_environment(
        envelope=expected.manifest["patrolCommandEnvelope"],
        ambient_environment={},
        dependency_environment=expected.manifest["environments"]["patrol"]["values"],
        command_environment={},
    )
    readback = revalidate_dependency_projection_cas(
        projection_root=root,
        evidence_path=expected.evidence_path,
        expected_digest=expected.evidence_digest,
        command_environment_owner="patrol",
        command_environment=command_environment,
    )
    assert (
        readback.manifest["patrolCommandEnvelopeDigest"]
        == (command_environment[envelope_contract.PATROL_COMMAND_ENVELOPE_DIGEST_ENV])
    )
    if mutation == "pods":
        (patrol_ios.pods_root / "Headers/example.h").write_text(
            "void drift(void);\n", encoding="utf-8"
        )
    else:
        (patrol_ios.ios_root / "Podfile.lock").write_bytes(
            patrol_ios_lock + b"# drift\n"
        )
    with pytest.raises(ValueError, match=DEPENDENCY_PROJECTION_CAS_BLOCKER):
        revalidate_dependency_projection_cas(
            projection_root=root,
            evidence_path=expected.evidence_path,
            expected_digest=expected.evidence_digest,
        )


def _wrapper(root: Path, relative: str, archive: bytes) -> Path:
    gradle = root / relative
    wrapper = gradle / "gradle/wrapper"
    wrapper.mkdir(parents=True)
    checksum = hashlib.sha256(archive).hexdigest()
    (wrapper / "gradle-wrapper.properties").write_text(
        "distributionUrl=https\\://services.gradle.org/distributions/"
        "gradle-8.14-bin.zip\n"
        f"distributionSha256Sum={checksum}\n",
        encoding="utf-8",
    )
    (wrapper / "gradle-wrapper.jar").write_bytes(b"wrapper jar")
    (gradle / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")
    (gradle / "gradlew").chmod(0o755)
    (gradle / "gradlew.bat").write_text("@echo off\r\n", encoding="utf-8")
    return gradle


def _android_home(tmp_path: Path, root: Path) -> tuple[Path, Path]:
    archive = b"gradle distribution"
    roots = [
        _wrapper(root, "quwoquan_app/android", archive),
        _wrapper(root, "quwoquan_app/test_host/patrol/android", archive),
    ]
    raw = tmp_path / "raw-gradle-home"
    distribution = raw / "wrapper/dists/gradle-8.14-bin/fixture"
    distribution.mkdir(parents=True)
    (distribution / "gradle-8.14-bin.zip").write_bytes(archive)
    artifact = b"plugin artifact"
    sha1 = hashlib.sha1(artifact, usedforsecurity=False).hexdigest()
    artifact_path = (
        raw
        / "caches/modules-2/files-2.1/com.example/plugin/1.0"
        / sha1
        / "plugin-1.0.jar"
    )
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(artifact)
    snapshot = seal_android_gradle_home(
        project_root=root,
        gradle_user_home=raw,
        destination=tmp_path / "sealed-gradle",
        gradle_roots=roots,
    )
    home = copy_android_gradle_snapshot(
        snapshot,
        root / ANDROID_GRADLE_PROJECTION_RELATIVE,
        project_root=root,
        gradle_roots=roots,
    )
    projected_artifact = next((home / "caches/modules-2/files-2.1").rglob("*.jar"))
    return home, projected_artifact


def test_android_declared_domain_ignores_only_real_runtime_transients(
    tmp_path: Path,
) -> None:
    root = tmp_path / "projection"
    cache, _lock, _payload = _pub(root)
    home, artifact = _android_home(tmp_path, root)
    projection = _projection(cache, android_home=home)
    expected = _prepare(
        root=root,
        source=_source_manifest(tmp_path, {"productionPub", "androidGradle"}),
        projection=projection,
    )
    transients = {
        "caches/8.14/fileHashes/fileHashes.bin": b"derived",
        "caches/9.3.1/kotlin-dsl/accessors.bin": b"derived",
        "caches/jars-9/jar.bin": b"derived",
        "caches/journal-1/file-access.bin": b"derived",
        "daemon/8.14/daemon.log": b"derived",
        "kotlin-profile/profile": b"derived",
        "native/native-platform": b"derived",
        "notifications/release-features.rendered": b"derived",
        "android/repositories.cfg": b"derived",
        "caches/modules-2/modules-2.lock": b"lock",
        "caches/CACHEDIR.TAG": b"tag",
    }
    for relative, content in transients.items():
        path = home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    revalidate_dependency_projection_cas(
        projection_root=root,
        evidence_path=expected.evidence_path,
        expected_digest=expected.evidence_digest,
        command_environment_owner="production",
        command_environment=projection.production_environment,
    )

    artifact.write_bytes(b"tampered dependency")
    with pytest.raises(ValueError, match=DEPENDENCY_PROJECTION_CAS_BLOCKER):
        revalidate_dependency_projection_cas(
            projection_root=root,
            evidence_path=expected.evidence_path,
            expected_digest=expected.evidence_digest,
        )


def test_android_unlisted_modules_node_and_evidence_or_environment_drift_fail(
    tmp_path: Path,
) -> None:
    root = tmp_path / "projection"
    cache, _lock, _payload = _pub(root)
    home, _artifact = _android_home(tmp_path, root)
    projection = _projection(cache, android_home=home)
    expected = _prepare(
        root=root,
        source=_source_manifest(tmp_path, {"productionPub", "androidGradle"}),
        projection=projection,
    )
    injected = home / "caches/modules-2/metadata-2.107/injected.lock"
    injected.parent.mkdir(parents=True, exist_ok=True)
    injected.write_bytes(b"not transient")
    with pytest.raises(ValueError, match=DEPENDENCY_PROJECTION_CAS_BLOCKER):
        revalidate_dependency_projection_cas(
            projection_root=root,
            evidence_path=expected.evidence_path,
            expected_digest=expected.evidence_digest,
        )
    injected.unlink()

    drifted_environment = {
        **projection.production_environment,
        "GRADLE_USER_HOME": str(Path.home() / ".gradle"),
    }
    with pytest.raises(ValueError, match=DEPENDENCY_PROJECTION_CAS_BLOCKER):
        revalidate_dependency_projection_cas(
            projection_root=root,
            evidence_path=expected.evidence_path,
            expected_digest=expected.evidence_digest,
            command_environment_owner="production",
            command_environment=drifted_environment,
        )

    expected.evidence_path.write_bytes(expected.evidence_path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match=DEPENDENCY_PROJECTION_EVIDENCE_BLOCKER):
        load_dependency_projection_cas_evidence(
            projection_root=root,
            evidence_path=expected.evidence_path,
            expected_digest=expected.evidence_digest,
        )
