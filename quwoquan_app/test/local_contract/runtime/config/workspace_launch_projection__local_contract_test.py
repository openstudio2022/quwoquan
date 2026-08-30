"""Workspace launches freeze source before the canonical launcher reads it."""

# spec_ref: specs/feature-tree/runtime/runtime-config/design.md#dec-003

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from quwoquan_app.scripts.device import prepare_workspace_launch_projection as source
from quwoquan_ops.cli.lib.app_source_capsule import app_source_capsule_roots


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
