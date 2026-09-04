"""Test-only builders for the App dependency sync transaction suite."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.commands import app_dependency_sync as sync

PROJECTION_INPUTS = (
    "quwoquan_service/contracts/metadata/_shared/app_artifact_manifest.yaml",
    "quwoquan_service/contracts/metadata/_shared/app_launch_manifest.yaml",
)
PROJECTION_OUTPUTS = (
    (
        "quwoquan_app/android/app/src/runtimeConfigShared/java/fixture/"
        "AppLaunchContract.java"
    ),
    "quwoquan_app/ios/Runner/AppLaunchContract.generated.swift",
    "quwoquan_app/lib/runtime/config/generated/app_launch_contract.g.dart",
    (
        "quwoquan_app/tool/app_launch_contract_codegen/"
        "app_launch_contract.generated.json"
    ),
    "quwoquan_ops/cli/lib/generated/app_launch_contract.py",
)
PROJECTION_MANIFEST = (
    "quwoquan_app/tool/app_launch_contract_codegen/generated_manifest.json"
)


def digest(marker: str) -> str:
    return "sha256:" + marker * 64


def source_identity() -> dict[str, str]:
    return {
        "flutterVersion": "3.47.0",
        "flutterCommandResolutionDigest": digest("a"),
        "productionPubResolutionInputDigest": digest("b"),
        "patrolPubResolutionInputDigest": digest("c"),
        "nativeResolutionInputDigest": digest("d"),
    }


def stub_sync(monkeypatch: Any, output: Path) -> None:
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    monkeypatch.setenv("QWQ_HOST_LOCK_ROOT", str(output / "host-locks"))
    monkeypatch.setattr(
        sync,
        "resolved_flutter_identity",
        lambda _env: {
            "executable": "/fixture/flutter",
            "flutterVersion": "3.47.0",
            "commandResolutionDigest": digest("a"),
        },
    )
    monkeypatch.setattr(sync, "_source_identity", lambda **_kwargs: source_identity())


def _sha256(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def write_projection_closure(
    root: Path,
    *,
    inputs: tuple[str, ...] = PROJECTION_INPUTS,
    outputs: tuple[str, ...] = PROJECTION_OUTPUTS,
) -> dict[str, bytes]:
    """Write one small valid generated-code closure for projection tests."""

    contents: dict[str, bytes] = {}
    for relative in (*inputs, *outputs):
        content = f"fixture closure: {relative}\n".encode()
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        contents[relative] = content
    manifest = {
        "schema": "qwq.app-launch-contract-codegen-manifest",
        "generator": "tools/codegen_app_metadata --app-launch-contract-only",
        "sourceDigest": _sha256(b"fixture source"),
        "inputs": [
            {"path": relative, "sha256": _sha256(contents[relative])}
            for relative in inputs
        ],
        "outputs": [
            {
                "path": relative,
                "sha256": _sha256(contents[relative]),
                "bytes": len(contents[relative]),
            }
            for relative in outputs
        ],
    }
    manifest_path = root / PROJECTION_MANIFEST
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return contents


def minimal_projection_source(root: Path) -> Path:
    app = root / "quwoquan_app"
    (app / "test").mkdir(parents=True)
    (app / "lib").mkdir()
    (app / "lib/main.dart").write_text("void main() {}\n", encoding="utf-8")
    patrol_test = app / "test_host/patrol/test"
    patrol_test.mkdir(parents=True)
    (patrol_test / "canonical").symlink_to("../../../test", target_is_directory=True)
    for generated in (
        app / ".dart_tool/package_config.json",
        app / ".flutter-plugins-dependencies",
        app / "build/output",
        app / "ios/Pods/payload",
        app / "ios/Flutter/Generated.xcconfig",
        app / "ios/Flutter/Flutter.podspec",
    ):
        generated.parent.mkdir(parents=True, exist_ok=True)
        generated.write_text("stale\n", encoding="utf-8")
    service = (
        root / "quwoquan_service/contracts/runtime_errors/packages/dart/"
        "quwoquan_runtime_errors"
    )
    service.mkdir(parents=True)
    (service / "pubspec.yaml").write_text("name: runtime_errors\n", encoding="utf-8")
    write_projection_closure(root)
    return app


def android_failure_fixture(
    root: Path,
) -> tuple[
    sync.DependencyComponentBuildContext,
    Path,
    dict[str, Path],
    dict[str, str],
    Path,
]:
    work, process, generation = root / "work", root / "process", root / "generation"
    for path in (work, process, generation):
        path.mkdir()
    projection = root / "projection"
    for host in (
        projection / "quwoquan_app",
        projection / "quwoquan_app/test_host/patrol",
    ):
        package_config = host / ".dart_tool/package_config.json"
        package_config.parent.mkdir(parents=True)
        package_config.write_text("{}", encoding="utf-8")
    replays = {
        "productionPub": root / "production-replay",
        "patrolPub": root / "patrol-replay",
    }
    for replay in replays.values():
        replay.mkdir()
    context = sync.DependencyComponentBuildContext(
        repo_root=root / "repo",
        attempt_id="a" * 32,
        work_root=work,
        process_root=process,
        generation_root=generation,
        flutter_identity={"executable": "/flutter"},
        source_identity=source_identity(),
    )
    return (
        context,
        projection,
        replays,
        {"productionPub": digest("1"), "patrolPub": digest("2")},
        root / "attempt-trust",
    )


def _dependency(marker: str) -> dict[str, object]:
    return {
        "schema": f"fixture-dependency-{marker}.v1",
        "treeDigest": digest(marker),
        "entryCount": 1,
    }


def _write_manifest(root: Path, manifest: Mapping[str, object]) -> None:
    root.mkdir(parents=True)
    encoded = json.dumps(
        dict(manifest), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    (root / "manifest.json").write_bytes(encoded)


def _manifest_digest(manifest: Mapping[str, object]) -> str:
    declaration = sync.component_declaration(
        snapshot_ref=Path("snapshots/fixture"), manifest=manifest
    )
    return str(declaration["manifestDigest"])


def component_builder(
    mutate: Callable[[dict[str, dict[str, object]]], None] | None = None,
) -> sync.ComponentBuilder:
    def build(
        context: sync.DependencyComponentBuildContext,
    ) -> Mapping[str, Path]:
        source = context.source_identity
        manifests: dict[str, dict[str, object]] = {
            "productionPub": {
                "schema": sync.PUB_CACHE_SYNC_MANIFEST_SCHEMA,
                "flutterVersion": source["flutterVersion"],
                "flutterCommandResolutionDigest": source[
                    "flutterCommandResolutionDigest"
                ],
                "resolutionInputDigest": source["productionPubResolutionInputDigest"],
                "dependency": _dependency("1"),
            },
            "patrolPub": {
                "schema": sync.PATROL_PUB_SYNC_MANIFEST_SCHEMA,
                "flutterVersion": source["flutterVersion"],
                "flutterCommandResolutionDigest": source[
                    "flutterCommandResolutionDigest"
                ],
                "resolutionInputDigest": source["patrolPubResolutionInputDigest"],
                "dependency": _dependency("2"),
            },
        }
        production_digest = _manifest_digest(manifests["productionPub"])
        patrol_digest = _manifest_digest(manifests["patrolPub"])
        manifests.update(
            {
                "productionIosPods": {
                    "schema": sync.IOS_POD_CAPSULE_SCHEMA,
                    "dependencyHost": sync.IOS_POD_PRODUCTION_HOST,
                    "nativeDependencyMode": sync.IOS_NATIVE_DEPENDENCY_MODE,
                    "upstreamDependencyDigest": production_digest,
                    "treeDigest": digest("3"),
                    "entryCount": 3,
                },
                "patrolIosPods": {
                    "schema": sync.IOS_POD_CAPSULE_SCHEMA,
                    "dependencyHost": sync.IOS_POD_PATROL_HOST,
                    "nativeDependencyMode": sync.IOS_NATIVE_DEPENDENCY_MODE,
                    "upstreamDependencyDigest": patrol_digest,
                    "treeDigest": digest("4"),
                    "entryCount": 4,
                },
                "androidGradle": {
                    "schema": sync.ANDROID_GRADLE_SYNC_SCHEMA,
                    "nativeResolutionInputDigest": source[
                        "nativeResolutionInputDigest"
                    ],
                    "upstreamDependencyDigests": {
                        "productionPub": production_digest,
                        "patrolPub": patrol_digest,
                    },
                    "dependency": _dependency("5"),
                },
            }
        )
        if mutate is not None:
            mutate(manifests)
        roots: dict[str, Path] = {}
        for name in sync.APP_DEPENDENCY_COMPONENTS:
            root = context.generation_root / name
            _write_manifest(root, manifests[name])
            roots[name] = root
        return roots

    return build
