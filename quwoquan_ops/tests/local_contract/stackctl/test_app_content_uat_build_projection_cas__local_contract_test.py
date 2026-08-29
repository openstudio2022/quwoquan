"""Build outputs cannot hide unbound bytes beside an immutable App source capsule."""

# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from quwoquan_ops.cli.commands import app_preflight_uat_launch as launch
from quwoquan_ops.cli.commands import (
    app_preflight_uat_launch_projection_seal as projection_seal,
)
from quwoquan_ops.cli.commands.app_preflight_uat_launch_projection_seal import (
    FLUTTER_ANDROID_3_47_GRADLE_8_14_POLICY_ID,
    FLUTTER_IOS_3_47_COCOAPODS_1_16_POLICY_ID,
    seal_projection_build,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]


def _digest(marker: str) -> str:
    return "sha256:" + marker * 64


def _source_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    source_in_derived_subtree: bool = False,
) -> tuple[Path, Path]:
    capsule = tmp_path / "candidate/input-capsule"
    files = {
        "quwoquan_app/run.sh": b"#!/bin/sh\n",
        "quwoquan_ops/cli/stackctl.py": b"CANDIDATE = True\n",
        "quwoquan_ops/policies/app_build_projection_policy.json": (
            _REPO_ROOT / "quwoquan_ops/policies/app_build_projection_policy.json"
        ).read_bytes(),
        "quwoquan_app/lib/main_prod.dart": b"void main() {}\n",
    }
    if source_in_derived_subtree:
        files["quwoquan_app/.dart_tool/source-owned.json"] = b'{"source":true}\n'
    entries: list[dict[str, object]] = []
    for relative, content in files.items():
        source = capsule / "repo" / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(content)
        mode = 0o555 if relative.endswith(".sh") else 0o444
        source.chmod(mode)
        entries.append(
            {
                "logicalPath": relative,
                "capsulePath": f"repo/{relative}",
                "kind": "file",
                "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
                "size": len(content),
                "mode": mode,
            }
        )
    manifest = {
        "schema": "stackctl-package-input-capsule.v1",
        "baselineId": _digest("a"),
        "sourceRevision": "b" * 40,
        "workspaceStatusDigest": _digest("c"),
        "deploymentInputDigest": _digest("d"),
        "deploymentInputFileCount": len(entries),
        "deploymentInputRoots": [
            "quwoquan_app",
            "quwoquan_ops/cli",
            "quwoquan_ops/environments",
            "quwoquan_ops/policies",
        ],
        "entries": entries,
    }
    manifest_path = capsule / "manifest.json"
    manifest_path.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        launch,
        "verify_package_input_capsule",
        lambda _root: manifest,
    )
    output_root = tmp_path / "output"
    projection = launch.materialize_app_content_launch_projection(
        runtime_binding={
            "candidateDigest": manifest["baselineId"],
            "packageDigest": _digest("e"),
            "sourceRevision": manifest["sourceRevision"],
            "sourceCapsuleWorkspaceStatusDigest": manifest["workspaceStatusDigest"],
            "sourceCapsuleDigest": manifest["deploymentInputDigest"],
            "sourceCapsuleManifestRef": str(manifest_path),
        },
        output_root=output_root,
        projection_root=output_root / "source-projection",
        evidence_path=output_root / "source-projection.json",
    )
    return manifest_path, Path(projection["sourceProjectionRoot"])


def _write(root: Path, relative: str, content: bytes = b"derived\n") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_none_policy_is_zero_derived_nodes_not_ignore_extra_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, projection = _source_projection(tmp_path, monkeypatch)

    sealed = seal_projection_build(manifest_path, projection, policy_id="none")

    assert sealed.derived_entry_count == 0
    (projection / "quwoquan_app/build").mkdir()
    with pytest.raises(ValueError, match="derived output rejected by policy"):
        seal_projection_build(manifest_path, projection, policy_id="none")


def test_ios_policy_seals_source_policy_files_modes_and_raw_symlink_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, projection = _source_projection(tmp_path, monkeypatch)
    plugin_state = _write(
        projection,
        "quwoquan_app/.flutter-plugins-dependencies",
        b'{"plugins":[]}\n',
    )
    _write(projection, "quwoquan_app/.dart_tool/package_config.json")
    pod_manifest = _write(projection, "quwoquan_app/ios/Pods/Manifest.lock")
    plugin_link = projection / "quwoquan_app/ios/.symlinks/plugins/manifest"
    plugin_link.parent.mkdir(parents=True)
    plugin_link.symlink_to(pod_manifest)
    assert plugin_link.resolve() == pod_manifest.resolve()

    first = seal_projection_build(
        manifest_path,
        projection,
        policy_id=FLUTTER_IOS_3_47_COCOAPODS_1_16_POLICY_ID,
    )
    same = seal_projection_build(
        manifest_path,
        projection,
        policy_id=FLUTTER_IOS_3_47_COCOAPODS_1_16_POLICY_ID,
        expected_build_projection_digest=first.build_projection_digest,
    )

    assert first == same
    assert first.derived_entry_count > 0
    assert first.source_projection_digest.startswith("sha256:")
    assert first.derived_output_digest.startswith("sha256:")
    assert first.derived_output_policy_digest.startswith("sha256:")
    plugin_state.chmod(0o600)
    changed = seal_projection_build(
        manifest_path,
        projection,
        policy_id=FLUTTER_IOS_3_47_COCOAPODS_1_16_POLICY_ID,
    )
    assert changed.derived_output_digest != first.derived_output_digest
    assert changed.build_projection_digest != first.build_projection_digest
    with pytest.raises(ValueError, match="build projection digest mismatch"):
        seal_projection_build(
            manifest_path,
            projection,
            policy_id=FLUTTER_IOS_3_47_COCOAPODS_1_16_POLICY_ID,
            expected_build_projection_digest=first.build_projection_digest,
        )


def test_android_policy_admits_flutter_and_gradle_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, projection = _source_projection(tmp_path, monkeypatch)
    _write(projection, "quwoquan_app/.dart_tool/package_config.json")
    _write(projection, "quwoquan_app/android/local.properties")
    _write(projection, "quwoquan_app/build/app/outputs/app.apk")
    _write(projection, "quwoquan_app/android/.gradle/8.14/fileHashes.bin")
    _write(projection, "quwoquan_app/android/.kotlin/sessions/session.bin")
    _write(projection, "quwoquan_app/android/build/reports/problems.html")
    _write(projection, "quwoquan_app/android/app/build/generated/source.txt")

    sealed = seal_projection_build(
        manifest_path,
        projection,
        policy_id=FLUTTER_ANDROID_3_47_GRADLE_8_14_POLICY_ID,
    )

    assert sealed.policy_id == FLUTTER_ANDROID_3_47_GRADLE_8_14_POLICY_ID
    assert sealed.derived_entry_count > 7


def test_android_policy_rejects_new_app_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, projection = _source_projection(tmp_path, monkeypatch)
    _write(
        projection,
        "quwoquan_app/android/app/src/main/kotlin/example/Injected.kt",
    )

    with pytest.raises(ValueError, match="derived output rejected by policy"):
        seal_projection_build(
            manifest_path,
            projection,
            policy_id=FLUTTER_ANDROID_3_47_GRADLE_8_14_POLICY_ID,
        )


def test_source_manifest_wins_even_inside_an_allowed_derived_subtree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, projection = _source_projection(
        tmp_path,
        monkeypatch,
        source_in_derived_subtree=True,
    )
    source_owned = projection / "quwoquan_app/.dart_tool/source-owned.json"
    source_owned.write_text('{"source":false}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="source projection entry CAS mismatch"):
        seal_projection_build(
            manifest_path,
            projection,
            policy_id=FLUTTER_IOS_3_47_COCOAPODS_1_16_POLICY_ID,
        )


def test_policy_is_manifest_owned_candidate_source_not_live_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, projection = _source_projection(tmp_path, monkeypatch)
    projected_policy = (
        projection / "quwoquan_ops/policies/app_build_projection_policy.json"
    )
    projected_policy.write_text('{"schema":"injected"}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="source projection entry CAS mismatch"):
        seal_projection_build(manifest_path, projection, policy_id="none")


def test_seal_rejects_derived_output_changed_during_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, projection = _source_projection(tmp_path, monkeypatch)
    original_inventory = projection_seal._inventory
    calls = 0

    def drifting_inventory(root: Path) -> list[object]:
        nonlocal calls
        calls += 1
        result = original_inventory(root)
        if calls == 1:
            _write(root, "quwoquan_app/build/late-output.bin")
        return result

    monkeypatch.setattr(projection_seal, "_inventory", drifting_inventory)
    with pytest.raises(ValueError, match="tree changed during inventory"):
        seal_projection_build(
            manifest_path,
            projection,
            policy_id=FLUTTER_IOS_3_47_COCOAPODS_1_16_POLICY_ID,
        )


@pytest.mark.parametrize(
    "relative",
    [
        "quwoquan_app/test_host/lib/injected.dart",
        "quwoquan_app/integration_test/injected.dart",
        "quwoquan_app/ios/Runner/Injected.swift",
        "quwoquan_app/.dart_tool/unknown/injected.json",
        "quwoquan_ops/.dart_tool/package_config.json",
    ],
)
def test_ios_policy_rejects_test_sources_runner_sources_and_unknown_dart_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
) -> None:
    manifest_path, projection = _source_projection(tmp_path, monkeypatch)
    _write(projection, relative)

    with pytest.raises(ValueError, match="derived output rejected by policy"):
        seal_projection_build(
            manifest_path,
            projection,
            policy_id=FLUTTER_IOS_3_47_COCOAPODS_1_16_POLICY_ID,
        )


def test_ios_policy_rejects_special_nodes_and_hardlinks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, projection = _source_projection(tmp_path, monkeypatch)
    fifo = projection / "quwoquan_app/build/unsafe.fifo"
    fifo.parent.mkdir(parents=True)
    os.mkfifo(fifo)
    with pytest.raises(ValueError, match="special node"):
        seal_projection_build(
            manifest_path,
            projection,
            policy_id=FLUTTER_IOS_3_47_COCOAPODS_1_16_POLICY_ID,
        )
    fifo.unlink()
    original = _write(projection, "quwoquan_app/build/original.bin")
    os.link(original, projection / "quwoquan_app/build/hardlink.bin")
    with pytest.raises(ValueError, match="hardlink"):
        seal_projection_build(
            manifest_path,
            projection,
            policy_id=FLUTTER_IOS_3_47_COCOAPODS_1_16_POLICY_ID,
        )


def test_ios_policy_rejects_symlinks_outside_the_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, projection = _source_projection(tmp_path, monkeypatch)
    outside = _write(tmp_path, "outside/cache/plugin")
    link = projection / "quwoquan_app/ios/.symlinks/plugins/external"
    link.parent.mkdir(parents=True)
    link.symlink_to(outside)

    with pytest.raises(ValueError, match="symlink escapes build root"):
        seal_projection_build(
            manifest_path,
            projection,
            policy_id=FLUTTER_IOS_3_47_COCOAPODS_1_16_POLICY_ID,
        )


def test_ios_policy_admits_plugin_symlink_to_capsule_projected_pub_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, projection = _source_projection(tmp_path, monkeypatch)
    package = _write(
        projection,
        "quwoquan_app/.dart_tool/qwq_pub_cache/hosted/pub.flutter-io.cn/"
        "plugin-1.0.0/ios/plugin.podspec",
        b"Pod::Spec.new {}\n",
    )
    link = projection / "quwoquan_app/ios/.symlinks/plugins/plugin"
    link.parent.mkdir(parents=True)
    link.symlink_to(package.parent.parent)

    sealed = seal_projection_build(
        manifest_path,
        projection,
        policy_id=FLUTTER_IOS_3_47_COCOAPODS_1_16_POLICY_ID,
    )

    assert sealed.derived_output_digest.startswith("sha256:")
    assert link.resolve().is_relative_to(projection.resolve())
