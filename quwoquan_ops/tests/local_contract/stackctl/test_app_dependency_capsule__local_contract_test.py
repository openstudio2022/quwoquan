"""Hosted Pub build inputs come from one lock-bound read-only capsule."""

# spec_ref: specs/feature-tree/runtime/runtime-config/design.md#dec-003

from __future__ import annotations

import hashlib
import json
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from quwoquan_ops.cli.lib import package_reuse
from quwoquan_ops.cli.lib.package_reuse import (
    dependency_bundle,
    input_capsule,
    pub_cache_capsule,
    pub_cache_store,
)
from quwoquan_ops.cli.lib.package_reuse.dependency_fs import remove_private_tree
from quwoquan_ops.cli.lib.package_reuse.pub_cache_capsule import (
    PUB_CACHE_SYNC_MANIFEST_SCHEMA,
    _canonical_bytes,
    _digest_bytes,
    build_pub_cache_snapshot,
    copy_snapshot_tree_with_lock,
    is_canonical_pub_cache_transient,
)


def _repo(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repo"
    app = root / "quwoquan_app"
    app.mkdir(parents=True)
    archive_sha = "a" * 64
    (app / "pubspec.yaml").write_text(
        "name: capsule_fixture\n"
        "environment:\n  sdk: ^3.9.0\n"
        "dependencies:\n  path_fixture:\n    path: packages/path_fixture\n",
        encoding="utf-8",
    )
    (app / ".flutter-version").write_text("3.47.0\n", encoding="ascii")
    path_package = app / "packages/path_fixture"
    path_package.mkdir(parents=True)
    (path_package / "pubspec.yaml").write_text(
        "name: path_fixture\nversion: 0.1.0\n",
        encoding="utf-8",
    )
    (app / "pubspec.lock").write_text(
        "packages:\n"
        "  fixture_pkg:\n"
        "    dependency: transitive\n"
        "    description:\n"
        "      name: fixture_pkg\n"
        f"      sha256: {archive_sha}\n"
        "      url: https://pub.flutter-io.cn\n"
        "    source: hosted\n"
        "    version: 1.2.3\n"
        "  path_fixture:\n"
        "    dependency: direct main\n"
        "    description:\n"
        "      path: packages/path_fixture\n"
        "      relative: true\n"
        "    source: path\n"
        "    version: 0.1.0\n",
        encoding="utf-8",
    )
    (app / "run.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
    subprocess.run(["git", "add", "quwoquan_app"], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Dependency Capsule",
            "-c",
            "user.email=dependency-capsule@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "fixture",
        ],
        cwd=root,
        check=True,
    )
    return root, archive_sha


def _activate_snapshot(repo: Path, output: Path, archive_sha: str) -> None:
    network = output / "network"
    package = network / "hosted/pub.flutter-io.cn/fixture_pkg-1.2.3"
    package.mkdir(parents=True)
    (package / "pubspec.yaml").write_text(
        "name: fixture_pkg\nversion: 1.2.3\n",
        encoding="utf-8",
    )
    (package / "lib.dart").write_text("const fixture = true;\n", encoding="utf-8")
    archive = (
        network
        / "hosted-hashes/pub.flutter-io.cn/fixture_pkg-1.2.3.sha256"
    )
    archive.parent.mkdir(parents=True)
    archive.write_text(archive_sha + "\n", encoding="ascii")
    lock = repo / "quwoquan_app/pubspec.lock"
    snapshot = build_pub_cache_snapshot(lock_path=lock, cache_root=network)
    base = output / "env/repo/local/app-dependency-sync/cache"
    relative = Path("snapshots/face/productionPub")
    target = base / relative
    target.mkdir(parents=True)
    copy_snapshot_tree_with_lock(
        snapshot,
        target / "pub",
        lock_path=lock,
        writable=False,
    )
    wrapper = {
        "schema": PUB_CACHE_SYNC_MANIFEST_SCHEMA,
        "flutterVersion": "3.47.0",
        "flutterCommandResolutionDigest": "sha256:" + "b" * 64,
        **pub_cache_store.resolution_input_identity(repo),
        "dependency": snapshot.manifest,
    }
    (target / "manifest.json").write_text(
        json.dumps(wrapper, sort_keys=True),
        encoding="utf-8",
    )
    components = {
        "productionPub": dependency_bundle.component_declaration(
            snapshot_ref=relative,
            manifest=wrapper,
        )
    }
    for name in dependency_bundle.APP_DEPENDENCY_COMPONENTS[1:]:
        component_manifest = {
            "schema": f"fixture-{name}.v1",
            "treeDigest": "sha256:" + "d" * 64,
            "entryCount": 1,
        }
        component_ref = Path("snapshots/face") / name
        component_root = base / component_ref
        component_root.mkdir(parents=True)
        (component_root / "manifest.json").write_bytes(
            _canonical_bytes(component_manifest)
        )
        components[name] = dependency_bundle.component_declaration(
            snapshot_ref=component_ref,
            manifest=component_manifest,
        )
    receipt_ref = "env/repo/runs/app-dependency-sync/fixture/report.json"
    receipt = {
        "schema": dependency_bundle.APP_DEPENDENCY_BUNDLE_RECEIPT_SCHEMA,
        "claim": "PREPARED_NOT_ACTIVE",
        "attemptId": "face",
        "components": components,
        "activationEvidence": {
            "requiredActiveRef": "env/repo/local/app-dependency-sync/cache/active.json",
            "requiredAttemptId": "face",
        },
    }
    receipt_path = output / receipt_ref
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_bytes(_canonical_bytes(receipt))
    active = {
        "schema": dependency_bundle.APP_DEPENDENCY_BUNDLE_ACTIVE_SCHEMA,
        "attemptId": "face",
        "flutterVersion": "3.47.0",
        "flutterCommandResolutionDigest": "sha256:" + "b" * 64,
        "productionPubResolutionInputDigest": wrapper["resolutionInputDigest"],
        "patrolPubResolutionInputDigest": "sha256:" + "e" * 64,
        "nativeResolutionInputDigest": "sha256:" + "f" * 64,
        "components": components,
        "receiptRef": receipt_ref,
        "receiptDigest": _digest_bytes(_canonical_bytes(receipt)),
    }
    base.mkdir(parents=True, exist_ok=True)
    (base / "active.json").write_text(json.dumps(active), encoding="utf-8")


@pytest.fixture(autouse=True)
def _stable_flutter_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pub_cache_store,
        "current_flutter_identity",
        lambda: {
            "flutterVersion": "3.47.0",
            "flutterCommandResolutionDigest": "sha256:" + "b" * 64,
        },
    )
    monkeypatch.setattr(
        dependency_bundle,
        "_current_source_identity",
        lambda repo: {
            "flutterVersion": "3.47.0",
            "flutterCommandResolutionDigest": "sha256:" + "b" * 64,
            "productionPubResolutionInputDigest": pub_cache_store.resolution_input_identity(
                repo
            )["resolutionInputDigest"],
            "patrolPubResolutionInputDigest": "sha256:" + "e" * 64,
            "nativeResolutionInputDigest": "sha256:" + "f" * 64,
        },
    )

    def load_production_only(*, repo_root: Path):
        return SimpleNamespace(
            production_pub=pub_cache_store.load_managed_pub_cache_snapshot(
                repo_root=repo_root
            )
        )

    def copy_production_only(*, snapshots, capsule_root: Path):
        snapshot = snapshots.production_pub
        content = pub_cache_store.sync_manifest_bytes(snapshot)
        marker = capsule_root / package_reuse.PUB_CACHE_DEPENDENCY_MANIFEST
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_bytes(content)
        marker.chmod(0o444)
        copy_snapshot_tree_with_lock(
            snapshot,
            capsule_root / package_reuse.PUB_CACHE_DEPENDENCY_TREE,
            lock_path=capsule_root / "repo/quwoquan_app/pubspec.lock",
            writable=False,
        )
        return [
            {
                "logicalPath": package_reuse.PUB_CACHE_DEPENDENCY_LOGICAL_PATH,
                "capsulePath": package_reuse.PUB_CACHE_DEPENDENCY_MANIFEST.as_posix(),
                "kind": "file",
                "digest": _digest_bytes(content),
                "size": len(content),
                "mode": 0o444,
            }
        ]

    monkeypatch.setattr(
        input_capsule,
        "load_managed_dependency_snapshots",
        load_production_only,
    )
    monkeypatch.setattr(
        input_capsule,
        "copy_dependency_bundle_to_capsule",
        copy_production_only,
    )
    monkeypatch.setattr(
        input_capsule,
        "verify_dependency_bundle_capsule",
        lambda *, capsule_root, manifest_entries: pub_cache_store.capsule_dependency_snapshot(
            capsule_root=capsule_root,
            manifest_entries=manifest_entries,
        ),
    )


def test_package_capsule_projects_only_the_managed_locked_pub_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, archive_sha = _repo(tmp_path)
    output = tmp_path / "output"
    _activate_snapshot(repo, output, archive_sha)
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    monkeypatch.setattr(package_reuse, "ROOT", repo)
    capsule = tmp_path / "candidate/input-capsule"

    manifest = package_reuse.materialize_package_input_capsule(
        ["quwoquan_app"],
        capsule_root=capsule,
    )

    assert any(
        item["logicalPath"] == package_reuse.PUB_CACHE_DEPENDENCY_LOGICAL_PATH
        for item in manifest["entries"]
    )
    package_reuse.verify_package_input_capsule(capsule)
    projection = tmp_path / "projection"
    shutil.copytree(capsule / "repo", projection)
    for path in projection.rglob("*"):
        if path.is_file():
            path.chmod(0o755 if path.stat().st_mode & 0o111 else 0o644)
        elif path.is_dir():
            path.chmod(0o755)
    projected_cache = package_reuse.materialize_verified_capsule_pub_cache(
        manifest_path=capsule / "manifest.json",
        projection_root=projection,
    )
    assert projected_cache.is_dir()
    assert not any(path.is_symlink() for path in projected_cache.rglob("*"))
    assert (
        projected_cache
        / "hosted/pub.flutter-io.cn/fixture_pkg-1.2.3/lib.dart"
    ).read_text(encoding="utf-8") == "const fixture = true;\n"


def test_capsule_rejects_dependency_tree_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, archive_sha = _repo(tmp_path)
    output = tmp_path / "output"
    _activate_snapshot(repo, output, archive_sha)
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    monkeypatch.setattr(package_reuse, "ROOT", repo)
    capsule = tmp_path / "candidate/input-capsule"
    package_reuse.materialize_package_input_capsule(
        ["quwoquan_app"],
        capsule_root=capsule,
    )
    dependency = (
        capsule
        / "dependencies/dart-pub-cache/hosted/pub.flutter-io.cn/fixture_pkg-1.2.3/lib.dart"
    )
    dependency.chmod(0o644)
    dependency.write_text("const fixture = false;\n", encoding="utf-8")

    with pytest.raises(ValueError, match="capsule tree drifted|snapshot file"):
        package_reuse.verify_package_input_capsule(capsule)


def test_capsule_rejects_unlocked_dependency_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, archive_sha = _repo(tmp_path)
    output = tmp_path / "output"
    _activate_snapshot(repo, output, archive_sha)
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    monkeypatch.setattr(package_reuse, "ROOT", repo)
    capsule = tmp_path / "candidate/input-capsule"
    package_reuse.materialize_package_input_capsule(
        ["quwoquan_app"],
        capsule_root=capsule,
    )
    package_dir = (
        capsule
        / "dependencies/dart-pub-cache/hosted/pub.flutter-io.cn/fixture_pkg-1.2.3"
    )
    package_dir.chmod(0o755)
    (package_dir / "injected.dart").write_text("malicious\n", encoding="utf-8")

    with pytest.raises(ValueError, match="capsule tree drifted|unlocked bytes"):
        package_reuse.verify_package_input_capsule(capsule)


def test_global_pub_cache_is_never_a_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _archive_sha = _repo(tmp_path)
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path / "empty-output"))
    monkeypatch.setattr(package_reuse, "ROOT", repo)
    monkeypatch.setenv("PUB_CACHE", str(tmp_path / "untrusted-global-cache"))

    with pytest.raises(ValueError, match="managed dependency bundle root"):
        package_reuse.materialize_package_input_capsule(
            ["quwoquan_app"],
            capsule_root=tmp_path / "candidate/input-capsule",
        )


def test_dependency_manifest_digest_is_bound_into_capsule_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, archive_sha = _repo(tmp_path)
    output = tmp_path / "output"
    _activate_snapshot(repo, output, archive_sha)
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    monkeypatch.setattr(package_reuse, "ROOT", repo)
    capsule = tmp_path / "candidate/input-capsule"
    manifest = package_reuse.materialize_package_input_capsule(
        ["quwoquan_app"],
        capsule_root=capsule,
    )
    dependency_entry = next(
        item
        for item in manifest["entries"]
        if item["logicalPath"] == package_reuse.PUB_CACHE_DEPENDENCY_LOGICAL_PATH
    )
    encoded = (capsule / dependency_entry["capsulePath"]).read_bytes()
    assert dependency_entry["digest"] == "sha256:" + hashlib.sha256(encoded).hexdigest()
    assert dependency_entry["size"] == len(encoded)
    assert manifest["deploymentInputFileCount"] == len(manifest["entries"])


@pytest.mark.parametrize(
    "relative",
    [
        "quwoquan_app/pubspec.yaml",
        "quwoquan_app/packages/path_fixture/pubspec.yaml",
    ],
)
def test_sync_rejects_root_or_path_pubspec_resolution_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
) -> None:
    repo, archive_sha = _repo(tmp_path)
    output = tmp_path / "output"
    _activate_snapshot(repo, output, archive_sha)
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    path = repo / relative
    path.write_text(path.read_text(encoding="utf-8") + "# drift\n", encoding="utf-8")

    with pytest.raises(
        ValueError, match="stale for productionPubResolutionInputDigest"
    ):
        pub_cache_store.load_managed_pub_cache_snapshot(repo_root=repo)


def test_sync_rejects_flutter_toolchain_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, archive_sha = _repo(tmp_path)
    output = tmp_path / "output"
    _activate_snapshot(repo, output, archive_sha)
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    monkeypatch.setattr(
        pub_cache_store,
        "current_flutter_identity",
        lambda: {
            "flutterVersion": "3.47.1",
            "flutterCommandResolutionDigest": "sha256:" + "c" * 64,
        },
    )

    with pytest.raises(ValueError, match="stale for Flutter toolchain"):
        pub_cache_store.load_managed_pub_cache_snapshot(repo_root=repo)


def test_managed_snapshot_rejects_symlink_ancestor_and_hardlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, archive_sha = _repo(tmp_path)
    output = tmp_path / "output"
    _activate_snapshot(repo, output, archive_sha)
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    base = output / "env/repo/local/app-dependency-sync/cache"
    snapshots = base / "snapshots"
    displaced = base / "displaced-snapshots"
    snapshots.rename(displaced)
    snapshots.symlink_to(displaced, target_is_directory=True)

    with pytest.raises(ValueError, match="unavailable or linked"):
        pub_cache_store.load_managed_pub_cache_snapshot(repo_root=repo)

    snapshots.unlink()
    displaced.rename(snapshots)
    locked_file = next((snapshots).rglob("lib.dart"))
    (output / "hardlink-witness").hardlink_to(locked_file)
    with pytest.raises(ValueError, match="single-link regular file"):
        pub_cache_store.load_managed_pub_cache_snapshot(repo_root=repo)


def test_snapshot_binds_empty_directory_and_readonly_cleanup_converges(
    tmp_path: Path,
) -> None:
    repo, archive_sha = _repo(tmp_path)
    network = tmp_path / "network"
    package = network / "hosted/pub.flutter-io.cn/fixture_pkg-1.2.3"
    package.mkdir(parents=True)
    (package / "lib.dart").write_text("const fixture = true;\n", encoding="utf-8")
    (package / "empty").mkdir()
    archive = network / "hosted-hashes/pub.flutter-io.cn/fixture_pkg-1.2.3.sha256"
    archive.parent.mkdir(parents=True)
    archive.write_text(archive_sha + "\n", encoding="ascii")

    snapshot = build_pub_cache_snapshot(
        lock_path=repo / "quwoquan_app/pubspec.lock",
        cache_root=network,
    )
    assert (
        "hosted/pub.flutter-io.cn/fixture_pkg-1.2.3/empty"
        in snapshot.directories
    )
    copy = tmp_path / "copied"
    copy_snapshot_tree_with_lock(
        snapshot,
        copy,
        lock_path=repo / "quwoquan_app/pubspec.lock",
        writable=False,
    )
    assert (copy / "hosted/pub.flutter-io.cn/fixture_pkg-1.2.3/empty").is_dir()

    readonly = tmp_path / "readonly-staging"
    nested = readonly / "one/two"
    nested.mkdir(parents=True)
    (nested / "payload").write_text("payload", encoding="ascii")
    for directory in (nested, nested.parent, readonly):
        directory.chmod(0o555)
    remove_private_tree(readonly)
    assert not readonly.exists()


@pytest.mark.skipif(sys.platform != "darwin", reason="APFS clone projection is Darwin-only")
def test_writable_projection_clones_tree_and_normalizes_modes(
    tmp_path: Path,
) -> None:
    repo, archive_sha = _repo(tmp_path)
    source = tmp_path / "source"
    package = source / "hosted/pub.flutter-io.cn/fixture_pkg-1.2.3"
    package.mkdir(parents=True)
    payload = package / "lib.dart"
    payload.write_text("const fixture = true;\n", encoding="utf-8")
    executable = package / "tool.sh"
    executable.write_text("#!/bin/sh\n", encoding="ascii")
    executable.chmod(0o555)
    (package / "empty").mkdir()
    archive = source / "hosted-hashes/pub.flutter-io.cn/fixture_pkg-1.2.3.sha256"
    archive.parent.mkdir(parents=True)
    archive.write_text(archive_sha + "\n", encoding="ascii")
    snapshot = build_pub_cache_snapshot(
        lock_path=repo / "quwoquan_app/pubspec.lock",
        cache_root=source,
        reject_unlocked=True,
    )

    destination = tmp_path / "writable"
    copy_snapshot_tree_with_lock(
        snapshot,
        destination,
        lock_path=repo / "quwoquan_app/pubspec.lock",
        writable=True,
    )

    projected_payload = destination / payload.relative_to(source)
    projected_executable = destination / executable.relative_to(source)
    projected_empty = destination / package.relative_to(source) / "empty"
    assert projected_payload.read_bytes() == payload.read_bytes()
    assert projected_empty.is_dir()
    assert stat.S_IMODE(destination.stat().st_mode) == 0o700
    assert stat.S_IMODE(projected_empty.stat().st_mode) == 0o700
    assert stat.S_IMODE(projected_payload.stat().st_mode) == 0o644
    assert stat.S_IMODE(projected_executable.stat().st_mode) == 0o755
    assert projected_payload.stat().st_ino != payload.stat().st_ino
    assert projected_payload.stat().st_nlink == 1

    source_bytes = payload.read_bytes()
    payload.write_text("const fixture = changed;\n", encoding="utf-8")
    assert projected_payload.read_bytes() == source_bytes


def test_writable_projection_rejects_post_clone_cas_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, archive_sha = _repo(tmp_path)
    source = tmp_path / "source"
    package = source / "hosted/pub.flutter-io.cn/fixture_pkg-1.2.3"
    package.mkdir(parents=True)
    (package / "lib.dart").write_text("const fixture = true;\n", encoding="utf-8")
    archive = source / "hosted-hashes/pub.flutter-io.cn/fixture_pkg-1.2.3.sha256"
    archive.parent.mkdir(parents=True)
    archive.write_text(archive_sha + "\n", encoding="ascii")
    snapshot = build_pub_cache_snapshot(
        lock_path=repo / "quwoquan_app/pubspec.lock",
        cache_root=source,
        reject_unlocked=True,
    )
    original = pub_cache_capsule._clone_writable_snapshot_tree_darwin

    def clone_then_drift(*, snapshot, destination: Path) -> None:
        original(snapshot=snapshot, destination=destination)
        drifted = destination / snapshot.files[0].relative
        drifted.write_bytes(drifted.read_bytes() + b"drift")

    monkeypatch.setattr(
        pub_cache_capsule,
        "_clone_writable_snapshot_tree_darwin",
        clone_then_drift,
    )
    monkeypatch.setattr(pub_cache_capsule.sys, "platform", "darwin")

    with pytest.raises(ValueError):
        copy_snapshot_tree_with_lock(
            snapshot,
            tmp_path / "drifted",
            lock_path=repo / "quwoquan_app/pubspec.lock",
            writable=True,
        )


def test_readonly_projection_does_not_use_darwin_clone_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, archive_sha = _repo(tmp_path)
    source = tmp_path / "source"
    package = source / "hosted/pub.flutter-io.cn/fixture_pkg-1.2.3"
    package.mkdir(parents=True)
    (package / "lib.dart").write_text("const fixture = true;\n", encoding="utf-8")
    archive = source / "hosted-hashes/pub.flutter-io.cn/fixture_pkg-1.2.3.sha256"
    archive.parent.mkdir(parents=True)
    archive.write_text(archive_sha + "\n", encoding="ascii")
    snapshot = build_pub_cache_snapshot(
        lock_path=repo / "quwoquan_app/pubspec.lock",
        cache_root=source,
        reject_unlocked=True,
    )
    monkeypatch.setattr(pub_cache_capsule.sys, "platform", "darwin")
    monkeypatch.setattr(
        pub_cache_capsule,
        "_clone_writable_snapshot_tree_darwin",
        lambda **_kwargs: pytest.fail("readonly projection used writable clone tree"),
    )

    destination = tmp_path / "readonly"
    copy_snapshot_tree_with_lock(
        snapshot,
        destination,
        lock_path=repo / "quwoquan_app/pubspec.lock",
        writable=False,
    )
    assert stat.S_IMODE(destination.stat().st_mode) == 0o555


def test_readonly_projection_normalizes_noncanonical_executable_mode(
    tmp_path: Path,
) -> None:
    repo, archive_sha = _repo(tmp_path)
    source = tmp_path / "source"
    package = source / "hosted/pub.flutter-io.cn/fixture_pkg-1.2.3"
    package.mkdir(parents=True)
    executable = package / "tool/presubmit"
    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\n", encoding="ascii")
    executable.chmod(0o754)
    archive = source / "hosted-hashes/pub.flutter-io.cn/fixture_pkg-1.2.3.sha256"
    archive.parent.mkdir(parents=True)
    archive.write_text(archive_sha + "\n", encoding="ascii")
    snapshot = build_pub_cache_snapshot(
        lock_path=repo / "quwoquan_app/pubspec.lock",
        cache_root=source,
        reject_unlocked=True,
    )

    destination = tmp_path / "readonly"
    copy_snapshot_tree_with_lock(
        snapshot,
        destination,
        lock_path=repo / "quwoquan_app/pubspec.lock",
        writable=False,
    )

    projected = destination / executable.relative_to(source)
    assert projected.read_bytes() == executable.read_bytes()
    assert stat.S_IMODE(projected.stat().st_mode) == 0o555


def test_readonly_projection_rejects_source_executable_class_drift(
    tmp_path: Path,
) -> None:
    repo, archive_sha = _repo(tmp_path)
    source = tmp_path / "source"
    package = source / "hosted/pub.flutter-io.cn/fixture_pkg-1.2.3"
    package.mkdir(parents=True)
    executable = package / "tool/presubmit"
    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\n", encoding="ascii")
    executable.chmod(0o754)
    archive = source / "hosted-hashes/pub.flutter-io.cn/fixture_pkg-1.2.3.sha256"
    archive.parent.mkdir(parents=True)
    archive.write_text(archive_sha + "\n", encoding="ascii")
    snapshot = build_pub_cache_snapshot(
        lock_path=repo / "quwoquan_app/pubspec.lock",
        cache_root=source,
        reject_unlocked=True,
    )
    executable.chmod(0o644)
    destination = tmp_path / "readonly"

    with pytest.raises(ValueError, match="snapshot clone source drifted"):
        copy_snapshot_tree_with_lock(
            snapshot,
            destination,
            lock_path=repo / "quwoquan_app/pubspec.lock",
            writable=False,
        )

    assert not (destination / executable.relative_to(source)).exists()


@pytest.mark.skipif(sys.platform != "darwin", reason="APFS clone projection is Darwin-only")
def test_writable_projection_prunes_canonical_pub_transients_before_replay(
    tmp_path: Path,
) -> None:
    repo, archive_sha = _repo(tmp_path)
    source = tmp_path / "source"
    package = source / "hosted/pub.flutter-io.cn/fixture_pkg-1.2.3"
    package.mkdir(parents=True)
    (package / "lib.dart").write_text("const fixture = true;\n", encoding="utf-8")
    archive = source / "hosted-hashes/pub.flutter-io.cn/fixture_pkg-1.2.3.sha256"
    archive.parent.mkdir(parents=True)
    archive.write_text(archive_sha + "\n", encoding="ascii")
    transient = source / "_temp/downloads/partial.tmp"
    transient.parent.mkdir(parents=True)
    transient.write_bytes(b"partial")
    snapshot = build_pub_cache_snapshot(
        lock_path=repo / "quwoquan_app/pubspec.lock",
        cache_root=source,
        admitted_extra=is_canonical_pub_cache_transient,
    )

    destination = tmp_path / "replay"
    copy_snapshot_tree_with_lock(
        snapshot,
        destination,
        lock_path=repo / "quwoquan_app/pubspec.lock",
        writable=True,
        admitted_extra=is_canonical_pub_cache_transient,
    )

    assert not (destination / "_temp").exists()
    replay = build_pub_cache_snapshot(
        lock_path=repo / "quwoquan_app/pubspec.lock",
        cache_root=destination,
        reject_unlocked=True,
    )
    assert replay.manifest == snapshot.manifest


@pytest.mark.skipif(sys.platform != "darwin", reason="APFS clone projection is Darwin-only")
def test_writable_projection_rejects_unknown_extra_with_transient_policy(
    tmp_path: Path,
) -> None:
    repo, archive_sha = _repo(tmp_path)
    source = tmp_path / "source"
    package = source / "hosted/pub.flutter-io.cn/fixture_pkg-1.2.3"
    package.mkdir(parents=True)
    (package / "lib.dart").write_text("const fixture = true;\n", encoding="utf-8")
    archive = source / "hosted-hashes/pub.flutter-io.cn/fixture_pkg-1.2.3.sha256"
    archive.parent.mkdir(parents=True)
    archive.write_text(archive_sha + "\n", encoding="ascii")
    snapshot = build_pub_cache_snapshot(
        lock_path=repo / "quwoquan_app/pubspec.lock",
        cache_root=source,
        reject_unlocked=True,
    )
    unexpected = source / "unexpected/payload"
    unexpected.parent.mkdir()
    unexpected.write_bytes(b"unclassified")
    destination = tmp_path / "replay"

    with pytest.raises(ValueError, match="contains extra directory: unexpected"):
        copy_snapshot_tree_with_lock(
            snapshot,
            destination,
            lock_path=repo / "quwoquan_app/pubspec.lock",
            writable=True,
            admitted_extra=is_canonical_pub_cache_transient,
        )

    assert not destination.exists()


@pytest.mark.skipif(sys.platform != "darwin", reason="APFS clone projection is Darwin-only")
def test_writable_projection_rejects_unsafe_node_under_admitted_transient(
    tmp_path: Path,
) -> None:
    repo, archive_sha = _repo(tmp_path)
    source = tmp_path / "source"
    package = source / "hosted/pub.flutter-io.cn/fixture_pkg-1.2.3"
    package.mkdir(parents=True)
    (package / "lib.dart").write_text("const fixture = true;\n", encoding="utf-8")
    archive = source / "hosted-hashes/pub.flutter-io.cn/fixture_pkg-1.2.3.sha256"
    archive.parent.mkdir(parents=True)
    archive.write_text(archive_sha + "\n", encoding="ascii")
    snapshot = build_pub_cache_snapshot(
        lock_path=repo / "quwoquan_app/pubspec.lock",
        cache_root=source,
        reject_unlocked=True,
    )
    transient = source / "_temp"
    transient.mkdir()
    (transient / "escape").symlink_to(package, target_is_directory=True)
    destination = tmp_path / "replay"

    with pytest.raises(ValueError, match="directory is unsafe: _temp/escape"):
        copy_snapshot_tree_with_lock(
            snapshot,
            destination,
            lock_path=repo / "quwoquan_app/pubspec.lock",
            writable=True,
            admitted_extra=is_canonical_pub_cache_transient,
        )

    assert not destination.exists()
