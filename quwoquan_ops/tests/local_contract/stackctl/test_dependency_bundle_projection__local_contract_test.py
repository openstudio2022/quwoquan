"""One package projection routes all commands through one dependency bundle."""

# spec_ref: specs/feature-tree/runtime/runtime-config/design.md#dec-003

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from quwoquan_ops.cli.lib.package_reuse import (
    dependency_bundle_projection as projection,
)
from quwoquan_ops.cli.lib.package_reuse.pub_cache_capsule import _digest_bytes


def _stub_capsule(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, SimpleNamespace, SimpleNamespace]:
    capsule = tmp_path / "capsule"
    capsule.mkdir()
    manifest = capsule / "manifest.json"
    manifest.write_text("{}\n", encoding="ascii")
    production = SimpleNamespace(encoded_sync_manifest=b"production")
    patrol = SimpleNamespace(encoded_sync_manifest=b"patrol")
    monkeypatch.setattr(
        projection,
        "verify_package_input_capsule",
        lambda _root: {"entries": [{"logicalPath": "fixture"}]},
    )
    monkeypatch.setattr(
        projection,
        "verify_dependency_bundle_capsule",
        lambda **_kwargs: (production, patrol, object(), object(), object()),
    )
    monkeypatch.setattr(
        projection,
        "materialize_capsule_pub_cache",
        lambda **_kwargs: tmp_path / "production-pub",
    )
    monkeypatch.setattr(
        projection,
        "materialize_capsule_patrol_pub_cache",
        lambda **_kwargs: tmp_path / "patrol-pub",
    )
    return manifest, production, patrol


def test_android_projection_forces_one_private_gradle_home_for_both_hosts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, _production, _patrol = _stub_capsule(tmp_path, monkeypatch)
    gradle = tmp_path / "gradle"
    monkeypatch.setattr(
        projection,
        "materialize_capsule_android_gradle_home",
        lambda **_kwargs: gradle,
    )
    monkeypatch.setattr(
        projection,
        "private_gradle_environment",
        lambda *, gradle_user_home, base: {
            **base,
            "GRADLE_USER_HOME": str(gradle_user_home),
        },
    )

    result = projection.materialize_dependency_bundle_projection(
        manifest_path=manifest,
        projection_root=tmp_path / "repo",
        private_state_root=tmp_path / "private",
        platform="android",
        base_environment={"SAFE": "1"},
        include_patrol=True,
    )

    assert result.android_gradle_home == gradle
    assert result.production_environment["SAFE"] == "1"
    assert result.production_environment["PUB_CACHE"] == str(
        tmp_path / "production-pub"
    )
    assert result.production_environment["GRADLE_USER_HOME"] == str(gradle)
    assert result.production_environment["HOME"].startswith(str(tmp_path / "private"))
    assert result.production_environment["XDG_CONFIG_HOME"].startswith(
        str(tmp_path / "private")
    )
    assert result.production_environment["FLUTTER_SWIFT_PACKAGE_MANAGER"] == "false"
    assert result.patrol_environment is not None
    assert result.patrol_environment["SAFE"] == "1"
    assert result.patrol_environment["PUB_CACHE"] == str(tmp_path / "patrol-pub")
    assert result.patrol_environment["GRADLE_USER_HOME"] == str(gradle)
    assert result.patrol_environment["HOME"].startswith(str(tmp_path / "private"))
    assert result.patrol_environment["FLUTTER_SWIFT_PACKAGE_MANAGER"] == "false"


def test_web_projection_uses_fresh_flutter_home_and_ignores_global_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, _production, _patrol = _stub_capsule(tmp_path, monkeypatch)

    result = projection.materialize_dependency_bundle_projection(
        manifest_path=manifest,
        projection_root=tmp_path / "repo",
        private_state_root=tmp_path / "private",
        platform="web",
        base_environment={
            "HOME": "/developer/home",
            "XDG_CONFIG_HOME": "/developer/config",
            "HTTP_PROXY": "http://developer-proxy.invalid",
        },
    )

    assert result.production_environment["HOME"].startswith(str(tmp_path / "private"))
    assert result.production_environment["XDG_CONFIG_HOME"].startswith(
        str(tmp_path / "private")
    )
    assert result.production_environment["FLUTTER_SWIFT_PACKAGE_MANAGER"] == "false"
    assert "HTTP_PROXY" not in result.production_environment


def test_ios_projection_replays_each_host_against_its_own_pub_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, production, patrol = _stub_capsule(tmp_path, monkeypatch)
    calls: list[dict[str, object]] = []

    def project_ios(**kwargs):
        calls.append(kwargs)
        host = str(kwargs["dependency_host"])
        return object(), object(), {**kwargs["base_environment"], "HOST": host}

    monkeypatch.setattr(projection, "_ios_projection", project_ios)

    result = projection.materialize_dependency_bundle_projection(
        manifest_path=manifest,
        projection_root=tmp_path / "repo",
        private_state_root=tmp_path / "private",
        platform="ios",
        base_environment={"SAFE": "1"},
        pod_executable="/fixture/pod",
        include_patrol=True,
    )

    assert [call["dependency_host"] for call in calls] == [
        projection.IOS_POD_PRODUCTION_HOST,
        projection.IOS_POD_PATROL_HOST,
    ]
    assert calls[0]["upstream_dependency_digest"] == _digest_bytes(
        production.encoded_sync_manifest
    )
    assert calls[1]["upstream_dependency_digest"] == _digest_bytes(
        patrol.encoded_sync_manifest
    )
    assert result.production_environment["HOST"] == "production"
    assert result.production_environment["FLUTTER_SWIFT_PACKAGE_MANAGER"] == "false"
    assert result.patrol_environment is not None
    assert result.patrol_environment["HOST"] == "patrol"
    assert result.patrol_environment["FLUTTER_SWIFT_PACKAGE_MANAGER"] == "false"
