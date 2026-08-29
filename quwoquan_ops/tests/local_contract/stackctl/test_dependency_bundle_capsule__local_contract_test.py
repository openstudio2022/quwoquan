"""Package dependency selection reads one active generation for all consumers."""

# spec_ref: specs/feature-tree/runtime/runtime-config/design.md#dec-003

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from quwoquan_ops.cli.lib.package_reuse import dependency_bundle_capsule as capsule
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
    monkeypatch.setattr(capsule, "resolve_cocoapods_executable", lambda _value: "/pod")
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
