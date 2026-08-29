"""Patrol has an exact hosted-Pub capsule independent from production Pub."""

# spec_ref: specs/feature-tree/runtime/runtime-config/design.md#dec-003

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from quwoquan_ops.cli.lib.package_reuse import patrol_pub_store
from quwoquan_ops.cli.lib.package_reuse.patrol_pub_cache import (
    PATROL_HOST_RELATIVE,
    PATROL_PUB_DEPENDENCY_TREE,
    build_patrol_pub_cache_snapshot,
    patrol_resolution_input_paths,
)
from quwoquan_ops.cli.lib.package_reuse.patrol_pub_projection import (
    materialize_capsule_patrol_pub_cache,
)
from quwoquan_ops.cli.lib.package_reuse.patrol_pub_store import (
    copy_patrol_pub_snapshot_to_capsule,
    load_patrol_pub_cache_snapshot_at,
    patrol_capsule_snapshot,
    write_patrol_pub_cache_snapshot,
)

_FLUTTER = {
    "flutterVersion": "3.47.0",
    "flutterCommandResolutionDigest": "sha256:" + "f" * 64,
}


@pytest.fixture(autouse=True)
def _restore_tmp_permissions_for_pytest_cleanup(tmp_path: Path):
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


def _hosted_entry(name: str, version: str, archive_sha: str) -> str:
    return (
        f"  {name}:\n"
        "    dependency: transitive\n"
        "    description:\n"
        f"      name: {name}\n"
        f"      sha256: {archive_sha}\n"
        "      url: https://pub.flutter-io.cn\n"
        "    source: hosted\n"
        f"    version: {version}\n"
    )


def _path_entry(name: str, relative: str) -> str:
    return (
        f"  {name}:\n"
        "    dependency: direct main\n"
        "    description:\n"
        f"      path: {relative}\n"
        "      relative: true\n"
        "    source: path\n"
        "    version: 1.0.0\n"
    )


def _repo(tmp_path: Path) -> tuple[Path, dict[tuple[str, str], str]]:
    root = tmp_path / "repo"
    app = root / "quwoquan_app"
    host = root / PATROL_HOST_RELATIVE
    plugin = app / "vendor/plugin_a"
    path_package = app / "packages/path_b"
    host.mkdir(parents=True)
    plugin.mkdir(parents=True)
    path_package.mkdir(parents=True)
    (app / ".flutter-version").write_text("3.47.0\n", encoding="ascii")
    (app / "pubspec.yaml").write_text(
        "name: fixture_app\n"
        "version: 1.0.0\n"
        "dependencies:\n"
        "  plugin_a:\n"
        "    path: vendor/plugin_a\n",
        encoding="utf-8",
    )
    (plugin / "pubspec.yaml").write_text(
        "name: plugin_a\n"
        "version: 1.0.0\n"
        "dependencies:\n"
        "  path_b:\n"
        "    path: ../../packages/path_b\n",
        encoding="utf-8",
    )
    (path_package / "pubspec.yaml").write_text(
        "name: path_b\nversion: 1.0.0\n", encoding="utf-8"
    )
    (host / "pubspec.yaml").write_text(
        "name: patrol_fixture\n"
        "version: 1.0.0\n"
        "dependencies:\n"
        "  fixture_app:\n"
        "    path: ../..\n"
        "  path_b:\n"
        "    path: ../../packages/path_b\n"
        "dependency_overrides:\n"
        "  plugin_a:\n"
        "    path: ../../vendor/plugin_a\n",
        encoding="utf-8",
    )
    hashes = {
        ("patrol_only", "2.0.0"): "a" * 64,
        ("conflict_pkg", "2.0.0"): "b" * 64,
        ("production_only", "1.0.0"): "c" * 64,
        ("conflict_pkg", "1.0.0"): "d" * 64,
    }
    (host / "pubspec.lock").write_text(
        "packages:\n"
        + _hosted_entry("patrol_only", "2.0.0", hashes[("patrol_only", "2.0.0")])
        + _hosted_entry("conflict_pkg", "2.0.0", hashes[("conflict_pkg", "2.0.0")])
        + _path_entry("fixture_app", "../..")
        + _path_entry("plugin_a", "../../vendor/plugin_a")
        + _path_entry("path_b", "../../packages/path_b"),
        encoding="utf-8",
    )
    (app / "pubspec.lock").write_text(
        "packages:\n"
        + _hosted_entry(
            "production_only", "1.0.0", hashes[("production_only", "1.0.0")]
        )
        + _hosted_entry("conflict_pkg", "1.0.0", hashes[("conflict_pkg", "1.0.0")]),
        encoding="utf-8",
    )
    return root, hashes


def _union_cache(tmp_path: Path, hashes: dict[tuple[str, str], str]) -> Path:
    cache = tmp_path / "private-union-cache"
    for (name, version), archive_sha in hashes.items():
        package = cache / f"hosted/pub.flutter-io.cn/{name}-{version}"
        package.mkdir(parents=True)
        (package / "pubspec.yaml").write_text(
            f"name: {name}\nversion: {version}\n", encoding="utf-8"
        )
        (package / "lib.dart").write_text(
            f"const identity = '{name}-{version}';\n", encoding="utf-8"
        )
        archive = cache / f"hosted-hashes/pub.flutter-io.cn/{name}-{version}.sha256"
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_text(archive_sha + "\n", encoding="ascii")
    return cache


def _snapshot(tmp_path: Path):
    repo, hashes = _repo(tmp_path)
    cache = _union_cache(tmp_path, hashes)
    return (
        repo,
        cache,
        build_patrol_pub_cache_snapshot(
            repo_root=repo,
            cache_root=cache,
            flutter_identity=_FLUTTER,
        ),
    )


def _capsule(repo: Path, snapshot, destination: Path):
    destination.mkdir()
    shutil.copytree(repo, destination / "repo")
    marker = copy_patrol_pub_snapshot_to_capsule(
        snapshot=snapshot,
        capsule_root=destination,
    )
    return marker


def test_union_cache_selects_only_patrol_lock_and_binds_recursive_path_pubspecs(
    tmp_path: Path,
) -> None:
    repo, cache, snapshot = _snapshot(tmp_path)

    packages = {
        (item["name"], item["version"]) for item in snapshot.manifest["hostedPackages"]
    }
    assert packages == {("patrol_only", "2.0.0"), ("conflict_pkg", "2.0.0")}
    assert not any("production_only" in item.relative for item in snapshot.files)
    assert not any("conflict_pkg-1.0.0" in item.relative for item in snapshot.files)
    assert (cache / "hosted/pub.flutter-io.cn/production_only-1.0.0").is_dir()
    paths = {
        path.relative_to(repo).as_posix()
        for path in patrol_resolution_input_paths(repo)
    }
    assert paths == {
        "quwoquan_app/.flutter-version",
        "quwoquan_app/packages/path_b/pubspec.yaml",
        "quwoquan_app/pubspec.yaml",
        "quwoquan_app/test_host/patrol/pubspec.lock",
        "quwoquan_app/test_host/patrol/pubspec.yaml",
        "quwoquan_app/vendor/plugin_a/pubspec.yaml",
    }

    managed = write_patrol_pub_cache_snapshot(
        snapshot=snapshot,
        destination=tmp_path / "managed",
        repo_root=repo,
    )
    loaded = load_patrol_pub_cache_snapshot_at(
        repo_root=repo,
        snapshot_root=managed,
        expected_flutter=_FLUTTER,
    )
    assert loaded.manifest == snapshot.manifest
    selected_source = cache / "hosted/pub.flutter-io.cn/patrol_only-2.0.0/lib.dart"
    selected_copy = managed / "pub/hosted/pub.flutter-io.cn/patrol_only-2.0.0/lib.dart"
    assert selected_source.stat().st_ino != selected_copy.stat().st_ino


def test_capsule_projects_exact_patrol_cache_without_global_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _cache, snapshot = _snapshot(tmp_path)
    capsule = tmp_path / "capsule"
    marker = _capsule(repo, snapshot, capsule)
    readback = patrol_capsule_snapshot(
        capsule_root=capsule,
        manifest_entries=[marker],
    )
    assert readback is not None and readback.manifest == snapshot.manifest
    projection = tmp_path / "projection"
    shutil.copytree(capsule / "repo", projection)
    untrusted_global = tmp_path / "developer-global-pub-cache"
    monkeypatch.setenv("PUB_CACHE", str(untrusted_global))
    monkeypatch.setattr(
        patrol_pub_store, "current_flutter_identity", lambda: dict(_FLUTTER)
    )

    projected = materialize_capsule_patrol_pub_cache(
        capsule_root=capsule,
        manifest_entries=[marker],
        projection_root=projection,
    )

    assert projected != untrusted_global
    assert (projected / "hosted/pub.flutter-io.cn/patrol_only-2.0.0").is_dir()
    assert (projected / "hosted/pub.flutter-io.cn/conflict_pkg-2.0.0").is_dir()
    assert not (projected / "hosted/pub.flutter-io.cn/production_only-1.0.0").exists()
    assert not (projected / "hosted/pub.flutter-io.cn/conflict_pkg-1.0.0").exists()


@pytest.mark.parametrize(
    "relative",
    [
        "quwoquan_app/test_host/patrol/pubspec.yaml",
        "quwoquan_app/vendor/plugin_a/pubspec.yaml",
        "quwoquan_app/.flutter-version",
    ],
)
def test_managed_snapshot_rejects_recursive_resolution_input_drift(
    tmp_path: Path,
    relative: str,
) -> None:
    repo, _cache, snapshot = _snapshot(tmp_path)
    managed = write_patrol_pub_cache_snapshot(
        snapshot=snapshot,
        destination=tmp_path / "managed",
        repo_root=repo,
    )
    source = repo / relative
    source.write_text(
        source.read_text(encoding="utf-8") + "# drift\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="stale for resolution inputs"):
        load_patrol_pub_cache_snapshot_at(
            repo_root=repo,
            snapshot_root=managed,
            expected_flutter=_FLUTTER,
        )


@pytest.mark.parametrize("node_kind", ["symlink", "hardlink", "fifo"])
def test_sync_rejects_unsafe_selected_package_nodes(
    tmp_path: Path,
    node_kind: str,
) -> None:
    repo, hashes = _repo(tmp_path)
    cache = _union_cache(tmp_path, hashes)
    package = cache / "hosted/pub.flutter-io.cn/patrol_only-2.0.0"
    if node_kind == "symlink":
        (package / "linked.dart").symlink_to("lib.dart")
    elif node_kind == "hardlink":
        os.link(package / "lib.dart", package / "hardlinked.dart")
    else:
        os.mkfifo(package / "special.pipe")

    with pytest.raises(ValueError, match="symlink|hardlink|special node"):
        build_patrol_pub_cache_snapshot(
            repo_root=repo,
            cache_root=cache,
            flutter_identity=_FLUTTER,
        )


def test_managed_snapshot_rejects_extra_bytes_and_capsule_marker_drift(
    tmp_path: Path,
) -> None:
    repo, _cache, snapshot = _snapshot(tmp_path)
    managed = write_patrol_pub_cache_snapshot(
        snapshot=snapshot,
        destination=tmp_path / "managed",
        repo_root=repo,
    )
    injected_parent = managed / "pub/hosted/pub.flutter-io.cn/patrol_only-2.0.0"
    injected_parent.chmod(0o755)
    (injected_parent / "injected.dart").write_text("bad\n", encoding="utf-8")
    (injected_parent / "injected.dart").chmod(0o444)
    injected_parent.chmod(0o555)

    with pytest.raises(ValueError, match="unlocked bytes|tree drifted"):
        load_patrol_pub_cache_snapshot_at(
            repo_root=repo,
            snapshot_root=managed,
            expected_flutter=_FLUTTER,
        )

    capsule = tmp_path / "capsule"
    marker = _capsule(repo, snapshot, capsule)
    duplicate = dict(marker)
    with pytest.raises(ValueError, match="missing or duplicated"):
        patrol_capsule_snapshot(
            capsule_root=capsule,
            manifest_entries=[marker, duplicate],
        )


def test_projection_rejects_flutter_drift_and_missing_explicit_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _cache, snapshot = _snapshot(tmp_path)
    capsule = tmp_path / "capsule"
    marker = _capsule(repo, snapshot, capsule)
    projection = tmp_path / "projection"
    shutil.copytree(capsule / "repo", projection)
    monkeypatch.setenv("PUB_CACHE", str(tmp_path / "global-valid-cache"))
    monkeypatch.setattr(
        patrol_pub_store,
        "current_flutter_identity",
        lambda: {
            "flutterVersion": "3.48.0",
            "flutterCommandResolutionDigest": "sha256:" + "e" * 64,
        },
    )

    with pytest.raises(ValueError, match="Flutter toolchain drifted"):
        materialize_capsule_patrol_pub_cache(
            capsule_root=capsule,
            manifest_entries=[marker],
            projection_root=projection,
        )

    with pytest.raises(ValueError, match="unavailable"):
        build_patrol_pub_cache_snapshot(
            repo_root=repo,
            cache_root=tmp_path / "explicit-missing-cache",
            flutter_identity=_FLUTTER,
        )


def test_capsule_rejects_writable_tree_and_symlink_projection_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _cache, snapshot = _snapshot(tmp_path)
    capsule = tmp_path / "capsule"
    marker = _capsule(repo, snapshot, capsule)
    writable = capsule / PATROL_PUB_DEPENDENCY_TREE / "hosted"
    writable.chmod(0o755)
    with pytest.raises(ValueError, match="writable bytes"):
        patrol_capsule_snapshot(capsule_root=capsule, manifest_entries=[marker])
    writable.chmod(0o555)

    projection = tmp_path / "projection"
    shutil.copytree(capsule / "repo", projection)
    host = projection / PATROL_HOST_RELATIVE
    external = tmp_path / "external-dot-tool"
    external.mkdir()
    (host / ".dart_tool").symlink_to(external, target_is_directory=True)
    monkeypatch.setattr(
        patrol_pub_store, "current_flutter_identity", lambda: dict(_FLUTTER)
    )
    with pytest.raises(ValueError, match="unavailable or linked"):
        materialize_capsule_patrol_pub_cache(
            capsule_root=capsule,
            manifest_entries=[marker],
            projection_root=projection,
        )
