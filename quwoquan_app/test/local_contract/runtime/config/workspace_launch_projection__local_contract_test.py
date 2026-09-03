"""Workspace launches freeze source before the canonical launcher reads it."""

# spec_ref: specs/feature-tree/runtime/runtime-config/design.md#dec-003

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from quwoquan_app.scripts.device import prepare_workspace_launch_projection as source
from quwoquan_ops.cli.lib.app_source_capsule import app_source_capsule_roots
from quwoquan_ops.cli.lib.package_reuse.dependency_bundle import (
    AppDependencyBundleStaleError,
)


def _digest(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def test_projection_verifier_rejects_source_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    capsule = output / "attempt/input-capsule"
    projection = output / "attempt/repo"
    capsule_file = capsule / "repo/quwoquan_app/run.sh"
    projected_file = projection / "quwoquan_app/run.sh"
    capsule_file.parent.mkdir(parents=True)
    projected_file.parent.mkdir(parents=True)
    content = b"#!/bin/sh\n"
    capsule_file.write_bytes(content)
    projected_file.write_bytes(content)
    capsule_file.chmod(0o444)
    projected_file.chmod(0o700)
    manifest_path = capsule / "manifest.json"
    manifest_path.write_text("{}\n", encoding="ascii")
    manifest = {
        "entries": [
            {
                "logicalPath": "quwoquan_app/run.sh",
                "capsulePath": "repo/quwoquan_app/run.sh",
                "kind": "file",
                "digest": _digest(content),
                "size": len(content),
                "mode": 0o555,
            }
        ]
    }
    monkeypatch.setattr(
        source,
        "verify_package_input_capsule",
        lambda _root: manifest,
    )

    assert source.verify_workspace_launch_projection(
        output_root=output,
        projection_root=projection,
        source_capsule_manifest=manifest_path,
    ) is manifest

    projected_file.write_bytes(b"tampered\n")
    with pytest.raises(ValueError, match="file_cas_drift"):
        source.verify_workspace_launch_projection(
            output_root=output,
            projection_root=projection,
            source_capsule_manifest=manifest_path,
        )


def test_package_and_workspace_share_one_source_root_closure() -> None:
    roots = app_source_capsule_roots()

    assert roots[:4] == (
        "quwoquan_app",
        "quwoquan_ops",
        "quwoquan_service/contracts/metadata",
        "quwoquan_service/contracts/runtime_errors/packages/dart/quwoquan_runtime_errors",
    )
    assert "quwoquan_service/services" in roots
    assert "quwoquan_service/control-plane/platform-ops" in roots
    assert "quwoquan_service/cmd/service-core/composition.yaml" in roots
    assert len(roots) == len(set(roots))


def test_attempt_root_accepts_canonicalized_output_alias(tmp_path: Path) -> None:
    physical_output = tmp_path / "physical-output"
    output_alias = tmp_path / "output-alias"
    physical_output.mkdir()
    output_alias.symlink_to(physical_output, target_is_directory=True)
    lexical_output = output_alias / "canonical-output"

    attempt = source._safe_attempt_root(
        lexical_output,
        lexical_output / "env/repo/runs/attempt",
    )

    assert attempt.is_dir()
    assert attempt.resolve().is_relative_to(lexical_output.resolve())


def test_attempt_root_rejects_intermediate_symlink_escape(tmp_path: Path) -> None:
    output = tmp_path / "output"
    escape = tmp_path / "escape"
    output.mkdir()
    escape.mkdir()
    (output / "runs").symlink_to(escape, target_is_directory=True)

    with pytest.raises(ValueError, match="workspace_projection_path_unsafe"):
        source._safe_attempt_root(output, output / "runs/attempt")

    assert not (escape / "attempt").exists()


def test_attempt_root_rejects_parent_traversal_without_mutation(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    outside = tmp_path / "outside"

    with pytest.raises(ValueError, match="workspace_projection_path_unsafe"):
        source._safe_attempt_root(output, output / "runs/../../outside/attempt")

    assert not outside.exists()


def _main_args(tmp_path: Path) -> list[str]:
    output = tmp_path / "output"
    return [
        "--output-root",
        str(output),
        "--attempt-root",
        str(output / "env/repo/runs/attempt"),
    ]


def test_stale_failure_emits_machine_envelope_and_typed_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def _raise(**_kwargs: object) -> dict[str, str]:
        raise AppDependencyBundleStaleError("nativeResolutionInputDigest")

    monkeypatch.setattr(source, "prepare_workspace_launch_projection", _raise)

    exit_code = source.main(_main_args(tmp_path))

    captured = capsys.readouterr()
    assert exit_code == 2
    assert json.loads(captured.out) == {
        "status": "failed",
        "errorCode": "APP.DEPENDENCY.bundle_stale",
        "errorField": "nativeResolutionInputDigest",
    }
    stderr_lines = captured.err.splitlines()
    assert stderr_lines[0].startswith("APP.DEPENDENCY.bundle_stale:")
    assert (
        "App dependency bundle is stale for nativeResolutionInputDigest"
        in stderr_lines[0]
    )


def test_generic_failure_is_not_disguised_as_stale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def _raise(**_kwargs: object) -> dict[str, str]:
        raise ValueError("fixture generic failure")

    monkeypatch.setattr(source, "prepare_workspace_launch_projection", _raise)

    exit_code = source.main(_main_args(tmp_path))

    captured = capsys.readouterr()
    assert exit_code == 2
    assert json.loads(captured.out) == {
        "status": "failed",
        "errorCode": "APP.LAUNCH.workspace_projection_failed",
    }
    assert "bundle_stale" not in captured.out
    assert "bundle_stale" not in captured.err
    assert captured.err.splitlines()[0] == (
        "APP.LAUNCH.workspace_projection_failed: fixture generic failure"
    )


def test_typed_failure_envelope_carries_leading_error_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def _raise(**_kwargs: object) -> dict[str, str]:
        raise ValueError("APP.LAUNCH.workspace_projection_not_fresh")

    monkeypatch.setattr(source, "prepare_workspace_launch_projection", _raise)

    exit_code = source.main(_main_args(tmp_path))

    captured = capsys.readouterr()
    assert exit_code == 2
    assert json.loads(captured.out) == {
        "status": "failed",
        "errorCode": "APP.LAUNCH.workspace_projection_not_fresh",
    }
    assert captured.err.splitlines()[0] == (
        "APP.LAUNCH.workspace_projection_not_fresh"
    )


def test_success_stdout_export_protocol_is_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = {
        "projectionRoot": str(tmp_path / "projection/repo"),
        "sourceCapsuleManifest": str(tmp_path / "projection/input-capsule/manifest.json"),
        "sourceRevision": "1" * 40,
        "sourceCapsuleDigest": "sha256:" + "2" * 64,
    }
    monkeypatch.setattr(
        source,
        "prepare_workspace_launch_projection",
        lambda **_kwargs: dict(result),
    )

    exit_code = source.main(_main_args(tmp_path))

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload == result
    # 失败 envelope 依赖 "status" 字段判别；成功导出协议不得携带该字段。
    assert "status" not in payload
    assert captured.err == ""


def test_projection_verifier_rejects_intermediate_symlink_escape(
    tmp_path: Path,
) -> None:
    output = tmp_path / "output"
    escape = tmp_path / "escape"
    capsule = output / "capsule"
    output.mkdir()
    escape.mkdir()
    capsule.mkdir()
    manifest = capsule / "manifest.json"
    manifest.write_text("{}\n", encoding="ascii")
    (output / "projection-link").symlink_to(escape, target_is_directory=True)

    with pytest.raises(ValueError, match="workspace_projection_handoff_unsafe"):
        source.verify_workspace_launch_projection(
            output_root=output,
            projection_root=output / "projection-link",
            source_capsule_manifest=manifest,
        )
