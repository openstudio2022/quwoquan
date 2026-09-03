"""The Android component binds tasks and native resolution to its CAS."""

# spec_ref: specs/feature-tree/runtime/runtime-config/design.md#dec-003

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from quwoquan_ops.cli.lib.package_reuse import android_gradle_component as component
from quwoquan_ops.cli.lib.package_reuse.android_gradle_store import (
    GradleInvocation,
    seal_android_gradle_home,
)

UPSTREAM_DIGESTS = {
    "productionPub": "sha256:" + "c" * 64,
    "patrolPub": "sha256:" + "d" * 64,
}


def _snapshot(tmp_path: Path) -> tuple[Path, object, list[GradleInvocation]]:
    project = tmp_path / "project"
    gradle_root = project / "quwoquan_app/android"
    wrapper = gradle_root / "gradle/wrapper"
    wrapper.mkdir(parents=True)
    archive = b"gradle distribution"
    checksum = hashlib.sha256(archive).hexdigest()
    (wrapper / "gradle-wrapper.properties").write_text(
        "distributionUrl=https\\://services.gradle.org/distributions/gradle-8.14-bin.zip\n"
        f"distributionSha256Sum={checksum}\n",
        encoding="utf-8",
    )
    (wrapper / "gradle-wrapper.jar").write_bytes(b"wrapper jar")
    (gradle_root / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")
    (gradle_root / "gradlew").chmod(0o755)
    (gradle_root / "gradlew.bat").write_text("@echo off\r\n", encoding="utf-8")
    home = tmp_path / "home"
    distribution = home / "wrapper/dists/gradle-8.14-bin/fixture"
    distribution.mkdir(parents=True)
    (distribution / "gradle-8.14-bin.zip").write_bytes(archive)
    artifact = b"plugin"
    sha1 = hashlib.sha1(artifact, usedforsecurity=False).hexdigest()
    artifact_path = (
        home
        / "caches/modules-2/files-2.1/com.example/plugin/1.0"
        / sha1
        / "plugin-1.0.jar"
    )
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(artifact)
    invocations = [GradleInvocation(gradle_root, (":app:assembleDebug",))]
    snapshot = seal_android_gradle_home(
        project_root=project,
        gradle_user_home=home,
        destination=tmp_path / "sealed",
        gradle_roots=[gradle_root],
    )
    return project, snapshot, invocations


@pytest.fixture(autouse=True)
def _native_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        component,
        "native_resolution_input_identity",
        lambda _root: {
            "nativeResolutionInputDigest": "sha256:" + "a" * 64,
            "nativeResolutionInputCount": 1,
            "nativeResolutionInputs": [
                {"path": "android/build.gradle", "size": 1, "sha256": "sha256:" + "b" * 64}
            ],
        },
    )


def test_component_round_trip_binds_invocation_set(tmp_path: Path) -> None:
    project, snapshot, invocations = _snapshot(tmp_path)
    gradle_root = invocations[0].gradle_root
    (gradle_root / "gradlew").unlink()
    (gradle_root / "gradlew.bat").unlink()
    (gradle_root / "gradle/wrapper/gradle-wrapper.jar").unlink()
    parent = tmp_path / "components"
    parent.mkdir()
    target = parent / "android"

    component.write_android_gradle_component(
        project_root=project,
        snapshot=snapshot,
        invocations=invocations,
        upstream_dependency_digests=UPSTREAM_DIGESTS,
        destination=target,
    )

    loaded = component.load_android_gradle_component(
        project_root=project,
        component_root=target,
        invocations=invocations,
        upstream_dependency_digests=UPSTREAM_DIGESTS,
    )
    assert loaded.manifest == snapshot.manifest


def test_component_rejects_task_or_native_input_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, snapshot, invocations = _snapshot(tmp_path)
    parent = tmp_path / "components"
    parent.mkdir()
    target = parent / "android"
    component.write_android_gradle_component(
        project_root=project,
        snapshot=snapshot,
        invocations=invocations,
        upstream_dependency_digests=UPSTREAM_DIGESTS,
        destination=target,
    )

    with pytest.raises(ValueError, match="invocation set"):
        component.load_android_gradle_component(
            project_root=project,
            component_root=target,
            invocations=[GradleInvocation(invocations[0].gradle_root, ("help",))],
            upstream_dependency_digests=UPSTREAM_DIGESTS,
        )

    monkeypatch.setattr(
        component,
        "native_resolution_input_identity",
        lambda _root: {
            "nativeResolutionInputDigest": "sha256:" + "c" * 64,
            "nativeResolutionInputCount": 1,
            "nativeResolutionInputs": [],
        },
    )
    with pytest.raises(ValueError, match="native inputs"):
        component.load_android_gradle_component(
            project_root=project,
            component_root=target,
            invocations=invocations,
            upstream_dependency_digests=UPSTREAM_DIGESTS,
        )


def test_component_rejects_upstream_pub_drift(tmp_path: Path) -> None:
    project, snapshot, invocations = _snapshot(tmp_path)
    parent = tmp_path / "components"
    parent.mkdir()
    target = parent / "android"
    component.write_android_gradle_component(
        project_root=project,
        snapshot=snapshot,
        invocations=invocations,
        upstream_dependency_digests=UPSTREAM_DIGESTS,
        destination=target,
    )

    with pytest.raises(ValueError, match="upstream Pub"):
        component.load_android_gradle_component(
            project_root=project,
            component_root=target,
            invocations=invocations,
            upstream_dependency_digests={
                **UPSTREAM_DIGESTS,
                "productionPub": "sha256:" + "e" * 64,
            },
        )
