"""Package dependency selection reads one active generation for all consumers."""

# spec_ref: specs/feature-tree/runtime/runtime-config/design.md#dec-003

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from quwoquan_ops.cli.lib.app_dependency_toolchain import AppDependencyToolchainError
from quwoquan_ops.cli.lib.package_reuse import dependency_bundle_capsule as capsule
from quwoquan_ops.cli.lib.package_reuse.ios_pod_inputs import (
    IOS_POD_PATROL_HOST,
    IOS_POD_PRODUCTION_HOST,
)
from quwoquan_ops.cli.lib.package_reuse.pub_cache_capsule import _digest_bytes


class _Bundle:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._manifests = {
            "productionPub": {"schema": "prod-pub"},
            "patrolPub": {"schema": "patrol-pub"},
            "productionIosPods": {
                "schema": "prod-ios",
                "resolutionInputs": [
                    {"logicalPath": "quwoquan_app/ios/Podfile"}
                ],
            },
            "patrolIosPods": {
                "schema": "patrol-ios",
                "resolutionInputs": [
                    {"logicalPath": "quwoquan_app/test_host/patrol/ios/Podfile"}
                ],
            },
            "androidGradle": {
                "schema": "android-sync",
                "dependency": {"schema": "android-tree"},
            },
        }

    def component_root(self, name: str) -> Path:
        return self._root / name

    def component_manifest(self, name: str):
        return self._manifests[name]


def test_loader_keeps_pub_pod_and_gradle_in_one_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _Bundle(tmp_path / "components")
    production_pub = SimpleNamespace(
        encoded_sync_manifest=b"production-pub",
        sync_manifest=bundle.component_manifest("productionPub"),
    )
    patrol_pub = SimpleNamespace(
        encoded_sync_manifest=b"patrol-pub",
        sync_manifest=bundle.component_manifest("patrolPub"),
    )
    pod_calls: list[dict[str, object]] = []

    monkeypatch.setattr(capsule, "load_active_dependency_bundle", lambda **_kw: bundle)
    monkeypatch.setattr(
        capsule,
        "current_flutter_identity",
        lambda: {
            "flutterVersion": "3.47.0",
            "flutterCommandResolutionDigest": "sha256:" + "a" * 64,
        },
    )
    monkeypatch.setattr(
        capsule, "load_pub_cache_snapshot_at", lambda **_kw: production_pub
    )
    monkeypatch.setattr(
        capsule, "load_patrol_pub_cache_snapshot_at", lambda **_kw: patrol_pub
    )
    pod_identity = SimpleNamespace(executable=Path("/pod"))
    monkeypatch.setattr(
        capsule,
        "resolve_cocoapods_identity",
        lambda *, search_path: pod_identity,
    )
    monkeypatch.setattr(
        capsule,
        "ios_pod_resolution_inputs",
        lambda **_kw: {"fixture.podspec": tmp_path / "fixture.podspec"},
    )

    def load_pod(**kwargs):
        pod_calls.append(kwargs)
        name = "productionIosPods" if "test_host" not in str(kwargs["expected_podfile_lock"]) else "patrolIosPods"
        return SimpleNamespace(manifest=bundle.component_manifest(name))

    monkeypatch.setattr(capsule, "load_verified_ios_pod_capsule", load_pod)
    android = SimpleNamespace(manifest={"schema": "android-tree"})
    monkeypatch.setattr(capsule, "load_android_gradle_component", lambda **_kw: android)

    loaded = capsule.load_managed_dependency_snapshots(repo_root=tmp_path)

    assert loaded.production_pub is production_pub
    assert loaded.patrol_pub is patrol_pub
    assert len(pod_calls) == 2
    assert pod_calls[0]["upstream_dependency_digest"] == _digest_bytes(
        b"production-pub"
    )
    assert pod_calls[1]["upstream_dependency_digest"] == _digest_bytes(b"patrol-pub")
    assert loaded.android_gradle is android


def test_loader_resolves_cocoapods_from_path_when_environment_identity_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _Bundle(tmp_path / "components")
    production_pub = SimpleNamespace(
        encoded_sync_manifest=b"production-pub",
        sync_manifest=bundle.component_manifest("productionPub"),
    )
    patrol_pub = SimpleNamespace(
        encoded_sync_manifest=b"patrol-pub",
        sync_manifest=bundle.component_manifest("patrolPub"),
    )
    pod = tmp_path / "canonical/bin/pod"
    pod.parent.mkdir(parents=True)
    pod.write_text("fixture", encoding="utf-8")
    monkeypatch.setenv("PATH", str(pod.parent))
    for key in capsule.COCOAPODS_ENVIRONMENT_KEYS:
        monkeypatch.delenv(key, raising=False)
    observed: dict[str, object] = {}

    monkeypatch.setattr(capsule, "load_active_dependency_bundle", lambda **_kw: bundle)
    monkeypatch.setattr(
        capsule,
        "current_flutter_identity",
        lambda: {
            "flutterVersion": "3.47.0",
            "flutterCommandResolutionDigest": "sha256:" + "a" * 64,
        },
    )
    monkeypatch.setattr(
        capsule, "load_pub_cache_snapshot_at", lambda **_kw: production_pub
    )
    monkeypatch.setattr(
        capsule, "load_patrol_pub_cache_snapshot_at", lambda **_kw: patrol_pub
    )

    def resolve(*, search_path):
        observed["search_path"] = search_path
        return SimpleNamespace(executable=pod)

    monkeypatch.setattr(capsule, "resolve_cocoapods_identity", resolve)
    monkeypatch.setattr(
        capsule,
        "cocoapods_identity_from_environment",
        lambda _environment: (_ for _ in ()).throw(
            AssertionError("absent identity must resolve once from PATH")
        ),
    )
    monkeypatch.setattr(capsule, "ios_pod_resolution_inputs", lambda **_kw: {})

    def load_pod(**kwargs):
        name = (
            "productionIosPods"
            if "test_host" not in str(kwargs["expected_podfile_lock"])
            else "patrolIosPods"
        )
        return SimpleNamespace(manifest=bundle.component_manifest(name))

    monkeypatch.setattr(capsule, "load_verified_ios_pod_capsule", load_pod)
    monkeypatch.setattr(
        capsule,
        "canonical_android_uat_gradle_invocations",
        lambda _repository: [],
    )
    monkeypatch.setattr(
        capsule,
        "load_android_gradle_component",
        lambda **_kw: SimpleNamespace(manifest={"schema": "android-tree"}),
    )

    loaded = capsule.load_managed_dependency_snapshots(repo_root=tmp_path)

    assert loaded.production_pub is production_pub
    assert observed == {"search_path": str(pod.parent)}


def test_loader_rejects_partial_cocoapods_environment_as_mixed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _Bundle(tmp_path / "components")
    production_pub = SimpleNamespace(
        encoded_sync_manifest=b"production-pub",
        sync_manifest=bundle.component_manifest("productionPub"),
    )
    patrol_pub = SimpleNamespace(
        encoded_sync_manifest=b"patrol-pub",
        sync_manifest=bundle.component_manifest("patrolPub"),
    )
    for key in capsule.COCOAPODS_ENVIRONMENT_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("QWQ_COCOAPODS_VERSION", "1.16.2")

    monkeypatch.setattr(capsule, "load_active_dependency_bundle", lambda **_kw: bundle)
    monkeypatch.setattr(
        capsule,
        "current_flutter_identity",
        lambda: {
            "flutterVersion": "3.47.0",
            "flutterCommandResolutionDigest": "sha256:" + "a" * 64,
        },
    )
    monkeypatch.setattr(
        capsule, "load_pub_cache_snapshot_at", lambda **_kw: production_pub
    )
    monkeypatch.setattr(
        capsule, "load_patrol_pub_cache_snapshot_at", lambda **_kw: patrol_pub
    )
    monkeypatch.setattr(
        capsule,
        "resolve_cocoapods_identity",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("partial identity must not fall back to PATH")
        ),
    )

    with pytest.raises(ValueError, match="cocoapods_mixed"):
        capsule.load_managed_dependency_snapshots(repo_root=tmp_path)


def test_loader_explicit_pod_uses_declared_physical_directory_not_ambient_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _Bundle(tmp_path / "components")
    production_pub = SimpleNamespace(
        encoded_sync_manifest=b"production-pub",
        sync_manifest=bundle.component_manifest("productionPub"),
    )
    patrol_pub = SimpleNamespace(
        encoded_sync_manifest=b"patrol-pub",
        sync_manifest=bundle.component_manifest("patrolPub"),
    )
    explicit = tmp_path / "canonical/bin/pod"
    explicit.parent.mkdir(parents=True)
    explicit.write_text("fixture", encoding="utf-8")
    hostile = tmp_path / "hostile/bin"
    hostile.mkdir(parents=True)
    monkeypatch.setenv("PATH", str(hostile))
    observed: dict[str, object] = {}

    monkeypatch.setattr(capsule, "load_active_dependency_bundle", lambda **_kw: bundle)
    monkeypatch.setattr(
        capsule,
        "current_flutter_identity",
        lambda: {
            "flutterVersion": "3.47.0",
            "flutterCommandResolutionDigest": "sha256:" + "a" * 64,
        },
    )
    monkeypatch.setattr(
        capsule, "load_pub_cache_snapshot_at", lambda **_kw: production_pub
    )
    monkeypatch.setattr(
        capsule, "load_patrol_pub_cache_snapshot_at", lambda **_kw: patrol_pub
    )

    def resolve(candidate, *, search_path):
        observed.update(candidate=candidate, search_path=search_path)
        return SimpleNamespace(executable=explicit)

    monkeypatch.setattr(capsule, "resolve_cocoapods_identity", resolve)
    monkeypatch.setattr(capsule, "ios_pod_resolution_inputs", lambda **_kw: {})

    def load_pod(**kwargs):
        name = (
            "productionIosPods"
            if "test_host" not in str(kwargs["expected_podfile_lock"])
            else "patrolIosPods"
        )
        return SimpleNamespace(manifest=bundle.component_manifest(name))

    monkeypatch.setattr(capsule, "load_verified_ios_pod_capsule", load_pod)
    monkeypatch.setattr(
        capsule,
        "canonical_android_uat_gradle_invocations",
        lambda _repository: [],
    )
    monkeypatch.setattr(
        capsule,
        "load_android_gradle_component",
        lambda **_kw: SimpleNamespace(manifest={"schema": "android-tree"}),
    )

    capsule.load_managed_dependency_snapshots(
        repo_root=tmp_path,
        pod_executable=explicit,
    )

    assert observed == {
        "candidate": explicit,
        "search_path": str(explicit.parent),
    }


def test_digest_identity_contains_all_five_component_markers() -> None:
    snapshots = SimpleNamespace(
        production_pub=SimpleNamespace(encoded_sync_manifest=b"a"),
        patrol_pub=SimpleNamespace(encoded_sync_manifest=b"b"),
        production_ios_pods=SimpleNamespace(encoded_manifest=b"c"),
        patrol_ios_pods=SimpleNamespace(encoded_manifest=b"d"),
        android_gradle=SimpleNamespace(encoded_manifest=b"e"),
    )

    records = capsule.dependency_bundle_digest_entries(snapshots)

    assert len(records) == 5
    assert len({logical for logical, _kind, _content in records}) == 5


@pytest.mark.parametrize(
    ("host", "ios_relative"),
    (
        (IOS_POD_PRODUCTION_HOST, Path("quwoquan_app/ios")),
        (IOS_POD_PATROL_HOST, Path("quwoquan_app/test_host/patrol/ios")),
    ),
)
def test_package_capsule_verifier_binds_each_host_podfile_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    host: str,
    ios_relative: Path,
) -> None:
    capsule_root = tmp_path / "capsule"
    ios_root = capsule_root / "repo" / ios_relative
    ios_root.mkdir(parents=True)
    (ios_root / "Podfile").write_bytes(b"podfile-must-not-be-used")
    expected_lock = ios_root / "Podfile.lock"
    expected_lock.write_bytes(b"fresh-lock")
    sentinel = object()

    monkeypatch.setattr(capsule, "_capsule_marker", lambda **_kwargs: b"marker")
    monkeypatch.setattr(capsule, "ios_pod_resolution_inputs", lambda **_kwargs: {})

    def load(**kwargs):
        assert kwargs["expected_podfile_lock"] == expected_lock
        if kwargs["expected_podfile_lock"].read_bytes() != b"fresh-lock":
            raise ValueError("iOS Pod capsule is stale for current Podfile.lock")
        return sentinel

    monkeypatch.setattr(capsule, "load_ios_pod_capsule_bytes", load)

    assert (
        capsule._ios_capsule_snapshot(
            capsule_root=capsule_root,
            manifest_entries=[],
            dependency_host=host,
            upstream_dependency_digest="sha256:" + "a" * 64,
        )
        is sentinel
    )


@pytest.mark.parametrize(
    ("host", "ios_relative"),
    (
        (IOS_POD_PRODUCTION_HOST, Path("quwoquan_app/ios")),
        (IOS_POD_PATROL_HOST, Path("quwoquan_app/test_host/patrol/ios")),
    ),
)
def test_package_capsule_verifier_rejects_stale_host_podfile_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    host: str,
    ios_relative: Path,
) -> None:
    capsule_root = tmp_path / "capsule"
    ios_root = capsule_root / "repo" / ios_relative
    ios_root.mkdir(parents=True)
    # A wrong implementation that passes Podfile to expected_podfile_lock would
    # accept this decoy and miss the actual stale lock beside it.
    (ios_root / "Podfile").write_bytes(b"snapshot-lock")
    expected_lock = ios_root / "Podfile.lock"
    expected_lock.write_bytes(b"stale-lock")

    monkeypatch.setattr(capsule, "_capsule_marker", lambda **_kwargs: b"marker")
    monkeypatch.setattr(capsule, "ios_pod_resolution_inputs", lambda **_kwargs: {})

    def load(**kwargs):
        if kwargs["expected_podfile_lock"].read_bytes() != b"snapshot-lock":
            raise ValueError("iOS Pod capsule is stale for current Podfile.lock")
        return object()

    monkeypatch.setattr(capsule, "load_ios_pod_capsule_bytes", load)

    with pytest.raises(ValueError, match="stale for current Podfile.lock"):
        capsule._ios_capsule_snapshot(
            capsule_root=capsule_root,
            manifest_entries=[],
            dependency_host=host,
            upstream_dependency_digest="sha256:" + "a" * 64,
        )
